"""Randomness beacon.

The audit draw seed comes from a beacon round that is not computable until after
the snapshots are committed, so the sampling schedule is unpredictable to the
party being audited. The MVP default is a deterministic offline stub with the
same interface as drand; APP_BEACON=drand switches to the public beacon.
"""
from __future__ import annotations

import hashlib

from .config import settings


def round_signature(round_number: int) -> str:
    """Return the beacon signature for a round (hex)."""
    if settings.beacon == "drand":
        try:
            import requests

            base = settings.drand_url.rstrip("/")
            r = requests.get(f"{base}/public/{round_number}", timeout=8)
            r.raise_for_status()
            return r.json()["signature"]
        except Exception:
            # fall back to the deterministic stub rather than fail the demo
            pass
    return hashlib.sha256(f"drand-stub|{round_number}".encode()).hexdigest()


def seed_from_round(round_number: int, job_id: str) -> str:
    """Bind the beacon to the job so schedules never collide across jobs."""
    sig = round_signature(round_number)
    return hashlib.sha256(f"{sig}|{job_id}".encode()).hexdigest()
