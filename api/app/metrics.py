"""Prometheus metrics exposed at /metrics and graphed in Grafana."""

from prometheus_client import Counter, Gauge, Histogram

LATENCY_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30)

PREDICTIONS = Counter("churnpulse_predictions_total", "Predictions received from Flink", ["kind"])
ALERTS = Counter("churnpulse_alerts_total", "Churn alerts raised", ["alert"])
BAD_MESSAGES = Counter("churnpulse_bad_messages_total", "Unparseable Kafka messages")
END_TO_END = Histogram("churnpulse_end_to_end_seconds",
                       "Event created -> prediction stored", buckets=LATENCY_BUCKETS)
FLINK_PROCESSING = Histogram("churnpulse_flink_processing_seconds",
                             "Time Flink spent scoring one event", buckets=LATENCY_BUCKETS)
API_PREDICT = Histogram("churnpulse_api_predict_seconds", "On-demand /predict latency",
                        buckets=LATENCY_BUCKETS)
WS_CLIENTS = Gauge("churnpulse_websocket_clients", "Connected dashboard clients")
