"""ChurnPulse streaming job (PyFlink DataStream API).

customer-events (Kafka)
   -> parse + event-time watermarks
   -> key by customer_id
   -> ScoreCustomer: keeps each customer's live profile and recent-event window
      in Flink keyed state (checkpointed), applies the event, re-scores with
      the trained model and emits a prediction with reasons and signals
   -> churn-predictions (Kafka)
   -> 10-second tumbling window over all predictions -> churn-stats (Kafka)
"""

from __future__ import annotations

import json
import logging
import os
import time

from pyflink.common import Configuration, Duration, Types, WatermarkStrategy
from pyflink.common.serialization import SimpleStringSchema
from pyflink.common.time import Time
from pyflink.common.watermark_strategy import TimestampAssigner
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.base import DeliveryGuarantee
from pyflink.datastream.connectors.kafka import (
    KafkaOffsetsInitializer,
    KafkaRecordSerializationSchema,
    KafkaSink,
    KafkaSource,
)
from pyflink.datastream.functions import KeyedProcessFunction, ProcessAllWindowFunction, RuntimeContext
from pyflink.datastream.state import ValueStateDescriptor
from pyflink.datastream.window import TumblingProcessingTimeWindows

BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092")
EVENTS_TOPIC = os.environ.get("EVENTS_TOPIC", "customer-events")
PREDICTIONS_TOPIC = os.environ.get("PREDICTIONS_TOPIC", "churn-predictions")
STATS_TOPIC = os.environ.get("STATS_TOPIC", "churn-stats")
SIGNAL_WINDOW_MS = int(os.environ.get("SIGNAL_WINDOW_MS", 10 * 60 * 1000))  # 10 minutes
RAPID_RISE = float(os.environ.get("RAPID_RISE", 0.15))
PARALLELISM = int(os.environ.get("JOB_PARALLELISM", 2))


class EventTime(TimestampAssigner):
    def extract_timestamp(self, value, record_timestamp) -> int:
        try:
            return int(json.loads(value)["event_time"])
        except Exception:  # malformed record: fall back to Kafka's timestamp
            return record_timestamp


class ScoreCustomer(KeyedProcessFunction):
    """Stateful per-customer scoring."""

    def open(self, runtime_context: RuntimeContext):
        from churnpulse.events import apply_event, is_downgrade
        from churnpulse.predict import ChurnModel

        self.apply_event, self.is_downgrade = apply_event, is_downgrade
        self.model = ChurnModel(os.environ["CHURNPULSE_MODELS"])  # profile + survey models
        self.profile = runtime_context.get_state(ValueStateDescriptor("profile", Types.STRING()))
        self.last_probability = runtime_context.get_state(ValueStateDescriptor("last_p", Types.DOUBLE()))
        self.recent = runtime_context.get_state(ValueStateDescriptor("recent", Types.STRING()))

    def process_element(self, value, ctx: KeyedProcessFunction.Context):
        received = time.time() * 1000
        try:
            event = json.loads(value)
        except json.JSONDecodeError:
            logging.warning("dropping malformed event: %s", value[:200])
            return

        stored = self.profile.value()
        if stored is None and event["event_type"] != "snapshot":
            logging.warning("no profile yet for %s, event skipped", event.get("customer_id"))
            return
        before = json.loads(stored) if stored else None

        downgrade = before is not None and self.is_downgrade(before, event)
        try:
            after = self.apply_event(before or {}, event)
            is_snapshot = event["event_type"] == "snapshot"
            # Reasons cost ~20 ms; the initial load of every customer skips them.
            scored = self.model.predict(after, explain=not is_snapshot)
        except Exception as exc:  # never let one bad event stop the stream
            logging.exception("scoring failed for %s: %s", event.get("customer_id"), exc)
            return
        self.profile.update(json.dumps(after))

        # Sliding signal window kept in state: (event_time, was_downgrade).
        now = int(event["event_time"])
        recent = [r for r in json.loads(self.recent.value() or "[]") if now - r[0] <= SIGNAL_WINDOW_MS]
        if not is_snapshot:
            recent.append([now, int(downgrade)])
        self.recent.update(json.dumps(recent))

        previous = self.last_probability.value()
        probability = scored["churn_probability"]
        self.last_probability.update(probability)

        alert = None
        if not is_snapshot and previous is not None:
            if scored["will_churn"] and previous < scored["threshold"]:
                alert = "crossed_threshold"
            elif probability - previous >= RAPID_RISE:
                alert = "rapid_rise"

        yield json.dumps({
            "customer_id": event["customer_id"],
            "event_id": event["event_id"],
            "event_type": event["event_type"],
            "event_source": event.get("source"),
            "event_time": now,
            "scored_at": int(time.time() * 1000),
            "processing_ms": round(time.time() * 1000 - received, 2),
            "probability": probability,
            "previous_probability": previous,
            "delta": None if previous is None else round(probability - previous, 4),
            "risk_band": scored["risk_band"],
            "will_churn": scored["will_churn"],
            "threshold": scored["threshold"],
            "reasons": scored.get("reasons", []),
            "signals": {
                "events_10m": len(recent),
                "downgrades_10m": sum(r[1] for r in recent),
                "was_downgrade": downgrade,
            },
            "alert": alert,
            "profile": after,
            "model": scored["model"],
            "model_used": scored["model_used"],
        })


