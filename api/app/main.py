"""ChurnPulse API: customers, predictions, retention actions and the live feed."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import random
import string
import time
from contextlib import asynccontextmanager

import pandas as pd
from confluent_kafka import Producer
from fastapi import FastAPI, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from prometheus_client import make_asgi_app
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from pydantic import ValidationError

from churnpulse import config
from churnpulse.actions import ACTIONS_BY_ID, recommend, recommend_many
from churnpulse.events import EVENT_LABELS, diff_to_events, new_event, scenario
from churnpulse.features import CATEGORIES, CHOICES, build_features
from churnpulse.predict import ChurnModel

from . import metrics
from .consumer import PredictionConsumer, hub
from .schemas import CHANNELS, LIFESTYLES, ActionUpdate, CustomerIn, Prediction
from .settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("churnpulse.api")

state: dict = {}


def _load_cities() -> dict[str, dict]:
    """City name -> typical latitude/longitude/population/zip, for easy data entry."""
    path = config.CUSTOMERS_CSV
    if not path.exists():
        return {}
    df = pd.read_csv(path, usecols=["city", "zip_code", "latitude", "longitude", "population"],
                     dtype={"zip_code": str})
    grouped = df.groupby("city").agg(latitude=("latitude", "mean"), longitude=("longitude", "mean"),
                                     population=("population", "max"), zip_code=("zip_code", "first"))
    return {city.lower(): {"city": city, **{k: (round(v, 6) if isinstance(v, float) else v)
                                            for k, v in row.items()}}
            for city, row in grouped.to_dict(orient="index").items()}


@asynccontextmanager
async def lifespan(app: FastAPI):
    model = ChurnModel()
    for m in model.models.values():
        _ = m.explainer  # build explainers once, not on the first request
    state["model"] = model
    state["card"] = json.loads(config.MODEL_CARD_PATH.read_text())
    state["cities"] = _load_cities()
    state["pool"] = ConnectionPool(settings.database_url, min_size=2, max_size=10,
                                   kwargs={"row_factory": dict_row}, open=True)
    state["producer"] = Producer({"bootstrap.servers": settings.kafka_bootstrap})
    hub.loop = asyncio.get_running_loop()
    if settings.start_consumer:
        state["consumer"] = PredictionConsumer(state["pool"])
        state["consumer"].start()
    log.info("API ready: profile=%s survey=%s", model.profile.model_name, model.survey.model_name)
    yield
    if "consumer" in state:
        state["consumer"].stop_event.set()
    state["producer"].flush(5)
    state["pool"].close()


app = FastAPI(
    title="ChurnPulse API",
    version="2.0.0",
    description="Real-time customer churn prediction with persona data, retention actions and a live feed.",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","),
                   allow_methods=["*"], allow_headers=["*"])
app.mount("/metrics", make_asgi_app())


def query(sql: str, params: dict | tuple | None = None, one: bool = False):
    with state["pool"].connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        if cur.description is None:
            return None
        return cur.fetchone() if one else cur.fetchall()


def publish(events: list[dict]) -> None:
    for event in events:
        state["producer"].produce(settings.events_topic, key=event["customer_id"], value=json.dumps(event))
    state["producer"].flush(5)


def new_customer_id() -> str:
    """Same shape as the dataset's ids, e.g. 4821-QXLZA."""
    while True:
        cid = f"{random.randint(1000, 9999)}-{''.join(random.choices(string.ascii_uppercase, k=5))}"
        if query("SELECT 1 FROM customers WHERE customer_id = %s", (cid,), one=True) is None:
            return cid


def thresholds() -> dict:
    return {kind: m.threshold for kind, m in state["model"].models.items()}


# ------------------------------------------------------------------ health, model, metadata
@app.get("/api/health", tags=["ops"])
def health():
    db_ok = True
    try:
        query("SELECT 1", one=True)
    except Exception:
        db_ok = False
    consumer = state.get("consumer")
    return {"status": "ok" if db_ok else "degraded", "database": db_ok,
            "stream_consumer": bool(consumer and consumer.is_alive()),
            "models": {k: m.model_name for k, m in state["model"].models.items()}}


@app.get("/api/model", tags=["model"])
def model_card():
    return state["card"]


@app.get("/api/meta", tags=["model"])
def meta():
    """Choices and lookups the customer forms need."""
    return {
        "choices": CHOICES | {"lifestyle": LIFESTYLES, "preferred_channel": CHANNELS},
        "categories": CATEGORIES,
        "cities": sorted(state["cities"].values(), key=lambda c: c["city"]),
        "event_labels": EVENT_LABELS,
        "thresholds": thresholds(),
        "risk_bands": config.RISK_BANDS,
    }


