import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, DollarSign, Info, ListChecks, Target } from "lucide-react";
import { api, type ActionLog, type QueueItem } from "../lib/api";
import { money, num, pct, timeAgo } from "../lib/format";
import { ActionCard } from "./Customer360";
import { Avatar, Empty, ErrorBox, Kpi, ModelChip, PageHeader, RiskBadge, Section, Skeleton, Tabs } from "../components/ui";

export default function ActionCenter() {
  const [queue, setQueue] = useState<{ total: number; potential_value: number; items: QueueItem[] } | null>(null);
  const [log, setLog] = useState<ActionLog[]>([]);
  const [tab, setTab] = useState<"queue" | "log">("queue");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    Promise.all([api.queue(30), api.actionLog()])
      .then(([q, l]) => { setQueue(q); setLog(l); setError(null); })
      .catch((e) => setError(String(e.message)));
  }, []);
  useEffect(() => { load(); }, [load]);

  const accepted = log.filter((l) => l.status === "accepted");
  return (
    <div className="space-y-6">
      <PageHeader title="Action Center" subtitle="Who to contact, what to offer, and what it's worth — ranked by expected value." />

      <div className="grid gap-4 sm:grid-cols-3">
        <Kpi label="Customers to contact" value={queue ? num(queue.total) : "…"} icon={<Target className="h-5 w-5" />} tone="rose"
             hint="above the decision threshold, with a worthwhile action" />
        <Kpi label="Potential value" value={queue ? money(queue.potential_value, true) : "…"} icon={<DollarSign className="h-5 w-5" />} tone="amber" delay={0.05}
             hint="if every best action is accepted" />
        <Kpi label="Accepted so far" value={num(accepted.length)} icon={<CheckCircle2 className="h-5 w-5" />} tone="brand" delay={0.1}
             hint={`${money(accepted.reduce((s, l) => s + l.expected_value, 0))} expected value saved`} />
      </div>

      <div className="flex items-start gap-3 rounded-xl border border-line bg-surface-2/60 p-4 text-sm text-ink-2">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-brand-500" />
        <p>Each action is tested by re-scoring the customer as if they accepted it. Estimates are model-based — logging the real
          outcome (accepted / declined) builds the evidence to measure what truly works. Accepting applies the change through Kafka,
          so the customer's live risk updates within a second.</p>
      </div>

      <Tabs tabs={[{ id: "queue", label: "Priority queue", icon: <Target className="h-3.5 w-3.5" /> },
                   { id: "log", label: "Outreach log", icon: <ListChecks className="h-3.5 w-3.5" /> }]}
            active={tab} onChange={setTab} />

      {error && <ErrorBox error={error} />}
      {tab === "queue" ? (
        !queue ? <div className="grid gap-4 lg:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-64" />)}</div>
          : queue.items.length === 0 ? <Section><Empty text="No customers need action right now." /></Section> : (
          <div className="grid gap-4 lg:grid-cols-2">
            {queue.items.map((q, i) => (
              <Section key={q.customer_id}>
                <div className="mb-4 flex items-center gap-3">
                  <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-surface-2 text-xs font-bold text-muted">{i + 1}</span>
                  <Avatar id={q.customer_id} name={q.name} size="sm" />
                  <div className="min-w-0 flex-1">
                    <Link to={`/customers/${q.customer_id}`} className="font-semibold text-ink hover:text-brand-600">{q.name}</Link>
                    <p className="truncate text-xs text-muted">{q.contract} · ${q.monthly_charges.toFixed(0)}/mo · {q.city}
                      {q.persona?.lifestyle && <> · {q.persona.lifestyle}</>}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-lg font-bold text-rose-500 tabular-nums">{pct(q.probability, 0)}</p>
                    <div className="flex items-center gap-1"><RiskBadge band={q.risk_band} /><ModelChip kind={q.model_used} /></div>
                  </div>
                </div>
                <ActionCard action={q.actions[0]} customerId={q.customer_id} onDone={() => setTimeout(load, 800)} />
                {q.actions.length > 1 && (
                  <p className="mt-3 text-xs text-muted">Alternatives: {q.actions.slice(1).map((a) => `${a.title} (+${money(a.expected_value)})`).join(" · ")}</p>
                )}
              </Section>
            ))}
          </div>
        )
      ) : (
        <Section padded={false}>
          {log.length === 0 ? <Empty text="No outreach logged yet." /> : (
            <table className="w-full text-sm">
              <thead className="border-b border-line bg-surface-2/60 text-left"><tr className="label">
                <th className="px-5 py-3">Customer</th><th className="px-3 py-3">Action</th><th className="px-3 py-3">Channel</th>
                <th className="px-3 py-3">Risk</th><th className="px-3 py-3 text-right">Exp. value</th><th className="px-3 py-3">Status</th><th className="px-5 py-3">When</th>
              </tr></thead>
              <tbody className="divide-y divide-line">
                {log.map((l) => (
                  <tr key={l.id}>
                    <td className="px-5 py-3"><Link to={`/customers/${l.customer_id}`} className="font-medium text-ink hover:text-brand-600">{l.name}</Link></td>
                    <td className="px-3 py-3 text-ink-2">{l.title}</td>
                    <td className="px-3 py-3 text-muted">{l.channel}</td>
                    <td className="px-3 py-3 tabular-nums text-ink-2">{pct(l.probability_before, 0)} → <b className="text-emerald-500">{pct(l.probability_after, 0)}</b></td>
                    <td className="px-3 py-3 text-right tabular-nums text-ink-2">{money(l.expected_value)}</td>
                    <td className="px-3 py-3"><span className={`chip ${l.status === "accepted" ? "!border-emerald-500/40 !text-emerald-600" : l.status === "declined" ? "!border-rose-500/40 !text-rose-500" : ""}`}>{l.status}</span></td>
                    <td className="px-5 py-3 text-xs text-muted">{timeAgo(l.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Section>
      )}
    </div>
  );
}
