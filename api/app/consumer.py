"""Kafka -> PostgreSQL + WebSocket bridge.

Runs in a background thread. Reads Flink's predictions and stats, writes them
to PostgreSQL in batches and forwards live events to connected dashboards.

Delivery is at-least-once: offsets are committed only after the database
commit, and every write is idempotent (upsert / ON CONFLICT DO NOTHING on the
event id), so a replay after a crash never double-counts anything.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from datetime import UTC, datetime

from confluent_kafka import Consumer, KafkaError
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from . import metrics
from .settings import settings

log = logging.getLogger("churnpulse.consumer")

UPSERT_SCORE = """
INSERT INTO customer_scores (customer_id, probability, previous_probability, risk_band, will_churn, model_used,
                             reasons, signals, profile, monthly_charges, last_event_type, alert, updated_at)
VALUES (%(customer_id)s, %(probability)s, %(previous_probability)s, %(risk_band)s, %(will_churn)s,
        %(model_used)s, %(reasons)s, %(signals)s, %(profile)s, %(monthly)s, %(event_type)s, %(alert)s,
        %(scored)s)
ON CONFLICT (customer_id) DO UPDATE SET
    probability = EXCLUDED.probability, previous_probability = EXCLUDED.previous_probability,
    risk_band = EXCLUDED.risk_band, will_churn = EXCLUDED.will_churn, model_used = EXCLUDED.model_used,
    reasons = CASE WHEN jsonb_array_length(EXCLUDED.reasons) > 0 THEN EXCLUDED.reasons
                   ELSE customer_scores.reasons END,
    signals = EXCLUDED.signals, profile = EXCLUDED.profile, monthly_charges = EXCLUDED.monthly_charges,
    last_event_type = EXCLUDED.last_event_type, alert = EXCLUDED.alert, updated_at = EXCLUDED.updated_at
WHERE customer_scores.updated_at <= EXCLUDED.updated_at
"""

INSERT_EVENT = """
INSERT INTO prediction_events (customer_id, event_id, event_type, event_source, probability,
                               previous_probability, risk_band, model_used, alert, reasons, end_to_end_ms,
                               created_at)
VALUES (%(customer_id)s, %(event_id)s, %(event_type)s, %(event_source)s, %(probability)s,
        %(previous_probability)s, %(risk_band)s, %(model_used)s, %(alert)s, %(reasons)s, %(e2e)s, %(scored)s)
ON CONFLICT (event_id) DO NOTHING
"""

UPSERT_STATS = """
INSERT INTO stream_stats (window_end, predictions, live_events, alerts, high_risk,
                          avg_probability, avg_processing_ms)
VALUES (%(window_end)s, %(predictions)s, %(live_events)s, %(alerts)s, %(high_risk)s,
        %(avg_probability)s, %(avg_processing_ms)s)
