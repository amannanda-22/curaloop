"""Process mining on the journey event log (pure Python, no pm4py dependency).

From the append-only `events` table we discover how patients ACTUALLY move, compare with the
ideal pathway (conformance), and find the bottleneck edge. Same idea Celonis-style tools use on
hospital logs - here small enough to run in-process.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median

from .states import IDEAL_PATH


def traces_from_events(events) -> dict[int, list[tuple[str, object]]]:
    traces: dict[int, list[tuple[str, object]]] = defaultdict(list)
    for e in sorted(events, key=lambda x: (x.ts, x.id)):
        if e.kind == "state" and e.to_state:
            traces[e.journey_id].append((e.to_state, e.ts))
    return traces


def discover(traces: dict[int, list[tuple[str, object]]]) -> dict:
    edge_count: Counter = Counter()
    edge_days: dict[tuple[str, str], list[float]] = defaultdict(list)
    node_count: Counter = Counter()
    variants: Counter = Counter()
    for seq in traces.values():
        states = [s for s, _ in seq]
        for s in set(states):
            node_count[s] += 1
        variants[" > ".join(states)] += 1
        for (a, ta), (b, tb) in zip(seq, seq[1:]):
            edge_count[(a, b)] += 1
            edge_days[(a, b)].append((tb - ta).total_seconds() / 86400.0)

    edges = []
    for (a, b), n in edge_count.items():
        med = round(median(edge_days[(a, b)]), 2)
        back = IDEAL_PATH.index(b) < IDEAL_PATH.index(a) if a in IDEAL_PATH and b in IDEAL_PATH else False
        edges.append({"from": a, "to": b, "count": n, "median_days": med, "back_edge": back,
                      "total_wait_days": round(sum(edge_days[(a, b)]), 1)})
    edges.sort(key=lambda e: -e["count"])

    # conformance: exact ideal prefix with no repeated states and no skipped state
    total = len(traces)
    conforming = rework = skipped = lost = 0
    for seq in traces.values():
        states = [s for s, _ in seq]
        if states and states[-1] == "LOST":
            lost += 1
        if len(set(states)) < len(states):
            rework += 1
        elif states == IDEAL_PATH[: len(states)] or (states[-1] == "LOST"):
            conforming += 1
        else:
            skipped += 1

    # SCHEDULED -> ATTENDED is the planned wait for the appointment date, not a process delay
    forward = [e for e in edges if not e["back_edge"] and e["to"] != "LOST" and e["from"] != "SCHEDULED"]
    bottleneck = max(forward, key=lambda e: e["total_wait_days"], default=None)
    return {
        "nodes": [{"state": s, "count": node_count.get(s, 0)} for s in IDEAL_PATH + ["LOST"]],
        "edges": edges,
        "variants": [{"path": p, "count": n} for p, n in variants.most_common(8)],
        "conformance": {
            "journeys": total,
            "on_ideal_path": conforming,
            "with_rework_loops": rework,
            "skipped_a_step": skipped,
            "ended_lost": lost,
            "fitness_pct": round(100.0 * conforming / total, 1) if total else 0.0,
        },
        "bottleneck": bottleneck,
    }
