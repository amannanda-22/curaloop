"""Barrier-aware Next-Best-Action (NBA) engine.

Two ideas combined:
  1. ESCALATION LADDER - SMS -> coordinator call -> ASHA home visit -> supervisor review.
     Position on the ladder comes from how many outreach attempts have already been made.
  2. BARRIER MAPPING - once a reason is known (transport, cost, fear, ...), the action is the one
     that removes THAT barrier, not just "try again".

Rule-based on purpose: a care coordinator must be able to read why the system suggests something.
The `effect` numbers are expert priors used by the optimizer; they are editable assumptions and
are never presented as learned accuracy.
"""
from __future__ import annotations

from . import outreach
from .gaps import current_appointment, days_between, sla_for

LADDER = [
    {"step": "SMS", "channel": "sms", "unit": "sms", "owner": "System (WhatsApp/SMS)",
     "title": "Send two-way WhatsApp/SMS reminder"},
    {"step": "CALL", "channel": "call", "unit": "call", "owner": "Care coordinator",
     "title": "Call the patient"},
    {"step": "ASHA", "channel": "asha_visit", "unit": "asha_visit", "owner": "ASHA / field worker",
     "title": "Arrange an ASHA home visit"},
    {"step": "SUPERVISOR", "channel": "supervisor_review", "unit": "supervisor", "owner": "Programme manager",
     "title": "Supervisor review: decide to continue or close as lost"},
]

BARRIER_ACTIONS = {
    "TRANSPORT": dict(unit="asha_visit", channel="asha_visit", owner="ASHA / field worker",
                      title="ASHA visit + arrange travel support",
                      detail="Group the visit with a transport-supported day (108/PHC vehicle) or accompany the patient."),
    "COST": dict(unit="call", channel="call", owner="Care coordinator",
                 title="Check PM-JAY / state scheme eligibility and call patient",
                 detail="Confirm which government health scheme can cover the visit and explain it to the patient."),
    "FEAR": dict(unit="asha_visit", channel="asha_visit", owner="ASHA / field worker",
                 title="ASHA counselling visit",
                 detail="In-person reassurance and logistics support. No clinical advice - questions go to the facility doctor."),
    "UNDERSTANDING": dict(unit="call", channel="call", owner="Care coordinator",
                          title="Call and explain the next step in the patient's language",
                          detail="Use teach-back: ask the patient to repeat where/when to go."),
    "WORK_LEAVE": dict(unit="call", channel="call", owner="Care coordinator",
                       title="Offer an evening/weekend slot",
                       detail="Ask the facility desk for a slot outside working hours; call to book."),
    "UNREACHABLE": dict(unit="asha_visit", channel="asha_visit", owner="ASHA / field worker",
                        title="Verify contact via ASHA home visit",
                        detail="Phone is not working. Verify the number with family / ABHA record during a visit."),
    "RELOCATED": dict(unit="call", channel="call", owner="Care coordinator",
                      title="Transfer the referral to the nearest facility",
                      detail="Get the new location and re-issue the referral to a nearby facility."),
}

# Expert priors: absolute lift in 14-day loop-closure probability when an action is taken.
# ASSUMPTIONS - editable, not learned. Shown as such in the UI.
ACTION_EFFECT = {
    "sms": {"default": 0.05, "UNREACHABLE": 0.0, "UNDERSTANDING": 0.03, "FEAR": 0.02, "TRANSPORT": 0.02, "COST": 0.02},
    "call": {"default": 0.14, "UNDERSTANDING": 0.26, "WORK_LEAVE": 0.22, "COST": 0.2, "FEAR": 0.16,
             "TRANSPORT": 0.08, "UNREACHABLE": 0.02, "RELOCATED": 0.18},
    "asha_visit": {"default": 0.26, "TRANSPORT": 0.32, "UNREACHABLE": 0.36, "FEAR": 0.34, "COST": 0.2,
                   "UNDERSTANDING": 0.3, "WORK_LEAVE": 0.14, "RELOCATED": 0.06},
}


def effect_of(unit: str, barrier: str | None) -> float:
    table = ACTION_EFFECT.get(unit)
    if not table:
        return 0.0
    return table.get(barrier or "default", table["default"])


