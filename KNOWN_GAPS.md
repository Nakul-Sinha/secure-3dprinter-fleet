# Known gaps

This file is deliberate honesty about what the build does not yet deliver, so no
reader mistakes a scoped-out item for a delivered guarantee. Each open item maps
to a later phase in [Phases.md](Phases.md).

## Closed in Phase B

| Area | What now exists |
| --- | --- |
| External audit verification | Audit events, checkpoints, and export bundles are signed with **Ed25519**. Verification needs only the public key (`GET /api/audit/public-key`), so an external auditor can check a bundle without holding any secret that would let them forge one. |
| Tail truncation of the audit log | **Signed checkpoints** commit to the head hash, event count, and a Merkle root. `verify_chain` compares the log against the latest checkpoint, so deleting the newest events is now detected. |
| External anchoring | `AnchorRegistry.sol` anchors a checkpoint digest on-chain, putting the commitment somewhere the server operator does not control. Proven end to end in the CI integration job. |
| Trusted timestamping | Pluggable timestamp authority. `LocalTSA` is the offline default; `Rfc3161TSA` is the production client. |
| Real printer drivers | `MoonrakerDriver` and `OctoPrintDriver` speak the real firmware HTTP APIs, tested against injected fake transports. Attaching a printer is a configuration change, not a code change. |
| Independent observation plane | `sensors.py` provides the power-meter adapter (`ShellyPowerMeter` for real hardware, simulated for offline) and the gross-false-completion check. The job pipeline now builds its proof from the independent plane and fails a job whose power never rises above idle. |
| PDF export, pagination, rate limiting, idempotency keys | Implemented and tested. |

## Still open

| Area | Status | Deferred to |
| --- | --- | --- |
| Qualified (eIDAS) timestamps | The interface and an RFC-3161 client exist, but the default authority is local, so no legal time presumption is claimed. Pointing `APP_TSA_URL` at a qualified authority upgrades this. | Configuration, then Phase C |
| Real sensor hardware | The adapters are written and tested; no physical meter or printer is attached in this repository. | Phase B deployment |
| Multi-organization ledger | The chain path is real and CI-proven, but runs single-org. Tamper-resistance across parties needs validators at independent organizations. | Phase C |
| Payment settlement and bonds | `SettlementEscrow` is designed but not built. | Phase C |
| Independent witness ownership | The independent plane exists in software, but at A2 the witness must be owned and sealed by a party other than the operator. | Phase D |
| Physical part ratification (CT/PUF) | Out of scope until A3; internal-correctness proof and payment gating depend on it. | Phase D |
| Confidential enclave quorum | Not built. | Phase D |

The verdict shown to a user is always tier-tagged (`Verified@A0`) and never
implies more assurance than the tier earns.
