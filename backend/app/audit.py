"""Audit query, tamper-evidence verification, and signed export bundles."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import anchor
from .crypto import canonical_bytes
from .keys import public_key_hex, sign_audit, verify_audit
from .ledger import get_ledger
from .models import AuditEvent


def list_events(session: Session, *, action: str | None = None, target: str | None = None,
                limit: int = 200) -> list[AuditEvent]:
    q = select(AuditEvent).order_by(AuditEvent.seq.asc())
    if action:
        q = q.where(AuditEvent.action == action)
    if target:
        q = q.where(AuditEvent.target == target)
    return list(session.execute(q).scalars())[:limit]


def verify_chain(session: Session):
    return get_ledger().verify_chain(session)


def _event_dict(ev: AuditEvent) -> dict:
    return {
        "seq": ev.seq,
        "actor": ev.actor,
        "action": ev.action,
        "target": ev.target,
        "payload": ev.payload,
        "prev_hash": ev.prev_hash,
        "this_hash": ev.this_hash,
        "signature": ev.signature,
        "ts": ev.ts,
    }


def export_bundle(session: Session, *, target: str | None = None) -> dict:
    """Self-contained, signed audit bundle that re-verifies offline.

    The signed cryptographic body is always the FULL contiguous chain, because a
    hash chain only re-verifies as a contiguous whole. A per-job export uses
    `target` as a display-only focus filter (focus_seqs), so the bundle both
    re-verifies and identifies the job's events. The bundle carries the audit
    public key and the latest checkpoint, so a third party can verify it without
    any secret and can detect truncation.
    """
    events = [_event_dict(e) for e in list_events(session, limit=1_000_000)]
    check = verify_chain(session)
    focus = [e["seq"] for e in events if target is None or e["target"] == target]
    cp = anchor.latest(session)
    body = {
        "events": events,
        "chain_ok": check.ok,
        "count": len(events),
        "checkpoint": anchor.checkpoint_dict(cp) if cp else None,
    }
    bundle_sig = sign_audit(canonical_bytes(body))
    return {
        **body,
        "bundle_signature": bundle_sig,
        "public_key": public_key_hex(),
        "focus_target": target,
        "focus_seqs": focus,
    }


def verify_bundle(bundle: dict, expected_public_key: str) -> dict:
    """Verify a bundle against a public key the VERIFIER supplies.

    The key must be pinned out of band (fetch it once from /api/audit/public-key
    or from the operator). Trusting the key embedded in the bundle would prove
    nothing, because a forger would simply embed their own key alongside a
    fabricated history that is internally consistent with it.
    """
    import hmac as _hmac

    from .ledger import _event_hash

    pub = bundle.get("public_key", "")
    if not expected_public_key or not _hmac.compare_digest(pub, expected_public_key):
        return {"ok": False, "reason": "bundle signed by an unknown key"}
    body = {
        "events": bundle["events"],
        "chain_ok": bundle["chain_ok"],
        "count": bundle["count"],
        "checkpoint": bundle.get("checkpoint"),
    }
    if not verify_audit(canonical_bytes(body), bundle.get("bundle_signature", ""), pub):
        return {"ok": False, "reason": "bundle signature invalid"}
    prev = ""
    by_seq = {}
    for ev in bundle["events"]:
        expect = _event_hash(ev["seq"], ev["actor"], ev["action"], ev["target"],
                             ev["payload"], prev, ev["ts"])
        if ev["this_hash"] != expect or ev["prev_hash"] != prev:
            return {"ok": False, "reason": f"chain broken at seq {ev['seq']}"}
        if not verify_audit(ev["this_hash"].encode(), ev["signature"], pub):
            return {"ok": False, "reason": f"signature invalid at seq {ev['seq']}"}
        prev = ev["this_hash"]
        by_seq[ev["seq"]] = ev

    cp = bundle.get("checkpoint")
    if cp:
        cpres = anchor.verify_checkpoint(cp, expected_public_key)
        if not cpres["ok"]:
            return {"ok": False, "reason": cpres["reason"]}
        if bundle["count"] < cp["count"] or cp["seq"] not in by_seq:
            return {"ok": False, "reason": "truncated relative to the signed checkpoint"}
        if by_seq[cp["seq"]]["this_hash"] != cp["head_hash"]:
            return {"ok": False, "reason": "checkpoint head does not match the exported events"}
        covered = [e["this_hash"] for e in bundle["events"] if e["seq"] <= cp["seq"]]
        if anchor.merkle_root(covered) != cp["tree_root"]:
            return {"ok": False, "reason": "checkpoint Merkle root does not match the exported events"}
    return {
        "ok": True,
        "count": len(bundle["events"]),
        "attested": bool(cp),
        "warning": "" if cp else "no signed checkpoint: truncation is not attested",
    }
