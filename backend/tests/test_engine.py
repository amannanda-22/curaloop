from datetime import datetime, timedelta
from types import SimpleNamespace as NS

import numpy as np
import pytest

from app.engine import allocate, mining, nba, outreach, survival
from app.engine.gaps import detect_gaps, score_journey
from app.engine.rules import DEFAULT_RULES
from app.engine.states import TransitionError, can_transition, validate_transition

NOW = datetime(2026, 11, 18, 10, 0)
R = DEFAULT_RULES


def J(**kw):
    base = dict(state="REFERRED", urgency="HIGH", state_since=NOW - timedelta(days=5), opened_at=NOW - timedelta(days=6),
                appointments=[], last_no_show_at=None, missed_appointments=0, failed_contacts=0, contact_attempts=0,
                clinical_flag=False, barrier=None, events=[], facility=None)
    base.update(kw)
    return NS(**base)


P = NS(name="Lakshmi Devi", age=47, sex="F", language="te")


# ---- state machine -----------------------------------------------------------------------
def test_ideal_path_is_allowed():
    path = ["SCREENED", "REFERRED", "CONTACTED", "SCHEDULED", "ATTENDED", "CLOSED"]
    assert all(can_transition(a, b) for a, b in zip(path, path[1:]))


def test_no_skipping_steps():
    assert not can_transition("REFERRED", "SCHEDULED")
    assert not can_transition("CONTACTED", "CLOSED")


def test_noshow_loop_back_is_allowed():
    assert can_transition("SCHEDULED", "CONTACTED")


def test_closed_requires_facility_confirmation():
    with pytest.raises(TransitionError):
        validate_transition("ATTENDED", "CLOSED", via=None, role="coordinator")
    validate_transition("ATTENDED", "CLOSED", via="facility_outcome", role="facility")


def test_only_manager_can_mark_lost_with_reason():
    with pytest.raises(TransitionError):
        validate_transition("REFERRED", "LOST", role="coordinator", reason="x")
    with pytest.raises(TransitionError):
        validate_transition("REFERRED", "LOST", role="manager", reason="")
    validate_transition("REFERRED", "LOST", role="manager", reason="Unreachable")


# ---- gaps & scoring ----------------------------------------------------------------------
def test_sla_breach_detected_and_explained():
    gaps = detect_gaps(J(), NOW, R)
    assert gaps and gaps[0]["code"] == "NO_FIRST_CONTACT"
    assert "SLA" in gaps[0]["detail"]


def test_within_sla_has_no_gap():
    assert detect_gaps(J(state_since=NOW - timedelta(days=1)), NOW, R) == []


def test_routine_has_longer_sla_than_high():
    j = J(urgency="ROUTINE", state_since=NOW - timedelta(days=4))
    assert detect_gaps(j, NOW, R) == []
    assert detect_gaps(J(state_since=NOW - timedelta(days=4)), NOW, R)


def test_missed_appointment_gap_after_noshow():
    t = NOW - timedelta(days=2)
    j = J(state="CONTACTED", state_since=t, last_no_show_at=t, missed_appointments=1)
    assert any(g["code"] == "MISSED_APPOINTMENT" for g in detect_gaps(j, NOW, R))


def test_outcome_pending_is_a_facility_accountability_gap():
    j = J(state="ATTENDED", state_since=NOW - timedelta(days=6))
    assert any(g["code"] == "OUTCOME_PENDING" for g in detect_gaps(j, NOW, R))


def test_score_is_transparent_and_adds_up():
    j = J(failed_contacts=2, barrier="TRANSPORT")
    gaps = detect_gaps(j, NOW, R)
    total, parts, bucket = score_journey(j, gaps, P, NOW, R)
    assert total == sum(p["points"] for p in parts) and total > 0
    assert any("failed" in p["label"] for p in parts)


def test_closed_journeys_score_zero():
    total, _, bucket = score_journey(J(state="CLOSED"), [], P, NOW, R)
    assert total == 0 and bucket == "closed"


