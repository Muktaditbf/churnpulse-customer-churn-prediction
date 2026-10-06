import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Controller, useForm, type Control, type FieldPath } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ArrowLeft, ArrowRight, Check, Contact as ContactIcon, Loader2, Save, Wand2 } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { toast } from "sonner";
import { api, type CustomerInput, type Meta, type Prediction } from "../lib/api";
import { CATEGORY, MODEL_LABEL } from "../lib/format";
import { ActionCard } from "./Customer360";
import { ErrorBox, Gauge, ModelChip, PageHeader, ReasonBars, Section, Skeleton } from "../components/ui";

// ------------------------------------------------------------------ schema (mirrors the API)
const schema = z.object({
  contact: z.object({
    name: z.string().trim().min(2, "Enter the customer's full name"),
    email: z.string().trim().email("Enter a valid email").or(z.literal("")).optional(),
    phone: z.string().trim().max(30).optional(),
  }),
  geographic: z.object({
    city: z.string().trim().min(1, "Choose a city"),
    zip_code: z.string().optional(),
    latitude: z.coerce.number().min(-90).max(90),
    longitude: z.coerce.number().min(-180).max(180),
    population: z.coerce.number().int().min(0),
  }),
  demographic: z.object({
    gender: z.enum(["Female", "Male"]),
    age: z.coerce.number().int().min(18, "18 or older").max(100),
    married: z.boolean(),
    num_dependents: z.coerce.number().int().min(0).max(10),
  }),
  technographic: z.object({
    internet_type: z.enum(["Fiber Optic", "Cable", "DSL", "None"]),
    avg_monthly_gb: z.coerce.number().int().min(0).max(500),
    unlimited_data: z.boolean(), phone_service: z.boolean(), multiple_lines: z.boolean(),
    online_security: z.boolean(), online_backup: z.boolean(), device_protection: z.boolean(),
    premium_tech_support: z.boolean(), streaming_tv: z.boolean(), streaming_movies: z.boolean(), streaming_music: z.boolean(),
  }),
  behavioural: z.object({
    tenure_months: z.coerce.number().int().min(0).max(120),
    contract: z.enum(["Month-to-Month", "One Year", "Two Year"]),
    payment_method: z.enum(["Bank Withdrawal", "Credit Card", "Mailed Check"]),
    paperless_billing: z.boolean(),
    offer: z.enum(["None", "Offer A", "Offer B", "Offer C", "Offer D", "Offer E"]),
    referrals: z.coerce.number().int().min(0).max(20),
    monthly_charge: z.coerce.number().positive().max(500),
    avg_long_distance: z.coerce.number().min(0).max(200),
  }),
  psychographic: z.object({
    satisfaction_score: z.number().int().min(1).max(5).nullable(),
    price_sensitivity: z.number().int().min(1).max(5).nullable(),
    brand_loyalty: z.number().int().min(1).max(5).nullable(),
    preferred_channel: z.string().nullable(),
    lifestyle: z.string().nullable(),
    interests: z.array(z.string()),
  }),
});
type FormValues = z.infer<typeof schema>;

const DEFAULTS: FormValues = {
  contact: { name: "", email: "", phone: "" },
  geographic: { city: "Los Angeles", zip_code: "", latitude: 34.05, longitude: -118.25, population: 30000 },
  demographic: { gender: "Female", age: 35, married: false, num_dependents: 0 },
  technographic: { internet_type: "Fiber Optic", avg_monthly_gb: 20, unlimited_data: true, phone_service: true,
    multiple_lines: false, online_security: false, online_backup: false, device_protection: false,
    premium_tech_support: false, streaming_tv: false, streaming_movies: false, streaming_music: false },
  behavioural: { tenure_months: 3, contract: "Month-to-Month", payment_method: "Bank Withdrawal", paperless_billing: true,
    offer: "None", referrals: 0, monthly_charge: 75, avg_long_distance: 10 },
  psychographic: { satisfaction_score: null, price_sensitivity: null, brand_loyalty: null, preferred_channel: null,
    lifestyle: null, interests: [] },
};

