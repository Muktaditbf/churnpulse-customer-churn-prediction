"""Retention action center: the next best action for an at-risk customer.

For every feasible action the customer is re-scored *as if they accepted it*
(a counterfactual through the same model), giving the risk reduction. Its
expected value is

    risk reduction x MONTHS_OF_VALUE x monthly bill  -  cost of the action

Psychographic inputs (price sensitivity, lifestyle, preferred channel) are
not model features - there is no labelled data for them - but they tailor
which actions are suggested and how to reach the customer.

Effects are estimated with the *profile* model, then applied relatively to the
customer's current risk. The survey model leans so heavily on satisfaction
that it swings wildly when other fields change, which would make its
counterfactuals unreliable; the profile model learned how contracts and
services relate to churn without that shortcut.

The model is correlational: "customers on two-year contracts churn less" does
not guarantee that *moving* someone to a two-year contract keeps them. The
estimates rank actions sensibly; the outcome log lets the business measure
the real effect.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from . import config
from .features import CONTRACT_MONTHS
from .predict import ChurnModel


@dataclass(frozen=True)
class Action:
    id: str
    title: str
    description: str
    applies: Callable[[dict], bool]
    change: Callable[[dict], dict]          # profile fields after the action
    cost: Callable[[dict], float]           # dollars
    fits: tuple[str, ...] = ()              # lifestyles this suits best
    price_focused: bool = False


def _bill(p: dict) -> float:
    return float(p["monthly_charge"])


ACTIONS: list[Action] = [
    Action("contract_1y", "Offer a 1-year contract", "One month free for committing to 12 months.",
           lambda p: p["contract"] == "Month-to-Month",
           lambda p: {"contract": "One Year"}, lambda p: _bill(p), price_focused=True),
    Action("contract_2y", "Offer a 2-year contract", "Two months free for committing to 24 months.",
           lambda p: CONTRACT_MONTHS[p["contract"]] < 24,
           lambda p: {"contract": "Two Year"}, lambda p: 2 * _bill(p), fits=("Family", "Homeowner")),
    Action("tech_support", "Add Premium Tech Support", "Free for 6 months.",
           lambda p: p["internet_type"] != "None" and not p["premium_tech_support"],
           lambda p: {"premium_tech_support": True}, lambda p: 6 * 5.0, fits=("Senior", "Remote worker")),
    Action("security", "Add Online Security", "Free for 6 months.",
           lambda p: p["internet_type"] != "None" and not p["online_security"],
           lambda p: {"online_security": True}, lambda p: 6 * 5.0, fits=("Family", "Senior")),
    Action("autopay", "Switch to automatic payment", "$10 credit for setting up auto-pay.",
           lambda p: p["payment_method"] == "Mailed Check",
           lambda p: {"payment_method": "Credit Card"}, lambda p: 10.0),
    Action("unlimited", "Upgrade to unlimited data", "Free upgrade for 6 months.",
           lambda p: p["internet_type"] != "None" and not p["unlimited_data"],
           lambda p: {"unlimited_data": True}, lambda p: 6 * 10.0, fits=("Streamer", "Remote worker", "Gamer")),
    Action("streaming", "Streaming bundle", "TV, movies and music free for 6 months.",
           lambda p: p["internet_type"] != "None"
           and not (p["streaming_tv"] and p["streaming_movies"] and p["streaming_music"]),
           lambda p: {"streaming_tv": True, "streaming_movies": True, "streaming_music": True},
           lambda p: 6 * 12.0, fits=("Streamer", "Family", "Gamer")),
    Action("discount_10", "10% loyalty discount", "10% off the monthly bill for 12 months.",
           lambda p: _bill(p) > 30,
           lambda p: {"monthly_charge": round(_bill(p) * 0.9, 2)}, lambda p: 0.1 * _bill(p) * 12,
           fits=("Budget",), price_focused=True),
]
# Low satisfaction drives most survey-model risk; a call that resolves the issue
# is the first step. Its effect is estimated with the survey model (the only
# one that knows satisfaction), assuming the call lifts satisfaction one point.
ACTIONS.append(Action(
    "service_recovery", "Service recovery call", "A senior agent calls to resolve their issue.",
    lambda p: p.get("satisfaction_score") is not None and int(p["satisfaction_score"]) <= 3,
    lambda p: {"satisfaction_score": int(p["satisfaction_score"]) + 1}, lambda p: 15.0,
    fits=("Senior", "Family")))
ACTIONS_BY_ID = {a.id: a for a in ACTIONS}

CHANNEL_DEFAULT = "Email"


def recommend(model: ChurnModel, profile: dict, persona: dict | None = None, top: int = 3) -> list[dict]:
    """The best actions for one customer, highest expected value first."""
    return recommend_many(model, [("_", profile, persona)], top=top)["_"]


def recommend_many(model: ChurnModel, customers: list[tuple[str, dict, dict | None]],
                   top: int = 3) -> dict[str, list[dict]]:
    """Recommendations for many customers with one batched scoring pass.

    Every (customer, action) counterfactual is built first and all of them
    are scored together - about 100x faster than scoring one by one.
    """
    import pandas as pd

    from .features import build_features

    rows, keys, survey_rows, survey_keys = [], [], [], []
    for cid, profile, _ in customers:
        no_survey = {**profile, "satisfaction_score": None}
        rows.append(no_survey)
        keys.append((cid, None))
        survey_rows.append(profile)                      # current risk, routed normally
        survey_keys.append((cid, "_current"))
        for action in ACTIONS:
            if not action.applies(profile):
                continue
            if action.id == "service_recovery":
                survey_rows.append({**profile, **action.change(profile)})
                survey_keys.append((cid, action.id))
            else:
                rows.append({**no_survey, **action.change(profile)})
                keys.append((cid, action.id))
    if not rows:
        return {}
    profile_p = dict(zip(keys, model.profile.proba(build_features(pd.DataFrame(rows))).to_numpy(), strict=True))
    routed_p = dict(zip(survey_keys, model.score_frame(build_features(pd.DataFrame(survey_rows))).to_numpy(),
                        strict=True))

    def after_probability(cid: str, action_id: str, current: float) -> float:
        if action_id == "service_recovery":
            return float(routed_p[(cid, action_id)])
        base = float(profile_p[(cid, None)])
        ratio = float(profile_p[(cid, action_id)]) / base if base > 1e-6 else 1.0
        return current * min(ratio, 1.5)

    out: dict[str, list[dict]] = {}
    for cid, profile, persona in customers:
        persona = persona or {}
        sensitivity = int(persona.get("price_sensitivity") or 3)
        lifestyle = persona.get("lifestyle")
        channel = persona.get("preferred_channel") or CHANNEL_DEFAULT
        before = float(routed_p[(cid, "_current")])
        value_per_point = config.MONTHS_OF_VALUE * _bill(profile)

        results = []
        for action in ACTIONS:
            if (cid, action.id) not in profile_p and (cid, action.id) not in routed_p:
                continue
            after = after_probability(cid, action.id, before)
            reduction = before - after
            cost = round(action.cost(profile), 2)
            expected_value = round(reduction * value_per_point - cost, 2)

            # Psychographic fit: a ranking nudge, never a change to the risk estimate.
            fit, why = 1.0, []
            if action.price_focused and sensitivity >= 4:
                fit *= 1.25
                why.append("price-sensitive customer")
            elif action.price_focused and sensitivity <= 2:
                fit *= 0.8
            if lifestyle and lifestyle in action.fits:
                fit *= 1.2
                why.append(f"suits a {lifestyle.lower()} lifestyle")

            results.append({
                "action_id": action.id,
                "title": action.title,
                "description": action.description,
                "probability_before": round(before, 4),
                "probability_after": round(after, 4),
                "risk_reduction": round(reduction, 4),
                "cost": cost,
                "expected_value": expected_value,
                "score": round(expected_value * fit if expected_value > 0 else expected_value, 2),
                "channel": channel,
                "why": why,
                "changes": action.change(profile),
            })
        results.sort(key=lambda r: r["score"], reverse=True)
        out[cid] = [r for r in results if r["risk_reduction"] > 0 and r["expected_value"] > 0][:top]
    return out
