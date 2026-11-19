import type { ReactNode } from "react";
import type { RingSeg } from "../types";

const polar = (c: number, r: number, deg: number) => {
  const a = ((deg - 90) * Math.PI) / 180;
  return [c + r * Math.cos(a), c + r * Math.sin(a)];
};
const arc = (c: number, r: number, s: number, e: number) => {
  const [x1, y1] = polar(c, r, s);
  const [x2, y2] = polar(c, r, e);
  return `M${x1.toFixed(2)} ${y1.toFixed(2)} A${r} ${r} 0 ${e - s > 180 ? 1 : 0} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`;
};

const COLOR: Record<string, string> = {
  done: "var(--color-teal)", current: "var(--color-ink)", stuck: "var(--color-signal)",
  todo: "var(--color-line)", lost: "var(--color-ink3)",
};

/** CuraLoop's signature mark: six segments = six stages of the care loop. A red, pulsing segment is where the patient is stuck. */
export default function LoopRing({ segments, size = 44, stroke, children, label }: { segments: RingSeg[]; size?: number; stroke?: number; children?: ReactNode; label?: string }) {
  const w = stroke ?? Math.max(3, Math.round(size / 11));
  const c = size / 2;
  const r = c - w;
  const desc = segments.map((s) => `${s.label}: ${s.status === "stuck" ? "stuck" : s.status}`).join(", ");
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} role="img" aria-label={label ?? `Care loop progress. ${desc}`}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden>
        {segments.map((s, i) => (
          <path key={s.state} d={arc(c, r, i * 60 + 5, i * 60 + 55)} fill="none" stroke={COLOR[s.status]} strokeWidth={s.status === "current" || s.status === "stuck" ? w + 1.5 : w}
            strokeLinecap="round" className={s.status === "stuck" ? "pulse" : undefined} />
        ))}
      </svg>
      {children && <div className="absolute inset-0 flex flex-col items-center justify-center text-center leading-none">{children}</div>}
    </div>
  );
}
