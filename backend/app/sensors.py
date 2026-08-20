"""Independent-observation plane: external sensors the printer cannot spoof.

The anchor signal is mains power. A real smart plug or clamp meter sits on the
supply and reports actual watts, so it observes motor and heater work directly.
A printer controller has no electrical path to influence such a reading, which
is why this plane, and not firmware telemetry, is what a proof should be built
from.

Honest scope for this build: two implementations ship, and only one of them is a
real witness. `ShellyPowerMeter` talks to a physical device over HTTP.
`SimulatedPowerMeter` replays modelled data and is the default, so unless a
device is configured on the printer the "independent" plane is simulated. Every
sample therefore carries a `witness` provenance string, which is persisted and
surfaced, so nobody can mistake a modelled series for a physical observation.
"""
from __future__ import annotations

import statistics
from abc import ABC, abstractmethod

from .config import settings
from .constants import Phase, Plane


class PowerMeter(ABC):
    name: str = "abstract"
    physical: bool = False

    @property
    def provenance(self) -> str:
        """Where the readings came from. Recorded with every sample."""
        return self.name

    @abstractmethod
    def read_watts(self) -> float:
        ...

    def energy_kwh(self, watt_samples: list[float], interval_s: float = 1.0) -> float:
        if not watt_samples:
            return 0.0
        return sum(watt_samples) * interval_s / 3_600_000.0


class SimulatedPowerMeter(PowerMeter):
    """Replays a telemetry series produced by the simulator. Not a witness."""

    name = "simulated"
    physical = False

    def __init__(self, series: list[dict] | None = None):
        self.series = series or []
        self._i = 0

    def read_watts(self) -> float:
        if not self.series:
            return 0.0
        v = float(self.series[min(self._i, len(self.series) - 1)].get("power", 0.0))
        self._i += 1
        return v


class ShellyPowerMeter(PowerMeter):
    """Shelly-class energy-monitoring plug or DIN meter over local HTTP.

    Gen2 devices expose /rpc/Switch.GetStatus?id=0 with an `apower` field in
    watts. `http` is injectable so the adapter is testable without a device.
    """

    name = "shelly"
    physical = True

    def __init__(self, base_url: str, channel: int = 0, http=None, timeout: float = 3.0):
        self.base_url = base_url.rstrip("/")
        self.channel = channel
        self.timeout = timeout
        self._http = http

    @property
    def provenance(self) -> str:
        return f"shelly:{self.base_url}"

    def read_watts(self) -> float:
        path = f"/rpc/Switch.GetStatus?id={self.channel}"
        if self._http is not None:
            data = self._http("GET", self.base_url + path)
        else:
            import requests

            r = requests.get(self.base_url + path, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        return float(data.get("apower", data.get("power", 0.0)) or 0.0)


def sample_series(meter: PowerMeter, duration: int, expected_phases: list[str] | None = None) -> list[dict]:
    """Collect an independent-plane telemetry series from a power meter.

    A power meter observes watts only. Thermal and flow are left as None rather
    than zero-filled, so the verifier checks what was actually observed instead
    of judging a reading against modalities nobody measured.
    """
    out = []
    for bucket in range(duration):
        watts = meter.read_watts()
        phase = expected_phases[bucket] if expected_phases and bucket < len(expected_phases) else Phase.PRINTING
        out.append({
            "bucket": bucket,
            "expected_phase": phase,
            "actual_phase": None,
            "power": round(watts, 2),
            "thermal": None,
            "flow": None,
            "modalities": ["power"],
            "witness": meter.provenance,
            "physical_witness": meter.physical,
            "plane": Plane.INDEPENDENT,
        })
    return out


def gross_false_completion(series: list[dict]) -> dict:
    """Independent-plane check for a job that claims completion without work.

    A printer that reports done while drawing only idle power did not print.
    This uses the frozen idle envelope, so it stays consistent with the
    verification engine rather than inventing a second threshold.
    """
    watts = [float(s.get("power", 0.0)) for s in series]
    if not watts:
        return {"suspicious": True, "reason": "no independent power samples", "mean_watts": 0.0}
    idle_high = settings.envelopes[Phase.IDLE]["power"][1]
    mean = statistics.fmean(watts)
    peak = max(watts)
    active = sum(1 for w in watts if w > idle_high)
    suspicious = peak <= idle_high
    return {
        "suspicious": suspicious,
        "reason": ("power never rose above the idle envelope, so no physical work occurred"
                   if suspicious else "independent power shows real activity"),
        "mean_watts": round(mean, 2),
        "peak_watts": round(peak, 2),
        "active_buckets": active,
        "idle_threshold": idle_high,
        "energy_kwh": round(sum(watts) / 3_600_000.0, 6),
    }


_METERS = {"simulated": SimulatedPowerMeter, "shelly": ShellyPowerMeter}


def get_meter(kind: str = "simulated", **kw) -> PowerMeter:
    cls = _METERS.get(kind, SimulatedPowerMeter)
    if cls is SimulatedPowerMeter:
        return SimulatedPowerMeter(kw.get("series"))
    return cls(kw.pop("base_url", "http://127.0.0.1"), **kw)
