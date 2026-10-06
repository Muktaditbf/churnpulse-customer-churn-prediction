"""End-to-end tests against the running stack (`make up`); skipped otherwise.

    make test-e2e
"""

import os
import time

import httpx
import pytest

API = os.environ.get("CHURNPULSE_API", "http://localhost:8000")


def _stack_up() -> bool:
    try:
        return httpx.get(f"{API}/api/health", timeout=2).json()["stream_consumer"]
    except Exception:
        return False


pytestmark = [pytest.mark.e2e, pytest.mark.skipif(not _stack_up(), reason="stack not running")]

NEW_MEMBER = {
    "contact": {"name": "E2E Test Member", "email": "e2e@example.com", "phone": "(555) 000-0000"},
    "geographic": {"city": "Fresno"},
    "demographic": {"gender": "Male", "age": 27, "married": False, "num_dependents": 0},
    "technographic": {"internet_type": "Fiber Optic", "avg_monthly_gb": 25},
    "behavioural": {"tenure_months": 2, "contract": "Month-to-Month", "payment_method": "Mailed Check",
                    "monthly_charge": 95},
    "psychographic": {"price_sensitivity": 5, "lifestyle": "Streamer", "preferred_channel": "SMS"},
}


def wait_for(fn, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = fn()
        if result:
            return result
        time.sleep(0.4)
    return None


def test_new_member_is_scored_live_by_the_stream():
    started = time.time()
    created = httpx.post(f"{API}/api/customers", json=NEW_MEMBER).json()
    cid = created["customer_id"]
    assert created["model_used"] == "profile" and created["will_churn"], "instant prediction on create"

    detail = wait_for(lambda: (r := httpx.get(f"{API}/api/customers/{cid}")).status_code == 200 and r.json())
    assert detail, "Flink should score the new member within seconds"
    assert time.time() - started < 10
    assert detail["name"] == "E2E Test Member" and detail["source"] == "manual"
    assert detail["profile"]["latitude"] is not None, "city filled in the coordinates"
    assert abs(detail["probability"] - created["churn_probability"]) < 0.01, "stream and API agree"
    assert detail["actions"] and detail["actions"][0]["channel"] == "SMS"


def test_accepting_an_action_lowers_live_risk():
    cid = httpx.post(f"{API}/api/customers", json=NEW_MEMBER).json()["customer_id"]
    before = wait_for(lambda: (r := httpx.get(f"{API}/api/customers/{cid}")).status_code == 200 and r.json())
    action = before["actions"][0]
    httpx.post(f"{API}/api/actions", json={"customer_id": cid, "action_id": action["action_id"],
                                            "status": "accepted"}).raise_for_status()

    after = wait_for(lambda: (d := httpx.get(f"{API}/api/customers/{cid}").json())["probability"]
                     < before["probability"] - 0.02 and d)
    assert after, "accepted action should flow through Kafka/Flink and lower the risk"
    assert after["actions_log"][0]["status"] == "accepted"


def test_csv_import():
    template = httpx.get(f"{API}/api/customers/template.csv").text
    header, row = template.strip().splitlines()[:2]
    bad = row.replace("jane.doe@example.com", "not-an-email")
    csv = "\n".join([header, row, row.replace("Jane Doe", "John Roe"), bad]) + "\n"
    result = httpx.post(f"{API}/api/customers/import", files={"file": ("in.csv", csv, "text/csv")}).json()
    assert result["imported"] == 2 and result["failed"] == 1 and result["errors"][0]["row"] == 4
    cid = result["customers"][0]["customer_id"]
    assert wait_for(lambda: httpx.get(f"{API}/api/customers/{cid}").status_code == 200)


def test_churn_scenario_flows_through_the_stream():
    total = httpx.get(f"{API}/api/customers", params={"band": "low", "limit": 1}).json()["total"]
    items = httpx.get(f"{API}/api/customers",
                      params={"band": "low", "limit": 200, "offset": max(0, total - 200)}).json()["items"]
    cid = next(c["customer_id"] for c in items if c["contract"] == "Two Year")
    before = httpx.get(f"{API}/api/customers/{cid}").json()
    assert httpx.post(f"{API}/api/customers/{cid}/scenario/churn_risk").json()["events_sent"] == 6

    def scenario_done():
        d = httpx.get(f"{API}/api/customers/{cid}").json()
        demo = [h for h in d["history"] if (h["event_source"] or "").startswith("scenario")]
        return d if len(demo) >= 6 else None

    after = wait_for(scenario_done)
    assert after, "scenario events should round-trip within 15 s"
    assert after["profile"]["contract"] == "Month-to-Month" and after["profile"]["satisfaction_score"] == 2
    assert after["probability"] > before["probability"] + 0.3
    assert after["reasons"]


def test_action_queue_and_map():
    queue = httpx.get(f"{API}/api/actions", params={"limit": 10}).json()
    assert queue["total"] > 0 and queue["items"][0]["actions"][0]["expected_value"] > 0
    assert len(httpx.get(f"{API}/api/map").json()) >= 7043


def test_stream_latency_is_real_time():
    """Steady-state p95 over the last minute stays under one second (allowing a restart backlog to clear)."""
    deadline, p95 = time.time() + 75, None
    while time.time() < deadline:
        stats = httpx.get(f"{API}/api/stats").json()
        p95 = stats["p95_latency_ms"]
        if p95 is not None and p95 < 1000:
            break
        time.sleep(5)
    assert stats["customers_scored"] >= 7043
    assert p95 is not None and p95 < 1000, f"p95 latency {p95} ms"
