"""Capacity-constrained intervention optimizer.

Problem a coordinator faces every morning: 300 open cases, but only e.g. 25 calls and 6 ASHA visits
today. Who gets which action?

We model it as a small integer programme (solved exactly with scipy.optimize.milp):

    maximise   sum_i  w_i * ( P_i(action) - P_i(no action) ) * x_i,action
    subject to one action per patient, calls <= C, ASHA visits <= V   (SMS is unconstrained)

P_i(no action) comes from the survival model; the lift of each action is an editable expert PRIOR
(engine/nba.py::ACTION_EFFECT). The output is "expected additional loops closed in the horizon" -
an operational planning number, not a clinical prediction.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from .nba import effect_of

ACTIONS = ["sms", "call", "asha_visit"]


def build_options(item: dict) -> dict[str, float]:
    base = item["base_p"]
    barrier = item.get("barrier")
    out = {}
    for a in ACTIONS:
        out[a] = max(0.0, min(0.95, base + effect_of(a, barrier)) - base)
    return out


def optimize(items: list[dict], calls: int, visits: int) -> dict:
    """items: [{id, base_p, weight, barrier, age_rank}] -> plan."""
    n = len(items)
    if n == 0:
        return {"plan": [], "expected_gain": 0.0, "baseline_closures": 0.0, "fcfs_gain": 0.0, "solver": "none"}
    gains = np.zeros((n, 3))
    for i, it in enumerate(items):
        opts = build_options(it)
        for j, a in enumerate(ACTIONS):
            gains[i, j] = it["weight"] * opts[a]
    # tiny penalty so SMS is only chosen when it actually helps
    cost_pen = np.array([0.0005, 0.0, 0.0])
    c = -(gains - cost_pen).reshape(-1)  # maximise -> minimise negative

    # constraints
    A = []
    ub = []
    for i in range(n):  # one action per patient
        row = np.zeros(3 * n)
        row[3 * i: 3 * i + 3] = 1
        A.append(row)
        ub.append(1)
    row_calls = np.zeros(3 * n)
    row_visits = np.zeros(3 * n)
    for i in range(n):
        row_calls[3 * i + 1] = 1
        row_visits[3 * i + 2] = 1
    A += [row_calls, row_visits]
    ub += [calls, visits]
    res = milp(c, constraints=LinearConstraint(np.array(A), -np.inf, np.array(ub)),
               integrality=np.ones(3 * n), bounds=Bounds(0, 1))
    x = np.round(res.x).reshape(n, 3) if res.success else np.zeros((n, 3))
    solver = "milp" if res.success else "failed"

    plan = []
    for i, it in enumerate(items):
        j = int(np.argmax(x[i])) if x[i].sum() > 0 else None
        if j is None:
            continue
        plan.append({"id": it["id"], "action": ACTIONS[j], "expected_gain": round(float(gains[i, j]), 4)})
    total = float(sum(p["expected_gain"] for p in plan))
    baseline = float(sum(it["base_p"] * it["weight"] for it in items))

    # comparison: first-come-first-served (oldest first gets visits, then calls)
    fcfs = 0.0
    order = sorted(range(n), key=lambda k: items[k].get("age_rank", k))
    v_left, c_left = visits, calls
    for k in order:
        if v_left > 0:
            fcfs += gains[k, 2]
            v_left -= 1
        elif c_left > 0:
            fcfs += gains[k, 1]
            c_left -= 1
        else:
            fcfs += gains[k, 0]
    return {"plan": sorted(plan, key=lambda p: -p["expected_gain"]), "expected_gain": round(total, 3),
            "baseline_closures": round(baseline, 3), "fcfs_gain": round(float(fcfs), 3), "solver": solver}
