"""Domain services: every state change goes through here so rules, event log and audit trail
can never be bypassed by an endpoint."""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import config
from .engine import outreach
from .engine.gaps import current_appointment, days_between, detect_gaps, ring_segments, score_journey, sla_for
from .engine.nba import next_best_action
from .engine.states import OPEN_STATES, STATE_LABEL, TransitionError, validate_transition
from .models import Appointment, AuditLog, Event, Facility, Journey, Message, Patient, Screening


# ---------------------------------------------------------------------------------- helpers
def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def audit(db: Session, now: datetime, actor: str, role: str, action: str, entity: str,
          entity_id: int | None, detail: str = "") -> None:
    db.add(AuditLog(ts=now, actor=actor, role=role, action=action, entity=entity, entity_id=entity_id, detail=detail))


def log_event(db: Session, j: Journey, ts: datetime, kind: str, *, from_state=None, to_state=None,
              channel=None, detail="", actor="system") -> Event:
    ev = Event(journey_id=j.id, ts=ts, kind=kind, from_state=from_state, to_state=to_state,
               channel=channel, detail=detail, actor=actor)
    db.add(ev)
    return ev


def transition(db: Session, j: Journey, to_state: str, now: datetime, *, actor: str, role: str,
               via: str | None = None, reason: str | None = None, detail: str = "") -> None:
    validate_transition(j.state, to_state, via=via, role=role, reason=reason)
    src = j.state
    j.state = to_state
    j.state_since = now
    if to_state in ("CLOSED", "LOST"):
        j.closed_at = now
        j.close_reason = reason
    log_event(db, j, now, "state", from_state=src, to_state=to_state, detail=detail, actor=actor)
    audit(db, now, actor, role, f"state:{src}->{to_state}", "journey", j.id, detail)


def get_journey(db: Session, jid: int, fresh: bool = False) -> Journey:
    if fresh:
        db.expire_all()  # relationships may be stale after writes in the same session
    q = (select(Journey).where(Journey.id == jid).options(
        selectinload(Journey.patient), selectinload(Journey.screening), selectinload(Journey.facility),
        selectinload(Journey.appointments).selectinload(Appointment.facility),
        selectinload(Journey.events), selectinload(Journey.messages)))
    j = db.execute(q).scalar_one_or_none()
    if j is None:
        raise LookupError(f"journey {jid} not found")
    return j


# ---------------------------------------------------------------------------------- registry
def register_screening(db: Session, now: datetime, *, patient: dict, finding: str, urgency: str,
                       department: str, camp: str, actor: str, role: str) -> Journey:
    p = None
    if patient.get("id"):
        p = db.get(Patient, patient["id"])
    if p is None:
        p = Patient(abha_id=patient.get("abha_id") or f"91-{abs(hash(patient['name'])) % 10**4:04d}-{now:%H%M}-{now:%S}00",
                    name=patient["name"], age=patient["age"], sex=patient["sex"], phone=patient["phone"],
                    language=patient.get("language", "te"), village=patient.get("village", "Unknown"),
                    lat=patient.get("lat", 17.7), lon=patient.get("lon", 83.2))
        db.add(p)
        db.flush()
    s = Screening(patient_id=p.id, camp=camp, screened_at=now, finding=finding, urgency=urgency, department=department)
    db.add(s)
    db.flush()
    j = Journey(patient_id=p.id, screening_id=s.id, department=department, urgency=urgency,
                state="SCREENED", state_since=now, opened_at=now)
    db.add(j)
    db.flush()
    log_event(db, j, now, "state", to_state="SCREENED", detail=f"Screening flag: {finding}", actor=actor)
    audit(db, now, actor, role, "screening.create", "journey", j.id, finding)
    return j


def refer(db: Session, j: Journey, facility_id: int, department: str | None, now: datetime, *, actor: str, role: str) -> None:
    fac = db.get(Facility, facility_id)
    if fac is None:
        raise LookupError("facility not found")
    j.facility_id = fac.id
    if department:
        j.department = department
    j.distance_km = round(haversine_km(j.patient.lat, j.patient.lon, fac.lat, fac.lon) * 1.3, 1)
    transition(db, j, "REFERRED", now, actor=actor, role=role, detail=f"Referred to {fac.name} ({j.department})")


