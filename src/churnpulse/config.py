"""Paths and constants shared by training, streaming and serving."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("CHURNPULSE_ROOT", Path(__file__).resolve().parents[2]))

DATA_V11 = ROOT / "data" / "raw" / "ibm_v11"
DATA_PROCESSED = ROOT / "data" / "processed"
CUSTOMERS_CSV = DATA_PROCESSED / "customers.csv"
MODELS_DIR = Path(os.environ.get("CHURNPULSE_MODELS", ROOT / "models"))

# Two cooperating models (see README): the profile model scores every customer;
# the survey model is used whenever a satisfaction score is known.
MODEL_PATHS = {
    "profile": MODELS_DIR / "profile_model.joblib",
    "survey": MODELS_DIR / "survey_model.joblib",
}
MODEL_CARD_PATH = MODELS_DIR / "model_card.json"

MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", f"sqlite:///{ROOT / 'mlflow.db'}")
MLFLOW_EXPERIMENT = "churnpulse"
MLFLOW_MODEL_NAMES = {"profile": "churnpulse-profile-model", "survey": "churnpulse-survey-model"}

RANDOM_STATE = 42
TEST_SIZE = 0.20

# Business assumptions used to pick each model's decision threshold and to
# value retention actions. A flagged customer is offered something worth
# OFFER_MONTHS of their bill (paid whether or not they would have left); it
# keeps a would-be churner with probability OFFER_SUCCESS_RATE; a kept
# customer is worth MONTHS_OF_VALUE months of bill.
OFFER_MONTHS = 1.5
OFFER_SUCCESS_RATE = 0.30
MONTHS_OF_VALUE = 12

# Risk bands shown on the dashboard, applied to the calibrated probability.
RISK_BANDS = [(0.0, "low"), (0.30, "medium"), (0.55, "high")]


def risk_band(probability: float) -> str:
    band = RISK_BANDS[0][1]
    for lower, name in RISK_BANDS:
        if probability >= lower:
            band = name
    return band
