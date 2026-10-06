"""Load both models once and score customer profiles.

Used by the Flink job (inside a Python UDF), the API and the action center.
A customer with a satisfaction score is scored by the survey model; everyone
else by the profile model.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import cached_property
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from . import config
from .features import has_survey, profile_to_frame


class ScoringModel:
    """One exported model (profile or survey)."""

    def __init__(self, path: str | Path):
        artifact = joblib.load(path)
        self.kind: str = artifact["kind"]
        self.model = artifact["model"]
        self.threshold: float = artifact["threshold"]
        self.features: list[str] = artifact["features"]
        self.model_name: str = artifact["model_name"]
        self.trained_at: str = artifact["trained_at"]
        self._explainer_pipeline = artifact["explainer_pipeline"]
        self._background = artifact["background"]

    @cached_property
    def explainer(self):
        from .explain import Explainer

        return Explainer(self._explainer_pipeline, self._background, self.features)

    def proba(self, X: pd.DataFrame) -> pd.Series:
        return pd.Series(self.model.predict_proba(X[self.features])[:, 1], index=X.index)


class ChurnModel:
    """Routes each customer to the right model and returns an explained prediction."""

    def __init__(self, models_dir: str | Path | None = None):
        base = Path(models_dir) if models_dir else config.MODELS_DIR
        self.models = {kind: ScoringModel(base / path.name) for kind, path in config.MODEL_PATHS.items()}

    @property
    def profile(self) -> ScoringModel:
        return self.models["profile"]

    @property
    def survey(self) -> ScoringModel:
        return self.models["survey"]

    def route(self, profile: Mapping[str, Any]) -> ScoringModel:
        return self.survey if has_survey(profile) else self.profile

    def score_frame(self, X: pd.DataFrame) -> pd.Series:
        """Batch scoring of engineered feature rows, routed row by row."""
        survey = X["satisfaction_score"].between(1, 5)
        out = pd.Series(index=X.index, dtype=float)
        if survey.any():
            out[survey] = self.survey.proba(X[survey])
        if (~survey).any():
            out[~survey] = self.profile.proba(X[~survey])
        return out

    def predict(self, profile: Mapping[str, Any], explain: bool = True) -> dict:
        model = self.route(profile)
        row = profile_to_frame(profile)
        probability = float(model.proba(row).iloc[0])
        result = {
            "churn_probability": round(probability, 4),
            "risk_band": config.risk_band(probability),
            "will_churn": probability >= model.threshold,
            "threshold": model.threshold,
            "model": model.model_name,
            "model_used": model.kind,
        }
        if explain:
            result["reasons"] = model.explainer.reasons(row)
        return result
