"""Ledger abstraction.

The same event schema runs on a chain (consensus enforced) or on a local
signed transparency log (evidenced). The MVP default is the log adapter: a
hash-chained, HMAC-signed append-only event stream. Any edit to, or deletion
from the middle of, the chain is detectable (it breaks a hash link).

Honest limit: deletion of the most recent (tail) events is NOT detectable from
the log alone, because the truncated chain remains internally consistent.
Closing that gap requires an external anchor of the signed head (public-chain
anchoring plus a qualified timestamp), which is Phase B. At tier A0 this is a
tamper-EVIDENT log, not a tamper-resistant ledger.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .crypto import audit_key, canonical_bytes, hmac_sign, hmac_verify, sha256_hex
from .models import AuditEvent, now_iso


@dataclass
class ChainCheck:
    ok: bool
    count: int
    first_bad_seq: int | None = None
    reason: str = ""


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
    """Hash-chained, signed transparency log."""

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
        ev.signature = hmac_sign(ev.this_hash.encode(), audit_key())
        session.flush()
        return ev

    def verify_chain(self, session: Session) -> ChainCheck:
        rows = list(session.execute(select(AuditEvent).order_by(AuditEvent.seq.asc())).scalars())
        prev = ""
        for ev in rows:
            expect = _event_hash(ev.seq, ev.actor, ev.action, ev.target, ev.payload, prev, ev.ts)
            if ev.this_hash != expect:
                return ChainCheck(False, len(rows), ev.seq, "hash mismatch (record altered)")
            if ev.prev_hash != prev:
                return ChainCheck(False, len(rows), ev.seq, "broken chain link")
            if not hmac_verify(ev.this_hash.encode(), ev.signature, audit_key()):
                return ChainCheck(False, len(rows), ev.seq, "bad signature")
            prev = ev.this_hash
        return ChainCheck(True, len(rows))


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
