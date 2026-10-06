// Typed client for the ChurnPulse v2 API.

export type Band = "low" | "medium" | "high";
export type ModelKind = "profile" | "survey";
export type Category = "geographic" | "demographic" | "technographic" | "behavioural" | "psychographic";

export interface Reason {
  feature: string;
  category: Category;
  value: string | number;
  impact: number;
  direction: string;
}

export interface Action {
  action_id: string;
  title: string;
  description: string;
  probability_before: number;
  probability_after: number;
  risk_reduction: number;
  cost: number;
  expected_value: number;
  score: number;
  channel: string;
  why: string[];
}

export interface Prediction {
  churn_probability: number;
  risk_band: Band;
  will_churn: boolean;
  threshold: number;
  model: string;
  model_used: ModelKind;
  reasons: Reason[];
  actions?: Action[];
}

export interface LiveItem {
  customer_id: string;
  name: string | null;
  event_type: string;
  event_source?: string | null;
  probability: number;
  previous_probability: number | null;
  delta: number | null;
  risk_band: Band;
  model_used: ModelKind | null;
  alert: string | null;
  reasons: Reason[];
  contract: string;
  tenure: number;
  monthly_charges: number;
  city?: string | null;
  scored_at?: number;
  created_at?: string;
}

export interface TimelinePoint {
  window_end: string;
  live_events: number;
  alerts: number;
  high_risk: number;
  avg_probability: number | null;
}

export interface Stats {
  customers_scored: number;
  high_risk: number;
  medium_risk: number;
  low_risk: number;
  flagged: number;
  survey_scored: number;
  new_members: number;
  avg_probability: number | null;
  expected_revenue_at_risk: number | null;
  cltv_at_risk: number | null;
  events_last_minute: number;
  alerts_last_hour: number;
  p50_latency_ms: number | null;
  p95_latency_ms: number | null;
  timeline: TimelinePoint[];
  distribution: { bucket: number; customers: number }[];
  actions: { accepted: number; contacted: number; value_saved: number };
  thresholds: Record<ModelKind, number>;
}

export interface CustomerRow {
  customer_id: string;
  name: string;
  email: string | null;
  city: string | null;
  source: string;
  probability: number;
  previous_probability: number | null;
  risk_band: Band;
  will_churn: boolean;
  model_used: ModelKind;
  alert: string | null;
  last_event_type: string;
  monthly_charges: number;
  contract: string;
  tenure: number;
  internet: string;
  age: number;
  updated_at: string;
}

export type Profile = Record<string, string | number | boolean | null>;

export interface Persona {
  price_sensitivity?: number | null;
  brand_loyalty?: number | null;
  preferred_channel?: string | null;
  lifestyle?: string | null;
  interests?: string[];
}

export interface ActionLog {
  id: number;
  customer_id: string;
  name?: string;
  action_id: string;
  title: string;
  channel: string | null;
  probability_before: number;
  probability_after: number;
  expected_value: number;
  cost: number;
  status: "contacted" | "accepted" | "declined";
  note: string | null;
  created_at: string;
}

export interface CustomerDetail {
  customer_id: string;
  name: string;
  email: string | null;
  phone: string | null;
  city: string | null;
  source: string;
  cltv: number | null;
  persona: Persona;
  probability: number;
  previous_probability: number | null;
  risk_band: Band;
  will_churn: boolean;
  model_used: ModelKind;
  alert: string | null;
  last_event_type: string;
  monthly_charges: number;
  reasons: Reason[];
  signals: { events_10m: number; downgrades_10m: number; was_downgrade: boolean } | null;
  profile: Profile;
  dataset_label: boolean | null;
  threshold: number;
  actions: Action[];
  actions_log: ActionLog[];
  created_at: string;
  updated_at: string;
  history: { event_type: string; event_source: string | null; probability: number; risk_band: Band;
             model_used: ModelKind | null; alert: string | null; created_at: string }[];
}

export interface QueueItem {
  customer_id: string;
  name: string;
  city: string | null;
  probability: number;
  risk_band: Band;
  model_used: ModelKind;
  monthly_charges: number;
  contract: string;
  actions: Action[];
  persona: Persona;
}

export interface City { city: string; latitude: number; longitude: number; population: number; zip_code: string }

