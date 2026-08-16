from app import audit
from app.ledger import get_ledger


def test_chain_appends_and_verifies(session):
    led = get_ledger()
    led.append(session, "op-1", "TestEvent", "t1", {"x": 1})
    led.append(session, "op-1", "TestEvent", "t2", {"x": 2})
    session.commit()
    check = led.verify_chain(session)
    assert check.ok is True
    assert check.count >= 2


def test_chain_detects_tampering(session):
    led = get_ledger()
    ev = led.append(session, "op-1", "TestEvent", "t1", {"x": 1})
    led.append(session, "op-1", "TestEvent", "t2", {"x": 2})
    session.commit()
    # tamper a stored payload after the fact
    ev.payload = {"x": 999}
    session.flush()
    check = led.verify_chain(session)
    assert check.ok is False
    assert check.first_bad_seq == ev.seq


def test_audit_bundle_reverifies(session):
    led = get_ledger()
    led.append(session, "op-1", "A", "t1", {})
    led.append(session, "op-1", "B", "t2", {})
    session.commit()
    bundle = audit.export_bundle(session)
    assert audit.verify_bundle(bundle)["ok"] is True


def test_audit_bundle_detects_edit(session):
    led = get_ledger()
    led.append(session, "op-1", "A", "t1", {})
    session.commit()
    bundle = audit.export_bundle(session)
    bundle["events"][0]["payload"] = {"tampered": True}
    assert audit.verify_bundle(bundle)["ok"] is False
