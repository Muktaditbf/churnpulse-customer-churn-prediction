"""API tests without Kafka/Postgres: the consumer is disabled for unit tests."""

import os

import pytest

os.environ["START_CONSUMER"] = "false"
os.environ.setdefault("DATABASE_URL", "postgresql://nobody:nothing@127.0.0.1:1/none")

from fastapi.testclient import TestClient  # noqa: E402

from api.app.main import app  # noqa: E402
from api.app.schemas import CustomerIn  # noqa: E402

RISKY = {
    "contact": {"name": "Test Person", "email": "test@example.com"},
    "geographic": {"city": "San Diego"},
    "demographic": {"age": 30},
    "technographic": {"internet_type": "Fiber Optic"},
    "behavioural": {"tenure_months": 1, "contract": "Month-to-Month", "monthly_charge": 95,
                    "payment_method": "Mailed Check"},
    "psychographic": {"price_sensitivity": 5, "preferred_channel": "SMS"},
}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_predict_uses_profile_model_without_survey(client):
    body = client.post("/api/predict", json=RISKY).json()
    assert body["model_used"] == "profile" and body["risk_band"] == "high" and body["will_churn"]
    assert body["reasons"] and body["actions"] and body["actions"][0]["channel"] == "SMS"
    assert body["profile"]["latitude"] is not None, "city fills in the coordinates"


def test_predict_uses_survey_model_with_survey(client):
    body = client.post("/api/predict", json={**RISKY, "psychographic": {"satisfaction_score": 5}}).json()
    assert body["model_used"] == "survey"


def test_validation_errors(client):
    assert client.post("/api/predict", json={**RISKY, "behavioural": {"contract": "Ten years"}}).status_code == 422
    assert client.post("/api/predict", json={**RISKY, "demographic": {"age": 5}}).status_code == 422
    assert client.post("/api/predict", json={"contact": {"name": "x"}}).status_code == 422


def test_meta_and_model_card(client):
    meta = client.get("/api/meta").json()
    assert len(meta["cities"]) > 1000 and "Fiber Optic" in meta["choices"]["internet_type"]
    card = client.get("/api/model").json()
    assert set(card["models"]) == {"profile", "survey"}


def test_csv_template_round_trips(client):
    text = client.get("/api/customers/template.csv").text
    header, row = text.strip().splitlines()[:2]
    record = dict(zip(header.split(","), row.split(","), strict=True))
    customer = CustomerIn.from_flat(record)
    assert customer.contact.name == "Jane Doe" and customer.psychographic.lifestyle == "Streamer"


def test_batch_scoring(client):
    template = client.get("/api/customers/template.csv").text
    bad = template.strip() + "\n" + ",".join(["Bad Row"] + [""] * (template.splitlines()[0].count(",")))
    bad = bad.replace("Bad Row,", "Bad Row,not-an-email,", 1)
    res = client.post("/api/predict/batch", files={"file": ("c.csv", bad, "text/csv")})
    assert res.status_code == 200
    lines = res.text.strip().splitlines()
    assert "churn_probability" in lines[0] and len(lines) == 3


def test_metrics_endpoint(client):
    assert "churnpulse_api_predict_seconds" in client.get("/metrics/").text