export interface Meta {
  choices: Record<string, string[]>;
  categories: Category[];
  cities: City[];
  event_labels: Record<string, string>;
  thresholds: Record<ModelKind, number>;
}

export interface CustomerInput {
  contact: { name: string; email?: string | null; phone?: string | null };
  geographic: Record<string, unknown>;
  demographic: Record<string, unknown>;
  technographic: Record<string, unknown>;
  behavioural: Record<string, unknown>;
  psychographic: Record<string, unknown>;
}

export interface ImportResult {
  rows: number;
  imported: number;
  failed: number;
  customers: { customer_id: string; name: string }[];
  errors: { row: number; errors: string[] }[];
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { headers: init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }, ...init });
  if (!res.ok) {
    let detail = await res.text();
    try {
      const body = JSON.parse(detail);
      detail = typeof body.detail === "string" ? body.detail
        : Array.isArray(body.detail) ? body.detail.map((d: { loc: string[]; msg: string }) => `${d.loc.slice(1).join(".")}: ${d.msg}`).join("; ")
        : detail;
    } catch { /* plain text */ }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

const upload = (file: File) => { const form = new FormData(); form.append("file", file); return form; };

export const api = {
  meta: () => request<Meta>("/api/meta"),
  stats: () => request<Stats>("/api/stats"),
  map: () => request<[string, number, number, number][]>("/api/map"),
  live: (limit = 30) => request<LiveItem[]>(`/api/live?limit=${limit}`),
  customers: (params: Record<string, string | number>) =>
    request<{ total: number; items: CustomerRow[] }>(`/api/customers?${new URLSearchParams(params as Record<string, string>)}`),
  customer: (id: string) => request<CustomerDetail>(`/api/customers/${encodeURIComponent(id)}`),
  create: (body: CustomerInput) => request<Prediction & { customer_id: string }>("/api/customers", { method: "POST", body: JSON.stringify(body) }),
  update: (id: string, body: CustomerInput) =>
    request<Prediction & { changed_fields: string[] }>(`/api/customers/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(body) }),
  archive: (id: string) => request<{ archived: boolean }>(`/api/customers/${encodeURIComponent(id)}`, { method: "DELETE" }),
  predict: (body: CustomerInput) => request<Prediction & { profile: Profile }>("/api/predict", { method: "POST", body: JSON.stringify(body) }),
  importCsv: (file: File) => request<ImportResult>("/api/customers/import", { method: "POST", body: upload(file) }),
  scoreCsv: async (file: File) => {
    const res = await fetch("/api/predict/batch", { method: "POST", body: upload(file) });
    if (!res.ok) throw new ApiError(res.status, await res.text());
    return res.blob();
  },
  scenario: (id: string, name: "churn_risk" | "loyalty") =>
    request<{ events_sent: number }>(`/api/customers/${encodeURIComponent(id)}/scenario/${name}`, { method: "POST" }),
  queue: (limit = 40) => request<{ total: number; potential_value: number; items: QueueItem[] }>(`/api/actions?limit=${limit}`),
  recordAction: (body: { customer_id: string; action_id: string; status: string; note?: string }) =>
    request<ActionLog>("/api/actions", { method: "POST", body: JSON.stringify(body) }),
  actionLog: () => request<ActionLog[]>("/api/actions/log"),
  model: () => request<ModelCard>("/api/model"),
};

export interface ModelCardEntry {
  model_name: string;
  features: number;
  cv_roc_auc: number;
  threshold: number;
  test_metrics: {
    roc_auc: number; pr_auc: number; brier: number; threshold: number; accuracy: number; precision: number;
    recall: number; f1: number; "accuracy_at_0.5": number; retention_value: number; retention_value_contact_everyone: number;
    confusion: { tn: number; fp: number; fn: number; tp: number };
  };
  model_comparison: { model: string; roc_auc: number; roc_auc_std: number; pr_auc: number; accuracy: number; recall: number; f1: number }[];
  top_features: { feature: string; mean_abs_shap: number; category: Category }[];
  importance_by_category: Record<Category, number>;
}

export interface ModelCard {
  trained_at: string;
  dataset: string;
  train_rows: number;
  test_rows: number;
  churn_rate: number;
  excluded_columns: string[];
  business_assumptions: { offer_months_of_bill: number; offer_success_rate: number; months_of_value: number };
  models: Record<ModelKind, ModelCardEntry>;
}
