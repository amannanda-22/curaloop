import { useEffect, useState } from "react";
import { Phone, Footprints, MessageSquare, FlaskConical } from "lucide-react";
import { api } from "../api";
import { useStore } from "../store";
import type { PlanRes, SimRes } from "../types";
import { Card, Chip, Loading, bucketStyle } from "./ui";
import { LineChart } from "./charts";
import Impact from "./Impact";

const ACT = { call: { label: "Call", icon: Phone, tone: "bg-sky-soft text-sky" }, asha_visit: { label: "ASHA visit", icon: Footprints, tone: "bg-teal-soft text-teal-deep" }, sms: { label: "WhatsApp/SMS", icon: MessageSquare, tone: "bg-mist text-ink2" } } as const;

export default function Planner() {
  const { tick, select, go } = useStore();
  const [calls, setCalls] = useState(25);
  const [visits, setVisits] = useState(6);
  const [plan, setPlan] = useState<PlanRes | null>(null);
  const [extra, setExtra] = useState(2);
  const [sms, setSms] = useState(50);
  const [transport, setTransport] = useState(true);
  const [sim, setSim] = useState<SimRes | null>(null);

  useEffect(() => {
    const t = setTimeout(() => { api<PlanRes>("/api/planner/optimize", { body: { calls, asha_visits: visits } }).then(setPlan); }, 200);
    return () => clearTimeout(t);
  }, [calls, visits, tick]);
  useEffect(() => {
    const t = setTimeout(() => { api<SimRes>("/api/planner/simulate", { body: { extra_asha: extra, sms_two_way_pct: sms / 100, transport_support: transport, days: 30 } }).then(setSim); }, 300);
    return () => clearTimeout(t);
  }, [extra, sms, transport, tick]);

  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-bold">Impact &amp; planner</h1>
        <p className="max-w-3xl text-sm text-ink3">First, the evidence: does working the list move the needle, and how much survives if our assumptions are wrong? Then the tools: who gets which action today, and "what if we had more capacity?".</p></div>

      <Impact />

      <Card eyebrow="Capacity-constrained optimizer" title="Today's best use of limited effort" right={<Chip tone="sky">Integer programme (scipy MILP)</Chip>}>
        <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
          <div className="space-y-4">
            <Slider label="Calls available today" value={calls} min={0} max={80} onChange={setCalls} />
            <Slider label="ASHA field visits today" value={visits} min={0} max={25} onChange={setVisits} />
            {plan ? (
              <div className="rounded-xl bg-teal-soft/60 p-4">
                <div className="eyebrow">Expected extra loops closed (14 days)</div>
                <div className="num text-4xl font-semibold text-teal-deep">{plan.expected_extra_closures.toFixed(1)}</div>
                <div className="mt-1 text-sm text-ink2">vs <span className="num font-semibold">{plan.fcfs_extra_closures.toFixed(1)}</span> if effort goes first-come-first-served
                  {plan.improvement_vs_fcfs_pct != null && <b className="ml-1 text-teal">(+{plan.improvement_vs_fcfs_pct}%)</b>}</div>
                <div className="mt-2 text-xs text-ink3">{plan.candidates} cases with a gap · solver: {plan.solver}</div>
              </div>) : <Loading />}
            <p className="text-xs text-ink3">{plan?.assumption_note}</p>
          </div>
          <div className="min-w-0">
            {!plan ? <Loading /> : (
              <div className="max-h-[430px] overflow-y-auto rounded-xl border border-line">
                <table className="w-full text-left text-sm">
                  <thead className="sticky top-0 bg-card"><tr className="border-b border-line text-xs uppercase tracking-wide text-ink3"><th className="px-3 py-2">Patient</th><th className="px-2">Action</th><th className="px-2">Why</th><th className="px-3 text-right">Gain</th></tr></thead>
                  <tbody>{plan.plan.slice(0, 40).map((p) => {
                    const a = ACT[p.action as keyof typeof ACT]; const Icon = a.icon;
                    return (<tr key={p.id} className="border-b border-line/60 hover:bg-mist/60">
                      <td className="px-3 py-2"><button className="text-left font-bold text-ink hover:underline" onClick={() => { select(p.id); go("worklist"); }}>{p.patient.name}</button>
                        <div className="text-xs text-ink3">{p.patient.village} · {p.urgency === "HIGH" ? "Urgent" : "Routine"}</div></td>
                      <td className="px-2"><span className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-bold ${a.tone}`}><Icon className="h-3.5 w-3.5" aria-hidden />{a.label}</span></td>
                      <td className="px-2 text-ink2">{p.headline_gap}{p.barrier_label && <span className="ml-1 text-ink3">· {p.barrier_label}</span>}</td>
                      <td className="num px-3 text-right font-semibold">+{(p.expected_gain * 100).toFixed(0)}%<span className={`ml-2 inline-block h-2 w-2 rounded-full align-middle ${bucketStyle(p.bucket).bar}`} aria-label={p.bucket} /></td></tr>);
                  })}</tbody>
                </table>
              </div>)}
          </div>
        </div>
      </Card>

      <Card eyebrow="What-if simulator" title="What happens in 30 days if we change the programme?" right={<Chip tone="amber"><FlaskConical className="h-3 w-3" aria-hidden />Scenario analysis, not a forecast</Chip>}>
        <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
          <div className="space-y-4">
            <Slider label="Extra ASHA workers" value={extra} min={0} max={8} onChange={setExtra} suffix="" />
            <Slider label="Patients using two-way WhatsApp" value={sms} min={0} max={100} onChange={setSms} suffix="%" />
            <label className="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border border-line bg-card px-3 font-bold"><input type="checkbox" checked={transport} onChange={(e) => setTransport(e.target.checked)} className="h-5 w-5 accent-teal" />Fund transport support</label>
            {sim ? (
              <div className="rounded-xl bg-teal-soft/60 p-4"><div className="eyebrow">Extra loops closed vs today's plan</div>
                <div className="num text-4xl font-semibold text-teal-deep">{sim.extra_closures >= 0 ? "+" : ""}{sim.extra_closures}</div>
                <div className="text-sm text-ink2">{sim.baseline.final_mean} → <b>{sim.scenario.final_mean}</b> closures from {sim.open_journeys} open cases</div></div>) : <Loading />}
            <p className="text-xs text-ink3">{sim?.assumption_note} Uses the same editable prior effects as the optimizer.</p>
          </div>
          <div className="min-w-0">
            {sim && (
              <LineChart ariaLabel="Cumulative loops closed over 30 days: baseline versus scenario" xMax={30} yMax={Math.max(20, Math.ceil(Math.max(...sim.scenario.p95, ...sim.baseline.p95) / 20) * 20)}
                xLabel="Days from today" yLabel="Cumulative loops closed" band={sim.scenario.days.map((d, i) => ({ x: d, lo: sim.scenario.p05[i], hi: sim.scenario.p95[i] }))}
                series={[{ name: "Baseline", color: "var(--color-ink3)", dashed: true, points: sim.baseline.days.map((d, i) => ({ x: d, y: sim.baseline.mean[i] })) },
                  { name: "Scenario", color: "var(--color-teal)", points: sim.scenario.days.map((d, i) => ({ x: d, y: sim.scenario.mean[i] })) }]} />)}
            <p className="mt-1 text-xs text-ink3">Shaded band: 5th–95th percentile of 200 Monte Carlo runs for the scenario.</p>
          </div>
        </div>
      </Card>
    </div>
  );
}

function Slider({ label, value, min, max, onChange, suffix = "" }: { label: string; value: number; min: number; max: number; onChange: (n: number) => void; suffix?: string }) {
  return (
    <label className="block"><div className="flex items-baseline justify-between"><span className="text-sm font-bold">{label}</span><span className="num text-lg font-semibold text-teal-deep">{value}{suffix}</span></div>
      <input type="range" min={min} max={max} value={value} onChange={(e) => onChange(Number(e.target.value))} className="mt-1 h-8 w-full accent-teal" /></label>
  );
}