class StreamStats(ProcessAllWindowFunction):
    """Throughput and risk summary for each 10-second window."""

    def process(self, context: ProcessAllWindowFunction.Context, elements):
        rows = [json.loads(e) for e in elements]
        live = [r for r in rows if r["event_type"] != "snapshot"]
        yield json.dumps({
            "window_end": context.window().end,
            "predictions": len(rows),
            "live_events": len(live),
            "alerts": sum(1 for r in live if r["alert"]),
            "high_risk": sum(1 for r in rows if r["risk_band"] == "high"),
            "avg_probability": round(sum(r["probability"] for r in rows) / len(rows), 4) if rows else None,
            "avg_processing_ms": (round(sum(r["processing_ms"] for r in rows) / len(rows), 2)
                                  if rows else None),
        })


def kafka_sink(topic: str) -> KafkaSink:
    return (
        KafkaSink.builder()
        .set_bootstrap_servers(BOOTSTRAP)
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic(topic)
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        )
        .set_delivery_guarantee(DeliveryGuarantee.AT_LEAST_ONCE)
        .build()
    )


def main() -> None:
    # Latency settings belong to the job, so they are set here: they would be
    # ignored on the cluster. PyFlink batches records for Python operators and
    # flushes a batch after `bundle.time` - the default of 1 s added ~1 s per
    # Python operator (2 in this job) to every prediction.
    conf = Configuration()
    conf.set_string("python.fn-execution.bundle.time", os.environ.get("BUNDLE_TIME_MS", "20"))
    conf.set_string("python.fn-execution.bundle.size", "500")
    env = StreamExecutionEnvironment.get_execution_environment(conf)
    env.set_parallelism(PARALLELISM)
    env.set_buffer_timeout(10)
    env.enable_checkpointing(30_000)

    source = (
        KafkaSource.builder()
        .set_bootstrap_servers(BOOTSTRAP)
        .set_topics(EVENTS_TOPIC)
        .set_group_id("churnpulse-flink")
        .set_starting_offsets(KafkaOffsetsInitializer.earliest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )
    watermarks = (
        WatermarkStrategy.for_bounded_out_of_orderness(Duration.of_seconds(5))
        .with_timestamp_assigner(EventTime())
        .with_idleness(Duration.of_seconds(30))
    )

    events = env.from_source(source, watermarks, "customer-events")
    predictions = (
        events.key_by(lambda raw: json.loads(raw)["customer_id"], key_type=Types.STRING())
        .process(ScoreCustomer(), output_type=Types.STRING())
        .name("score-customer")
    )
    predictions.sink_to(kafka_sink(PREDICTIONS_TOPIC)).name("churn-predictions")

    (
        predictions.window_all(TumblingProcessingTimeWindows.of(Time.seconds(10)))
        .process(StreamStats(), output_type=Types.STRING())
        .name("stream-stats")
        .sink_to(kafka_sink(STATS_TOPIC))
        .name("churn-stats")
    )

    env.execute("churnpulse-realtime-scoring")


if __name__ == "__main__":
    main()
