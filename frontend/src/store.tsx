import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, ApiError, setApiRole } from "./api";
import type { Clock, Meta, Role } from "./types";

export type Screen = "worklist" | "outreach" | "facility" | "insights" | "planner" | "audit";
export interface Toast { id: number; kind: "ok" | "err" | "info"; text: string }

interface Store {
  role: Role; setRole: (r: Role) => void;
  meta: Meta | null; clock: Clock | null;
  tick: number; bump: () => void;
  selectedId: number | null; select: (id: number | null) => void;
  screen: Screen; go: (s: Screen) => void;
  toasts: Toast[]; toast: (kind: Toast["kind"], text: string) => void;
  run: <T>(fn: () => Promise<T>, okMsg?: string) => Promise<T | undefined>;
  busy: boolean; secure: boolean; signOut: () => void;
  reloadMeta: () => Promise<void>;
}
const Ctx = createContext<Store>(null as unknown as Store);
export const useStore = () => useContext(Ctx);

export function StoreProvider({ children, initialRole = "coordinator", secure = false, signOut = () => {} }: { children: ReactNode; initialRole?: Role; secure?: boolean; signOut?: () => void }) {
  const [role, setRoleState] = useState<Role>(initialRole);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [clock, setClock] = useState<Clock | null>(null);
  const [tick, setTick] = useState(0);
  const [selectedId, select] = useState<number | null>(null);
  const [screen, go] = useState<Screen>("worklist");
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [busy, setBusy] = useState(false);
  const nextId = useRef(1);

  const setRole = useCallback((r: Role) => { setApiRole(r); setRoleState(r); }, []);
  const bump = useCallback(() => setTick((t) => t + 1), []);
  const toast = useCallback((kind: Toast["kind"], text: string) => {
    const id = nextId.current++;
    setToasts((t) => [...t.slice(-3), { id, kind, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === "err" ? 7000 : 3800);
  }, []);

  const reloadMeta = useCallback(async () => {
    const m = await api<Meta>("/api/meta");
    setMeta(m);
    if (m.hero_journey_id) select(m.hero_journey_id);
  }, []);
  useEffect(() => { reloadMeta(); }, [reloadMeta]);
  useEffect(() => { api<Clock>("/api/clock").then(setClock); }, [tick]);

  const run = useCallback(async <T,>(fn: () => Promise<T>, okMsg?: string) => {
    setBusy(true);
    try {
      const r = await fn();
      if (okMsg) toast("ok", okMsg);
      bump();
      return r;
    } catch (e) {
      toast("err", e instanceof ApiError ? e.message : "Something went wrong. Is the API running?");
      return undefined;
    } finally { setBusy(false); }
  }, [toast, bump]);

  const value = useMemo(() => ({ role, setRole, meta, clock, tick, bump, selectedId, select, screen, go, toasts, toast, run, busy, secure, signOut, reloadMeta }),
    [role, setRole, meta, clock, tick, bump, selectedId, screen, toasts, toast, run, busy, secure, signOut, reloadMeta]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useFetch<T>(path: string | null, deps: unknown[] = []) {
  const { tick } = useStore();
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!path) return;
    let live = true;
    setLoading(true);
    api<T>(path).then((d) => { if (live) { setData(d); setError(null); } })
      .catch((e) => { if (live) setError(e.message); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, tick, ...deps]);
  return { data, loading, error };
}
