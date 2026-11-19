import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { cx } from "../util";
import type { Bucket } from "../types";
import { useStore } from "../store";

const BUCKET: Record<string, { bg: string; fg: string; bar: string; label: string }> = {
  critical: { bg: "bg-signal-soft", fg: "text-signal", bar: "bg-signal", label: "Critical" },
  high: { bg: "bg-amber-soft", fg: "text-amber", bar: "bg-amber", label: "High" },
  medium: { bg: "bg-sky-soft", fg: "text-sky", bar: "bg-sky", label: "Medium" },
  low: { bg: "bg-mist", fg: "text-ink2", bar: "bg-ink3", label: "Low" },
  closed: { bg: "bg-moss-soft", fg: "text-moss", bar: "bg-moss", label: "Closed" },
};
export const bucketStyle = (b: Bucket | string) => BUCKET[b] ?? BUCKET.low;

export function BucketBadge({ bucket, score }: { bucket: Bucket; score?: number }) {
  const s = bucketStyle(bucket);
  return (
    <span className={cx("inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-bold", s.bg, s.fg)}>
      <span className={cx("h-2 w-2 rounded-full", s.bar)} aria-hidden />
      {s.label}{score !== undefined && <span className="num font-semibold"> {score}</span>}
    </span>
  );
}

export function Chip({ children, tone = "mist", title }: { children: ReactNode; tone?: "mist" | "teal" | "signal" | "amber" | "moss" | "sky" | "ink"; title?: string }) {
  const t = {
    mist: "bg-mist text-ink2", teal: "bg-teal-soft text-teal-deep", signal: "bg-signal-soft text-signal",
    amber: "bg-amber-soft text-amber", moss: "bg-moss-soft text-moss", sky: "bg-sky-soft text-sky", ink: "bg-ink text-paper",
  }[tone];
  return <span title={title} className={cx("inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-semibold whitespace-nowrap", t)}>{children}</span>;
}

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "soft" | "ghost" | "danger"; busy?: boolean; size?: "sm" | "md" };
export function Btn({ variant = "soft", busy, size = "md", className, children, disabled, ...p }: BtnProps) {
  const v = {
    primary: "bg-teal text-white hover:bg-teal-deep",
    soft: "bg-teal-soft text-teal-deep hover:bg-[#c3e3dc]",
    ghost: "bg-transparent text-ink2 hover:bg-mist border border-line",
    danger: "bg-signal-soft text-signal hover:bg-[#f4cdb8]",
  }[variant];
  return (
    <button {...p} disabled={disabled || busy}
      className={cx("inline-flex items-center justify-center gap-2 rounded-lg font-bold transition-colors", size === "md" ? "min-h-10 px-4 text-sm" : "min-h-8 px-3 text-xs", v, className)}>
      {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}{children}
    </button>
  );
}

export function Card({ children, className, title, eyebrow, right }: { children: ReactNode; className?: string; title?: ReactNode; eyebrow?: string; right?: ReactNode }) {
  return (
    <section className={cx("rounded-2xl border border-line bg-card p-5 shadow-[0_1px_0_rgba(18,49,58,.04)]", className)}>
      {(title || eyebrow) && (
        <header className="mb-3 flex items-start justify-between gap-3">
          <div>{eyebrow && <div className="eyebrow">{eyebrow}</div>}{title && <h3 className="text-lg font-bold leading-tight text-ink">{title}</h3>}</div>
          {right}
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: "signal" | "teal" | "ink" }) {
  return (
    <div className="rounded-xl border border-line bg-card px-4 py-3">
      <div className="eyebrow">{label}</div>
      <div className={cx("num mt-1 text-[28px] font-semibold leading-none", tone === "signal" ? "text-signal" : tone === "teal" ? "text-teal" : "text-ink")}>{value}</div>
      {sub && <div className="mt-1.5 text-xs text-ink3">{sub}</div>}
    </div>
  );
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return <div className="rounded-xl border border-dashed border-line px-6 py-10 text-center"><div className="font-bold text-ink2">{title}</div>{hint && <div className="mt-1 text-sm text-ink3">{hint}</div>}</div>;
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return <div className="flex items-center gap-2 py-8 text-ink3" role="status"><Loader2 className="h-4 w-4 animate-spin" aria-hidden />{label}…</div>;
}

export function Toasts() {
  const { toasts } = useStore();
  return (
    <div className="pointer-events-none fixed bottom-4 left-1/2 z-50 flex w-[min(92vw,520px)] -translate-x-1/2 flex-col gap-2" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} role={t.kind === "err" ? "alert" : "status"}
          className={cx("rise pointer-events-auto rounded-xl border px-4 py-3 text-sm font-bold shadow-lg",
            t.kind === "err" ? "border-signal/30 bg-signal-soft text-signal" : t.kind === "ok" ? "border-moss/30 bg-moss-soft text-moss" : "border-line bg-card text-ink")}>
          {t.text}
        </div>
      ))}
    </div>
  );
}

export function Select({ value, onChange, children, label, className }: { value: string | number; onChange: (v: string) => void; children: ReactNode; label: string; className?: string }) {
  return (
    <label className={cx("block", className)}>
      <span className="eyebrow">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="mt-1 block min-h-10 w-full rounded-lg border border-line bg-card px-3 text-sm font-semibold text-ink">{children}</select>
    </label>
  );
}
