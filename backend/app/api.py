"""REST API (mounted under /api)."""
from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import audit, jobs, materials, printers, users
from .auth import issue_token, user_from_token
from .constants import Scenario
from .db import get_session
from .models import Job, User

router = APIRouter(prefix="/api")


def db() -> Session:
    yield from get_session()


def current_user(authorization: str = Header(default=""), session: Session = Depends(db)) -> User:
    token = authorization[7:] if authorization.lower().startswith("bearer ") else authorization
    user = user_from_token(session, token)
    if user is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user


# ---- auth ----

class LoginBody(BaseModel):
    user_id: str


@router.post("/auth/login")
def login(body: LoginBody, session: Session = Depends(db)):
    user = session.get(User, body.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="unknown user")
    return {"token": issue_token(user.id), "user_id": user.id, "role": user.role}


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return {"user_id": user.id, "role": user.role, "org": user.org}


# ---- users ----

class UserBody(BaseModel):
    id: str
    role: str
    org: str = "default"


class RoleBody(BaseModel):
    role: str


@router.post("/users")
def create_user(body: UserBody, user: User = Depends(current_user), session: Session = Depends(db)):
    u = users.create_user(session, user, id=body.id, role=body.role, org=body.org)
    session.commit()
    return {"id": u.id, "role": u.role, "org": u.org}


@router.post("/users/{user_id}/role")
def grant_role(user_id: str, body: RoleBody, user: User = Depends(current_user), session: Session = Depends(db)):
    u = users.grant_role(session, user, user_id, body.role)
    session.commit()
    return {"id": u.id, "role": u.role}


@router.get("/users")
def list_users(user: User = Depends(current_user), session: Session = Depends(db)):
    from .auth import require

    require(user, "fleet.read")
    return [{"id": u.id, "role": u.role, "org": u.org} for u in users.list_users(session)]


# ---- printers ----

class PrinterBody(BaseModel):
    id: str
    model: str = ""
    materials: list[str] = ["PLA"]
    tolerance_class: str = "standard"
    location: str = ""


class AvailabilityBody(BaseModel):
    available: bool


@router.post("/printers")
def add_printer(body: PrinterBody, user: User = Depends(current_user), session: Session = Depends(db)):
    from .auth import require

    require(user, "printer.add")
    p = printers.add_printer(session, id=body.id, model=body.model, materials=body.materials,
                             tolerance_class=body.tolerance_class, location=body.location)
    session.commit()
    return {"id": p.id, "status": p.status, "materials": p.materials}


@router.post("/printers/{printer_id}/availability")
def set_availability(printer_id: str, body: AvailabilityBody, user: User = Depends(current_user),
                     session: Session = Depends(db)):
    from .auth import require

    require(user, "printer.availability")
    p = printers.set_availability(session, printer_id, body.available)
    if p is None:
        raise HTTPException(status_code=404, detail="printer not found")
    session.commit()
    return {"id": p.id, "status": p.status}


@router.get("/printers")
def list_printers(user: User = Depends(current_user), session: Session = Depends(db)):
    from .auth import require

    require(user, "fleet.read")
    return [
        {"id": p.id, "model": p.model, "status": p.status, "materials": p.materials,
         "tolerance_class": p.tolerance_class, "health": p.health, "current_job": p.current_job}
        for p in printers.list_printers(session)
    ]


# ---- materials ----

class MaterialBody(BaseModel):
    id: str
    type: str
    stock_qty: float = 1000.0
    density: float = 1.24
    nominal_temp: float = 210.0
    cost_per_gram: float = 0.03
    supplier: str = ""


@router.post("/materials")
def add_material(body: MaterialBody, user: User = Depends(current_user), session: Session = Depends(db)):
    from .auth import require

    require(user, "material.manage")
    m = materials.register_lot(session, id=body.id, type=body.type, stock_qty=body.stock_qty,
                               density=body.density, nominal_temp=body.nominal_temp,
                               cost_per_gram=body.cost_per_gram, supplier=body.supplier)
    session.commit()
    return {"id": m.id, "type": m.type, "stock_qty": m.stock_qty}


@router.get("/materials")
def list_materials(user: User = Depends(current_user), session: Session = Depends(db)):
    from .auth import require

    require(user, "fleet.read")
    out = []
    for m in materials.list_materials(session):
        avail = m.stock_qty - m.reserved_qty
        out.append({"id": m.id, "type": m.type, "stock_qty": m.stock_qty,
                    "reserved_qty": m.reserved_qty, "available": avail,
                    "low_stock": avail < 100})
    return out


# ---- jobs ----

class JobBody(BaseModel):
    design_name: str
    design_b64: str | None = None
    material_lot_id: str | None = None
    grams: float = 10.0
    priority: int = 5
    tolerance_class: str = "standard"
    scenario: str = Scenario.LEGITIMATE
    duration: int = 120


def _job_view(session: Session, job: Job) -> dict:
    from .models import TelemetrySample, VerificationRecord
    from sqlalchemy import select

    vr = session.execute(
        select(VerificationRecord).where(VerificationRecord.job_id == job.id)
        .order_by(VerificationRecord.id.desc())
    ).scalars().first()
    samples = list(session.execute(
        select(TelemetrySample).where(TelemetrySample.job_id == job.id)
        .order_by(TelemetrySample.bucket)
    ).scalars())
    return {
        "id": job.id, "client_id": job.client_id, "design_name": job.design_name,
        "material_lot_id": job.material_lot_id, "printer_id": job.printer_id,
        "status": job.status, "assurance_tier": job.assurance_tier, "verdict": job.verdict,
        "scenario": job.scenario, "object_ref": job.object_ref, "file_hash": job.file_hash,
        "verification": vr.detail if vr else None,
        "telemetry": [{"bucket": s.bucket, "power": s.power, "thermal": s.thermal,
                       "flow": s.flow, "expected_phase": s.expected_phase} for s in samples],
    }


