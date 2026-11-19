import { cx } from "../util";

export interface Series { name: string; color: string; points: { x: number; y: number }[]; dashed?: boolean }
export interface Band { x: number; lo: number; hi: number }

/** Minimal accessible SVG line chart: direct end-labels + legend so colour is never the only cue. */
export function LineChart({ series, band, bandColor = "var(--color-teal)", xMax, yMax, xLabel, yLabel, yFmt = (v: number) => String(Math.round(v)), height = 260, ariaLabel, endLabels = true }:
  { series: Series[]; band?: Band[]; bandColor?: string; xMax: number; yMax: number; xLabel: string; yLabel: string; yFmt?: (v: number) => string; height?: number; ariaLabel: string; endLabels?: boolean }) {
  const W = 640, H = height, m = { l: 54, r: 92, t: 12, b: 38 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const sx = (x: number) => m.l + (x / xMax) * iw;
  const sy = (y: number) => m.t + ih - (y / yMax) * ih;
  const path = (pts: { x: number; y: number }[]) => pts.map((p, i) => `${i ? "L" : "M"}${sx(p.x).toFixed(1)} ${sy(p.y).toFixed(1)}`).join(" ");
  const yt = [0, 0.25, 0.5, 0.75, 1].map((f) => f * yMax);
  const nx = xMax % 3 === 0 ? 3 : 4;
  const xt = Array.from({ length: nx + 1 }, (_, i) => Math.round((xMax / nx) * i));
  const bandPath = band && band.length
    ? `${band.map((b, i) => `${i ? "L" : "M"}${sx(b.x).toFixed(1)} ${sy(b.hi).toFixed(1)}`).join(" ")} ${[...band].reverse().map((b) => `L${sx(b.x).toFixed(1)} ${sy(b.lo).toFixed(1)}`).join(" ")} Z` : "";
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={ariaLabel}>
        {yt.map((v) => (<g key={v}><line x1={m.l} x2={W - m.r} y1={sy(v)} y2={sy(v)} stroke="var(--color-line)" strokeWidth="1" />
          <text x={m.l - 8} y={sy(v) + 4} textAnchor="end" className="num" fontSize="11" fill="var(--color-ink3)">{yFmt(v)}</text></g>))}
        {xt.map((v) => <text key={v} x={sx(v)} y={H - 18} textAnchor="middle" className="num" fontSize="11" fill="var(--color-ink3)">{v}</text>)}
        <text x={m.l + iw / 2} y={H - 3} textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--color-ink3)">{xLabel}</text>
        <text transform={`translate(11 ${m.t + ih / 2}) rotate(-90)`} textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--color-ink3)">{yLabel}</text>
        {bandPath && <path d={bandPath} fill={bandColor} opacity=".14" />}
        {series.map((s) => (<g key={s.name}>
          <path d={path(s.points)} fill="none" stroke={s.color} strokeWidth="2.6" strokeLinejoin="round" strokeLinecap="round" strokeDasharray={s.dashed ? "6 5" : undefined} />
          {endLabels && s.points.length > 0 && <text x={sx(s.points[s.points.length - 1].x) + 8} y={sy(s.points[s.points.length - 1].y) + 4} fontSize="12" fontWeight="700" fill={s.color}>{s.name}</text>}
        </g>))}
      </svg>
      <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink2">
        {series.map((s) => <li key={s.name} className="flex items-center gap-1.5"><svg width="22" height="8" aria-hidden><line x1="0" x2="22" y1="4" y2="4" stroke={s.color} strokeWidth="3" strokeDasharray={s.dashed ? "5 3" : undefined} /></svg>{s.name}</li>)}
      </ul>
    </div>
  );
}

export function HBar({ value, max, color = "var(--color-teal)", label }: { value: number; max: number; color?: string; label?: string }) {
  return <div className="h-2.5 w-full overflow-hidden rounded-full bg-mist" role="img" aria-label={label}><div className="h-full rounded-full" style={{ width: `${Math.max(2, (value / Math.max(max, 1)) * 100)}%`, background: color }} /></div>;
}

export const stageColor = (i: number, n: number) => `color-mix(in srgb, var(--color-teal) ${100 - (i / Math.max(n - 1, 1)) * 45}%, var(--color-ink))`;
export { cx };
