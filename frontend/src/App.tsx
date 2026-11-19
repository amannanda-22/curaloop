import { useEffect, useState } from "react";
import { Activity, Building2, ClipboardCheck, ListChecks, LogOut, MessagesSquare, Route, ScrollText } from "lucide-react";
import { StoreProvider, useStore, type Screen } from "./store";
import { api, getToken, setToken } from "./api";
import { cx, fmtLong } from "./util";
import type { Role } from "./types";
import { Btn, Toasts } from "./components/ui";
import LoopRing from "./components/LoopRing";
import Worklist from "./components/Worklist";
import Outreach from "./components/Outreach";
import Facility from "./components/Facility";
import Insights from "./components/Insights";
import Planner from "./components/Planner";
import Audit from "./components/Audit";
import GuidedDemo from "./components/GuidedDemo";
import Login from "./components/Login";

const NAV: { key: Screen; label: string; icon: typeof ListChecks }[] = [
  { key: "worklist", label: "Worklist", icon: ListChecks },
  { key: "outreach", label: "Outreach", icon: MessagesSquare },
  { key: "facility", label: "Facility desk", icon: Building2 },
  { key: "insights", label: "Insights", icon: Activity },
  { key: "planner", label: "Impact", icon: Route },
  { key: "audit", label: "Rules & audit", icon: ScrollText },
];
const LOGO_SEGS = (["done", "done", "done", "done", "stuck", "todo"] as const).map((status, i) => ({ state: String(i), label: "", status }));

function Shell() {
  const { screen, go, role, setRole, clock, meta, run, secure, signOut } = useStore();
  const advance = (d: number) => run(() => api("/api/clock/advance", { body: { days: d } }), `Time machine: +${d} day${d > 1 ? "s" : ""}`);
  return (
    <div className="min-h-full lg:grid lg:grid-cols-[232px_1fr]">
      <aside className="hidden border-r border-line bg-card/70 px-4 py-5 lg:block">
        <div className="sticky top-5">
          <div className="mb-8 flex items-center gap-3 px-1">
            <LoopRing segments={LOGO_SEGS as any} size={40} label="CuraLoop logo" />
            <div><div className="text-xl font-bold leading-none tracking-tight">CuraLoop</div><div className="mt-1 text-[11px] font-bold uppercase tracking-widest text-ink3">Close the loop</div></div>
          </div>
          <nav aria-label="Main" className="space-y-1">
            {NAV.map(({ key, label, icon: Icon }) => (
              <button key={key} onClick={() => go(key)} aria-current={screen === key ? "page" : undefined}
                className={cx("flex min-h-11 w-full items-center gap-3 rounded-xl px-3 text-left font-bold transition-colors", screen === key ? "bg-ink text-paper" : "text-ink2 hover:bg-mist")}>
                <Icon className="h-5 w-5" aria-hidden />{label}</button>))}
          </nav>
          <div className="mt-8 rounded-xl border border-line bg-paper p-3 text-xs leading-relaxed text-ink3">
            <ClipboardCheck className="mb-1 h-4 w-4 text-teal" aria-hidden />
            Synthetic data only. CuraLoop prioritises <b>operational follow-up</b>. It never diagnoses or advises clinically.
          </div>
        </div>
      </aside>

      <div className="min-w-0 pb-24 lg:pb-8">
        <header className="sticky top-0 z-30 border-b border-line bg-paper/90 px-4 py-2.5 backdrop-blur sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
            <div className="flex items-center gap-2.5 lg:hidden"><LoopRing segments={LOGO_SEGS as any} size={30} label="CuraLoop" /><span className="text-lg font-bold">CuraLoop</span><button onClick={() => go("audit")} className="ml-1 min-h-9 rounded-lg border border-line px-2 text-xs font-bold text-ink2">Rules & audit</button></div>
            <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Time machine">
              <div><div className="eyebrow">Demo date</div><div className="text-sm font-bold">{clock ? fmtLong(clock.now) : "…"}</div></div>
              {[1, 3, 7].map((d) => <Btn key={d} size="sm" variant="ghost" onClick={() => advance(d)} title="Fast-forward the simulated clock to watch SLAs breach">+{d}d</Btn>)}
            </div>
            {secure ? (
              <div className="flex items-center gap-2 rounded-xl border border-line bg-card py-1 pl-3 pr-1 text-sm">
                <span className="font-bold">{meta?.roles[role] ?? role}</span>
                <button onClick={signOut} className="flex min-h-9 items-center gap-1.5 rounded-lg px-3 font-bold text-ink2 hover:bg-mist"><LogOut className="h-4 w-4" aria-hidden />Sign out</button>
              </div>
            ) : (
            <div role="radiogroup" aria-label="Acting as" className="flex rounded-xl border border-line bg-card p-1">
              {(Object.keys(meta?.roles ?? { coordinator: "", facility: "", manager: "" }) as Role[]).map((r) => (
                <button key={r} role="radio" aria-checked={role === r} onClick={() => setRole(r)}
                  className={cx("min-h-9 rounded-lg px-3 text-sm font-bold transition-colors", role === r ? "bg-teal text-white" : "text-ink2 hover:bg-mist")}>
                  {meta?.roles[r] ?? r}</button>))}
            </div>)}
          </div>
        </header>
        <main className="px-4 py-5 sm:px-6">
          {screen === "worklist" && <Worklist />}
          {screen === "outreach" && <Outreach />}
          {screen === "facility" && <Facility />}
          {screen === "insights" && <Insights />}
          {screen === "planner" && <Planner />}
          {screen === "audit" && <Audit />}
        </main>
      </div>

      <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-line bg-card lg:hidden">
        {NAV.slice(0, 5).map(({ key, label, icon: Icon }) => (
          <button key={key} onClick={() => go(key)} aria-current={screen === key ? "page" : undefined}
            className={cx("flex min-h-14 flex-col items-center justify-center gap-0.5 text-[10px] font-bold", screen === key ? "text-teal" : "text-ink3")}>
            <Icon className="h-5 w-5" aria-hidden />{label.split(" ")[0]}</button>))}
      </nav>
      <GuidedDemo />
      <Toasts />
    </div>
  );
}

export default function App() {
  const [mode, setMode] = useState<"loading" | "demo" | "secure">("loading");
  const [role, setRole] = useState<Role | null>(null);
  useEffect(() => {
    fetch("/api/meta/public").then((r) => r.json()).then((j) => setMode(j.auth_mode === "secure" ? "secure" : "demo")).catch(() => setMode("demo"));
  }, []);
  useEffect(() => {
    if (mode !== "secure" || !getToken()) return;
    api<{ role: Role }>("/api/auth/me").then((j) => setRole(j.role)).catch(() => setToken(null));
    const off = () => setRole(null);
    window.addEventListener("curaloop:signout", off);
    return () => window.removeEventListener("curaloop:signout", off);
  }, [mode]);
  if (mode === "loading") return null;
  if (mode === "secure" && !role) return <Login onDone={setRole} />;
  const signOut = () => { setToken(null); setRole(null); };
  return <StoreProvider initialRole={role ?? "coordinator"} secure={mode === "secure"} signOut={signOut}><Shell /></StoreProvider>;
}
