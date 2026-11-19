import { AlertTriangle, CheckCircle2, Info } from "lucide-react";
import { useFetch } from "../store";
import type { FacRes, Fairness, Funnel, Patterns, Process, Summary, SurvivalRes } from "../types";
import { cx, pct } from "../util";
import { Card, Chip, Loading, Stat } from "./ui";
import { HBar, LineChart, stageColor } from "./charts";
import ProcessMap from "./ProcessMap";

const STRATA_COLOR = ["var(--color-teal)", "var(--color-amber)", "var(--color-signal)"];

export default function Insights() {
  const { data: s } = useFetch<Summary>("/api/insights/summary");
  const { data: f } = useFetch<Funnel>("/api/insights/funnel");
  const { data: pm } = useFetch<Process>("/api/insights/process");
  const { data: sv } = useFetch<SurvivalRes>("/api/insights/survival?by=distance");
  const { data: pt } = useFetch<Patterns>("/api/insights/patterns");
  const { data: fr } = useFetch<Fairness>("/api/insights/fairness");
  const { data: fc } = useFetch<FacRes>("/api/insights/facilities");

  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-bold">Where the loop leaks</h1>
        <p className="max-w-3xl text-sm text-ink3">Not a wall of counts. Each panel answers one question: where do patients fall out, how long do they wait, and who is being missed.</p></div>

      {s ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
          <Stat label="Flagged" value={s.patients_flagged} />
          <Stat label="Referral rate" value={pct(s.referral_rate_pct)} />
          <Stat label="Loops closed" value={pct(s.loop_closure_rate_pct)} tone="teal" sub={`${s.loops_closed} patients`} />
          <Stat label="Missed appts" value={pct(s.missed_appointment_rate_pct)} tone="signal" />
          <Stat label="Avg referral delay" value={s.avg_referral_delay_days != null ? `${s.avg_referral_delay_days}d` : "-"} />
          <Stat label="Median to close" value={s.median_days_to_close != null ? `${s.median_days_to_close}d` : "-"} />
          <Stat label="Open with gaps" value={s.open_with_gaps} tone="signal" sub={`${s.critical} critical`} />
          <Stat label="Lost" value={s.lost} sub="closed by manager" />
        </div>
      ) : <Loading />}

      <div className="grid gap-5 xl:grid-cols-2">
        <Card eyebrow="Leakage funnel" title="Screened → loop closed" right={f?.biggest_leak && <Chip tone="signal"><AlertTriangle className="h-3 w-3" aria-hidden />Biggest leak: {f.biggest_leak.label}</Chip>}>
          {!f ? <Loading /> : (
            <ol className="space-y-1.5">
              {f.stages.map((st, i) => (
                <li key={st.state}>
                  {i > 0 && <div className={cx("num ml-2 border-l-2 py-0.5 pl-3 text-xs", f.biggest_leak?.state === st.state ? "border-signal font-bold text-signal" : "border-line text-ink3")}>
                    −{st.dropped} fell out · {(100 - st.pct_of_prev).toFixed(0)}% of previous stage</div>}
                  <div className="flex items-center gap-3">
                    <div className="w-32 shrink-0 text-sm font-bold">{st.label}</div>
                    <div className="h-9 flex-1 overflow-hidden rounded-lg bg-mist"><div className="flex h-full items-center rounded-lg px-3 text-sm font-semibold text-white" style={{ width: `${st.pct_of_start}%`, minWidth: 44, background: stageColor(i, f.stages.length) }}><span className="num">{st.count}</span></div></div>
                    <div className="num w-12 text-right text-sm text-ink2">{st.pct_of_start.toFixed(0)}%</div>
                  </div>
                </li>))}
            </ol>
          )}
        </Card>

        <Card eyebrow="Time to closure" title="Closure curve by distance to facility" right={<Chip>Kaplan-Meier · open cases censored</Chip>}>
          {!sv ? <Loading /> : (<>
            <LineChart ariaLabel="Share of referrals closed over time, by distance band" xMax={sv.max_day} yMax={1} xLabel="Days since screening" yLabel="Loops closed" yFmt={(v) => `${Math.round(v * 100)}%`}
              series={sv.strata.map((st, i) => ({ name: st.name, color: STRATA_COLOR[i % 3], points: st.curve.map((p) => ({ x: p.day, y: p.closed })) }))} />
            <div className="mt-2 grid grid-cols-3 gap-2 text-center text-sm">
              {sv.strata.map((st, i) => <div key={st.name} className="rounded-lg bg-mist px-2 py-1.5"><div className="font-bold" style={{ color: STRATA_COLOR[i % 3] }}>{st.name}</div><div className="num">{st.closed_by_day_30_pct}% by day 30</div><div className="text-xs text-ink3">n = {st.n}</div></div>)}
            </div>
          </>)}
        </Card>
      </div>

      <Card eyebrow="Process mining" title="How patients actually move (discovered from the event log)"
        right={pm && <div className="flex flex-wrap gap-1.5"><Chip tone="teal">{pm.conformance.fitness_pct}% follow the ideal path</Chip><Chip tone="amber">{pm.conformance.with_rework_loops} with rework loops</Chip><Chip>{pm.conformance.ended_lost} lost</Chip></div>}>
        {!pm ? <Loading /> : (<>
          <ProcessMap data={pm} />
          {pm.bottleneck && <p className="mt-3 rounded-lg bg-signal-soft px-3 py-2 text-sm font-bold text-signal">Bottleneck: {pm.bottleneck.from.toLowerCase()} → {pm.bottleneck.to.toLowerCase()} · median {pm.bottleneck.median_days} days across {pm.bottleneck.count} patients ({pm.bottleneck.total_wait_days} patient-days of waiting).</p>}
          <details className="mt-3"><summary className="min-h-9 cursor-pointer text-sm font-bold text-teal">Most common paths (variants)</summary>
            <ul className="mt-2 space-y-1 text-sm">{pm.variants.map((v) => <li key={v.path} className="flex justify-between gap-4 border-b border-line/70 py-1"><span className="text-ink2">{v.path.split(" > ").map((p) => p[0] + p.slice(1).toLowerCase()).join(" → ")}</span><span className="num font-semibold">{v.count}</span></li>)}</ul></details>
        </>)}
      </Card>

      <div className="grid gap-5 xl:grid-cols-2">
        <Card eyebrow="Does the analysis find real structure?" title="Planted-pattern recovery" right={<Chip tone="sky"><Info className="h-3 w-3" aria-hidden />Synthetic data</Chip>}>
          {!pt ? <Loading /> : (<>
            <p className="mb-3 text-sm text-ink2">The data generator planted two drop-off effects. If the pipeline works it should recover them. Cohort: {pt.cohort_size} referrals opened 60+ days ago.</p>
            <ul className="space-y-3">{pt.checks.map((c) => (
              <li key={c.name} className="rounded-xl border border-line p-3">
                <div className="flex flex-wrap items-center justify-between gap-2"><b>{c.name}</b>
                  <Chip tone={c.status === "recovered" ? "moss" : "amber"}>{c.status === "recovered" ? <CheckCircle2 className="h-3 w-3" aria-hidden /> : <AlertTriangle className="h-3 w-3" aria-hidden />}{c.status}</Chip></div>
                <div className="mt-2 grid grid-cols-3 gap-2 text-center">
                  <div><div className="eyebrow">Planted</div><div className="num text-xl font-semibold">{c.planted?.toFixed(1)}×</div></div>
                  <div><div className="eyebrow">Recovered</div><div className="num text-xl font-semibold text-teal">{c.recovered.rr?.toFixed(2)}×</div></div>
                  <div><div className="eyebrow">95% CI</div><div className="num text-xl font-semibold">{c.recovered.lo?.toFixed(1)}–{c.recovered.hi?.toFixed(1)}</div></div>
                </div>
                <div className="mt-2 text-xs text-ink3">Drop-off {c.group_a}: <span className="num">{c.rate_a_pct}%</span> vs {c.group_b}: <span className="num">{c.rate_b_pct}%</span></div>
              </li>))}</ul>
            <p className="mt-3 text-xs text-ink3">{pt.note}</p>
          </>)}
        </Card>

        <Card eyebrow="Fairness audit" title="Who is being missed?" right={fr && <Chip>{fr.cohort_size} referrals</Chip>}>
          {!fr ? <Loading /> : (<>
            {fr.groups.map((g) => (
              <div key={g.dimension} className="mb-4 last:mb-0">
                <div className="eyebrow mb-1">{g.dimension}</div>
                <ul className="space-y-1.5">{g.rows.map((r) => (
                  <li key={r.group} className="grid grid-cols-[96px_1fr_auto] items-center gap-3 text-sm">
                    <span className="font-semibold">{r.group}</span>
                    <HBar value={r.closure_rate_pct} max={100} color={r.flag ? "var(--color-signal)" : "var(--color-teal)"} label={`${r.group} closure ${r.closure_rate_pct}%`} />
                    <span className="num flex items-center gap-2">{r.closure_rate_pct}% <span className="text-xs text-ink3">n={r.n}</span>{r.flag && <Chip tone="signal">Investigate</Chip>}</span>
                  </li>))}</ul>
              </div>))}
            <p className="text-xs text-ink3">{fr.rule}</p>
          </>)}
        </Card>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.6fr_1fr]">
        <Card eyebrow="Accountability by facility" title="Who closes the loop, and how fast">
          {!fc ? <Loading /> : (
            <div className="overflow-x-auto"><table className="w-full min-w-[640px] text-left text-sm">
              <thead><tr className="border-b border-line text-xs uppercase tracking-wide text-ink3"><th className="py-2 pr-2">Facility</th><th className="px-2 text-right">Referred</th><th className="px-2 text-right">Closed</th><th className="px-2 text-right">Lost</th><th className="px-2 text-right">Open</th><th className="px-2 text-right">Closure</th><th className="px-2 text-right">Median days</th><th className="pl-2 text-right">Awaiting outcome</th></tr></thead>
              <tbody>{fc.facilities.map((r) => (
                <tr key={r.facility_id} className="border-b border-line/60">
                  <td className="py-2 pr-2 font-bold">{r.name}</td><td className="num px-2 text-right">{r.referred}</td><td className="num px-2 text-right">{r.closed}</td><td className="num px-2 text-right">{r.lost}</td><td className="num px-2 text-right">{r.open}</td>
                  <td className="num px-2 text-right font-semibold">{r.closure_rate_pct}%</td><td className="num px-2 text-right">{r.median_days_to_close ?? "-"}</td>
                  <td className="pl-2 text-right">{r.awaiting_outcome > 0 ? <Chip tone="amber">{r.awaiting_outcome}</Chip> : <span className="num text-ink3">0</span>}</td></tr>))}</tbody>
            </table></div>)}
        </Card>
        <Card eyebrow="Reasons patients give" title="Top barriers">
          {!fc ? <Loading /> : fc.barriers.length === 0 ? <p className="text-ink2">No barriers logged yet.</p> : (
            <ul className="space-y-2.5">{fc.barriers.map((b) => (
              <li key={b.code} className="grid grid-cols-[1fr_auto] items-center gap-3"><div><div className="mb-1 text-sm font-bold">{b.label}</div><HBar value={b.count} max={fc.barriers[0].count} color="var(--color-amber)" label={`${b.label}: ${b.count}`} /></div><span className="num text-lg font-semibold">{b.count}</span></li>))}</ul>)}
        </Card>
      </div>
    </div>
  );
}
