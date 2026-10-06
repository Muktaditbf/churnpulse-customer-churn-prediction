import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Archive, ArrowLeft, Check, HeartHandshake, Mail, MapPin, Pencil, Phone, Send, TrendingUp, X } from "lucide-react";
import { toast } from "sonner";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, ApiError, type Action, type Category, type CustomerDetail } from "../lib/api";
import { CATEGORY, EVENT_LABELS, featureLabel, formatValue, MODEL_LABEL, money, pct, timeAgo } from "../lib/format";
import { useLive } from "../lib/useLive";
import {
  Avatar, CategoryBadge, Empty, ErrorBox, Gauge, ModelChip, ReasonBars, RiskBadge, Section, Skeleton, Stat, Tabs,
} from "../components/ui";

const PROFILE_GROUPS: Record<Category, string[]> = {
  geographic: ["city", "zip_code", "latitude", "longitude", "population"],
  demographic: ["gender", "age", "married", "num_dependents"],
  technographic: ["internet_type", "avg_monthly_gb", "unlimited_data", "phone_service", "multiple_lines", "online_security",
                  "online_backup", "device_protection", "premium_tech_support", "streaming_tv", "streaming_movies", "streaming_music"],
  behavioural: ["tenure_months", "contract", "payment_method", "paperless_billing", "offer", "monthly_charge", "total_charges",
                "total_refunds", "total_extra_data_charges", "avg_long_distance"],
  psychographic: ["satisfaction_score", "referrals"],
};

type Tab = Category | "timeline";

