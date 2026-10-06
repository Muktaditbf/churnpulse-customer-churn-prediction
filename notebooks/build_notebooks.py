"""Generate the four project notebooks (v2: persona data, two models)."""

from pathlib import Path

import nbformat as nbf

HERE = Path(__file__).parent

SETUP = """\
%matplotlib inline
import warnings, os
warnings.filterwarnings("ignore")
os.environ["MLFLOW_DISABLE_AGENT_HINT"] = "1"
import numpy as np, pandas as pd, matplotlib.pyplot as plt, seaborn as sns
from churnpulse import config
from churnpulse.dataset import load_customers
from churnpulse.features import FEATURE_CATEGORY, CATEGORIES
sns.set_theme(style="whitegrid", palette=["#0aa38a", "#f43f5e", "#f59e0b", "#6366f1", "#38bdf8"])
CAT_COLORS = {"geographic": "#38bdf8", "demographic": "#a78bfa", "technographic": "#22d3ee",
              "behavioural": "#fbbf24", "psychographic": "#f472b6"}
pd.set_option("display.max_columns", 50)
"""


def nb(cells):
    book = nbf.v4.new_notebook()
    book.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    book.cells = [nbf.v4.new_markdown_cell(c[3:]) if c.startswith("md:") else nbf.v4.new_code_cell(c) for c in cells]
    return book


def churn_by(cols, title):
    return (f"fig, axes = plt.subplots(1, {len(cols)}, figsize=({5 * len(cols)}, 4))\n"
            f"for ax, col in zip(np.atleast_1d(axes), {cols!r}):\n"
            "    (df.groupby(col)['churned'].mean().sort_values() * 100).plot.barh(ax=ax, color='#0aa38a')\n"
            "    ax.set_title(col); ax.set_xlabel('churn rate %'); ax.set_ylabel('')\n"
            f"fig.suptitle({title!r}, fontweight='bold'); plt.tight_layout(); plt.show()")


EDA = [
    "md:# 01 · Exploratory data analysis — by persona category\n\n"
    "**Dataset:** IBM Telco Customer Churn **v11.1.3** — 7,043 customers of a California telecom company, "
    "merged from five IBM tables (demographics, location, population, services, status). Names, emails and phone "
    "numbers are generated for display; they are never model inputs.\n\n"
    "We look at churn through five lenses: **geographic, demographic, technographic, behavioural, psychographic**.",
    SETUP,
    "df = load_customers()\nprint(df.shape)\ndf.head(3).T",
    "rate = df['churned'].mean()\nprint(f'Churn rate: {rate:.1%}  ({df.churned.sum():,} of {len(df):,} customers left)')",
    "md:About **26.5%** left. Predicting \"nobody leaves\" already scores 73.5% accuracy, so ROC-AUC, recall and a "
    "business metric matter more than accuracy alone.",
    "md:## 🌍 Geographic",
    "fig, ax = plt.subplots(figsize=(7, 8))\nsc = ax.scatter(df.longitude, df.latitude, c=df.churned, cmap='RdYlGn_r', s=4, alpha=.6)\n"
    "ax.set_title('Customers by location (red = churned)'); ax.set_aspect(1.2); plt.show()",
    "city = df.groupby('city').agg(customers=('customer_id', 'size'), churn=('churned', 'mean')).query('customers >= 30')\n"
    "city.sort_values('churn', ascending=False).head(10).style.format({'churn': '{:.0%}'})",
    "md:Churn is spread across the state; some cities run hotter, but most have too few customers to learn from "
    "directly — so the model uses **latitude, longitude and area population** instead of the city name.",
    "md:## 👥 Demographic",
    "fig, axes = plt.subplots(1, 2, figsize=(13, 4))\n"
    "sns.kdeplot(data=df, x='age', hue='churned', common_norm=False, fill=True, ax=axes[0]); axes[0].set_title('Age')\n"
    "(df.groupby('num_dependents')['churned'].mean() * 100).plot.bar(ax=axes[1], color='#a78bfa', rot=0)\n"
    "axes[1].set_title('Churn % by number of dependents'); plt.tight_layout(); plt.show()",
    "md:Seniors churn more; customers **with dependents rarely leave** — one of the strongest demographic signals.",
    "md:## 💻 Technographic",
    churn_by(["internet_type", "premium_tech_support", "online_security", "unlimited_data"], "Technographic"),
    "md:**Fiber optic** customers churn most, and those without tech support or security churn far more — "
    "they are paying for speed but not for help.",
    "md:## 🔁 Behavioural",
    churn_by(["contract", "payment_method", "offer"], "Behavioural"),
    "fig, axes = plt.subplots(1, 2, figsize=(13, 4))\n"
    "sns.kdeplot(data=df, x='tenure_months', hue='churned', common_norm=False, fill=True, ax=axes[0]); axes[0].set_title('Tenure')\n"
    "sns.kdeplot(data=df, x='monthly_charge', hue='churned', common_norm=False, fill=True, ax=axes[1]); axes[1].set_title('Monthly charge')\n"
    "plt.tight_layout(); plt.show()",
    "md:Month-to-month contracts, mailed checks, **Offer E** and the first months are high-risk.",
    "md:## 🧠 Psychographic",
    "fig, axes = plt.subplots(1, 2, figsize=(13, 4))\n"
    "(df.groupby(df.referrals.clip(upper=5))['churned'].mean() * 100).plot.bar(ax=axes[0], color='#f472b6', rot=0)\n"
    "axes[0].set_title('Churn % by referrals made (5 = 5+)')\n"
    "(df.groupby('satisfaction_score')['churned'].mean() * 100).plot.bar(ax=axes[1], color='#f472b6', rot=0)\n"
    "axes[1].set_title('Churn % by satisfaction score'); plt.tight_layout(); plt.show()",
    "md:Customers who **refer friends** almost never leave (advocacy). Satisfaction separates churners *perfectly* "
    "— see the leakage analysis in notebook 03.",
]

