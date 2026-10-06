import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Download, FileSpreadsheet, Loader2, UploadCloud, XCircle } from "lucide-react";
import { toast } from "sonner";
import { api, type ImportResult } from "../lib/api";
import { PageHeader, Section } from "../components/ui";

function parsePreview(text: string, rows = 6): string[][] {
  return text.split(/\r?\n/).filter(Boolean).slice(0, rows + 1).map((line) => line.split(","));
}

export default function ImportPage() {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string[][]>([]);
  const [rowCount, setRowCount] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState<"import" | "score" | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);

  const choose = async (f: File | undefined) => {
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".csv")) { toast.error("Please choose a .csv file"); return; }
    const text = await f.text();
    setFile(f);
    setPreview(parsePreview(text));
    setRowCount(text.split(/\r?\n/).filter(Boolean).length - 1);
    setResult(null);
  };

  const runImport = async () => {
    if (!file) return;
    setBusy("import");
    try {
      const r = await api.importCsv(file);
      setResult(r);
      toast.success(`${r.imported} customer(s) imported and sent to the live stream`);
    } catch (e) { toast.error((e as Error).message); }
    setBusy(null);
  };

  const runScore = async () => {
    if (!file) return;
    setBusy("score");
    try {
      const blob = await api.scoreCsv(file);
      const url = URL.createObjectURL(blob);
      Object.assign(document.createElement("a"), { href: url, download: "churnpulse_scored.csv" }).click();
      URL.revokeObjectURL(url);
      toast.success("Scored CSV downloaded");
    } catch (e) { toast.error((e as Error).message); }
    setBusy(null);
  };

  return (
    <div className="space-y-6">
      <PageHeader title="Import & score" subtitle="Add many customers at once, or score a list without saving it."
        actions={<a className="btn-ghost" href="/api/customers/template.csv"><Download className="h-4 w-4" /> Download CSV template</a>} />

      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); choose(e.dataTransfer.files[0]); }}
        onClick={() => input.current?.click()}
        className={`card flex cursor-pointer flex-col items-center justify-center gap-3 border-2 border-dashed p-12 text-center transition ${
          dragging ? "border-brand-500 bg-brand-500/5" : "hover:border-brand-500/50"}`}>
        <div className="rounded-2xl bg-brand-500/10 p-4"><UploadCloud className="h-8 w-8 text-brand-600 dark:text-brand-400" /></div>
        <div>
          <p className="font-semibold text-ink">{file ? file.name : "Drop a CSV file here, or click to choose"}</p>
          <p className="mt-1 text-sm text-muted">{file ? `${rowCount.toLocaleString()} rows` : "Use the template columns · up to 5,000 rows"}</p>
        </div>
        <input ref={input} type="file" accept=".csv" hidden onChange={(e) => choose(e.target.files?.[0])} />
      </div>

      {preview.length > 0 && (
        <Section title="Preview" subtitle="First rows of your file">
          <div className="overflow-x-auto rounded-xl border border-line">
            <table className="w-full text-xs">
              <thead className="bg-surface-2"><tr>{preview[0].map((h, i) => <th key={i} className="whitespace-nowrap px-3 py-2 text-left font-semibold text-muted">{h}</th>)}</tr></thead>
              <tbody className="divide-y divide-line">
                {preview.slice(1).map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className="whitespace-nowrap px-3 py-2 text-ink-2">{c}</td>)}</tr>)}
              </tbody>
            </table>
          </div>
          <div className="mt-5 flex flex-wrap gap-3">
            <button className="btn-primary" disabled={!!busy} onClick={runImport}>
              {busy === "import" ? <Loader2 className="h-4 w-4 animate-spin" /> : <UploadCloud className="h-4 w-4" />} Import as customers
            </button>
            <button className="btn-ghost" disabled={!!busy} onClick={runScore}>
              {busy === "score" ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileSpreadsheet className="h-4 w-4" />} Score only & download
            </button>
          </div>
        </Section>
      )}

      {result && (
        <Section title="Import result">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl bg-surface-2 p-4"><p className="label">Rows</p><p className="mt-1 text-2xl font-bold text-ink">{result.rows}</p></div>
            <div className="rounded-xl bg-emerald-500/10 p-4"><p className="label">Imported</p><p className="mt-1 flex items-center gap-2 text-2xl font-bold text-emerald-600 dark:text-emerald-400"><CheckCircle2 className="h-5 w-5" />{result.imported}</p></div>
            <div className="rounded-xl bg-rose-500/10 p-4"><p className="label">Failed</p><p className="mt-1 flex items-center gap-2 text-2xl font-bold text-rose-500"><XCircle className="h-5 w-5" />{result.failed}</p></div>
          </div>
          {result.customers.length > 0 && (
            <div className="mt-5">
              <p className="label mb-2">New customers (being scored live)</p>
              <div className="flex flex-wrap gap-2">
                {result.customers.map((c) => <Link key={c.customer_id} to={`/customers/${c.customer_id}`} className="chip hover:border-brand-500">{c.name}</Link>)}
              </div>
            </div>
          )}
          {result.errors.length > 0 && (
            <div className="mt-5 space-y-2">
              <p className="label">Rows that need fixing</p>
              {result.errors.map((e) => (
                <div key={e.row} className="rounded-lg border border-rose-500/20 bg-rose-500/5 px-3 py-2 text-sm">
                  <b className="text-rose-500">Row {e.row}:</b> <span className="text-ink-2">{e.errors.join(" · ")}</span>
                </div>
              ))}
            </div>
          )}
        </Section>
      )}
    </div>
  );
}
