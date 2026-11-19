"""CuraLoop API (FastAPI). Interactive docs: /docs  (OpenAPI/Swagger)."""
from __future__ import annotations

import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import analytics, clock, config, security, seed as seeder, services
from .db import SessionLocal, get_db, init_db, reset_db
from .engine import allocate, fhir, nba, outreach, simulate, survival
from .engine.gaps import days_between, detect_gaps
from .engine.rules import get_rules, set_rules
from .engine.states import OUTCOME_CODES, STATE_LABEL, STATES, TransitionError
from .models import AuditLog, Facility, Journey, Message, Patient, Setting

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as db:
        if db.execute(select(func.count(Patient.id))).scalar_one() == 0:
            seeder.seed(db)
            db.commit()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="CuraLoop - Screening-to-Care Closed-Loop API",
    version="1.0.0",
    description="Closed-loop accountability for screening -> referral -> follow-up. "
                "All data is synthetic. Not a diagnostic tool; no clinical advice is produced.",
)


# ------------------------------------------------------------------------------ errors / roles
@app.exception_handler(TransitionError)
async def _transition_error(_: Request, exc: TransitionError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def _value_error(_: Request, exc: ValueError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(LookupError)
async def _lookup_error(_: Request, exc: LookupError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


ROLES = {"coordinator": "Care coordinator", "facility": "Facility desk", "manager": "Programme manager"}


class Ctx:
    def __init__(self, role: str, actor: str):
        self.role, self.actor = role, actor


def ctx(request: Request, x_role: str = Header("coordinator"), x_actor: str = Header("")) -> Ctx:
    if security.SECURE:                                   # token identity only; headers are ignored
        auth = getattr(request.state, "auth", None)
        if not auth:
            raise HTTPException(401, "Sign in required")
        return Ctx(auth["r"], auth["a"])
    role = x_role.lower()
    if role not in ROLES:
        raise HTTPException(400, f"Unknown role '{x_role}'")
    return Ctx(role, x_actor or ROLES[role])


@app.middleware("http")
async def guard(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/"):
        authz = request.headers.get("authorization", "")
        if authz.lower().startswith("bearer "):
            request.state.auth = security.verify_token(authz[7:])
        if security.SECURE and not path.startswith(security.PUBLIC_PREFIXES) and not getattr(request.state, "auth", None):
            return JSONResponse(status_code=401, content={"detail": "Sign in required"})
    resp: Response = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=200)


@app.post("/api/auth/login")
def login(body: LoginBody, request: Request, db: Session = Depends(get_db)):
    key = request.client.host if request.client else "?"
    if security.rate_limited(key):
        raise HTTPException(429, "Too many attempts. Try again in a few minutes.")
    role = security.check_login(body.username, body.password)
    if role is None:
        security.record_attempt(key)
        services.audit(db, clock.now(db), body.username[:40], "anonymous", "auth.failed", "system", None, "bad credentials")
        db.commit()
        raise HTTPException(401, "Wrong username or password")
    services.audit(db, clock.now(db), role, role, "auth.login", "system", None, "signed in")
    db.commit()
    return {"token": security.issue_token(role, ROLES[role]), "role": role, "expires_in": security.TOKEN_TTL_S}


@app.get("/api/auth/me")
def whoami(c: Ctx = Depends(ctx)):
    return {"role": c.role, "actor": c.actor, "mode": security.AUTH_MODE}


@app.get("/api/meta/public")
def meta_public():
    return {"auth_mode": security.AUTH_MODE, "app": "CuraLoop"}


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    n = db.execute(select(func.count(Patient.id))).scalar_one()
    return {"status": "ok", "synthetic_data": True, "patients": n, "auth_mode": security.AUTH_MODE, "version": app.version}


def allow(c: Ctx, *roles: str) -> None:
    if c.role not in roles:
        raise HTTPException(403, f"Role '{c.role}' is not allowed to do this. Allowed: {', '.join(roles)}")




def _fresh(db: Session, jid: int) -> dict:
    db.commit()
    j = services.get_journey(db, jid, fresh=True)
    return services.journey_card(j, clock.now(db), get_rules(db), detail=True)


# ------------------------------------------------------------------------------ meta & clock
@app.get("/api/meta")
def meta(db: Session = Depends(get_db)):
    facs = db.execute(select(Facility)).scalars().all()
    hero = db.get(Setting, "hero_journey_id")
    return {"roles": ROLES, "states": [{"code": s, "label": STATE_LABEL[s]} for s in STATES],
            "barriers": outreach.BARRIERS, "languages": outreach.LANGS, "outcomes": OUTCOME_CODES,
            "facilities": [{"id": f.id, "name": f.name, "kind": f.kind, "area": f.area} for f in facs],
            "hero_journey_id": hero.value if hero else None,
            "ladder": [s["step"] for s in nba.LADDER],
            "llm_enabled": bool(config.ANTHROPIC_API_KEY)}


@app.get("/api/clock")
def get_clock(db: Session = Depends(get_db)):
    return {"now": clock.now(db).isoformat(), "offset_days": clock.get_offset(db)}


class AdvanceBody(BaseModel):
    days: float = Field(gt=0, le=60)


@app.post("/api/clock/advance")
def advance_clock(body: AdvanceBody, db: Session = Depends(get_db), c: Ctx = Depends(ctx)):
    if security.SECURE and not config.ALLOW_DEMO_TOOLS:
        raise HTTPException(403, "The time machine is a demo tool and is disabled in secure mode.")
    now = clock.advance(db, body.days)
    changed = services.sweep(db, now)
    services.audit(db, now, c.actor, c.role, "clock.advance", "system", None, f"+{body.days} day(s); {changed} no-show(s) detected")
    db.commit()
    return {"now": now.isoformat(), "offset_days": clock.get_offset(db), "no_shows_detected": changed}


@app.post("/api/demo/reset")
def demo_reset(db: Session = Depends(get_db)):
    if security.SECURE and not config.ALLOW_DEMO_TOOLS:
        raise HTTPException(403, "Demo reset is disabled in secure mode (it would wipe real data).")
    db.close()
    reset_db()
    with SessionLocal() as s:
        info = seeder.seed(s)
        s.commit()
    return {"status": "reseeded", **info}


# ------------------------------------------------------------------------------ worklist
@app.get("/api/worklist")
def worklist(limit: int = 60, bucket: str | None = None, q: str | None = None, db: Session = Depends(get_db)):
    now = clock.now(db)
    rules = get_rules(db)
    if services.sweep(db, now):
        db.commit()
    cards = []
    for j in services.open_journeys(db):
        card = services.journey_card(j, now, rules)
        if card["gaps"] or card["state"] in ("SCREENED",):
            cards.append(card)
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for c in cards:
        counts[c["bucket"]] += 1
    if bucket:
        cards = [c for c in cards if c["bucket"] == bucket]
    if q:
        ql = q.lower()
        cards = [c for c in cards if ql in c["patient"]["name"].lower() or ql in c["patient"]["village"].lower()]
    cards.sort(key=lambda c: (-c["score"], -c["age_in_state_days"]))
    return {"as_of": now.isoformat(), "total": len(cards), "counts": counts, "items": cards[:limit]}


@app.get("/api/journeys/{jid}")
def journey_detail(jid: int, db: Session = Depends(get_db)):
    j = services.get_journey(db, jid)
    return services.journey_card(j, clock.now(db), get_rules(db), detail=True)


@app.get("/api/patients")
def search_patients(q: str = "", db: Session = Depends(get_db)):
    stmt = select(Patient).where(Patient.name.ilike(f"%{q}%") | Patient.village.ilike(f"%{q}%")).limit(25)
    out = []
    for p in db.execute(stmt).scalars():
        js = db.execute(select(Journey).where(Journey.patient_id == p.id).order_by(Journey.opened_at.desc())).scalars().all()
        out.append({**services.patient_dict(p), "journeys": [{"id": j.id, "state": j.state, "department": j.department} for j in js]})
    return out


# ------------------------------------------------------------------------------ registry / screening
class ScreeningBody(BaseModel):
    patient_id: int | None = None
    name: str | None = Field(default=None, min_length=2, max_length=80)
    age: int | None = Field(default=None, ge=0, le=120)
    sex: str | None = Field(default=None, pattern="^[FM]$")
    phone: str | None = Field(default=None, min_length=8, max_length=24)
    language: str = Field(default="te", pattern="^(te|hi|en)$")
    village: str = "Unknown"
    finding: str = Field(min_length=3, max_length=120)
    urgency: str = Field(pattern="^(HIGH|ROUTINE)$")
    department: str = Field(min_length=2, max_length=60)
    camp: str = "Health camp"


@app.post("/api/screenings")
def create_screening(body: ScreeningBody, db: Session = Depends(get_db), c: Ctx = Depends(ctx)):
    allow(c, "coordinator", "manager")
    now = clock.now(db)
    if body.patient_id:
        patient = {"id": body.patient_id}
    else:
        if not all([body.name, body.age is not None, body.sex, body.phone]):
            raise ValueError("name, age, sex and phone are required for a new patient")
        patient = {"name": body.name, "age": body.age, "sex": body.sex, "phone": body.phone,
                   "language": body.language, "village": body.village}
    j = services.register_screening(db, now, patient=patient, finding=body.finding, urgency=body.urgency,
                                    department=body.department, camp=body.camp, actor=c.actor, role=c.role)
    return _fresh(db, j.id)


# ------------------------------------------------------------------------------ journey actions
class ReferBody(BaseModel):
    facility_id: int
    department: str | None = None


@app.post("/api/journeys/{jid}/refer")
def refer(jid: int, body: ReferBody, db: Session = Depends(get_db), c: Ctx = Depends(ctx)):
    allow(c, "coordinator", "manager")
    j = services.get_journey(db, jid)
    services.refer(db, j, body.facility_id, body.department, clock.now(db), actor=c.actor, role=c.role)
    return _fresh(db, jid)


class ContactBody(BaseModel):
    channel: str = Field(pattern="^(sms|call|asha_visit|whatsapp)$")
    outcome: str = Field(pattern="^(sent|reached|no_answer|wrong_number)$")
    barrier: str | None = None
    note: str = Field(default="", max_length=300)


@app.post("/api/journeys/{jid}/contact")
def contact(jid: int, body: ContactBody, db: Session = Depends(get_db), c: Ctx = Depends(ctx)):
    allow(c, "coordinator", "manager")
    j = services.get_journey(db, jid)
    services.log_contact(db, j, clock.now(db), channel=body.channel, outcome=body.outcome, barrier=body.barrier,
                         note=body.note, actor=c.actor, role=c.role)
    return _fresh(db, jid)


class BarrierBody(BaseModel):
    barrier: str


@app.post("/api/journeys/{jid}/barrier")
def barrier(jid: int, body: BarrierBody, db: Session = Depends(get_db), c: Ctx = Depends(ctx)):
    allow(c, "coordinator", "manager")
    j = services.get_journey(db, jid)
    services.set_barrier(db, j, body.barrier, clock.now(db), actor=c.actor, role=c.role)
    return _fresh(db, jid)


class ScheduleBody(BaseModel):
    when: datetime | None = None
    in_days: float | None = Field(default=None, gt=0, le=90)
    facility_id: int | None = None


@app.post("/api/journeys/{jid}/schedule")
def schedule(jid: int, body: ScheduleBody, db: Session = Depends(get_db), c: Ctx = Depends(ctx)):
    allow(c, "coordinator", "manager")
    j = services.get_journey(db, jid)
    now = clock.now(db)
    when = body.when or (now + timedelta(days=body.in_days or 3)).replace(hour=10, minute=0, second=0, microsecond=0)
    services.schedule(db, j, body.facility_id, when.replace(tzinfo=None), now, actor=c.actor, role=c.role)
    return _fresh(db, jid)


@app.post("/api/journeys/{jid}/attend")
def attend(jid: int, db: Session = Depends(get_db), c: Ctx = Depends(ctx)):
    allow(c, "facility")
    j = services.get_journey(db, jid)
    services.mark_attended(db, j, clock.now(db), actor=c.actor, role=c.role)
    return _fresh(db, jid)


class OutcomeBody(BaseModel):
    outcome_code: str
    note: str = Field(default="", max_length=300)


@app.post("/api/journeys/{jid}/outcome")
def outcome(jid: int, body: OutcomeBody, db: Session = Depends(get_db), c: Ctx = Depends(ctx)):
    allow(c, "facility")  # the closed-loop rule: only the receiving facility can close the loop
    j = services.get_journey(db, jid)
    services.confirm_outcome(db, j, body.outcome_code, body.note, clock.now(db), actor=c.actor, role=c.role)
    return _fresh(db, jid)


class LostBody(BaseModel):
    reason: str = Field(min_length=3, max_length=160)


@app.post("/api/journeys/{jid}/close-lost")
def close_lost(jid: int, body: LostBody, db: Session = Depends(get_db), c: Ctx = Depends(ctx)):
    j = services.get_journey(db, jid)
    services.close_lost(db, j, body.reason, clock.now(db), actor=c.actor, role=c.role)
    return _fresh(db, jid)


@app.post("/api/journeys/{jid}/clear-flag")
def clear_flag(jid: int, db: Session = Depends(get_db), c: Ctx = Depends(ctx)):
    allow(c, "coordinator", "manager")
    j = services.get_journey(db, jid)
    services.clear_clinical_flag(db, j, clock.now(db), actor=c.actor, role=c.role)
    return _fresh(db, jid)


# ------------------------------------------------------------------------------ messaging (outreach agent)
class SendBody(BaseModel):
    template: str = Field(pattern="^(reminder|appt_reminder|menu)$")


@app.post("/api/journeys/{jid}/messages/send")
def send_message(jid: int, body: SendBody, db: Session = Depends(get_db), c: Ctx = Depends(ctx)):
    allow(c, "coordinator", "manager")
    j = services.get_journey(db, jid)
    services.send_template(db, j, body.template, clock.now(db), actor=c.actor, role=c.role)
    return _fresh(db, jid)


class InboundBody(BaseModel):
    text: str = Field(min_length=1, max_length=500)


@app.post("/api/journeys/{jid}/inbound")
def inbound(jid: int, body: InboundBody, db: Session = Depends(get_db)):
    """Patient-side simulator: what would arrive from the WhatsApp webhook."""
    j = services.get_journey(db, jid)
    res = services.receive_message(db, j, body.text, clock.now(db))
    card = _fresh(db, jid)
    return {"parsed": res["parsed"], "journey": card}


@app.get("/api/webhooks/whatsapp")
def whatsapp_verify(request: Request):
    """Meta webhook handshake (hub.challenge) - uses WHATSAPP_VERIFY_TOKEN."""
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and config.WHATSAPP_VERIFY_TOKEN and q.get("hub.verify_token") == config.WHATSAPP_VERIFY_TOKEN:
        return Response(content=q.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(403, "verification failed")


@app.post("/api/webhooks/whatsapp")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    """Meta WhatsApp Cloud API webhook. If WHATSAPP_APP_SECRET is set, X-Hub-Signature-256 is enforced."""
    import hashlib, hmac, json as _json
    raw = await request.body()
    if config.WHATSAPP_APP_SECRET:
        sig = request.headers.get("x-hub-signature-256", "")
        good = "sha256=" + hmac.new(config.WHATSAPP_APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, good):
            raise HTTPException(403, "bad signature")
    try:
        payload = _json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "invalid JSON")
    try:
        msg = payload["entry"][0]["changes"][0]["value"]["messages"][0]
        phone, text = msg["from"], msg["text"]["body"]
    except (KeyError, IndexError, TypeError):
        return {"status": "ignored", "reason": "unsupported payload"}
    digits = re.sub(r"\D", "", phone)[-10:]
    for p in db.execute(select(Patient)).scalars():
        if re.sub(r"\D", "", p.phone).endswith(digits):
            j = db.execute(select(Journey).where(Journey.patient_id == p.id, Journey.state.notin_(["CLOSED", "LOST"]))
                           .order_by(Journey.opened_at.desc())).scalars().first()
            if j:
                j = services.get_journey(db, j.id)
                res = services.receive_message(db, j, text, clock.now(db))
                db.commit()
                return {"status": "processed", "intent": res["parsed"]["intent"]}
    return {"status": "ignored", "reason": "no open journey for this number"}


@app.get("/api/approvals")
def approvals(db: Session = Depends(get_db)):
    now = clock.now(db)
    q = select(Message).where(Message.status == "pending_approval").order_by(Message.ts.desc())
    out = []
    for m in db.execute(q).scalars():
        j = services.get_journey(db, m.journey_id)
        out.append({**services.message_dict(m), "patient": services.patient_dict(j.patient), "state": j.state,
                    "age_hours": round(days_between(m.ts, now) * 24, 1)})
    return out


class DecisionBody(BaseModel):
    approve: bool


@app.post("/api/messages/{mid}/decision")
def decide(mid: int, body: DecisionBody, db: Session = Depends(get_db), c: Ctx = Depends(ctx)):
    allow(c, "coordinator", "manager")
    m = db.get(Message, mid)
    if m is None:
        raise LookupError("message not found")
    services.approve_message(db, m, clock.now(db), approve=body.approve, actor=c.actor, role=c.role)
    return _fresh(db, m.journey_id)


# ------------------------------------------------------------------------------ facility desk
@app.get("/api/facility/queue")
def facility_queue(facility_id: int | None = None, db: Session = Depends(get_db)):
    now = clock.now(db)
    rules = get_rules(db)
    services.sweep(db, now)
    items = []
    for j in services.open_journeys(db):
        if j.state not in ("SCHEDULED", "ATTENDED"):
            continue
        if facility_id and j.facility_id != facility_id:
            continue
        items.append(services.journey_card(j, now, rules))
    items.sort(key=lambda c: (c["state"] != "ATTENDED", c["appointment"]["when"] if c["appointment"] else ""))
    return {"as_of": now.isoformat(), "items": items}


# ------------------------------------------------------------------------------ insights
@app.get("/api/insights/summary")
def insights_summary(db: Session = Depends(get_db)):
    return analytics.summary(db, clock.now(db), get_rules(db))


@app.get("/api/insights/funnel")
def insights_funnel(db: Session = Depends(get_db)):
    return analytics.funnel(db)


@app.get("/api/insights/process")
def insights_process(db: Session = Depends(get_db)):
    return analytics.process_map(db)


@app.get("/api/insights/survival")
def insights_survival(by: str = "distance", db: Session = Depends(get_db)):
    return analytics.strata_survival(db, clock.now(db), by)


@app.get("/api/insights/patterns")
def insights_patterns(db: Session = Depends(get_db)):
    return analytics.pattern_recovery(db, clock.now(db))


@app.get("/api/insights/fairness")
def insights_fairness(db: Session = Depends(get_db)):
    return analytics.fairness(db, clock.now(db))


@app.get("/api/insights/facilities")
def insights_facilities(db: Session = Depends(get_db)):
    return {"facilities": analytics.facilities_table(db, clock.now(db)), "barriers": analytics.barrier_counts(db)}


# ------------------------------------------------------------------------------ planner (optimizer + what-if)
def _planner_items(db: Session, now: datetime, rules: dict) -> tuple[list[dict], dict]:
    df = analytics._journeys_df(db, now)
    models: dict[str, tuple] = {}
    if not df.empty:
        ref = df[df["referred"]]
        for urg in ("HIGH", "ROUTINE"):
            sub = ref[ref["urgency"] == urg]
            if len(sub) >= 10:
                models[urg] = survival.kaplan_meier(sub["duration"], sub["closed"])
    horizon = rules.get("horizon_days", 14)
    items, meta_by_id = [], {}
    for j in services.open_journeys(db):
        if j.state not in ("REFERRED", "CONTACTED", "SCHEDULED") or j.clinical_flag:
            continue
        gaps = detect_gaps(j, now, rules)
        if not gaps:
            continue
        elapsed = days_between(j.opened_at, now)
        mdl = models.get(j.urgency)
        base = survival.conditional_close_prob(mdl[0], mdl[1], elapsed, horizon) if mdl else 0.25
        base = max(0.02, min(base, 0.9))
        card = services.journey_card(j, now, rules)
        items.append({"id": j.id, "base_p": base, "weight": 1.5 if j.urgency == "HIGH" else 1.0,
                      "barrier": j.barrier, "age_rank": -elapsed})
        meta_by_id[j.id] = card
    return items, meta_by_id


class PlanBody(BaseModel):
    calls: int | None = Field(default=None, ge=0, le=500)
    asha_visits: int | None = Field(default=None, ge=0, le=200)


@app.post("/api/planner/optimize")
def planner_optimize(body: PlanBody, db: Session = Depends(get_db)):
    now = clock.now(db)
    rules = get_rules(db)
    calls = body.calls if body.calls is not None else rules["capacity"]["calls"]
    visits = body.asha_visits if body.asha_visits is not None else rules["capacity"]["asha_visits"]
    items, meta_by_id = _planner_items(db, now, rules)
    res = allocate.optimize(items, calls, visits)
    plan = []
    for p in res["plan"]:
        card = meta_by_id[p["id"]]
        plan.append({**p, "patient": card["patient"], "state": card["state"], "urgency": card["urgency"],
                     "barrier_label": card["barrier_label"], "score": card["score"], "bucket": card["bucket"],
                     "headline_gap": card["gaps"][0]["label"] if card["gaps"] else "",
                     "nba_title": card["nba"]["title"] if card["nba"] else ""})
    improvement = None
    if res["fcfs_gain"] > 0:
        improvement = round(100.0 * (res["expected_gain"] - res["fcfs_gain"]) / res["fcfs_gain"], 1)
    return {"capacity": {"calls": calls, "asha_visits": visits}, "candidates": len(items), "plan": plan,
            "expected_extra_closures": res["expected_gain"], "fcfs_extra_closures": res["fcfs_gain"],
            "improvement_vs_fcfs_pct": improvement, "solver": res["solver"],
            "assumption_note": "Action lifts are editable expert priors, not learned effects. Gains are weighted "
                               "expected additional loop closures within the horizon - an operational planning aid."}


class SimBody(BaseModel):
    extra_asha: int = Field(default=0, ge=0, le=20)
    sms_two_way_pct: float = Field(default=0.0, ge=0, le=1)
    transport_support: bool = False
    days: int = Field(default=30, ge=7, le=90)


@app.post("/api/planner/simulate")
def planner_simulate(body: SimBody, db: Session = Depends(get_db)):
    now = clock.now(db)
    rules = get_rules(db)
    items, _ = _planner_items(db, now, rules)
    cap = rules["capacity"]
    base = simulate.run(items, calls_per_day=cap["calls"], visits_per_day=cap["asha_visits"], days=body.days)
    scen = simulate.run(items, calls_per_day=cap["calls"], visits_per_day=cap["asha_visits"], days=body.days,
                        extra_asha=body.extra_asha, sms_two_way_pct=body.sms_two_way_pct,
                        transport_support=body.transport_support)
    return {"baseline": base, "scenario": scen, "extra_closures": round(scen["final_mean"] - base["final_mean"], 1),
            "open_journeys": len(items),
            "assumption_note": "Scenario analysis using editable prior effects. Not a forecast of clinical outcomes."}


# ------------------------------------------------------------------------------ rules, audit, FHIR
@app.get("/api/rules")
def read_rules(db: Session = Depends(get_db)):
    return get_rules(db)


@app.put("/api/rules")
def update_rules(patch: dict, db: Session = Depends(get_db), c: Ctx = Depends(ctx)):
    allow(c, "manager")
    new = set_rules(db, patch)
    services.audit(db, clock.now(db), c.actor, c.role, "rules.update", "settings", None, str(patch)[:200])
    db.commit()
    return new


@app.get("/api/audit")
def audit_log(limit: int = 80, db: Session = Depends(get_db)):
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 500))
    return [{"id": a.id, "ts": a.ts.isoformat(), "actor": a.actor, "role": a.role, "action": a.action,
             "entity": a.entity, "entity_id": a.entity_id, "detail": a.detail} for a in db.execute(q).scalars()]


@app.get("/api/fhir/journey/{jid}")
def fhir_export(jid: int, db: Session = Depends(get_db)):
    j = services.get_journey(db, jid)
    card = services.journey_card(j, clock.now(db), get_rules(db))
    return fhir.journey_bundle(j, card["nba"])


# ------------------------------------------------------------------------------ consent & data export
class ConsentBody(BaseModel):
    consent: bool
    note: str = Field(default="", max_length=200)


@app.post("/api/patients/{pid}/consent")
def set_consent(pid: int, body: ConsentBody, db: Session = Depends(get_db), c: Ctx = Depends(ctx)):
    allow(c, "coordinator", "manager")
    p = db.get(Patient, pid)
    if not p:
        raise LookupError("Patient not found")
    p.consent_outreach = body.consent
    services.audit(db, clock.now(db), c.actor, c.role, "consent.granted" if body.consent else "consent.withdrawn",
                   "patient", pid, body.note or "recorded by staff")
    db.commit()
    return {"id": pid, "consent_outreach": p.consent_outreach}


@app.get("/api/export/deidentified")
def export_deidentified(db: Session = Depends(get_db), c: Ctx = Depends(ctx)):
    """Analysis extract without name, phone, ABHA id or village. Pseudonym is salted and not reversible by the recipient."""
    import hashlib
    allow(c, "manager")
    now = clock.now(db)
    rows = []
    for j in services.all_journeys(db):
        p = j.patient
        pseudo = hashlib.sha256(f"{security._SECRET}:{p.id}".encode()).hexdigest()[:12]
        rows.append({"pseudonym": pseudo, "age_band": f"{(p.age // 10) * 10}-{(p.age // 10) * 10 + 9}", "sex": p.sex,
                     "language": p.language, "urgency": j.urgency, "state": j.state, "barrier": j.barrier,
                     "days_open": round(days_between(j.opened_at, now), 1), "contact_attempts": j.contact_attempts})
    services.audit(db, now, c.actor, c.role, "export.deidentified", "system", None, f"{len(rows)} rows")
    db.commit()
    return {"rows": rows, "fields_removed": ["name", "phone", "abha_id", "village", "coordinates"]}


# ------------------------------------------------------------------------------ impact model
EVIDENCE = [
    {"id": "pakhare2021", "claim": "In a Bhopal urban-slum cohort of 1,451 screen-positive adults, 34.9% never linked to any provider and "
     "only 55.2% were still on care at 6 months; late community-health-worker engagement (OR 2.6) and distance (OR 1.7) predicted non-linkage.",
     "cite": "Pakhare A et al., BMJ Open 2021;11:e045997",
     "url": "https://bmjopen.bmj.com/content/bmjopen/11/8/e045997.full.pdf"},
]


@app.get("/api/impact")
def impact(calls: int | None = None, asha_visits: int | None = None, annual_screen_positive: int = 10000,
           baseline_closure: float = 0.55, db: Session = Depends(get_db)):
    """Policy comparison + sensitivity on today's open cases, and an editable district projection."""
    if not (100 <= annual_screen_positive <= 5_000_000) or not (0.05 <= baseline_closure <= 0.95):
        raise HTTPException(422, "annual_screen_positive must be 100..5,000,000 and baseline_closure 0.05..0.95")
    now = clock.now(db)
    rules = get_rules(db)
    c = calls if calls is not None else rules["capacity"]["calls"]
    v = asha_visits if asha_visits is not None else rules["capacity"]["asha_visits"]
    items, _ = _planner_items(db, now, rules)
    res = simulate.impact(items, calls=c, visits=v, days=30, n_sims=80)
    n, closed_sq = res["open_cases"], res["closed_by_day"]["status_quo"]
    stuck = max(n - closed_sq, 1e-9)
    proj = []
    for row in res["sensitivity"]:
        share = row["gain_mean"] / stuck
        extra = annual_screen_positive * (1 - baseline_closure) * share
        proj.append({"effect_scale": row["scale"], "recovery_share": round(share, 3),
                     "extra_reaching_care": int(round(extra)),
                     "closure_after": round(baseline_closure + (1 - baseline_closure) * share, 3)})
    return {**res, "projection": {"annual_screen_positive": annual_screen_positive, "baseline_closure": baseline_closure, "rows": proj},
            "evidence": EVIDENCE,
            "honesty": ["All patients are synthetic. Action lifts are expert priors, not learned effects.",
                        "Numbers are scenario analysis for planning, not clinical outcomes or a forecast.",
                        "The pilot (docs/PILOT_PLAN.md) exists to replace these priors with measured effects."]}


# ------------------------------------------------------------------------------ static frontend
_dist = config.FRONTEND_DIST
if (_dist / "index.html").exists():
    if (_dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404)
        target = _dist / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(_dist / "index.html")
else:
    @app.get("/", include_in_schema=False)
    def root():
        return {"app": "CuraLoop API", "docs": "/docs",
                "note": "Frontend not built yet. Run: cd frontend && npm install && npm run build"}
