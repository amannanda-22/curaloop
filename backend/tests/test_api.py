"""End-to-end API tests: the full Lakshmi journey, RBAC, closed-loop rule, validation, analytics."""
import pytest

from conftest import H


@pytest.fixture(scope="module")
def mclient():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        assert c.post("/api/demo/reset").status_code == 200
        yield c


def hero(c):
    return c.get("/api/meta").json()["hero_journey_id"]


# ------------------------------------------------------------------ seed sanity
def test_health_and_meta(mclient):
    assert mclient.get("/api/health").json()["synthetic_data"] is True
    m = mclient.get("/api/meta").json()
    assert set(m["roles"]) == {"coordinator", "facility", "manager"} and len(m["facilities"]) >= 4


def test_worklist_is_ranked_and_contains_hero(mclient):
    wl = mclient.get("/api/worklist?limit=200").json()
    scores = [i["score"] for i in wl["items"]]
    assert scores == sorted(scores, reverse=True) and wl["total"] > 20
    assert hero(mclient) in [i["id"] for i in wl["items"]]
    assert all(i["gaps"] or i["state"] == "SCREENED" for i in wl["items"])


def test_every_flag_explains_itself(mclient):
    for item in mclient.get("/api/worklist?limit=30").json()["items"]:
        assert item["score_breakdown"] and item["nba"]["why"] and item["nba"]["title"]
        assert sum(p["points"] for p in item["score_breakdown"]) == item["score"]


def test_funnel_is_monotonic_and_names_biggest_leak(mclient):
    f = mclient.get("/api/insights/funnel").json()
    counts = [s["count"] for s in f["stages"]]
    assert counts == sorted(counts, reverse=True) and f["biggest_leak"]["dropped"] > 0


def test_summary_kpis_present(mclient):
    s = mclient.get("/api/insights/summary").json()
    for k in ("patients_flagged", "referral_rate_pct", "loop_closure_rate_pct", "missed_appointment_rate_pct",
              "avg_referral_delay_days", "open_with_gaps", "median_days_to_close"):
        assert k in s and s[k] is not None


def test_planted_patterns_are_recovered(mclient):
    checks = mclient.get("/api/insights/patterns").json()["checks"]
    assert {c["status"] for c in checks} == {"recovered"}
    far = checks[0]
    assert far["recovered"]["rr"] > 1.3  # direction and size are right


def test_fairness_audit_flags_planted_disparity(mclient):
    groups = {g["dimension"]: g for g in mclient.get("/api/insights/fairness").json()["groups"]}
    assert any(r["flag"] for r in groups["Sex"]["rows"] + groups["Distance to facility"]["rows"])


def test_process_mining_has_bottleneck_and_rework(mclient):
    pm = mclient.get("/api/insights/process").json()
    assert pm["bottleneck"] and pm["conformance"]["with_rework_loops"] > 0 and pm["variants"]


def test_survival_strata_ordered_by_distance(mclient):
    s = mclient.get("/api/insights/survival").json()
    by = {x["name"]: x for x in s["strata"]}
    assert by["20+ km"]["closed_by_day_30_pct"] < by["<10 km"]["closed_by_day_30_pct"]


# ------------------------------------------------------------------ optimizer & simulator
def test_planner_respects_capacity_and_beats_fcfs(mclient):
    r = mclient.post("/api/planner/optimize", json={"calls": 12, "asha_visits": 4}).json()
    acts = [p["action"] for p in r["plan"]]
    assert acts.count("call") <= 12 and acts.count("asha_visit") <= 4
    assert r["expected_extra_closures"] >= r["fcfs_extra_closures"]
    assert "assumption" in r["assumption_note"].lower() or "priors" in r["assumption_note"].lower()


def test_more_capacity_never_hurts(mclient):
    small = mclient.post("/api/planner/optimize", json={"calls": 5, "asha_visits": 1}).json()
    big = mclient.post("/api/planner/optimize", json={"calls": 40, "asha_visits": 10}).json()
    assert big["expected_extra_closures"] >= small["expected_extra_closures"]


def test_whatif_extra_asha_increases_closures(mclient):
    r = mclient.post("/api/planner/simulate", json={"extra_asha": 4, "sms_two_way_pct": 0.6, "transport_support": True}).json()
    assert r["scenario"]["final_mean"] > r["baseline"]["final_mean"]
    assert r["scenario"]["p05"][-1] <= r["scenario"]["mean"][-1] <= r["scenario"]["p95"][-1]