FEATURES = [
    "md:# 02 · Feature engineering\n\n"
    "All feature logic lives in **`src/churnpulse/features.py`** — shared by this notebook, training, the Flink "
    "streaming job, the API and the action center (no training/serving skew). Every feature belongs to one persona "
    "category, which drives the dashboard's grouped explanations.",
    SETUP,
    "from churnpulse.features import build_features, PROFILE_FEATURES, SURVEY_FEATURES\n"
    "df = load_customers(); X = build_features(df)\n"
    "pd.Series(FEATURE_CATEGORY).value_counts().rename('features').to_frame()",
    "md:## Engineered features\n| Feature | Category | Why |\n|---|---|---|\n"
    "| `log_population` | geographic | area density on a sensible scale |\n"
    "| `under_30`, `senior` | demographic | life-stage effects in age |\n"
    "| `num_addons`, `num_protection` | technographic | more services = more locked in |\n"
    "| `gb_per_dollar` | technographic | perceived value of the plan |\n"
    "| `charge_increase_ratio` | behavioural | today's bill vs historic average — price rises trigger churn |\n"
    "| `contract_months`, `auto_pay`, `had_refund`, `extra_data_share`, `tenure_group` | behavioural | commitment, friction, problems |\n"
    "| `referred_a_friend` | psychographic | advocacy / loyalty |",
    "new = ['under_30', 'senior', 'num_addons', 'num_protection', 'gb_per_dollar', 'charge_increase_ratio',\n"
    "       'contract_months', 'auto_pay', 'had_refund', 'referred_a_friend']\n"
    "X[new].assign(churned=df.churned).groupby('churned').mean().T.round(3)",
    "md:## Same function for one live customer\nThis is exactly what the Flink job and the API call:",
    "from churnpulse.features import profile_to_frame, PROFILE_FIELDS\n"
    "profile = df.iloc[0][PROFILE_FIELDS].to_dict()\nprofile_to_frame(profile)[SURVEY_FEATURES].T.head(15)",
    "md:## Two feature sets\n* **Profile model:** every feature except the satisfaction survey.\n"
    "* **Survey model:** the same plus `satisfaction_score`.",
    "print(len(PROFILE_FEATURES), 'profile features;', len(SURVEY_FEATURES), 'survey features')",
]