# ------------------------------------------------------------------ predictions
@app.post("/api/predict", tags=["predict"])
def predict(customer: CustomerIn):
    """Score any persona profile instantly (used by the add-customer preview)."""
    start = time.perf_counter()
    profile = customer.to_profile(state["cities"])
    result = state["model"].predict(profile, explain=True)
    actions = recommend(state["model"], profile, customer.persona()) if result["will_churn"] else []
    metrics.API_PREDICT.observe(time.perf_counter() - start)
    return {**Prediction(**result).model_dump(), "actions": actions, "profile": profile}


@app.post("/api/predict/batch", tags=["predict"])
async def predict_batch(file: UploadFile = File(...)):
    """Upload a CSV of customers (template columns) and download it scored."""
    rows = _read_csv(await file.read())
    out = []
    for i, row in enumerate(rows, start=2):
        try:
            customer = CustomerIn.from_flat(row)
            r = state["model"].predict(customer.to_profile(state["cities"]), explain=True)
            out.append({**row, "churn_probability": r["churn_probability"], "risk_band": r["risk_band"],
                        "will_churn": r["will_churn"], "model_used": r["model_used"],
                        "top_reason": r["reasons"][0]["feature"] if r["reasons"] else "", "error": ""})
        except ValidationError as exc:
            out.append({**row, "error": f"row {i}: " + "; ".join(e["msg"] for e in exc.errors())})
    fieldnames = list(dict.fromkeys(k for row in out for k in row))
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, restval="")
    writer.writeheader()
    writer.writerows(out)
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=churnpulse_scored.csv"})


# ------------------------------------------------------------------ dashboard data
@app.get("/api/stats", tags=["dashboard"])
def stats():
    months = config.MONTHS_OF_VALUE
    totals = query(f"""
        SELECT count(*)                                              AS customers_scored,
               count(*) FILTER (WHERE s.risk_band = 'high')          AS high_risk,
               count(*) FILTER (WHERE s.risk_band = 'medium')        AS medium_risk,
               count(*) FILTER (WHERE s.risk_band = 'low')           AS low_risk,
               count(*) FILTER (WHERE s.will_churn)                  AS flagged,
               count(*) FILTER (WHERE s.model_used = 'survey')       AS survey_scored,
               avg(s.probability)                                    AS avg_probability,
               sum(s.probability * s.monthly_charges * {months})     AS expected_revenue_at_risk,
               sum(s.probability * c.cltv)                           AS cltv_at_risk,
               count(*) FILTER (WHERE c.source <> 'dataset')         AS new_members
        FROM customer_scores s JOIN customers c USING (customer_id)
        WHERE NOT c.archived""", one=True)
    live = query("""
        SELECT count(*) FILTER (WHERE created_at > now() - interval '1 minute')   AS events_last_minute,
               count(*) FILTER (WHERE alert IS NOT NULL
                                AND created_at > now() - interval '1 hour')        AS alerts_last_hour,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY end_to_end_ms)
                   FILTER (WHERE created_at > now() - interval '1 minute')         AS p50_latency_ms,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY end_to_end_ms)
                   FILTER (WHERE created_at > now() - interval '1 minute')         AS p95_latency_ms
        FROM prediction_events
        WHERE event_type <> 'snapshot' AND created_at > now() - interval '1 hour'""", one=True)
    timeline = query("""
        SELECT window_end, live_events, alerts, high_risk, avg_probability, avg_processing_ms
        FROM stream_stats WHERE window_end > now() - interval '30 minutes' ORDER BY window_end""")
    distribution = query("""
        SELECT width_bucket(probability, 0, 1, 20) AS bucket, count(*) AS customers
        FROM customer_scores GROUP BY 1 ORDER BY 1""")
    actions = query("""
        SELECT count(*) FILTER (WHERE status = 'accepted') AS accepted,
               count(*) FILTER (WHERE status = 'contacted') AS contacted,
               coalesce(sum(expected_value) FILTER (WHERE status = 'accepted'), 0) AS value_saved
        FROM retention_actions""", one=True)
    return {**totals, **live, "timeline": timeline, "distribution": distribution, "actions": actions,
            "thresholds": thresholds()}


@app.get("/api/map", tags=["dashboard"])
def risk_map():
    """Every customer's location and risk, for the geographic map."""
    rows = query("""
        SELECT s.customer_id, (s.profile->>'latitude')::float AS lat, (s.profile->>'longitude')::float AS lon,
               s.probability, s.risk_band
        FROM customer_scores s JOIN customers c USING (customer_id) WHERE NOT c.archived""")
    return [[r["customer_id"], round(r["lat"], 4), round(r["lon"], 4), round(r["probability"], 3)]
            for r in rows if r["lat"] is not None]


