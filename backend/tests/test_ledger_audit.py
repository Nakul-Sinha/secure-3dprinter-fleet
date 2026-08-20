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
    from app.keys import public_key_hex

    led = get_ledger()
    led.append(session, "op-1", "A", "t1", {})
    led.append(session, "op-1", "B", "t2", {})
    session.commit()
    bundle = audit.export_bundle(session)
    assert audit.verify_bundle(bundle, public_key_hex())["ok"] is True


def test_audit_bundle_detects_edit(session):
    from app.keys import public_key_hex

    led = get_ledger()
    led.append(session, "op-1", "A", "t1", {})
    session.commit()
    bundle = audit.export_bundle(session)
    bundle["events"][0]["payload"] = {"tampered": True}
    assert audit.verify_bundle(bundle, public_key_hex())["ok"] is False


def test_per_job_bundle_reverifies_on_interleaved_stream(session):
    from app.keys import public_key_hex

    # events for different jobs are interleaved in the chain
    led = get_ledger()
    led.append(session, "op", "A", "job-1", {})
    led.append(session, "op", "B", "job-2", {})
    led.append(session, "op", "C", "job-1", {})
    session.commit()
    bundle = audit.export_bundle(session, target="job-1")
    # the signed body is the full chain, so it re-verifies offline
    assert audit.verify_bundle(bundle, public_key_hex())["ok"] is True
    assert bundle["count"] == len(bundle["events"])
    # focus_seqs identify only job-1's events
    focus_targets = {e["target"] for e in bundle["events"] if e["seq"] in bundle["focus_seqs"]}
    assert focus_targets == {"job-1"}
