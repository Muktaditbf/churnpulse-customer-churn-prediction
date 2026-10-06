"""Live customer events: what can happen to a customer, and how it changes them.

Every event changes real model inputs, so the model genuinely re-scores the
customer. The simulator and the API create events; the Flink job applies them
with ``apply_event`` to the customer's live profile. All of them import this
module, so they always agree on what an event means.
"""

from __future__ import annotations

import copy
import random
import time
import uuid
from typing import Any

from .features import ADDONS, CHOICES, CONTRACT_MONTHS

EVENT_TYPES = [
    "snapshot",            # full profile; starts (or resets) a customer's state
    "billing_cycle",       # a month passes: tenure + 1, totals grow
    "contract_change",
    "service_change",      # add or remove one add-on service
    "internet_change",
    "price_change",
    "payment_change",
    "offer_accepted",
    "usage_change",        # behavioural: monthly data usage moves
    "referral",            # psychographic: the customer refers a friend
    "survey",              # psychographic: a satisfaction survey answer (1-5)
    "profile_update",      # edits from the customer manager (any fields)
]

EVENT_LABELS = {
    "snapshot": "Profile loaded", "billing_cycle": "Monthly billing", "contract_change": "Contract changed",
    "service_change": "Service changed", "internet_change": "Internet changed", "price_change": "Price changed",
    "payment_change": "Payment method changed", "offer_accepted": "Offer accepted",
    "usage_change": "Data usage changed", "referral": "Referred a friend", "survey": "Satisfaction survey",
    "profile_update": "Profile edited",
}


def new_event(customer_id: str, event_type: str, payload: dict[str, Any] | None = None,
              source: str = "simulator") -> dict:
    return {
        "event_id": uuid.uuid4().hex,
        "customer_id": customer_id,
        "event_type": event_type,
        "event_time": int(time.time() * 1000),
        "payload": payload or {},
        "source": source,
    }


def is_downgrade(profile: dict, event: dict) -> bool:
    """Events a retention team would see as a warning sign."""
    p, t = event["payload"], event["event_type"]
    if t == "contract_change":
        return CONTRACT_MONTHS[p["contract"]] < CONTRACT_MONTHS[profile["contract"]]
    if t == "service_change":
        return bool(profile.get(p["service"])) and not p["value"]
    if t == "price_change":
        return float(p["monthly_charge"]) > float(profile["monthly_charge"]) * 1.03
    if t == "payment_change":
        return profile["payment_method"] != "Mailed Check" and p["payment_method"] == "Mailed Check"
    if t == "internet_change":
        return p["internet_type"] == "None" and profile["internet_type"] != "None"
    if t == "usage_change":
        return float(p["avg_monthly_gb"]) < float(profile["avg_monthly_gb"]) * 0.7
    if t == "survey":
        return float(p["satisfaction_score"]) <= 2
    return False


def apply_event(profile: dict, event: dict) -> dict:
    """Return the customer's profile after the event (the input is not changed)."""
    t, p = event["event_type"], event["payload"]
    if t == "snapshot":
        return dict(p)

    out = copy.deepcopy(profile)
    if t == "billing_cycle":
        out["tenure_months"] = int(out["tenure_months"]) + 1
        out["total_charges"] = round(float(out.get("total_charges") or 0) + float(out["monthly_charge"]), 2)
        out["total_long_distance_charges"] = round(
            float(out.get("total_long_distance_charges") or 0) + float(out["avg_long_distance"]), 2)
    elif t == "contract_change":
        out["contract"] = p["contract"]
    elif t == "service_change":
        if out["internet_type"] != "None" or p["service"] not in ADDONS:
            out[p["service"]] = bool(p["value"])
    elif t == "internet_change":
        out["internet_type"] = p["internet_type"]
        if p["internet_type"] == "None":
            for service in ADDONS:
                out[service] = False
            out["avg_monthly_gb"] = 0
    elif t == "price_change":
        out["monthly_charge"] = round(float(p["monthly_charge"]), 2)
    elif t == "payment_change":
        out["payment_method"] = p["payment_method"]
    elif t == "offer_accepted":
        out["offer"] = p["offer"]
    elif t == "usage_change":
        out["avg_monthly_gb"] = max(0, int(p["avg_monthly_gb"]))
    elif t == "referral":
        out["referrals"] = int(out["referrals"]) + int(p.get("count", 1))
    elif t == "survey":
        out["satisfaction_score"] = int(p["satisfaction_score"])
    elif t == "profile_update":
        out.update(p)
    else:
        raise ValueError(f"unknown event type: {t}")
    return out


