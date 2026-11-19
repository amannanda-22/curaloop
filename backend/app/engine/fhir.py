"""FHIR R4-aligned export of one journey (mapping layer, not a certified implementation).

Patient -> Patient;  Journey -> ServiceRequest;  Appointment -> Appointment;
open next action -> Task;  messages -> Communication.
The bundle is structurally FHIR-shaped but has not been validated against a national profile
(e.g. ABDM / NRCeS). All data is synthetic.
"""
from __future__ import annotations

SR_STATUS = {"SCREENED": "draft", "REFERRED": "active", "CONTACTED": "active", "SCHEDULED": "active",
             "ATTENDED": "active", "CLOSED": "completed", "LOST": "revoked"}
APPT_STATUS = {"booked": "booked", "attended": "fulfilled", "no_show": "noshow", "cancelled": "cancelled"}


def journey_bundle(j, nba: dict | None) -> dict:
    p = j.patient
    entries = []
    entries.append({"resource": {
        "resourceType": "Patient", "id": f"patient-{p.id}",
        "identifier": [{"system": "https://healthid.ndhm.gov.in", "value": p.abha_id}],
        "name": [{"text": p.name}], "gender": "female" if p.sex == "F" else "male",
        "telecom": [{"system": "phone", "value": p.phone}],
        "communication": [{"language": {"coding": [{"code": p.language}]}}],
        "address": [{"city": p.village, "country": "IN"}],
    }})
    entries.append({"resource": {
        "resourceType": "ServiceRequest", "id": f"referral-{j.id}",
        "status": SR_STATUS[j.state], "intent": "order",
        "priority": "urgent" if j.urgency == "HIGH" else "routine",
        "subject": {"reference": f"Patient/patient-{p.id}"},
        "authoredOn": j.opened_at.isoformat() + "Z",
        "performer": [{"display": j.facility.name}] if j.facility else [],
        "category": [{"text": "Screening follow-up referral"}],
        "code": {"text": j.department},
        "reasonCode": [{"text": j.screening.finding}],
        "note": [{"text": f"CuraLoop journey state: {j.state}" + (f"; barrier: {j.barrier}" if j.barrier else "")}],
    }})
    for a in j.appointments:
        entries.append({"resource": {
            "resourceType": "Appointment", "id": f"appt-{a.id}", "status": APPT_STATUS.get(a.status, "proposed"),
            "start": a.scheduled_for.isoformat() + "Z",
            "basedOn": [{"reference": f"ServiceRequest/referral-{j.id}"}],
            "participant": [{"actor": {"reference": f"Patient/patient-{p.id}"}, "status": "accepted" if a.patient_confirmed else "tentative"},
                            {"actor": {"display": a.facility.name}, "status": "accepted"}],
        }})
    if nba:
        entries.append({"resource": {
            "resourceType": "Task", "id": f"task-{j.id}", "status": "requested", "intent": "proposal",
            "focus": {"reference": f"ServiceRequest/referral-{j.id}"},
            "description": nba["title"], "owner": {"display": nba["owner"]},
        }})
    for m in j.messages:
        entries.append({"resource": {
            "resourceType": "Communication", "id": f"msg-{m.id}",
            "status": "completed" if m.status in ("sent", "received") else "preparation",
            "sent": m.ts.isoformat() + "Z", "medium": [{"text": m.channel}],
            "payload": [{"contentString": m.text}],
        }})
    return {"resourceType": "Bundle", "type": "collection", "entry": entries,
            "meta": {"tag": [{"system": "https://curaloop.example/tags", "code": "SYNTHETIC-DATA"}]}}