ON CONFLICT (window_end) DO NOTHING
"""


def _ts(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


class LiveHub:
    """Fan-out of live messages to every connected WebSocket."""

    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.queues: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self.queues.add(queue)
        metrics.WS_CLIENTS.set(len(self.queues))
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self.queues.discard(queue)
        metrics.WS_CLIENTS.set(len(self.queues))

    def publish(self, message: dict) -> None:
        """Called from the consumer thread; hands the message to the event loop."""
        if self.loop is None:
            return
        self.loop.call_soon_threadsafe(self._fan_out, message)

    def _fan_out(self, message: dict) -> None:
        for queue in list(self.queues):
            if queue.full():          # a slow browser must not block everyone else
                queue.get_nowait()
            queue.put_nowait(message)


hub = LiveHub()


def compact(p: dict, name: str | None = None) -> dict:
    """The small version of a prediction sent to browsers."""
    profile = p["profile"]
    return {
        "customer_id": p["customer_id"],
        "name": name,
        "model_used": p.get("model_used"),
        "event_type": p["event_type"],
        "event_source": p.get("event_source"),
        "probability": p["probability"],
        "previous_probability": p["previous_probability"],
        "delta": p["delta"],
        "risk_band": p["risk_band"],
        "will_churn": p["will_churn"],
        "alert": p["alert"],
        "reasons": p["reasons"][:3],
        "signals": p["signals"],
        "contract": profile["contract"],
        "tenure": profile["tenure_months"],
        "monthly_charges": profile["monthly_charge"],
        "city": profile.get("city"),
        "scored_at": p["scored_at"],
    }


class PredictionConsumer(threading.Thread):
    def __init__(self, pool: ConnectionPool):
        super().__init__(name="kafka-consumer", daemon=True)
        self.pool = pool
        self.stop_event = threading.Event()
        self.connected = False
        self.snapshots_seen = 0
        self.names: dict[str, str] = {}

    def run(self) -> None:
        consumer = Consumer({
            "bootstrap.servers": settings.kafka_bootstrap,
            "group.id": settings.consumer_group,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        })
        consumer.subscribe([settings.predictions_topic, settings.stats_topic])
        log.info("consuming %s and %s", settings.predictions_topic, settings.stats_topic)
        try:
            while not self.stop_event.is_set():
                messages = consumer.consume(num_messages=500, timeout=0.1)
                if not messages:
                    continue
                self.connected = True
                predictions, stats = [], []
                for msg in messages:
                    if msg.error():
                        if msg.error().code() != KafkaError._PARTITION_EOF:
                            log.warning("kafka error: %s", msg.error())
                        continue
                    try:
                        payload = json.loads(msg.value())
                    except json.JSONDecodeError:
                        metrics.BAD_MESSAGES.inc()
                        continue
                    (stats if msg.topic() == settings.stats_topic else predictions).append(payload)
                self._store(predictions, stats)
                consumer.commit(asynchronous=True)
                self._broadcast(predictions, stats)
        except Exception:  # keep the service alive; health check reports the problem
            log.exception("consumer crashed")
            self.connected = False
        finally:
            consumer.close()

    def _store(self, predictions: list[dict], stats: list[dict]) -> None:
        now_ms = time.time() * 1000
        score_rows, event_rows = {}, []
        for p in predictions:
            e2e = now_ms - p["event_time"]
            row = {
                **p,
                "reasons": Jsonb(p["reasons"]),
                "signals": Jsonb(p["signals"]),
                "profile": Jsonb(p["profile"]),
                "monthly": p["profile"]["monthly_charge"],
                "scored": _ts(p["scored_at"]),
                "e2e": round(e2e, 1),
            }
            score_rows[p["customer_id"]] = row       # only the newest per customer
            event_rows.append(row)
            if p["event_type"] != "snapshot":
                metrics.END_TO_END.observe(e2e / 1000)
                metrics.FLINK_PROCESSING.observe(p["processing_ms"] / 1000)
                if p["alert"]:
                    metrics.ALERTS.labels(p["alert"]).inc()
            metrics.PREDICTIONS.labels("snapshot" if p["event_type"] == "snapshot" else "live").inc()
        with self.pool.connection() as conn, conn.cursor() as cur:
            live_ids = list({p["customer_id"] for p in predictions if p["event_type"] != "snapshot"})
            if live_ids:
                cur.execute("SELECT customer_id, name FROM customers WHERE customer_id = ANY(%s)", (live_ids,))
                self.names.update({row["customer_id"]: row["name"] for row in cur.fetchall()})
            if score_rows:
                cur.executemany(UPSERT_SCORE, list(score_rows.values()))
                cur.executemany(INSERT_EVENT, event_rows)
            for s in stats:
                cur.execute(UPSERT_STATS, {**s, "window_end": _ts(s["window_end"])})

    def _broadcast(self, predictions: list[dict], stats: list[dict]) -> None:
        live = [p for p in predictions if p["event_type"] != "snapshot"]
        snapshots = len(predictions) - len(live)
        if snapshots:
            self.snapshots_seen += snapshots
            hub.publish({"type": "snapshot_progress", "scored": self.snapshots_seen})
        for p in live[-50:]:
            hub.publish({"type": "prediction", "data": compact(p, self.names.get(p["customer_id"]))})
        for s in stats:
            hub.publish({"type": "stats", "data": s})
