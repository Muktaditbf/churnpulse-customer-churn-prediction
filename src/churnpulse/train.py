"""Train both ChurnPulse models: compare, tune, calibrate, pick a threshold, evaluate, export.

* profile model - every persona feature except the satisfaction survey; scores
  every customer, including brand-new ones.
* survey model  - the same plus the satisfaction score; used whenever a
  customer has answered the survey.

    python -m churnpulse.train            # both models
    python -m churnpulse.train --trials 10 --no-mlflow
"""

from __future__ import annotations

import json
import logging
import os
import platform
import time
import warnings
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_predict, cross_validate, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from . import config
from .dataset import LEAKY_COLUMNS, load_customers
from .features import (
    CATEGORIES,
    FEATURE_CATEGORY,
    ID_COLUMN,
    PROFILE_FEATURES,
    SURVEY_FEATURES,
    TARGET,
    build_features,
    categorical_features,
    numeric_features,
)

log = logging.getLogger("churnpulse.train")

CV = StratifiedKFold(n_splits=5, shuffle=True, random_state=config.RANDOM_STATE)
MODEL_FEATURES = {"profile": PROFILE_FEATURES, "survey": SURVEY_FEATURES}

# Simplest first: faster to score in the stream, easier to explain, smaller.
SIMPLICITY_ORDER = ["logistic_regression", "lightgbm", "xgboost", "catboost", "random_forest"]
TIE_TOLERANCE = 0.002  # well inside the fold-to-fold spread of ROC-AUC
# Random Forest is compared for reference but not deployed: explaining it
# needs the shap library, which cannot initialise inside Flink's Python workers.
DEPLOYABLE = {"logistic_regression", "lightgbm", "xgboost", "catboost"}


def quiet_warnings() -> None:
    """Hide known-harmless library noise so real problems stand out."""
    for pattern in [".*iprint.*", ".*device.*", ".*X does not have valid feature names.*"]:
        warnings.filterwarnings("ignore", message=pattern)
    warnings.filterwarnings("ignore", category=FutureWarning)
    os.environ["PYTHONWARNINGS"] = "ignore"  # also silences joblib worker processes


# --------------------------------------------------------------------------- data
@dataclass
class Split:
    X_train: pd.DataFrame
    X_test: pd.DataFrame
    y_train: pd.Series
    y_test: pd.Series
    ids_test: pd.Series


def load_split() -> Split:
    """One stratified 80/20 split shared by both models."""
    raw = load_customers()
    df = build_features(raw)
    X, y = df[SURVEY_FEATURES], raw[TARGET]
    X_tr, X_te, y_tr, y_te, _, ids_te = train_test_split(
        X, y, raw[ID_COLUMN], test_size=config.TEST_SIZE, stratify=y, random_state=config.RANDOM_STATE)
    return Split(X_tr, X_te, y_tr, y_te, ids_te)


