"""Checkpointing and anchoring of the audit log head.

A checkpoint is a signed, timestamped commitment to the log at a point in time:
the head hash, the event count, and a Merkle root over all event hashes. It does
three jobs:

1. Makes tail truncation detectable (ledger.verify_chain compares against it).
2. Gives an external party a small object to verify instead of the whole log.
3. Provides the digest that is anchored on-chain, so the commitment exists
   somewhere the operator of this server does not control.

The signature covers the body AND the timestamp stamp, so neither the head nor
the claimed time can be changed after the fact. Verification requires the
verifier to supply the public key it trusts: a key carried inside the object
being verified would prove nothing, since a forger would simply supply their own.
"""
from __future__ import annotations

import hashlib
import hmac

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


def body_digest(body: dict) -> str:
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def _signed_payload(body: dict, stamp: dict) -> bytes:
    return canonical_bytes({"body": body, "stamp": stamp})


def _normalize_stamp(stamp: dict) -> dict:
    return {
        "authority": stamp.get("authority", ""),
        "token": stamp.get("token", ""),
        "time": stamp.get("time", ""),
    }


def _stamp_of(cp: dict) -> dict:
    return {
        "authority": cp.get("tsa_authority", ""),
        "token": cp.get("tsa_token", ""),
        "time": cp.get("tsa_time", ""),
    }


def create_checkpoint(session: Session, anchor: bool = True) -> Checkpoint | None:
    """Sign, timestamp, and optionally anchor the current log head."""
    rows = list(session.execute(select(AuditEvent).order_by(AuditEvent.seq.asc())).scalars())
    if not rows:
        return None
    head = rows[-1]
    root = merkle_root([r.this_hash for r in rows])
    body = checkpoint_body(head.seq, len(rows), head.this_hash, root)
    digest = body_digest(body)
    stamp = get_authority().stamp(digest)
    # Sign exactly the fields that verification can reconstruct from the stored
    # checkpoint, so the payload is identical on both sides.
    signature = sign_audit(_signed_payload(body, _normalize_stamp(stamp)))

    cp = Checkpoint(
        seq=head.seq, count=len(rows), head_hash=head.this_hash, tree_root=root,
        signature=signature, public_key=public_key_hex(),
        tsa_authority=stamp["authority"], tsa_token=stamp["token"], tsa_time=stamp["time"],
    )
    if anchor:
        tx, err = anchor_on_chain(digest)
        cp.anchor_tx = tx
        cp.anchor_error = err
    session.add(cp)
    session.flush()
    get_ledger().append(session, "system", "CheckpointCreated", str(cp.seq),
                        {"count": cp.count, "root": root, "digest": digest,
                         "anchored": bool(cp.anchor_tx)})
    return cp


def anchor_on_chain(digest_hex: str) -> tuple[str | None, str | None]:
    """Anchor a checkpoint digest. Returns (tx_hash, error). Never raises."""
    try:
        from .chain import get_bridge

        bridge = get_bridge()
        if bridge is None:
            return None, "no chain bridge configured"
        tx = bridge.anchor(digest_hex)
        if tx and not bridge.is_anchored(digest_hex):
            return tx, "anchor transaction did not register the digest"
        return tx, None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def verify_against_chain(session: Session) -> dict:
    """Cross-check the local checkpoint against the on-chain anchor.

    An attacker with database access can delete local checkpoints, so local
    evidence alone cannot prove nothing was erased. The chain is outside that
    blast radius: if a digest is anchored there, a local log that no longer
    matches it is provably incomplete.
    """
    try:
        from .chain import get_bridge

        bridge = get_bridge()
        if bridge is None:
            return {"checked": False, "reason": "no chain bridge configured"}
        cp = latest(session)
        if cp is None:
            return {"checked": False, "reason": "no local checkpoint to compare"}
        body = checkpoint_body(cp.seq, cp.count, cp.head_hash, cp.tree_root)
        digest = body_digest(body)
        anchored = bridge.is_anchored(digest)
        return {
            "checked": True,
            "ok": anchored,
            "digest": digest,
            "reason": "" if anchored else
                      "the latest local checkpoint is not anchored on-chain",
        }
    except Exception as e:
        return {"checked": False, "reason": f"{type(e).__name__}: {e}"}


def latest(session: Session) -> Checkpoint | None:
    return session.execute(
        select(Checkpoint).order_by(Checkpoint.seq.desc()).limit(1)
    ).scalar_one_or_none()


def verify_checkpoint(cp: dict, expected_public_key: str) -> dict:
    """Verify a checkpoint offline against a public key the verifier trusts."""
    pub = cp.get("public_key", "")
    if not expected_public_key or not hmac.compare_digest(pub, expected_public_key):
        return {"ok": False, "reason": "checkpoint signed by an unknown key"}
    body = checkpoint_body(cp["seq"], cp["count"], cp["head_hash"], cp["tree_root"])
    stamp = _stamp_of(cp)
    if not verify_audit(_signed_payload(body, stamp), cp.get("signature", ""), pub):
        return {"ok": False, "reason": "checkpoint signature invalid"}
    authority = get_authority()
    if stamp.get("authority") == authority.name:
        if not authority.verify(body_digest(body), stamp, pub):
            return {"ok": False, "reason": "checkpoint timestamp does not attest this head"}
    return {"ok": True, "qualified_time": bool(cp.get("tsa_qualified", False))}


def checkpoint_dict(cp: Checkpoint) -> dict:
    return {
        "seq": cp.seq, "count": cp.count, "head_hash": cp.head_hash, "tree_root": cp.tree_root,
        "signature": cp.signature, "public_key": cp.public_key,
        "tsa_authority": cp.tsa_authority, "tsa_token": cp.tsa_token, "tsa_time": cp.tsa_time,
        "anchor_tx": cp.anchor_tx, "anchor_error": cp.anchor_error, "created_at": cp.created_at,
    }
