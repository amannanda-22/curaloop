import { useState, type ReactNode } from "react";
import { AlertTriangle, ArrowRight, CalendarX, CheckCircle2, FileText, Flag, Languages, MapPin, MessageCircle, Phone, ShieldAlert, Zap, Info, Lock } from "lucide-react";
import { api } from "../api";
import { useFetch, useStore } from "../store";
import type { Card as CardT, JEvent, Msg } from "../types";
import { ago, cx, fmtDate, fmtDateTime } from "../util";
import { Btn, BucketBadge, Card, Chip, Loading, Select, bucketStyle } from "./ui";
import LoopRing from "./LoopRing";

const KIND_ICON: Record<string, ReactNode> = {
  state: <ArrowRight className="h-4 w-4" />, contact: <Phone className="h-4 w-4" />, barrier: <Flag className="h-4 w-4" />,
  message: <MessageCircle className="h-4 w-4" />, no_show: <CalendarX className="h-4 w-4" />, flag: <ShieldAlert className="h-4 w-4" />,
  note: <FileText className="h-4 w-4" />,
};

export default function JourneyPanel({ id }: { id: number }) {
  const { data: j, loading } = useFetch<CardT>(`/api/journeys/${id}`);
  const { clock, meta, role, run, select } = useStore();
  const [channel, setChannel] = useState("call");
  const [outcome, setOutcome] = useState("no_answer");
  const [barrier, setBarrier] = useState("");
  const [note, setNote] = useState("");
  const [days, setDays] = useState("3");
  const [fac, setFac] = useState("");
  const [lostReason, setLostReason] = useState("");

  if (loading && !j) return <Loading />;
  if (!j) return null;
  const now = clock?.now ?? new Date().toISOString();
  const post = (path: string, body?: unknown, okMsg?: string, r?: any) => run(() => api(`/api/journeys/${j.id}${path}`, { body: body ?? {}, role: r }), okMsg);
  const open = !["CLOSED", "LOST"].includes(j.state);
  const stuck = j.gaps.length > 0;
  const total = j.score_breakdown.reduce((a, p) => a + p.points, 0) || 1;
  const nba = j.nba;
  const isHero = j.id === meta?.hero_journey_id;

  return (
    <div className="space-y-4">
      {/* header */}
      <Card className="rise">
        <div className="flex flex-wrap items-center gap-5">
          <LoopRing segments={j.ring} size={118} label={`Care loop for ${j.patient.name}`}>
            <span className="num text-[30px] font-semibold">{j.state === "CLOSED" ? "✓" : Math.round(j.age_in_state_days)}</span>
            <span className="mt-1 text-[10px] font-bold uppercase tracking-wider text-ink3">
              {j.state === "CLOSED" ? "closed" : j.sla_days != null ? `of ${j.sla_days}d SLA` : "days here"}
            </span>
          </LoopRing>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-2xl font-bold leading-tight">{j.patient.name}</h2>
              {isHero && <Chip tone="teal">Demo patient</Chip>}
              {open && <BucketBadge bucket={j.bucket} score={j.score} />}
            </div>
            <div className="mt-0.5 text-ink2">{j.patient.age} yrs · {j.patient.sex === "F" ? "Female" : "Male"} · {j.patient.village}</div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Chip tone={j.urgency === "HIGH" ? "signal" : "mist"}>{j.urgency === "HIGH" ? "Urgent follow-up" : "Routine follow-up"}</Chip>
              <Chip tone="sky"><Languages className="h-3 w-3" aria-hidden />{j.patient.language_name}</Chip>
              {j.facility && <Chip><MapPin className="h-3 w-3" aria-hidden />{j.facility} · {j.distance_km} km</Chip>}
              <Chip title="Synthetic ABHA-style id" >{j.patient.abha_id}</Chip>
              {j.patient.consent_outreach === false && <Chip tone="signal" title="Patient replied STOP. Use calls or an ASHA visit.">Opted out of messages</Chip>}
            </div>
            <div className="mt-2 text-sm text-ink3">Screening flag: <span className="font-semibold text-ink2">{j.finding}</span> → {j.department}</div>
          </div>
        </div>
        <ol className="mt-4 grid grid-cols-3 gap-1.5 sm:grid-cols-6" aria-label="Loop stages">
          {j.ring.map((s) => (
            <li key={s.state} className={cx("rounded-lg px-2 py-1.5 text-center text-[11px] font-bold leading-tight",
              s.status === "done" ? "bg-teal-soft text-teal-deep" : s.status === "stuck" ? "bg-signal-soft text-signal" : s.status === "current" ? "bg-ink text-paper" : s.status === "lost" ? "bg-mist text-ink2 line-through" : "bg-mist text-ink3")}>
              {s.label}{s.status === "stuck" && <span className="block text-[10px] font-semibold">stuck here</span>}
            </li>
          ))}
        </ol>
        {j.state === "CLOSED" && <p className="mt-3 rounded-lg bg-moss-soft px-3 py-2 text-sm font-bold text-moss"><CheckCircle2 className="mr-1.5 inline h-4 w-4" aria-hidden />Loop closed {j.closed_at && fmtDate(j.closed_at)} · confirmed by the receiving facility: {j.close_reason}</p>}
        {j.state === "LOST" && <p className="mt-3 rounded-lg bg-mist px-3 py-2 text-sm font-bold text-ink2">Closed as lost to follow-up: {j.close_reason}</p>}
      </Card>

      {/* why flagged */}
      {open && (
        <Card eyebrow="Why this case is flagged" title={stuck ? "Where the journey is stuck" : "On track"} className="rise">
          {stuck ? (
            <ul className="space-y-2.5">
              {j.gaps.map((g) => (
                <li key={g.code} className="flex gap-3">
                  <AlertTriangle className={cx("mt-0.5 h-5 w-5 shrink-0", g.severity >= 3 ? "text-signal" : "text-amber")} aria-hidden />
                  <div><div className="font-bold">{g.label}</div><div className="text-sm text-ink2">{g.detail}</div></div>
                </li>
              ))}
            </ul>
          ) : <p className="text-ink2">Within SLA for this stage. No action needed yet.</p>}
          {j.score_breakdown.length > 0 && (
            <div className="mt-4">
              <div className="eyebrow mb-1.5">Priority score <span className="num text-ink">{j.score}</span> — every point explained</div>
              <div className="flex h-3 overflow-hidden rounded-full bg-mist" role="img" aria-label={j.score_breakdown.map((p) => `${p.label} ${p.points}`).join(", ")}>
                {j.score_breakdown.map((p, i) => <span key={p.label} style={{ width: `${(p.points / total) * 100}%`, opacity: 1 - i * 0.12 }} className={bucketStyle(j.bucket).bar} />)}
              </div>
              <ul className="mt-2 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
                {j.score_breakdown.map((p) => <li key={p.label} className="flex justify-between gap-2 border-b border-line/70 py-1"><span className="text-ink2">{p.label}</span><span className="num font-semibold">+{p.points}</span></li>)}
              </ul>
            </div>
          )}
        </Card>
      )}

      {/* next best action */}
      {open && nba && (
        <Card className="rise border-l-4 border-l-teal">
          <div className="flex items-start justify-between gap-3">
            <div><div className="eyebrow flex items-center gap-1.5"><Zap className="h-3.5 w-3.5 text-teal" aria-hidden />Next best action</div>
              <h3 className="mt-0.5 text-xl font-bold leading-snug">{nba.title}</h3></div>
            <Chip tone="teal">{nba.owner}</Chip>
          </div>
          <p className="mt-1 text-ink2">{nba.detail}</p>
          <ul className="mt-3 space-y-1 text-sm text-ink2">{nba.why.map((w) => <li key={w} className="flex gap-2"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-teal" aria-hidden />{w}</li>)}</ul>
          <div className="mt-3 flex items-center gap-1.5" aria-label={`Escalation ladder, current step ${nba.step}`}>
            {nba.ladder.map((s, i) => {
              const cur = nba.step === s || (nba.step === "BARRIER" && s === "ASHA");
              return (<span key={s} className="flex items-center gap-1.5">
                <span className={cx("rounded-md px-2 py-0.5 text-[11px] font-bold", cur ? "bg-teal text-white" : "bg-mist text-ink3")}>{s === "SMS" ? "SMS" : s === "CALL" ? "Call" : s === "ASHA" ? "ASHA visit" : "Supervisor"}</span>
                {i < nba.ladder.length - 1 && <ArrowRight className="h-3 w-3 text-ink3" aria-hidden />}</span>);
            })}
          </div>
          {nba.script && (
            <figure className="mt-3 rounded-xl bg-mist px-4 py-3">
              <figcaption className="eyebrow mb-1">Suggested message · {j.patient.language_name}</figcaption>
              <blockquote className="text-[15px] leading-relaxed">{nba.script}</blockquote>
            </figure>
          )}
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {nba.step === "SMS" && <Btn variant="primary" onClick={() => post("/messages/send", { template: "reminder" }, "WhatsApp reminder sent")}>Send two-way WhatsApp reminder</Btn>}
            {nba.step === "REMIND" && <Btn variant="primary" onClick={() => post("/messages/send", { template: "appt_reminder" }, "Appointment reminder sent")}>Send appointment reminder</Btn>}
            {nba.step === "CLINICIAN" && <Btn variant="primary" onClick={() => post("/clear-flag", {}, "Marked as reviewed by clinician")}>Clinician has reviewed - clear flag</Btn>}
            {["CALL", "ASHA", "BARRIER", "SUPERVISOR"].includes(nba.step) && (<>
              <Btn variant="primary" onClick={() => post("/contact", { channel: nba.channel === "asha_visit" ? "asha_visit" : "call", outcome: "reached", barrier: barrier || null, note }, "Logged: patient reached")}>
                {nba.channel === "asha_visit" ? "Log ASHA visit: patient reached" : "Log call: patient reached"}</Btn>
              <Btn variant="ghost" onClick={() => post("/contact", { channel: nba.channel === "asha_visit" ? "asha_visit" : "call", outcome: "no_answer", note }, "Logged: no answer")}>Log: no answer</Btn>
            </>)}
            {nba.step === "FACILITY_NUDGE" && (<>
              <Chip tone="amber"><Lock className="h-3 w-3" aria-hidden />Only the facility can close this loop</Chip>
              <Btn variant="ghost" size="sm" onClick={() => post("/outcome", { outcome_code: "SEEN_PLAN_DOCUMENTED" }, undefined, "coordinator")}>Try closing it yourself</Btn>
            </>)}
          </div>
        </Card>
      )}

      {/* actions */}
      {open && (
        <Card eyebrow="Coordinator tools" title="Log what happened" className="rise">
          {j.state === "SCREENED" && (
            <div className="flex flex-wrap items-end gap-3">
              <Select label="Receiving facility" value={fac} onChange={setFac} className="min-w-64">
                <option value="">Choose facility…</option>{meta?.facilities.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
              </Select>
              <Btn variant="primary" disabled={!fac} onClick={() => post("/refer", { facility_id: Number(fac) }, "Referral raised")}>Raise referral</Btn>
            </div>
          )}
          {["REFERRED", "CONTACTED"].includes(j.state) && (
            <div className="grid gap-3 sm:grid-cols-4">
              <Select label="Channel" value={channel} onChange={setChannel}><option value="call">Phone call</option><option value="sms">SMS</option><option value="asha_visit">ASHA home visit</option></Select>
              <Select label="Result" value={outcome} onChange={setOutcome}><option value="reached">Patient reached</option><option value="no_answer">No answer</option><option value="wrong_number">Wrong number</option><option value="sent">Sent (no reply yet)</option></Select>
              <Select label="Barrier heard" value={barrier} onChange={setBarrier}><option value="">None / unknown</option>{meta && Object.entries(meta.barriers).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
              <label className="block"><span className="eyebrow">Note</span><input value={note} onChange={(e) => setNote(e.target.value)} className="mt-1 block min-h-10 w-full rounded-lg border border-line bg-card px-3 text-sm" placeholder="Optional" /></label>
              <div className="flex flex-wrap gap-2 sm:col-span-4">
                <Btn onClick={() => post("/contact", { channel, outcome, barrier: barrier || null, note }, "Attempt logged")}>Log attempt</Btn>
                <Btn variant="ghost" onClick={() => post("/messages/send", { template: "reminder" }, "WhatsApp reminder sent")}>Send WhatsApp reminder</Btn>
                <Btn variant="ghost" onClick={() => post("/messages/send", { template: "menu" }, "Barrier question sent")}>Ask what is stopping them</Btn>
              </div>
            </div>
          )}
          {j.state === "CONTACTED" && (
            <div className="mt-4 flex flex-wrap items-end gap-3 border-t border-line pt-4">
              <Select label="Book appointment" value={days} onChange={setDays}>{[2, 3, 5, 7].map((d) => <option key={d} value={d}>In {d} days</option>)}</Select>
              <Btn variant="primary" onClick={() => post("/schedule", { in_days: Number(days) }, "Appointment booked")}>Book appointment</Btn>
            </div>
          )}
          {j.state === "SCHEDULED" && j.appointment && (
            <p className="text-ink2">Appointment at {j.appointment.facility} on <b>{fmtDateTime(j.appointment.when)}</b> · {j.appointment.confirmed ? <Chip tone="moss">Patient confirmed</Chip> : <Chip tone="amber">Not confirmed yet</Chip>}. Attendance is recorded by the facility desk.</p>
          )}
          {j.state === "ATTENDED" && <p className="text-ink2">Waiting for the facility to confirm the visit outcome. You cannot close this loop yourself - that is the point.</p>}
          {role === "manager" && (
            <div className="mt-4 flex flex-wrap items-end gap-3 border-t border-line pt-4">
              <label className="min-w-64 flex-1"><span className="eyebrow">Close as lost (manager only)</span>
                <input value={lostReason} onChange={(e) => setLostReason(e.target.value)} placeholder="Reason, e.g. unreachable after full ladder" className="mt-1 block min-h-10 w-full rounded-lg border border-line bg-card px-3 text-sm" /></label>
              <Btn variant="danger" disabled={lostReason.length < 3} onClick={() => post("/close-lost", { reason: lostReason }, "Closed as lost")}>Close as lost</Btn>
            </div>
          )}
        </Card>
      )}

      {/* timeline */}
      <Card eyebrow="Patient journey" title="Timeline" className="rise" right={<a className="inline-flex min-h-9 items-center gap-1 text-sm font-bold text-teal underline-offset-2 hover:underline" href={`/api/fhir/journey/${j.id}`} target="_blank" rel="noreferrer"><Info className="h-4 w-4" aria-hidden />FHIR bundle</a>}>
        <Timeline events={j.events ?? []} messages={j.messages ?? []} now={now} />
      </Card>
    </div>
  );
}

function Timeline({ events, messages, now }: { events: JEvent[]; messages: Msg[]; now: string }) {
  type Item = { ts: string; ev?: JEvent; msg?: Msg };
  const evs = events.filter((e) => !(e.kind === "message" && messages.length));
  const items: Item[] = [...evs.map((ev) => ({ ts: ev.ts, ev })), ...messages.filter((m) => m.status !== "rejected").map((msg) => ({ ts: msg.ts, msg }))]
    .sort((a, b) => (a.ts < b.ts ? 1 : -1));
  return (
    <ol className="relative space-y-3 border-l-2 border-line pl-5">
      {items.map((it, i) => {
        if (it.msg) {
          const m = it.msg;
          return (
            <li key={`m${m.id}`} className="relative">
              <span className="absolute -left-[31px] top-1 grid h-6 w-6 place-items-center rounded-full bg-sky-soft text-sky"><MessageCircle className="h-3.5 w-3.5" aria-hidden /></span>
              <div className="text-xs text-ink3">{fmtDateTime(m.ts)} · {ago(m.ts, now)} · {m.channel}</div>
              <div className={cx("mt-1 max-w-xl rounded-xl px-3 py-2 text-sm", m.direction === "in" ? "bg-card ring-1 ring-line" : "bg-teal-soft", m.status === "pending_approval" && "ring-2 ring-amber")}>
                <div className="mb-0.5 flex flex-wrap items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-ink3">
                  {m.direction === "in" ? "Patient" : "CuraLoop"}{m.intent && <Chip>{m.intent}{m.barrier ? ` · ${m.barrier}` : ""}</Chip>}
                  {m.status === "pending_approval" && <Chip tone="amber">Awaiting approval</Chip>}{m.flag && <Chip tone="signal">{m.flag}</Chip>}
                </div>
                {m.text}
              </div>
            </li>
          );
        }
        const e = it.ev!;
        const tone = e.kind === "no_show" || e.kind === "flag" ? "bg-signal-soft text-signal" : e.kind === "barrier" ? "bg-amber-soft text-amber" : e.kind === "state" ? "bg-teal-soft text-teal-deep" : "bg-mist text-ink2";
        return (
          <li key={`e${e.id}${i}`} className="relative">
            <span className={cx("absolute -left-[31px] top-0.5 grid h-6 w-6 place-items-center rounded-full", tone)}>{KIND_ICON[e.kind] ?? KIND_ICON.note}</span>
            <div className="text-xs text-ink3">{fmtDateTime(e.ts)} · {ago(e.ts, now)} · {e.actor}</div>
            <div className="text-sm font-semibold text-ink">{e.kind === "state" && e.to ? `${e.from ? e.from.toLowerCase() + " → " : ""}${e.to.toLowerCase()}` : e.kind}{e.channel ? ` · ${e.channel}` : ""}</div>
            {e.detail && <div className="text-sm text-ink2">{e.detail}</div>}
          </li>
        );
      })}
    </ol>
  );
}