def _rationale(journey, gaps, rules) -> list[str]:
    sla = sla_for(journey, rules)
    why = []
    for g in gaps:
        why.append(g["detail"])
    if journey.contact_attempts:
        why.append(f"{journey.contact_attempts} outreach attempt(s) so far, {journey.failed_contacts} failed.")
    if journey.barrier:
        why.append(f"Barrier reported: {outreach.BARRIERS.get(journey.barrier, journey.barrier)}.")
    if sla is not None and not gaps:
        why.append(f"Within SLA ({sla:g} day(s) allowed in this stage).")
    return why


def next_best_action(journey, patient, facility_name: str, now, rules: dict) -> dict | None:
    """Return the single next action for this journey (or None when the loop is closed)."""
    if journey.state in ("CLOSED", "LOST"):
        return None
    gaps_rationale = None  # computed lazily by caller for performance; here we recompute cheaply
    from .gaps import detect_gaps

    gaps = detect_gaps(journey, now, rules)
    gaps_rationale = _rationale(journey, gaps, rules)
    lang = patient.language
    first = patient.name.split()[0]
    appt = current_appointment(journey)
    action: dict

    if journey.clinical_flag:
        action = dict(step="CLINICIAN", unit="clinician", channel="clinician", owner="Clinician on duty",
                      title="Hand over to a clinician - do not advise via chat",
                      detail="Patient described symptoms. Coordinator must not give medical advice; escalate now.",
                      script=None)
    elif journey.state == "SCREENED":
        action = dict(step="REFER", unit="referral", channel="referral", owner="Care coordinator",
                      title="Raise the referral now",
                      detail="Choose the receiving facility and department so the loop can start.", script=None)
    elif journey.state == "ATTENDED":
        action = dict(step="FACILITY_NUDGE", unit="facility_nudge", channel="sms", owner="Facility desk",
                      title="Ask the facility to confirm the visit outcome",
                      detail="The loop closes only when the facility confirms the outcome.",
                      script=outreach.render("facility_nudge", "en", name=patient.name,
                                             when=f"{journey.state_since:%d %b}"))
    elif journey.state == "SCHEDULED" and appt and appt.status == "booked" and appt.scheduled_for >= now:
        days_to = days_between(now, appt.scheduled_for)
        if appt.patient_confirmed:
            action = dict(step="WAIT", unit="none", channel="none", owner="-", title="Patient confirmed - no action needed",
                          detail=f"Visit on {appt.scheduled_for:%d %b}. The facility will mark attendance.", script=None)
        else:
            action = dict(step="REMIND", unit="sms", channel="sms", owner="System (WhatsApp/SMS)",
                          title="Send appointment reminder (2-way confirm)",
                          detail=f"Appointment in {days_to:.0f} day(s). Unconfirmed appointments are the biggest no-show risk.",
                          script=outreach.render("appt_reminder", lang, name=first, facility=facility_name,
                                                 when=f"{appt.scheduled_for:%d %b}"))
    elif journey.barrier and journey.barrier in BARRIER_ACTIONS:
        base = dict(BARRIER_ACTIONS[journey.barrier])
        if journey.failed_contacts >= 2 and base["unit"] == "call":
            base.update(unit="asha_visit", channel="asha_visit", owner="ASHA / field worker",
                        title="Escalate to ASHA visit (calls are not working)",
                        detail=base["detail"] + " Escalated because two or more calls failed.")
        base["step"] = "BARRIER"
        base["script"] = outreach.render(f"support_{journey.barrier}", lang, name=first) \
            if f"support_{journey.barrier}" in outreach.T else None
        action = base
    else:
        idx = min(journey.contact_attempts, len(LADDER) - 1)
        if journey.failed_contacts >= 2:
            idx = max(idx, 2)  # phone route is not working
        step = dict(LADDER[idx])
        action = dict(step=step["step"], unit=step["unit"], channel=step["channel"], owner=step["owner"],
                      title=step["title"], detail=f"Escalation ladder step {idx + 1} of {len(LADDER)}.", script=None)
        if step["step"] == "SMS":
            action["script"] = outreach.render("reminder", lang, name=first, facility=facility_name)
        elif step["step"] == "CALL":
            action["detail"] += " Ask what is stopping the visit and log the barrier."
        elif step["step"] == "ASHA":
            action["detail"] += " SMS and calls did not close the loop."

    action["effect"] = round(effect_of(action["unit"], journey.barrier), 2) if action["unit"] in ACTION_EFFECT else 0.0
    action["why"] = gaps_rationale
    action["ladder"] = [s["step"] for s in LADDER]
    return action
