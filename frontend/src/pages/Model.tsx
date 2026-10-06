import { useEffect, useState } from "react";
import { AlertTriangle, ShieldCheck, Sparkles } from "lucide-react";
import { Bar, BarChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type Category, type ModelCard, type ModelKind } from "../lib/api";
import { CATEGORY, featureLabel, money, pct } from "../lib/format";
import { ErrorBox, PageHeader, Section, Skeleton, Tabs } from "../components/ui";

const tooltipStyle = { background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 12, fontSize: 12, color: "var(--ink)" };
const nice = (s: string) => s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()).replace("Xgboost", "XGBoost").replace("Lightgbm", "LightGBM").replace("Catboost", "CatBoost");

export default function ModelPage() {
  const [card, setCard] = useState<ModelCard | null>(null);
  const [kind, setKind] = useState<ModelKind>("profile");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.model().then(setCard).catch((e) => setError(String(e.message))); }, []);

  if (error) return <ErrorBox error={error} />;
  if (!card) return <Skeleton className="h-[600px]" />;
  const m = card.models[kind];
  const t = m.test_metrics;
  const cm = t.confusion;
  const categories = (Object.entries(m.importance_by_category) as [Category, number][]).filter(([, v]) => v > 0);

  return (
    <div className="space-y-6">
      <PageHeader title="Models" subtitle={`${card.dataset} · ${card.train_rows.toLocaleString()} training / ${card.test_rows.toLocaleString()} held-out test customers · trained ${new Date(card.trained_at).toLocaleDateString()}`} />

      <div className="grid gap-4 md:grid-cols-2">
        {(["profile", "survey"] as const).map((k) => {
          const mm = card.models[k];
          const survey = k === "survey";
          return (
            <button key={k} onClick={() => setKind(k)}
                    className={`card p-6 text-left transition ${kind === k ? "ring-2 ring-brand-500" : "hover:ring-1 hover:ring-line"}`}>
              <div className="flex items-center gap-2">
                {survey ? <Sparkles className="h-5 w-5 text-pink-500" /> : <ShieldCheck className="h-5 w-5 text-sky-500" />}
                <h2 className="font-semibold text-ink">{survey ? "Survey model" : "Profile model"}</h2>
                <span className="chip ml-auto">{nice(mm.model_name)} · {mm.features} features</span>
              </div>
              <p className="mt-1 text-sm text-muted">{survey ? "Used when the customer answered a satisfaction survey." : "Used for every customer without a survey — including brand-new members."}</p>
              <div className="mt-5 grid grid-cols-3 gap-3">
                <div><p className="label">Accuracy</p><p className="mt-1 text-3xl font-bold tracking-tight text-ink">{pct(mm.test_metrics["accuracy_at_0.5"])}</p></div>
                <div><p className="label">ROC-AUC</p><p className="mt-1 text-3xl font-bold tracking-tight text-ink">{mm.test_metrics.roc_auc.toFixed(3)}</p></div>
                <div><p className="label">Value saved</p><p className="mt-1 text-3xl font-bold tracking-tight text-emerald-500">{money(mm.test_metrics.retention_value, true)}</p></div>
              </div>
            </button>
          );
        })}
      </div>

      <div className="flex items-start gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-ink-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
        <p><b className="text-ink">About the survey model's accuracy.</b> In this IBM dataset the satisfaction score is almost
          a copy of the answer — every customer scoring 1–2 left and nobody scoring 4–5 did. Real surveys are weaker signals,
          so expect the survey model to be less accurate on real customers. The profile model's ~85% is the dependable baseline.
          Columns only known after a customer leaves ({card.excluded_columns.slice(0, 4).join(", ")}…) are never used.</p>
      </div>

      <Tabs tabs={[{ id: "profile", label: "Profile model" }, { id: "survey", label: "Survey model" }]} active={kind} onChange={setKind} />

      <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {[["Accuracy @0.5", pct(t["accuracy_at_0.5"])], ["ROC-AUC", t.roc_auc.toFixed(3)], ["PR-AUC", t.pr_auc.toFixed(3)],
          ["Recall", pct(t.recall)], ["Precision", pct(t.precision)], ["Brier", t.brier.toFixed(3)]].map(([l, v]) => (
          <div key={l} className="card p-4"><p className="label">{l}</p><p className="mt-1 text-xl font-bold text-ink">{v}</p></div>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <Section title="What drives churn — by persona category" subtitle="Share of total explanation (SHAP) on the test set" className="lg:col-span-2">
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={categories.map(([c, v]) => ({ name: CATEGORY[c].label, value: v, color: CATEGORY[c].color }))}
                   dataKey="value" innerRadius={60} outerRadius={95} paddingAngle={3} stroke="none">
                {categories.map(([c]) => <Cell key={c} fill={CATEGORY[c].color} />)}
              </Pie>
              <Tooltip formatter={(v: number) => pct(v)} contentStyle={tooltipStyle} />
            </PieChart>
          </ResponsiveContainer>
          <ul className="mt-2 space-y-2">
            {categories.sort((a, b) => b[1] - a[1]).map(([c, v]) => {
              const Icon = CATEGORY[c].icon;
              return (
                <li key={c} className="flex items-center gap-2 text-sm">
                  <Icon className="h-4 w-4" style={{ color: CATEGORY[c].color }} />
                  <span className="flex-1 text-ink-2">{CATEGORY[c].label}</span>
                  <b className="tabular-nums text-ink">{pct(v)}</b>
                </li>
              );
            })}
          </ul>
        </Section>

        <Section title="Top features" subtitle="Mean absolute SHAP value (log-odds)" className="lg:col-span-3">
          <ResponsiveContainer width="100%" height={380}>
            <BarChart data={m.top_features.map((f) => ({ ...f, label: featureLabel(f.feature) }))} layout="vertical" margin={{ left: 10 }}>
              <XAxis type="number" tick={{ fontSize: 11, fill: "var(--muted)" }} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="label" width={160} tick={{ fontSize: 12, fill: "var(--ink-2)" }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "var(--surface-2)" }} />
              <Bar dataKey="mean_abs_shap" name="importance" radius={[0, 6, 6, 0]} isAnimationActive={false}>
                {m.top_features.map((f) => <Cell key={f.feature} fill={CATEGORY[f.category].color} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Section>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="Model comparison" subtitle="5-fold cross-validation on the training set">
          <table className="w-full text-sm">
            <thead><tr className="label text-left"><th className="pb-2">Model</th><th className="pb-2 text-right">ROC-AUC</th><th className="pb-2 text-right">Accuracy</th><th className="pb-2 text-right">Recall</th></tr></thead>
            <tbody className="divide-y divide-line">
              {m.model_comparison.map((r) => (
                <tr key={r.model} className={r.model === m.model_name ? "font-semibold text-brand-600 dark:text-brand-400" : "text-ink-2"}>
                  <td className="py-2.5">{nice(r.model)}{r.model === m.model_name && " ✓"}</td>
                  <td className="py-2.5 text-right tabular-nums">{r.roc_auc.toFixed(4)} <span className="text-xs text-muted">±{r.roc_auc_std.toFixed(3)}</span></td>
                  <td className="py-2.5 text-right tabular-nums">{pct(r.accuracy)}</td>
                  <td className="py-2.5 text-right tabular-nums">{pct(r.recall)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-xs text-muted">The top two were tuned with Optuna; the simplest model within 0.002 ROC-AUC of the best is deployed.</p>
        </Section>

        <Section title="Confusion matrix" subtitle={`Held-out test set at the business threshold (${m.threshold})`}>
          <div className="grid grid-cols-[auto_1fr_1fr] gap-2 text-center text-sm">
            <div /><div className="label">Predicted stay</div><div className="label">Predicted leave</div>
            <div className="label self-center">Stayed</div>
            <div className="rounded-xl bg-emerald-500/10 p-5 text-2xl font-bold text-emerald-600 dark:text-emerald-400">{cm.tn}</div>
            <div className="rounded-xl bg-amber-500/10 p-5 text-2xl font-bold text-amber-600 dark:text-amber-400">{cm.fp}</div>
            <div className="label self-center">Left</div>
            <div className="rounded-xl bg-rose-500/10 p-5 text-2xl font-bold text-rose-500">{cm.fn}</div>
            <div className="rounded-xl bg-emerald-500/10 p-5 text-2xl font-bold text-emerald-600 dark:text-emerald-400">{cm.tp}</div>
          </div>
          <p className="mt-4 rounded-xl bg-surface-2 p-3 text-sm text-ink-2">
            Contacting flagged customers would gain <b className="text-emerald-500">{money(t.retention_value)}</b> vs
            <b className="text-rose-500"> {money(t.retention_value_contact_everyone)}</b> if everyone got the offer.
          </p>
        </Section>
      </div>
    </div>
  );
}
