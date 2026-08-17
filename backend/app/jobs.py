"""Job lifecycle orchestration (tier A0).

Pipeline: register (Client) -> authorize (Operator, guards) -> schedule
(Operator, scheduler) -> dispatch (Operator, tampered-payload check, print
simulation, commit-then-beacon verification) -> Verified@A0 or Failed. Every
transition is written to the ledger, giving the tamper-evident audit trail.
"""
from __future__ import annotations

import hashlib
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import drivers, materials, scheduler
from . import verify as verifier
from .auth import AccessDenied, require
from .config import settings
from .constants import JOB_TRANSITIONS, JobStatus, PrinterStatus, Role, Scenario, Tier, Verdict
from .ledger import get_ledger
from .models import Job, Printer, TelemetrySample, VerificationRecord, User, utcnow


class JobError(Exception):
    pass


def _new_id() -> str:
    return "job-" + secrets.token_hex(8)


def get_job(session: Session, job_id: str) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise JobError(f"job not found: {job_id}")
    return job


def _check_transition(job: Job, new_status: str) -> None:
    """Validate a transition WITHOUT mutating state, so side effects can be
    ordered after the guard and never leak on a rejected path."""
    if new_status not in JOB_TRANSITIONS.get(job.status, set()):
        raise JobError(f"illegal transition {job.status} -> {new_status}")


def _transition(session: Session, job: Job, new_status: str, actor_id: str) -> None:
    _check_transition(job, new_status)
    old = job.status
    job.status = new_status
    session.flush()
    get_ledger().append(session, actor_id, "JobTransition", job.id, {"from": old, "to": new_status})


def create_job(session: Session, actor: User, *, design: bytes, design_name: str,
               material_lot_id: str | None = None, grams: float = 10.0, priority: int = 5,
               tolerance_class: str = "standard", scenario: str = Scenario.LEGITIMATE,
               duration: int = 120) -> Job:
    from . import storage

    require(actor, "job.register")
    cid, file_hash = storage.put(session, design)
    # Anchor a SALTED commitment of the file hash, not the raw correlatable hash.
    # The raw file_hash stays off-chain in the job record for receipt re-verify.
    salt = secrets.token_hex(16)
    commitment = hashlib.sha256(f"{salt}|{file_hash}".encode()).hexdigest()
    job = Job(
        id=_new_id(), client_id=actor.id, design_name=design_name,
        material_lot_id=material_lot_id, material_grams=grams, priority=priority,
        tolerance_class=tolerance_class, scenario=scenario, status=JobStatus.DRAFT,
        assurance_tier=Tier.A0, object_ref=cid, file_hash=file_hash,
        meta={"duration": duration, "salt": salt, "commitment": commitment},
    )
    session.add(job)
    session.flush()
    get_ledger().append(session, actor.id, "JobRegistered", job.id,
                        {"cid": cid, "commitment": commitment, "client": actor.id})
    _transition(session, job, JobStatus.SUBMITTED, actor.id)
    return job


def authorize_job(session: Session, actor: User, job_id: str) -> Job:
    require(actor, "job.schedule")
    job = get_job(session, job_id)
    _check_transition(job, JobStatus.AUTHORIZED)  # validate before any side effect
    if job.material_lot_id:
        if not materials.reserve(session, job.material_lot_id, job.material_grams):
            raise JobError("insufficient material to authorize")
    job.meta = {**(job.meta or {}), "reserved": bool(job.material_lot_id)}
    _transition(session, job, JobStatus.AUTHORIZED, actor.id)
    return job


def schedule_job(session: Session, actor: User, job_id: str) -> Job:
    require(actor, "job.schedule")
    job = get_job(session, job_id)
    _check_transition(job, JobStatus.SCHEDULED)  # must be Authorized
    printer = scheduler.select_printer(session, job)
    if printer is None:
        # capacity exhaustion: queue rather than reject (SD-3). The job stays
        # Authorized and is promoted automatically when a printer frees.
        depth = _queue_depth(session)
        job.meta = {**(job.meta or {}), "queued": True, "queue_position": depth + 1}
        session.flush()
        get_ledger().append(session, actor.id, "JobQueued", job.id, {"position": depth + 1})
        return job
    scheduler.reserve(session, printer, job)
    job.printer_id = printer.id
    job.meta = {**(job.meta or {}), "queued": False}
    _transition(session, job, JobStatus.SCHEDULED, actor.id)
    get_ledger().append(session, actor.id, "JobScheduled", job.id, {"printer": printer.id})
    return job


def _queue_depth(session: Session) -> int:
    return sum(1 for j in list_jobs(session) if (j.meta or {}).get("queued"))