export function ActionCard({ action, onDone, customerId, compact = false }: {
  action: Action; customerId: string; onDone?: () => void; compact?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const record = async (status: "contacted" | "accepted" | "declined") => {
    setBusy(true);
    try {
      await api.recordAction({ customer_id: customerId, action_id: action.action_id, status });
      toast.success(status === "accepted" ? `“${action.title}” accepted — risk updating live` : `Logged as ${status}`);
      onDone?.();
    } catch (e) {
      toast.error(String((e as Error).message));
    }
    setBusy(false);
  };
  return (
    <div className="rounded-xl border border-line bg-surface-2/60 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-semibold text-ink">{action.title}</p>
          <p className="text-xs text-muted">{action.description}</p>
        </div>
        <span className="shrink-0 rounded-lg bg-emerald-500/10 px-2 py-1 text-xs font-bold text-emerald-600 dark:text-emerald-400">
          +{money(action.expected_value)}
        </span>
      </div>
      <div className="mt-3 flex items-center gap-2 text-sm">
        <span className="font-semibold tabular-nums text-rose-500">{pct(action.probability_before, 0)}</span>
        <div className="relative h-1.5 flex-1 rounded-full bg-line">
          <div className="absolute inset-y-0 rounded-full bg-gradient-to-r from-emerald-400 to-rose-400"
               style={{ left: `${action.probability_after * 100}%`, right: `${100 - action.probability_before * 100}%` }} />
        </div>
        <span className="font-semibold tabular-nums text-emerald-500">{pct(action.probability_after, 0)}</span>
      </div>
      <p className="mt-2 text-xs text-muted">
        Cost {money(action.cost)} · reach via <b className="text-ink-2">{action.channel}</b>
        {action.why.length > 0 && <> · {action.why.join(", ")}</>}
      </p>
      {!compact && (
        <div className="mt-3 flex flex-wrap gap-2">
          <button disabled={busy} onClick={() => record("accepted")} className="btn-primary !px-3 !py-1.5 text-xs"><Check className="h-3.5 w-3.5" /> Accepted</button>
          <button disabled={busy} onClick={() => record("contacted")} className="btn-ghost !px-3 !py-1.5 text-xs"><Send className="h-3.5 w-3.5" /> Contacted</button>
          <button disabled={busy} onClick={() => record("declined")} className="btn-ghost !px-3 !py-1.5 text-xs"><X className="h-3.5 w-3.5" /> Declined</button>
        </div>
      )}
    </div>
  );
}

export default function Customer360() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState<CustomerDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("behavioural");
  const [running, setRunning] = useState<string | null>(null);

  const load = useCallback(async (attempt = 0): Promise<void> => {
    try {
      setData(await api.customer(id));
      setError(null);
    } catch (e) {
      // A brand-new customer is being scored by Flink - retry for a few seconds.
      if (e instanceof ApiError && e.status === 409 && attempt < 20) {
        await new Promise((r) => setTimeout(r, 700));
        return load(attempt + 1);
      }
      setError((e as Error).message);
    }
  }, [id]);
  useEffect(() => { setData(null); load(); }, [load]);

  useLive(useCallback((m) => { if (m.type === "prediction" && m.data.customer_id === id) load(); }, [id, load]));

  const scenario = async (name: "churn_risk" | "loyalty") => {
    setRunning(name);
    try {
      await api.scenario(id, name);
      toast.message(name === "churn_risk" ? "Sending churn signals through Kafka…" : "Sending loyalty events through Kafka…");
    } catch (e) { toast.error((e as Error).message); }
    setTimeout(() => setRunning(null), 2500);
  };

  const archive = async () => {
    if (!confirm("Archive this customer? They will be hidden from lists; history is kept.")) return;
    await api.archive(id);
    toast.success("Customer archived");
    navigate("/customers");
  };

  if (error && !data) return <ErrorBox error={error} />;
  if (!data) return (
    <div className="space-y-6"><Skeleton className="h-24" /><div className="grid gap-6 lg:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-80" />)}</div></div>
  );

  const history = [...data.history].reverse().map((h, i) => ({ ...h, step: i + 1 }));
  const tabs: { id: Tab; label: string; icon?: React.ReactNode }[] = [
    ...(Object.keys(PROFILE_GROUPS) as Category[]).map((c) => {
      const Icon = CATEGORY[c].icon;
      return { id: c as Tab, label: CATEGORY[c].label, icon: <Icon className="h-3.5 w-3.5" style={{ color: CATEGORY[c].color }} /> };
    }),
    { id: "timeline", label: "Timeline" },
  ];

  return (
    <div className="space-y-6">
      <Link to="/customers" className="inline-flex items-center gap-1 text-sm text-muted hover:text-ink"><ArrowLeft className="h-4 w-4" /> Customers</Link>

      <div className="card relative overflow-hidden p-6">
        <div className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-brand-500/10 blur-3xl" />
        <div className="relative flex flex-wrap items-center gap-5">
          <Avatar id={data.customer_id} name={data.name} size="lg" />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-bold tracking-tight text-ink">{data.name}</h1>
              <RiskBadge band={data.risk_band} />
              <ModelChip kind={data.model_used} />
              {data.source !== "dataset" && <span className="chip">{data.source === "import" ? "Imported" : "Added manually"}</span>}
            </div>
            <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted">
              <span className="font-mono">{data.customer_id}</span>
              {data.email && <span className="flex items-center gap-1.5"><Mail className="h-3.5 w-3.5" />{data.email}</span>}
              {data.phone && <span className="flex items-center gap-1.5"><Phone className="h-3.5 w-3.5" />{data.phone}</span>}
              {data.city && <span className="flex items-center gap-1.5"><MapPin className="h-3.5 w-3.5" />{data.city}</span>}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link to={`/customers/${id}/edit`} className="btn-ghost"><Pencil className="h-4 w-4" /> Edit</Link>
            <button className="btn-ghost" disabled={!!running} onClick={() => scenario("churn_risk")}><TrendingUp className="h-4 w-4 text-rose-500" /> Churn signals</button>
            <button className="btn-ghost" disabled={!!running} onClick={() => scenario("loyalty")}><HeartHandshake className="h-4 w-4 text-emerald-500" /> Loyalty signals</button>
            <button className="btn-danger" onClick={archive}><Archive className="h-4 w-4" /></button>
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Section title="Churn risk" subtitle={`${MODEL_LABEL[data.model_used]} · updated ${timeAgo(data.updated_at)}`}>
          <Gauge probability={data.probability} band={data.risk_band} threshold={data.threshold} />
          <p className={`mt-3 text-center text-lg font-semibold ${data.will_churn ? "text-rose-500" : "text-emerald-500"}`}>
            {data.will_churn ? "Likely to leave" : "Likely to stay"}
          </p>
          <div className="mt-4 grid grid-cols-2 gap-2">
            <Stat label="12-mo value at risk" value={money(data.probability * data.monthly_charges * 12)} />
            <Stat label="Lifetime value" value={data.cltv ? money(data.cltv) : "—"} />
            <Stat label="Events (10 min)" value={data.signals?.events_10m ?? 0} />
            <Stat label="Downgrades (10 min)" value={data.signals?.downgrades_10m ?? 0} tone={(data.signals?.downgrades_10m ?? 0) > 0 ? "bad" : undefined} />
          </div>
        </Section>

        <Section title="Why this score" subtitle="Top factors right now (SHAP), by persona category">
          <ReasonBars reasons={data.reasons} />
        </Section>

        <Section title="Recommended actions" subtitle="Ranked by expected value saved">
          {data.actions.length === 0 ? <Empty text={data.will_churn ? "No action lowers the risk further." : "Low risk — no action needed."} /> : (
            <div className="space-y-3">
              {data.actions.map((a) => <ActionCard key={a.action_id} action={a} customerId={id} onDone={() => setTimeout(load, 1200)} />)}
            </div>
          )}
        </Section>
      </div>

      <Section>
        <div className="mb-5"><Tabs tabs={tabs} active={tab} onChange={setTab} /></div>
        {tab === "timeline" ? (
          <div className="grid gap-6 lg:grid-cols-5">
            <div className="lg:col-span-3">
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={history} margin={{ left: -10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
                  <XAxis dataKey="step" tick={{ fontSize: 11, fill: "var(--muted)" }} axisLine={false} tickLine={false} />
                  <YAxis domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} tick={{ fontSize: 11, fill: "var(--muted)" }} axisLine={false} tickLine={false} />
                  <Tooltip formatter={(v: number) => pct(v)} contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 12 }}
                           labelFormatter={(s) => { const h = history[Number(s) - 1]; return h ? EVENT_LABELS[h.event_type] ?? h.event_type : ""; }} />
                  <ReferenceLine y={data.threshold} stroke="var(--muted)" strokeDasharray="4 4" />
                  <Line type="monotone" dataKey="probability" stroke="#14c9a8" strokeWidth={2.5} dot={{ r: 3, fill: "#14c9a8" }} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <ul className="max-h-[260px] space-y-1 overflow-y-auto pr-1 lg:col-span-2">
              {data.history.map((h, i) => (
                <li key={i} className="flex items-center justify-between rounded-lg px-2 py-1.5 text-sm hover:bg-surface-2">
                  <span className="flex items-center gap-2 text-ink-2">
                    {EVENT_LABELS[h.event_type] ?? h.event_type}
                    {h.event_source && h.event_source !== "simulator" && <span className="text-[10px] text-muted">({h.event_source.split(":")[0]})</span>}
                    {h.alert && <span className="rounded bg-rose-500/15 px-1 text-[10px] font-bold text-rose-500">ALERT</span>}
                  </span>
                  <span className="flex items-center gap-3"><b className="tabular-nums text-ink">{pct(h.probability)}</b><span className="w-14 text-right text-xs text-muted">{timeAgo(h.created_at)}</span></span>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <div>
            <div className="mb-4 flex items-center justify-between">
              <CategoryBadge category={tab} />
              <span className="text-xs text-muted">{CATEGORY[tab].hint}</span>
            </div>
            <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
              {PROFILE_GROUPS[tab].map((k) => (
                <div key={k} className="flex items-center justify-between border-b border-line pb-2">
                  <dt className="text-sm text-muted">{featureLabel(k)}</dt>
                  <dd className="text-sm font-medium text-ink">{k === "satisfaction_score" && data.profile[k] == null ? "No survey yet" : formatValue(data.profile[k], k)}</dd>
                </div>
              ))}
              {tab === "psychographic" && (["price_sensitivity", "brand_loyalty", "preferred_channel", "lifestyle"] as const).map((k) => (
                <div key={k} className="flex items-center justify-between border-b border-line pb-2">
                  <dt className="text-sm text-muted">{featureLabel(k).replace(/_/g, " ")} <span className="text-[10px]">(advice only)</span></dt>
                  <dd className="text-sm font-medium text-ink">{formatValue(data.persona?.[k])}</dd>
                </div>
              ))}
            </dl>
            {tab === "psychographic" && data.persona?.interests && data.persona.interests.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-2">{data.persona.interests.map((i) => <span key={i} className="chip">{i}</span>)}</div>
            )}
          </div>
        )}
      </Section>

      {data.actions_log.length > 0 && (
        <Section title="Retention history" subtitle="Outreach logged for this customer">
          <ul className="divide-y divide-line">
            {data.actions_log.map((a) => (
              <li key={a.id} className="flex items-center justify-between py-2.5 text-sm">
                <span className="text-ink-2">{a.title} <span className="text-muted">via {a.channel}</span></span>
                <span className="flex items-center gap-3">
                  <span className={`chip ${a.status === "accepted" ? "!text-emerald-600" : a.status === "declined" ? "!text-rose-500" : ""}`}>{a.status}</span>
                  <span className="text-xs text-muted">{timeAgo(a.created_at)}</span>
                </span>
              </li>
            ))}
          </ul>
        </Section>
      )}
      {data.dataset_label != null && (
        <p className="text-xs text-muted">Reference: in the original IBM data this customer {data.dataset_label ? "did" : "did not"} churn. Live events since then are simulated.</p>
      )}
    </div>
  );
}
