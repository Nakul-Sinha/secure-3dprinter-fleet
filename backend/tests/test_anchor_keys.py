from app import anchor, audit
from app.keys import public_key_hex, sign_audit, verify_audit
from app.ledger import get_ledger
from app.models import AuditEvent


def test_ed25519_sign_and_verify():
    data = b"audit-head"
    sig = sign_audit(data)
    assert verify_audit(data, sig) is True
    assert verify_audit(b"other", sig) is False


def test_public_key_is_stable_and_public_only_verification():
    pub = public_key_hex()
    assert len(pub) == 64  # 32 raw bytes hex
    sig = sign_audit(b"x")
    # an external party with ONLY the public key can verify
    assert verify_audit(b"x", sig, pub) is True


def test_checkpoint_created_and_verifies_offline(session):
    led = get_ledger()
    for i in range(4):
        led.append(session, "op", "Event", f"t{i}", {"i": i})
    session.commit()
    cp = anchor.create_checkpoint(session, anchor=False)
    session.commit()
    assert cp is not None and cp.count >= 4
    assert anchor.verify_checkpoint(anchor.checkpoint_dict(cp))["ok"] is True


def test_checkpoint_signature_tamper_detected(session):
    led = get_ledger()
    led.append(session, "op", "Event", "t", {})
    session.commit()
    cp = anchor.create_checkpoint(session, anchor=False)
    session.commit()
    d = anchor.checkpoint_dict(cp)
    d["head_hash"] = "00" * 32
    assert anchor.verify_checkpoint(d)["ok"] is False


def test_tail_truncation_is_detected(session):
    led = get_ledger()
    for i in range(5):
        led.append(session, "op", "Event", f"t{i}", {"i": i})
    session.commit()
    anchor.create_checkpoint(session, anchor=False)
    session.commit()
    assert led.verify_chain(session).ok is True

    # delete the two newest events: the chain stays internally consistent
    newest = session.query(AuditEvent).order_by(AuditEvent.seq.desc()).limit(2).all()
    for ev in newest:
        session.delete(ev)
    session.commit()

    check = led.verify_chain(session)
    assert check.ok is False
    assert "truncat" in check.reason.lower()


def test_bundle_carries_public_key_and_checkpoint(session):
    led = get_ledger()
    led.append(session, "op", "Event", "job-1", {})
    session.commit()
    anchor.create_checkpoint(session, anchor=False)
    session.commit()
    bundle = audit.export_bundle(session, target="job-1")
    assert bundle["public_key"] == public_key_hex()
    assert bundle["checkpoint"] is not None
    res = audit.verify_bundle(bundle)
    assert res["ok"] is True and res["checkpoint_verified"] is True


def test_timestamp_authority_stamps_checkpoint(session):
    led = get_ledger()
    led.append(session, "op", "Event", "t", {})
    session.commit()
    cp = anchor.create_checkpoint(session, anchor=False)
    session.commit()
    assert cp.tsa_authority == "local-dev-tsa"
    assert cp.tsa_token and cp.tsa_time