MODELING = [
    "md:# 03 · Two models: selection, tuning, calibration, evaluation\n\n"
    "1. **Leakage analysis** — which columns cannot be used\n"
    "2. For each model: compare 5 algorithms with 5-fold CV → tune the top two (Optuna) → simplest within 0.002 "
    "ROC-AUC wins → sigmoid calibration → business threshold → one evaluation on the untouched test set.\n\n"
    "XGBoost trains on the **RTX 4060 GPU**. Every run is logged to **MLflow**.",
    SETUP,
    "md:## 1 · Leakage analysis",
    "pd.crosstab(load_customers().satisfaction_score, load_customers().churned, margins=True)",
    "md:**Every** customer with satisfaction 1–2 churned and **none** with 4–5 did. In this dataset the survey is "
    "almost a copy of the answer. Real surveys are weaker, so:\n\n"
    "* the **profile model** (no survey) is the dependable baseline and scores new members;\n"
    "* the **survey model** uses it when available — its accuracy is reported, with this caveat.\n\n"
    "Columns known only *after* a customer leaves are always excluded:",
    "from churnpulse.dataset import LEAKY_COLUMNS\nLEAKY_COLUMNS",
    "md:## 2 · Train both models",
    "import logging\nlogging.basicConfig(level=logging.INFO, format='%(message)s')\n"
    "from churnpulse import train as T\nT.quiet_warnings()\nsplit, results = T.train(n_trials=30)",
    "for r in results:\n    print(f'\\n=== {r.kind} model ===')\n    display(r.comparison.round(4))",
    "fig, axes = plt.subplots(1, 2, figsize=(14, 4))\n"
    "for ax, r in zip(axes, results):\n"
    "    r.comparison.plot.barh(x='model', y='roc_auc', xerr='roc_auc_std', legend=False, ax=ax, color='#0aa38a')\n"
    "    ax.set_xlim(r.comparison.roc_auc.min() - 0.03, 1); ax.set_title(f'{r.kind} model · CV ROC-AUC')\n"
    "plt.tight_layout(); plt.show()",
    "md:## 3 · Held-out test results",
    "pd.DataFrame({r.kind: {k: v for k, v in r.test_metrics.items() if not isinstance(v, dict)} for r in results}).round(4)",
    "from sklearn.metrics import ConfusionMatrixDisplay, RocCurveDisplay\nfrom sklearn.calibration import CalibrationDisplay\n"
    "fig, axes = plt.subplots(2, 3, figsize=(18, 10))\n"
    "for row, r in zip(axes, results):\n"
    "    ConfusionMatrixDisplay.from_predictions(split.y_test, (r.test_proba >= r.threshold).astype(int), display_labels=['stay', 'leave'], ax=row[0], colorbar=False, cmap='Greens')\n"
    "    RocCurveDisplay.from_predictions(split.y_test, r.test_proba, ax=row[1])\n"
    "    CalibrationDisplay.from_predictions(split.y_test, r.test_proba, n_bins=10, ax=row[2])\n"
    "    for ax, t in zip(row, ['confusion matrix', 'ROC', 'calibration']): ax.set_title(f'{r.kind}: {t}')\n"
    "plt.tight_layout(); plt.show()",
    "for r in results:\n    m = r.test_metrics\n"
    "    print(f\"{r.kind:8s} {r.best.name:12s} accuracy {m['accuracy_at_0.5']:.1%}  ROC-AUC {m['roc_auc']:.3f}  \"\n"
    "          f\"saves ${m['retention_value']:,.0f} vs ${m['retention_value_contact_everyone']:,.0f} contacting everyone\")",
    "md:## 4 · Export\n`make train` (`python -m churnpulse.train`) runs exactly this code, exports both models and "
    "registers them in MLflow. Set `EXPORT = True` to export from here.",
    "EXPORT = False\nif EXPORT:\n    T.export(split, results)",
]

EXPLAIN = [
    "md:# 04 · Explainability by persona category\n\nEvery live prediction comes with its top reasons. Tree models "
    "use **native, exact SHAP contributions** (no `shap` library needed in production).",
    SETUP,
    "import json\nfrom churnpulse.predict import ChurnModel\nfrom churnpulse.train import load_split\n"
    "model = ChurnModel(); card = json.loads(config.MODEL_CARD_PATH.read_text()); split = load_split()\n"
    "{k: (m.model_name, round(card['models'][k]['test_metrics']['roc_auc'], 4)) for k, m in model.models.items()}",
    "fig, axes = plt.subplots(1, 2, figsize=(13, 4))\n"
    "for ax, kind in zip(axes, ['profile', 'survey']):\n"
    "    s = pd.Series(card['models'][kind]['importance_by_category'])\n"
    "    s.plot.pie(ax=ax, colors=[CAT_COLORS[c] for c in s.index], autopct='%1.0f%%', ylabel='')\n"
    "    ax.set_title(f'{kind} model · share of explanation')\nplt.show()",
    "contrib = model.profile.explainer.contributions(split.X_test)\nimp = contrib.abs().mean().sort_values().tail(15)\n"
    "imp.plot.barh(color=[CAT_COLORS[FEATURE_CATEGORY[f]] for f in imp.index], figsize=(8, 6))\n"
    "plt.title('Profile model · top features (colour = persona category)'); plt.show()",
    "md:## Exactness check\nContributions + the base value must equal the model's raw score:",
    "e = model.profile.explainer\nXt = e.prep.transform(split.X_test[model.profile.features].head(500))\n"
    "full = e.model.predict(Xt, pred_contrib=True)\nnp.allclose(full.sum(axis=1), e.model.predict(Xt, raw_score=True))",
    "md:## Explaining single customers",
    "proba = model.profile.proba(split.X_test)\nfor label, idx in [('highest risk', proba.idxmax()), ('lowest risk', proba.idxmin())]:\n"
    "    print(f'--- {label}: p={proba[idx]:.3f}, actually churned={split.y_test[idx]}')\n"
    "    for r in model.profile.explainer.reasons(split.X_test.loc[[idx]]): print('   ', r)",
    "md:## Retention actions for a risky customer\nThe action center re-scores counterfactuals with the same model:",
    "from churnpulse.actions import recommend\nfrom churnpulse.features import PROFILE_FIELDS\n"
    "row = load_customers().set_index('customer_id').loc[split.ids_test.loc[proba.idxmax()]]\n"
    "profile = {**row[PROFILE_FIELDS].to_dict(), 'satisfaction_score': None}\n"
    "pd.DataFrame(recommend(model, profile, {'price_sensitivity': 5}, top=5))[['title', 'probability_before', 'probability_after', 'expected_value', 'why']]",
]

for name, cells in [("01_eda", EDA), ("02_features", FEATURES), ("03_modeling", MODELING), ("04_explainability", EXPLAIN)]:
    nbf.write(nb(cells), HERE / f"{name}.ipynb")
    print("wrote", name)
