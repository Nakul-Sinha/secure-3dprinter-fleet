"""Material lot and inventory service."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import MaterialLot


def register_lot(session: Session, *, id: str, type: str, lot: str = "", density: float = 1.24,
                 nominal_temp: float = 210.0, cost_per_gram: float = 0.03, stock_qty: float = 1000.0,
                 supplier: str = "") -> MaterialLot:
    m = MaterialLot(id=id, type=type, lot=lot, density=density, nominal_temp=nominal_temp,
                    cost_per_gram=cost_per_gram, stock_qty=stock_qty, supplier=supplier)
    session.merge(m)
    session.flush()
    return session.get(MaterialLot, id)


def available(session: Session, material_id: str) -> float:
    m = session.get(MaterialLot, material_id)
    if m is None:
        return 0.0
    return m.stock_qty - m.reserved_qty


def reserve(session: Session, material_id: str, grams: float) -> bool:
    m = session.get(MaterialLot, material_id)
    if m is None or (m.stock_qty - m.reserved_qty) < grams:
        return False
    m.reserved_qty += grams
    session.flush()
    return True


def release(session: Session, material_id: str, grams: float) -> None:
    m = session.get(MaterialLot, material_id)
    if m is not None:
        m.reserved_qty = max(0.0, m.reserved_qty - grams)
        session.flush()


def consume(session: Session, material_id: str, grams: float) -> None:
    m = session.get(MaterialLot, material_id)
    if m is not None:
        m.stock_qty = max(0.0, m.stock_qty - grams)
        m.reserved_qty = max(0.0, m.reserved_qty - grams)
        session.flush()


def low_stock(session: Session, threshold: float = 100.0) -> list[MaterialLot]:
    rows = session.execute(select(MaterialLot)).scalars()
    return [m for m in rows if (m.stock_qty - m.reserved_qty) < threshold]


def list_materials(session: Session) -> list[MaterialLot]:
    return list(session.execute(select(MaterialLot).order_by(MaterialLot.id)).scalars())
