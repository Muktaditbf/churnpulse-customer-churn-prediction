import type { ReactNode } from "react";
import { ArrowDownRight, ArrowUpRight, Inbox, Minus, ShieldCheck, Sparkles } from "lucide-react";
import { motion } from "motion/react";
import type { Band, Category, ModelKind, Reason } from "../lib/api";
import { avatarColor, BAND_COLOR, BAND_STYLE, CATEGORY, featureLabel, formatValue, initials, pct } from "../lib/format";

export function RiskBadge({ band }: { band: Band }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize ring-1 ${BAND_STYLE[band]}`}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: BAND_COLOR[band] }} />
      {band}
    </span>
  );
}

export function ModelChip({ kind }: { kind: ModelKind | null | undefined }) {
  if (!kind) return null;
  const survey = kind === "survey";
  return (
    <span title={survey ? "Scored by the survey model (satisfaction known)" : "Scored by the profile model"}
          className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
            survey ? "bg-pink-500/10 text-pink-600 dark:text-pink-400" : "bg-sky-500/10 text-sky-600 dark:text-sky-400"}`}>
      {survey ? <Sparkles className="h-3 w-3" /> : <ShieldCheck className="h-3 w-3" />}
      {survey ? "Survey" : "Profile"}
    </span>
  );
}

export function Delta({ value }: { value: number | null | undefined }) {
  if (value == null || Math.abs(value) < 0.005) return <Minus className="h-4 w-4 text-muted/50" />;
  const up = value > 0;
  const Icon = up ? ArrowUpRight : ArrowDownRight;
  return (
    <span className={`inline-flex items-center text-xs font-semibold tabular-nums ${up ? "text-rose-500" : "text-emerald-500"}`}>
      <Icon className="h-4 w-4" />
      {(Math.abs(value) * 100).toFixed(1)}
    </span>
  );
}

export function Avatar({ id, name, size = "md" }: { id: string; name?: string | null; size?: "sm" | "md" | "lg" }) {
  const sizes = { sm: "h-8 w-8 text-xs", md: "h-10 w-10 text-sm", lg: "h-16 w-16 text-xl" };
  return (
    <div className={`flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br font-semibold text-white shadow-sm ${avatarColor(id)} ${sizes[size]}`}>
      {initials(name)}
    </div>
  );
}

export function Kpi({ label, value, hint, icon, tone = "brand", delay = 0 }: {
  label: string; value: ReactNode; hint?: ReactNode; icon: ReactNode; tone?: "brand" | "rose" | "amber" | "violet" | "sky"; delay?: number;
}) {
  const tones = {
    brand: "from-brand-500/20 to-brand-500/5 text-brand-600 dark:text-brand-400",
    rose: "from-rose-500/20 to-rose-500/5 text-rose-600 dark:text-rose-400",
    amber: "from-amber-500/20 to-amber-500/5 text-amber-600 dark:text-amber-400",
    violet: "from-violet-500/20 to-violet-500/5 text-violet-600 dark:text-violet-400",
    sky: "from-sky-500/20 to-sky-500/5 text-sky-600 dark:text-sky-400",
  };
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay, duration: 0.35 }}
                className="card relative overflow-hidden p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="label">{label}</p>
          <p className="mt-2 text-[28px] font-bold leading-none tracking-tight text-ink tabular-nums">{value}</p>
          {hint && <p className="mt-2 text-xs text-muted">{hint}</p>}
        </div>
        <div className={`rounded-xl bg-gradient-to-br p-2.5 ${tones[tone]}`}>{icon}</div>
      </div>
    </motion.div>
  );
}