def test_clinical_flag_outranks_everything():
    a = score_journey(J(), detect_gaps(J(), NOW, R), P, NOW, R)[0]
    jf = J(clinical_flag=True)
    b = score_journey(jf, detect_gaps(jf, NOW, R), P, NOW, R)[0]
    assert b >= a + 40


# ---- next best action --------------------------------------------------------------------
def test_ladder_escalates_with_attempts():
    steps = []
    for attempts in range(4):
        j = J(contact_attempts=attempts)
        steps.append(nba.next_best_action(j, P, "CHC", NOW, R)["step"])
    assert steps == ["SMS", "CALL", "ASHA", "SUPERVISOR"]


def test_barrier_overrides_ladder():
    a = nba.next_best_action(J(barrier="TRANSPORT", contact_attempts=1), P, "CHC", NOW, R)
    assert a["step"] == "BARRIER" and a["unit"] == "asha_visit" and "travel" in a["title"].lower()


def test_cost_barrier_suggests_scheme_check():
    a = nba.next_best_action(J(barrier="COST"), P, "CHC", NOW, R)
    assert "PM-JAY" in a["title"]


def test_failed_calls_escalate_call_actions_to_asha():
    a = nba.next_best_action(J(barrier="UNDERSTANDING", failed_contacts=2), P, "CHC", NOW, R)
    assert a["unit"] == "asha_visit"


def test_clinical_flag_never_gives_chat_advice():
    a = nba.next_best_action(J(clinical_flag=True), P, "CHC", NOW, R)
    assert a["step"] == "CLINICIAN" and a["script"] is None


def test_nba_script_is_in_patient_language():
    a = nba.next_best_action(J(), P, "CHC Anakapalle", NOW, R)
    assert "నమస్కారం" in a["script"]


def test_closed_journey_has_no_action():
    assert nba.next_best_action(J(state="CLOSED"), P, "CHC", NOW, R) is None


# ---- multilingual outreach agent ---------------------------------------------------------
@pytest.mark.parametrize("text,intent,barrier", [
    ("1", "CONFIRM", None), ("2", "RESCHEDULE", None), ("3", "HELP", None),
    ("yes I will come", "CONFIRM", None), ("haan theek hai", "CONFIRM", None),
    ("బస్సు లేదు, చాలా దూరం", "BARRIER", "TRANSPORT"),
    ("paisa nahi hai", "BARRIER", "COST"),
    ("naaku bhayam ga undi", "BARRIER", "FEAR"),
    ("मुझे डर लग रहा है", "BARRIER", "FEAR"),
    ("I can't take leave from work", "BARRIER", "WORK_LEAVE"),
    ("samajh nahi aaya", "BARRIER", "UNDERSTANDING"),
    ("can we do another day", "RESCHEDULE", None),
])
def test_parse_intents(text, intent, barrier):
    r = outreach.parse_message(text)
    assert r["intent"] == intent and r["barrier"] == barrier


@pytest.mark.parametrize("text", ["I have chest pain", "सीने में दर्द है", "ఛాతీ నొప్పి గా ఉంది", "bleeding a lot"])
def test_red_flags_detected_in_three_languages(text):
    r = outreach.parse_message(text)
    assert r["red_flag"] and r["intent"] == "RED_FLAG"


def test_menu_reply_maps_digit_to_barrier():
    assert outreach.parse_message("1", awaiting_menu=True)["barrier"] == "TRANSPORT"
    assert outreach.parse_message("2", awaiting_menu=True)["barrier"] == "COST"


def test_telugu_digits_and_language_detection():
    assert outreach.parse_message("౧")["intent"] == "CONFIRM"
    assert outreach.detect_language("బస్సు లేదు") == "te"
    assert outreach.detect_language("मदद चाहिए") == "hi"


def test_unknown_message_is_not_guessed():
    assert outreach.parse_message("asdf qwerty")["intent"] == "UNKNOWN"


def test_all_templates_exist_in_all_languages():
    for name, block in outreach.T.items():
        assert set(block) == {"en", "hi", "te"}, name


def test_no_template_gives_medical_advice_words():
    banned = ["take medicine", "dose", "diagnos", "prescri"]
    for block in outreach.T.values():
        for text in block.values():
            assert not any(b in text.lower() for b in banned)


