"""Checkpointing and anchoring of the audit log head.

A checkpoint is a signed, timestamped commitment to the log at a point in time:
the head hash, the event count, and a Merkle root over all event hashes. It does
three jobs:

1. Makes tail truncation detectable (ledger.verify_chain compares against it).
2. Gives an external party a small object to verify instead of the whole log.
3. Provides the digest that is anchored on-chain, so the commitment exists
   somewhere the operator of this server does not control.

Anchoring to the chain is best effort: if no chain is configured or reachable,
the checkpoint is still created and signed, and anchor_tx stays empty.
"""
from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from .crypto import canonical_bytes
from .keys import public_key_hex, sign_audit, verify_audit
from .ledger import get_ledger
from .models import AuditEvent, Checkpoint
from .timestamps import get_authority


def merkle_root(hashes: list[str]) -> str:
    if not hashes:
        return ""
    layer = list(hashes)
    while len(layer) > 1:
        nxt = []
        for i in range(0, len(layer), 2):
            a = layer[i]
            b = layer[i + 1] if i + 1 < len(layer) else layer[i]
            nxt.append(hashlib.sha256((a + b).encode()).hexdigest())
        layer = nxt
    return layer[0]


def checkpoint_body(seq: int, count: int, head_hash: str, tree_root: str) -> dict:
    return {"seq": seq, "count": count, "head_hash": head_hash, "tree_root": tree_root}


def create_checkpoint(session: Session, anchor: bool = True) -> Checkpoint | None:
    """Sign, timestamp, and optionally anchor the current log head."""
    rows = list(session.execute(select(AuditEvent).order_by(AuditEvent.seq.asc())).scalars())
    if not rows:
        return None
    head = rows[-1]
    root = merkle_root([r.this_hash for r in rows])
    body = checkpoint_body(head.seq, len(rows), head.this_hash, root)
    digest = hashlib.sha256(canonical_bytes(body)).hexdigest()
    signature = sign_audit(canonical_bytes(body))
    stamp = get_authority().stamp(digest)

    cp = Checkpoint(
        seq=head.seq, count=len(rows), head_hash=head.this_hash, tree_root=root,
        signature=signature, public_key=public_key_hex(),
        tsa_authority=stamp["authority"], tsa_token=stamp["token"], tsa_time=stamp["time"],
    )
    if anchor:
        cp.anchor_tx = anchor_on_chain(digest)
    session.add(cp)
    session.flush()
    get_ledger().append(session, "system", "CheckpointCreated", str(cp.seq),
                        {"count": cp.count, "root": root, "anchored": bool(cp.anchor_tx)})
    return cp


def anchor_on_chain(digest_hex: str) -> str | None:
    """Anchor a checkpoint digest on the configured chain. None if unavailable."""
    try:
        from .chain import get_bridge

        bridge = get_bridge()
        if bridge is None:
            return None
        return bridge.anchor(digest_hex)
    except Exception:
        return None


def latest(session: Session) -> Checkpoint | None:
    return session.execute(
        select(Checkpoint).order_by(Checkpoint.seq.desc()).limit(1)
    ).scalar_one_or_none()


def verify_checkpoint(cp: dict) -> dict:
    """Verify a checkpoint object offline using only its public key."""
    body = checkpoint_body(cp["seq"], cp["count"], cp["head_hash"], cp["tree_root"])
    ok = verify_audit(canonical_bytes(body), cp.get("signature", ""), cp.get("public_key"))
    return {"ok": ok, "reason": "" if ok else "checkpoint signature invalid"}


def checkpoint_dict(cp: Checkpoint) -> dict:
    return {
        "seq": cp.seq, "count": cp.count, "head_hash": cp.head_hash, "tree_root": cp.tree_root,
        "signature": cp.signature, "public_key": cp.public_key,
        "tsa_authority": cp.tsa_authority, "tsa_token": cp.tsa_token, "tsa_time": cp.tsa_time,
        "anchor_tx": cp.anchor_tx, "created_at": cp.created_at,
    }
