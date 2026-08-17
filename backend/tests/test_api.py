import pytest
from fastapi.testclient import TestClient

from app.db import reset_db_for_tests
from app.ledger import reset_ledger_for_tests


@pytest.fixture()
def client():
    reset_db_for_tests("sqlite:///:memory:")
    reset_ledger_for_tests()
    from app.main import app

    with TestClient(app) as c:
        yield c


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def login(client, user_id: str) -> str:
    r = client.post("/api/auth/login", json={"user_id": user_id})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_end_to_end_flow(client):
    admin = login(client, "admin")
    # seed operators, clients, printers, materials
    assert client.post("/api/demo/seed", headers=_auth(admin)).status_code == 200

    # client submits a job
    ctok = login(client, "client-acme")
    r = client.post("/api/jobs", headers=_auth(ctok), json={
        "design_name": "bracket.3mf", "material_lot_id": "mat-pla-001",
        "scenario": "legitimate", "duration": 100,
    })
    assert r.status_code == 200, r.text
    job_id = r.json()["id"]

    # operator runs it
    otok = login(client, "op-1")
    r = client.post(f"/api/jobs/{job_id}/run", headers=_auth(otok))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "Verified@A0"
    assert r.json()["verdict"] == "VerifiedA0"

    # audit chain verifies
    r = client.get("/api/audit/verify", headers=_auth(otok))
    assert r.json()["ok"] is True

    # audit bundle re-verifies
    bundle = client.get("/api/audit/bundle", headers=_auth(otok)).json()
    assert bundle["chain_ok"] is True


def test_fake_completion_flow(client):
    admin = login(client, "admin")
    client.post("/api/demo/seed", headers=_auth(admin))
    ctok = login(client, "client-acme")
    job_id = client.post("/api/jobs", headers=_auth(ctok), json={
        "design_name": "ghost.3mf", "material_lot_id": "mat-pla-001",
        "scenario": "lazy-fake", "duration": 100,
    }).json()["id"]
    otok = login(client, "op-1")
    r = client.post(f"/api/jobs/{job_id}/run", headers=_auth(otok))
    assert r.json()["status"] == "Failed"


def test_unauthorized_access_blocked(client):
    admin = login(client, "admin")
    client.post("/api/demo/seed", headers=_auth(admin))
    # a client cannot add a printer
    ctok = login(client, "client-acme")
    r = client.post("/api/printers", headers=_auth(ctok),
                    json={"id": "rogue", "materials": ["PLA"]})
    assert r.status_code == 403
    # an admin cannot register a job (separation of duties)
    r = client.post("/api/jobs", headers=_auth(admin),
                    json={"design_name": "x.3mf", "material_lot_id": "mat-pla-001"})
    assert r.status_code == 403


def test_client_cannot_read_another_clients_job(client):
    admin = login(client, "admin")
    client.post("/api/demo/seed", headers=_auth(admin))
    client.post("/api/users", headers=_auth(admin), json={"id": "client-evil", "role": "Client"})
    ctok = login(client, "client-acme")
    job_id = client.post("/api/jobs", headers=_auth(ctok), json={
        "design_name": "secret.3mf", "material_lot_id": "mat-pla-001",
    }).json()["id"]
    # a different client must not read it (no IDOR leak of file_hash/CID)
    etok = login(client, "client-evil")
    assert client.get(f"/api/jobs/{job_id}", headers=_auth(etok)).status_code == 404
    # the owner still can
    assert client.get(f"/api/jobs/{job_id}", headers=_auth(ctok)).status_code == 200


def test_materials_low_stock_flag(client):
    admin = login(client, "admin")
    client.post("/api/demo/seed", headers=_auth(admin))
    client.post("/api/materials", headers=_auth(admin),
                json={"id": "mat-low", "type": "PLA", "stock_qty": 10})
    mats = client.get("/api/materials", headers=_auth(admin)).json()
    low = next(m for m in mats if m["id"] == "mat-low")
    assert low["low_stock"] is True


def test_audit_csv_export(client):
    admin = login(client, "admin")
    client.post("/api/demo/seed", headers=_auth(admin))
    r = client.get("/api/audit/export.csv", headers=_auth(admin))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "seq,actor,action" in r.text


def test_requires_authentication(client):
    assert client.get("/api/jobs").status_code == 401
