"""Commit-then-beacon verification engine (tier-A2 preview, run in simulation).

Flow: commit a per-bucket snapshot hash for the whole run, derive the audited
subset from a beacon round that is only known afterwards, reveal the sampled
buckets, and check each reading against its expected phase envelope.

Honest scoping:
- Sampling catches GROSS false-completion, with P(evade) = exp(-q * phi * n).
- Localized sabotage (a few defective buckets) is caught by CONTINUOUS
  screening of every bucket, not by sampling. Both results are reported.
"""
from __future__ import annotations

import hashlib
import math

from .beacon import round_signature, seed_from_round
from .config import settings
from .constants import Verdict

_TOL = 1e-6


def _prf(seed: str, i: int) -> int:
    return int(hashlib.sha256(f"{seed}|{i}".encode()).hexdigest(), 16)


def generate_schedule(seed: str, duration: int, n: int) -> list[int]:
    """Deterministic sample of n distinct bucket indices from a seed."""
    n = min(n, duration)
    idx = list(range(duration))
    # Fisher-Yates driven by the PRF
    for i in range(duration - 1, 0, -1):
        j = _prf(seed, i) % (i + 1)
        idx[i], idx[j] = idx[j], idx[i]
    return sorted(idx[:n])


def snapshot_commit(job_id: str, bucket: int, reading: dict, beacon_sig: str) -> str:
    core = {
        "job": job_id,
        "bucket": bucket,
        "power": reading["power"],
        "thermal": reading["thermal"],
        "flow": reading["flow"],
        "beacon": beacon_sig,
    }
    blob = "|".join(f"{k}={core[k]}" for k in sorted(core))
    return hashlib.sha256(blob.encode()).hexdigest()


def commit_all(job_id: str, telemetry: list[dict], r0: int = 1) -> list[str]:
    """Real-time commitments: each bucket bound to its concurrent beacon round."""
    commitments = []
    for reading in telemetry:
        i = reading["bucket"]
        sig = round_signature(r0 + i)
        commitments.append(snapshot_commit(job_id, i, reading, sig))
    return commitments


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


def in_envelope(reading: dict, phase: str) -> bool:
    env = settings.envelopes[phase]
    for key in ("power", "thermal", "flow"):
        lo, hi = env[key]
        val = reading[key]
        if val < lo - _TOL or val > hi + _TOL:
            return False
    return True


def p_evade(phi: float, n: int, q: float = 1.0) -> float:
    """Probability that sampling misses gross fakery. Zero if nothing is faked."""
    if phi <= 0:
        return 0.0
    return math.exp(-q * phi * n)


def verify_job(job_id: str, telemetry: list[dict], commitments: list[str], r0: int = 1, n: int | None = None) -> dict:
    duration = len(telemetry)
    n = n or settings.sampling_n
    # audit draw from a FUTURE round, computable only after all commits
    future_round = r0 + duration + 2
    seed = seed_from_round(future_round, job_id)
    sampled = generate_schedule(seed, duration, n)

    # sampling pass: recompute each sampled commitment (no post-hoc edit) and
    # check the reading against the EXPECTED phase envelope
    sampled_fail = []
    for i in sampled:
        reading = telemetry[i]
        sig = round_signature(r0 + i)
        recomputed = snapshot_commit(job_id, i, reading, sig)
        integrity_ok = recomputed == commitments[i]
        env_ok = in_envelope(reading, reading["expected_phase"])
        if not (integrity_ok and env_ok):
            sampled_fail.append({"bucket": i, "integrity": integrity_ok, "in_envelope": env_ok})

    sampling_ok = len(sampled_fail) == 0

    # continuous screening: every bucket against its expected envelope
    screen_fail = [t["bucket"] for t in telemetry if not in_envelope(t, t["expected_phase"])]
    phi = (len(screen_fail) / duration) if duration else 0.0
    pe = p_evade(phi, n)

    verdict = Verdict.VERIFIED_A0 if sampling_ok else Verdict.FAILED
    return {
        "verdict": verdict,
        "sampling_ok": sampling_ok,
        "n": n,
        "sampled": sampled,
        "sampled_failures": sampled_fail,
        "screening_failures": len(screen_fail),
        "screening_buckets": screen_fail[:50],
        "faked_fraction": round(phi, 4),
        "p_evade": pe,
        "merkle_root": merkle_root(commitments),
        "note": (
            "Sampling bounds gross false-completion (P_evade shown). "
            "Localized sabotage is caught by continuous screening, and internal "
            "correctness requires A3 physical ratification."
        ),
    }
