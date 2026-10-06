import { useState } from "react";
import { Link, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { Toaster } from "sonner";
import {
  Activity, BrainCircuit, ChevronsLeft, ChevronsRight, ExternalLink, LayoutDashboard, Moon, Search, Sun, Target,
  Upload, UserPlus, Users,
} from "lucide-react";
import { useTheme } from "./lib/theme";
import Overview from "./pages/Overview";
import Customers from "./pages/Customers";
import Customer360 from "./pages/Customer360";
import CustomerForm from "./pages/CustomerForm";
import ImportPage from "./pages/Import";
import ActionCenter from "./pages/ActionCenter";
import ModelPage from "./pages/Model";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/customers", label: "Customers", icon: Users },
  { to: "/actions", label: "Action Center", icon: Target },
  { to: "/customers/new", label: "Add customer", icon: UserPlus },
  { to: "/import", label: "Import & score", icon: Upload },
  { to: "/model", label: "Models", icon: BrainCircuit },
];

// The public demo serves everything from one origin: only the safe, read-only tools.
const TOOLS = import.meta.env.VITE_PUBLIC_DEMO
  ? [
      { href: "/flink/", label: "Flink" },
      { href: "/api/docs", label: "API docs" },
    ]
  : [
      { href: "http://localhost:8080", label: "Kafka UI" },
      { href: "http://localhost:8081", label: "Flink" },
      { href: "http://localhost:3001", label: "Grafana" },
      { href: "http://localhost:5000", label: "MLflow" },
      { href: "/api/docs", label: "API docs" },
    ];

export default function App() {
  const { theme, toggle } = useTheme();
  const [collapsed, setCollapsed] = useState(false);
  const [q, setQ] = useState("");
  const navigate = useNavigate();

  return (
    <div className="flex min-h-screen">
      <aside className={`sticky top-0 hidden h-screen shrink-0 flex-col border-r border-line bg-surface/70 backdrop-blur-xl transition-all duration-300 md:flex ${collapsed ? "w-[76px]" : "w-64"}`}>
        <Link to="/" className="flex items-center gap-3 px-5 py-5">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-brand-400 to-brand-600 shadow-lg shadow-brand-600/30">
            <Activity className="h-5 w-5 text-white" strokeWidth={2.5} />
          </div>
          {!collapsed && (
            <div>
              <p className="font-bold tracking-tight text-ink">ChurnPulse</p>
              <p className="text-[11px] text-muted">Customer retention AI</p>
            </div>
          )}
        </Link>
        <nav className="mt-2 space-y-1 px-3">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === "/" || to === "/customers"} title={label}
              className={({ isActive }) => `group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${
                isActive ? "bg-brand-500/10 text-brand-700 dark:text-brand-400" : "text-ink-2 hover:bg-surface-2 hover:text-ink"}`}>
              <Icon className="h-[18px] w-[18px] shrink-0" />
              {!collapsed && label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto px-3 pb-4">
          {!collapsed && (
            <>
              <p className="label mb-1.5 px-3">Platform</p>
              {TOOLS.map((t) => (
                <a key={t.label} href={t.href} target="_blank" rel="noreferrer"
                   className="flex items-center justify-between rounded-lg px-3 py-1.5 text-sm text-muted hover:bg-surface-2 hover:text-ink">
                  {t.label} <ExternalLink className="h-3.5 w-3.5 opacity-60" />
                </a>
              ))}
            </>
          )}
          <button onClick={() => setCollapsed(!collapsed)}
                  className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs text-muted hover:bg-surface-2">
            {collapsed ? <ChevronsRight className="h-4 w-4" /> : <><ChevronsLeft className="h-4 w-4" /> Collapse</>}
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-line bg-app/75 px-4 py-3 backdrop-blur-xl sm:px-8">
          <form className="relative max-w-md flex-1" onSubmit={(e) => { e.preventDefault(); navigate(`/customers?q=${encodeURIComponent(q)}`); }}>
            <Search className="absolute left-3.5 top-3 h-4 w-4 text-muted" />
            <input className="input pl-10" placeholder="Search customers by name, email, city or ID…" value={q}
                   onChange={(e) => setQ(e.target.value)} />
          </form>
          <div className="ml-auto flex items-center gap-2">
            <Link to="/customers/new" className="btn-primary hidden sm:inline-flex"><UserPlus className="h-4 w-4" /> Add customer</Link>
            <button onClick={toggle} className="btn-ghost h-10 w-10 !p-0" title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}>
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
          </div>
        </header>
        <main className="min-w-0 flex-1 px-4 py-6 sm:px-8 sm:py-8">
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/customers" element={<Customers />} />
            <Route path="/customers/new" element={<CustomerForm />} />
            <Route path="/customers/:id" element={<Customer360 />} />
            <Route path="/customers/:id/edit" element={<CustomerForm />} />
            <Route path="/import" element={<ImportPage />} />
            <Route path="/actions" element={<ActionCenter />} />
            <Route path="/model" element={<ModelPage />} />
          </Routes>
        </main>
      </div>
      <Toaster richColors position="bottom-right" theme={theme} closeButton />
    </div>
  );
}
