"""Configurable, transparent rules. Stored in the DB (Setting 'rules') so a programme manager can
tune them without a deploy; these are the defaults.

IMPORTANT: nothing in here is a clinical rule. SLAs and weights are OPERATIONAL follow-up policy.
`action_effect` values are expert PRIORS (editable assumptions) - they are not learned from data and
are always labelled as such in the UI.
"""
from copy import deepcopy

from sqlalchemy.orm import Session

from ..models import Setting

DEFAULT_RULES = {
    # days a journey may sit in a state before it is an SLA breach
    "sla_days": {
        "HIGH": {"SCREENED": 1, "REFERRED": 2, "CONTACTED": 3, "ATTENDED": 3},
        "ROUTINE": {"SCREENED": 3, "REFERRED": 5, "CONTACTED": 7, "ATTENDED": 7},
    },
    # priority score weights (points) - every flag shows its breakdown
    "weights": {
        "urgency_high": 30,
        "overdue_per_day": 2,
        "overdue_cap": 30,
        "missed_appointment": 20,
        "failed_contact": 5,
        "failed_contact_cap": 15,
        "barrier_open": 5,
        "age_60_plus": 5,
        "clinical_flag": 40,
    },
    "buckets": {"critical": 70, "high": 45, "medium": 20},
    "capacity": {"calls": 25, "asha_visits": 6},
    "horizon_days": 14,
}


def get_rules(db: Session) -> dict:
    rules = deepcopy(DEFAULT_RULES)
    row = db.get(Setting, "rules")
    if row and isinstance(row.value, dict):
        for k, v in row.value.items():
            if isinstance(v, dict) and isinstance(rules.get(k), dict):
                for k2, v2 in v.items():
                    if isinstance(v2, dict) and isinstance(rules[k].get(k2), dict):
                        rules[k][k2].update(v2)
                    else:
                        rules[k][k2] = v2
            else:
                rules[k] = v
    return rules


def set_rules(db: Session, patch: dict) -> dict:
    current = get_rules(db)
    for k, v in patch.items():
        if k not in current:
            raise ValueError(f"unknown rule group: {k}")
        if isinstance(v, dict) and isinstance(current[k], dict):
            for k2, v2 in v.items():
                if isinstance(v2, dict) and isinstance(current[k].get(k2), dict):
                    current[k][k2].update(v2)
                else:
                    current[k][k2] = v2
        else:
            current[k] = v
    row = db.get(Setting, "rules")
    if row is None:
        db.add(Setting(key="rules", value=current))
    else:
        row.value = current
    db.flush()
    return current
