import json

import numpy as np
import pytest
from sklearn.metrics import roc_auc_score

from churnpulse import config
from churnpulse.train import load_split
from tests.conftest import no_survey, strip


@pytest.fixture(scope="module")
def card():
    return json.loads(config.MODEL_CARD_PATH.read_text())


@pytest.fixture(scope="module")
def split():
    return load_split()


def test_metrics_are_in_honest_ranges(card):
    profile, survey = card["models"]["profile"]["test_metrics"], card["models"]["survey"]["test_metrics"]
    assert 0.88 <= profile["roc_auc"] <= 0.95      # much higher would suggest leakage
    assert survey["roc_auc"] > profile["roc_auc"]
    for m in (profile, survey):
        assert m["retention_value"] > m["retention_value_contact_everyone"]


@pytest.mark.parametrize("kind", ["profile", "survey"])
def test_reported_auc_is_reproducible(model, split, card, kind):
    scorer = model.models[kind]
    proba = scorer.proba(split.X_test)
    expected = card["models"][kind]["test_metrics"]["roc_auc"]
    assert roc_auc_score(split.y_test, proba) == pytest.approx(expected, abs=1e-9)


def test_profile_model_is_calibrated(model, split):
    """Average predicted risk matches the real churn rate."""
    assert model.profile.proba(split.X_test).mean() == pytest.approx(split.y_test.mean(), abs=0.03)


def test_routing(model, profiles):
    p = strip(next(iter(profiles.values())))
    assert model.predict(p, explain=False)["model_used"] == "survey"
    assert model.predict(no_survey(p), explain=False)["model_used"] == "profile"


def test_prediction_contract(model, profiles):
    out = model.predict(no_survey(next(iter(profiles.values()))))
    assert set(out) >= {"churn_probability", "risk_band", "will_churn", "threshold", "reasons", "model_used"}
    assert 0 <= out["churn_probability"] <= 1 and out["risk_band"] in {"low", "medium", "high"}
    assert len(out["reasons"]) == 5 and all(r["category"] for r in out["reasons"])


@pytest.mark.parametrize("kind", ["profile", "survey"])
def test_contributions_are_exact(model, split, kind):
    """Native contributions + base value must equal the model's raw score exactly."""
    scorer = model.models[kind]
    e = scorer.explainer
    Xt = np.asarray(e.prep.transform(split.X_test[scorer.features].head(200)), dtype=float)
    if e.kind != "LGBMClassifier":
        pytest.skip("check written for LightGBM")
    full = e.model.predict(Xt, pred_contrib=True)
    assert np.allclose(full.sum(axis=1), e.model.predict(Xt, raw_score=True))
    grouped = e.contributions(split.X_test[scorer.features].head(200))
    assert np.allclose(grouped.sum(axis=1), full[:, :-1].sum(axis=1))


def test_known_profiles_rank_sensibly(model, profiles):
    risky = no_survey(next(p for p in profiles.values() if p["contract"] == "Month-to-Month"
                           and p["internet_type"] == "Fiber Optic" and p["tenure_months"] <= 2 and p["referrals"] == 0))
    loyal = no_survey(next(p for p in profiles.values() if p["contract"] == "Two Year" and p["tenure_months"] >= 60))
    assert model.predict(risky)["churn_probability"] > 0.5 > model.predict(loyal)["churn_probability"]
