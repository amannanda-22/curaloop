import type { Role } from "./types";

let currentRole: Role = "coordinator";
export const setApiRole = (r: Role) => { currentRole = r; };

// Secure mode: bearer token kept in sessionStorage (cleared when the tab closes).
const TK = "curaloop.token";
export const getToken = (): string | null => { try { return sessionStorage.getItem(TK); } catch { return null; } };
export const setToken = (t: string | null) => { try { t ? sessionStorage.setItem(TK, t) : sessionStorage.removeItem(TK); } catch { /* private mode */ } };

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown; role?: Role } = {}): Promise<T> {
  const res = await fetch(path, {
    method: opts.method ?? (opts.body !== undefined ? "POST" : "GET"),
    headers: { "Content-Type": "application/json", "X-Role": opts.role ?? currentRole,
      ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}) },
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 401 && getToken()) { setToken(null); window.dispatchEvent(new Event("curaloop:signout")); }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : Array.isArray(j.detail) ? j.detail.map((d: any) => d.msg).join("; ") : msg;
    } catch { /* ignore */ }
    throw new ApiError(res.status, msg);
  }
  return res.json();
}