@router.post("/jobs")
def create_job(body: JobBody, user: User = Depends(current_user), session: Session = Depends(db)):
    if body.design_b64:
        design = base64.b64decode(body.design_b64)
    else:
        design = f"3mf-payload::{body.design_name}::{body.scenario}".encode()
    job = jobs.create_job(session, user, design=design, design_name=body.design_name,
                          material_lot_id=body.material_lot_id, grams=body.grams, priority=body.priority,
                          tolerance_class=body.tolerance_class, scenario=body.scenario, duration=body.duration)
    session.commit()
    return _job_view(session, job)


@router.post("/jobs/{job_id}/authorize")
def authorize(job_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    job = jobs.authorize_job(session, user, job_id)
    session.commit()
    return _job_view(session, job)


@router.post("/jobs/{job_id}/schedule")
def schedule(job_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    job = jobs.schedule_job(session, user, job_id)
    session.commit()
    return _job_view(session, job)


@router.post("/jobs/{job_id}/dispatch")
def dispatch(job_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    job = jobs.dispatch_job(session, user, job_id)
    session.commit()
    return _job_view(session, job)


@router.post("/jobs/{job_id}/run")
def run(job_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    """Authorize, schedule, and dispatch in one call (Operator)."""
    jobs.authorize_job(session, user, job_id)
    jobs.schedule_job(session, user, job_id)
    job = jobs.dispatch_job(session, user, job_id)
    session.commit()
    return _job_view(session, job)


@router.post("/jobs/{job_id}/cancel")
def cancel(job_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    job = jobs.cancel_job(session, user, job_id)
    session.commit()
    return _job_view(session, job)


@router.get("/jobs")
def list_jobs(limit: int = 100, offset: int = 0,
              user: User = Depends(current_user), session: Session = Depends(db)):
    from .constants import Role

    client_id = user.id if user.role == Role.CLIENT else None
    rows = jobs.list_jobs(session, client_id=client_id)[offset:offset + limit]
    return [_job_view(session, j) for j in rows]


@router.get("/jobs/{job_id}")
def get_job(job_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    from .constants import Role

    job = jobs.get_job(session, job_id)
    if user.role == Role.CLIENT and job.client_id != user.id:
        raise HTTPException(status_code=404, detail="job not found")
    return _job_view(session, job)


# ---- audit ----

@router.get("/audit/events")
def audit_events(action: str | None = None, target: str | None = None,
                 limit: int = 200, offset: int = 0,
                 user: User = Depends(current_user), session: Session = Depends(db)):
    from .auth import require

    require(user, "audit.read")
    rows = audit.list_events(session, action=action, target=target, limit=100000)[offset:offset + limit]
    return [
        {"seq": e.seq, "actor": e.actor, "action": e.action, "target": e.target,
         "payload": e.payload, "this_hash": e.this_hash, "ts": e.ts}
        for e in rows
    ]


@router.get("/audit/export.csv")
def audit_export_csv(target: str | None = None,
                     user: User = Depends(current_user), session: Session = Depends(db)):
    import csv
    import io

    from fastapi.responses import Response

    from .auth import require

    require(user, "audit.read")
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["seq", "actor", "action", "target", "ts", "this_hash"])
    for e in audit.list_events(session, target=target, limit=1_000_000):
        writer.writerow([e.seq, e.actor, e.action, e.target, e.ts, e.this_hash])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=audit.csv"})


@router.get("/audit/verify")
def audit_verify(user: User = Depends(current_user), session: Session = Depends(db)):
    from .auth import require

    require(user, "audit.read")
    c = audit.verify_chain(session)
    return {"ok": c.ok, "count": c.count, "first_bad_seq": c.first_bad_seq, "reason": c.reason}


@router.get("/audit/bundle")
def audit_bundle(target: str | None = None, user: User = Depends(current_user), session: Session = Depends(db)):
    from .auth import require

    require(user, "audit.read")
    return audit.export_bundle(session, target=target)


# ---- setup helpers (Admin) ----

@router.post("/demo/seed")
def demo_seed(user: User = Depends(current_user), session: Session = Depends(db)):
    """Create demo operators, clients, printers, and materials for the walkthrough."""
    from .auth import require

    require(user, "user.manage")
    for uid, role in [("op-1", "Operator"), ("client-acme", "Client"), ("auditor-1", "Auditor")]:
        if session.get(User, uid) is None:
            users.create_user(session, user, id=uid, role=role)
    for m in materials.list_materials(session):
        break
    else:
        materials.register_lot(session, id="mat-pla-001", type="PLA", stock_qty=1000)
    if not printers.list_printers(session):
        printers.add_printer(session, id="printer-01", model="Prusa-MK4", materials=["PLA", "PETG"],
                             tolerance_class="fine")
        printers.add_printer(session, id="printer-02", model="Voron-2.4",
                             materials=["PLA", "ABS", "PETG"], tolerance_class="precision")
    session.commit()
    return {"seeded": True}
