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
    assert anchor.verify_checkpoint(anchor.checkpoint_dict(cp), public_key_hex())["ok"] is True


def test_checkpoint_signature_tamper_detected(session):
    led = get_ledger()
    led.append(session, "op", "Event", "t", {})
    session.commit()
    cp = anchor.create_checkpoint(session, anchor=False)
    session.commit()
    d = anchor.checkpoint_dict(cp)
    d["head_hash"] = "00" * 32
    assert anchor.verify_checkpoint(d, public_key_hex())["ok"] is False


def test_checkpoint_time_cannot_be_backdated(session):
    """The signature covers the timestamp, so the claimed time cannot change."""
    led = get_ledger()
    led.append(session, "op", "Event", "t", {})
    session.commit()
    cp = anchor.create_checkpoint(session, anchor=False)
    session.commit()
    d = anchor.checkpoint_dict(cp)
    d["tsa_time"] = "1999-01-01T00:00:00+00:00"
    assert anchor.verify_checkpoint(d, public_key_hex())["ok"] is False


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
    res = audit.verify_bundle(bundle, public_key_hex())
    assert res["ok"] is True and res["attested"] is True


def test_forged_bundle_signed_with_another_key_is_rejected(session):
    """The verifier must pin the key. A bundle that is internally consistent
    with an attacker's own key proves nothing and must not verify."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from app.crypto import canonical_bytes
    from app.ledger import _event_hash

    attacker = Ed25519PrivateKey.generate()
    attacker_pub = attacker.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    ).hex()

    prev = ""
    events = []
    for seq in (1, 2):
        ev = {"seq": seq, "actor": "attacker", "action": "JobVerified",
              "target": "job-never-happened", "payload": {"verdict": "VerifiedA0"},
              "prev_hash": prev, "ts": "2026-01-01T00:00:00+00:00"}
        ev["this_hash"] = _event_hash(seq, ev["actor"], ev["action"], ev["target"],
                                      ev["payload"], prev, ev["ts"])
        ev["signature"] = attacker.sign(ev["this_hash"].encode()).hex()
        prev = ev["this_hash"]
        events.append(ev)

    body = {"events": events, "chain_ok": True, "count": len(events), "checkpoint": None}
    forged = {**body,
              "bundle_signature": attacker.sign(canonical_bytes(body)).hex(),
              "public_key": attacker_pub}

    # self-consistent with the attacker's key, but not with the pinned key
    assert audit.verify_bundle(forged, attacker_pub)["ok"] is True
    res = audit.verify_bundle(forged, public_key_hex())
    assert res["ok"] is False
    assert "unknown key" in res["reason"]


def test_bundle_without_checkpoint_is_flagged_unattested(session):
    led = get_ledger()
    led.append(session, "op", "Event", "job-x", {})
    session.commit()
    bundle = audit.export_bundle(session)
    res = audit.verify_bundle(bundle, public_key_hex())
    assert res["ok"] is True
    assert res["attested"] is False
    assert "not attested" in res["warning"]


def test_deleting_only_checkpoint_rows_is_detected(session):
    """The log records that a checkpoint was created. Deleting the attestation
    while leaving that record is self-incriminating."""
    from app.models import Checkpoint

    led = get_ledger()
    for i in range(6):
        led.append(session, "op", "Event", f"t{i}", {"i": i})
    session.commit()
    anchor.create_checkpoint(session, anchor=False)
    session.commit()

    for cp in session.query(Checkpoint).all():
        session.delete(cp)
    session.commit()

    check = led.verify_chain(session)
    assert check.ok is False
    assert "checkpoint records were deleted" in check.reason


def test_erasing_all_local_attestation_downgrades_to_unattested(session):
    """If an attacker with database access deletes the checkpoints AND the log
    entries that mention them, the remaining log is internally consistent. The
    honest result is 'not attested', not a clean pass. Only an external anchor
    can defeat this, which is what AnchorRegistry is for."""
    from app.models import Checkpoint

    led = get_ledger()
    for i in range(6):
        led.append(session, "op", "Event", f"t{i}", {"i": i})
    session.commit()
    anchor.create_checkpoint(session, anchor=False)
    session.commit()

    for ev in session.query(AuditEvent).filter(AuditEvent.action == "CheckpointCreated").all():
        session.delete(ev)
    for ev in session.query(AuditEvent).order_by(AuditEvent.seq.desc()).limit(2).all():
        session.delete(ev)
    for cp in session.query(Checkpoint).all():
        session.delete(cp)
    session.commit()

    check = led.verify_chain(session)
    assert check.attested is False
    assert "not attested" in check.reason


def test_unattested_log_is_reported_as_not_attested(session):
    from app.config import settings

    old = settings.checkpoint_every
    settings.checkpoint_every = 0  # disable automatic checkpointing
    try:
        led = get_ledger()
        led.append(session, "op", "Event", "t", {})
        session.commit()
        check = led.verify_chain(session)
        assert check.ok is True
        assert check.attested is False
        assert "not attested" in check.reason
    finally:
        settings.checkpoint_every = old


def test_automatic_checkpointing_bounds_the_window(session):
    from app.config import settings

    old = settings.checkpoint_every
    settings.checkpoint_every = 3
    try:
        led = get_ledger()
        for i in range(8):
            led.append(session, "op", "Event", f"t{i}", {"i": i})
        session.commit()
        assert anchor.latest(session) is not None  # created without anyone asking
        assert led.verify_chain(session).attested is True
    finally:
        settings.checkpoint_every = old


def test_timestamp_authority_stamps_checkpoint(session):
    led = get_ledger()
    led.append(session, "op", "Event", "t", {})
    session.commit()
    cp = anchor.create_checkpoint(session, anchor=False)
    session.commit()
    assert cp.tsa_authority == "local-dev-tsa"
    assert cp.tsa_token and cp.tsa_time
