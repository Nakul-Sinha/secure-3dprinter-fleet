"""Audit query, tamper-evidence verification, and signed export bundles."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .crypto import audit_key, canonical_bytes, hmac_sign, hmac_verify
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
    re-verifies and identifies the job's events.
    """
    events = [_event_dict(e) for e in list_events(session, limit=1_000_000)]
    check = verify_chain(session)
    focus = [e["seq"] for e in events if target is None or e["target"] == target]
    body = {"events": events, "chain_ok": check.ok, "count": len(events)}
    bundle_sig = hmac_sign(canonical_bytes(body), audit_key())
    return {**body, "bundle_signature": bundle_sig, "focus_target": target, "focus_seqs": focus}


def verify_bundle(bundle: dict) -> dict:
    """Recompute the hash chain, the per-event signatures, and the bundle signature."""
    from .ledger import _event_hash

    body = {"events": bundle["events"], "chain_ok": bundle["chain_ok"], "count": bundle["count"]}
    if not hmac_verify(canonical_bytes(body), bundle.get("bundle_signature", ""), audit_key()):
        return {"ok": False, "reason": "bundle signature invalid"}
    prev = ""
    for ev in bundle["events"]:
        expect = _event_hash(ev["seq"], ev["actor"], ev["action"], ev["target"],
                             ev["payload"], prev, ev["ts"])
        if ev["this_hash"] != expect or ev["prev_hash"] != prev:
            return {"ok": False, "reason": f"chain broken at seq {ev['seq']}"}
        if not hmac_verify(ev["this_hash"].encode(), ev["signature"], audit_key()):
            return {"ok": False, "reason": f"signature invalid at seq {ev['seq']}"}
        prev = ev["this_hash"]
    return {"ok": True, "count": len(bundle["events"])}
