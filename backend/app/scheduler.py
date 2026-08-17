"""Deterministic scheduler: capability match, scoring, reservation, concurrency."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .constants import JobStatus, PrinterStatus
from .models import Job, Printer
from .printers import is_capable


def _queue_depth(session: Session, printer_id: str) -> int:
    return int(
        session.execute(
            select(func.count(Job.id)).where(
                Job.printer_id == printer_id,
                Job.status.in_([JobStatus.SCHEDULED, JobStatus.DISPATCHED, JobStatus.PRINTING]),
            )
        ).scalar_one()
    )


def score(job: Job, queue_depth: int) -> int:
    """Higher is better. Priority 1 is most urgent (1..9)."""
    return (10 - job.priority) * 100 - queue_depth * 10


def select_printer(session: Session, job: Job) -> Printer | None:
    printers = list(session.execute(select(Printer).order_by(Printer.id)).scalars())
    candidates = []
    for p in printers:
        if is_capable(session, p, job):
            candidates.append((score(job, _queue_depth(session, p.id)), p.id, p))
    if not candidates:
        return None
    # rank by score desc, tie-break by printer id asc (deterministic)
    candidates.sort(key=lambda t: (-t[0], t[1]))
    return candidates[0][2]


def reserve(session: Session, printer: Printer, job: Job) -> None:
    printer.current_job = job.id
    session.flush()


def release(session: Session, printer_id: str) -> None:
    p = session.get(Printer, printer_id)
    if p is not None:
        p.current_job = None
        if p.status == PrinterStatus.PRINTING:
            p.status = PrinterStatus.IDLE
        session.flush()
