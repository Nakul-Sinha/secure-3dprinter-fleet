"""Trusted timestamping.

A checkpoint carries a timestamp token from a timestamp authority so the time of
the audit head is attested by a party other than this server. The interface is
pluggable:

- LocalTSA is the default. It is a stub that signs the digest with the local
  audit key. It proves the digest existed no later than the server said, which
  is useful for development and testing, but it carries no independent legal
  weight because the same operator controls it.
- Rfc3161TSA calls a real RFC-3161 authority over the network. It is the
  production path and the one that carries an eIDAS presumption when the
  authority is qualified. It needs connectivity, so it is not exercised by the
  offline test suite.

The honest claim at tier A0 is therefore "timestamped by the local authority".
Only a qualified external authority upgrades that to a legal presumption.
"""
from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod

from .keys import sign_audit


class TimestampAuthority(ABC):
    name: str = "abstract"
    qualified: bool = False

    @abstractmethod
    def stamp(self, digest_hex: str) -> dict:
        """Return {authority, token, time, qualified}."""


class LocalTSA(TimestampAuthority):
    name = "local-dev-tsa"
    qualified = False

    def stamp(self, digest_hex: str) -> dict:
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        token = sign_audit(f"{self.name}|{digest_hex}|{now}".encode())
        return {"authority": self.name, "token": token, "time": now, "qualified": False}


class Rfc3161TSA(TimestampAuthority):
    """Real RFC-3161 client. Requires network access and the rfc3161ng package."""

    qualified = True

    def __init__(self, url: str, name: str | None = None):
        self.url = url
        self.name = name or url

    def stamp(self, digest_hex: str) -> dict:
        import base64

        import rfc3161ng  # imported lazily; optional dependency

        stamper = rfc3161ng.RemoteTimestamper(self.url, hashname="sha256")
        token = stamper(digest=bytes.fromhex(digest_hex))
        return {
            "authority": self.name,
            "token": base64.b64encode(token).decode(),
            "time": rfc3161ng.get_timestamp(token).isoformat(),
            "qualified": True,
        }


_authority: TimestampAuthority | None = None


def get_authority() -> TimestampAuthority:
    global _authority
    if _authority is None:
        import os

        url = os.environ.get("APP_TSA_URL", "")
        _authority = Rfc3161TSA(url) if url else LocalTSA()
    return _authority


def reset_authority_for_tests() -> None:
    global _authority
    _authority = None
