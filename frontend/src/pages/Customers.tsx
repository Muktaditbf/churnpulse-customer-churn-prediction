import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Search, Upload, UserPlus } from "lucide-react";
import { api, type CustomerRow } from "../lib/api";
import { EVENT_LABELS, num, timeAgo } from "../lib/format";
import { Avatar, Delta, Empty, ErrorBox, ModelChip, PageHeader, RiskBadge, RiskBar, Skeleton } from "../components/ui";

const PAGE = 20;

export default function Customers() {
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get("q") ?? "");
  const [band, setBand] = useState("");
  const [source, setSource] = useState("");
  const [model, setModel] = useState("");
  const [sort, setSort] = useState("risk");
  const [page, setPage] = useState(0);
  const [data, setData] = useState<{ total: number; items: CustomerRow[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => { setSearch(params.get("q") ?? ""); setPage(0); }, [params]);

  useEffect(() => {
    const q: Record<string, string | number> = { sort, limit: PAGE, offset: page * PAGE };
    if (band) q.band = band;
    if (source) q.source = source;
    if (model) q.model = model;
    if (search.trim()) q.search = search.trim();
    const t = setTimeout(() => api.customers(q).then((d) => { setData(d); setError(null); }).catch((e) => setError(String(e.message))), 200);
    return () => clearTimeout(t);
  }, [band, source, model, search, sort, page]);

  const reset = () => setPage(0);

  return (
    <div className="space-y-6">
      <PageHeader title="Customers" subtitle={data ? `${num(data.total)} customers, each with a live churn score` : "Loading…"}
        actions={<>
          <Link to="/import" className="btn-ghost"><Upload className="h-4 w-4" /> Import CSV</Link>
          <Link to="/customers/new" className="btn-primary"><UserPlus className="h-4 w-4" /> Add customer</Link>
        </>} />

      <div className="card flex flex-wrap items-center gap-3 p-3">
        <div className="relative min-w-[16rem] flex-1">
          <Search className="absolute left-3.5 top-3 h-4 w-4 text-muted" />
          <input className="input pl-10" placeholder="Name, email, city or ID" value={search}
                 onChange={(e) => { setSearch(e.target.value); reset(); if (params.get("q")) setParams({}); }} />
        </div>
        {[
          { value: band, set: setBand, options: [["", "All risk levels"], ["high", "High risk"], ["medium", "Medium risk"], ["low", "Low risk"]] },
          { value: source, set: setSource, options: [["", "All customers"], ["new", "New members"], ["dataset", "Original dataset"]] },
          { value: model, set: setModel, options: [["", "Both models"], ["survey", "Survey model"], ["profile", "Profile model"]] },
          { value: sort, set: setSort, options: [["risk", "Highest risk"], ["value", "Most revenue at risk"], ["change", "Biggest change"], ["recent", "Recently updated"], ["name", "Name A–Z"]] },
        ].map((f, i) => (
          <select key={i} className="input w-auto" value={f.value} onChange={(e) => { f.set(e.target.value); reset(); }}>
            {f.options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        ))}
      </div>

      {error && <ErrorBox error={error} />}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-line bg-surface-2/60 text-left">
              <tr className="label">
                <th className="px-5 py-3 font-semibold">Customer</th>
                <th className="px-3 py-3 font-semibold">Location</th>
                <th className="px-3 py-3 font-semibold">Plan</th>
                <th className="px-3 py-3 text-right font-semibold">Monthly</th>
                <th className="px-3 py-3 font-semibold">Last event</th>
                <th className="px-3 py-3 font-semibold">Change</th>
                <th className="px-3 py-3 font-semibold">Churn risk</th>
                <th className="px-5 py-3 font-semibold">Level</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {!data ? Array.from({ length: 8 }, (_, i) => (
                <tr key={i}><td colSpan={8} className="px-5 py-3"><Skeleton className="h-9" /></td></tr>
              )) : data.items.map((c) => (
                <tr key={c.customer_id} onClick={() => navigate(`/customers/${c.customer_id}`)}
                    className="cursor-pointer transition hover:bg-surface-2/70">
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-3">
                      <Avatar id={c.customer_id} name={c.name} size="sm" />
                      <div className="min-w-0">
                        <p className="flex items-center gap-2 font-semibold text-ink">
                          {c.name}
                          {c.source !== "dataset" && <span className="rounded bg-brand-500/15 px-1.5 text-[10px] font-bold uppercase text-brand-700 dark:text-brand-400">new</span>}
                          {c.alert && <span className="rounded bg-rose-500/15 px-1.5 text-[10px] font-bold uppercase text-rose-600 dark:text-rose-400">alert</span>}
                        </p>
                        <p className="truncate text-xs text-muted">{c.email ?? c.customer_id}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-3 text-ink-2">{c.city ?? "—"}</td>
                  <td className="px-3 py-3">
                    <p className="text-ink-2">{c.contract}</p>
                    <p className="text-xs text-muted">{c.internet} · {c.tenure} mo</p>
                  </td>
                  <td className="px-3 py-3 text-right tabular-nums text-ink-2">${c.monthly_charges.toFixed(2)}</td>
                  <td className="px-3 py-3 text-ink-2">
                    {EVENT_LABELS[c.last_event_type] ?? c.last_event_type}
                    <span className="block text-xs text-muted">{timeAgo(c.updated_at)}</span>
                  </td>
                  <td className="px-3 py-3"><Delta value={c.previous_probability == null ? null : c.probability - c.previous_probability} /></td>
                  <td className="px-3 py-3"><div className="flex items-center gap-2"><RiskBar value={c.probability} band={c.risk_band} /><ModelChip kind={c.model_used} /></div></td>
                  <td className="px-5 py-3"><RiskBadge band={c.risk_band} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          {data && data.items.length === 0 && <Empty text="No customers match these filters." />}
        </div>
        {data && data.total > PAGE && (
          <div className="flex items-center justify-between border-t border-line px-5 py-3 text-sm">
            <span className="text-muted">Page {page + 1} of {Math.ceil(data.total / PAGE)}</span>
            <div className="flex gap-2">
              <button className="btn-ghost !py-1.5" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
              <button className="btn-ghost !py-1.5" disabled={(page + 1) * PAGE >= data.total} onClick={() => setPage(page + 1)}>Next</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
