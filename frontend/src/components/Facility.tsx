import { useState } from "react";
import { Building2, CheckCircle2, Lock } from "lucide-react";
import { api } from "../api";
import { useFetch, useStore } from "../store";
import type { Card as CardT } from "../types";
import { fmtDateTime } from "../util";
import { Btn, Card, Chip, Empty, Loading, Select } from "./ui";
import LoopRing from "./LoopRing";

export default function Facility() {
  const { meta, role, setRole, run } = useStore();
  const [fid, setFid] = useState("");
  const [outcome, setOutcome] = useState("SEEN_PLAN_DOCUMENTED");
  const { data, loading } = useFetch<{ items: CardT[] }>(`/api/facility/queue${fid ? `?facility_id=${fid}` : ""}`);
  const isFac = role === "facility";
  const act = (id: number, path: string, body: unknown, ok: string) => run(() => api(`/api/journeys/${id}${path}`, { body, role: "facility" }), ok);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="text-2xl font-bold">Facility desk</h1>
          <p className="max-w-2xl text-sm text-ink3">The receiving facility is the only party that can record attendance and confirm the outcome. That confirmation is what closes the loop.</p></div>
        <Select label="Facility" value={fid} onChange={setFid} className="min-w-72"><option value="">All facilities</option>{meta?.facilities.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}</Select>
      </div>
      {!isFac && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-amber/40 bg-amber-soft/60 px-4 py-3 text-sm">
          <Lock className="h-4 w-4 text-amber" aria-hidden /><span className="font-bold text-amber">You are viewing as {meta?.roles[role]}.</span>
          <span className="text-ink2">Actions below belong to the facility desk.</span>
          <Btn size="sm" variant="primary" onClick={() => setRole("facility")}>Switch to Facility desk</Btn>
        </div>
      )}
      {loading && !data ? <Loading /> : !data || data.items.length === 0 ? <Empty title="No patients expected" hint="Book appointments from the worklist." /> : (
        <ul className="grid gap-3 lg:grid-cols-2">
          {data.items.map((c) => (
            <li key={c.id}><Card className="h-full">
              <div className="flex items-center gap-4">
                <LoopRing segments={c.ring} size={58}><span className="num text-xs font-semibold">{Math.round(c.age_in_state_days)}d</span></LoopRing>
                <div className="min-w-0 flex-1">
                  <div className="font-bold">{c.patient.name} <span className="text-sm font-normal text-ink3">{c.patient.age}{c.patient.sex}</span></div>
                  <div className="text-sm text-ink2">{c.department}</div>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
                    <Chip tone={c.state === "ATTENDED" ? "amber" : "sky"}><Building2 className="h-3 w-3" aria-hidden />{c.facility}</Chip>
                    {c.appointment && <Chip>{fmtDateTime(c.appointment.when)}</Chip>}
                    {c.appointment?.confirmed && <Chip tone="moss">Confirmed by patient</Chip>}
                    {c.gaps[0] && <Chip tone="signal">{c.gaps[0].label}</Chip>}
                  </div>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap items-end gap-2 border-t border-line pt-3">
                {c.state === "SCHEDULED" && <Btn variant="primary" onClick={() => act(c.id, "/attend", {}, "Attendance recorded")}><CheckCircle2 className="h-4 w-4" aria-hidden />Mark attended</Btn>}
                {c.state === "ATTENDED" && (<>
                  <Select label="Visit outcome" value={outcome} onChange={setOutcome} className="min-w-60">{meta && Object.entries(meta.outcomes).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
                  <Btn variant="primary" onClick={() => act(c.id, "/outcome", { outcome_code: outcome }, "Outcome confirmed - loop closed")}><CheckCircle2 className="h-4 w-4" aria-hidden />Confirm outcome & close loop</Btn>
                </>)}
                {!isFac && <span className="text-xs text-ink3">Acts as the facility desk when clicked.</span>}
              </div>
            </Card></li>))}
        </ul>
      )}
    </div>
  );
}
