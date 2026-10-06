import random

from churnpulse.events import (
    EVENT_TYPES,
    apply_event,
    diff_to_events,
    is_downgrade,
    new_event,
    random_event,
    scenario,
)
from churnpulse.features import ADDONS, profile_to_frame
from tests.conftest import no_survey, strip


def first(profiles, cond):
    return next(strip(p) for p in profiles.values() if cond(p))


def test_billing_cycle_adds_a_month(profiles):
    p = first(profiles, lambda p: True)
    after = apply_event(p, new_event("x", "billing_cycle"))
    assert after["tenure_months"] == p["tenure_months"] + 1
    assert after["total_charges"] == round(p["total_charges"] + p["monthly_charge"], 2)
    assert p["tenure_months"] == after["tenure_months"] - 1, "input must not be modified"


def test_dropping_internet_clears_addons(profiles):
    p = first(profiles, lambda p: p["internet_type"] == "Fiber Optic")
    after = apply_event(p, new_event("x", "internet_change", {"internet_type": "None"}))
    assert not any(after[s] for s in ADDONS) and after["avg_monthly_gb"] == 0


def test_survey_and_downgrades(profiles):
    p = first(profiles, lambda p: p["contract"] == "Two Year")
    assert apply_event(p, new_event("x", "survey", {"satisfaction_score": 2}))["satisfaction_score"] == 2
    assert is_downgrade(p, new_event("x", "contract_change", {"contract": "Month-to-Month"}))
    assert is_downgrade(p, new_event("x", "survey", {"satisfaction_score": 1}))
    assert not is_downgrade(p, new_event("x", "billing_cycle"))


def test_random_events_always_produce_valid_profiles(profiles):
    """10,000 random events must never create a profile the model cannot score."""
    rng = random.Random(0)
    state = {cid: strip(p) for cid, p in list(profiles.items())[:100]}
    seen = set()
    for _ in range(10_000):
        cid = rng.choice(list(state))
        event = random_event(cid, state[cid], rng)
        seen.add(event["event_type"])
        state[cid] = apply_event(state[cid], event)
    for p in state.values():
        profile_to_frame(p)
    assert seen <= set(EVENT_TYPES) and len(seen) >= 9


def test_profile_edit_becomes_one_event(profiles):
    p = first(profiles, lambda p: True)
    events = diff_to_events("x", p, {**p, "contract": "Two Year", "age": 50})
    assert len(events) == 1 and set(events[0]["payload"]) <= {"contract", "age"}
    assert diff_to_events("x", p, dict(p)) == []


def test_churn_scenario_raises_risk(profiles, model):
    p = no_survey(first(profiles, lambda p: p["contract"] == "Two Year" and p["premium_tech_support"]))
    before = model.predict(p, explain=False)["churn_probability"]
    for e in scenario("churn_risk", "x", p):
        p = apply_event(p, e)
    after = model.predict(p, explain=False)
    assert after["model_used"] == "survey"          # the survey event switches models
    assert after["churn_probability"] > before + 0.3