const STEPS = [
  { id: "contact", label: "Contact", icon: ContactIcon, hint: "Who they are — shown in the app, never used to predict" },
  { id: "geographic", ...CATEGORY.geographic },
  { id: "demographic", ...CATEGORY.demographic },
  { id: "technographic", ...CATEGORY.technographic },
  { id: "behavioural", ...CATEGORY.behavioural },
  { id: "psychographic", ...CATEGORY.psychographic },
] as const;

const INTERESTS = ["Sports", "Movies", "Music", "Gaming", "Travel", "Tech", "News", "Cooking", "Fitness", "Education"];

// ------------------------------------------------------------------ small field components
function Field({ label, error, children, hint }: { label: string; error?: string; children: React.ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      <div className="mt-1.5">{children}</div>
      {hint && !error && <span className="mt-1 block text-xs text-muted">{hint}</span>}
      {error && <span className="mt-1 block text-xs font-medium text-rose-500">{error}</span>}
    </label>
  );
}

function Toggle<N extends FieldPath<FormValues>>({ control, name, label, disabled }: { control: Control<FormValues>; name: N; label: string; disabled?: boolean }) {
  return (
    <Controller control={control} name={name} render={({ field }) => (
      <button type="button" disabled={disabled} onClick={() => field.onChange(!field.value)}
              className={`flex items-center justify-between gap-3 rounded-xl border px-3.5 py-2.5 text-left text-sm transition disabled:opacity-40 ${
                field.value ? "border-brand-500/50 bg-brand-500/10 text-ink" : "border-line bg-surface-2 text-ink-2"}`}>
        {label}
        <span className={`relative h-5 w-9 shrink-0 rounded-full transition ${field.value ? "bg-brand-500" : "bg-line"}`}>
          <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition ${field.value ? "left-[18px]" : "left-0.5"}`} />
        </span>
      </button>
    )} />
  );
}

function Segmented<N extends FieldPath<FormValues>>({ control, name, options }: { control: Control<FormValues>; name: N; options: string[] }) {
  return (
    <Controller control={control} name={name} render={({ field }) => (
      <div className="flex flex-wrap gap-1.5">
        {options.map((o) => (
          <button key={o} type="button" onClick={() => field.onChange(o)}
                  className={`rounded-lg border px-3 py-2 text-sm font-medium transition ${
                    field.value === o ? "border-brand-500 bg-brand-500/10 text-brand-700 dark:text-brand-400" : "border-line bg-surface-2 text-ink-2 hover:border-muted/40"}`}>
            {o}
          </button>
        ))}
      </div>
    )} />
  );
}

function Scale<N extends FieldPath<FormValues>>({ control, name, low, high, allowNone, noneLabel = "Unknown" }: {
  control: Control<FormValues>; name: N; low: string; high: string; allowNone?: boolean; noneLabel?: string;
}) {
  return (
    <Controller control={control} name={name} render={({ field }) => (
      <div>
        <div className="flex gap-1.5">
          {allowNone && (
            <button type="button" onClick={() => field.onChange(null)}
                    className={`rounded-lg border px-3 py-2 text-xs font-medium ${field.value == null ? "border-brand-500 bg-brand-500/10 text-brand-700 dark:text-brand-400" : "border-line bg-surface-2 text-muted"}`}>
              {noneLabel}
            </button>
          )}
          {[1, 2, 3, 4, 5].map((n) => (
            <button key={n} type="button" onClick={() => field.onChange(n)}
                    className={`h-10 flex-1 rounded-lg border text-sm font-semibold transition ${
                      field.value === n ? "border-brand-500 bg-brand-500 text-white" : "border-line bg-surface-2 text-ink-2 hover:border-muted/40"}`}>
              {n}
            </button>
          ))}
        </div>
        <div className="mt-1 flex justify-between text-[11px] text-muted"><span>{low}</span><span>{high}</span></div>
      </div>
    )} />
  );
}

// ------------------------------------------------------------------ page
export default function CustomerForm() {
  const { id } = useParams();
  const editing = Boolean(id);
  const navigate = useNavigate();
  const [meta, setMeta] = useState<Meta | null>(null);
  const [step, setStep] = useState(0);
  const [preview, setPreview] = useState<Prediction | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [loading, setLoading] = useState(editing);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { control, register, handleSubmit, watch, setValue, reset, trigger, formState: { errors } } =
    useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: DEFAULTS, mode: "onTouched" });

  useEffect(() => { api.meta().then(setMeta).catch((e) => setError(String(e.message))); }, []);

  // Edit mode: load the customer into the form.
  useEffect(() => {
    if (!id) return;
    api.customer(id).then((c) => {
      const p = c.profile as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
      const pick = (keys: string[]): any => Object.fromEntries(keys.map((k) => [k, p[k]]));
      reset({
        contact: { name: c.name, email: c.email ?? "", phone: c.phone ?? "" },
        geographic: { ...pick(["city", "zip_code", "latitude", "longitude", "population"]) } as FormValues["geographic"],
        demographic: pick(["gender", "age", "married", "num_dependents"]) as FormValues["demographic"],
        technographic: pick(Object.keys(DEFAULTS.technographic)) as FormValues["technographic"],
        behavioural: pick(Object.keys(DEFAULTS.behavioural)) as FormValues["behavioural"],
        psychographic: {
          satisfaction_score: (p.satisfaction_score as number | null) ?? null,
          price_sensitivity: c.persona?.price_sensitivity ?? null, brand_loyalty: c.persona?.brand_loyalty ?? null,
          preferred_channel: c.persona?.preferred_channel ?? null, lifestyle: c.persona?.lifestyle ?? null,
          interests: c.persona?.interests ?? [],
        },
      });
      setLoading(false);
    }).catch((e) => setError(String(e.message)));
  }, [id, reset]);

  const values = watch();
  const internet = values.technographic.internet_type;
  const toInput = (v: FormValues): CustomerInput => ({
    ...v,
    contact: { name: v.contact.name || "Preview", email: v.contact.email || null, phone: v.contact.phone || null },
  });

  // Live risk preview: re-scores ~300 ms after the last change.
  const key = JSON.stringify({ ...values, contact: undefined });
  useEffect(() => {
    if (loading) return;
    const parsed = schema.omit({ contact: true }).safeParse(values);
    if (!parsed.success) return;
    const t = setTimeout(() => {
      setPreviewing(true);
      api.predict(toInput(values)).then(setPreview).catch(() => {}).finally(() => setPreviewing(false));
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, loading]);

  const cities = useMemo(() => meta?.cities ?? [], [meta]);
  const pickCity = (name: string) => {
    setValue("geographic.city", name, { shouldValidate: true });
    const c = cities.find((x) => x.city.toLowerCase() === name.toLowerCase());
    if (c) {
      setValue("geographic.latitude", c.latitude);
      setValue("geographic.longitude", c.longitude);
      setValue("geographic.population", c.population);
      setValue("geographic.zip_code", c.zip_code);
    }
  };

  const next = async () => {
    const ok = await trigger(STEPS[step].id as FieldPath<FormValues>);
    if (ok) setStep((s) => Math.min(s + 1, STEPS.length - 1));
  };

  const onSubmit = async (v: FormValues) => {
    setSaving(true);
    try {
      if (editing && id) {
        const r = await api.update(id, toInput(v));
        toast.success(r.changed_fields.length ? `Saved — ${r.changed_fields.length} change(s) sent to the live stream` : "Saved — no profile changes");
        navigate(`/customers/${id}`);
      } else {
        const r = await api.create(toInput(v));
        toast.success(`${v.contact.name} added — ${Math.round(r.churn_probability * 100)}% churn risk`);
        navigate(`/customers/${r.customer_id}`);
      }
    } catch (e) {
      toast.error((e as Error).message);
    }
    setSaving(false);
  };

  if (error) return <ErrorBox error={error} />;
  if (loading || !meta) return <Skeleton className="h-[600px]" />;
  const S = STEPS[step];
  const err = (path: string) => path.split(".").reduce<any>((o, k) => o?.[k], errors)?.message as string | undefined;

  return (
    <div className="space-y-6">
      <PageHeader title={editing ? `Edit ${values.contact.name}` : "Add a customer"}
        subtitle="Fill in what you know — every step updates the predicted risk on the right instantly."
        actions={<Link to={editing ? `/customers/${id}` : "/customers"} className="btn-ghost"><ArrowLeft className="h-4 w-4" /> Cancel</Link>} />

      {/* stepper */}
      <div className="card flex gap-1 overflow-x-auto p-2">
        {STEPS.map((s, i) => {
          const Icon = s.icon;
          const done = i < step;
          return (
            <button key={s.id} type="button" onClick={() => setStep(i)}
                    className={`flex min-w-[9rem] flex-1 items-center gap-2.5 rounded-xl px-3 py-2.5 text-left transition ${
                      i === step ? "bg-surface-2 ring-1 ring-line" : "hover:bg-surface-2/60"}`}>
              <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${done ? "bg-brand-500 text-white" : "bg-surface-2"}`}
                    style={!done && "color" in s ? { color: s.color } : undefined}>
                {done ? <Check className="h-4 w-4" /> : <Icon className="h-4 w-4" />}
              </span>
              <span className="min-w-0">
                <span className="block text-[11px] text-muted">Step {i + 1}</span>
                <span className={`block truncate text-sm font-semibold ${i === step ? "text-ink" : "text-ink-2"}`}>{s.label}</span>
              </span>
            </button>
          );
        })}
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="grid gap-6 xl:grid-cols-5">
        <Section className="xl:col-span-3" title={<span className="flex items-center gap-2">{S.label}</span>} subtitle={S.hint}>
          <AnimatePresence mode="wait">
            <motion.div key={step} initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }}
                        transition={{ duration: 0.18 }} className="space-y-5">
              {S.id === "contact" && (<>
                <Field label="Full name" error={err("contact.name")}><input className="input" placeholder="e.g. Maria Garcia" {...register("contact.name")} /></Field>
                <div className="grid gap-5 sm:grid-cols-2">
                  <Field label="Email" error={err("contact.email")}><input className="input" placeholder="maria@example.com" {...register("contact.email")} /></Field>
                  <Field label="Phone"><input className="input" placeholder="(555) 010-2030" {...register("contact.phone")} /></Field>
                </div>
                <p className="rounded-xl bg-surface-2 p-3 text-xs text-muted">Names and contact details are for your team. The model never uses them — a name can't predict churn, and using it would be unfair.</p>
              </>)}

              {S.id === "geographic" && (<>
                <Field label="City" error={err("geographic.city")} hint="Type to search 1,100+ California cities — location details fill in automatically">
                  <input className="input" list="cities" value={values.geographic.city} onChange={(e) => pickCity(e.target.value)} />
                  <datalist id="cities">{cities.map((c) => <option key={c.city} value={c.city} />)}</datalist>
                </Field>
                <div className="grid gap-5 sm:grid-cols-2">
                  <Field label="Zip code"><input className="input" {...register("geographic.zip_code")} /></Field>
                  <Field label="Area population" hint="People living in the zip code" error={err("geographic.population")}><input type="number" className="input" {...register("geographic.population")} /></Field>
                  <Field label="Latitude" error={err("geographic.latitude")}><input type="number" step="any" className="input" {...register("geographic.latitude")} /></Field>
                  <Field label="Longitude" error={err("geographic.longitude")}><input type="number" step="any" className="input" {...register("geographic.longitude")} /></Field>
                </div>
              </>)}

              {S.id === "demographic" && (<>
                <div className="grid gap-5 sm:grid-cols-2">
                  <Field label="Gender"><Segmented control={control} name="demographic.gender" options={["Female", "Male"]} /></Field>
                  <Field label={`Age: ${values.demographic.age}`} error={err("demographic.age")}>
                    <input type="range" min={18} max={90} className="w-full accent-brand-500" {...register("demographic.age")} />
                  </Field>
                  <Field label="Number of dependents"><input type="number" min={0} max={10} className="input" {...register("demographic.num_dependents")} /></Field>
                  <div className="pt-6"><Toggle control={control} name="demographic.married" label="Married" /></div>
                </div>
              </>)}

              {S.id === "technographic" && (<>
                <Field label="Internet type"><Segmented control={control} name="technographic.internet_type" options={meta.choices.internet_type} /></Field>
                <Field label={`Monthly data use: ${values.technographic.avg_monthly_gb} GB`}>
                  <input type="range" min={0} max={90} disabled={internet === "None"} className="w-full accent-brand-500" {...register("technographic.avg_monthly_gb")} />
                </Field>
                <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
                  <Toggle control={control} name="technographic.phone_service" label="Phone service" />
                  <Toggle control={control} name="technographic.multiple_lines" label="Multiple lines" disabled={!values.technographic.phone_service} />
                  {([["unlimited_data", "Unlimited data"], ["online_security", "Online security"], ["online_backup", "Online backup"],
                     ["device_protection", "Device protection"], ["premium_tech_support", "Premium tech support"],
                     ["streaming_tv", "Streaming TV"], ["streaming_movies", "Streaming movies"], ["streaming_music", "Streaming music"]] as const).map(([k, l]) => (
                    <Toggle key={k} control={control} name={`technographic.${k}`} label={l} disabled={internet === "None"} />
                  ))}
                </div>
              </>)}

              {S.id === "behavioural" && (<>
                <div className="grid gap-5 sm:grid-cols-2">
                  <Field label={`Tenure: ${values.behavioural.tenure_months} months`}>
                    <input type="range" min={0} max={72} className="w-full accent-brand-500" {...register("behavioural.tenure_months")} />
                  </Field>
                  <Field label={`Monthly bill: $${values.behavioural.monthly_charge}`} error={err("behavioural.monthly_charge")}>
                    <input type="range" min={18} max={120} className="w-full accent-brand-500" {...register("behavioural.monthly_charge")} />
                  </Field>
                </div>
                <Field label="Contract"><Segmented control={control} name="behavioural.contract" options={meta.choices.contract} /></Field>
                <Field label="Payment method"><Segmented control={control} name="behavioural.payment_method" options={meta.choices.payment_method} /></Field>
                <Field label="Accepted offer"><Segmented control={control} name="behavioural.offer" options={meta.choices.offer} /></Field>
                <div className="grid gap-5 sm:grid-cols-3">
                  <Field label="Long-distance $/month"><input type="number" step="any" className="input" {...register("behavioural.avg_long_distance")} /></Field>
                  <Field label="Friends referred"><input type="number" min={0} className="input" {...register("behavioural.referrals")} /></Field>
                  <div className="pt-6"><Toggle control={control} name="behavioural.paperless_billing" label="Paperless billing" /></div>
                </div>
              </>)}

              {S.id === "psychographic" && (<>
                <Field label="Satisfaction survey" hint="Known? The more accurate survey model is used. Unknown? The profile model.">
                  <Scale control={control} name="psychographic.satisfaction_score" low="Very unhappy" high="Very happy" allowNone noneLabel="Not surveyed" />
                </Field>
                <div className="rounded-xl border border-dashed border-line p-4">
                  <p className="mb-4 text-xs text-muted">These shape <b>recommended actions</b> (e.g. discounts for price-sensitive customers). They aren't model inputs — no training data exists for them.</p>
                  <div className="grid gap-5 sm:grid-cols-2">
                    <Field label="Price sensitivity"><Scale control={control} name="psychographic.price_sensitivity" low="Not at all" high="Very" allowNone /></Field>
                    <Field label="Brand loyalty"><Scale control={control} name="psychographic.brand_loyalty" low="Low" high="High" allowNone /></Field>
                    <Field label="Lifestyle">
                      <Controller control={control} name="psychographic.lifestyle" render={({ field }) => (
                        <select className="input" value={field.value ?? ""} onChange={(e) => field.onChange(e.target.value || null)}>
                          <option value="">Not specified</option>{meta.choices.lifestyle.map((l) => <option key={l}>{l}</option>)}
                        </select>)} />
                    </Field>
                    <Field label="Preferred contact channel">
                      <Controller control={control} name="psychographic.preferred_channel" render={({ field }) => (
                        <select className="input" value={field.value ?? ""} onChange={(e) => field.onChange(e.target.value || null)}>
                          <option value="">Not specified</option>{meta.choices.preferred_channel.map((l) => <option key={l}>{l}</option>)}
                        </select>)} />
                    </Field>
                  </div>
                  <div className="mt-5">
                    <span className="label">Interests</span>
                    <Controller control={control} name="psychographic.interests" render={({ field }) => (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {INTERESTS.map((i) => {
                          const on = field.value.includes(i);
                          return (
                            <button key={i} type="button" onClick={() => field.onChange(on ? field.value.filter((x) => x !== i) : [...field.value, i])}
                                    className={`rounded-full border px-3 py-1 text-xs font-medium ${on ? "border-pink-500/50 bg-pink-500/10 text-pink-600 dark:text-pink-400" : "border-line text-muted"}`}>{i}</button>
                          );
                        })}
                      </div>)} />
                  </div>
                </div>
              </>)}
            </motion.div>
          </AnimatePresence>

          <div className="mt-8 flex items-center justify-between border-t border-line pt-5">
            <button type="button" className="btn-ghost" disabled={step === 0} onClick={() => setStep(step - 1)}><ArrowLeft className="h-4 w-4" /> Back</button>
            {step < STEPS.length - 1 ? (
              <button type="button" className="btn-primary" onClick={next}>Next <ArrowRight className="h-4 w-4" /></button>
            ) : (
              <button type="submit" className="btn-primary" disabled={saving}>
                {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                {editing ? "Save changes" : "Add customer"}
              </button>
            )}
          </div>
        </Section>

        <div className="space-y-6 xl:col-span-2">
          <div className="space-y-6 xl:sticky xl:top-24">
            <Section title={<span className="flex items-center gap-2"><Wand2 className="h-4 w-4 text-brand-500" /> Live prediction</span>}
                     subtitle={preview ? <span className="flex items-center gap-2">{MODEL_LABEL[preview.model_used]} <ModelChip kind={preview.model_used} /></span> : "Fill in the form…"}
                     action={previewing ? <Loader2 className="h-4 w-4 animate-spin text-muted" /> : null}>
              {preview ? (<>
                <Gauge probability={preview.churn_probability} band={preview.risk_band} threshold={preview.threshold} />
                <p className={`mt-2 text-center font-semibold ${preview.will_churn ? "text-rose-500" : "text-emerald-500"}`}>
                  {preview.will_churn ? "Likely to leave — act early" : "Likely to stay"}
                </p>
              </>) : <Skeleton className="h-40" />}
            </Section>
            {preview && <Section title="Why" subtitle="Biggest factors for this profile"><ReasonBars reasons={preview.reasons.slice(0, 5)} compact /></Section>}
            {preview?.actions && preview.actions.length > 0 && (
              <Section title="What would help" subtitle="Best retention actions for this profile">
                <div className="space-y-3">{preview.actions.slice(0, 2).map((a) => <ActionCard key={a.action_id} action={a} customerId="" compact />)}</div>
              </Section>
            )}
          </div>
        </div>
      </form>
    </div>
  );
}
