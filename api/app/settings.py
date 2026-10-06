"""Service configuration from environment variables (12-factor style)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.environ.get("DATABASE_URL", "postgresql://churnpulse:churnpulse@localhost:5432/churnpulse")
    kafka_bootstrap: str = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9094")
    events_topic: str = os.environ.get("EVENTS_TOPIC", "customer-events")
    predictions_topic: str = os.environ.get("PREDICTIONS_TOPIC", "churn-predictions")
    stats_topic: str = os.environ.get("STATS_TOPIC", "churn-stats")
    consumer_group: str = os.environ.get("CONSUMER_GROUP", "churnpulse-api")
    start_consumer: bool = os.environ.get("START_CONSUMER", "true").lower() == "true"
    cors_origins: str = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173")


settings = Settings()
