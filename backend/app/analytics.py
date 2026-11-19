"""Analytics: leakage funnel, KPIs, survival strata, pattern recovery and fairness audit (Pandas/NumPy)."""
from __future__ import annotations

import math
from datetime import datetime

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from .engine import mining, survival
from .engine.gaps import days_between, detect_gaps, score_journey
from .engine.states import IDEAL_PATH, OPEN_STATES, STATE_LABEL
from .models import Appointment, Event, Facility, Journey, Setting
from . import services


def distance_band(km: float) -> str:
    return "<10 km" if km < 10 else "10-20 km" if km < 20 else "20+ km"


def age_band(age: int) -> str:
    return "<40" if age < 40 else "40-59" if age < 60 else "60+"


def _journeys_df(db: Session, now: datetime) -> pd.DataFrame:
    rows = []
    for j in services.open_journeys(db) + list(db.execute(
            select(Journey).where(Journey.state.in_(["CLOSED", "LOST"]))).scalars()):
        end = j.closed_at or now
        rows.append({
            "id": j.id, "state": j.state, "urgency": j.urgency, "sex": j.patient.sex, "age": j.patient.age,
            "distance_km": j.distance_km, "facility_id": j.facility_id,
            "opened_at": j.opened_at, "closed_at": j.closed_at,
            "duration": max(0.0, days_between(j.opened_at, end)),
            "closed": 1 if j.state == "CLOSED" else 0,
            "lost": 1 if j.state == "LOST" else 0,
            "referred": j.facility_id is not None,
            "village": j.patient.village,
        })
    return pd.DataFrame(rows)


def funnel(db: Session) -> dict:
    events = list(db.execute(select(Event).where(Event.kind == "state")).scalars())
    reached: dict[str, set] = {s: set() for s in IDEAL_PATH}
    for e in events:
        if e.to_state in reached:
            reached[e.to_state].add(e.journey_id)
    stages = []
    prev = None
    for s in IDEAL_PATH:
        n = len(reached[s])
        drop = (prev - n) if prev is not None else 0
        stages.append({"state": s, "label": STATE_LABEL[s], "count": n, "dropped": drop,
                       "pct_of_prev": round(100.0 * n / prev, 1) if prev else 100.0,
                       "pct_of_start": round(100.0 * n / max(len(reached["SCREENED"]), 1), 1)})
        prev = n
    biggest = max(stages[1:], key=lambda s: s["dropped"], default=None)
    return {"stages": stages, "biggest_leak": biggest}


def summary(db: Session, now: datetime, rules: dict) -> dict:
    journeys = services.open_journeys(db)
    flagged = db.execute(select(Journey.id)).all()
    total = len(flagged)
    closed = db.execute(select(Journey.id).where(Journey.state == "CLOSED")).all()
    lost = db.execute(select(Journey.id).where(Journey.state == "LOST")).all()
    referred_ids = db.execute(select(Journey.id).where(Journey.facility_id.is_not(None))).all()
    appts = db.execute(select(Appointment)).scalars().all()
    no_show = sum(1 for a in appts if a.status == "no_show")
    attended_events = {e.journey_id for e in db.execute(select(Event).where(Event.kind == "state", Event.to_state == "ATTENDED")).scalars()}

    # SLA breaches & gap counts on open journeys
    breaches = {s: 0 for s in ("SCREENED", "REFERRED", "CONTACTED", "SCHEDULED", "ATTENDED")}
    gap_journeys = 0
    critical = 0
    for j in journeys:
        gaps = detect_gaps(j, now, rules)
        if gaps:
            gap_journeys += 1
            breaches[j.state] += 1
            _, _, bucket = score_journey(j, gaps, j.patient, now, rules)
            if bucket == "critical":
                critical += 1

    # referral delay (screened -> referred) from events
    first_ev: dict[int, dict[str, datetime]] = {}
    for e in db.execute(select(Event).where(Event.kind == "state", Event.to_state.in_(["SCREENED", "REFERRED"]))).scalars():
        first_ev.setdefault(e.journey_id, {})[e.to_state] = e.ts
    delays = [days_between(v["SCREENED"], v["REFERRED"]) for v in first_ev.values() if "SCREENED" in v and "REFERRED" in v]

    df = _journeys_df(db, now)
    med = None
    if not df.empty:
        t, s = survival.kaplan_meier(df["duration"], df["closed"])
        med = survival.median_time(t, s)
    return {
        "as_of": now.isoformat(),
        "patients_flagged": total,
        "referred": len(referred_ids),
        "referral_rate_pct": round(100.0 * len(referred_ids) / total, 1) if total else 0.0,
        "loops_closed": len(closed),
        "loop_closure_rate_pct": round(100.0 * len(closed) / max(len(referred_ids), 1), 1),
        "attended": len(attended_events),
        "follow_up_completion_pct": round(100.0 * len(attended_events) / max(len(referred_ids), 1), 1),
        "lost": len(lost),
        "open": len(journeys),
        "open_with_gaps": gap_journeys,
        "critical": critical,
        "missed_appointment_rate_pct": round(100.0 * no_show / max(len(appts), 1), 1),
        "avg_referral_delay_days": round(float(np.mean(delays)), 1) if delays else None,
        "median_days_to_close": round(med, 1) if med is not None else None,
        "sla_breaches_by_stage": breaches,
    }