export function Section({ title, subtitle, action, children, className = "", padded = true }: {
  title?: ReactNode; subtitle?: ReactNode; action?: ReactNode; children: ReactNode; className?: string; padded?: boolean;
}) {
  return (
    <section className={`card ${padded ? "p-5" : ""} ${className}`}>
      {(title || action) && (
        <div className={`flex items-start justify-between gap-4 ${padded ? "mb-4" : "px-5 pt-5 pb-3"}`}>
          <div>
            {title && <h2 className="font-semibold tracking-tight text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-ink sm:text-[28px]">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

/** Half-circle gauge of the churn probability with the decision threshold marked. */
export function Gauge({ probability, band, threshold, size = 220 }: { probability: number; band: Band; threshold: number; size?: number }) {
  const r = 80, c = Math.PI * r;
  const angle = Math.PI * (1 - threshold);
  const tx = 100 + r * Math.cos(angle), ty = 100 - r * Math.sin(angle);
  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 200 118" style={{ width: size }}>
        <defs>
          <linearGradient id={`g-${band}`} x1="0" x2="1">
            <stop offset="0%" stopColor={BAND_COLOR[band]} stopOpacity={0.55} />
            <stop offset="100%" stopColor={BAND_COLOR[band]} />
          </linearGradient>
        </defs>
        <path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke="var(--line)" strokeWidth="14" strokeLinecap="round" />
        <path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke={`url(#g-${band})`} strokeWidth="14" strokeLinecap="round"
              strokeDasharray={`${c * probability} ${c}`} style={{ transition: "stroke-dasharray .7s cubic-bezier(.2,.8,.2,1)" }} />
        <circle cx={tx} cy={ty} r="5" fill="var(--surface)" stroke="var(--ink)" strokeWidth="2.5" />
        <text x="100" y="86" textAnchor="middle" fill="var(--ink)" style={{ fontSize: 32, fontWeight: 800 }}>{pct(probability, 0)}</text>
        <text x="100" y="106" textAnchor="middle" fill="var(--muted)" style={{ fontSize: 10 }}>chance of leaving</text>
      </svg>
      <p className="text-[11px] text-muted">○ marker = decision threshold ({pct(threshold, 0)})</p>
    </div>
  );
}

/** SHAP contributions with a persona-category marker; red pushes towards churn. */
export function ReasonBars({ reasons, compact = false }: { reasons: Reason[]; compact?: boolean }) {
  if (!reasons?.length) return <Empty text="No explanation yet." />;
  const max = Math.max(...reasons.map((r) => Math.abs(r.impact)), 0.01);
  return (
    <ul className={compact ? "space-y-2.5" : "space-y-3.5"}>
      {reasons.map((r, i) => {
        const cat = CATEGORY[r.category];
        const Icon = cat?.icon;
        return (
          <li key={r.feature}>
            <div className="mb-1.5 flex items-center justify-between gap-3 text-sm">
              <span className="flex min-w-0 items-center gap-2">
                {Icon && <Icon className={`h-3.5 w-3.5 shrink-0 ${cat.text}`} />}
                <span className="truncate font-medium text-ink-2">{featureLabel(r.feature)}</span>
                <span className="truncate text-muted">= {formatValue(r.value, r.feature)}</span>
              </span>
              <span className={`shrink-0 text-xs font-semibold ${r.impact > 0 ? "text-rose-500" : "text-emerald-500"}`}>
                {r.impact > 0 ? "▲ raises" : "▼ lowers"}
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-surface-2">
              <motion.div initial={{ width: 0 }} animate={{ width: `${(Math.abs(r.impact) / max) * 100}%` }}
                          transition={{ duration: 0.6, delay: i * 0.05 }}
                          className={`h-2 rounded-full ${r.impact > 0 ? "bg-gradient-to-r from-rose-400 to-rose-500" : "bg-gradient-to-r from-emerald-400 to-emerald-500"}`} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function CategoryBadge({ category }: { category: Category }) {
  const c = CATEGORY[category];
  const Icon = c.icon;
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-ink-2">
      <span className="flex h-6 w-6 items-center justify-center rounded-lg" style={{ background: `${c.color}22` }}>
        <Icon className="h-3.5 w-3.5" style={{ color: c.color }} />
      </span>
      {c.label}
    </span>
  );
}

export function RiskBar({ value, band }: { value: number; band: Band }) {
  return (
    <div className="flex items-center gap-2.5">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-surface-2">
        <div className="h-1.5 rounded-full" style={{ width: `${value * 100}%`, background: BAND_COLOR[band] }} />
      </div>
      <span className="w-10 text-right text-sm font-semibold tabular-nums text-ink">{pct(value, 0)}</span>
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} />;
}

export function Empty({ text, icon }: { text: string; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center text-sm text-muted">
      {icon ?? <Inbox className="h-6 w-6 opacity-60" />}
      {text}
    </div>
  );
}

export function ErrorBox({ error }: { error: string }) {
  return <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-600 dark:text-rose-400">{error}</div>;
}

export function Tabs<T extends string>({ tabs, active, onChange }: {
  tabs: { id: T; label: string; icon?: ReactNode }[]; active: T; onChange: (t: T) => void;
}) {
  return (
    <div className="flex gap-1 overflow-x-auto rounded-xl border border-line bg-surface-2 p-1">
      {tabs.map((t) => (
        <button key={t.id} type="button" onClick={() => onChange(t.id)}
                className={`relative flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                  active === t.id ? "text-ink" : "text-muted hover:text-ink-2"}`}>
          {active === t.id && (
            <motion.span layoutId="tab-pill" className="absolute inset-0 rounded-lg bg-surface shadow-sm"
                         transition={{ type: "spring", bounce: 0.2, duration: 0.4 }} />
          )}
          <span className="relative flex items-center gap-1.5">{t.icon}{t.label}</span>
        </button>
      ))}
    </div>
  );
}

export function Stat({ label, value, tone }: { label: string; value: ReactNode; tone?: "good" | "bad" }) {
  return (
    <div className="rounded-xl border border-line bg-surface-2 p-3">
      <p className="label">{label}</p>
      <p className={`mt-1 font-semibold tabular-nums ${tone === "good" ? "text-emerald-500" : tone === "bad" ? "text-rose-500" : "text-ink"}`}>{value}</p>
    </div>
  );
}
