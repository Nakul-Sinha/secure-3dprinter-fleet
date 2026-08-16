import pytest

from app import printers, scheduler
from app.auth import AccessDenied, can, issue_token, parse_token, require, separation_of_duties_holds
from app.constants import JobStatus, Role
from app.materials import register_lot
from app.models import Job


def test_separation_of_duties():
    assert separation_of_duties_holds() is True


def test_permission_matrix(actors):
    assert can(Role.CLIENT, "job.register") is True
    assert can(Role.ADMIN, "job.register") is False  # SoD: admin cannot register
    assert can(Role.OPERATOR, "job.schedule") is True
    assert can(Role.CLIENT, "job.schedule") is False


def test_require_raises_for_wrong_role(actors):
    with pytest.raises(AccessDenied):
        require(actors["admin"], "job.register")


def test_token_roundtrip():
    t = issue_token("op-1")
    assert parse_token(t) == "op-1"
    assert parse_token("op-1.badsig") is None


def _seed_fleet(session):
    register_lot(session, id="mat-pla-001", type="PLA", stock_qty=1000)
    printers.add_printer(session, id="printer-01", model="A", materials=["PLA"], tolerance_class="standard")
    printers.add_printer(session, id="printer-02", model="B", materials=["PLA"], tolerance_class="fine")
    session.flush()


def test_scheduler_matches_capability_and_is_deterministic(session):
    _seed_fleet(session)
    job = Job(id="j1", client_id="client-1", material_lot_id="mat-pla-001", priority=1,
              tolerance_class="standard", status=JobStatus.AUTHORIZED)
    session.add(job)
    session.flush()
    p1 = scheduler.select_printer(session, job)
    p2 = scheduler.select_printer(session, job)
    assert p1 is not None and p1.id == p2.id


def test_scheduler_rejects_incompatible_material(session):
    printers.add_printer(session, id="printer-abs", model="C", materials=["ABS"], tolerance_class="fine")
    register_lot(session, id="mat-pla-001", type="PLA", stock_qty=1000)
    session.flush()
    job = Job(id="j2", client_id="client-1", material_lot_id="mat-pla-001",
              tolerance_class="standard", status=JobStatus.AUTHORIZED)
    session.add(job)
    session.flush()
    assert scheduler.select_printer(session, job) is None


def test_scheduler_concurrency_uses_two_printers(session):
    _seed_fleet(session)
    j1 = Job(id="ja", client_id="c", material_lot_id="mat-pla-001", priority=1,
             tolerance_class="standard", status=JobStatus.AUTHORIZED)
    j2 = Job(id="jb", client_id="c", material_lot_id="mat-pla-001", priority=1,
             tolerance_class="standard", status=JobStatus.AUTHORIZED)
    session.add_all([j1, j2])
    session.flush()
    p1 = scheduler.select_printer(session, j1)
    scheduler.reserve(session, p1, j1)
    p2 = scheduler.select_printer(session, j2)
    assert p1.id != p2.id  # the reserved printer is not offered again
