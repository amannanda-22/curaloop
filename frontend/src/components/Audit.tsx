import { useEffect, useState } from "react";
import { Lock } from "lucide-react";
import { api } from "../api";
import { useFetch, useStore } from "../store";
import type { AuditRow, Rules } from "../types";
import { fmtDateTime } from "../util";
import { Btn, Card, Chip, Loading } from "./ui";

export default function Audit() {
  const { role, run, setRole } = useStore();
  const { data: rows } = useFetch<AuditRow[]>("/api/audit?limit=120");
  const { data: rules } = useFetch<Rules>("/api/rules");
  const [draft, setDraft] = useState<Rules | null>(null);
  useEffect(() => { if (rules) setDraft(structuredClone(rules)); }, [rules]);
  const isMgr = role === "manager";
  const save = () => draft && run(() => api("/api/rules", { method: "PUT", body: draft }), "Rules saved. Worklist re-ranked.");

  const num = (v: string) => Math.max(0, Number(v) || 0);
  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-bold">Rules & audit trail</h1>
        <p className="max-w-3xl text-sm text-ink3">Prioritisation is configurable and transparent. Operational policy only, nothing clinical. Every action, by every role and by the agent, is logged (who, when, what) to support DPDP Act 2023 accountability.</p></div>

      <Card eyebrow="Configurable rules" title="SLAs and priority weights" right={isMgr ? <Btn variant="primary" onClick={save}>Save rules</Btn> : <Btn size="sm" variant="ghost" onClick={() => setRole("manager")}><Lock className="h-3.5 w-3.5" aria-hidden />Switch to Programme manager to edit</Btn>}>
        {!draft ? <Loading /> : (
          <div className="grid gap-6 lg:grid-cols-2">
            <div>
              <div className="eyebrow mb-2">Days allowed in each stage before it is an SLA breach</div>
              <table className="w-full text-sm"><thead><tr className="text-left text-xs uppercase tracking-wide text-ink3"><th className="py-1">Stage</th><th>Urgent</th><th>Routine</th></tr></thead>
                <tbody>{["SCREENED", "REFERRED", "CONTACTED", "ATTENDED"].map((st) => (
                  <tr key={st} className="border-t border-line/60"><td className="py-1.5 font-bold">{st[0] + st.slice(1).toLowerCase()}</td>
                    {["HIGH", "ROUTINE"].map((u) => <td key={u}><input aria-label={`${u} ${st} SLA days`} type="number" min={0} disabled={!isMgr} value={draft.sla_days[u][st]} onChange={(e) => setDraft({ ...draft, sla_days: { ...draft.sla_days, [u]: { ...draft.sla_days[u], [st]: num(e.target.value) } } })} className="num min-h-9 w-20 rounded-md border border-line bg-card px-2 disabled:bg-mist" /></td>)}</tr>))}</tbody></table>
              <div className="mt-4 grid grid-cols-2 gap-3">
                {(["calls", "asha_visits"] as const).map((k) => <label key={k}><span className="eyebrow">{k === "calls" ? "Daily calls" : "Daily ASHA visits"}</span>
                  <input type="number" min={0} disabled={!isMgr} value={draft.capacity[k]} onChange={(e) => setDraft({ ...draft, capacity: { ...draft.capacity, [k]: num(e.target.value) } })} className="num mt-1 block min-h-9 w-full rounded-md border border-line bg-card px-2 disabled:bg-mist" /></label>)}
              </div>
            </div>
            <div>
              <div className="eyebrow mb-2">Priority score points</div>
              <ul className="grid gap-x-4 gap-y-1.5 sm:grid-cols-2">{Object.entries(draft.weights).map(([k, v]) => (
                <li key={k} className="flex items-center justify-between gap-2 text-sm"><span className="text-ink2">{k.replace(/_/g, " ")}</span>
                  <input aria-label={k} type="number" min={0} disabled={!isMgr} value={v} onChange={(e) => setDraft({ ...draft, weights: { ...draft.weights, [k]: num(e.target.value) } })} className="num min-h-9 w-20 rounded-md border border-line bg-card px-2 disabled:bg-mist" /></li>))}</ul>
            </div>
          </div>)}
      </Card>

      <Card eyebrow="Immutable log" title="Audit trail" right={<Chip>latest 120</Chip>}>
        {!rows ? <Loading /> : (
          <div className="max-h-[480px] overflow-auto"><table className="w-full min-w-[720px] text-left text-sm">
            <thead className="sticky top-0 bg-card"><tr className="border-b border-line text-xs uppercase tracking-wide text-ink3"><th className="py-2 pr-3">When</th><th className="pr-3">Who</th><th className="pr-3">Role</th><th className="pr-3">Action</th><th className="pr-3">Case</th><th>Detail</th></tr></thead>
            <tbody>{rows.map((r) => (<tr key={r.id} className="border-b border-line/60"><td className="num py-1.5 pr-3 text-xs text-ink3">{fmtDateTime(r.ts)}</td><td className="pr-3 font-semibold">{r.actor}</td><td className="pr-3"><Chip>{r.role}</Chip></td><td className="num pr-3 text-xs">{r.action}</td><td className="num pr-3">{r.entity_id ?? "-"}</td><td className="max-w-md truncate text-ink2">{r.detail}</td></tr>))}</tbody></table></div>)}
      </Card>
    </div>
  );
}
