export const fmtDate = (iso: string) =>
  new Date(iso + (iso.endsWith("Z") ? "" : "Z")).toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "UTC" });
export const fmtDateTime = (iso: string) =>
  new Date(iso + (iso.endsWith("Z") ? "" : "Z")).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "UTC", hour12: false });
export const fmtLong = (iso: string) =>
  new Date(iso + (iso.endsWith("Z") ? "" : "Z")).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
export const ago = (iso: string, now: string) => {
  const d = (new Date(now + "Z").getTime() - new Date(iso + "Z").getTime()) / 86400000;
  if (d < 0) return `in ${Math.abs(d).toFixed(0)}d`;
  if (d < 1 / 24) return "just now";
  if (d < 1) return `${Math.round(d * 24)}h ago`;
  return `${Math.round(d)}d ago`;
};
export const cx = (...a: (string | false | null | undefined)[]) => a.filter(Boolean).join(" ");
export const pct = (n: number | null | undefined, d = 0) => (n == null ? "-" : `${n.toFixed(d)}%`);