# ------------------------------------------------------------------ RBAC / validation / errors
def test_unknown_role_rejected(mclient):
    r = mclient.post(f"/api/journeys/{hero(mclient)}/barrier", json={"barrier": "COST"}, headers={"X-Role": "hacker"})
    assert r.status_code == 400


def test_validation_errors_are_422(mclient):
    r = mclient.post(f"/api/journeys/{hero(mclient)}/contact", json={"channel": "pigeon", "outcome": "sent"}, headers=H())
    assert r.status_code == 422
    r = mclient.post("/api/screenings", json={"name": "A", "finding": "x", "urgency": "URGENT", "department": "y"}, headers=H())
    assert r.status_code == 422


def test_missing_journey_is_404(mclient):
    assert mclient.get("/api/journeys/999999").status_code == 404


def test_coordinator_cannot_close_the_loop(mclient):
    j = hero(mclient)
    assert mclient.post(f"/api/journeys/{j}/outcome", json={"outcome_code": "SEEN_PLAN_DOCUMENTED"}, headers=H("coordinator")).status_code == 403
    assert mclient.post(f"/api/journeys/{j}/attend", headers=H("coordinator")).status_code == 403
    assert mclient.post(f"/api/journeys/{j}/outcome", json={"outcome_code": "SEEN_PLAN_DOCUMENTED"}, headers=H("manager")).status_code == 403


def test_facility_cannot_skip_states(mclient):
    j = hero(mclient)  # REFERRED
    r = mclient.post(f"/api/journeys/{j}/outcome", json={"outcome_code": "SEEN_PLAN_DOCUMENTED"}, headers=H("facility"))
    assert r.status_code == 409


def test_only_manager_can_close_lost(mclient):
    j = hero(mclient)
    assert mclient.post(f"/api/journeys/{j}/close-lost", json={"reason": "test"}, headers=H("coordinator")).status_code == 409
    assert mclient.put("/api/rules", json={"capacity": {"calls": 30}}, headers=H("coordinator")).status_code == 403
    r = mclient.put("/api/rules", json={"capacity": {"calls": 30}}, headers=H("manager"))
    assert r.status_code == 200 and r.json()["capacity"]["calls"] == 30
    mclient.put("/api/rules", json={"capacity": {"calls": 25}}, headers=H("manager"))


# ------------------------------------------------------------------ patient registry
def test_register_screening_then_refer(mclient):
    r = mclient.post("/api/screenings", headers=H(), json={
        "name": "Test Patient", "age": 55, "sex": "F", "phone": "+91 90000 99999", "language": "te",
        "village": "Anandapuram", "finding": "Elevated blood pressure reading", "urgency": "HIGH",
        "department": "General Medicine (NCD clinic)", "camp": "Test camp"})
    assert r.status_code == 200 and r.json()["state"] == "SCREENED"
    jid = r.json()["id"]
    assert r.json()["nba"]["step"] == "REFER"
    fid = mclient.get("/api/meta").json()["facilities"][0]["id"]
    r2 = mclient.post(f"/api/journeys/{jid}/refer", json={"facility_id": fid}, headers=H())
    assert r2.json()["state"] == "REFERRED" and r2.json()["distance_km"] >= 0
    states = [e["to"] for e in r2.json()["events"] if e["kind"] == "state"]
    assert states == ["SCREENED", "REFERRED"]


def test_patient_search(mclient):
    r = mclient.get("/api/patients?q=Lakshmi").json()
    assert any(p["name"] == "Lakshmi Devi" and p["journeys"] for p in r)


