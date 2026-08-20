"""Real-firmware drivers and the independent-plane power sensor.

Both are exercised against injected fake transports, so the code paths that will
talk to a real printer and a real meter are covered without hardware.
"""
from app.constants import Plane
from app.drivers import MoonrakerDriver, OctoPrintDriver, PrinterDriver, SimulatedDriver, get_driver
from app.sensors import (
    ShellyPowerMeter,
    SimulatedPowerMeter,
    gross_false_completion,
    get_meter,
    sample_series,
)
from app.simulate import simulate


# ---- drivers ----

def moonraker_http(state="printing", nozzle=210.0, progress=0.4):
    def _http(method, url, payload=None):
        if "/printer/objects/query" in url:
            return {"result": {"status": {
                "extruder": {"temperature": nozzle},
                "heater_bed": {"temperature": 60.0},
                "print_stats": {"state": state, "filename": "part.gcode"},
                "virtual_sdcard": {"progress": progress},
            }}}
        return {"ok": True}
    return _http


def octoprint_http(state="Printing", nozzle=205.0, completion=55.0):
    def _http(method, url, payload=None):
        if url.endswith("/api/printer"):
            return {"state": {"text": state},
                    "temperature": {"tool0": {"actual": nozzle}, "bed": {"actual": 60.0}}}
        if url.endswith("/api/job"):
            return {"progress": {"completion": completion}}
        return {"ok": True}
    return _http


def test_moonraker_driver_reads_status_and_telemetry():
    d = MoonrakerDriver("http://printer.local", http=moonraker_http())
    s = d.status()
    assert s["state"] == "printing" and s["nozzle"] == 210.0
    tele = d.run("job-1", 5, "legitimate")
    assert len(tele) == 5
    assert tele[0]["expected_phase"] == "printing"
    # firmware telemetry is the UNTRUSTED plane and must be labelled as such
    assert all(t["plane"] == Plane.MACHINE for t in tele)


def test_moonraker_heating_phase_when_nozzle_cold():
    d = MoonrakerDriver("http://p", http=moonraker_http(state="printing", nozzle=80.0))
    assert d.run("j", 1, "legitimate")[0]["expected_phase"] == "heating"


def test_octoprint_driver_reads_status_and_telemetry():
    d = OctoPrintDriver("http://octo.local", api_key="k", http=octoprint_http())
    s = d.status()
    assert s["state"] == "Printing"
    assert round(s["progress"], 2) == 0.55
    tele = d.run("job-2", 3, "legitimate")
    assert len(tele) == 3 and all(t["plane"] == Plane.MACHINE for t in tele)


def test_driver_registry_and_fallback():
    assert isinstance(get_driver("simulated"), SimulatedDriver)
    assert isinstance(get_driver("moonraker", base_url="http://x"), MoonrakerDriver)
    assert isinstance(get_driver("octoprint", base_url="http://x"), OctoPrintDriver)
    assert isinstance(get_driver("nope"), SimulatedDriver)
    assert isinstance(get_driver("moonraker", base_url="http://x"), PrinterDriver)


def test_simulated_driver_is_independent_plane():
    assert SimulatedDriver().plane == Plane.INDEPENDENT


# ---- sensors ----

def test_shelly_meter_reads_watts():
    calls = []

    def _http(method, url):
        calls.append(url)
        return {"apower": 312.5}

    m = ShellyPowerMeter("http://plug.local", http=_http)
    assert m.read_watts() == 312.5
    assert "Switch.GetStatus" in calls[0]


def test_simulated_meter_replays_series():
    series = simulate("j", 10, "legitimate")
    m = SimulatedPowerMeter(series)
    vals = [m.read_watts() for _ in range(10)]
    assert len(vals) == 10 and max(vals) > 0


def test_sample_series_is_independent_plane():
    m = SimulatedPowerMeter(simulate("j", 6, "legitimate"))
    out = sample_series(m, 6)
    assert len(out) == 6
    assert all(s["plane"] == Plane.INDEPENDENT for s in out)


def test_power_check_flags_fake_completion():
    fake = simulate("j-fake", 60, "lazy-fake")
    res = gross_false_completion(sample_series(SimulatedPowerMeter(fake), 60))
    assert res["suspicious"] is True
    assert "idle" in res["reason"]


def test_power_check_passes_real_job():
    real = simulate("j-real", 60, "legitimate")
    res = gross_false_completion(sample_series(SimulatedPowerMeter(real), 60))
    assert res["suspicious"] is False
    assert res["active_buckets"] > 0
    assert res["energy_kwh"] > 0


def test_power_check_handles_empty_series():
    assert gross_false_completion([])["suspicious"] is True


def test_get_meter_registry():
    assert isinstance(get_meter("simulated"), SimulatedPowerMeter)
    assert isinstance(get_meter("shelly", base_url="http://x"), ShellyPowerMeter)
