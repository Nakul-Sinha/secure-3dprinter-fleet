from app.drivers import PrinterDriver, SimulatedDriver, get_driver


def test_simulated_driver_produces_telemetry():
    d = get_driver("simulated")
    assert isinstance(d, PrinterDriver)
    tele = d.run("job-x", 50, "legitimate")
    assert len(tele) == 50
    assert {"bucket", "power", "thermal", "flow", "expected_phase"} <= set(tele[0])


def test_unknown_driver_falls_back_to_simulated():
    assert isinstance(get_driver("does-not-exist"), SimulatedDriver)