# ---------------------------------------------------------------------------------- outreach
def log_contact(db: Session, j: Journey, now: datetime, *, channel: str, outcome: str, barrier: str | None,
                note: str, actor: str, role: str) -> None:
    """Record an outreach attempt and its result."""
    if j.state not in OPEN_STATES:
        raise TransitionError("Journey is already closed.")
    if channel not in ("sms", "call", "asha_visit", "whatsapp"):
        raise ValueError("unknown channel")
    if outcome not in ("sent", "reached", "no_answer", "wrong_number"):
        raise ValueError("unknown outcome")
    j.contact_attempts += 1
    j.last_contact_at = now
    log_event(db, j, now, "contact", channel=channel, detail=f"{outcome}" + (f" - {note}" if note else ""), actor=actor)
    if outcome in ("no_answer", "wrong_number"):
        j.failed_contacts += 1
        if outcome == "wrong_number" and not j.barrier:
            set_barrier(db, j, "UNREACHABLE", now, actor=actor, role=role)
    if outcome == "reached":
        j.failed_contacts = 0 if channel == "asha_visit" else j.failed_contacts
        if j.state == "REFERRED":
            transition(db, j, "CONTACTED", now, actor=actor, role=role, detail=f"Patient reached by {channel}")
    if barrier:
        set_barrier(db, j, barrier, now, actor=actor, role=role)
    audit(db, now, actor, role, f"contact:{channel}:{outcome}", "journey", j.id, note)


def set_barrier(db: Session, j: Journey, barrier: str, now: datetime, *, actor: str, role: str) -> None:
    if barrier not in outreach.BARRIERS:
        raise ValueError("unknown barrier")
    j.barrier = barrier
    log_event(db, j, now, "barrier", detail=barrier, actor=actor)
    audit(db, now, actor, role, "barrier.set", "journey", j.id, barrier)


def schedule(db: Session, j: Journey, facility_id: int | None, when: datetime, now: datetime, *, actor: str, role: str) -> Appointment:
    if j.state != "CONTACTED":
        raise TransitionError("Appointments can be booked once the patient has been reached.")
    if when <= now:
        raise ValueError("Appointment must be in the future.")
    fid = facility_id or j.facility_id
    if fid is None:
        raise ValueError("No facility for appointment.")
    a = Appointment(journey_id=j.id, facility_id=fid, scheduled_for=when, status="booked")
    db.add(a)
    db.flush()
    if j.barrier:
        log_event(db, j, now, "barrier", detail=f"{j.barrier} resolved", actor=actor)
        j.barrier = None
    transition(db, j, "SCHEDULED", now, actor=actor, role=role, detail=f"Appointment {when:%d %b %H:%M}")
    return a


def mark_attended(db: Session, j: Journey, now: datetime, *, actor: str, role: str) -> None:
    appt = current_appointment(j)
    if j.state != "SCHEDULED" or appt is None:
        raise TransitionError("No booked appointment to mark as attended.")
    appt.status = "attended"
    transition(db, j, "ATTENDED", now, actor=actor, role=role, via="facility_attendance", detail="Facility confirmed attendance")


def confirm_outcome(db: Session, j: Journey, outcome_code: str, note: str, now: datetime, *, actor: str, role: str) -> None:
    from .engine.states import OUTCOME_CODES
    if outcome_code not in OUTCOME_CODES:
        raise ValueError("unknown outcome code")
    j.outcome_code = outcome_code
    transition(db, j, "CLOSED", now, actor=actor, role=role, via="facility_outcome", reason=OUTCOME_CODES[outcome_code],
               detail=f"Outcome confirmed by facility: {OUTCOME_CODES[outcome_code]}" + (f" ({note})" if note else ""))


def close_lost(db: Session, j: Journey, reason: str, now: datetime, *, actor: str, role: str) -> None:
    transition(db, j, "LOST", now, actor=actor, role=role, reason=reason, detail=f"Closed as lost: {reason}")


def clear_clinical_flag(db: Session, j: Journey, now: datetime, *, actor: str, role: str) -> None:
    j.clinical_flag = False
    log_event(db, j, now, "flag", detail="Clinical flag reviewed by clinician", actor=actor)
    audit(db, now, actor, role, "clinical_flag.clear", "journey", j.id)


