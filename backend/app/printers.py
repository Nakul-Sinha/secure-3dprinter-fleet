"""Printer registry service."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .constants import PrinterStatus
from .models import Job, MaterialLot, Printer


def add_printer(session: Session, *, id: str, model: str = "", driver_type: str = "simulated",
                materials: list[str] | None = None, tolerance_class: str = "standard",
                location: str = "", build: tuple[int, int, int] = (220, 220, 250)) -> Printer:
    p = Printer(id=id, model=model, driver_type=driver_type, materials=materials or ["PLA"],
                tolerance_class=tolerance_class, location=location,
                build_x=build[0], build_y=build[1], build_z=build[2],
                status=PrinterStatus.IDLE)
    session.merge(p)
    session.flush()
    return session.get(Printer, id)


def set_availability(session: Session, printer_id: str, available: bool) -> Printer | None:
    p = session.get(Printer, printer_id)
    if p is None:
        return None
    if available:
        if p.status in (PrinterStatus.OFFLINE, PrinterStatus.MAINTENANCE):
            p.status = PrinterStatus.IDLE
    else:
        if p.status == PrinterStatus.IDLE:
            p.status = PrinterStatus.MAINTENANCE
    session.flush()
    return p


def set_health(session: Session, printer_id: str, health: str) -> Printer | None:
    p = session.get(Printer, printer_id)
    if p is None:
        return None
    p.health = health
    session.flush()
    return p


def list_printers(session: Session) -> list[Printer]:
    return list(session.execute(select(Printer).order_by(Printer.id)).scalars())


def is_capable(session: Session, printer: Printer, job: Job) -> bool:
    """Material, tolerance, and reservation checks."""
    if printer.status != PrinterStatus.IDLE or printer.current_job is not None:
        return False
    if job.material_lot_id:
        mat = session.get(MaterialLot, job.material_lot_id)
        if mat is None or mat.type not in (printer.materials or []):
            return False
    tol_rank = {"draft": 0, "standard": 1, "fine": 2, "precision": 3}
    if tol_rank.get(printer.tolerance_class, 1) < tol_rank.get(job.tolerance_class, 1):
        return False
    return True