# ---------------------------------------------------------------- generation
def random_event(customer_id: str, profile: dict, rng: random.Random) -> dict:
    """One plausible event for this customer, roughly as often as in real life."""
    kind = rng.choices(
        ["billing_cycle", "usage_change", "service_change", "price_change", "survey", "payment_change",
         "contract_change", "offer_accepted", "referral", "internet_change"],
        weights=[40, 14, 12, 9, 6, 6, 5, 4, 3, 1],
    )[0]
    has_internet = profile["internet_type"] != "None"
    if kind in ("service_change", "usage_change") and not has_internet:
        kind = "billing_cycle"

    if kind == "billing_cycle":
        return new_event(customer_id, kind)
    if kind == "usage_change":
        factor = rng.choice([0.4, 0.6, 0.8, 1.2, 1.5])
        return new_event(customer_id, kind, {"avg_monthly_gb": round(int(profile["avg_monthly_gb"]) * factor) + 1})
    if kind == "service_change":
        service = rng.choice(ADDONS)
        return new_event(customer_id, kind, {"service": service, "value": not bool(profile[service])})
    if kind == "price_change":
        change = rng.choice([-0.10, -0.05, 0.05, 0.08, 0.12, 0.18])
        return new_event(customer_id, kind,
                         {"monthly_charge": round(float(profile["monthly_charge"]) * (1 + change), 2)})
    if kind == "survey":
        return new_event(customer_id, kind, {"satisfaction_score": rng.choices([1, 2, 3, 4, 5],
                                                                               weights=[1, 1, 3, 3, 2])[0]})
    if kind == "payment_change":
        options = [m for m in CHOICES["payment_method"] if m != profile["payment_method"]]
        return new_event(customer_id, kind, {"payment_method": rng.choice(options)})
    if kind == "contract_change":
        options = [c for c in CHOICES["contract"] if c != profile["contract"]]
        return new_event(customer_id, kind, {"contract": rng.choice(options)})
    if kind == "offer_accepted":
        options = [o for o in CHOICES["offer"] if o not in ("None", profile["offer"])]
        return new_event(customer_id, kind, {"offer": rng.choice(options)})
    if kind == "referral":
        return new_event(customer_id, kind, {"count": 1})
    options = [i for i in CHOICES["internet_type"] if i != profile["internet_type"]]
    return new_event(customer_id, kind, {"internet_type": rng.choice(options)})


def scenario(name: str, customer_id: str, profile: dict) -> list[dict]:
    """Scripted stories used by the demo buttons and the end-to-end tests."""
    if name == "churn_risk":
        steps = [
            ("contract_change", {"contract": "Month-to-Month"}),
            ("service_change", {"service": "premium_tech_support", "value": False}),
            ("service_change", {"service": "online_security", "value": False}),
            ("usage_change", {"avg_monthly_gb": max(1, int(profile["avg_monthly_gb"]) // 4)}),
            ("price_change", {"monthly_charge": round(float(profile["monthly_charge"]) * 1.2, 2)}),
            ("survey", {"satisfaction_score": 2}),
        ]
    elif name == "loyalty":
        steps = [
            ("contract_change", {"contract": "Two Year"}),
            ("service_change", {"service": "premium_tech_support", "value": True}),
            ("service_change", {"service": "online_security", "value": True}),
            ("payment_change", {"payment_method": "Credit Card"}),
            ("referral", {"count": 1}),
            ("survey", {"satisfaction_score": 5}),
        ]
    else:
        raise ValueError(f"unknown scenario: {name}")
    return [new_event(customer_id, t, p, source=f"scenario:{name}") for t, p in steps]


def diff_to_events(customer_id: str, before: dict, after: dict, source: str = "customer-manager") -> list[dict]:
    """Turn an edit into one profile_update event carrying only what changed."""
    changed = {k: v for k, v in after.items() if before.get(k) != v}
    return [new_event(customer_id, "profile_update", changed, source=source)] if changed else []