# ------------------------------------------------------------------ the full story: Lakshmi
def test_lakshmi_full_loop_from_screening_to_closed(mclient):
    c, j = mclient, hero(mclient)

    # 1. flagged: SLA breach, explained, ladder says field visit (SMS + failed call already tried)
    card = c.get(f"/api/journeys/{j}").json()
    assert card["state"] == "REFERRED" and card["gaps"][0]["code"] == "NO_FIRST_CONTACT"
    assert card["nba"]["step"] == "ASHA"

    # 2. she replies on WhatsApp in Telugu -> barrier extracted, draft reply waits for approval
    res = c.post(f"/api/journeys/{j}/inbound", json={"text": "బస్సు లేదు, చాలా దూరం, డబ్బులు కూడా లేవు"}).json()
    assert res["parsed"]["intent"] == "BARRIER" and res["parsed"]["barrier"] == "TRANSPORT"
    card = res["journey"]
    assert card["state"] == "CONTACTED" and card["barrier"] == "TRANSPORT"
    pending = [m for m in card["messages"] if m["status"] == "pending_approval"]
    assert len(pending) == 1 and "ప్రయాణ" in pending[0]["text"]
    assert any(a["id"] == pending[0]["id"] for a in c.get("/api/approvals").json())

    # 3. coordinator approves; next action now targets the barrier
    card = c.post(f"/api/messages/{pending[0]['id']}/decision", json={"approve": True}, headers=H()).json()
    assert all(m["status"] != "pending_approval" for m in card["messages"])
    assert card["nba"]["step"] == "BARRIER" and "travel" in card["nba"]["title"].lower()

    # 4. ASHA visit reaches her, appointment booked 3 days out, barrier resolved
    c.post(f"/api/journeys/{j}/contact", json={"channel": "asha_visit", "outcome": "reached", "note": "Arranged vehicle"}, headers=H())
    card = c.post(f"/api/journeys/{j}/schedule", json={"in_days": 3}, headers=H()).json()
    assert card["state"] == "SCHEDULED" and card["barrier"] is None and card["appointment"]["status"] == "booked"

    # 5. she confirms with "1" -> appointment confirmed automatically
    res = c.post(f"/api/journeys/{j}/inbound", json={"text": "1"}).json()
    assert res["journey"]["appointment"]["confirmed"] is True
    assert res["journey"]["nba"]["step"] == "WAIT"

    # 6. time passes; the facility (not the coordinator) records attendance
    c.post("/api/clock/advance", json={"days": 3}, headers=H())
    card = c.post(f"/api/journeys/{j}/attend", headers=H("facility")).json()
    assert card["state"] == "ATTENDED"
    assert card["nba"]["step"] == "FACILITY_NUDGE"

    # 7. loop closes ONLY when the facility confirms the outcome
    before = c.get("/api/insights/funnel").json()["stages"][-1]["count"]
    card = c.post(f"/api/journeys/{j}/outcome", json={"outcome_code": "TREATMENT_STARTED", "note": "Plan documented"}, headers=H("facility")).json()
    assert card["state"] == "CLOSED" and card["nba"] is None and card["closed_at"]
    assert c.get("/api/insights/funnel").json()["stages"][-1]["count"] == before + 1

    # 8. the whole story is in the event log and audit trail
    kinds = [e["to"] for e in card["events"] if e["kind"] == "state"]
    assert kinds == ["SCREENED", "REFERRED", "CONTACTED", "SCHEDULED", "ATTENDED", "CLOSED"]
    actions = [a["action"] for a in c.get("/api/audit?limit=200").json()]
    assert "state:ATTENDED->CLOSED" in actions and "message.approve" in actions
    # closed journeys leave the worklist
    assert j not in [i["id"] for i in c.get("/api/worklist?limit=300").json()["items"]]


def test_fhir_bundle_for_closed_journey(mclient):
    b = mclient.get(f"/api/fhir/journey/{hero(mclient)}").json()
    types = [e["resource"]["resourceType"] for e in b["entry"]]
    assert b["resourceType"] == "Bundle" and {"Patient", "ServiceRequest", "Appointment", "Communication"} <= set(types)
    sr = next(e["resource"] for e in b["entry"] if e["resource"]["resourceType"] == "ServiceRequest")
    assert sr["status"] == "completed" and b["meta"]["tag"][0]["code"] == "SYNTHETIC-DATA"


# ------------------------------------------------------------------ no-show, red flag, webhook
def _pick(c, state, **cond):
    for i in c.get("/api/worklist?limit=300").json()["items"]:
        if i["state"] == state and all(i.get(k) == v for k, v in cond.items()):
            return i
    return None


def test_noshow_is_detected_automatically(mclient):
    c = mclient
    item = _pick(c, "CONTACTED", barrier=None, missed_appointments=0)
    assert item, "need a CONTACTED journey in seed data"
    j = item["id"]
    card = c.post(f"/api/journeys/{j}/schedule", json={"in_days": 2}, headers=H()).json()
    assert card["state"] == "SCHEDULED"
    c.post("/api/clock/advance", json={"days": 5}, headers=H())
    card = c.get(f"/api/journeys/{j}").json()
    assert card["state"] == "CONTACTED" and card["missed_appointments"] == 1
    assert any(g["code"] == "MISSED_APPOINTMENT" for g in card["gaps"])
    assert card["appointments"][-1]["status"] == "no_show"