def promote_queued(session: Session) -> list[str]:
    """Schedule queued jobs onto newly free printers (system action)."""
    promoted = []
    queued = [j for j in list_jobs(session) if (j.meta or {}).get("queued") and j.status == JobStatus.AUTHORIZED]
    queued.sort(key=lambda j: j.created_at)
    for job in queued:
        printer = scheduler.select_printer(session, job)
        if printer is None:
            continue
        scheduler.reserve(session, printer, job)
        job.printer_id = printer.id
        job.meta = {**(job.meta or {}), "queued": False}
        _transition(session, job, JobStatus.SCHEDULED, "system")
        get_ledger().append(session, "system", "JobScheduled", job.id, {"printer": printer.id, "promoted": True})
        promoted.append(job.id)
    return promoted


def _fail(session: Session, job: Job, actor: User, reason: str) -> None:
    # _fail is only reachable after Authorize, so a reservation is held.
    if job.material_lot_id and (job.meta or {}).get("reserved", True):
        materials.release(session, job.material_lot_id, job.material_grams)
    if job.printer_id:
        scheduler.release(session, job.printer_id)
    job.completed_at = utcnow()
    _transition(session, job, JobStatus.FAILED, actor.id)
    get_ledger().append(session, actor.id, "JobFailed", job.id, {"reason": reason})
    promote_queued(session)


def dispatch_job(session: Session, actor: User, job_id: str) -> Job:
    """Dispatch, run the simulated print, and verify."""
    require(actor, "job.dispatch")
    job = get_job(session, job_id)
    _transition(session, job, JobStatus.DISPATCHED, actor.id)
    job.dispatched_at = utcnow()
    printer = session.get(Printer, job.printer_id) if job.printer_id else None
    if printer is not None:
        printer.status = PrinterStatus.PRINTING
        session.flush()

    # 1) Tampered-payload check before the printer runs anything.
    from . import storage

    if not storage.verify_on_receipt(session, job.object_ref, job.file_hash):
        get_ledger().append(session, actor.id, "PayloadRejected", job.id, {"reason": "hash mismatch"})
        _fail(session, job, actor, "tampered payload rejected before execution")
        return job

    # 2) Run the print (simulated) and verify via commit-then-beacon.
    _transition(session, job, JobStatus.PRINTING, actor.id)
    duration = int(job.meta.get("duration", 120))
    driver = drivers.get_driver(printer.driver_type if printer else "simulated")
    telemetry = driver.run(job.id, duration, job.scenario)
    commitments = verifier.commit_all(job.id, telemetry)
    result = verifier.verify_job(job.id, telemetry, commitments, n=settings.sampling_n)

    # persist the drawn telemetry samples for the job-detail view
    for i in result["sampled"]:
        t = telemetry[i]
        session.add(TelemetrySample(job_id=job.id, bucket=i, power=t["power"], thermal=t["thermal"],
                                    flow=t["flow"], expected_phase=t["expected_phase"], plane=t["plane"]))
    session.add(VerificationRecord(job_id=job.id, schedule_commit=result["merkle_root"],
                                   drawn_set=result["sampled"], verdict=result["verdict"], tier=Tier.A0,
                                   p_evade=result["p_evade"], detail=result))
    session.flush()
    get_ledger().append(session, actor.id, "SnapshotsCommitted", job.id,
                        {"root": result["merkle_root"], "n": result["n"]})

    if result["verdict"] == Verdict.VERIFIED_A0:
        job.verdict = Verdict.VERIFIED_A0
        if job.material_lot_id:
            materials.consume(session, job.material_lot_id, job.material_grams)
        scheduler.release(session, job.printer_id)
        job.completed_at = utcnow()
        _transition(session, job, JobStatus.VERIFIED_A0, actor.id)
        get_ledger().append(session, actor.id, "JobVerified", job.id,
                            {"verdict": Verdict.VERIFIED_A0, "p_evade": result["p_evade"],
                             "screening_failures": result["screening_failures"]})
        promote_queued(session)
    else:
        _fail(session, job, actor, result["reason"])
    return job


def cancel_job(session: Session, actor: User, job_id: str) -> Job:
    require(actor, "job.cancel")
    job = get_job(session, job_id)
    # a Client may only cancel their own job
    if actor.role == Role.CLIENT and job.client_id != actor.id:
        raise AccessDenied(actor.id, "job.cancel")
    _check_transition(job, JobStatus.CANCELLED)
    reserved = (job.meta or {}).get("reserved") or job.status in (JobStatus.AUTHORIZED, JobStatus.SCHEDULED)
    if job.material_lot_id and reserved:
        materials.release(session, job.material_lot_id, job.material_grams)
    if job.printer_id:
        scheduler.release(session, job.printer_id)
    _transition(session, job, JobStatus.CANCELLED, actor.id)
    promote_queued(session)
    return job


def run_pipeline(session: Session, client: User, operator: User, **kwargs) -> Job:
    """Convenience: full happy path for demos and tests."""
    job = create_job(session, client, **kwargs)
    authorize_job(session, operator, job.id)
    schedule_job(session, operator, job.id)
    return dispatch_job(session, operator, job.id)


def list_jobs(session: Session, client_id: str | None = None) -> list[Job]:
    q = select(Job).order_by(Job.created_at.desc())
    if client_id:
        q = q.where(Job.client_id == client_id)
    return list(session.execute(q).scalars())
