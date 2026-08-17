"""Synthetic dataset generator.

Produces the datasets the problem statement asks for: jobs, materials, printers,
users, and labeled per-bucket telemetry (legitimate, lazy-fake, sabotaged).
Fixed counts: 100 jobs across 5 printers and 3 materials.
"""
from __future__ import annotations

import csv
import os

import numpy as np

from .constants import Scenario
from .simulate import simulate

MATERIALS = [
    {"id": "mat-pla-001", "type": "PLA", "density": 1.24, "nominal_temp": 210, "cost_per_gram": 0.03},
    {"id": "mat-abs-001", "type": "ABS", "density": 1.04, "nominal_temp": 240, "cost_per_gram": 0.04},
    {"id": "mat-petg-001", "type": "PETG", "density": 1.27, "nominal_temp": 235, "cost_per_gram": 0.05},
]

PRINTERS = [
    {"id": f"printer-{i:02d}", "model": m, "materials": mats, "tolerance_class": tol}
    for i, (m, mats, tol) in enumerate(
        [
            ("Prusa-MK4", ["PLA", "PETG"], "fine"),
            ("Voron-2.4", ["PLA", "ABS", "PETG"], "precision"),
            ("Ender-3", ["PLA"], "standard"),
            ("UltiMaker-S5", ["PLA", "ABS", "PETG"], "fine"),
            ("Bambu-X1", ["PLA", "ABS", "PETG"], "precision"),
        ],
        start=1,
    )
]

USERS = [
    {"user_id": "admin", "role": "Admin", "org": "fleet", "granted_by": "system"},
    {"user_id": "op-1", "role": "Operator", "org": "fleet", "granted_by": "admin"},
    {"user_id": "op-2", "role": "Operator", "org": "fleet", "granted_by": "admin"},
    {"user_id": "client-acme", "role": "Client", "org": "acme", "granted_by": "admin"},
    {"user_id": "client-globex", "role": "Client", "org": "globex", "granted_by": "admin"},
    {"user_id": "auditor-1", "role": "Auditor", "org": "regulator", "granted_by": "admin"},
]


def generate(out_dir: str, n_jobs: int = 100, seed: int = 7) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    rng = np.random.default_rng(seed)

    def write_csv(name, rows, fields):
        with open(os.path.join(out_dir, name), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k) for k in fields})

    write_csv("materials.csv", MATERIALS, ["id", "type", "density", "nominal_temp", "cost_per_gram"])
    write_csv("printers.csv",
              [{**p, "materials": "|".join(p["materials"])} for p in PRINTERS],
              ["id", "model", "materials", "tolerance_class"])
    write_csv("users.csv", USERS, ["user_id", "role", "org", "granted_by"])

    clients = [u["user_id"] for u in USERS if u["role"] == "Client"]
    scenarios = ([Scenario.LEGITIMATE] * 70 + [Scenario.LAZY_FAKE] * 15 + [Scenario.SABOTAGED] * 15)
    rng.shuffle(scenarios)

    jobs = []
    telemetry_rows = []
    counts = {Scenario.LEGITIMATE: 0, Scenario.LAZY_FAKE: 0, Scenario.SABOTAGED: 0}
    for j in range(n_jobs):
        scenario = scenarios[j % len(scenarios)]
        counts[scenario] += 1
        material = MATERIALS[j % len(MATERIALS)]
        duration = int(rng.integers(90, 180))
        job_id = f"ds-job-{j:03d}"
        jobs.append({
            "job_id": job_id,
            "client": clients[j % len(clients)],
            "design": f"part_{j:03d}.3mf",
            "material": material["id"],
            "layer_height": round(float(rng.choice([0.1, 0.15, 0.2, 0.28])), 2),
            "est_duration": duration,
            "priority": int(rng.integers(1, 9)),
            "scenario": scenario,
        })
        for t in simulate(job_id, duration, scenario, seed=j):
            telemetry_rows.append({
                "job_id": job_id, "bucket": t["bucket"], "power": t["power"],
                "thermal": t["thermal"], "flow": t["flow"],
                "expected_phase": t["expected_phase"], "plane": t["plane"], "label": scenario,
            })

    write_csv("jobs.csv", jobs,
              ["job_id", "client", "design", "material", "layer_height", "est_duration", "priority", "scenario"])
    write_csv("telemetry.csv", telemetry_rows,
              ["job_id", "bucket", "power", "thermal", "flow", "expected_phase", "plane", "label"])

    summary = {
        "jobs": len(jobs),
        "printers": len(PRINTERS),
        "materials": len(MATERIALS),
        "users": len(USERS),
        "telemetry_rows": len(telemetry_rows),
        "scenario_counts": counts,
        "out_dir": os.path.abspath(out_dir),
    }
    return summary


if __name__ == "__main__":
    here = os.path.dirname(__file__)
    target = os.path.abspath(os.path.join(here, "..", "..", "datasets"))
    print(generate(target))
