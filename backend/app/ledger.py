"""Ledger abstraction.

The same event schema runs on a chain (consensus enforced) or on a local
signed transparency log (evidenced). The MVP default is the log adapter: a
hash-chained, Ed25519-signed, append-only event stream. Any edit to, or
deletion from the middle of, the chain is detectable because it breaks a hash
link, and any forgery is detectable because the signature will not verify
against the published public key.

Tail truncation, deleting the most recent events, leaves an internally
consistent chain. That is closed by signed checkpoints (see anchor.py): a
checkpoint commits to the head at a point in time, so a log that has fewer
events than the last checkpoint is provably truncated.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .crypto import canonical_bytes, sha256_hex
from .keys import sign_audit, verify_audit
from .models import AuditEvent, Checkpoint, now_iso


@dataclass
class ChainCheck:
    ok: bool
    count: int
    first_bad_seq: int | None = None
    reason: str = ""
    # attested is False when no signed checkpoint covers the log. The chain may
    # be internally consistent and still be missing its newest entries, so this
    # flag must be surfaced rather than folded into `ok`.
    attested: bool = False
    checkpoint_seq: int | None = None


def _event_hash(seq: int, actor: str, action: str, target: str, payload, prev: str, ts_iso: str) -> str:
    core = {
        "seq": seq,
        "actor": actor,
        "action": action,
        "target": target,
        "payload": payload,
        "prev": prev,
        "ts": ts_iso,
    }
    return sha256_hex(canonical_bytes(core))


class LedgerAdapter(ABC):
    @abstractmethod
    def append(self, session: Session, actor: str, action: str, target: str, payload: dict) -> AuditEvent: ...

    @abstractmethod
    def head(self, session: Session) -> str: ...

    @abstractmethod
    def verify_chain(self, session: Session) -> ChainCheck: ...


class LogLedger(LedgerAdapter):
    """Hash-chained, Ed25519-signed transparency log."""

    def head(self, session: Session) -> str:
        row = session.execute(
            select(AuditEvent).order_by(AuditEvent.seq.desc()).limit(1)
        ).scalar_one_or_none()
        return row.this_hash if row else ""

    def append(self, session: Session, actor: str, action: str, target: str, payload: dict) -> AuditEvent:
        prev = self.head(session)
        ev = AuditEvent(actor=actor, action=action, target=target, payload=payload, prev_hash=prev, ts=now_iso())
        session.add(ev)
        session.flush()  # assign seq
        ev.this_hash = _event_hash(ev.seq, actor, action, target, payload, prev, ev.ts)
        ev.signature = sign_audit(ev.this_hash.encode())
        session.flush()
        _maybe_checkpoint(session, ev.seq)
        return ev

    def verify_chain(self, session: Session) -> ChainCheck:
        rows = list(session.execute(select(AuditEvent).order_by(AuditEvent.seq.asc())).scalars())
        prev = ""
        expected_seq = None
        by_seq: dict[int, AuditEvent] = {}
        for ev in rows:
            expect = _event_hash(ev.seq, ev.actor, ev.action, ev.target, ev.payload, prev, ev.ts)
            if ev.this_hash != expect:
                return ChainCheck(False, len(rows), ev.seq, "hash mismatch (record altered)")
            if ev.prev_hash != prev:
                return ChainCheck(False, len(rows), ev.seq, "broken chain link")
            if not verify_audit(ev.this_hash.encode(), ev.signature):
                return ChainCheck(False, len(rows), ev.seq, "bad signature")
            if expected_seq is not None and ev.seq != expected_seq:
                return ChainCheck(False, len(rows), ev.seq,
                                  f"sequence gap: expected {expected_seq}, found {ev.seq}")
            expected_seq = ev.seq + 1
            prev = ev.this_hash
            by_seq[ev.seq] = ev

        return self._check_truncation(session, rows, by_seq)

    def _check_truncation(self, session: Session, rows: list[AuditEvent],
                          by_seq: dict[int, AuditEvent]) -> ChainCheck:
        cp = session.execute(
            select(Checkpoint).order_by(Checkpoint.seq.desc()).limit(1)
        ).scalar_one_or_none()

        # A checkpoint records itself in the log. If the log says checkpoints
        # were created but the checkpoint table does not have them, the
        # attestations were deleted, which is itself evidence of tampering.
        logged = [ev for ev in rows if ev.action == "CheckpointCreated"]
        if logged and (cp is None or cp.seq < max(int(ev.target) for ev in logged if ev.target.isdigit())):
            return ChainCheck(False, len(rows), logged[-1].seq,
                              "checkpoint records were deleted: the log references checkpoints "
                              "that no longer exist")
        if cp is None:
            return ChainCheck(True, len(rows), None,
                              "no signed checkpoint yet: tail truncation is not attested",
                              attested=False)
        if len(rows) < cp.count or cp.seq not in by_seq:
            return ChainCheck(False, len(rows), cp.seq,
                              "truncated: the log is shorter than the last signed checkpoint",
                              attested=True, checkpoint_seq=cp.seq)
        if by_seq[cp.seq].this_hash != cp.head_hash:
            return ChainCheck(False, len(rows), cp.seq,
                              "history rewritten: head at the checkpoint does not match",
                              attested=True, checkpoint_seq=cp.seq)
        return ChainCheck(True, len(rows), None, "", attested=True, checkpoint_seq=cp.seq)


_checkpointing = False


def _maybe_checkpoint(session: Session, seq: int) -> None:
    """Checkpoint periodically so the truncation-detection window is bounded.

    Without this, a deployment where nobody calls the checkpoint endpoint has no
    attestation at all. The guard prevents recursion, because creating a
    checkpoint itself appends an event.
    """
    global _checkpointing
    from .config import settings

    every = getattr(settings, "checkpoint_every", 0)
    if _checkpointing or not every or seq % every != 0:
        return
    _checkpointing = True
    try:
        from .anchor import create_checkpoint

        create_checkpoint(session, anchor=settings.anchor_checkpoints)
    except Exception:
        pass
    finally:
        _checkpointing = False


_ledger: LedgerAdapter | None = None


def get_ledger() -> LedgerAdapter:
    """The generic audit stream is always the signed transparency log. On-chain
    anchoring of the domain lifecycle (jobs, roles) is handled separately by the
    optional chain bridge (see chain.py), enabled with APP_LEDGER=chain."""
    global _ledger
    if _ledger is None:
        _ledger = LogLedger()
    return _ledger


def reset_ledger_for_tests() -> None:
    global _ledger
    _ledger = None
