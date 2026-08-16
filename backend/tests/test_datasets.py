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