# ---- survival ----------------------------------------------------------------------------
def test_kaplan_meier_matches_hand_calculation():
    t, s = survival.kaplan_meier([1, 2, 3, 4], [1, 1, 0, 1])
    assert list(t) == [0, 1, 2, 4]
    assert np.allclose(s, [1, 0.75, 0.5, 0.0])
    assert survival.median_time(t, s) == 2


def test_censoring_is_not_treated_as_failure():
    t, s = survival.kaplan_meier([5, 5, 5, 10], [0, 0, 0, 1])
    assert s[-1] == pytest.approx(0.0)  # one at risk at day 10 -> closes -> survival 0
    t2, s2 = survival.kaplan_meier([5, 5, 5, 10], [0, 0, 0, 0])
    assert list(s2) == [1.0]  # nobody closed: survival stays 1


def test_conditional_probability_in_range():
    t, s = survival.kaplan_meier([2, 4, 6, 8, 10, 12], [1, 1, 1, 1, 0, 1])
    p = survival.conditional_close_prob(t, s, 3, 14)
    assert 0 < p <= 1


# ---- optimizer ---------------------------------------------------------------------------
def test_optimizer_respects_capacity():
    items = [{"id": i, "base_p": 0.2, "weight": 1.0, "barrier": None, "age_rank": i} for i in range(30)]
    res = allocate.optimize(items, calls=5, visits=2)
    acts = [p["action"] for p in res["plan"]]
    assert acts.count("call") <= 5 and acts.count("asha_visit") <= 2
    assert acts.count("asha_visit") == 2 and acts.count("call") == 5


def test_optimizer_gives_visits_to_those_who_benefit_most():
    items = [
        {"id": 1, "base_p": 0.2, "weight": 1.0, "barrier": "UNREACHABLE", "age_rank": 1},   # visit lift .36
        {"id": 2, "base_p": 0.2, "weight": 1.0, "barrier": "RELOCATED", "age_rank": 2},     # visit lift only .06
    ]
    res = allocate.optimize(items, calls=1, visits=1)
    by_id = {p["id"]: p["action"] for p in res["plan"]}
    assert by_id[1] == "asha_visit" and by_id[2] == "call"


def test_optimizer_beats_or_matches_fcfs():
    rng = np.random.default_rng(1)
    barriers = [None, "TRANSPORT", "UNREACHABLE", "RELOCATED", "FEAR", "COST"]
    items = [{"id": i, "base_p": float(rng.uniform(0.05, 0.5)), "weight": float(rng.choice([1.0, 1.5])),
              "barrier": barriers[i % 6], "age_rank": -float(rng.uniform(0, 40))} for i in range(60)]
    res = allocate.optimize(items, calls=10, visits=4)
    assert res["expected_gain"] >= res["fcfs_gain"] - 1e-9


def test_optimizer_handles_empty():
    assert allocate.optimize([], 5, 5)["plan"] == []


# ---- process mining ----------------------------------------------------------------------
def ev(jid, to, day, i):
    return NS(journey_id=jid, kind="state", to_state=to, ts=datetime(2026, 1, 1) + timedelta(days=day), id=i)


def test_process_discovery_finds_rework_and_bottleneck():
    events = [
        ev(1, "SCREENED", 0, 1), ev(1, "REFERRED", 1, 2), ev(1, "CONTACTED", 3, 3), ev(1, "SCHEDULED", 4, 4),
        ev(1, "ATTENDED", 6, 5), ev(1, "CLOSED", 7, 6),
        ev(2, "SCREENED", 0, 7), ev(2, "REFERRED", 1, 8), ev(2, "CONTACTED", 11, 9), ev(2, "SCHEDULED", 12, 10),
        ev(2, "CONTACTED", 15, 11), ev(2, "SCHEDULED", 16, 12),
    ]
    res = mining.discover(mining.traces_from_events(events))
    assert res["conformance"]["journeys"] == 2
    assert res["conformance"]["with_rework_loops"] == 1
    assert any(e["back_edge"] for e in res["edges"])
    assert (res["bottleneck"]["from"], res["bottleneck"]["to"]) == ("REFERRED", "CONTACTED")