# ---------------------------------------------------------------------------------- messaging
def _out(db: Session, j: Journey, now: datetime, text: str, lang: str, *, status: str, intent: str | None = None,
         channel: str = "whatsapp", note: str | None = None, flag: str | None = None) -> Message:
    m = Message(journey_id=j.id, ts=now, direction="out", channel=channel, language=lang, text=text,
                intent=intent, status=status, note=note, flag=flag)
    db.add(m)
    db.flush()
    return m


def send_template(db: Session, j: Journey, template: str, now: datetime, *, actor: str, role: str,
                  channel: str = "whatsapp") -> Message:
    if j.state not in OPEN_STATES:
        raise TransitionError("Journey is closed.")
    p = j.patient
    if not p.consent_outreach and template != "optout":
        raise ValueError("This patient has opted out of messages. Use a phone call or an ASHA visit.")
    first = p.name.split()[0]
    appt = current_appointment(j)
    facility = j.facility.name if j.facility else "the health centre"
    kw = {"name": first, "facility": facility,
          "when": f"{appt.scheduled_for:%d %b}" if appt else ""}
    text = outreach.render(template, p.language, **kw)
    m = _out(db, j, now, text, p.language, status="sent", channel=channel,
             intent="MENU" if template == "menu" else template.upper())
    j.contact_attempts += 1
    j.last_contact_at = now
    log_event(db, j, now, "contact", channel=channel, detail=f"sent {template}", actor=actor)
    audit(db, now, actor, role, f"message.send:{template}", "journey", j.id, text[:120])
    return m


def _classify_with_llm(text: str, lang: str) -> dict | None:
    """Optional: only when ANTHROPIC_API_KEY is set; falls back silently to the rule engine."""
    if not config.ANTHROPIC_API_KEY:
        return None
    try:
        import httpx

        prompt = (
            "Classify this patient message sent to a health-follow-up service (Telugu/Hindi/English, any script). "
            "Return ONLY JSON {\"intent\": CONFIRM|RESCHEDULE|HELP|BARRIER|RED_FLAG|UNKNOWN, "
            "\"barrier\": TRANSPORT|COST|FEAR|UNDERSTANDING|WORK_LEAVE|RELOCATED|null}. "
            "RED_FLAG if the patient describes symptoms or an emergency. Never give advice.\n\nMessage: " + text)
        r = httpx.post("https://api.anthropic.com/v1/messages", timeout=8, headers={
            "x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-haiku-5-5", "max_tokens": 80, "messages": [{"role": "user", "content": prompt}]})
        data = json.loads(r.json()["content"][0]["text"])
        if data.get("intent") in {"CONFIRM", "RESCHEDULE", "HELP", "BARRIER", "RED_FLAG", "UNKNOWN"}:
            return {"intent": data["intent"], "barrier": data.get("barrier"), "red_flag": data["intent"] == "RED_FLAG",
                    "language": lang, "confidence": "medium"}
    except Exception:
        return None
    return None


