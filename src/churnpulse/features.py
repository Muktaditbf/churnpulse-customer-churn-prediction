"""Feature engineering - the single source of truth (v2, persona-based).

The notebooks, training, the Flink job, the API and the action center all
call these functions, so a customer is always turned into model inputs the
same way. Every feature belongs to one persona category; the dashboard groups
explanations and importance by these categories.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

ID_COLUMN = "customer_id"
TARGET = "churned"

# ------------------------------------------------------------------ raw profile
# The fields a customer profile carries, by persona category. These are what
# the API accepts, what Flink keeps in state and what the UI edits.
PROFILE_SCHEMA: dict[str, list[str]] = {
    "geographic": ["city", "zip_code", "latitude", "longitude", "population"],
    "demographic": ["gender", "age", "married", "num_dependents"],
    "technographic": ["phone_service", "multiple_lines", "internet_type", "avg_monthly_gb", "unlimited_data",
                      "online_security", "online_backup", "device_protection", "premium_tech_support",
                      "streaming_tv", "streaming_movies", "streaming_music"],
    "behavioural": ["tenure_months", "contract", "payment_method", "paperless_billing", "offer", "referrals",
                    "monthly_charge", "total_charges", "total_refunds", "total_extra_data_charges",
                    "avg_long_distance", "total_long_distance_charges"],
    "psychographic": ["satisfaction_score"],
}
PROFILE_FIELDS = [f for fields in PROFILE_SCHEMA.values() for f in fields]
OPTIONAL_FIELDS = {"satisfaction_score", "city", "zip_code", "total_charges", "total_refunds",
                   "total_extra_data_charges", "total_long_distance_charges"}

# Accepted category values (the API validates against these, the UI offers them).
CHOICES = {
    "gender": ["Female", "Male"],
    "internet_type": ["Fiber Optic", "Cable", "DSL", "None"],
    "contract": ["Month-to-Month", "One Year", "Two Year"],
    "payment_method": ["Bank Withdrawal", "Credit Card", "Mailed Check"],
    "offer": ["None", "Offer A", "Offer B", "Offer C", "Offer D", "Offer E"],
}
ADDONS = ["online_security", "online_backup", "device_protection", "premium_tech_support",
          "streaming_tv", "streaming_movies", "streaming_music", "unlimited_data"]
PROTECTION = ["online_security", "online_backup", "device_protection", "premium_tech_support"]
BOOLEAN_FIELDS = ["married", "phone_service", "multiple_lines", "paperless_billing", *ADDONS]

CONTRACT_MONTHS = {"Month-to-Month": 1, "One Year": 12, "Two Year": 24}
TENURE_BINS = [-1, 6, 12, 24, 48, 1_000]
TENURE_LABELS = ["0-6m", "7-12m", "13-24m", "25-48m", "49m+"]

# ------------------------------------------------------------------ model features
FEATURE_CATEGORY: dict[str, str] = {
    # geographic
    "latitude": "geographic", "longitude": "geographic", "log_population": "geographic",
    # demographic
    "age": "demographic", "gender": "demographic", "married": "demographic", "num_dependents": "demographic",
    "under_30": "demographic", "senior": "demographic",
    # technographic
    "internet_type": "technographic", "avg_monthly_gb": "technographic", "unlimited_data": "technographic",
    "phone_service": "technographic", "multiple_lines": "technographic", "online_security": "technographic",
    "online_backup": "technographic", "device_protection": "technographic",
    "premium_tech_support": "technographic", "streaming_tv": "technographic",
    "streaming_movies": "technographic", "streaming_music": "technographic",
    "num_addons": "technographic", "num_protection": "technographic", "gb_per_dollar": "technographic",
    # behavioural
    "tenure_months": "behavioural", "tenure_group": "behavioural", "contract": "behavioural",
    "contract_months": "behavioural", "payment_method": "behavioural", "auto_pay": "behavioural",
    "paperless_billing": "behavioural", "offer": "behavioural", "monthly_charge": "behavioural",
    "total_charges": "behavioural", "avg_monthly_charge": "behavioural", "charge_increase_ratio": "behavioural",
    "total_refunds": "behavioural", "had_refund": "behavioural", "extra_data_share": "behavioural",
    "avg_long_distance": "behavioural",
    # psychographic
    "referrals": "psychographic", "referred_a_friend": "psychographic",
    "satisfaction_score": "psychographic",
}
CATEGORICAL_FEATURES = ["gender", "internet_type", "contract", "payment_method", "offer", "tenure_group"]
SURVEY_ONLY = ["satisfaction_score"]
PROFILE_FEATURES = [f for f in FEATURE_CATEGORY if f not in SURVEY_ONLY]
SURVEY_FEATURES = list(FEATURE_CATEGORY)
CATEGORIES = ["geographic", "demographic", "technographic", "behavioural", "psychographic"]


def numeric_features(features: list[str]) -> list[str]:
    return [f for f in features if f not in CATEGORICAL_FEATURES]


def categorical_features(features: list[str]) -> list[str]:
    return [f for f in features if f in CATEGORICAL_FEATURES]


# ------------------------------------------------------------------ transforms
def clean_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Fill optional totals, normalise types. Works on one row or many."""
    out = df.copy()
    tenure = pd.to_numeric(out["tenure_months"], errors="coerce").fillna(0)
    monthly = pd.to_numeric(out["monthly_charge"], errors="coerce").fillna(0)
    out["tenure_months"] = tenure
    out["monthly_charge"] = monthly
    for col in ["total_charges", "total_refunds", "total_extra_data_charges", "total_long_distance_charges"]:
        if col not in out:
            out[col] = np.nan
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["total_charges"] = out["total_charges"].fillna(tenure * monthly)
    out["total_long_distance_charges"] = out["total_long_distance_charges"].fillna(
        tenure * pd.to_numeric(out["avg_long_distance"], errors="coerce").fillna(0))
    out[["total_refunds", "total_extra_data_charges"]] = out[["total_refunds", "total_extra_data_charges"]].fillna(0)
    for col in BOOLEAN_FIELDS:
        out[col] = out[col].map(lambda v: str(v).strip().lower() in ("true", "yes", "1")).astype(int)
    if "satisfaction_score" not in out:
        out["satisfaction_score"] = np.nan
    out["satisfaction_score"] = pd.to_numeric(out["satisfaction_score"], errors="coerce")
    for col in ["latitude", "longitude", "population", "age", "num_dependents", "avg_monthly_gb",
                "referrals", "avg_long_distance"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["offer"] = out["offer"].fillna("None").replace("", "None")
    out["internet_type"] = out["internet_type"].fillna("None").replace("", "None")
    return out


def engineer(df: pd.DataFrame) -> pd.DataFrame:
    """Add the derived features. Expects ``clean_profile`` output."""
    out = df.copy()
    tenure, monthly = out["tenure_months"].astype(float), out["monthly_charge"].astype(float)
    total = out["total_charges"].astype(float)

    out["log_population"] = np.log1p(out["population"].astype(float))
    out["under_30"] = (out["age"] < 30).astype(int)
    out["senior"] = (out["age"] >= 65).astype(int)

    out["num_addons"] = out[ADDONS].sum(axis=1)
    out["num_protection"] = out[PROTECTION].sum(axis=1)
    out["gb_per_dollar"] = out["avg_monthly_gb"].astype(float) / monthly.clip(lower=1)

    avg = np.where(tenure > 0, total / tenure.clip(lower=1), monthly)
    out["avg_monthly_charge"] = avg
    out["charge_increase_ratio"] = np.where(avg > 0, monthly / np.where(avg > 0, avg, 1), 1.0)
    out["contract_months"] = out["contract"].map(CONTRACT_MONTHS).fillna(1).astype(int)
    out["auto_pay"] = (out["payment_method"] != "Mailed Check").astype(int)
    out["had_refund"] = (out["total_refunds"] > 0).astype(int)
    out["extra_data_share"] = out["total_extra_data_charges"] / total.clip(lower=1)
    out["tenure_group"] = pd.cut(tenure, bins=TENURE_BINS, labels=TENURE_LABELS).astype(str)
    out["referred_a_friend"] = (out["referrals"] > 0).astype(int)
    return out


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Raw customer rows -> every model feature (both models' columns)."""
    return engineer(clean_profile(df))


def profile_to_frame(profile: Mapping[str, Any]) -> pd.DataFrame:
    """One customer profile (dict from Kafka, the API or the UI) -> one feature row."""
    missing = [f for f in PROFILE_FIELDS if f not in profile and f not in OPTIONAL_FIELDS]
    if missing:
        raise ValueError(f"profile is missing fields: {missing}")
    row = {f: profile.get(f) for f in PROFILE_FIELDS}
    return build_features(pd.DataFrame([row]))


def has_survey(profile: Mapping[str, Any]) -> bool:
    value = profile.get("satisfaction_score")
    try:
        return value is not None and not pd.isna(value) and 1 <= float(value) <= 5
    except (TypeError, ValueError):
        return False
