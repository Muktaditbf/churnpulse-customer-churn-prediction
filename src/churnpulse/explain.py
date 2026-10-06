"""Per-feature contributions (SHAP values), summed back to human-readable features.

Every deployable model has an exact, library-native way to get SHAP values,
so the ``shap`` package is never imported in production (it cannot initialise
inside Flink's Python workers):

* Logistic Regression: closed form, coefficient x (value - background mean)
* LightGBM:  ``predict(..., pred_contrib=True)``
* XGBoost:   ``Booster.predict(..., pred_contribs=True)``
* CatBoost:  ``get_feature_importance(type="ShapValues")``

All values are in log-odds of the uncalibrated model; positive pushes towards
churn. One-hot columns are added back together per original feature.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

from .features import FEATURE_CATEGORY, categorical_features, numeric_features


class Explainer:
    def __init__(self, pipeline: Pipeline, background: pd.DataFrame, features: list[str]):
        self.prep = pipeline.named_steps["prep"]
        self.model = pipeline.named_steps["model"]
        self.features = features
        self.kind = type(self.model).__name__
        self.groups = self._feature_groups()
        if self.kind == "LogisticRegression":
            self._coef = self.model.coef_[0]
            self._mean = self.prep.transform(background[features]).mean(axis=0)

    def _feature_groups(self) -> list[str]:
        """For every encoded column, the original feature it came from."""
        encoder = self.prep.named_transformers_["cat"]
        groups = []
        for feature, cats in zip(categorical_features(self.features), encoder.categories_, strict=True):
            groups.extend([feature] * len(cats))
        groups.extend(numeric_features(self.features))
        return groups

    def _raw(self, Xt: np.ndarray) -> np.ndarray:
        if self.kind == "LogisticRegression":
            return (Xt - self._mean) * self._coef
        if self.kind == "LGBMClassifier":
            return self.model.predict(Xt, pred_contrib=True)[:, :-1]
        if self.kind == "XGBClassifier":
            import xgboost as xgb

            return self.model.get_booster().predict(xgb.DMatrix(Xt), pred_contribs=True)[:, :-1]
        if self.kind == "CatBoostClassifier":
            from catboost import Pool

            return self.model.get_feature_importance(Pool(Xt), type="ShapValues")[:, :-1]
        raise TypeError(f"no native explanation for {self.kind}")

    def contributions(self, X: pd.DataFrame) -> pd.DataFrame:
        """SHAP values (log-odds), one column per original feature."""
        Xt = np.asarray(self.prep.transform(X[self.features]), dtype=float)
        encoded = pd.DataFrame(self._raw(Xt), columns=self.groups, index=X.index)
        return encoded.T.groupby(level=0, sort=False).sum().T[self.features]

    def reasons(self, row: pd.DataFrame, top: int = 5) -> list[dict]:
        """Biggest drivers for one customer, positive = pushes towards churn."""
        contrib = self.contributions(row).iloc[0]
        order = contrib.abs().sort_values(ascending=False).index[:top]
        out = []
        for feature in order:
            value = row.iloc[0][feature]
            if isinstance(value, (float, np.floating)):
                value = round(float(value), 2)
            elif isinstance(value, (np.integer, np.bool_)):
                value = int(value)
            out.append({
                "feature": feature,
                "category": FEATURE_CATEGORY[feature],
                "value": value,
                "impact": round(float(contrib[feature]), 4),
                "direction": "raises risk" if contrib[feature] > 0 else "lowers risk",
            })
        return out