def receive_message(db: Session, j: Journey, text: str, now: datetime, *, actor: str = "patient") -> dict:
    """Handle an inbound patient message: parse, update the loop, draft/send a reply.

    Returns {"parsed": ..., "replies": [message dicts]} for the UI.
    """
    p = j.patient
    first = p.name.split()[0]
    last_msg = j.messages[-1] if j.messages else None
    awaiting_menu = bool(last_msg and last_msg.direction == "out" and last_msg.intent == "MENU"
                         and last_msg.status == "sent")
    parsed = outreach.parse_message(text, awaiting_menu=awaiting_menu, lang_hint=p.language)
    if parsed["intent"] == "UNKNOWN":
        alt = _classify_with_llm(text, parsed["language"])
        if alt:
            parsed = alt
    lang = parsed["language"]

    inbound = Message(journey_id=j.id, ts=now, direction="in", channel="whatsapp", language=lang, text=text,
                      intent=parsed["intent"], barrier=parsed["barrier"], status="received",
                      flag="RED_FLAG" if parsed["red_flag"] else None)
    db.add(inbound)
    db.flush()
    log_event(db, j, now, "message", channel="whatsapp", detail=f"inbound {parsed['intent']}"
              + (f"/{parsed['barrier']}" if parsed["barrier"] else ""), actor=actor)
    j.last_contact_at = now

    replies: list[Message] = []
    appt = current_appointment(j)
    intent = parsed["intent"]

    # a reply from the patient == contact made
    if j.state == "REFERRED" and intent != "UNKNOWN":
        transition(db, j, "CONTACTED", now, actor="system", role="system", detail="Patient replied on WhatsApp")

    if intent == "OPT_OUT":
        p.consent_outreach = False
        audit(db, now, "patient", "patient", "consent.withdrawn", "patient", p.id, "Patient replied STOP")
        replies.append(_out(db, j, now, outreach.render("optout", lang, name=first), lang, status="sent",
                            note="Opt-out confirmed. No further messages; switch to calls / ASHA."))
    elif intent == "RED_FLAG":
        j.clinical_flag = True
        log_event(db, j, now, "flag", detail="Clinical red flag in patient message", actor="system")
        replies.append(_out(db, j, now, outreach.render("red_flag", lang, name=first), lang, status="sent",
                            note="Fixed safety template - no advice. Clinician alerted.", flag="RED_FLAG"))
    elif intent == "CONFIRM":
        if j.state == "SCHEDULED" and appt and appt.status == "booked":
            appt.patient_confirmed = True
            replies.append(_out(db, j, now, outreach.render("ack_confirm", lang, name=first), lang, status="sent",
                                note="Auto-sent acknowledgement"))
        else:
            replies.append(_out(db, j, now, outreach.render("ack_reached", lang, name=first), lang, status="sent",
                                note="Auto-sent; coordinator should now book a slot"))
    elif intent == "RESCHEDULE":
        if j.state == "SCHEDULED" and appt and appt.status == "booked":
            proposed = max(appt.scheduled_for, now) + timedelta(days=3)
            replies.append(_out(db, j, now, outreach.render("reschedule", lang, name=first, when=f"{proposed:%d %b}"),
                                lang, status="pending_approval", intent="RESCHEDULE",
                                note=f"Draft proposes {proposed:%d %b}. Needs approval because it changes the appointment."))
        else:
            replies.append(_out(db, j, now, outreach.render("ack_reached", lang, name=first), lang, status="sent"))
    elif intent == "HELP":
        replies.append(_out(db, j, now, outreach.render("menu", lang, name=first), lang, status="sent", intent="MENU",
                            note="Auto-sent barrier menu"))
    elif intent == "BARRIER":
        b = parsed["barrier"]
        if b:
            set_barrier(db, j, b, now, actor="outreach-agent", role="system")
        key = f"support_{b}" if b else "support_OTHER"
        replies.append(_out(db, j, now, outreach.render(key, lang, name=first), lang, status="pending_approval",
                            intent="SUPPORT", note="Draft promises support - waits for coordinator approval."))
    else:
        log_event(db, j, now, "note", detail="Message not understood - needs human reading", actor="system")
        inbound.note = "Not understood - a coordinator should read this."

    audit(db, now, actor, "patient", f"message.inbound:{intent}", "journey", j.id, text[:120])
    return {"parsed": parsed, "inbound": inbound, "replies": replies}


def approve_message(db: Session, m: Message, now: datetime, *, approve: bool, actor: str, role: str) -> None:
    if m.status != "pending_approval":
        raise ValueError("Message is not waiting for approval.")
    if approve and not m.journey.patient.consent_outreach:
        approve = False                                   # consent withdrawn while the draft was waiting
    m.status = "sent" if approve else "rejected"
    m.ts = now if approve else m.ts
    j = m.journey
    log_event(db, j, now, "message", channel=m.channel, detail=("approved & sent" if approve else "rejected") + f": {m.intent or ''}",
              actor=actor)
    audit(db, now, actor, role, "message.approve" if approve else "message.reject", "message", m.id, m.text[:100])