# --------------------------------------------------------------------------- models
def preprocessor(features: list[str]) -> ColumnTransformer:
    return ColumnTransformer(
        [("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categorical_features(features)),
         ("num", StandardScaler(), numeric_features(features))],
        verbose_feature_names_out=False,
    )


def _xgb(**params):
    from xgboost import XGBClassifier

    base = dict(n_estimators=400, learning_rate=0.05, max_depth=4, subsample=0.8, colsample_bytree=0.8,
                eval_metric="logloss", tree_method="hist", device="cuda", random_state=config.RANDOM_STATE)
    return XGBClassifier(**(base | params))


def _lgbm(**params):
    from lightgbm import LGBMClassifier

    base = dict(n_estimators=400, learning_rate=0.03, num_leaves=15, subsample=0.8, subsample_freq=1,
                colsample_bytree=0.8, random_state=config.RANDOM_STATE, verbose=-1, n_jobs=4)
    return LGBMClassifier(**(base | params))


def _catboost(**params):
    from catboost import CatBoostClassifier

    base = dict(iterations=500, learning_rate=0.05, depth=5, random_seed=config.RANDOM_STATE,
                verbose=False, thread_count=4, allow_writing_files=False)
    return CatBoostClassifier(**(base | params))


def candidate_models() -> dict[str, Any]:
    return {
        "logistic_regression": LogisticRegression(max_iter=4000, C=1.0),
        "random_forest": RandomForestClassifier(n_estimators=400, min_samples_leaf=3, n_jobs=-1,
                                                random_state=config.RANDOM_STATE),
        "xgboost": _xgb(),
        "lightgbm": _lgbm(),
        "catboost": _catboost(),
    }


def make_pipeline(model, features: list[str]) -> Pipeline:
    return Pipeline([("prep", preprocessor(features)), ("model", model)])


def compare_models(split: Split, features: list[str]) -> pd.DataFrame:
    rows = []
    for name, model in candidate_models().items():
        start = time.perf_counter()
        scores = cross_validate(
            make_pipeline(model, features), split.X_train[features], split.y_train, cv=CV,
            scoring=["roc_auc", "average_precision", "accuracy", "f1", "recall", "precision"],
            n_jobs=-1 if name == "logistic_regression" else 1)
        rows.append({
            "model": name,
            "roc_auc": scores["test_roc_auc"].mean(),
            "roc_auc_std": scores["test_roc_auc"].std(),
            "pr_auc": scores["test_average_precision"].mean(),
            "accuracy": scores["test_accuracy"].mean(),
            "f1": scores["test_f1"].mean(),
            "recall": scores["test_recall"].mean(),
            "precision": scores["test_precision"].mean(),
            "seconds": time.perf_counter() - start,
        })
        log.info("  %-20s roc_auc=%.4f accuracy=%.4f", name, rows[-1]["roc_auc"], rows[-1]["accuracy"])
    return pd.DataFrame(rows).sort_values("roc_auc", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------- tuning
def _suggest(trial, name: str):
    if name == "logistic_regression":
        return LogisticRegression(C=trial.suggest_float("C", 1e-3, 10, log=True),
                                  penalty=trial.suggest_categorical("penalty", ["l1", "l2"]),
                                  solver="liblinear", max_iter=4000)
    if name == "xgboost":
        return _xgb(n_estimators=trial.suggest_int("n_estimators", 150, 900, step=50),
                    learning_rate=trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
                    max_depth=trial.suggest_int("max_depth", 2, 7),
                    min_child_weight=trial.suggest_float("min_child_weight", 1, 20, log=True),
                    subsample=trial.suggest_float("subsample", 0.5, 1.0),
                    colsample_bytree=trial.suggest_float("colsample_bytree", 0.4, 1.0),
                    reg_lambda=trial.suggest_float("reg_lambda", 1e-2, 20, log=True),
                    gamma=trial.suggest_float("gamma", 0, 5))
    if name == "lightgbm":
        return _lgbm(n_estimators=trial.suggest_int("n_estimators", 150, 900, step=50),
                     learning_rate=trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
                     num_leaves=trial.suggest_int("num_leaves", 4, 64),
                     min_child_samples=trial.suggest_int("min_child_samples", 5, 100),
                     subsample=trial.suggest_float("subsample", 0.5, 1.0),
                     colsample_bytree=trial.suggest_float("colsample_bytree", 0.4, 1.0),
                     reg_lambda=trial.suggest_float("reg_lambda", 1e-2, 20, log=True))
    if name == "catboost":
        return _catboost(iterations=trial.suggest_int("iterations", 200, 900, step=50),
                         learning_rate=trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
                         depth=trial.suggest_int("depth", 3, 8),
                         l2_leaf_reg=trial.suggest_float("l2_leaf_reg", 1, 20, log=True))
    raise ValueError(name)


@dataclass
class Tuned:
    name: str
    cv_roc_auc: float
    params: dict
    pipeline: Pipeline
    history: list = field(default_factory=list)


def tune(split: Split, name: str, features: list[str], n_trials: int = 30) -> Tuned:
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial):
        scores = cross_validate(make_pipeline(_suggest(trial, name), features), split.X_train[features],
                                split.y_train, cv=CV, scoring="roc_auc",
                                n_jobs=-1 if name == "logistic_regression" else 1)
        return scores["test_score"].mean()

    study = optuna.create_study(direction="maximize",
                                sampler=optuna.samplers.TPESampler(seed=config.RANDOM_STATE))
    study.optimize(objective, n_trials=n_trials)
    best = _suggest(optuna.trial.FixedTrial(study.best_params), name)
    return Tuned(name, study.best_value, study.best_params, make_pipeline(best, features),
                 [t.value for t in study.trials])


def pick_simplest(tuned: list[Tuned]) -> Tuned:
    """Best ROC-AUC wins, unless a simpler model is statistically tied with it."""
    top = max(t.cv_roc_auc for t in tuned)
    tied = [t for t in tuned if top - t.cv_roc_auc <= TIE_TOLERANCE]
    return min(tied, key=lambda t: SIMPLICITY_ORDER.index(t.name))


# --------------------------------------------------------------------------- threshold & evaluation
def retention_value(y_true, proba, monthly, threshold: float) -> float:
    """Net money saved by making an offer to everyone at or above the threshold."""
    flagged = np.asarray(proba) >= threshold
    monthly = np.asarray(monthly, dtype=float)
    saved = config.OFFER_SUCCESS_RATE * config.MONTHS_OF_VALUE * monthly
    gain = np.where(np.asarray(y_true) == 1, saved, 0.0) - config.OFFER_MONTHS * monthly
    return float(gain[flagged].sum())


def choose_threshold(y_true, proba, monthly) -> tuple[float, pd.DataFrame]:
    grid = np.round(np.arange(0.05, 0.91, 0.01), 2)
    curve = pd.DataFrame({
        "threshold": grid,
        "value": [retention_value(y_true, proba, monthly, t) for t in grid],
        "f1": [f1_score(y_true, proba >= t, zero_division=0) for t in grid],
        "recall": [recall_score(y_true, proba >= t, zero_division=0) for t in grid],
        "precision": [precision_score(y_true, proba >= t, zero_division=0) for t in grid],
    })
    return float(curve.loc[curve["value"].idxmax(), "threshold"]), curve


def evaluate(y_true, proba, threshold: float, monthly) -> dict:
    pred = (proba >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, pred).ravel()
    return {
        "roc_auc": roc_auc_score(y_true, proba),
        "pr_auc": average_precision_score(y_true, proba),
        "brier": brier_score_loss(y_true, proba),
        "threshold": threshold,
        "accuracy": accuracy_score(y_true, pred),
        "precision": precision_score(y_true, pred, zero_division=0),
        "recall": recall_score(y_true, pred, zero_division=0),
        "f1": f1_score(y_true, pred, zero_division=0),
        "accuracy_at_0.5": accuracy_score(y_true, proba >= 0.5),
        "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "retention_value": retention_value(y_true, proba, monthly, threshold),
        "retention_value_contact_everyone": retention_value(y_true, proba, monthly, 0.0),
    }


def to_cpu(obj) -> None:
    """XGBoost trains on the GPU; the streaming/serving containers have none."""
    from xgboost import XGBClassifier

    stack = [obj]
    while stack:
        item = stack.pop()
        if isinstance(item, XGBClassifier):
            item.set_params(device="cpu")
        elif isinstance(item, Pipeline):
            stack.extend(step for _, step in item.steps)
        elif isinstance(item, CalibratedClassifierCV):
            stack.extend(c.estimator for c in getattr(item, "calibrated_classifiers_", []))
            stack.append(item.estimator)


# --------------------------------------------------------------------------- full run
@dataclass
class TrainResult:
    kind: str
    features: list[str]
    comparison: pd.DataFrame
    tuned: list[Tuned]
    best: Tuned
    model: CalibratedClassifierCV
    explainer_pipeline: Pipeline
    threshold: float
    threshold_curve: pd.DataFrame
    test_metrics: dict
    test_proba: np.ndarray


def train_model(split: Split, kind: str, n_trials: int = 30, tune_top: int = 2) -> TrainResult:
    features = MODEL_FEATURES[kind]
    log.info("== %s model (%d features)", kind, len(features))
    comparison = compare_models(split, features)
    finalists = [m for m in comparison["model"] if m in DEPLOYABLE][:tune_top]
    tuned = [tune(split, name, features, n_trials) for name in finalists]
    best = pick_simplest(tuned)
    log.info("  chosen: %s (cv roc_auc %.4f)", best.name, best.cv_roc_auc)

    # Sigmoid (Platt) calibration: smooth, so small live changes move the score.
    calibrated = CalibratedClassifierCV(clone(best.pipeline), method="sigmoid", cv=5)
    X_tr = split.X_train[features]
    monthly_tr = split.X_train["monthly_charge"].to_numpy()
    oof = cross_val_predict(calibrated, X_tr, split.y_train, cv=CV, method="predict_proba")[:, 1]
    threshold, curve = choose_threshold(split.y_train, oof, monthly_tr)

    calibrated.fit(X_tr, split.y_train)
    explainer_pipeline = clone(best.pipeline).fit(X_tr, split.y_train)
    to_cpu(calibrated)
    to_cpu(explainer_pipeline)

    proba = calibrated.predict_proba(split.X_test[features])[:, 1]
    metrics = evaluate(split.y_test, proba, threshold, split.X_test["monthly_charge"].to_numpy())
    log.info("  test roc_auc=%.4f accuracy=%.4f (threshold %.2f)", metrics["roc_auc"],
             metrics["accuracy_at_0.5"], threshold)
    return TrainResult(kind, features, comparison, tuned, best, calibrated, explainer_pipeline,
                       threshold, curve, metrics, proba)


def importance(result: TrainResult, split: Split) -> tuple[pd.DataFrame, dict]:
    from .explain import Explainer

    background = split.X_train[result.features].sample(100, random_state=0)
    contrib = Explainer(result.explainer_pipeline, background, result.features).contributions(
        split.X_test[result.features])
    per_feature = contrib.abs().mean().sort_values(ascending=False)
    per_category = per_feature.groupby(lambda f: FEATURE_CATEGORY[f]).sum()
    per_category = (per_category / per_category.sum()).reindex(CATEGORIES).fillna(0)
    top = per_feature.head(15).rename("mean_abs_shap").reset_index().rename(columns={"index": "feature"})
    top["category"] = top["feature"].map(FEATURE_CATEGORY)
    return top, per_category.round(4).to_dict()


def export(split: Split, results: list[TrainResult], log_mlflow: bool = True) -> dict:
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    trained_at = datetime.now(UTC).isoformat(timespec="seconds")
    card = {
        "trained_at": trained_at,
        "dataset": "IBM Telco Customer Churn v11.1.3 (7,043 customers, California)",
        "train_rows": int(len(split.X_train)),
        "test_rows": int(len(split.X_test)),
        "churn_rate": float(split.y_train.mean()),
        "excluded_columns": LEAKY_COLUMNS,
        "business_assumptions": {
            "offer_months_of_bill": config.OFFER_MONTHS,
            "offer_success_rate": config.OFFER_SUCCESS_RATE,
            "months_of_value": config.MONTHS_OF_VALUE,
        },
        "versions": {"python": platform.python_version(), "scikit-learn": sklearn.__version__},
        "models": {},
    }
    for r in results:
        background = split.X_train[r.features].sample(100, random_state=0)
        top, by_category = importance(r, split)
        joblib.dump({
            "kind": r.kind,
            "model": r.model,
            "explainer_pipeline": r.explainer_pipeline,
            "background": background,
            "threshold": r.threshold,
            "features": r.features,
            "model_name": r.best.name,
            "trained_at": trained_at,
        }, config.MODEL_PATHS[r.kind], compress=3)
        card["models"][r.kind] = {
            "model_name": r.best.name,
            "features": len(r.features),
            "cv_roc_auc": r.best.cv_roc_auc,
            "best_params": r.best.params,
            "threshold": r.threshold,
            "test_metrics": r.test_metrics,
            "model_comparison": r.comparison.round(4).to_dict(orient="records"),
            "top_features": top.round(4).to_dict(orient="records"),
            "importance_by_category": by_category,
        }
    config.MODEL_CARD_PATH.write_text(json.dumps(card, indent=2, default=float))
    if log_mlflow:
        _log_mlflow(results, card)
    return card


def _log_mlflow(results: list[TrainResult], card: dict) -> None:
    os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
    import mlflow
    import mlflow.sklearn
    import skops.io as sio

    mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
    mlflow.set_experiment(config.MLFLOW_EXPERIMENT)
    for r in results:
        with mlflow.start_run(run_name=f"{r.kind}-{card['trained_at']}"):
            for row in r.comparison.to_dict(orient="records"):
                with mlflow.start_run(run_name=f"cv-{row['model']}", nested=True):
                    mlflow.log_metrics({k: float(v) for k, v in row.items() if k != "model"})
            for t in r.tuned:
                with mlflow.start_run(run_name=f"tuned-{t.name}", nested=True):
                    mlflow.log_params(t.params)
                    mlflow.log_metric("cv_roc_auc", t.cv_roc_auc)
            mlflow.log_params({"kind": r.kind, "model": r.best.name, "threshold": r.threshold,
                               "features": len(r.features)})
            mlflow.log_metrics({f"test_{k}": float(v) for k, v in r.test_metrics.items()
                                if isinstance(v, (int, float))})
            mlflow.log_artifact(str(config.MODEL_CARD_PATH))
            # MLflow saves with skops, which only loads explicitly trusted types.
            # These are our own freshly trained objects, so they are trusted.
            trusted = sio.get_untrusted_types(data=sio.dumps(r.model))
            mlflow.sklearn.log_model(r.model, name="model",
                                     registered_model_name=config.MLFLOW_MODEL_NAMES[r.kind],
                                     skops_trusted_types=trusted)


def train(n_trials: int = 30) -> tuple[Split, list[TrainResult]]:
    split = load_split()
    return split, [train_model(split, kind, n_trials) for kind in ("profile", "survey")]


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Train the ChurnPulse models")
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--no-mlflow", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    quiet_warnings()

    split, results = train(n_trials=args.trials)
    card = export(split, results, log_mlflow=not args.no_mlflow)
    for kind, m in card["models"].items():
        t = m["test_metrics"]
        print(f"{kind:8s} {m['model_name']:20s} ROC-AUC {t['roc_auc']:.4f}  accuracy {t['accuracy_at_0.5']:.4f}  "
              f"threshold {t['threshold']:.2f}  value ${t['retention_value']:,.0f}")


if __name__ == "__main__":
    main()
