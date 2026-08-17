"""Printer driver abstraction (PI-1).

A seam so Phase B can plug in real firmware drivers (Moonraker, OctoPrint, Duet)
behind the same interface the scheduler and job service already use. The MVP
ships the simulated driver.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .simulate import simulate


class PrinterDriver(ABC):
    """Drives one print and yields per-bucket telemetry for the trusted plane."""

    name: str = "abstract"

    @abstractmethod
    def run(self, job_id: str, duration: int, scenario: str) -> list[dict]:
        ...


class SimulatedDriver(PrinterDriver):
    name = "simulated"

    def run(self, job_id: str, duration: int, scenario: str) -> list[dict]:
        return simulate(job_id, duration, scenario)


# Phase B adds: MoonrakerDriver, OctoPrintDriver, DuetDriver, PrusaLinkDriver.
_REGISTRY = {"simulated": SimulatedDriver}


def get_driver(driver_type: str = "simulated") -> PrinterDriver:
    return _REGISTRY.get(driver_type, SimulatedDriver)()
