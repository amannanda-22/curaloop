import type { Process, ProcEdge } from "../types";

const LABEL: Record<string, string> = { SCREENED: "Screened", REFERRED: "Referred", CONTACTED: "Reached", SCHEDULED: "Booked", ATTENDED: "Attended", CLOSED: "Closed", LOST: "Lost" };
const ORDER = ["SCREENED", "REFERRED", "CONTACTED", "SCHEDULED", "ATTENDED", "CLOSED"];

/** Process map discovered from the event log: node = state, edge thickness = patients, red = bottleneck / rework / loss. */
export default function ProcessMap({ data }: { data: Process }) {
  const W = 780, H = 330, nodeW = 82, nodeH = 52, y = 150, gap = (W - 40 - nodeW) / 5;
  const x = (s: string) => 20 + ORDER.indexOf(s) * gap;
  const lostX = W / 2 - nodeW / 2, lostY = 262;
  const maxC = Math.max(...data.edges.map((e) => e.count), 1);
  const w = (c: number) => 2 + (c / maxC) * 5;
  const count = (s: string) => data.nodes.find((n) => n.state === s)?.count ?? 0;
  const bn = data.bottleneck;
  const isBn = (e: ProcEdge) => bn && e.from === bn.from && e.to === bn.to;

  const edgeEls = data.edges.map((e) => {
    const key = `${e.from}-${e.to}`;
    const bottle = isBn(e);
    const color = bottle ? "var(--color-signal)" : e.back_edge ? "var(--color-amber)" : e.to === "LOST" ? "var(--color-ink3)" : "var(--color-teal)";
    if (e.to === "LOST") {
      const sx = x(e.from) + nodeW / 2, sy = y + nodeH;
      const ex = lostX + nodeW / 2 + (sx < W / 2 ? -14 : 14) + (ORDER.indexOf(e.from) - 2) * 3, ey = lostY;
      return <g key={key}><path d={`M${sx} ${sy} C${sx} ${sy + 60}, ${ex} ${ey - 60}, ${ex} ${ey}`} fill="none" stroke={color} strokeWidth={Math.max(1.5, w(e.count) * 0.6)} strokeDasharray="5 4" opacity=".7" />
        <text x={(sx + ex) / 2 + (sx < W / 2 ? -6 : 6)} y={(sy + ey) / 2 + 4} textAnchor={sx < W / 2 ? "end" : "start"} className="num" fontSize="11" fill="var(--color-ink2)">{e.count}</text></g>;
    }
    if (e.back_edge) {
      const sx = x(e.from) + nodeW / 2, ex = x(e.to) + nodeW / 2, top = y - 8;
      return <g key={key}><path d={`M${sx} ${top} C${sx} ${top - 70}, ${ex} ${top - 70}, ${ex} ${top}`} fill="none" stroke={color} strokeWidth={Math.max(1.5, w(e.count) * 0.7)} markerEnd="url(#arrow-a)" />
        <text x={(sx + ex) / 2} y={top - 52} textAnchor="middle" fontSize="12" fontWeight="700" fill="var(--color-amber)">rework loop · {e.count}</text></g>;
    }
    const adjacent = ORDER.indexOf(e.to) - ORDER.indexOf(e.from) === 1;
    if (!adjacent) return null;
    const sx = x(e.from) + nodeW, ex = x(e.to), cy = y + nodeH / 2;
    return <g key={key}><line x1={sx} y1={cy} x2={ex - 2} y2={cy} stroke={color} strokeWidth={w(e.count)} strokeLinecap="butt" markerEnd={bottle ? "url(#arrow-r)" : "url(#arrow-t)"} />
      <text x={(sx + ex) / 2} y={cy - 16} textAnchor="middle" className="num" fontSize="11" fontWeight="600" fill="var(--color-ink)">{e.count}</text>
      <text x={(sx + ex) / 2} y={cy + 26} textAnchor="middle" className="num" fontSize="11" fill={bottle ? "var(--color-signal)" : "var(--color-ink3)"} fontWeight={bottle ? 700 : 400}>{e.median_days}d</text></g>;
  });

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`Process map. ${bn ? `Bottleneck: ${LABEL[bn.from]} to ${LABEL[bn.to]}, median ${bn.median_days} days.` : ""}`}>
        <defs>
          {[["t", "var(--color-teal)"], ["r", "var(--color-signal)"], ["a", "var(--color-amber)"]].map(([id, c]) => (
            <marker key={id} id={`arrow-${id}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="3.2" markerHeight="3.2" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill={c} /></marker>))}
        </defs>
        {edgeEls}
        {ORDER.map((s) => (
          <g key={s}><rect x={x(s)} y={y} width={nodeW} height={nodeH} rx="12" fill="var(--color-card)" stroke={s === "CLOSED" ? "var(--color-moss)" : "var(--color-ink)"} strokeWidth="2" />
            <text x={x(s) + nodeW / 2} y={y + 22} textAnchor="middle" fontSize="13" fontWeight="700" fill="var(--color-ink)">{LABEL[s]}</text>
            <text x={x(s) + nodeW / 2} y={y + 41} textAnchor="middle" className="num" fontSize="13" fill="var(--color-ink2)">{count(s)}</text></g>))}
        <g><rect x={lostX} y={lostY} width={nodeW} height={nodeH} rx="12" fill="var(--color-mist)" stroke="var(--color-ink3)" strokeWidth="2" strokeDasharray="5 4" />
          <text x={lostX + nodeW / 2} y={lostY + 22} textAnchor="middle" fontSize="13" fontWeight="700" fill="var(--color-ink2)">Lost</text>
          <text x={lostX + nodeW / 2} y={lostY + 41} textAnchor="middle" className="num" fontSize="13" fill="var(--color-ink2)">{count("LOST")}</text></g>
      </svg>
      <ul className="mt-1 flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink2">
        <li><span className="mr-1.5 inline-block h-1.5 w-6 rounded bg-teal align-middle" />ideal path (thickness = patients; days = median wait)</li>
        <li><span className="mr-1.5 inline-block h-1.5 w-6 rounded bg-signal align-middle" />bottleneck</li>
        <li><span className="mr-1.5 inline-block h-1.5 w-6 rounded bg-amber align-middle" />rework (no-show → reschedule)</li>
        <li><span className="mr-1.5 inline-block h-0 w-6 border-t-2 border-dashed border-ink3 align-middle" />lost</li>
      </ul>
    </div>
  );
}
