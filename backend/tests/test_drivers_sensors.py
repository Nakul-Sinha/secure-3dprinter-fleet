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


def test_simulated_driver_is_labelled_as_a_simulated_witness():
    """The simulator stands in for the independent plane, but its output must
    declare that it is modelled data so no verdict reads as physical evidence."""
    tele = SimulatedDriver().run("j", 5, "legitimate")
    assert SimulatedDriver().plane == Plane.INDEPENDENT
    assert all(t["witness"] == "simulated" for t in tele)
    assert all(t["physical_witness"] is False for t in tele)


def test_real_driver_job_verifies_end_to_end(session, actors):
    """Regression: a power meter reports watts only. If the verifier demanded
    thermal and flow from it, every real-printer job would fail."""
    from app import jobs, materials, printers
    from app.constants import JobStatus

    materials.register_lot(session, id="mat-pla-001", type="PLA", stock_qty=1000)
    printers.add_printer(session, id="printer-real", model="Voron", materials=["PLA"],
                         tolerance_class="fine", driver_type="moonraker",
                         driver_url="http://printer.local")
    session.flush()

    import app.drivers as drv

    original = drv.MoonrakerDriver.__init__

    def patched(self, base_url, **kw):
        original(self, base_url, http=moonraker_http(), **kw)

    drv.MoonrakerDriver.__init__ = patched
    try:
        job = jobs.run_pipeline(session, actors["client"], actors["operator"],
                                design=b"real", design_name="real.3mf",
                                material_lot_id="mat-pla-001", duration=60)
    finally:
        drv.MoonrakerDriver.__init__ = original

    assert job.status == JobStatus.VERIFIED_A0


def test_power_only_series_passes_envelope_check():
    from app.simulate import expected_timeline
    from app.verify import in_envelope

    duration = 60
    phases = expected_timeline(duration)
    m = SimulatedPowerMeter(simulate("j", duration, "legitimate"))
    series = sample_series(m, duration, phases)
    # thermal and flow are unobserved, so they must be skipped rather than
    # judged as zero and failed
    assert series[0]["thermal"] is None and series[0]["flow"] is None
    assert all(in_envelope(s, s["expected_phase"]) for s in series)


def test_reading_with_no_observed_modality_fails_closed():
    from app.verify import in_envelope

    assert in_envelope({"power": None, "thermal": None, "flow": None}, "printing") is False


def test_series_records_witness_provenance():
    physical = ShellyPowerMeter("http://plug.local", http=lambda m, u: {"apower": 320.0})
    series = sample_series(physical, 3, ["printing"] * 3)
    assert series[0]["witness"] == "shelly:http://plug.local"
    assert series[0]["physical_witness"] is True

    modelled = sample_series(SimulatedPowerMeter(simulate("j", 3, "legitimate")), 3)
    assert modelled[0]["witness"] == "simulated"
    assert modelled[0]["physical_witness"] is False


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
