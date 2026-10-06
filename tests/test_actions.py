from churnpulse.actions import ACTIONS, recommend, recommend_many
from tests.conftest import no_survey


def risky(profiles):
    return no_survey(next(p for p in profiles.values() if p["contract"] == "Month-to-Month" and p["_label"] == 1
                          and p["payment_method"] == "Mailed Check"))


def test_recommendations_lower_risk_and_are_ranked(model, profiles):
    recs = recommend(model, risky(profiles), top=5)
    assert recs, "a risky month-to-month customer should get suggestions"
    assert all(r["risk_reduction"] > 0 and r["probability_after"] < r["probability_before"] for r in recs)
    scores = [r["score"] for r in recs]
    assert scores == sorted(scores, reverse=True)


def test_only_feasible_actions(model, profiles):
    p = no_survey(next(p for p in profiles.values() if p["contract"] == "Two Year"))
    ids = {r["action_id"] for r in recommend(model, p, top=10)}
    assert not {"contract_1y", "contract_2y"} & ids
    for action in ACTIONS:
        if action.applies(p):
            action.change(p)  # must not raise


def test_psychographic_tailoring(model, profiles):
    p = risky(profiles)
    base = {r["action_id"]: r["score"] for r in recommend(model, p, {"price_sensitivity": 3}, top=10)}
    persona = {"price_sensitivity": 5, "preferred_channel": "SMS"}
    sensitive = {r["action_id"]: r for r in recommend(model, p, persona, top=10)}
    if "discount_10" in base and base["discount_10"] > 0:
        assert sensitive["discount_10"]["score"] > base["discount_10"]
    assert all(r["channel"] == "SMS" for r in sensitive.values())


def test_batch_equals_single(model, profiles):
    items = [(cid, no_survey(p), None) for cid, p in list(profiles.items())[:40]]
    batch = recommend_many(model, items)
    for cid, p, _ in items[:10]:
        assert [r["action_id"] for r in batch[cid]] == [r["action_id"] for r in recommend(model, p)]
