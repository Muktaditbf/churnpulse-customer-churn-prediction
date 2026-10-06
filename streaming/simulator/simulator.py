"""Live customer event simulator.

1. Loads the 7,043 IBM Telco v11 customers (with names and persona data)
   into PostgreSQL - the customer master data.
2. Publishes one ``snapshot`` event per customer so Flink knows every profile.
3. Streams realistic events (billing, usage, services, price, surveys, ...)
   to Kafka at EVENTS_PER_SEC.

On restart it continues from each customer's live profile (as computed by
Flink and stored by the API), so new events are always real changes.
"""

from __future__ import annotations

import json
import logging
import os
import random
import signal
import time

import pandas as pd
import psycopg
from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient

from churnpulse.events import apply_event, new_event, random_event
from churnpulse.features import PROFILE_FIELDS

BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9094")
TOPIC = os.environ.get("EVENTS_TOPIC", "customer-events")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://churnpulse:churnpulse@localhost:5432/churnpulse")
DATA_PATH = os.environ.get("DATA_PATH", "data/processed/customers.csv")
EVENTS_PER_SEC = float(os.environ.get("EVENTS_PER_SEC", 4))
SEED = int(os.environ.get("SIMULATOR_SEED", 7))

log = logging.getLogger("simulator")
running = True


def stop(*_):
    global running
    running = False


def wait_for_kafka(admin: AdminClient, timeout: int = 120) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if TOPIC in admin.list_topics(timeout=5).topics:
                return
        except Exception:  # broker still starting
            pass
        log.info("waiting for Kafka topic %s ...", TOPIC)
        time.sleep(3)
    raise TimeoutError("Kafka topic not available")


def to_profile(row: dict) -> dict:
    """A CSV row -> a JSON-safe profile (no NaN, native types)."""
    profile = {}
    for field in PROFILE_FIELDS:
        value = row.get(field)
        if isinstance(value, float) and pd.isna(value):
            value = None
        elif hasattr(value, "item"):
            value = value.item()
        profile[field] = value
    profile["zip_code"] = str(profile["zip_code"])
    if profile["satisfaction_score"] is not None:
        profile["satisfaction_score"] = int(profile["satisfaction_score"])
    return profile


def load_customers() -> pd.DataFrame:
    return pd.read_csv(DATA_PATH, dtype={"zip_code": str})


def customers_loaded() -> bool:
    with psycopg.connect(DATABASE_URL) as conn:
        return conn.execute("SELECT count(*) FROM customers WHERE source = 'dataset'").fetchone()[0] > 0


def save_customers(df: pd.DataFrame, profiles: dict[str, dict]) -> None:
    cols = ["customer_id", "name", "email", "phone", "city", "zip_code", "profile", "cltv", "actual_churn", "source"]
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn, conn.cursor() as cur:
        with cur.copy(f"COPY customers_staging ({', '.join(cols)}) FROM STDIN") as copy:
            for row in df.to_dict(orient="records"):
                cid = row["customer_id"]
                copy.write_row((cid, row["name"], row["email"], row["phone"], row["city"], str(row["zip_code"]),
                                json.dumps(profiles[cid]), float(row["cltv"]), bool(row["churned"]), "dataset"))
        cur.execute(f"""
            INSERT INTO customers ({', '.join(cols)})
            SELECT {', '.join(cols)} FROM customers_staging
            ON CONFLICT (customer_id) DO NOTHING""")
        cur.execute("TRUNCATE customers_staging")
    log.info("saved %d customers to PostgreSQL", len(df))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    wait_for_kafka(AdminClient({"bootstrap.servers": BOOTSTRAP}))
    producer = Producer({"bootstrap.servers": BOOTSTRAP, "linger.ms": 20, "acks": "all",
                         "enable.idempotence": True})

    df = load_customers()
    profiles = {row["customer_id"]: to_profile(row) for row in df.to_dict(orient="records")}

    def send(event: dict) -> None:
        producer.produce(TOPIC, key=event["customer_id"], value=json.dumps(event))

    if not customers_loaded():
        save_customers(df, profiles)
        for cid, profile in profiles.items():
            send(new_event(cid, "snapshot", profile))
        producer.flush()
        log.info("published %d snapshot events", len(profiles))
    else:
        # Continue from the live profiles Flink computed (stored by the API).
        with psycopg.connect(DATABASE_URL) as conn:
            for cid, profile in conn.execute("SELECT customer_id, profile FROM customer_scores"):
                if cid in profiles:
                    profiles[cid] = profile
        log.info("customers already loaded - continuing from their live profiles")

    rng = random.Random(SEED)
    ids = list(profiles)
    sent, started = 0, time.time()
    while running:
        cid = rng.choice(ids)
        event = random_event(cid, profiles[cid], rng)
        profiles[cid] = apply_event(profiles[cid], event)
        send(event)
        producer.poll(0)
        sent += 1
        if sent % 200 == 0:
            log.info("%d live events sent (%.1f/s)", sent, sent / (time.time() - started))
        time.sleep(rng.expovariate(EVENTS_PER_SEC))
    producer.flush()
    log.info("stopped after %d live events", sent)


if __name__ == "__main__":
    main()
