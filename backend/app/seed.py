"""Synthetic data generator with PLANTED, documented effects.

Everything here is fake: names, phone numbers, ABHA-style ids. Real patient data is never used.

Planted effects (stored in Setting 'planted_effects' so analytics can prove it recovers them):
  * far_distance_dropoff_multiplier = 2.5 -> referrals > 20 km from the facility are lost 2.5x as often
  * female_dropoff_multiplier       = 1.5 -> women are lost 1.5x as often (what the fairness audit should find)
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
from sqlalchemy.orm import Session

from . import clock, services
from .models import Appointment, Event, Facility, Journey, Message, Patient, Screening, Setting
from .engine import outreach

PLANTED = {"far_distance_dropoff_multiplier": 2.5, "female_dropoff_multiplier": 1.5, "base_dropoff": 0.16}

FACILITIES = [
    ("PHC Anandapuram", "PHC", "Anandapuram", 17.92, 83.37),
    ("PHC Sabbavaram", "PHC", "Sabbavaram", 17.80, 83.10),
    ("CHC Anakapalle", "CHC", "Anakapalle", 17.69, 83.00),
    ("Area Hospital Narsipatnam", "Area Hospital", "Narsipatnam", 17.67, 82.61),
    ("District Hospital Visakhapatnam", "District Hospital", "Visakhapatnam", 17.72, 83.30),
]
VILLAGES = [  # name, lat, lon
    ("Anandapuram", 17.92, 83.37), ("Bheemunipatnam", 17.89, 83.45), ("Padmanabham", 17.88, 83.38),
    ("Sabbavaram", 17.80, 83.10), ("Paravada", 17.62, 83.12), ("Anakapalle", 17.69, 83.00),
    ("Chodavaram", 17.83, 82.94), ("Narsipatnam", 17.67, 82.61), ("Madugula", 18.05, 82.81),
    ("Paderu", 18.08, 82.67),
]
FIRST_F = ["Lakshmi", "Padma", "Sita", "Radha", "Savitri", "Kamala", "Durga", "Jyothi", "Sunita", "Rani", "Vijaya",
           "Anitha", "Swapna", "Bharathi", "Parvathi", "Mangamma", "Rajeswari", "Satyavathi"]
FIRST_M = ["Ramesh", "Suresh", "Venkat", "Srinivas", "Naresh", "Mahesh", "Ravi", "Prasad", "Appala", "Gopal",
           "Kumar", "Rao", "Satish", "Murali", "Chandra", "Naidu", "Raju", "Krishna"]
LAST = ["Naidu", "Reddy", "Rao", "Devi", "Kumar", "Patnaik", "Raju", "Varma", "Chowdary", "Prasad", "Murthy", "Sharma",
        "Gouda", "Setty", "Kondeti", "Bhaskar"]
FINDINGS = [  # finding, department, p, high-urgency probability
    ("Elevated blood pressure reading", "General Medicine (NCD clinic)", 0.36, 0.30),
    ("Raised random blood sugar reading", "General Medicine (NCD clinic)", 0.26, 0.25),
    ("Oral lesion noted at screening", "Oral Medicine / ENT", 0.14, 0.7),
    ("Breast examination - lump noted", "Surgery / Breast clinic", 0.08, 0.8),
    ("Cervical screening - positive visual test", "Gynaecology", 0.10, 0.7),
    ("Vision screening - referral advised", "Ophthalmology", 0.06, 0.1),
]
CAMPS = ["Health camp - Anandapuram", "Health camp - Chodavaram", "Health camp - Sabbavaram", "Health camp - Madugula",
         "Health camp - Paravada", "Health camp - Narsipatnam"]


def _pick_facility(dept: str, vill_lat, vill_lon, facs: list[Facility]) -> Facility:
    pool = facs
    if dept in ("Oral Medicine / ENT", "Surgery / Breast clinic", "Gynaecology", "Ophthalmology"):
        pool = [f for f in facs if f.kind in ("District Hospital", "Area Hospital")]
    return min(pool, key=lambda f: services.haversine_km(vill_lat, vill_lon, f.lat, f.lon))


def _phone(rng) -> str:
    return f"+91 90000 {rng.integers(10000, 99999)}"


def _abha(rng) -> str:
    return f"{rng.integers(10, 99)}-{rng.integers(1000, 9999)}-{rng.integers(1000, 9999)}-{rng.integers(1000, 9999)}"


def seed(db: Session, *, n_patients: int = 520, rng_seed: int = 42) -> dict:
    rng = np.random.default_rng(rng_seed)
    now = clock.now(db)
    facs = []
    for name, kind, area, lat, lon in FACILITIES:
        f = Facility(name=name, kind=kind, area=area, lat=lat, lon=lon)
        db.add(f)
        facs.append(f)
    db.flush()
    db.add(Setting(key="planted_effects", value=PLANTED))

    fp = np.array([f[2] for f in FINDINGS])
    fp = fp / fp.sum()
    created = 0
    for _ in range(n_patients):
        sex = "F" if rng.random() < 0.56 else "M"
        name = f"{rng.choice(FIRST_F if sex == 'F' else FIRST_M)} {rng.choice(LAST)}"
        village = VILLAGES[int(rng.integers(0, len(VILLAGES)))]
        lang = rng.choice(["te", "te", "te", "hi", "en"])
        age = int(np.clip(rng.normal(52, 13), 30, 82))
        p = Patient(abha_id=_abha(rng), name=name, age=age, sex=sex, phone=_phone(rng), language=str(lang),
                    village=village[0], lat=village[1] + rng.normal(0, 0.02), lon=village[2] + rng.normal(0, 0.02))
        db.add(p)
        db.flush()
        fi = int(rng.choice(len(FINDINGS), p=fp))
        finding, dept, _, p_high = FINDINGS[fi]
        urgency = "HIGH" if rng.random() < p_high else "ROUTINE"
        opened = now - timedelta(days=float(rng.uniform(1, 150)))
        _simulate_one(db, rng, p, finding, dept, urgency, opened, now, facs, str(rng.choice(CAMPS)))
        created += 1

    hero_id = _hero(db, now, facs)
    db.add(Setting(key="hero_journey_id", value=hero_id))
    db.flush()
    return {"patients": created + 1, "hero_journey_id": hero_id}


def _sms(db, j, p, ts, facility_name):
    first = p.name.split()[0]
    db.add(Message(journey_id=j.id, ts=ts, direction="out", channel="whatsapp", language=p.language,
                   text=outreach.render("reminder", p.language, name=first, facility=facility_name),
                   status="sent", intent="REMINDER"))


def _simulate_one(db, rng, p, finding, dept, urgency, opened, now, facs, camp) -> Journey:
    s = Screening(patient_id=p.id, camp=camp, screened_at=opened, finding=finding, urgency=urgency, department=dept)
    db.add(s)
    db.flush()
    fac = _pick_facility(dept, p.lat, p.lon, facs)
    dist = round(services.haversine_km(p.lat, p.lon, fac.lat, fac.lon) * 1.3, 1)
    j = Journey(patient_id=p.id, screening_id=s.id, department=dept, urgency=urgency, state="SCREENED",
                state_since=opened, opened_at=opened)
    db.add(j)
    db.flush()

    ev: list[tuple] = [(opened, "state", None, "SCREENED", None, f"Screening flag: {finding}", "camp-team")]
    t = opened
    state = "SCREENED"
    stopped = False

    def go(to, delay_days, actor, detail="", channel=None):
        nonlocal t, state, stopped
        if stopped:
            return False
        nt = t + timedelta(days=float(delay_days))
        if nt > now:
            stopped = True
            return False
        ev.append((nt, "state", state, to, channel, detail, actor))
        t, state = nt, to
        return True

    p_loss = PLANTED["base_dropoff"]
    if dist >= 20:
        p_loss *= PLANTED["far_distance_dropoff_multiplier"]
    if p.sex == "F":
        p_loss *= PLANTED["female_dropoff_multiplier"]
    p_loss = min(p_loss, 0.9)
    lost = rng.random() < p_loss
    never_referred = rng.random() < 0.06
    stop_at = rng.choice(["REFERRED", "CONTACTED", "SCHEDULED"], p=[0.38, 0.40, 0.22]) if lost else None
    barrier = None
    if lost or rng.random() < 0.35:
        if dist >= 20 and rng.random() < 0.55:
            barrier = "TRANSPORT"
        else:
            barrier = str(rng.choice(["TRANSPORT", "COST", "FEAR", "UNDERSTANDING", "WORK_LEAVE", "UNREACHABLE"],
                                     p=[0.2, 0.2, 0.18, 0.14, 0.18, 0.10]))
    attempts = failed = missed = 0
    last_no_show = None
    j.facility_id = None

    if never_referred:
        stopped = True
    else:
        if go("REFERRED", rng.exponential(1.1), "coordinator", f"Referred to {fac.name} ({dept})"):
            j.facility_id, j.distance_km = fac.id, dist
    if state == "REFERRED":
        if stop_at == "REFERRED":
            stopped = True
            barrier = None  # never reached the patient, so no barrier is known
            # stuck: a couple of outreach attempts that failed, spaced out
            n_try = int(rng.integers(0, 3))
            for k in range(n_try):
                at = t + timedelta(days=0.4 + k * 1.5)
                if at <= now:
                    ev.append((at, "contact", None, None, "sms" if k == 0 else "call",
                               "sent" if k == 0 else "no_answer", "coordinator"))
                    attempts += 1
                    failed += 0 if k == 0 else 1
                    if k == 0:
                        _sms(db, j, p, at, fac.name)
        else:
            delay = rng.lognormal(0.6 if urgency == "HIGH" else 1.0, 0.6)
            n_fail = int(rng.choice([0, 1, 2], p=[0.6, 0.28, 0.12]))
            ok = go("CONTACTED", delay, "coordinator", "Patient reached")
            if ok:
                for k in range(n_fail):
                    at = j_t = t - timedelta(days=delay * (0.7 - 0.2 * k))
                    ev.append((max(at, opened), "contact", None, None, "call", "no_answer", "coordinator"))
                    attempts += 1
                    failed += 1
                attempts += 1
                ev.append((t, "contact", None, None, "call", "reached", "coordinator"))
                if barrier:
                    ev.append((t, "barrier", None, None, None, barrier, "coordinator"))
                if rng.random() < 0.55:
                    _sms(db, j, p, max(opened, t - timedelta(days=delay)), fac.name)
            else:
                attempts = 1 if rng.random() < 0.7 else 0
                if attempts:
                    ev.append((min(t + timedelta(days=0.3), now), "contact", None, None, "sms", "sent", "coordinator"))
    if state == "CONTACTED" and not stopped:
        if stop_at == "CONTACTED":
            stopped = True
        else:
            if barrier and rng.random() < 0.7:
                pass
            for _round in range(3):
                if state != "CONTACTED":
                    break
                if not go("SCHEDULED", rng.lognormal(0.7, 0.6), "coordinator", "Appointment booked"):
                    break
                appt_at = t + timedelta(days=float(rng.uniform(2, 8)))
                a = Appointment(journey_id=j.id, facility_id=fac.id, scheduled_for=appt_at, status="booked",
                                patient_confirmed=bool(rng.random() < 0.55))
                db.add(a)
                if barrier:
                    ev.append((t, "barrier", None, None, None, f"{barrier} resolved", "coordinator"))
                    barrier = None
                p_noshow = 0.12 + (0.12 if dist >= 20 else 0) + (0.1 if stop_at == "SCHEDULED" else 0)
                if stop_at == "SCHEDULED" or rng.random() < p_noshow:
                    # no-show -> back to CONTACTED (rework loop)
                    ns = appt_at + timedelta(days=1)
                    if ns <= now:
                        a.status = "no_show"
                        ev.append((ns, "no_show", None, None, None, f"Missed {appt_at:%d %b}", "system"))
                        ev.append((ns, "state", "SCHEDULED", "CONTACTED", None, "No-show detected - back to rescheduling", "system"))
                        t, state = ns, "CONTACTED"
                        missed += 1
                        last_no_show = ns
                        if stop_at == "SCHEDULED" and _round >= 1:
                            stopped = True
                            break
                        continue
                    stopped = True
                    break
                # attends
                if appt_at <= now:
                    a.status = "attended"
                    t = appt_at
                    ev.append((appt_at, "state", "SCHEDULED", "ATTENDED", None, "Facility confirmed attendance", "facility-desk"))
                    state = "ATTENDED"
                    slow = rng.random() < 0.14
                    delay_out = rng.uniform(6, 14) if slow else rng.lognormal(0.2, 0.6)
                    if go("CLOSED", delay_out, "facility-desk", "Outcome confirmed by facility"):
                        j.outcome_code = str(rng.choice(["SEEN_PLAN_DOCUMENTED", "TREATMENT_STARTED",
                                                         "REFERRED_ONWARD", "NO_FURTHER_CARE_NEEDED"], p=[0.4, 0.35, 0.15, 0.1]))
                        j.close_reason = outreach.BARRIERS.get("x", "Outcome confirmed by facility")
                    break
                else:
                    break  # appointment in the future; remains SCHEDULED

    # old stuck journeys -> closed as lost by a manager
    if lost and state in ("REFERRED", "CONTACTED", "SCREENED") and (now - opened).days > 45:
        ts = min(now - timedelta(days=float(rng.uniform(1, 10))), now)
        ts = max(ts, t + timedelta(days=1))
        if ts <= now:
            ev.append((ts, "state", state, "LOST", None, "Closed as lost: unreachable after full escalation ladder", "manager"))
            state = "LOST"
            j.closed_at, j.close_reason = ts, "Unreachable after full escalation ladder"
            t = ts
    if never_referred and (now - opened).days > 45 and state == "SCREENED":
        ts = opened + timedelta(days=float(rng.uniform(20, 40)))
        ev.append((ts, "state", "SCREENED", "LOST", None, "Closed as lost: never referred (audit)", "manager"))
        state, j.closed_at, j.close_reason, t = "LOST", ts, "Never referred - closed at audit", ts

    j.state = state
    j.state_since = t
    j.barrier = barrier if state in ("REFERRED", "CONTACTED") else None
    j.contact_attempts, j.failed_contacts = attempts, failed
    j.missed_appointments, j.last_no_show_at = missed, last_no_show
    if state == "CLOSED":
        j.closed_at = t
        j.close_reason = "Outcome confirmed by facility"
    for ts, kind, src, dst, ch, detail, actor in ev:
        db.add(Event(journey_id=j.id, ts=ts, kind=kind, from_state=src, to_state=dst, channel=ch, detail=detail, actor=actor))
    db.flush()
    return j


def _hero(db: Session, now: datetime, facs: list[Facility]) -> int:
    """Lakshmi Devi - the demo patient (synthetic)."""
    vil = next(v for v in VILLAGES if v[0] == "Madugula")
    p = Patient(abha_id="91-4821-7730-1156", name="Lakshmi Devi", age=47, sex="F", phone="+91 90000 00101",
                language="te", village=vil[0], lat=vil[1], lon=vil[2])
    db.add(p)
    db.flush()
    fac = next(f for f in facs if f.name == "CHC Anakapalle")
    opened = now - timedelta(days=6)
    s = Screening(patient_id=p.id, camp="Health camp - Madugula", screened_at=opened,
                  finding="Elevated blood pressure reading", urgency="HIGH", department="General Medicine (NCD clinic)")
    db.add(s)
    db.flush()
    dist = round(services.haversine_km(p.lat, p.lon, fac.lat, fac.lon) * 1.3, 1)
    j = Journey(patient_id=p.id, screening_id=s.id, facility_id=fac.id, department=s.department, urgency="HIGH",
                state="REFERRED", state_since=now - timedelta(days=5.5), opened_at=opened, distance_km=dist,
                contact_attempts=2, failed_contacts=1, last_contact_at=now - timedelta(days=3))
    db.add(j)
    db.flush()
    rows = [
        (opened, "state", None, "SCREENED", None, "Screening flag: Elevated blood pressure reading", "camp-team"),
        (now - timedelta(days=5.5), "state", "SCREENED", "REFERRED", None, f"Referred to {fac.name} (General Medicine (NCD clinic))", "coordinator"),
        (now - timedelta(days=4.5), "contact", None, None, "sms", "sent", "system"),
        (now - timedelta(days=3), "contact", None, None, "call", "no_answer", "coordinator"),
    ]
    for ts, kind, src, dst, ch, detail, actor in rows:
        db.add(Event(journey_id=j.id, ts=ts, kind=kind, from_state=src, to_state=dst, channel=ch, detail=detail, actor=actor))
    db.add(Message(journey_id=j.id, ts=now - timedelta(days=4.5), direction="out", channel="whatsapp", language="te",
                   text=outreach.render("reminder", "te", name="Lakshmi", facility=fac.name), status="sent", intent="REMINDER"))
    db.flush()
    return j.id
