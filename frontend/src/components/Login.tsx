import { useState } from "react";
import { LockKeyhole } from "lucide-react";
import { setToken } from "../api";
import LoopRing from "./LoopRing";
import type { Role } from "../types";

const SEGS = (["done", "done", "done", "done", "stuck", "todo"] as const).map((status, i) => ({ state: String(i), label: "", status }));

export default function Login({ onDone }: { onDone: (r: Role) => void }) {
  const [username, setUsername] = useState("coordinator");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const res = await fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }) });
      const j = await res.json().catch(() => ({}));
      if (!res.ok) { setErr(typeof j.detail === "string" ? j.detail : "Could not sign in"); return; }
      setToken(j.token); onDone(j.role as Role);
    } catch { setErr("Cannot reach the server."); } finally { setBusy(false); }
  }

  return (
    <div className="grid min-h-full place-items-center px-4 py-10">
      <form onSubmit={submit} className="w-full max-w-sm rounded-2xl border border-line bg-card p-6 shadow-sm" aria-labelledby="login-h">
        <div className="mb-5 flex items-center gap-3">
          <LoopRing segments={SEGS as any} size={44} label="CuraLoop logo" />
          <div><h1 id="login-h" className="text-2xl font-bold leading-none tracking-tight">CuraLoop</h1>
            <p className="mt-1 text-xs font-bold uppercase tracking-widest text-ink3">Staff sign-in</p></div>
        </div>
        <label className="block text-sm font-bold" htmlFor="u">Role</label>
        <select id="u" value={username} onChange={(e) => setUsername(e.target.value)} className="mb-3 mt-1 min-h-11 w-full rounded-xl border border-line bg-paper px-3">
          <option value="coordinator">Care coordinator</option><option value="facility">Facility desk</option><option value="manager">Programme manager</option>
        </select>
        <label className="block text-sm font-bold" htmlFor="p">Password</label>
        <input id="p" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)}
          className="mb-3 mt-1 min-h-11 w-full rounded-xl border border-line bg-paper px-3" />
        {err && <p role="alert" className="mb-3 rounded-lg bg-rose-50 px-3 py-2 text-sm font-bold text-rose-800">{err}</p>}
        <button disabled={busy || !password} className="flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-teal font-bold text-white disabled:opacity-50">
          <LockKeyhole className="h-4 w-4" aria-hidden />{busy ? "Signing in…" : "Sign in"}</button>
        <p className="mt-4 text-xs leading-relaxed text-ink3">Access is role-based and every action is written to an audit log.</p>
      </form>
    </div>
  );
}
