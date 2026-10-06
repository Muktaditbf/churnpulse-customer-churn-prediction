import { Activity, Brain, Cpu, MapPin, Users, type LucideIcon } from "lucide-react";
import type { Band, Category, ModelKind } from "./api";

export const pct = (v: number | null | undefined, digits = 1) => (v == null ? "–" : `${(v * 100).toFixed(digits)}%`);

export const money = (v: number | null | undefined, compact = false) =>
  v == null ? "–"
    : v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0,
                                   notation: compact && Math.abs(v) >= 10_000 ? "compact" : "standard" });

export const num = (v: number | null | undefined) => (v == null ? "–" : v.toLocaleString("en-US"));

export const BAND_COLOR: Record<Band, string> = { low: "#10b981", medium: "#f59e0b", high: "#f43f5e" };
export const BAND_STYLE: Record<Band, string> = {
  low: "bg-emerald-500/10 text-emerald-600 ring-emerald-500/25 dark:text-emerald-400",
  medium: "bg-amber-500/10 text-amber-600 ring-amber-500/25 dark:text-amber-400",
  high: "bg-rose-500/10 text-rose-600 ring-rose-500/25 dark:text-rose-400",
};

export const MODEL_LABEL: Record<ModelKind, string> = { profile: "Profile model", survey: "Survey model" };

export const CATEGORY: Record<Category, { label: string; icon: LucideIcon; color: string; text: string; hint: string }> = {
  geographic: { label: "Geographic", icon: MapPin, color: "#38bdf8", text: "text-sky-500",
                hint: "Where the customer lives" },
  demographic: { label: "Demographic", icon: Users, color: "#a78bfa", text: "text-violet-500",
                 hint: "Who the customer is" },
  technographic: { label: "Technographic", icon: Cpu, color: "#22d3ee", text: "text-cyan-500",
                   hint: "Technology and services they use" },
  behavioural: { label: "Behavioural", icon: Activity, color: "#fbbf24", text: "text-amber-500",
                 hint: "How they buy, pay and use" },
  psychographic: { label: "Psychographic", icon: Brain, color: "#f472b6", text: "text-pink-500",
                   hint: "Attitudes, loyalty and preferences" },
};

const FEATURE_LABELS: Record<string, string> = {
  latitude: "Latitude", longitude: "Longitude", log_population: "Area population", population: "Area population",
  city: "City", zip_code: "Zip code",
  age: "Age", gender: "Gender", married: "Married", num_dependents: "Dependents", under_30: "Under 30",
  senior: "Senior (65+)",
  internet_type: "Internet type", avg_monthly_gb: "Monthly data (GB)", unlimited_data: "Unlimited data",
  phone_service: "Phone service", multiple_lines: "Multiple lines", online_security: "Online security",
  online_backup: "Online backup", device_protection: "Device protection", premium_tech_support: "Premium tech support",
  streaming_tv: "Streaming TV", streaming_movies: "Streaming movies", streaming_music: "Streaming music",
  num_addons: "Add-on services", num_protection: "Protection services", gb_per_dollar: "Data per dollar",
  tenure_months: "Tenure (months)", tenure_group: "Tenure group", contract: "Contract",
  contract_months: "Contract length", payment_method: "Payment method", auto_pay: "Automatic payment",
  paperless_billing: "Paperless billing", offer: "Offer", monthly_charge: "Monthly bill",
  total_charges: "Total billed", avg_monthly_charge: "Average past bill", charge_increase_ratio: "Price vs. past average",
  total_refunds: "Refunds", had_refund: "Had a refund", extra_data_share: "Extra data charges",
  avg_long_distance: "Long-distance spend", total_long_distance_charges: "Total long distance",
  total_extra_data_charges: "Total extra data", referrals: "Referrals", referred_a_friend: "Referred a friend",
  satisfaction_score: "Satisfaction score",
  price_sensitivity: "Price sensitivity", brand_loyalty: "Brand loyalty", preferred_channel: "Preferred channel",
  lifestyle: "Lifestyle",
};
export const featureLabel = (f: string) => FEATURE_LABELS[f] ?? f.replace(/_/g, " ");

const YES_NO = new Set(["married", "phone_service", "multiple_lines", "unlimited_data", "online_security",
  "online_backup", "device_protection", "premium_tech_support", "streaming_tv", "streaming_movies", "streaming_music",
  "paperless_billing", "under_30", "senior", "auto_pay", "had_refund", "referred_a_friend"]);
const MONEY = new Set(["monthly_charge", "total_charges", "avg_monthly_charge", "total_refunds", "avg_long_distance",
  "total_long_distance_charges", "total_extra_data_charges"]);

/** A profile value as a person would read it, e.g. "Yes", "$75.00", "24 months". */
export const formatValue = (v: unknown, feature?: string): string => {
  if (v == null || v === "") return "—";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (feature && YES_NO.has(feature)) return Number(v) ? "Yes" : "No";
  const n = typeof v === "number" ? v : Number.NaN;
  if (!Number.isNaN(n) && feature) {
    if (MONEY.has(feature)) return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
    if (feature === "contract_months") return `${n} month${n === 1 ? "" : "s"}`;
    if (feature === "tenure_months") return `${n} month${n === 1 ? "" : "s"}`;
    if (feature === "avg_monthly_gb") return `${n} GB`;
    if (feature === "charge_increase_ratio") return `${n.toFixed(2)}×`;
    if (feature === "extra_data_share") return `${(n * 100).toFixed(1)}%`;
    if (feature === "log_population") return Math.round(Math.expm1(n)).toLocaleString();
    if (feature === "population") return n.toLocaleString();
    if (feature === "satisfaction_score") return `${n} / 5`;
  }
  return String(v);
};

export const EVENT_LABELS: Record<string, string> = {
  snapshot: "Profile loaded", billing_cycle: "Monthly billing", contract_change: "Contract changed",
  service_change: "Service changed", internet_change: "Internet changed", price_change: "Price changed",
  payment_change: "Payment method changed", offer_accepted: "Offer accepted", usage_change: "Data usage changed",
  referral: "Referred a friend", survey: "Satisfaction survey", profile_update: "Profile edited",
};

export const timeAgo = (iso?: string | number) => {
  if (iso == null) return "";
  const t = typeof iso === "number" ? iso : Date.parse(iso);
  const s = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};

export const initials = (name?: string | null) =>
  (name ?? "?").split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join("");

const AVATAR_COLORS = ["from-teal-400 to-emerald-500", "from-sky-400 to-indigo-500", "from-fuchsia-400 to-pink-500",
  "from-amber-400 to-orange-500", "from-violet-400 to-purple-500", "from-cyan-400 to-blue-500"];
export const avatarColor = (id: string) =>
  AVATAR_COLORS[[...id].reduce((a, c) => a + c.charCodeAt(0), 0) % AVATAR_COLORS.length];
