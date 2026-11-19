"""Time-to-closure survival analysis (Kaplan-Meier), implemented with NumPy.

Why survival and not a plain classifier? Most journeys are still OPEN. Open journeys are
*censored* observations - dropping them (or labelling them "failed") biases every rate. Kaplan-Meier
uses them correctly.

Used for:
  * median time-to-closure per stratum (distance band, urgency...)
  * P(loop closes in the next h days | still open after t days) -> baseline for the optimizer
"""
from __future__ import annotations

import numpy as np


def kaplan_meier(durations, observed) -> tuple[np.ndarray, np.ndarray]:
    """durations: days (>=0). observed: 1 = loop closed, 0 = censored (still open / lost).

    Returns (times, survival) where survival[i] = P(not yet closed after times[i]).
    """
    d = np.asarray(durations, dtype=float)
    e = np.asarray(observed, dtype=int)
    if d.size == 0:
        return np.array([0.0]), np.array([1.0])
    order = np.argsort(d, kind="stable")
    d, e = d[order], e[order]
    times = np.unique(d[e == 1])
    surv = []
    s = 1.0
    for t in times:
        at_risk = int((d >= t).sum())
        events = int(((d == t) & (e == 1)).sum())
        s *= 1.0 - events / at_risk
        surv.append(s)
    return np.concatenate([[0.0], times]), np.concatenate([[1.0], np.array(surv)])


def survival_at(times: np.ndarray, surv: np.ndarray, t: float) -> float:
    idx = np.searchsorted(times, t, side="right") - 1
    return float(surv[max(idx, 0)])


def median_time(times: np.ndarray, surv: np.ndarray) -> float | None:
    below = np.where(surv <= 0.5)[0]
    return float(times[below[0]]) if below.size else None


def conditional_close_prob(times, surv, t_elapsed: float, horizon: float) -> float:
    """P(close within `horizon` more days | still open at `t_elapsed`)."""
    s_t = survival_at(times, surv, t_elapsed)
    if s_t <= 1e-9:
        # beyond observed support: fall back to the average daily hazard of the whole curve
        last_t = max(times[-1], 1.0)
        daily = 1.0 - max(surv[-1], 1e-3) ** (1.0 / last_t)
        return float(1.0 - (1.0 - daily) ** horizon)
    s_h = survival_at(times, surv, t_elapsed + horizon)
    return float(max(0.0, min(1.0, 1.0 - s_h / s_t)))


def curve_points(times: np.ndarray, surv: np.ndarray, max_day: float, step: float = 1.0) -> list[dict]:
    """Closure curve (1 - S(t)) sampled every `step` days, ready for plotting."""
    pts = []
    t = 0.0
    while t <= max_day + 1e-9:
        pts.append({"day": round(t, 1), "closed": round(1.0 - survival_at(times, surv, t), 4)})
        t += step
    return pts
