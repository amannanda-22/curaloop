"""Relational schema. Names follow FHIR R4 concepts so an export is a mapping, not a rewrite:

  Patient          -> FHIR Patient
  Journey          -> FHIR ServiceRequest (the referral) + CarePlan-like state
  Appointment      -> FHIR Appointment
  Event            -> FHIR Provenance / AuditEvent style journey log
  Message          -> FHIR Communication
  Facility         -> FHIR Organization / Location

All patient data in this project is SYNTHETIC.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Facility(Base):
    __tablename__ = "facilities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(40))  # PHC / CHC / Area Hospital / District Hospital
    area: Mapped[str] = mapped_column(String(80))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)


class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    abha_id: Mapped[str] = mapped_column(String(32), index=True)   # synthetic 14-digit style id
    name: Mapped[str] = mapped_column(String(120))
    age: Mapped[int] = mapped_column(Integer)
    sex: Mapped[str] = mapped_column(String(1))                    # F / M
    phone: Mapped[str] = mapped_column(String(24), index=True)     # synthetic
    language: Mapped[str] = mapped_column(String(4), default="te")  # te / hi / en
    village: Mapped[str] = mapped_column(String(80))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    consent_outreach: Mapped[bool] = mapped_column(Boolean, default=True)   # False after STOP / withdrawn consent


class Screening(Base):
    __tablename__ = "screenings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    camp: Mapped[str] = mapped_column(String(120))
    screened_at: Mapped[datetime] = mapped_column(DateTime)
    finding: Mapped[str] = mapped_column(String(120))   # screening-level flag, NOT a diagnosis
    urgency: Mapped[str] = mapped_column(String(8))     # HIGH / ROUTINE
    department: Mapped[str] = mapped_column(String(60))


class Journey(Base):
    """One screening-to-care journey (== one referral / ServiceRequest)."""

    __tablename__ = "journeys"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    screening_id: Mapped[int] = mapped_column(ForeignKey("screenings.id"))
    facility_id: Mapped[int | None] = mapped_column(ForeignKey("facilities.id"), nullable=True)
    department: Mapped[str] = mapped_column(String(60))
    urgency: Mapped[str] = mapped_column(String(8))
    state: Mapped[str] = mapped_column(String(16), index=True, default="SCREENED")
    state_since: Mapped[datetime] = mapped_column(DateTime)
    opened_at: Mapped[datetime] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    close_reason: Mapped[str | None] = mapped_column(String(160), nullable=True)
    barrier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    distance_km: Mapped[float] = mapped_column(Float, default=0.0)
    contact_attempts: Mapped[int] = mapped_column(Integer, default=0)
    failed_contacts: Mapped[int] = mapped_column(Integer, default=0)
    missed_appointments: Mapped[int] = mapped_column(Integer, default=0)
    last_no_show_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    clinical_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    outcome_code: Mapped[str | None] = mapped_column(String(40), nullable=True)

    patient: Mapped[Patient] = relationship()
    screening: Mapped[Screening] = relationship()
    facility: Mapped[Facility | None] = relationship()
    appointments: Mapped[list["Appointment"]] = relationship(
        back_populates="journey", order_by="Appointment.scheduled_for"
    )
    events: Mapped[list["Event"]] = relationship(back_populates="journey", order_by="Event.ts, Event.id")
    messages: Mapped[list["Message"]] = relationship(back_populates="journey", order_by="Message.ts, Message.id")


class Appointment(Base):
    __tablename__ = "appointments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    journey_id: Mapped[int] = mapped_column(ForeignKey("journeys.id"), index=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"))
    scheduled_for: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(12), default="booked")  # booked/attended/no_show/cancelled
    patient_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)

    journey: Mapped[Journey] = relationship(back_populates="appointments")
    facility: Mapped[Facility] = relationship()


class Event(Base):
    """Append-only journey log. This table IS the event log used for process mining."""

    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    journey_id: Mapped[int] = mapped_column(ForeignKey("journeys.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    kind: Mapped[str] = mapped_column(String(24))  # state / contact / barrier / message / no_show / flag / note
    from_state: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_state: Mapped[str | None] = mapped_column(String(16), nullable=True)
    channel: Mapped[str | None] = mapped_column(String(16), nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String(40), default="system")

    journey: Mapped[Journey] = relationship(back_populates="events")


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    journey_id: Mapped[int] = mapped_column(ForeignKey("journeys.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime)
    direction: Mapped[str] = mapped_column(String(3))        # in / out
    channel: Mapped[str] = mapped_column(String(12), default="whatsapp")
    language: Mapped[str] = mapped_column(String(4), default="en")
    text: Mapped[str] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(20), nullable=True)
    barrier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="sent")  # sent/received/pending_approval/rejected
    flag: Mapped[str | None] = mapped_column(String(20), nullable=True)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)

    journey: Mapped[Journey] = relationship(back_populates="messages")


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    actor: Mapped[str] = mapped_column(String(60))
    role: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict | list | float | int | str | None] = mapped_column(JSON)