def test_red_flag_is_never_answered_with_advice(mclient):
    c = mclient
    item = _pick(c, "REFERRED") or _pick(c, "CONTACTED")
    j = item["id"]
    res = c.post(f"/api/journeys/{j}/inbound", json={"text": "I have chest pain and cannot breathe"}).json()
    card = res["journey"]
    assert res["parsed"]["red_flag"] and card["clinical_flag"] is True
    assert card["nba"]["step"] == "CLINICIAN" and card["bucket"] in ("critical", "high")
    reply = [m for m in card["messages"] if m["direction"] == "out"][-1]
    assert "108" in reply["text"] and reply["flag"] == "RED_FLAG"
    card = c.post(f"/api/journeys/{j}/clear-flag", headers=H()).json()
    assert card["clinical_flag"] is False


def test_whatsapp_webhook_maps_phone_to_journey(mclient):
    c = mclient
    item = _pick(c, "REFERRED") or _pick(c, "CONTACTED")
    phone = item["patient"]["phone"].replace("+91 ", "91").replace(" ", "")
    payload = {"entry": [{"changes": [{"value": {"messages": [{"from": phone, "text": {"body": "2"}}]}}]}]}
    r = c.post("/api/webhooks/whatsapp", json=payload).json()
    assert r["status"] in ("processed", "ignored")
    assert c.post("/api/webhooks/whatsapp", json={"junk": 1}).json()["status"] == "ignored"


def test_unknown_message_waits_for_human(mclient):
    item = _pick(mclient, "REFERRED") or _pick(mclient, "CONTACTED")
    res = mclient.post(f"/api/journeys/{item['id']}/inbound", json={"text": "zzzz qqqq"}).json()
    assert res["parsed"]["intent"] == "UNKNOWN"
    last_in = [m for m in res["journey"]["messages"] if m["direction"] == "in"][-1]
    assert last_in["note"] and "human" in last_in["note"].lower() or "coordinator" in last_in["note"].lower()
    assert res["journey"]["messages"][-1]["direction"] == "in"  # the agent did not guess a reply


def test_impact_endpoint_structure_and_honesty(client):
    r = client.get("/api/impact", params={"calls": 25, "asha_visits": 6}).json()
    assert r["open_cases"] > 0
    cb = r["closed_by_day"]
    assert cb["curaloop"] >= cb["status_quo"]                       # working the list beats ignoring it
    g = r["gain_vs_status_quo"]
    assert g["lo"] <= g["mean"] <= g["hi"]
    sw = r["sensitivity"]
    assert sw[0]["scale"] == 0.0 and abs(sw[0]["gain_mean"]) < 0.01  # zero effect => zero gain (sanity)
    assert all(a["gain_mean"] <= b["gain_mean"] + 0.5 for a, b in zip(sw, sw[1:]))  # monotone in effect size
    assert len(r["projection"]["rows"]) == len(sw) and r["evidence"][0]["url"].startswith("https://")
    assert any("synthetic" in h.lower() for h in r["honesty"])


def test_impact_validates_inputs(client):
    assert client.get("/api/impact", params={"baseline_closure": 1.5}).status_code == 422


def test_opt_out_stops_messages_and_is_audited(client):
    from conftest import H
    hero = client.get("/api/meta").json()["hero_journey_id"]
    r = client.post(f"/api/journeys/{hero}/inbound", json={"text": "STOP"}, headers=H()).json()
    assert r["parsed"]["intent"] == "OPT_OUT"
    assert r["journey"]["patient"]["consent_outreach"] is False
    blocked = client.post(f"/api/journeys/{hero}/messages/send", json={"template": "reminder"}, headers=H())
    assert blocked.status_code == 422 and "opted out" in blocked.json()["detail"]
    assert any(a["action"] == "consent.withdrawn" for a in client.get("/api/audit", headers=H("manager")).json())
    pid = r["journey"]["patient"]["id"]                     # staff can record consent again
    assert client.post(f"/api/patients/{pid}/consent", json={"consent": True}, headers=H()).json()["consent_outreach"] is True


def test_red_flag_beats_opt_out_and_export_is_deidentified(client):
    from app.engine.outreach import parse_message
    assert parse_message("stop, I am bleeding a lot")["intent"] == "RED_FLAG"
    assert client.get("/api/export/deidentified", headers={"X-Role": "coordinator"}).status_code == 403
    rows = client.get("/api/export/deidentified", headers={"X-Role": "manager"}).json()["rows"]
    assert rows and not ({"name", "phone", "abha_id", "village"} & set(rows[0]))
