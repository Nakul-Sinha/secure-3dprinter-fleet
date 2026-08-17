import pytest

from app import jobs, materials, printers, storage
from app.auth import AccessDenied
from app.constants import JobStatus, Scenario, Verdict
from app.models import Blob


def _seed(session):
    materials.register_lot(session, id="mat-pla-001", type="PLA", stock_qty=1000)
    printers.add_printer(session, id="printer-01", model="Prusa", materials=["PLA"], tolerance_class="fine")
    session.flush()


def test_happy_path_verifies(session, actors):
    _seed(session)
    job = jobs.run_pipeline(session, actors["client"], actors["operator"],
                            design=b"legit-part", design_name="bracket.3mf",
                            material_lot_id="mat-pla-001", scenario=Scenario.LEGITIMATE, duration=120)
    assert job.status == JobStatus.VERIFIED_A0
    assert job.verdict == Verdict.VERIFIED_A0


def test_fake_completion_fails(session, actors):
    _seed(session)
    job = jobs.run_pipeline(session, actors["client"], actors["operator"],
                            design=b"fake-part", design_name="ghost.3mf",
                            material_lot_id="mat-pla-001", scenario=Scenario.LAZY_FAKE, duration=120)
    assert job.status == JobStatus.FAILED


def test_tampered_payload_rejected_before_printing(session, actors):
    _seed(session)
    job = jobs.create_job(session, actors["client"], design=b"real-part", design_name="p.3mf",
                          material_lot_id="mat-pla-001", scenario=Scenario.LEGITIMATE)
    jobs.authorize_job(session, actors["operator"], job.id)
    jobs.schedule_job(session, actors["operator"], job.id)
    # tamper the stored ciphertext after commit, before dispatch
    blob = session.get(Blob, job.object_ref)
    blob.ciphertext = blob.ciphertext[:-1] + bytes([blob.ciphertext[-1] ^ 0x02])
    session.flush()
    job = jobs.dispatch_job(session, actors["operator"], job.id)
    assert job.status == JobStatus.FAILED


def test_unauthorized_registration_denied(session, actors):
    _seed(session)
    with pytest.raises(AccessDenied):
        jobs.create_job(session, actors["admin"], design=b"x", design_name="x.3mf",
                        material_lot_id="mat-pla-001")


def test_material_reserved_and_consumed(session, actors):
    _seed(session)
    before = materials.available(session, "mat-pla-001")
    jobs.run_pipeline(session, actors["client"], actors["operator"], design=b"p", design_name="p.3mf",
                      material_lot_id="mat-pla-001", grams=25.0, scenario=Scenario.LEGITIMATE, duration=90)
    after = materials.available(session, "mat-pla-001")
    assert after == before - 25.0


def test_sabotage_pipeline_fails_closed(session, actors):
    _seed(session)
    job = jobs.run_pipeline(session, actors["client"], actors["operator"],
                            design=b"sab", design_name="weak.3mf", material_lot_id="mat-pla-001",
                            scenario=Scenario.SABOTAGED, duration=160)
    assert job.status == JobStatus.FAILED  # never Verified@A0 with a screening anomaly


def test_cancel_submitted_job_does_not_release_others_reservation(session, actors):
    _seed(session)
    a = jobs.create_job(session, actors["client"], design=b"a", design_name="a.3mf",
                        material_lot_id="mat-pla-001", grams=60)
    jobs.authorize_job(session, actors["operator"], a.id)
    reserved_avail = materials.available(session, "mat-pla-001")
    # B is created but never authorized (no reservation), then cancelled by its owner
    b = jobs.create_job(session, actors["client"], design=b"b", design_name="b.3mf",
                        material_lot_id="mat-pla-001", grams=60)
    jobs.cancel_job(session, actors["client"], b.id)
    assert materials.available(session, "mat-pla-001") == reserved_avail  # A intact


def test_capacity_exhaustion_queues_then_promotes(session, actors):
    materials.register_lot(session, id="mat-pla-001", type="PLA", stock_qty=1000)
    printers.add_printer(session, id="printer-01", model="P", materials=["PLA"], tolerance_class="fine")
    session.flush()
    j1 = jobs.create_job(session, actors["client"], design=b"1", design_name="1.3mf",
                         material_lot_id="mat-pla-001", scenario=Scenario.LEGITIMATE, duration=90)
    j2 = jobs.create_job(session, actors["client"], design=b"2", design_name="2.3mf",
                         material_lot_id="mat-pla-001", scenario=Scenario.LEGITIMATE, duration=90)
    jobs.authorize_job(session, actors["operator"], j1.id)
    jobs.authorize_job(session, actors["operator"], j2.id)
    jobs.schedule_job(session, actors["operator"], j1.id)   # gets the only printer
    r2 = jobs.schedule_job(session, actors["operator"], j2.id)  # queued
    assert (r2.meta or {}).get("queued") is True
    assert r2.status == JobStatus.AUTHORIZED
    jobs.dispatch_job(session, actors["operator"], j1.id)   # completes, frees printer, promotes j2
    assert jobs.get_job(session, j2.id).status == JobStatus.SCHEDULED
