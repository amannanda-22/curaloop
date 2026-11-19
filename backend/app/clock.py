"""Simulated clock ("time machine").

A care loop is slow (days/weeks). To demo SLA breaches, escalations and no-shows in a 3-minute
presentation, the app keeps a clock offset in the DB. `now(db)` = real UTC + offset.
Real deployments simply leave the offset at 0.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .models import Setting

KEY = "clock_offset_days"


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_offset(db: Session) -> float:
    row = db.get(Setting, KEY)
    return float(row.value) if row and row.value is not None else 0.0


def set_offset(db: Session, days: float) -> None:
    row = db.get(Setting, KEY)
    if row is None:
        db.add(Setting(key=KEY, value=float(days)))
    else:
        row.value = float(days)
    db.flush()


def now(db: Session) -> datetime:
    return utcnow() + timedelta(days=get_offset(db))


def advance(db: Session, days: float) -> datetime:
    set_offset(db, get_offset(db) + days)
    return now(db)
