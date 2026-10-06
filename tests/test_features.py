import pandas as pd
import pytest

from churnpulse.dataset import LEAKY_COLUMNS, RENAME
from churnpulse.features import (
    FEATURE_CATEGORY,
    PROFILE_FEATURES,
    SURVEY_FEATURES,
    build_features,
    has_survey,
    profile_to_frame,
)
from churnpulse.train import MODEL_FEATURES
from tests.conftest import no_survey, strip


def test_dataset_is_complete(customers):
    assert len(customers) == 7043
    assert customers["customer_id"].is_unique
    assert customers["churned"].mean() == pytest.approx(0.2654, abs=0.001)
    assert customers["name"].notna().all() and customers["email"].str.contains("@").all()


def test_no_leaky_column_reaches_a_model():
    leaky_targets = {RENAME[c] for c in LEAKY_COLUMNS if c in RENAME}   # e.g. cltv, churned
    for features in MODEL_FEATURES.values():
        assert not leaky_targets & set(features)
        assert not {"name", "email", "phone", "customer_id", "city", "zip_code"} & set(features)


def test_every_feature_has_a_persona_category():
    assert set(SURVEY_FEATURES) == set(FEATURE_CATEGORY)
    assert set(FEATURE_CATEGORY.values()) == {"geographic", "demographic", "technographic", "behavioural",
                                              "psychographic"}
    assert set(SURVEY_FEATURES) - set(PROFILE_FEATURES) == {"satisfaction_score"}


def test_single_profile_matches_batch(customers, profiles):
    """The streaming path (one dict) must equal the training path (whole table)."""
    batch = build_features(customers).set_index(customers["customer_id"])[SURVEY_FEATURES]
    for cid in list(profiles)[:150]:
        one = profile_to_frame(strip(profiles[cid])).iloc[0]
        for col in SURVEY_FEATURES:
            expected = batch.loc[cid, col]
            if isinstance(expected, str):
                assert one[col] == expected, (cid, col)
            else:
                assert float(one[col]) == pytest.approx(float(expected), nan_ok=True), (cid, col)


def test_engineered_values():
    row = profile_to_frame({
        "latitude": 34.0, "longitude": -118.0, "population": 999, "gender": "Male", "age": 70, "married": True,
        "num_dependents": 2, "phone_service": True, "multiple_lines": False, "internet_type": "Fiber Optic",
        "avg_monthly_gb": 30, "unlimited_data": True, "online_security": True, "online_backup": False,
        "device_protection": False, "premium_tech_support": True, "streaming_tv": False, "streaming_movies": False,
        "streaming_music": False, "tenure_months": 10, "contract": "One Year", "payment_method": "Mailed Check",
        "paperless_billing": False, "offer": "None", "referrals": 1, "monthly_charge": 100.0, "total_charges": 800.0,
        "avg_long_distance": 5.0}).iloc[0]
    assert row["senior"] == 1 and row["under_30"] == 0
    assert row["num_addons"] == 3 and row["num_protection"] == 2
    assert row["charge_increase_ratio"] == pytest.approx(1.25)
    assert row["contract_months"] == 12 and row["auto_pay"] == 0 and row["referred_a_friend"] == 1
    assert pd.isna(row["satisfaction_score"])


def test_survey_detection(profiles):
    p = strip(next(iter(profiles.values())))
    assert has_survey(p) and not has_survey(no_survey(p))
    assert not has_survey({**p, "satisfaction_score": 9})


def test_missing_required_field_is_rejected(profiles):
    p = strip(next(iter(profiles.values())))
    del p["contract"]
    with pytest.raises(ValueError, match="contract"):
        profile_to_frame(p)
