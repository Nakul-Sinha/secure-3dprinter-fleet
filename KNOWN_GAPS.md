# Known gaps

This file is deliberate honesty about what the build does not yet deliver, so no
reader mistakes a scoped-out item for a delivered guarantee. Each open item maps
to a later phase in [Phases.md](Phases.md).

## Closed in Phase B

| Area | What now exists |
| --- | --- |
| External audit verification | Audit events, checkpoints, and export bundles are signed with **Ed25519**. `verify_bundle` requires the caller to supply the public key it trusts (pin it once from `GET /api/audit/public-key`), so a bundle forged with an attacker's own key is rejected rather than verifying against itself. |
| Tail truncation of the audit log | **Signed checkpoints** commit to the head hash, event count, and Merkle root, and the signature covers the timestamp so the claimed time cannot be changed. `verify_chain` compares the log against the latest checkpoint. Checkpoints are created automatically every N events, so detection does not depend on somebody remembering to trigger one. |
| External anchoring | `AnchorRegistry.sol` anchors a checkpoint digest on-chain, and `verify_against_chain` cross-checks the local checkpoint against it. This is the only defense if an attacker with database access erases the local attestations. Proven end to end in CI with a real checkpoint digest. |
| Trusted timestamping | Pluggable authority with a `verify` method. `LocalTSA` is the offline default; `Rfc3161TSA` is the production client. |
| Real printer drivers | `MoonrakerDriver` and `OctoPrintDriver` speak the real firmware HTTP APIs, tested against injected fake transports and exercised through the full job pipeline. |
| Independent observation plane | `sensors.py` provides the power-meter adapters and the gross-false-completion gate, wired into the pipeline. Expected phases come from the authorized plan, never from the machine, so the controller cannot supply its own yardstick. |
| Hardware attachment as configuration | `Printer` carries `driver_type`, `driver_url`, `driver_api_key`, `meter_kind`, and `meter_url`. Pointing these at a real printer and a real meter drives physical hardware through the same code paths, with no code change. |
| PDF export, pagination, rate limiting, idempotency keys | Implemented. Idempotent replay is refused for unauthenticated requests, so a shared key behind one NAT cannot return another user's login token. |

## Closed in Phase C

| Area | What now exists |
| --- | --- |
| Settlement economics | `SettlementEscrow.sol` holds payment and a provider bond and releases only against a physical (A3) verdict. A missing verdict holds funds for arbitration instead of auto-refunding, a borderline failure disputes rather than slashes, the bond locks at funding rather than at job creation, and an expired arbitration unwinds neutrally so funds can never stick. Every terminal state is covered by a test. |
| Governance | `MultiSigTimelock.sol` puts privileged actions behind M-of-N approval plus a delay, with a guardian that can cancel but never execute. [GOVERNANCE.md](GOVERNANCE.md) defines roles, separation of duties, validator membership, disputes, and upgrades. |
| Consortium topology | `infra/besu` provides a four-validator QBFT compose file and bootstrap instructions, with the reasoning for why four is the minimum that tolerates a fault. |

## Still open

| Area | Status | Deferred to |
| --- | --- | --- |
| The witness is simulated by default | This is the most important caveat in the build. Unless a printer is configured with a real `meter_url`, the independent plane replays modelled data. Every sample and every verdict therefore records a `witness` provenance string and a `physical_witness` flag, and a verdict from a simulated witness carries a note saying it is evidence the protocol ran, not evidence of physical work. | Phase B deployment with hardware |
| Truncation detection granularity | Detected back to the last signed checkpoint. Events after it can still be removed, so the exposure window is the checkpoint interval (default 25 events). | Tune the interval, or Phase C |
| Qualified (eIDAS) timestamps | The interface and an RFC-3161 client exist, but the default authority is local and self-signed, so no legal time presumption is claimed. Pointing `APP_TSA_URL` at a qualified authority upgrades this. | Configuration |
| Multi-organization ledger | The contracts, the four-validator QBFT compose file, and the governance charter all exist. What cannot be supplied in software is the part that matters: validators operated by organizations with genuinely adverse interests. Until that is true the deployment is one administrative domain and the claim stays tamper-evident. | Deployment, not code |
| Payment settlement and bonds | `SettlementEscrow` is built and tested, including every terminal state and the stalling and griefing paths. It is not wired into the job pipeline, because releasing money requires the A3 physical verdict that no software-only build can produce. | Phase D |
| Independent witness ownership | Even with a real meter, at A2 the witness must be owned and sealed by a party other than the operator. Nothing in software can establish that. | Phase D |
| Physical part ratification (CT/PUF) | Out of scope until A3; internal-correctness proof and payment gating depend on it. | Phase D |
| Confidential enclave quorum | Not built. | Phase D |

The verdict shown to a user is always tier-tagged (`Verified@A0`) and never
implies more assurance than the tier earns.
