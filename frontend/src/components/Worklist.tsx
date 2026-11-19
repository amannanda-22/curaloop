import { useState } from "react";
import { Search } from "lucide-react";
import { useFetch, useStore } from "../store";
import type { Worklist as WL } from "../types";
import { cx } from "../util";
import { BucketBadge, Chip, Empty, Loading, bucketStyle } from "./ui";
import LoopRing from "./LoopRing";
import JourneyPanel from "./JourneyPanel";

const FILTERS = [["", "All"], ["critical", "Critical"], ["high", "High"], ["medium", "Medium"], ["low", "Low"]] as const;

export default function Worklist() {
  const { selectedId, select, meta } = useStore();
  const [bucket, setBucket] = useState("");
  const [q, setQ] = useState("");
  const { data, loading } = useFetch<WL>(`/api/worklist?limit=80${bucket ? `&bucket=${bucket}` : ""}${q ? `&q=${encodeURIComponent(q)}` : ""}`);

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(380px,460px)_1fr]">
      <div>
        <div className="mb-3">
          <h1 className="text-2xl font-bold">Today's worklist</h1>
          <p className="text-sm text-ink3">Ranked by why-it-matters. Open a case to see the reason and the suggested next step.</p>
        </div>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          {FILTERS.map(([k, label]) => (
            <button key={k} onClick={() => setBucket(k)} aria-pressed={bucket === k}
              className={cx("min-h-9 rounded-lg border px-3 text-sm font-bold transition-colors", bucket === k ? "border-ink bg-ink text-paper" : "border-line bg-card text-ink2 hover:bg-mist")}>
              {label}{data && k && <span className="num ml-1.5 opacity-80">{data.counts[k] ?? 0}</span>}
              {data && !k && <span className="num ml-1.5 opacity-80">{Object.values(data.counts).reduce((a, b) => a + b, 0)}</span>}
            </button>
          ))}
        </div>
        <label className="relative mb-3 block">
          <span className="sr-only">Search patient or village</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink3" aria-hidden />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name or village"
            className="min-h-10 w-full rounded-lg border border-line bg-card pl-9 pr-3 text-sm" />
        </label>
        {loading && !data ? <Loading /> : !data || data.items.length === 0 ? <Empty title="Nothing needs attention" hint="Every open journey is within its SLA." /> : (
          <ul className="max-h-[calc(100vh-290px)] space-y-2 overflow-y-auto pr-1">
            {[...data.items].sort((a, b) => Number(b.id === meta?.hero_journey_id) - Number(a.id === meta?.hero_journey_id)).map((c, i) => {
              const sel = c.id === selectedId;
              const s = bucketStyle(c.bucket);
              return (
                <li key={c.id} className="rise" style={{ animationDelay: `${Math.min(i, 8) * 25}ms` }}>
                  <button onClick={() => select(c.id)} aria-current={sel}
                    className={cx("group relative flex w-full items-center gap-3 overflow-hidden rounded-xl border p-3 text-left transition-colors",
                      sel ? "border-teal bg-teal-soft/50 shadow-sm" : "border-line bg-card hover:border-ink3")}>
                    <span className={cx("absolute inset-y-0 left-0 w-1", s.bar)} aria-hidden />
                    <LoopRing segments={c.ring} size={46}>
                      <span className="num text-[13px] font-semibold">{Math.round(c.age_in_state_days)}d</span>
                    </LoopRing>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="truncate font-bold">{c.patient.name}</span>
                        <span className="text-xs text-ink3">{c.patient.age}{c.patient.sex}</span>
                        {c.id === meta?.hero_journey_id && <Chip tone="teal">Demo patient</Chip>}
                      </div>
                      <div className="truncate text-sm text-ink2">{c.gaps[0]?.label ?? "Ready for referral"}</div>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-ink3">
                        <span>{c.state_label}</span><span aria-hidden>·</span><span>{c.patient.village}</span>
                        {c.urgency === "HIGH" && <Chip tone="signal">Urgent</Chip>}
                        {c.barrier_label && <Chip tone="amber">{c.barrier_label}</Chip>}
                        {c.clinical_flag && <Chip tone="signal">Clinician needed</Chip>}
                      </div>
                    </div>
                    <BucketBadge bucket={c.bucket} score={c.score} />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      <div className="min-w-0">{selectedId ? <JourneyPanel id={selectedId} /> : <Empty title="Select a case" />}</div>
    </div>
  );
}
