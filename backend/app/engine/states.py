"""The closed-loop state machine.

    SCREENED -> REFERRED -> CONTACTED -> SCHEDULED -> ATTENDED -> CLOSED
                   |            |            |
                  LOST         LOST   (no-show) back to CONTACTED

The rule that makes this a *closed loop* and not a tracker:
    A journey can only reach CLOSED when the RECEIVING FACILITY confirms the outcome.
    A coordinator ticking a box is not enough.
"""

STATES = ["SCREENED", "REFERRED", "CONTACTED", "SCHEDULED", "ATTENDED", "CLOSED", "LOST"]
IDEAL_PATH = ["SCREENED", "REFERRED", "CONTACTED", "SCHEDULED", "ATTENDED", "CLOSED"]
OPEN_STATES = {"SCREENED", "REFERRED", "CONTACTED", "SCHEDULED", "ATTENDED"}
TERMINAL_STATES = {"CLOSED", "LOST"}

STATE_LABEL = {
    "SCREENED": "Screened",
    "REFERRED": "Referred",
    "CONTACTED": "Patient reached",
    "SCHEDULED": "Appointment booked",
    "ATTENDED": "Attended",
    "CLOSED": "Loop closed",
    "LOST": "Lost to follow-up",
}

ALLOWED = {
    "SCREENED": {"REFERRED", "LOST"},
    "REFERRED": {"CONTACTED", "LOST"},
    "CONTACTED": {"SCHEDULED", "LOST"},
    "SCHEDULED": {"ATTENDED", "CONTACTED"},  # CONTACTED = no-show / reschedule loop
    "ATTENDED": {"CLOSED"},
    "CLOSED": set(),
    "LOST": set(),
}

OUTCOME_CODES = {
    "SEEN_PLAN_DOCUMENTED": "Seen - care plan documented",
    "TREATMENT_STARTED": "Treatment / management started",
    "REFERRED_ONWARD": "Referred onward to higher centre",
    "NO_FURTHER_CARE_NEEDED": "No further care needed",
}


class TransitionError(Exception):
    """Raised when a state change would break the closed-loop rules."""


def can_transition(src: str, dst: str) -> bool:
    return dst in ALLOWED.get(src, set())


def validate_transition(src: str, dst: str, *, via: str | None = None, role: str | None = None,
                        reason: str | None = None) -> None:
    if not can_transition(src, dst):
        raise TransitionError(f"Illegal transition {src} -> {dst}")
    if dst == "CLOSED" and via != "facility_outcome":
        raise TransitionError(
            "A journey can only be CLOSED when the receiving facility confirms the outcome "
            "(closed-loop rule). Ask the facility desk to confirm."
        )
    if dst == "ATTENDED" and via not in ("facility_attendance", "system_demo"):
        raise TransitionError("Attendance must be confirmed by the receiving facility.")
    if dst == "LOST":
        if role not in ("manager",):
            raise TransitionError("Only a programme manager can close a journey as lost to follow-up.")
        if not reason:
            raise TransitionError("A reason is required to close as lost.")
