# Datasets

Synthetic datasets for the platform, produced by `backend/app/datasets.py`.
Regenerate with:

```
cd backend
python -m app.datasets
```

Fixed size: 100 jobs across 5 printers and 3 materials, with labeled per-bucket
telemetry.

| File | Contents |
| --- | --- |
| `jobs.csv` | job id, client, design, material, layer height, estimated duration, priority, scenario label |
| `materials.csv` | material lots: type, density, nominal temperature, cost per gram |
| `printers.csv` | printer id, model, supported materials, tolerance class |
| `users.csv` | user id, role, org, granted-by |
| `telemetry.csv` | per-bucket power, thermal, flow, expected phase, plane, and scenario label |

Telemetry labels: `legitimate`, `lazy-fake` (no real activity), and `sabotaged`
(a localized defect window). These drive the scheduler tests, detector training,
and the empirical P(evade) validation.
