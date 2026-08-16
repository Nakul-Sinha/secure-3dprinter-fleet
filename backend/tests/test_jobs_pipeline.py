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