def strata_survival(db: Session, now: datetime, by: str = "distance") -> dict:
    df = _journeys_df(db, now)
    df = df[df["referred"]]
    if df.empty:
        return {"strata": []}
    df = df.copy()
    df["stratum"] = df["distance_km"].map(distance_band) if by == "distance" else df["urgency"]
    out = []
    max_day = 60
    for name in (["<10 km", "10-20 km", "20+ km"] if by == "distance" else ["HIGH", "ROUTINE"]):
        sub = df[df["stratum"] == name]
        if sub.empty:
            continue
        t, s = survival.kaplan_meier(sub["duration"], sub["closed"])
        out.append({"name": name, "n": int(len(sub)), "median_days": survival.median_time(t, s),
                    "closed_by_day_30_pct": round(100 * (1 - survival.survival_at(t, s, 30)), 1),
                    "curve": survival.curve_points(t, s, max_day, 2.0)})
    return {"by": by, "strata": out, "max_day": max_day}


def _risk_ratio(a_fail: int, a_n: int, b_fail: int, b_n: int) -> dict:
    """Relative risk of non-closure (a vs b) with 95% CI (log method)."""
    if min(a_n, b_n) == 0 or a_fail == 0 or b_fail == 0:
        return {"rr": None, "lo": None, "hi": None}
    rr = (a_fail / a_n) / (b_fail / b_n)
    se = math.sqrt(1 / a_fail - 1 / a_n + 1 / b_fail - 1 / b_n)
    return {"rr": round(rr, 2), "lo": round(math.exp(math.log(rr) - 1.96 * se), 2),
            "hi": round(math.exp(math.log(rr) + 1.96 * se), 2)}


def pattern_recovery(db: Session, now: datetime) -> dict:
    """Does the analytics layer recover the effects the synthetic-data generator PLANTED?

    Matured cohort only (opened >= 60 days ago and referred): any journey not closed by now was dropped.
    """
    planted = (db.get(Setting, "planted_effects").value if db.get(Setting, "planted_effects") else {}) or {}
    df = _journeys_df(db, now)
    if df.empty:
        return {"checks": [], "planted_known": bool(planted)}
    df = df[df["referred"]].copy()
    df["age_days"] = (now - df["opened_at"]).dt.total_seconds() / 86400
    cohort = df[df["age_days"] >= 60].copy()
    cohort["dropped"] = (cohort["closed"] == 0).astype(int)
    checks = []

    far = cohort[cohort["distance_km"] >= 20]
    near = cohort[cohort["distance_km"] < 20]
    rr = _risk_ratio(int(far["dropped"].sum()), len(far), int(near["dropped"].sum()), len(near))
    pl = planted.get("far_distance_dropoff_multiplier")
    checks.append({"name": "Distance 20+ km -> drop-off", "group_a": f"20+ km (n={len(far)})", "group_b": f"<20 km (n={len(near)})",
                   "rate_a_pct": round(100 * far["dropped"].mean(), 1) if len(far) else None,
                   "rate_b_pct": round(100 * near["dropped"].mean(), 1) if len(near) else None,
                   "recovered": rr, "planted": pl,
                   "status": _status(rr, pl)})
    fem = cohort[cohort["sex"] == "F"]
    male = cohort[cohort["sex"] == "M"]
    rr2 = _risk_ratio(int(fem["dropped"].sum()), len(fem), int(male["dropped"].sum()), len(male))
    pl2 = planted.get("female_dropoff_multiplier")
    checks.append({"name": "Women -> drop-off", "group_a": f"Female (n={len(fem)})", "group_b": f"Male (n={len(male)})",
                   "rate_a_pct": round(100 * fem["dropped"].mean(), 1) if len(fem) else None,
                   "rate_b_pct": round(100 * male["dropped"].mean(), 1) if len(male) else None,
                   "recovered": rr2, "planted": pl2, "status": _status(rr2, pl2)})
    return {"checks": checks, "cohort_size": int(len(cohort)), "planted_known": bool(planted),
            "note": "Synthetic data with known planted effects. Recovery shows the pipeline finds real structure; "
                    "it is NOT a clinical accuracy claim."}


