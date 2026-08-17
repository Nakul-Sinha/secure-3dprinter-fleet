# Known gaps (tier A0 MVP)

This file is deliberate honesty about what the A0 MVP does not yet deliver, so
no reader mistakes a scoped-out item for a delivered guarantee. Each item maps
to a later phase in [Phases.md](Phases.md). The A0 claim is tamper-EVIDENT,
simulated printers and sensors, and anti-false-completion in simulation.

| Area | A0 status | Deferred to |
| --- | --- | --- |
| Tail-truncation of the audit log | Detectable only with an external anchor; the log alone cannot detect deletion of the most recent events. | Phase B (public anchoring) |
| Qualified timestamps (eIDAS) | Timestamps are server wall-clock inside the hash chain; no qualified timestamp authority yet, so no legal time presumption is claimed. | Phase B |
| External (asymmetric) audit verification | Bundles are HMAC-signed with a domain-separated audit key, re-verifiable by a holder of that key. A third party without the key cannot yet verify. | Phase B+ (Ed25519 signing) |
| On-chain path in the running app by default | The app default is the signed log; the chain bridge is real and CI-proven but is opt-in (`APP_LEDGER=chain`) and does not yet map per-user on-chain identities. | Phase C (identity) |
| Real printers and sensors | Simulated via `SimulatedDriver` and the sensor simulator. A `PrinterDriver` seam exists for real drivers. | Phase B (Moonraker/OctoPrint) |
| Independent-plane trust | All telemetry is simulated on one plane; no independent witness hardware. | Phase D |
| PDF export, API rate limiting, idempotency keys | Not implemented (CSV export and pagination are). | Phase B |
| Physical part ratification (CT/PUF) | Out of scope for A0; payment gating and internal-correctness proof depend on it. | Phase D (A3) |

The verdict shown to a user is always tier-tagged (`Verified@A0`) and never
implies more assurance than the tier earns.
