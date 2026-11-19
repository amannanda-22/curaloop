"""What-if simulator ("digital twin lite").

Monte Carlo over the currently open journeys: each day a journey closes with a hazard derived from
the survival baseline; coordinator calls / ASHA visits (limited per day) and levers raise it.

    "What if we add 2 ASHA workers? Double SMS reminders? Fund transport support?"

The levers use the same editable PRIOR effects as the optimizer, so results are scenario analysis
for planning discussions - NOT a forecast of clinical outcomes. The UI labels them accordingly.
"""
from __future__ import annotations

import numpy as np

from .nba import effect_of

VISITS_PER_ASHA_PER_DAY = 3


def _daily_hazard(p14: float) -> float:
    p14 = min(max(p14, 0.0), 0.99)
    return 1.0 - (1.0 - p14) ** (1.0 / 14.0)


def run(items: list[dict], *, calls_per_day: int, visits_per_day: int, days: int = 30,
        extra_asha: int = 0, sms_two_way_pct: float = 0.0, transport_support: bool = False,
        n_sims: int = 200, seed: int = 7, order: str = "priority", effect_scale: float = 1.0,
        return_finals: bool = False) -> dict:
    """items: [{base_p, weight, barrier}] (open journeys). Returns closures curve with 5-95% band."""
    rng = np.random.default_rng(seed)
    n = len(items)
    if n == 0:
        return {"days": list(range(days + 1)), "mean": [0] * (days + 1), "p05": [0] * (days + 1), "p95": [0] * (days + 1),
                "final_mean": 0.0}
    base = np.array([it["base_p"] for it in items])
    barrier = [it.get("barrier") for it in items]
    visits = visits_per_day + extra_asha * VISITS_PER_ASHA_PER_DAY
    sms_boost = np.array([effect_of("sms", b) for b in barrier]) * sms_two_way_pct * effect_scale
    transport_boost = np.array([0.18 * effect_scale if (transport_support and b == "TRANSPORT") else 0.0 for b in barrier])

    w = np.array([it["weight"] for it in items])
    eff_visit = np.array([effect_of("asha_visit", b) for b in barrier]) * effect_scale
    eff_call = np.array([effect_of("call", b) for b in barrier]) * effect_scale
    age_order = np.argsort(np.array([it.get("age_rank", 0) for it in items]), kind="stable")

    curves = np.zeros((n_sims, days + 1))
    for s in range(n_sims):
        open_mask = np.ones(n, dtype=bool)
        cum = 0
        last_action_day = np.full(n, -99)
        for d in range(1, days + 1):
            p14 = base + sms_boost + transport_boost
            eligible = open_mask & (d - last_action_day >= 3)
            if order == "fcfs":      # oldest first: visits, then calls, no matching
                cand = [i for i in age_order if eligible[i]]
                v_idx, c_idx = cand[:visits], cand[visits: visits + calls_per_day]
            else:                    # barrier-matched greedy on weighted marginal gain (what the MILP optimises)
                idx = np.flatnonzero(eligible)
                v_idx = idx[np.argsort(-(w[idx] * eff_visit[idx]), kind="stable")][:visits]
                rest = np.setdiff1d(idx, v_idx, assume_unique=True)
                c_idx = rest[np.argsort(-(w[rest] * eff_call[rest]), kind="stable")][:calls_per_day]
            for i in v_idx:
                p14[i] += eff_visit[i]
                last_action_day[i] = d
            for i in c_idx:
                p14[i] += eff_call[i]
                last_action_day[i] = d
            q = np.clip(p14, 0.0, 0.95)
            h = 1.0 - (1.0 - q) ** (1.0 / 14.0)
            closed_today = (rng.random(n) < h) & open_mask
            open_mask &= ~closed_today
            cum += int(closed_today.sum())
            curves[s, d] = cum
    out_extra = {"finals": curves[:, -1].tolist()} if return_finals else {}
    return {
        **out_extra,
        "days": list(range(days + 1)),
        "mean": [round(float(x), 1) for x in curves.mean(axis=0)],
        "p05": [round(float(x), 1) for x in np.percentile(curves, 5, axis=0)],
        "p95": [round(float(x), 1) for x in np.percentile(curves, 95, axis=0)],
        "final_mean": round(float(curves[:, -1].mean()), 1),
        "open_journeys": n,
    }


def impact(items: list[dict], *, calls: int, visits: int, days: int = 30, n_sims: int = 120, seed: int = 11) -> dict:
    """Policy comparison on the SAME open cases with common random numbers (paired).

    status_quo : nobody works the list (patients close only at the natural survival hazard)
    manual     : same capacity, but an unprioritised first-come-first-served register
    curaloop   : same capacity, priority by urgency x room-to-improve + barrier-matched action
    Plus an effect-size sensitivity sweep: how much of the gain survives if the real action lifts are
    only a fraction of our expert priors (the honest answer to "your priors are made up").
    """
    def go(**kw):
        return run(items, days=days, n_sims=n_sims, seed=seed, return_finals=True, **kw)

    sq = go(calls_per_day=0, visits_per_day=0)
    man = go(calls_per_day=calls, visits_per_day=visits, order="fcfs")
    cl = go(calls_per_day=calls, visits_per_day=visits, order="priority")
    sq_f, man_f, cl_f = (np.array(x["finals"]) for x in (sq, man, cl))

    def band(a, b):  # paired difference b - a
        d = b - a
        return {"mean": round(float(d.mean()), 1), "lo": round(float(np.percentile(d, 5)), 1), "hi": round(float(np.percentile(d, 95)), 1)}

    n = len(items)
    sweep = []
    for scale in (0.0, 0.25, 0.5, 0.75, 1.0):
        r = go(calls_per_day=calls, visits_per_day=visits, effect_scale=scale)
        d = np.array(r["finals"]) - sq_f
        sweep.append({"scale": scale, "gain_mean": round(float(d.mean()), 1), "gain_lo": round(float(np.percentile(d, 5)), 1)})
    still_open_sq = max(n - float(sq_f.mean()), 1e-9)
    recovered = float(cl_f.mean() - sq_f.mean())
    return {
        "open_cases": n, "days": days, "capacity": {"calls_per_day": calls, "visits_per_day": visits},
        "closed_by_day": {k: round(float(v.mean()), 1) for k, v in (("status_quo", sq_f), ("manual", man_f), ("curaloop", cl_f))},
        "gain_vs_status_quo": band(sq_f, cl_f),
        "gain_vs_manual": band(man_f, cl_f),
        "recovery_share": round(recovered / still_open_sq, 3),   # share of otherwise-stuck cases CuraLoop closes
        "sensitivity": sweep,
        "curves": {"days": sq["days"], "status_quo": sq["mean"], "manual": man["mean"], "curaloop": cl["mean"]},
    }