def _status(rr: dict, planted) -> str:
    if planted is None or rr.get("rr") is None:
        return "n/a"
    return "recovered" if rr["lo"] <= planted <= rr["hi"] else "off"


def fairness(db: Session, now: datetime) -> dict:
    df = _journeys_df(db, now)
    if df.empty:
        return {"groups": []}
    df = df[df["referred"]].copy()
    df["age_days"] = (now - df["opened_at"]).dt.total_seconds() / 86400
    cohort = df[df["age_days"] >= 45].copy()
    cohort["band_age"] = cohort["age"].map(age_band)
    cohort["band_dist"] = cohort["distance_km"].map(distance_band)
    cohort["sex_label"] = cohort["sex"].map({"F": "Female", "M": "Male"})
    out = []
    for dim, col in (("Sex", "sex_label"), ("Age", "band_age"), ("Distance to facility", "band_dist")):
        rows = []
        for name, sub in cohort.groupby(col):
            rows.append({"group": name, "n": int(len(sub)), "closure_rate_pct": round(100 * sub["closed"].mean(), 1)})
        best = max((r["closure_rate_pct"] for r in rows), default=0)
        for r in rows:
            r["ratio_vs_best"] = round(r["closure_rate_pct"] / best, 2) if best else None
            r["flag"] = bool(r["ratio_vs_best"] is not None and r["ratio_vs_best"] < 0.8 and r["n"] >= 20)
        out.append({"dimension": dim, "rows": sorted(rows, key=lambda r: r["group"])})
    return {"groups": out, "rule": "Flag = closure rate below 80% of the best group (n >= 20). A prompt to investigate, not a verdict.",
            "cohort_size": int(len(cohort))}


def facilities_table(db: Session, now: datetime) -> list[dict]:
    df = _journeys_df(db, now)
    facs = {f.id: f for f in db.execute(select(Facility)).scalars()}
    out = []
    if df.empty:
        return out
    pending_outcome = {}
    for j in services.open_journeys(db):
        if j.state == "ATTENDED" and j.facility_id:
            pending_outcome[j.facility_id] = pending_outcome.get(j.facility_id, 0) + 1
    for fid, sub in df[df["referred"]].groupby("facility_id"):
        f = facs.get(int(fid))
        closed = sub[sub["closed"] == 1]
        out.append({"facility_id": int(fid), "name": f.name if f else str(fid), "kind": f.kind if f else "",
                    "referred": int(len(sub)), "closed": int(len(closed)), "lost": int(sub["lost"].sum()),
                    "open": int(sub["state"].isin(list(OPEN_STATES)).sum()),
                    "closure_rate_pct": round(100 * len(closed) / len(sub), 1),
                    "median_days_to_close": round(float(closed["duration"].median()), 1) if len(closed) else None,
                    "awaiting_outcome": pending_outcome.get(int(fid), 0)})
    return sorted(out, key=lambda r: -r["referred"])


def barrier_counts(db: Session) -> list[dict]:
    from .engine.outreach import BARRIERS
    counts: dict[str, int] = {}
    for e in db.execute(select(Event).where(Event.kind == "barrier")).scalars():
        code = e.detail.split(" ")[0]
        if code in BARRIERS and "resolved" not in e.detail:
            counts[code] = counts.get(code, 0) + 1
    return sorted(({"code": k, "label": BARRIERS[k], "count": v} for k, v in counts.items()), key=lambda r: -r["count"])


def process_map(db: Session) -> dict:
    events = list(db.execute(select(Event).where(Event.kind == "state")).scalars())
    return mining.discover(mining.traces_from_events(events))
