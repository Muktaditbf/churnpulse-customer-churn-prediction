import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, DollarSign, Radio, Target, UserPlus, Users, Zap } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type CustomerRow, type LiveItem, type Stats } from "../lib/api";
import { EVENT_LABELS, money, num, pct, timeAgo } from "../lib/format";
import { useLive, type LiveMessage } from "../lib/useLive";
import RiskMap from "../components/RiskMap";
import { Avatar, Delta, Empty, ErrorBox, Kpi, ModelChip, PageHeader, RiskBadge, Section, Skeleton } from "../components/ui";

const tooltipStyle = { background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 12, fontSize: 12, color: "var(--ink)" };

export default function Overview() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [points, setPoints] = useState<[string, number, number, number][]>([]);
  const [feed, setFeed] = useState<(LiveItem & { _key: string })[]>([]);
  const [top, setTop] = useState<CustomerRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    Promise.all([api.stats(), api.customers({ sort: "value", band: "high", limit: 6 })])
      .then(([s, c]) => { setStats(s); setTop(c.items); setError(null); })
      .catch((e) => setError(String(e.message ?? e)));
  }, []);

  useEffect(() => {
    refresh();
    api.map().then(setPoints).catch(() => {});
    api.live(20).then((items) => setFeed(items.map((i, n) => ({ ...i, _key: `init-${n}` })))).catch(() => {});
    const t1 = setInterval(refresh, 5000);
    const t2 = setInterval(() => api.map().then(setPoints).catch(() => {}), 30000);
    return () => { clearInterval(t1); clearInterval(t2); };
  }, [refresh]);

  const connected = useLive(useCallback((m: LiveMessage) => {
    if (m.type === "prediction") {
      setFeed((f) => [{ ...m.data, _key: `${m.data.customer_id}-${m.data.scored_at}` }, ...f].slice(0, 20));
    }
  }, []));

  if (error && !stats) return <ErrorBox error={`Cannot reach the API: ${error}`} />;

  const total = stats?.customers_scored || 1;
  const timeline = (stats?.timeline ?? []).map((t) => ({
    ...t, time: new Date(t.window_end).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
  }));
  const distribution = Array.from({ length: 20 }, (_, i) => ({
    range: `${i * 5}%`, from: i / 20, customers: stats?.distribution.find((d) => d.bucket === i + 1)?.customers ?? 0,
  }));

  return (
    <div className="space-y-6">
      <PageHeader title="Overview" subtitle="Every customer, scored live as events stream through Kafka and Flink."
        actions={
          <span className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-medium ring-1 ${
            connected ? "bg-emerald-500/10 text-emerald-600 ring-emerald-500/25 dark:text-emerald-400" : "bg-surface-2 text-muted ring-line"}`}>
            <Radio className={`h-4 w-4 ${connected ? "animate-pulse" : ""}`} />
            {connected ? "Live" : "Reconnecting…"}
            {stats?.p50_latency_ms != null && <span className="text-xs opacity-70">· {Math.round(stats.p50_latency_ms)} ms</span>}
          </span>
        } />

      {!stats ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[118px]" />)}</div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Kpi label="Customers monitored" value={num(stats.customers_scored)} icon={<Users className="h-5 w-5" />}
               hint={<>avg risk {pct(stats.avg_probability)} · <span className="text-brand-600 dark:text-brand-400">{num(stats.new_members)} new members</span></>} />
          <Kpi label="High risk" tone="rose" delay={0.05} value={num(stats.high_risk)} icon={<AlertTriangle className="h-5 w-5" />}
               hint={`${pct(stats.high_risk / total)} of base · ${num(stats.flagged)} need action`} />
          <Kpi label="Revenue at risk (12 mo)" tone="amber" delay={0.1} value={money(stats.expected_revenue_at_risk, true)}
               icon={<DollarSign className="h-5 w-5" />} hint={`lifetime value at risk ${money(stats.cltv_at_risk, true)}`} />
          <Kpi label="Retention wins" tone="violet" delay={0.15} value={num(stats.actions.accepted)}
               icon={<Target className="h-5 w-5" />} hint={`${money(stats.actions.value_saved)} expected value saved`} />
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-5">
        <Section title="Risk map" subtitle="Every customer by location · click a point to open them" className="xl:col-span-3">
          {points.length ? <RiskMap points={points} /> : <Skeleton className="h-[380px]" />}
        </Section>
        <div className="space-y-6 xl:col-span-2">
          <Section title="Risk distribution" subtitle="Customers by chance of leaving">
            <ResponsiveContainer width="100%" height={170}>
              <BarChart data={distribution} margin={{ left: -20 }}>
                <XAxis dataKey="range" tick={{ fontSize: 10, fill: "var(--muted)" }} interval={4} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: "var(--muted)" }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "var(--surface-2)" }} />
                <Bar dataKey="customers" radius={[4, 4, 0, 0]}>
                  {distribution.map((d) => <Cell key={d.range} fill={d.from >= 0.55 ? "#f43f5e" : d.from >= 0.3 ? "#f59e0b" : "#10b981"} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Section>
          <Section title="Stream activity" subtitle="Live events and alerts per 10-second Flink window">
            <ResponsiveContainer width="100%" height={150}>
              <AreaChart data={timeline} margin={{ left: -20 }}>
                <defs>
                  <linearGradient id="ev" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#14c9a8" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="#14c9a8" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
                <XAxis dataKey="time" tick={{ fontSize: 10, fill: "var(--muted)" }} minTickGap={40} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: "var(--muted)" }} allowDecimals={false} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={tooltipStyle} />
                <Area type="monotone" dataKey="live_events" name="events" stroke="#14c9a8" fill="url(#ev)" strokeWidth={2} />
                <Area type="monotone" dataKey="alerts" name="alerts" stroke="#f43f5e" fill="#f43f5e" fillOpacity={0.12} strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
            <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
              <div><p className="font-semibold text-ink tabular-nums">{num(stats?.events_last_minute)}</p><p className="text-muted">events/min</p></div>
              <div><p className="font-semibold text-ink tabular-nums">{stats?.p95_latency_ms == null ? "–" : `${Math.round(stats.p95_latency_ms)} ms`}</p><p className="text-muted">p95 latency</p></div>
              <div><p className="font-semibold text-ink tabular-nums">{num(stats?.alerts_last_hour)}</p><p className="text-muted">alerts/hour</p></div>
            </div>
          </Section>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-5">
        <Section title="Live predictions" subtitle="Each event re-scores the customer instantly" className="xl:col-span-3"
                 action={<Zap className="h-5 w-5 text-brand-500" />}>
          {feed.length === 0 ? <Empty text="Waiting for live events…" /> : (
            <ul className="-mx-2 divide-y divide-line">
              <AnimatePresence initial={false}>
                {feed.map((e) => (
                  <motion.li key={e._key} layout initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
                             className="flash flex items-center gap-3 rounded-xl px-2 py-2.5">
                    <Avatar id={e.customer_id} name={e.name} size="sm" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <Link to={`/customers/${e.customer_id}`} className="truncate text-sm font-semibold text-ink hover:text-brand-600">
                          {e.name ?? e.customer_id}
                        </Link>
                        <ModelChip kind={e.model_used} />
                        {e.alert && (
                          <span className="rounded-md bg-rose-500 px-1.5 py-0.5 text-[10px] font-bold uppercase text-white">
                            {e.alert === "crossed_threshold" ? "now at risk" : "risk jumped"}
                          </span>
                        )}
                      </div>
                      <p className="truncate text-xs text-muted">
                        {EVENT_LABELS[e.event_type] ?? e.event_type} · {e.contract} · {e.city ?? ""}
                        {e.event_source?.startsWith("scenario") || e.event_source?.startsWith("action") ? " · demo/action" : ""}
                      </p>
                    </div>
                    <Delta value={e.delta} />
                    <span className="w-11 text-right text-sm font-semibold tabular-nums text-ink">{pct(e.probability, 0)}</span>
                    <RiskBadge band={e.risk_band} />
                    <span className="hidden w-14 text-right text-xs text-muted lg:block">{timeAgo(e.scored_at ?? e.created_at)}</span>
                  </motion.li>
                ))}
              </AnimatePresence>
            </ul>
          )}
        </Section>

        <Section title="Call these first" subtitle="High risk × highest monthly value" className="xl:col-span-2"
                 action={<Link to="/actions" className="text-sm font-medium text-brand-600 hover:underline dark:text-brand-400">Action Center →</Link>}>
          {top.length === 0 ? <Empty text="No high-risk customers right now." /> : (
            <ul className="space-y-2">
              {top.map((c) => (
                <li key={c.customer_id}>
                  <Link to={`/customers/${c.customer_id}`} className="flex items-center gap-3 rounded-xl border border-line p-3 transition hover:border-brand-500/40 hover:bg-surface-2">
                    <Avatar id={c.customer_id} name={c.name} size="sm" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold text-ink">{c.name}</p>
                      <p className="truncate text-xs text-muted">{c.contract} · {c.tenure} mo · ${c.monthly_charges.toFixed(0)}/mo · {c.city}</p>
                    </div>
                    <span className="text-sm font-bold text-rose-500 tabular-nums">{pct(c.probability, 0)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
          <Link to="/customers/new" className="btn-ghost mt-4 w-full"><UserPlus className="h-4 w-4" /> Add & predict a new customer</Link>
        </Section>
      </div>
    </div>
  );
}
