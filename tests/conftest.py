import os

import pandas as pd
import pytest

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

from churnpulse.dataset import load_customers  # noqa: E402
from churnpulse.features import PROFILE_FIELDS  # noqa: E402


@pytest.fixture(scope="session")
def customers() -> pd.DataFrame:
    return load_customers()


@pytest.fixture(scope="session")
def profiles(customers) -> dict[str, dict]:
    """customer_id -> profile dict, like the simulator sends (plus the label as _label)."""
    out = {}
    for row in customers.to_dict("records"):
        p = {f: (None if pd.isna(row[f]) else row[f]) for f in PROFILE_FIELDS}
        p["_label"] = row["churned"]
        out[row["customer_id"]] = p
    return out


@pytest.fixture(scope="session")
def model():
    from churnpulse.predict import ChurnModel

    return ChurnModel()


def strip(profile: dict) -> dict:
    return {k: v for k, v in profile.items() if not k.startswith("_")}


def no_survey(profile: dict) -> dict:
    return {**strip(profile), "satisfaction_score": None}