# ---------------------------------------------------------------------------------- time-based sweep
def sweep(db: Session, now: datetime) -> int:
    """Auto-detect no-shows: booked appointments whose date passed >1 day ago with no attendance."""
    changed = 0
    q = (select(Journey).where(Journey.state == "SCHEDULED")
         .options(selectinload(Journey.appointments), selectinload(Journey.patient)))
    for j in db.execute(q).scalars():
        appt = current_appointment(j)
        if appt and appt.status == "booked" and appt.scheduled_for < now - timedelta(days=1):
            appt.status = "no_show"
            j.missed_appointments += 1
            j.last_no_show_at = now
            transition(db, j, "CONTACTED", now, actor="system", role="system", detail="No-show detected - back to rescheduling")
            log_event(db, j, now, "no_show", detail=f"Missed {appt.scheduled_for:%d %b}", actor="system")
            changed += 1
    return changed


# ---------------------------------------------------------------------------------- serialisers
def patient_dict(p: Patient) -> dict:
    return {"id": p.id, "name": p.name, "age": p.age, "sex": p.sex, "village": p.village,
            "language": p.language, "language_name": outreach.LANGS.get(p.language, p.language),
            "phone": p.phone, "abha_id": p.abha_id, "consent_outreach": p.consent_outreach}


def journey_card(j: Journey, now: datetime, rules: dict, *, detail: bool = False) -> dict:
    gaps = detect_gaps(j, now, rules)
    score, breakdown, bucket = score_journey(j, gaps, j.patient, now, rules)
    fac_name = j.facility.name if j.facility else "the referral facility"
    nba = next_best_action(j, j.patient, fac_name, now, rules)
    appt = current_appointment(j)
    sla = sla_for(j, rules)
    card = {
        "id": j.id,
        "patient": patient_dict(j.patient),
        "state": j.state, "state_label": STATE_LABEL[j.state],
        "urgency": j.urgency, "department": j.department,
        "finding": j.screening.finding,
        "facility": j.facility.name if j.facility else None,
        "facility_id": j.facility_id,
        "distance_km": j.distance_km,
        "age_in_state_days": round(days_between(j.state_since, now), 1),
        "journey_age_days": round(days_between(j.opened_at, now), 1),
        "sla_days": sla,
        "barrier": j.barrier,
        "barrier_label": outreach.BARRIERS.get(j.barrier) if j.barrier else None,
        "contact_attempts": j.contact_attempts, "failed_contacts": j.failed_contacts,
        "missed_appointments": j.missed_appointments,
        "clinical_flag": j.clinical_flag,
        "score": score, "bucket": bucket, "score_breakdown": breakdown,
        "gaps": gaps,
        "nba": nba,
        "appointment": ({"id": appt.id, "when": appt.scheduled_for.isoformat(), "status": appt.status,
                         "confirmed": appt.patient_confirmed, "facility": appt.facility.name} if appt else None),
        "ring": ring_segments(j, gaps),
        "closed_at": j.closed_at.isoformat() if j.closed_at else None,
        "close_reason": j.close_reason,
    }
    if detail:
        card["events"] = [{"id": e.id, "ts": e.ts.isoformat(), "kind": e.kind, "from": e.from_state, "to": e.to_state,
                           "channel": e.channel, "detail": e.detail, "actor": e.actor} for e in j.events]
        card["messages"] = [message_dict(m) for m in j.messages]
        card["screening"] = {"camp": j.screening.camp, "screened_at": j.screening.screened_at.isoformat(),
                             "finding": j.screening.finding}
        card["appointments"] = [{"id": a.id, "when": a.scheduled_for.isoformat(), "status": a.status,
                                 "confirmed": a.patient_confirmed, "facility": a.facility.name} for a in j.appointments]
    return card


def message_dict(m: Message) -> dict:
    return {"id": m.id, "journey_id": m.journey_id, "ts": m.ts.isoformat(), "direction": m.direction,
            "channel": m.channel, "language": m.language, "text": m.text, "intent": m.intent,
            "barrier": m.barrier, "status": m.status, "flag": m.flag, "note": m.note}


def open_journeys(db: Session) -> list[Journey]:
    q = (select(Journey).where(Journey.state.in_(OPEN_STATES)).options(
        selectinload(Journey.patient), selectinload(Journey.screening), selectinload(Journey.facility),
        selectinload(Journey.appointments).selectinload(Appointment.facility)))
    return list(db.execute(q).scalars())


def all_journeys(db: Session) -> list[Journey]:
    q = select(Journey).options(selectinload(Journey.patient))
    return list(db.execute(q).scalars())
