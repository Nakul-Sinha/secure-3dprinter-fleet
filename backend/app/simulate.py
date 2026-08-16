"""Printer and sensor simulators.

Produces per-bucket telemetry for three labeled scenarios:
- legitimate: readings follow the expected phase envelope,
- lazy-fake:  the printer reports done but draws only idle power (no real work),
- sabotaged:  readings mostly match, but a small contiguous window of printing
              buckets is defective (flow drops to zero, a void), which is the
              localized attack that sampling is not guaranteed to catch.
"""
from __future__ import annotations

import numpy as np

from .config import settings
from .constants import Phase, Scenario


def expected_timeline(duration: int) -> list[str]:
    """The phase the job is supposed to be in at each bucket."""
    idle = max(1, int(duration * 0.05))
    heating = max(1, int(duration * 0.15))
    cooling = max(1, int(duration * 0.10))
    printing = max(1, duration - idle - heating - cooling)
    seq = (
        [Phase.IDLE] * idle
        + [Phase.HEATING] * heating
        + [Phase.PRINTING] * printing
        + [Phase.COOLING] * cooling
    )
    # trim or pad to exactly duration
    seq = seq[:duration]
    while len(seq) < duration:
        seq.append(Phase.COOLING)
    return seq


def _mid(env, key):
    lo, hi = env[key]
    return (lo + hi) / 2.0


def _sample(rng, env, key):
    lo, hi = env[key]
    if hi <= lo:
        return float(lo)
    mid = (lo + hi) / 2.0
    span = (hi - lo) / 6.0  # keep within envelope with high probability
    return float(np.clip(rng.normal(mid, span), lo, hi))


def simulate(job_id: str, duration: int, scenario: str, seed: int = 0) -> list[dict]:
    rng = np.random.default_rng(abs(hash((job_id, seed))) % (2**32))
    timeline = expected_timeline(duration)
    envelopes = settings.envelopes
    idle_env = envelopes[Phase.IDLE]

    # sabotage window: a small contiguous slice of the printing phase
    printing_idx = [i for i, p in enumerate(timeline) if p == Phase.PRINTING]
    sab = set()
    if scenario == Scenario.SABOTAGED and printing_idx:
        w = max(1, int(len(printing_idx) * 0.03))  # 3 percent of printing
        start = printing_idx[len(printing_idx) // 2]
        sab = set(range(start, min(start + w, printing_idx[-1] + 1)))

    out = []
    for i in range(duration):
        phase = timeline[i]
        if scenario == Scenario.LAZY_FAKE:
            env = idle_env  # no real activity at all
            power = _sample(rng, env, "power")
            thermal = _sample(rng, env, "thermal")
            flow = 0.0
            actual_phase = Phase.IDLE
        else:
            env = envelopes[phase]
            power = _sample(rng, env, "power")
            thermal = _sample(rng, env, "thermal")
            flow = _sample(rng, env, "flow")
            actual_phase = phase
            if i in sab:
                flow = 0.0  # void: no material deposited while it should be printing
                power = float(env["power"][0] - 10)  # slightly low, still near-envelope
        out.append(
            {
                "bucket": i,
                "expected_phase": phase,
                "actual_phase": actual_phase,
                "power": round(power, 2),
                "thermal": round(thermal, 2),
                "flow": round(flow, 2),
                "plane": "independent",
            }
        )
    return out
