import { useState } from "react";
import { Check, ChevronDown, ChevronUp, Play, RotateCcw } from "lucide-react";
import { api } from "../api";
import { useStore, type Screen } from "../store";
import { cx } from "../util";
import { Btn } from "./ui";

interface Step { title: string; text: string; screen: Screen; run: (id: number) => Promise<unknown>; role?: "coordinator" | "facility" }

const TELUGU = "బస్సు లేదు, చాలా దూరం, డబ్బులు కూడా లేవు";
const STEPS: Step[] = [
  { title: "Meet Lakshmi", text: "47, flagged for elevated BP at a camp 6 days ago. Referred, SMS sent, call unanswered. The system has already flagged her: 5 days in 'referred' against a 2-day SLA.", screen: "worklist", run: async () => {} },
  { title: "She replies on WhatsApp in Telugu", text: "\"No bus, very far, no money either.\" The agent reads Telugu, extracts the barrier (transport) and moves her to 'reached'. A support reply is drafted, not sent.", screen: "outreach", run: (id) => api(`/api/journeys/${id}/inbound`, { body: { text: TELUGU } }) },
  { title: "Coordinator approves the draft", text: "Anything that promises support waits for a human. One click sends it in Telugu.", screen: "outreach", role: "coordinator",
    run: async (id) => { const a: any[] = await api("/api/approvals"); const m = a.find((x) => x.journey_id === id); if (m) await api(`/api/messages/${m.id}/decision`, { body: { approve: true }, role: "coordinator" }); } },
  { title: "ASHA visit + appointment", text: "Next-best-action matched her barrier: an ASHA visit with travel support, not 'try calling again'. Visit logged, appointment booked in 3 days.", screen: "worklist", role: "coordinator",
    run: async (id) => { await api(`/api/journeys/${id}/contact`, { body: { channel: "asha_visit", outcome: "reached", note: "Arranged vehicle with PHC" }, role: "coordinator" }); await api(`/api/journeys/${id}/schedule`, { body: { in_days: 3 }, role: "coordinator" }); } },
  { title: "She confirms with “1”", text: "Two-way reminder: a single digit confirms the appointment. No app, no login.", screen: "outreach", run: (id) => api(`/api/journeys/${id}/inbound`, { body: { text: "1" } }) },
  { title: "Time machine: +3 days, facility marks attended", text: "The receiving facility, not the coordinator, records that she showed up.", screen: "facility", role: "facility",
    run: async (id) => { await api("/api/clock/advance", { body: { days: 3 } }); await api(`/api/journeys/${id}/attend`, { method: "POST", body: {}, role: "facility" }); } },
  { title: "Facility confirms the outcome: loop closed", text: "Only the facility can close the loop. Then the funnel updates live.", screen: "insights", role: "facility",
    run: (id) => api(`/api/journeys/${id}/outcome`, { body: { outcome_code: "TREATMENT_STARTED", note: "Plan documented" }, role: "facility" }) },
];

export default function GuidedDemo() {
  const { meta, run, go, setRole, select, reloadMeta, bump, toast } = useStore();
  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);
  const hero = meta?.hero_journey_id;
  const done = idx >= STEPS.length;

  const next = async () => {
    if (!hero || done) return;
    const s = STEPS[idx];
    if (s.role) setRole(s.role);
    select(hero);
    const r = await run(async () => { await s.run(hero); return true; });
    if (r) { setIdx(idx + 1); go(s.screen); }
  };
  const reset = async () => {
    await run(() => api("/api/demo/reset", { method: "POST", body: {} }));
    setRole("coordinator"); setIdx(0); await reloadMeta(); go("worklist"); bump(); toast("info", "Demo data reset");
  };

  return (
    <div className="fixed bottom-20 right-3 z-40 w-[min(92vw,360px)] lg:bottom-5 lg:right-5">
      {open ? (
        <div className="rise rounded-2xl border border-ink bg-card shadow-2xl">
          <button onClick={() => setOpen(false)} className="flex min-h-11 w-full items-center justify-between rounded-t-2xl bg-ink px-4 text-left font-bold text-paper" aria-expanded>
            <span><Play className="mr-2 inline h-4 w-4" aria-hidden />Guided demo · Lakshmi's loop</span><ChevronDown className="h-5 w-5" aria-hidden />
          </button>
          <ol className="max-h-[52vh] space-y-1 overflow-y-auto p-3">
            {STEPS.map((s, i) => (
              <li key={s.title} className={cx("rounded-xl border px-3 py-2", i === idx ? "border-teal bg-teal-soft/50" : i < idx ? "border-line bg-mist/60" : "border-line")}>
                <div className="flex items-center gap-2 font-bold">
                  <span className={cx("grid h-5 w-5 shrink-0 place-items-center rounded-full text-[11px]", i < idx ? "bg-teal text-white" : i === idx ? "bg-ink text-paper" : "bg-mist text-ink3")}>{i < idx ? <Check className="h-3 w-3" aria-hidden /> : i + 1}</span>
                  <span className={i > idx ? "text-ink3" : ""}>{s.title}</span></div>
                {i === idx && <p className="mt-1 text-sm text-ink2">{s.text}</p>}
              </li>))}
          </ol>
          <div className="flex gap-2 border-t border-line p-3">
            <Btn variant="primary" className="flex-1" disabled={done || !hero} onClick={next}>{done ? "Demo complete" : idx === 0 ? "Start" : "Next step"}</Btn>
            <Btn variant="ghost" onClick={reset} aria-label="Reset demo data"><RotateCcw className="h-4 w-4" aria-hidden />Reset</Btn>
          </div>
        </div>
      ) : (
        <button onClick={() => setOpen(true)} className="ml-auto flex min-h-12 items-center gap-2 rounded-full bg-ink px-5 font-bold text-paper shadow-xl transition-transform hover:scale-[1.03]" aria-expanded={false}>
          <Play className="h-4 w-4" aria-hidden />Guided demo<ChevronUp className="h-4 w-4" aria-hidden /></button>
      )}
    </div>
  );
}
