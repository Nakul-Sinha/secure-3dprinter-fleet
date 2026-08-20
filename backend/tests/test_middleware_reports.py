import pytest
from fastapi.testclient import TestClient

from app.db import reset_db_for_tests
from app.ledger import reset_ledger_for_tests
from app.middleware import reset_guards_for_tests


@pytest.fixture()
def client():
    reset_db_for_tests("sqlite:///:memory:")
    reset_ledger_for_tests()
    reset_guards_for_tests()
    from app.main import app

    with TestClient(app) as c:
        yield c


def _auth(t):
    return {"Authorization": f"Bearer {t}"}


def login(client, uid):
    return client.post("/api/auth/login", json={"user_id": uid}).json()["token"]


def test_idempotency_key_replays_response(client):
    admin = login(client, "admin")
    client.post("/api/demo/seed", headers=_auth(admin))
    ctok = login(client, "client-acme")
    headers = {**_auth(ctok), "Idempotency-Key": "abc-123"}
    body = {"design_name": "part.3mf", "material_lot_id": "mat-pla-001"}
    first = client.post("/api/jobs", headers=headers, json=body)
    second = client.post("/api/jobs", headers=headers, json=body)
    assert first.status_code == 200 and second.status_code == 200
    # the same job is returned, no duplicate created
    assert first.json()["id"] == second.json()["id"]
    assert second.headers.get("Idempotent-Replay") == "true"


def test_different_idempotency_keys_create_distinct_jobs(client):
    admin = login(client, "admin")
    client.post("/api/demo/seed", headers=_auth(admin))
    ctok = login(client, "client-acme")
    body = {"design_name": "part.3mf", "material_lot_id": "mat-pla-001"}
    a = client.post("/api/jobs", headers={**_auth(ctok), "Idempotency-Key": "k1"}, json=body)
    b = client.post("/api/jobs", headers={**_auth(ctok), "Idempotency-Key": "k2"}, json=body)
    assert a.json()["id"] != b.json()["id"]


def test_rate_limit_returns_429(client, monkeypatch):
    import app.middleware as mw

    monkeypatch.setattr(mw, "MAX_PER_WINDOW", 5)
    admin = login(client, "admin")
    codes = [client.get("/api/printers", headers=_auth(admin)).status_code for _ in range(12)]
    assert 429 in codes


def test_health_is_not_rate_limited(client, monkeypatch):
    import app.middleware as mw

    monkeypatch.setattr(mw, "MAX_PER_WINDOW", 2)
    codes = [client.get("/health").status_code for _ in range(8)]
    assert set(codes) == {200}


def test_audit_pdf_export(client):
    admin = login(client, "admin")
    client.post("/api/demo/seed", headers=_auth(admin))
    r = client.get("/api/audit/export.pdf", headers=_auth(admin))
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_checkpoint_endpoints(client):
    admin = login(client, "admin")
    client.post("/api/demo/seed", headers=_auth(admin))
    made = client.post("/api/audit/checkpoint", headers=_auth(admin))
    assert made.status_code == 200
    cp = made.json()
    assert cp["count"] > 0 and cp["signature"] and cp["public_key"]
    latest = client.get("/api/audit/checkpoint", headers=_auth(admin)).json()
    assert latest["head_hash"] == cp["head_hash"]


def test_public_key_endpoint(client):
    r = client.get("/api/audit/public-key")
    assert r.status_code == 200
    assert r.json()["algorithm"] == "ed25519"
    assert len(r.json()["public_key"]) == 64


def test_client_cannot_create_checkpoint(client):
    admin = login(client, "admin")
    client.post("/api/demo/seed", headers=_auth(admin))
    ctok = login(client, "client-acme")
    assert client.post("/api/audit/checkpoint", headers=_auth(ctok)).status_code == 403
