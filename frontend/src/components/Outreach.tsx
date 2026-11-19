import { useState } from "react";
import { Bot, Send, ShieldCheck, Check, X } from "lucide-react";
import { api } from "../api";
import { useFetch, useStore } from "../store";
import type { Approval, Card as CardT, Worklist } from "../types";
import { cx, fmtDateTime } from "../util";
import { Btn, Card, Chip, Empty, Loading, Select } from "./ui";

const QUICK = [
  { label: "1 · Confirm", text: "1" }, { label: "2 · Reschedule", text: "2" }, { label: "3 · Need help", text: "3" },
  { label: "Telugu: transport", text: "బస్సు లేదు, చాలా దూరం, డబ్బులు కూడా లేవు" },
  { label: "Hindi: cost", text: "पैसे नहीं हैं, खर्च बहुत है" },
  { label: "English: work", text: "I cannot take leave from work" },
  { label: "Red-flag test", text: "I have chest pain and cannot breathe" },
];

export default function Outreach() {
  const { selectedId, select, run, role, clock } = useStore();
  const [text, setText] = useState("");
  const [last, setLast] = useState<any>(null);
  const { data: j, loading } = useFetch<CardT>(selectedId ? `/api/journeys/${selectedId}` : null);
  const { data: wl } = useFetch<Worklist>("/api/worklist?limit=25");
  const { data: appr } = useFetch<Approval[]>("/api/approvals");

  const send = async (t: string) => {
    if (!selectedId || !t.trim()) return;
    const r = await run(() => api(`/api/journeys/${selectedId}/inbound`, { body: { text: t } }));
    if (r) { setLast(r.parsed); setText(""); }
  };
  const decide = (id: number, approve: boolean) => run(() => api(`/api/messages/${id}/decision`, { body: { approve } }), approve ? "Approved and sent" : "Draft rejected");

  return (
    <div className="grid gap-5 xl:grid-cols-[430px_1fr]">
      <div>
        <h1 className="text-2xl font-bold">Two-way outreach</h1>
        <p className="mb-3 text-sm text-ink3">Patients answer in their own language. The agent reads the reply, updates the loop and drafts a response. No clinical advice, ever.</p>
        <Select label="Patient on the phone" value={selectedId ?? ""} onChange={(v) => select(Number(v))} className="mb-3">
          {j && !wl?.items.some((c) => c.id === j.id) && <option value={j.id}>{j.patient.name} · {j.patient.language_name} · {j.state_label}</option>}
          {wl?.items.map((c) => <option key={c.id} value={c.id}>{c.patient.name} · {c.patient.language_name} · {c.state_label}</option>)}
        </Select>
        <div className="mx-auto w-full max-w-[400px] rounded-[34px] border-[10px] border-ink bg-[#efe8d8] shadow-xl">
          <div className="flex items-center gap-3 rounded-t-[22px] bg-teal-deep px-4 py-3 text-white">
            <div className="grid h-9 w-9 place-items-center rounded-full bg-white/20 font-bold">{j?.patient.name[0] ?? "?"}</div>
            <div className="min-w-0"><div className="truncate font-bold leading-tight">{j?.patient.name ?? "Select a patient"}</div><div className="num text-xs opacity-80">{j?.patient.phone}</div></div>
          </div>
          <div className="h-[330px] space-y-2 overflow-y-auto px-3 py-3" aria-live="polite">
            {loading && !j ? <Loading /> : j?.messages?.filter((m) => m.status !== "rejected" && m.status !== "pending_approval").map((m) => (
              <div key={m.id} className={cx("max-w-[86%] rounded-2xl px-3 py-2 text-[14px] leading-snug shadow-sm", m.direction === "in" ? "ml-auto rounded-br-sm bg-[#d9fdd3]" : "rounded-bl-sm bg-white")}>
                {m.text}<div className="num mt-1 text-right text-[10px] text-ink3">{fmtDateTime(m.ts)}</div>
              </div>
            ))}
            {j && !j.messages?.length && <Empty title="No messages yet" hint="Send a reminder from the worklist." />}
          </div>
          <div className="rounded-b-[22px] bg-[#f6f2ea] px-3 pb-3 pt-2">
            <div className="mb-2 flex flex-wrap gap-1.5">{QUICK.map((q) => <button key={q.label} onClick={() => send(q.text)} className="min-h-8 rounded-full border border-line bg-white px-2.5 text-xs font-bold text-ink2 hover:bg-mist">{q.label}</button>)}</div>
            <form onSubmit={(e) => { e.preventDefault(); send(text); }} className="flex gap-2">
              <label className="flex-1"><span className="sr-only">Type as the patient</span>
                <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Type as the patient…" className="min-h-10 w-full rounded-full border border-line bg-white px-4 text-sm" /></label>
              <Btn variant="primary" type="submit" className="!rounded-full !px-3" aria-label="Send as patient"><Send className="h-4 w-4" aria-hidden /></Btn>
            </form>
          </div>
        </div>
      </div>

      <div className="space-y-4">
        <Card eyebrow="Agent output" title="What the agent understood" right={<Chip tone="teal"><Bot className="h-3 w-3" aria-hidden />Rule engine · te / hi / en</Chip>}>
          {last ? (
            <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div><dt className="eyebrow">Intent</dt><dd className="num mt-1 text-lg font-semibold">{last.intent}</dd></div>
              <div><dt className="eyebrow">Barrier</dt><dd className="mt-1 text-lg font-bold">{last.barrier ?? "-"}</dd></div>
              <div><dt className="eyebrow">Language</dt><dd className="mt-1 text-lg font-bold uppercase">{last.language}</dd></div>
              <div><dt className="eyebrow">Confidence</dt><dd className="mt-1 text-lg font-bold">{last.confidence}</dd></div>
            </dl>
          ) : <p className="text-ink2">Send a message as the patient. Try the Telugu quick reply.</p>}
        </Card>

        <Card eyebrow="Human in the loop" title={`Approval queue${appr ? ` (${appr.length})` : ""}`}>
          {!appr ? <Loading /> : appr.length === 0 ? <Empty title="No drafts waiting" hint="Replies that promise support or change an appointment land here." /> : (
            <ul className="space-y-3">{appr.slice(0, 8).map((a) => (
              <li key={a.id} className="rounded-xl border border-amber/40 bg-amber-soft/40 p-3">
                <div className="flex flex-wrap items-center gap-2"><b>{a.patient.name}</b><Chip tone="amber">{a.intent}</Chip><Chip>{a.language.toUpperCase()}</Chip>
                  <span className="text-xs text-ink3">{clock ? Math.round(a.age_hours) : ""}h waiting</span></div>
                <p className="mt-1.5 text-[15px]">{a.text}</p>
                {a.note && <p className="mt-1 text-xs text-ink3">{a.note}</p>}
                <div className="mt-2 flex gap-2">
                  <Btn size="sm" variant="primary" onClick={() => decide(a.id, true)}><Check className="h-4 w-4" aria-hidden />Approve & send</Btn>
                  <Btn size="sm" variant="ghost" onClick={() => decide(a.id, false)}><X className="h-4 w-4" aria-hidden />Reject</Btn>
                </div>
                {role === "facility" && <p className="mt-1 text-xs text-signal">Switch to Care coordinator to approve.</p>}
              </li>))}</ul>
          )}
        </Card>

        <Card eyebrow="Guardrails" title="What the agent will not do">
          <ul className="space-y-2 text-sm text-ink2">
            {["Never gives medical advice. Symptom words trigger a fixed safety message (call 108) and a clinician alert.",
              "Anything that promises support or changes an appointment waits for a coordinator's approval.",
              "Acknowledgements and the barrier menu are sent automatically. Low-confidence messages are never guessed; a human reads them.",
              "Every inbound and outbound message is stored with its parsed intent and written to the audit trail.",
              "Plugs into WhatsApp Cloud API through POST /api/webhooks/whatsapp. Demo runs on a built-in simulator."].map((t) => (
              <li key={t} className="flex gap-2"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-teal" aria-hidden />{t}</li>))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