@app.get("/api/customers", tags=["customers"])
def customers(
    band: str | None = Query(None, pattern="^(low|medium|high)$"),
    search: str | None = Query(None, max_length=60),
    source: str | None = Query(None, pattern="^(dataset|manual|import|new)$"),
    model: str | None = Query(None, pattern="^(profile|survey)$"),
    sort: str = Query("risk", pattern="^(risk|recent|change|name|value)$"),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    order = {"risk": "s.probability DESC", "recent": "s.updated_at DESC", "name": "c.name ASC",
             "change": "abs(coalesce(s.probability - s.previous_probability, 0)) DESC",
             "value": "s.probability * s.monthly_charges DESC"}[sort]
    where, params = ["NOT c.archived"], {}
    if band:
        where.append("s.risk_band = %(band)s")
        params["band"] = band
    if model:
        where.append("s.model_used = %(model)s")
        params["model"] = model
    if source == "new":
        where.append("c.source <> 'dataset'")
    elif source:
        where.append("c.source = %(source)s")
        params["source"] = source
    if search:
        where.append("(c.customer_id ILIKE %(q)s OR c.name ILIKE %(q)s OR c.email ILIKE %(q)s OR c.city ILIKE %(q)s)")
        params["q"] = f"%{search}%"
    clause = "WHERE " + " AND ".join(where)
    rows = query(f"""
        SELECT c.customer_id, c.name, c.email, c.city, c.source, s.probability, s.previous_probability,
               s.risk_band, s.will_churn, s.model_used, s.alert, s.last_event_type, s.monthly_charges,
               s.profile->>'contract' AS contract, (s.profile->>'tenure_months')::int AS tenure,
               s.profile->>'internet_type' AS internet, (s.profile->>'age')::int AS age, s.updated_at
        FROM customer_scores s JOIN customers c USING (customer_id) {clause}
        ORDER BY {order} LIMIT %(limit)s OFFSET %(offset)s""", {**params, "limit": limit, "offset": offset})
    total = query(f"SELECT count(*) AS n FROM customer_scores s JOIN customers c USING (customer_id) {clause}",
                  params, one=True)["n"]
    return {"total": total, "items": rows}


@app.get("/api/customers/template.csv", tags=["customers"], response_class=PlainTextResponse)
def import_template():
    """A CSV with every importable column and one example row."""
    fields = CustomerIn.flat_fields()
    example = CustomerIn(contact={"name": "Jane Doe", "email": "jane.doe@example.com", "phone": "(555) 010-2030"},
                         geographic={"city": "San Diego"}, psychographic={"price_sensitivity": 4,
                                                                          "lifestyle": "Streamer"})
    flat = {**example.contact.model_dump(), **example.geographic.model_dump(), **example.demographic.model_dump(),
            **example.technographic.model_dump(), **example.behavioural.model_dump(),
            **example.psychographic.model_dump()}
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerow({f: ("" if flat.get(f) is None else flat.get(f)) for f in fields})
    return PlainTextResponse(buffer.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=churnpulse_template.csv"})


def _save_new_customer(customer: CustomerIn, source: str) -> tuple[str, dict, dict]:
    cid = new_customer_id()
    profile = customer.to_profile(state["cities"])
    persona = customer.persona()
    query("""INSERT INTO customers (customer_id, name, email, phone, city, zip_code, profile, persona, source)
             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
          (cid, customer.contact.name, customer.contact.email, customer.contact.phone, profile.get("city"),
           profile.get("zip_code"), Jsonb(profile), Jsonb(persona), source))
    return cid, profile, persona


@app.post("/api/customers", tags=["customers"], status_code=201)
def create_customer(customer: CustomerIn):
    """Add a new member: saved, scored instantly, and tracked live by Flink from now on."""
    cid, profile, persona = _save_new_customer(customer, "manual")
    publish([new_event(cid, "snapshot", profile, source="customer-manager")])
    result = state["model"].predict(profile, explain=True)
    return {"customer_id": cid, **result, "actions": recommend(state["model"], profile, persona)}


@app.post("/api/customers/import", tags=["customers"])
async def import_customers(file: UploadFile = File(...)):
    """Bulk-add members from a CSV (see /api/customers/template.csv)."""
    rows = _read_csv(await file.read())
    if len(rows) > 5000:
        raise HTTPException(413, "at most 5,000 rows per import")
    created, errors, events = [], [], []
    for i, row in enumerate(rows, start=2):
        try:
            customer = CustomerIn.from_flat(row)
        except ValidationError as exc:
            errors.append({"row": i, "errors": [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]})
            continue
        cid, profile, _ = _save_new_customer(customer, "import")
        events.append(new_event(cid, "snapshot", profile, source="import"))
        created.append({"customer_id": cid, "name": customer.contact.name})
    publish(events)
    return {"rows": len(rows), "imported": len(created), "failed": len(errors), "customers": created[:50],
            "errors": errors[:100]}


@app.get("/api/customers/{customer_id}", tags=["customers"])
def customer(customer_id: str):
    row = query("""
        SELECT s.*, c.name, c.email, c.phone, c.city, c.persona, c.cltv, c.source, c.archived, c.created_at,
               c.actual_churn AS dataset_label
        FROM customer_scores s JOIN customers c USING (customer_id)
        WHERE s.customer_id = %s""", (customer_id,), one=True)
    if row is None:
        pending = query("SELECT customer_id FROM customers WHERE customer_id = %s", (customer_id,), one=True)
        raise HTTPException(404 if pending is None else 409,
                            "customer not found" if pending is None else "customer is being scored - retry")
    history = query("""
        SELECT event_type, event_source, probability, risk_band, model_used, alert, created_at
        FROM prediction_events WHERE customer_id = %s ORDER BY created_at DESC LIMIT 60""", (customer_id,))
    live = state["model"].predict(row["profile"], explain=True)
    actions_log = query("""SELECT * FROM retention_actions WHERE customer_id = %s ORDER BY created_at DESC LIMIT 20""",
                        (customer_id,))
    return {**row, "reasons": live["reasons"], "history": history,
            "threshold": live["threshold"],
            "actions": recommend(state["model"], row["profile"], row["persona"]),
            "actions_log": actions_log}


@app.put("/api/customers/{customer_id}", tags=["customers"])
def update_customer(customer_id: str, customer: CustomerIn):
    """Edit a customer. Profile changes become a real event, so history and alerts update."""
    current = query("SELECT profile FROM customer_scores WHERE customer_id = %s", (customer_id,), one=True)
    if current is None:
        raise HTTPException(404, "customer not found")
    profile = customer.to_profile(state["cities"])
    query("""UPDATE customers SET name = %s, email = %s, phone = %s, city = %s, zip_code = %s, persona = %s,
             updated_at = now() WHERE customer_id = %s""",
          (customer.contact.name, customer.contact.email, customer.contact.phone, profile.get("city"),
           profile.get("zip_code"), Jsonb(customer.persona()), customer_id))
    events = diff_to_events(customer_id, current["profile"], profile)
    publish(events)
    return {"customer_id": customer_id, "changed_fields": list(events[0]["payload"]) if events else [],
            **state["model"].predict(profile, explain=True)}


@app.delete("/api/customers/{customer_id}", tags=["customers"])
def archive_customer(customer_id: str):
    """Archive (soft delete): hidden from lists, history kept."""
    updated = query("UPDATE customers SET archived = TRUE, updated_at = now() WHERE customer_id = %s RETURNING 1",
                    (customer_id,), one=True)
    if updated is None:
        raise HTTPException(404, "customer not found")
    return {"customer_id": customer_id, "archived": True}


@app.get("/api/live", tags=["dashboard"])
def live(limit: int = Query(30, ge=1, le=200), alerts_only: bool = False):
    """Most recent live predictions, to fill the feed before WebSocket updates arrive."""
    rows = query(f"""
        SELECT e.customer_id, c.name, e.event_type, e.event_source, e.probability, e.previous_probability,
               e.probability - e.previous_probability AS delta, e.risk_band, e.model_used, e.alert, e.reasons,
               s.profile->>'contract' AS contract, (s.profile->>'tenure_months')::int AS tenure,
               s.monthly_charges, c.city, e.created_at
        FROM prediction_events e JOIN customer_scores s USING (customer_id) JOIN customers c USING (customer_id)
        WHERE e.event_type <> 'snapshot' {"AND e.alert IS NOT NULL" if alerts_only else ""}
        ORDER BY e.created_at DESC LIMIT %s""", (limit,))
    return rows


# ------------------------------------------------------------------ retention actions
@app.get("/api/actions", tags=["actions"])
def action_queue(limit: int = Query(40, ge=1, le=200)):
    """At-risk customers with their best next action, highest expected value first."""
    candidates = query("""
        SELECT s.customer_id, c.name, c.city, s.profile, c.persona, s.probability, s.risk_band, s.model_used,
               s.monthly_charges
        FROM customer_scores s JOIN customers c USING (customer_id)
        WHERE s.will_churn AND NOT c.archived
          AND NOT EXISTS (SELECT 1 FROM retention_actions a WHERE a.customer_id = s.customer_id
                          AND a.status IN ('accepted', 'declined') AND a.updated_at > now() - interval '7 days')
        ORDER BY s.probability * s.monthly_charges DESC LIMIT 400""")
    recs = recommend_many(state["model"], [(r["customer_id"], r["profile"], r["persona"]) for r in candidates], top=3)
    queue = []
    for r in candidates:
        best = recs.get(r["customer_id"]) or []
        if best and best[0]["expected_value"] > 0:
            queue.append({k: r[k] for k in ("customer_id", "name", "city", "probability", "risk_band",
                                            "model_used", "monthly_charges")}
                         | {"contract": r["profile"]["contract"], "actions": best,
                            "persona": r["persona"]})
    queue.sort(key=lambda q: q["actions"][0]["score"], reverse=True)
    return {"total": len(queue), "items": queue[:limit],
            "potential_value": round(sum(q["actions"][0]["expected_value"] for q in queue), 2)}


@app.post("/api/actions", tags=["actions"])
def record_action(update: ActionUpdate):
    """Log an outreach. 'accepted' applies the action as a real event - the live risk updates."""
    action = ACTIONS_BY_ID.get(update.action_id)
    if action is None:
        raise HTTPException(400, "unknown action")
    row = query("""SELECT s.profile, c.persona FROM customer_scores s JOIN customers c USING (customer_id)
                   WHERE s.customer_id = %s""", (update.customer_id,), one=True)
    if row is None:
        raise HTTPException(404, "customer not found")
    estimate = next((a for a in recommend(state["model"], row["profile"], row["persona"], top=len(ACTIONS_BY_ID))
                     if a["action_id"] == update.action_id), None)
    if estimate is None:
        raise HTTPException(400, "this action does not apply to the customer any more")
    record = query("""
        INSERT INTO retention_actions (customer_id, action_id, title, channel, probability_before,
                                       probability_after, expected_value, cost, status, note)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
                   (update.customer_id, action.id, action.title, estimate["channel"],
                    estimate["probability_before"], estimate["probability_after"], estimate["expected_value"],
                    estimate["cost"], update.status, update.note), one=True)
    if update.status == "accepted":
        publish([new_event(update.customer_id, "profile_update", action.change(row["profile"]),
                           source=f"action:{action.id}")])
    return record


@app.get("/api/actions/log", tags=["actions"])
def action_log(limit: int = Query(50, ge=1, le=200)):
    return query("""SELECT a.*, c.name FROM retention_actions a JOIN customers c USING (customer_id)
                    ORDER BY a.created_at DESC LIMIT %s""", (limit,))


@app.post("/api/customers/{customer_id}/scenario/{name}", tags=["demo"])
def run_scenario(customer_id: str, name: str):
    """Send a scripted series of real events for one customer into Kafka."""
    if name not in ("churn_risk", "loyalty"):
        raise HTTPException(400, "scenario must be churn_risk or loyalty")
    row = query("SELECT profile FROM customer_scores WHERE customer_id = %s", (customer_id,), one=True)
    if row is None:
        raise HTTPException(404, "customer not found or not scored yet")
    events = scenario(name, customer_id, row["profile"])
    publish(events)
    return {"customer_id": customer_id, "scenario": name, "events_sent": len(events),
            "event_types": [e["event_type"] for e in events]}


# ------------------------------------------------------------------ helpers
def _read_csv(data: bytes) -> list[dict]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "the file must be UTF-8 CSV")
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        extra = row.pop(None, None)  # a row with more cells than the header
        if extra:
            row["_extra_cells"] = ";".join(extra)
        rows.append(row)
    if not rows:
        raise HTTPException(400, "the CSV has no rows")
    return rows


@app.get("/api/features", tags=["model"])
def feature_preview(customer_id: str):
    """The engineered model inputs for one customer (transparency/debugging)."""
    row = query("SELECT profile FROM customer_scores WHERE customer_id = %s", (customer_id,), one=True)
    if row is None:
        raise HTTPException(404, "customer not found")
    return json.loads(build_features(pd.DataFrame([row["profile"]])).iloc[0].to_json())


# ------------------------------------------------------------------ live feed
@app.websocket("/ws/live")
async def live_socket(ws: WebSocket):
    await ws.accept()
    queue = hub.subscribe()
    try:
        while True:
            await ws.send_json(await queue.get(), mode="text")
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        hub.unsubscribe(queue)
