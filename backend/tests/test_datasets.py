import os

from app.datasets import generate


def test_dataset_generation(tmp_path):
    summary = generate(str(tmp_path), n_jobs=100)
    assert summary["jobs"] == 100
    assert summary["printers"] == 5
    assert summary["materials"] == 3
    assert summary["telemetry_rows"] > 0
    counts = summary["scenario_counts"]
    assert sum(counts.values()) == 100
    for name in ["jobs.csv", "materials.csv", "printers.csv", "users.csv", "telemetry.csv"]:
        assert os.path.exists(os.path.join(tmp_path, name))


def test_dataset_generation_is_deterministic(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    generate(str(a), n_jobs=20)
    generate(str(b), n_jobs=20)
    # telemetry must be byte-identical across process-independent regenerations
    assert (a / "telemetry.csv").read_text() == (b / "telemetry.csv").read_text()
    assert (a / "jobs.csv").read_text() == (b / "jobs.csv").read_text()
