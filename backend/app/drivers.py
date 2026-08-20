"""Printer driver abstraction and real firmware drivers.

The scheduler and job service talk to printers only through PrinterDriver, so a
simulated printer and a real one are interchangeable.

Trust note, and it is the important one: everything a driver returns comes from
the printer's own firmware, which the design treats as UNTRUSTED. Driver
telemetry is labelled plane="machine" and is used for the dashboard, progress,
and scheduling only. It must never anchor a verification proof. The proof is
built from the independent plane (see sensors.py), which observes the machine
from outside and cannot be spoofed by the controller.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

from .constants import Phase, Plane
from .simulate import simulate


class DriverError(Exception):
    pass


class PrinterDriver(ABC):
    """Drives one print and yields per-bucket telemetry."""

    name: str = "abstract"
    plane: str = Plane.MACHINE

    @abstractmethod
    def run(self, job_id: str, duration: int, scenario: str) -> list[dict]:
        ...

    def status(self) -> dict:
        return {"driver": self.name, "state": "unknown"}


class SimulatedDriver(PrinterDriver):
    name = "simulated"
    plane = Plane.INDEPENDENT  # the simulator stands in for the independent plane

    def run(self, job_id: str, duration: int, scenario: str) -> list[dict]:
        return simulate(job_id, duration, scenario)

    def status(self) -> dict:
        return {"driver": self.name, "state": "idle"}


class _HttpDriver(PrinterDriver):
    """Shared plumbing for HTTP firmware APIs.

    `http` is injectable so the drivers are testable without a printer: tests
    pass a fake that returns canned firmware responses.
    """

    def __init__(self, base_url: str, http=None, poll_interval: float = 0.0, timeout: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.poll_interval = poll_interval
        self.timeout = timeout
        self._http = http

    def _get(self, path: str) -> dict:
        if self._http is not None:
            return self._http("GET", self.base_url + path)
        import requests

        r = requests.get(self.base_url + path, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, payload: dict | None = None) -> dict:
        if self._http is not None:
            return self._http("POST", self.base_url + path, payload)
        import requests

        r = requests.post(self.base_url + path, json=payload or {}, timeout=self.timeout)
        r.raise_for_status()
        return r.json() if r.content else {}

    @staticmethod
    def _phase(state: str, nozzle: float, progress: float) -> str:
        state = (state or "").lower()
        if state in ("printing", "started", "running"):
            return Phase.PRINTING if nozzle >= 180 else Phase.HEATING
        if state in ("paused", "cooling", "complete", "completed", "finished"):
            return Phase.COOLING
        return Phase.IDLE

    def _sample(self, job_id: str, bucket: int) -> dict:
        raise NotImplementedError

    def run(self, job_id: str, duration: int, scenario: str) -> list[dict]:
        out = []
        for bucket in range(duration):
            out.append(self._sample(job_id, bucket))
            if self.poll_interval:
                time.sleep(self.poll_interval)
        return out


class MoonrakerDriver(_HttpDriver):
    """Klipper via the Moonraker HTTP API."""

    name = "moonraker"

    QUERY = "/printer/objects/query?extruder&heater_bed&print_stats&virtual_sdcard"

    def status(self) -> dict:
        data = self._get(self.QUERY).get("result", {}).get("status", {})
        stats = data.get("print_stats", {})
        return {
            "driver": self.name,
            "state": stats.get("state", "unknown"),
            "filename": stats.get("filename", ""),
            "nozzle": data.get("extruder", {}).get("temperature", 0.0),
            "bed": data.get("heater_bed", {}).get("temperature", 0.0),
            "progress": data.get("virtual_sdcard", {}).get("progress", 0.0),
        }

    def start(self, filename: str) -> dict:
        return self._post(f"/printer/print/start?filename={filename}")

    def cancel(self) -> dict:
        return self._post("/printer/print/cancel")

    def _sample(self, job_id: str, bucket: int) -> dict:
        s = self.status()
        nozzle = float(s.get("nozzle") or 0.0)
        return {
            "bucket": bucket,
            "expected_phase": self._phase(s.get("state", ""), nozzle, s.get("progress", 0.0)),
            "actual_phase": self._phase(s.get("state", ""), nozzle, s.get("progress", 0.0)),
            "power": 0.0,  # firmware cannot report mains power; independent plane supplies it
            "thermal": nozzle,
            "flow": 0.0,
            "progress": float(s.get("progress") or 0.0),
            "plane": Plane.MACHINE,
        }


class OctoPrintDriver(_HttpDriver):
    """Marlin and other serial firmwares via the OctoPrint REST API."""

    name = "octoprint"

    def __init__(self, base_url: str, api_key: str = "", **kw):
        super().__init__(base_url, **kw)
        self.api_key = api_key

    def status(self) -> dict:
        printer = self._get("/api/printer")
        job = self._get("/api/job")
        temps = printer.get("temperature", {})
        return {
            "driver": self.name,
            "state": printer.get("state", {}).get("text", "unknown"),
            "nozzle": temps.get("tool0", {}).get("actual", 0.0),
            "bed": temps.get("bed", {}).get("actual", 0.0),
            "progress": (job.get("progress", {}).get("completion") or 0.0) / 100.0,
        }

    def start(self, filename: str) -> dict:
        return self._post(f"/api/files/local/{filename}", {"command": "select", "print": True})

    def cancel(self) -> dict:
        return self._post("/api/job", {"command": "cancel"})

    def _sample(self, job_id: str, bucket: int) -> dict:
        s = self.status()
        nozzle = float(s.get("nozzle") or 0.0)
        phase = self._phase(s.get("state", ""), nozzle, s.get("progress", 0.0))
        return {
            "bucket": bucket,
            "expected_phase": phase,
            "actual_phase": phase,
            "power": 0.0,
            "thermal": nozzle,
            "flow": 0.0,
            "progress": float(s.get("progress") or 0.0),
            "plane": Plane.MACHINE,
        }


_REGISTRY = {
    "simulated": SimulatedDriver,
    "moonraker": MoonrakerDriver,
    "octoprint": OctoPrintDriver,
}


def get_driver(driver_type: str = "simulated", **kw) -> PrinterDriver:
    cls = _REGISTRY.get(driver_type, SimulatedDriver)
    if cls is SimulatedDriver:
        return SimulatedDriver()
    base_url = kw.pop("base_url", "http://127.0.0.1")
    return cls(base_url, **kw)
