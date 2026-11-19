import { useEffect, useState } from "react";
import { BookOpenCheck, Scale } from "lucide-react";
import { api } from "../api";
import { useStore } from "../store";
import { Card, Chip, Loading } from "./ui";
import { LineChart } from "./charts";

interface ImpactRes {
  open_cases: number; days: number;
  closed_by_day: { status_quo: number; manual: number; curaloop: number };
  gain_vs_status_quo: { mean: number; lo: number; hi: number };
  gain_vs_manual: { mean: number; lo: number; hi: number };
  recovery_share: number;
  sensitivity: { scale: number; gain_mean: number; gain_lo: number }[];
  curves: { days: number[]; status_quo: number[]; manual: number[]; curaloop: number[] };
  projection: { annual_screen_positive: number; baseline_closure: number; rows: { effect_scale: number; recovery_share: number; extra_reaching_care: number; closure_after: number }[] };
  evidence: { id: string; claim: string; cite: string; url: string }[];
  honesty: string[];
}

export default function Impact() {
  const { tick } = useStore();
  const [annual, setAnnual] = useState(10000);
  const [base, setBase] = useState(55);
  const [d, setD] = useState<ImpactRes | null>(null);
  useEffect(() => {
    const t = setTimeout(() => { api<ImpactRes>(`/api/impact?annual_screen_positive=${annual}&baseline_closure=${base / 100}`).then(setD); }, 350);
    return () => clearTimeout(t);
  }, [annual, base, tick]);

  if (!d) return <Card eyebrow="Impact model" title="Does working the list actually move the needle?"><Loading label="Running 400 Monte Carlo simulations" /></Card>;
  const yMax = Math.max(10, Math.ceil(Math.max(...d.curves.curaloop) / 10) * 10 + 10);
  const g = d.gain_vs_status_quo, m = d.gain_vs_manual;
  const manualSig = m.lo > 0;
  return (
    <Card eyebrow="Impact model" title="Does working the list actually move the needle?" right={<Chip tone="amber"><Scale className="h-3 w-3" aria-hidden />Synthetic cohort · priors, not measured effects</Chip>}>
      <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
        <div className="min-w-0">
          <LineChart endLabels={false} ariaLabel="Cumulative loops closed over 30 days under three policies" xMax={30} yMax={yMax} xLabel="Days from today" yLabel="Loops closed (of open cases)"
            series={[{ name: "Nobody works the list", color: "var(--color-ink3)", dashed: true, points: d.curves.days.map((x, i) => ({ x, y: d.curves.status_quo[i] })) },
              { name: "Manual register", color: "var(--color-sky)", points: d.curves.days.map((x, i) => ({ x, y: d.curves.manual[i] })) },
              { name: "CuraLoop", color: "var(--color-teal)", points: d.curves.days.map((x, i) => ({ x, y: d.curves.curaloop[i] })) }]} />
          <p className="mt-1 text-xs text-ink3">{d.open_cases} open cases with a gap · same calls and ASHA visits for the last two lines · paired Monte Carlo (common random numbers).</p>
        </div>
        <div className="space-y-3">
          <div className="rounded-xl bg-teal-soft/60 p-4">
            <div className="eyebrow">CuraLoop vs nobody working the list</div>
            <div className="num text-4xl font-semibold text-teal-deep">+{g.mean}</div>
            <div className="text-sm text-ink2">extra loops closed in {d.days} days · 90% range {g.lo} to {g.hi}</div>
          </div>
          <div className="rounded-xl border border-line p-4">
            <div className="eyebrow">CuraLoop vs a manual register</div>
            <div className="num text-2xl font-semibold">{m.mean >= 0 ? "+" : ""}{m.mean} <span className="text-sm font-normal text-ink3">({m.lo} to {m.hi})</span></div>
            <p className="mt-1 text-xs text-ink2">{manualSig ? "Prioritisation adds a measurable edge on top of tracking." :
              "Honest reading: this range includes zero. Most of the value comes from having a closed loop at all; barrier-matched prioritisation helps mainly when capacity is scarce, and the pilot is designed to measure it."}</p>
          </div>
        </div>
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-2">
        <div>
          <h3 className="mb-1 text-base font-bold">"Your priors are made up." Fair. How much survives if they are wrong?</h3>
          <table className="w-full text-left text-sm"><thead><tr className="border-b border-line text-xs uppercase tracking-wide text-ink3"><th className="py-2">If real action lifts are…</th><th className="text-right">Extra closed</th><th className="text-right">Worst-case (5%)</th></tr></thead>
            <tbody>{d.sensitivity.map((r) => (<tr key={r.scale} className="border-b border-line/60"><td className="py-2 font-semibold">{r.scale === 1 ? "as assumed (100%)" : r.scale === 0 ? "zero (no effect)" : `${r.scale * 100}% of assumed`}</td>
              <td className="num text-right font-semibold">+{r.gain_mean}</td><td className="num text-right text-ink2">+{r.gain_lo}</td></tr>))}</tbody></table>
          <p className="mt-2 text-xs text-ink3">Gain scales with effect size and vanishes at zero, so the result is only as good as the lift. That is exactly what the 90-day pilot measures.</p>
        </div>
        <div>
          <h3 className="mb-1 text-base font-bold">District projection <span className="text-sm font-normal text-ink3">(editable)</span></h3>
          <div className="grid grid-cols-2 gap-3">
            <label className="text-sm font-bold">Screen-positives / year
              <input type="number" min={100} max={5000000} step={500} value={annual} onChange={(e) => setAnnual(Math.max(100, Number(e.target.value) || 100))} className="num mt-1 min-h-11 w-full rounded-xl border border-line bg-paper px-3" /></label>
            <label className="text-sm font-bold">Baseline loop closure %
              <input type="number" min={5} max={95} value={base} onChange={(e) => setBase(Math.min(95, Math.max(5, Number(e.target.value) || 5)))} className="num mt-1 min-h-11 w-full rounded-xl border border-line bg-paper px-3" /></label>
          </div>
          <table className="mt-2 w-full text-left text-sm"><thead><tr className="border-b border-line text-xs uppercase tracking-wide text-ink3"><th className="py-2">Effect vs assumed</th><th className="text-right">More people reach care</th><th className="text-right">Closure</th></tr></thead>
            <tbody>{d.projection.rows.filter((r) => r.effect_scale > 0).map((r) => (<tr key={r.effect_scale} className="border-b border-line/60"><td className="py-2 font-semibold">{r.effect_scale * 100}%</td>
              <td className="num text-right font-semibold">+{r.extra_reaching_care.toLocaleString("en-IN")}</td><td className="num text-right text-ink2">{Math.round(d.projection.baseline_closure * 100)}% → {Math.round(r.closure_after * 100)}%</td></tr>))}</tbody></table>
        </div>
      </div>

      <div className="mt-5 grid gap-3 rounded-xl border border-line bg-paper p-4 text-sm lg:grid-cols-2">
        <div><div className="mb-1 flex items-center gap-2 font-bold"><BookOpenCheck className="h-4 w-4 text-teal" aria-hidden />Why the baseline is not invented</div>
          {d.evidence.map((e) => <p key={e.id} className="text-ink2">{e.claim} <a className="font-bold text-teal underline" href={e.url} target="_blank" rel="noreferrer">{e.cite}</a>. One study, one city, one condition: it justifies the problem and the default 55% closure, not our uplift.</p>)}</div>
        <ul className="list-disc space-y-1 pl-5 text-ink2">{d.honesty.map((h) => <li key={h}>{h}</li>)}</ul>
      </div>
    </Card>
  );
}
