"""ORM models (SQLAlchemy 2.0). Mirrors the data model in Architecture.md 6."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Integer, LargeBinary, String, Float, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def now_iso() -> str:
    return utcnow().isoformat()


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    org: Mapped[str] = mapped_column(String, default="default")
    role: Mapped[str] = mapped_column(String, index=True)
    auth_subject: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="active")
    granted_by: Mapped[str] = mapped_column(String, default="system")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class Printer(Base):
    __tablename__ = "printers"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    model: Mapped[str] = mapped_column(String, default="")
    driver_type: Mapped[str] = mapped_column(String, default="simulated")
    build_x: Mapped[int] = mapped_column(Integer, default=220)
    build_y: Mapped[int] = mapped_column(Integer, default=220)
    build_z: Mapped[int] = mapped_column(Integer, default=250)
    materials: Mapped[list] = mapped_column(JSON, default=list)
    tolerance_class: Mapped[str] = mapped_column(String, default="standard")
    location: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="idle", index=True)
    health: Mapped[str] = mapped_column(String, default="ok")
    device_pubkey: Mapped[str | None] = mapped_column(String, nullable=True)
    current_job: Mapped[str | None] = mapped_column(String, nullable=True)


class MaterialLot(Base):
    __tablename__ = "materials"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[str] = mapped_column(String, index=True)
    lot: Mapped[str] = mapped_column(String, default="")
    density: Mapped[float] = mapped_column(Float, default=1.24)
    nominal_temp: Mapped[float] = mapped_column(Float, default=210.0)
    cost_per_gram: Mapped[float] = mapped_column(Float, default=0.03)
    stock_qty: Mapped[float] = mapped_column(Float, default=1000.0)
    reserved_qty: Mapped[float] = mapped_column(Float, default=0.0)
    supplier: Mapped[str] = mapped_column(String, default="")


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    client_id: Mapped[str] = mapped_column(String, index=True)
    design_name: Mapped[str] = mapped_column(String, default="")
    material_lot_id: Mapped[str | None] = mapped_column(String, nullable=True)
    material_grams: Mapped[float] = mapped_column(Float, default=10.0)
    printer_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String, default="Draft", index=True)
    assurance_tier: Mapped[str] = mapped_column(String, default="A0")
    priority: Mapped[int] = mapped_column(Integer, default=5)
    tolerance_class: Mapped[str] = mapped_column(String, default="standard")
    bbox_x: Mapped[int] = mapped_column(Integer, default=100)
    bbox_y: Mapped[int] = mapped_column(Integer, default=100)
    bbox_z: Mapped[int] = mapped_column(Integer, default=100)
    object_ref: Mapped[str | None] = mapped_column(String, nullable=True)  # CID
    file_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    verdict: Mapped[str] = mapped_column(String, default="none")
    scenario: Mapped[str] = mapped_column(String, default="legitimate")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    dispatched_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class VerificationRecord(Base):
    __tablename__ = "verifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String, index=True)
    schedule_commit: Mapped[str] = mapped_column(String, default="")
    drawn_set: Mapped[list] = mapped_column(JSON, default=list)
    verdict: Mapped[str] = mapped_column(String, default="none")
    tier: Mapped[str] = mapped_column(String, default="A0")
    p_evade: Mapped[float] = mapped_column(Float, default=1.0)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class TelemetrySample(Base):
    __tablename__ = "telemetry"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String, index=True)
    bucket: Mapped[int] = mapped_column(Integer)
    power: Mapped[float] = mapped_column(Float, default=0.0)
    thermal: Mapped[float] = mapped_column(Float, default=0.0)
    flow: Mapped[float] = mapped_column(Float, default=0.0)
    expected_phase: Mapped[str] = mapped_column(String, default="")
    plane: Mapped[str] = mapped_column(String, default="independent")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String, default="system")
    action: Mapped[str] = mapped_column(String, index=True)
    target: Mapped[str] = mapped_column(String, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String, default="")
    this_hash: Mapped[str] = mapped_column(String, default="")
    signature: Mapped[str] = mapped_column(String, default="")
    ts: Mapped[str] = mapped_column(String, default=now_iso)  # ISO string: stable across DB round-trips


class Blob(Base):
    __tablename__ = "blobs"
    cid: Mapped[str] = mapped_column(String, primary_key=True)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    nonce: Mapped[bytes] = mapped_column(LargeBinary)
    wrapped_key: Mapped[bytes] = mapped_column(LargeBinary)
    size: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
