# Product Requirements Document (PRD)
## Blockchain-Based Secure & Tamper-Evident Multi-3D-Printer Management System

| | |
|---|---|
| **Product** | Secure, auditable fleet-management platform for 3D printers, with a progressively-verifiable execution overlay |
| **Companion doc** | *Solution Handbook* (architecture & protocol reference) - this PRD specifies **what** to build; the handbook specifies **how** it works |
| **Status** | v1.0 - production requirements baseline |
| **Method** | Derived from 3 research rounds + 5-front red-team + 3-front confirmation (16 agents, live sources) |
| **Date** | August 2026 |

---

## 1. Overview & product vision

The company operates a fleet of 3D printers and needs a **secure, tamper-evident management platform** that lets clients submit design jobs, routes them to authorized printers, monitors execution, and produces an **auditable, cryptographically-verifiable record** of what happened - protecting design IP and detecting false completion and tampering.

The product is delivered as a **fleet-management application on a permissioned blockchain**, plus an **optional, progressively-stronger verification overlay** expressed as an **assurance ladder (A0-A3)**. The base tier (A0) ships as a working product in weeks; higher tiers are additive and are switched on per-customer only when the trust configuration and economics justify them.

**Guiding principle (non-negotiable, applies to every requirement):** *cryptography cannot vouch for physical reality it did not independently observe.* Every guarantee is scoped to the trust configuration that earns it; the product **fails closed** to the honest lower tier rather than overclaiming.

---

## 2. Goals, non-goals & success metrics

### 2.1 Goals
- G1 - A single-org customer can upload → authorize → schedule → print → monitor → audit across multiple printers, with role-based access control, on day one.
- G2 - Design files and logs are stored tamper-evidently; any edit/deletion is cryptographically detectable; design IP is protected from bulk exfiltration.
- G3 - Smart contracts on a permissioned chain enforce access control and job lifecycle, and emit an immutable audit trail with verifiable timestamps.
- G4 - The platform can be upgraded, without re-architecture, to multi-party tamper-resistance (A1) and to verifiable physical execution / anti-false-completion (A2/A3).
- G5 - Every assurance claim shown to a user is accurate for that deployment's trust configuration.

### 2.2 Non-goals (v1)
- Decentralizing task delegation / a public print marketplace (manufacturing stays at known facilities).
- Proving *internal* part correctness from telemetry alone (that requires A3 physical ratification).
- Hiding a job's toolpath from the operator who must print it on a commodity (unattested) printer.
- zk-SNARK verification path, threshold proxy re-encryption, full cross-org DID federation (all v-next).

### 2.3 Success metrics (KPIs)
| KPI | Target |
|---|---|
| Time-to-first-value (A0 pilot deployed) | ≤ 8 weeks |
| Unauthorized-action block rate | 100% |
| Audit-log tamper detection | 100% of injected edits detected |
| Fake-completion catch rate (A2, gross) | ≥ 99% at φ ≥ 20% skipped |
| False-alarm rate on legitimate jobs (A2) | ≤ 1% |
| Scheduling throughput | ≥ fleet size × jobs/printer/day with < 2 s dispatch latency |
| Platform availability (A0 core) | ≥ 99.5% |

---

## 3. Personas
- **Fleet Admin** - owns the platform; manages users, printers, materials, policy; needs control + a defensible audit trail. Technical.
- **Operator** - runs/attends printers; dispatches and monitors jobs; needs a fast console and clear job state. Semi-technical.
- **Client / Design-Owner** (may be external) - submits design jobs, wants IP protected and proof their part was made. Non-crypto-native.
- **Auditor / Regulator** - read-only; needs a complete, verifiable, exportable history. Non-technical re: crypto.
- **Material Manager** - manages feedstock lots and inventory. Non-technical.
- **Security/Key Admin** - custodies keys, manages enrollment/revocation, incident response. Highly technical.

---

## 4. Assumptions & dependencies

### 4.1 Assumptions (register)
- AS1 - Base deployment is a **single company's own fleet** + external clients; multi-org settlement is a later upgrade.
- AS2 - Printers expose a controllable API (Moonraker/OctoPrint/Duet) or serial G-code.
- AS3 - For A1, ≥2 **adverse-interest** organizations will each operate a validator; for A2/A3, an **independent** (non-operator-owned) witness and independent CT/PUF custody exist. *If false, the affected tier is not offered and the system serves A0.*
- AS4 - Commodity printers have **no secure boot/attestation**; the platform is an external overlay that does not trust the machine.
- AS5 - Personal/patient data is kept **off-chain**; only non-personal random tokens are anchored.

### 4.2 Dependencies (register, each with fallback)
| Dependency | Used for | Fallback |
|---|---|---|
| Permissioned EVM (Hyperledger Besu QBFT); Hardhat/Anvil for dev | Ledger, contracts | Signed transparency log (Trillian/Rekor) where EVM undesirable |
| Encrypted object store (MinIO/S3) + Filecoin/Arweave anchor | File storage | Local encrypted store; DB |
| KMS (envelope encryption) | Key custody | HSM (regulated tier) |
| eIDAS qualified-timestamp TSA | Legal-grade timestamps | RFC-3161 TSA |
| drand quicknet (A2+) | Unpredictable sampling | Pause-not-fail; gated VRF fallback on proven round-skip |
| Confidential VM (Nitro/TDX/SEV-SNP, A2+) | Confidentiality only | n-of-m heterogeneous quorum; GovCloud for ITAR |
| Independent CT/NDT lab (A3) | Physical ratification | 100% CT for safety-critical |
| The Graph / indexer | Audit queries | Custom indexer over chain RPC / log |

---

## 5. Assurance-tier model (requirements reference these)
| Tier | Honest claim | Requires | Payment |
|---|---|---|---|
| **A0** (base) | Tamper-**evident** (edits detectable; EU rebuttable time presumption); not BFT | Base product | Manual/invoice |
| **A1** | Tamper-**resistant** across parties | ≥2 adverse-interest orgs each run a validator (N≥4 for 1-fault tolerance) | On-chain roles; optional escrow |
| **A2** | Quantified anti-**gross-false-completion** | ≥1 independent witness (verified) | No auto-release |
| **A3** | Physically-**verified** correct part | Independent witness + CT/PUF custody | **Payment gates here**; 100% CT for safety-critical |

**Enforcement:** the tier is a verifiable on-chain function of a signed **independence-attestation chain** (non-operator counterparty co-signs witness enrollment; auditor co-signs for the regulated tier). The badge renders only what the contract stamped. **Fail-closed:** absent a valid attestation → A0; an A3-committed job whose witness goes absent resolves to `Held`/`Failed`, never `Verified@A0`.

---

## 6. Data model (entities, key fields, enums)

**Enums (frozen):** `Role {None, Client, Operator, Admin, Auditor}` · `PrinterStatus {idle, printing, offline, maintenance, compromised}` · `JobStatus` (§9) · `AssuranceTier {A0, A1, A2, A3}` · `MaterialType {PLA, ABS, PETG, Nylon, Resin, Metal}` · `TelemetryPlane {machine, independent}` · `Verdict {none, VerifiedA0, VerifiedA2, VerifiedA3, Failed, Disputed}`.

| Entity | Key fields |
|---|---|
| **User** | id, org, role, authSubject(SSO), status, grantedBy, createdAt |
| **Printer** | id, model, driverType, buildVolume(x,y,z), materials[], toleranceClass, location, status, health, devicePubKey (A2+, nullable), capabilities |
| **MaterialLot** | id, type, lot#, density, nominalTemps, costPerGram, stockQty, supplier, provenanceRef |
| **Job** | id (random non-personal), clientId, designRef, sliceProfileRef, materialLotRef, printerId, status, assuranceTier, objectRef, fileHash, provenanceDAGRefs, verificationRef, bondRef, createdAt, dispatchedAt, completedAt |
| **DesignArtifact / SliceArtifact** | contentHash, parentHash, tool+version, params |
| **TelemetrySample** | jobId, bucket, modalityValues{}, plane, signature, beaconRef |
| **VerificationRecord** | jobId, scheduleCommit, merkleRoots[], drawnSet[], verdict, independenceAttestationRef, partBindingResult |
| **AuditEvent** | seq (monotonic), actor, action, target, prevHash, timestamp, signature |

---

## 7. Functional requirements

> Priority: **M**=Must, **S**=Should, **C**=Could. Tier = lowest tier where the requirement is active. Each maps to problem-statement item(s) (a)-(j).

### 7.1 Identity, authentication & access control
- **FR-IA-1 (M, A0, e)** - Users authenticate via enterprise SSO (OIDC/SAML); sessions via signed token (optionally SIWE at A1+). **AC:** invalid credentials denied; session expiry enforced.
- **FR-IA-2 (M, A0, c/e)** - Role-based access control is enforced by an on-chain `AccessControlHub` (OpenZeppelin AccessManager) with per-function permissions; the base may run app-RBAC mirrored to the contract. **AC:** an unauthorized state-changing call reverts and emits an `AccessDenied` event.
- **FR-IA-3 (M, A0, e)** - Separation of duties: whoever runs a job cannot grant roles or release payment; whoever grants roles cannot register/attest jobs. **AC:** attempts across duties are rejected.
- **FR-IA-4 (M, A0)** - Admin authority is a Safe multisig behind a timelock + guardian; no single EOA admin. **AC:** role changes require multisig + delay; guardian can emergency-freeze.
- **FR-IA-5 (S, A0)** - Onboarding/offboarding: SSO provision → role grant (audited); SSO deprovision → forward-safe revocation (freeze in-flight; **never** invalidate already-settled jobs). **AC:** a revoked user is blocked within the deny-list cache latency; settled records are untouched.
- **FR-IA-6 (S, A2)** - Certification binding: job authorization may require a valid "certified operator/printer for material X" credential (EAS/VC). **AC:** an uncertified operator cannot start a restricted-material job.
- **FR-IA-7 (S, A2)** - Machine identity: each printer/gateway is enrolled with a secure-element device key; snapshot commitments are per-sensor-signed and verified on-chain. **AC:** a commitment not signed by an enrolled key is rejected.

### 7.2 Design upload, storage & confidentiality
- **FR-ST-1 (M, A0, d/h)** - Clients upload design files (STL/3MF/G-code); the system stores the ciphertext in a private encrypted object store and content-addresses it. **AC:** plaintext never persists at rest unencrypted.
- **FR-ST-2 (M, A0, d)** - Envelope encryption: per-job DEK (AES-256-GCM), KEK in KMS. **AC:** DEK is never stored in plaintext; crypto-shred removes the off-chain payload.
- **FR-ST-3 (M, A0, d/j)** - Canonical-form hashing (RFC 8785 JCS for JSON metadata; 3MF inner-XML; normalized G-code); the file hash is anchored on-chain and **re-verified on receipt before printing** (reject on mismatch). **AC:** a tampered payload is rejected before execution.
- **FR-ST-4 (M, A0, h)** - Only **non-personal random tokens** and salted hashes are anchored on-chain; all human/patient linkage stays off-chain in a deletable store. **AC:** no field derivable from a natural person appears on-chain.
- **FR-ST-5 (S, A0)** - Provenance DAG: design → slice → G-code → material-lot → QIF → DPP, each node's hash anchored. **AC:** lineage of any job is reconstructable and integrity-checkable.
- **FR-ST-6 (S, A3)** - Decryption for printing occurs only inside the attested confidentiality enclave, released by KMS after the on-chain `Scheduled` event and revoked after completion. **AC:** DEK release requires both attestation and the on-chain authorization.
- **FR-ST-7 (M, A0)** - **Honest scope:** the UI/API must state that a job's toolpath is exposed to the executing operator on commodity printers (IP protection covers the archive and other jobs, handled contractually otherwise). **AC:** no UI implies toolpath confidentiality against the operator.

### 7.3 Job lifecycle & authorization
- **FR-JOB-1 (M, A0, c/j)** - A job progresses through the FSM (§9); each transition is guarded and emits an AuditEvent. **AC:** illegal transitions are rejected.
- **FR-JOB-2 (M, A0, c/e)** - `Authorized` requires: valid role + client entitlement + material availability + printer capability + quota. **AC:** a job failing any guard cannot be scheduled.
- **FR-JOB-3 (M, A0, j)** - Job status is always **tier-tagged** (`Verified@A0/A2/A3`); a bare "Verified" must never be displayed. **AC:** every status surface shows the tier.

### 7.4 Scheduling across multiple printers
- **FR-SC-1 (M, A0, f/i)** - The scheduler routes each authorized job to a capable, available printer using the deterministic scoring function (§11). **AC:** given fixtures, routing is reproducible.
- **FR-SC-2 (M, A0, f)** - Capability matching filters by material + build volume + tolerance class + health + availability. **AC:** an incompatible printer is never selected.
- **FR-SC-3 (M, A0, f)** - Concurrency: multiple jobs run on multiple printers simultaneously; reservations prevent double-booking. **AC:** the concurrent-multi-printer scenario (§14) passes.
- **FR-SC-4 (S, A0, f)** - Failover: on printer fault, pending jobs re-route; an in-flight faulted job → `Failed/Disputed` (never silently re-scheduled). **AC:** no committed verification header is orphaned.
- **FR-SC-5 (M, A2)** - On dispatch, the scheduler atomically populates the verification header (D, ω, S*, samplingPolicy). **AC:** header is immutable post-dispatch.
- **FR-SC-6 (S, A2)** - Scheduling-integrity: at A2+, capability/health used for routing are cross-checked against the independent plane (not operator-reported). **AC:** operator-biased routing inputs are flagged.

### 7.5 Verifiable execution (A2/A3)
- **FR-VE-1 (M, A2)** - Commit-then-beacon: per bucket, the trusted sensor signs `H(reading‖beacon)`; window Merkle roots are anchored before drand-round deadlines. **AC:** a stale/replayed reading fails the beacon-round check.
- **FR-VE-2 (M, A2)** - The audit subset is derived from a future drand round S* (seed = `sig_{S*} ⊕ commit-reveal/VDF entropy`, entropy fixed before reveal); draw submission is permissionless; sampled leaves verified on-chain (EIP-2537). **AC:** the gateway cannot predict the drawn set at commit time.
- **FR-VE-3 (M, A2)** - Continuous side-channel screening runs over **every** bucket (all per-bucket sensor signatures verified), not only the drawn subset. **AC:** fabricated data on un-drawn buckets is detectable.
- **FR-VE-4 (M, A2)** - The anti-false-completion bound is reported as `P_evade ≈ e^(−q·φ·n)` for **gross** false-completion only, with an empirically-calibrated, conservatively-floored q; localized sabotage is **not** claimed as covered by sampling. **AC:** no surface implies sampling catches single-layer sabotage.
- **FR-VE-5 (M, A3)** - Physical ratification: **100% X-ray CT** for correctness-/safety-critical jobs; CT random-subset + bond for non-catastrophic; mandatory customer-side PUF re-verification on receipt; bed→lab custody chain. **AC:** a safety-critical job cannot reach `Verified@A3` without a passing CT.
- **FR-VE-6 (M, A2)** - Enclave verdicts use an **n-of-m heterogeneous-vendor quorum**; disagreement → `Disputed`; a member that disagrees-then-loses is slashed. **AC:** a single compromised enclave cannot force `Verified` or silently force `Disputed` without penalty.
- **FR-VE-7 (S, A2)** - Cheap every-job plausibility check (perceptual/dimensional) reduces blatant substitution; labeled a plausibility check, counted toward assurance only if the camera is on the independent plane. **AC:** not presented as object-identity proof.

### 7.6 Ledger, audit & settlement
- **FR-LG-1 (M, A0, b/g/j)** - All lifecycle events form a single **unified, hash-chained, monotonic** audit stream (operational + verification), queryable with verified timestamps. **AC:** a gap or edit is detectable via sequence + prevHash + on-chain anchor.
- **FR-LG-2 (M, A0, d)** - eIDAS qualified timestamps are applied to periodic audit-log tree heads. **AC:** the timeline carries an EU rebuttable presumption of time.
- **FR-LG-3 (M, A2)** - Verification stores one Merkle root per job + snapshot events (not N storage writes); single-leaf verified on-chain under challenge. **AC:** on-chain cost per job is bounded regardless of snapshot count.
- **FR-LG-4 (M, A1)** - At A1, validators run at ≥3-4 independent orgs (N≥3f+1); periodic public anchoring of the state root. **AC:** no single org holds ≥⅓ of validators; anchor is externally verifiable.
- **FR-LG-5 (S, A1)** - `SettlementEscrow` (feature-flagged): releases stablecoin only on `Verified@A3`; bond locked at `Funded`; distinguishes `Fail` from `verdict-unavailable` (unavailable → arbitration holding funds); low-confidence/contested `Fail` → dispute (no auto-slash); bond disposition specified for **every** terminal state (`Funded→Expired` returns the operator bond); neutral, bounded arbitration. **AC:** no party profits by misbehaving; funds never stick indefinitely; honest operators are not slashed.

### 7.7 Querying, monitoring, dashboard & reporting
- **FR-UI-1 (M, A0, g)** - Screens: login/roles; job-submit wizard; fleet monitor; job detail (tier-tagged); print-history + audit viewer (verified timestamps, filter, export); verification-result view; printer detail; material inventory; user/role admin; alerts. **AC:** each screen enforces the role × action matrix.
- **FR-UI-2 (M, A0, g/j)** - Audit viewer shows the unified stream with verifiable timestamps and "no tampering detected" status; CSV/PDF export + signed audit bundle per job. **AC:** exported bundle re-verifies offline.
- **FR-UI-3 (S, A0)** - Fleet-ops monitoring & alerting (job-failure, verification-failure, printer-offline, material-low, SLA-breach) with escalation; notifications via email/SMS/webhook/in-app. **AC:** alerts fire within target latency.
- **FR-UI-4 (S, A0)** - Reports: utilization, kWh/cost (real energy at A0 via power meter), QA-pass, audit. **AC:** reports exportable.

### 7.8 Materials, datasets & integration
- **FR-MAT-1 (M, A0, a)** - Material-lot registration, stock levels, reserve-at-schedule, decrement-on-consume, low-stock alerts, material↔job matching. **AC:** insufficient stock blocks scheduling.
- **FR-DS-1 (M, A0, a)** - A synthetic-dataset generator produces the datasets (§12) with fixed counts and labels. **AC:** regenerable, schema-valid, used by scheduler tests and detector training.
- **FR-INT-1 (S, A0, f)** - Printer driver abstraction (Moonraker/OctoPrint/Duet/PrusaLink/Bambu). **AC:** adding a driver requires no contract/scheduler change.
- **FR-INT-2 (S, A0)** - G-code safety linting at the gateway (clamp temp ceilings, block `M302`/`M500`); firmware thermal protection kept on. **AC:** dangerous G-code is blocked pre-execution.
- **FR-INT-3 (C, A1)** - Northbound MES/ERP (OPC-UA AM / MTConnect) for work orders, material decrement, kWh/cost, QA disposition. **AC:** documented API contract.
- **FR-API-1 (M, A0)** - A documented REST/OpenAPI surface (§13) with auth scopes, pagination, rate limits, webhook schemas + retry semantics. **AC:** OpenAPI validates; rate limits enforced.

---

## 8. Non-functional requirements (targets)
- **NFR-PERF-1** - Dispatch decision < 2 s; audit query (single job) < 1 s; snapshot-commit latency < 5 s (A2).
- **NFR-SCALE-1** - Support ≥ 500 printers, ≥ 4,000 jobs/day, ≥ 80,000 snapshot events/day without redesign (Merkle batching).
- **NFR-AVAIL-1** - A0 core ≥ 99.5% uptime; RPO ≤ 15 min, RTO ≤ 4 h; A2 enclave/beacon losses degrade to `Held` (store-and-forward), never data loss.
- **NFR-SEC-1** - Contracts pass Slither + Foundry/Echidna invariant fuzzing + ≥1 external audit before production; align to IEC 62443 (gateway = OT), ISO 27001, NIST CSF.
- **NFR-PRIV-1** - No personal data on-chain; GDPR crypto-shredding for off-chain payloads; DPIA for medical; ITAR → US-person GovCloud enclave, public anchoring off.
- **NFR-USE-1** - Non-crypto users never handle seed phrases (gasless ERC-4337 at A1+; plain SSO at A0).
- **NFR-MAINT-1** - Operational contracts UUPS-upgradeable behind timelock+multisig; the VerificationContract is non-upgradeable; storage-layout CI checks on every version.
- **NFR-OBS-1** - Structured app + API access logging with retention; validator/infra monitoring (Prometheus/Grafana) separate from fleet-ops monitoring.

---

## 9. Job lifecycle FSM (states → tiers)
**A0-live:** `Draft → Submitted → Authorized → Scheduled → Dispatched → Printing → Verified@A0 | Failed | Cancelled | Expired`.
**A1/A2-added:** `Monitoring`, `AwaitingVerification`, `Disputed`, `Held`, `Verified@A2/A3`.
**Orthogonal:** `Degraded/Offline` (connectivity/enclave/drand loss → store-and-forward).
**Guards:** `Authorized` (role+entitlement+material+capability+quota); `Verified@A3` requires passing physical ratification; `Held` on committed-A3 witness-absence (never auto-`Verified@A0`). Bond/escrow disposition defined for **every** terminal state.

---

## 10. Key user journeys
- **UJ-1 Submit & print (Client):** login → upload design → pick material/priority → system authorizes, encrypts, stores, anchors hash → scheduler routes to an authorized printer → operator dispatches → monitor → `Verified@tier` + evidence bundle.
- **UJ-2 View history (Auditor):** open audit viewer → filter by job/date → see verified timestamps + "no tampering" → export signed bundle → re-verify offline.
- **UJ-3 Schedule under load (Operator):** multiple jobs queued → scheduler bin-packs across printers → capacity exhaustion queues with SLA → a printer faults → pending jobs re-route.
- **UJ-4 Onboard printer (Admin):** register printer + capabilities + (A2+) enroll device key + independence attestation → health-check acceptance.
- **UJ-5 Handle verification failure (Operator/Admin):** job flagged → dispute path (no auto-slash on low confidence) → CT adjudication → resolution recorded.

---

## 11. Scheduling algorithm (spec)
`score(printer, job) = w1·priority + w2·EDD_urgency − w3·queueDepth − w4·energyCost`, over the capable-and-available set (material + build volume + tolerance + health). Tie-break: lowest queueDepth, then FIFO by submit time. **Reservation** locks the printer on selection. **Capacity exhaustion:** queue (not reject) with SLA and position feedback. **Preemption:** only for a higher-priority job if the running job is preemptible (policy flag). **Failover:** on fault, release reservation, re-score pending jobs; in-flight faulted job → `Failed/Disputed`. Weights configurable; defaults published for reproducible acceptance tests.

---

## 12. Datasets spec (deliverable)
Fixed counts: **100 jobs × 5 printers × 3 materials.** Files: CSV + Parquet.
- **jobs.csv** - jobId, clientId, fileName, material, layerHeight, estDuration, expectedFeatureVector, label∈{legitimate, lazy-fake, sabotaged}.
- **materials.csv** - id, type, density, nominalTemp, costPerGram.
- **telemetry.parquet** - jobId, bucket, power, thermal, filamentFlow, acoustic, vibration, plane, label.
- **users.csv** - userId, wallet/subject, role, grantedBy, timestamp.
Used for: demos, scheduler tests, detector training, empirical **P_evade vs n** validation.

---

## 13. API surface (summary; full OpenAPI to be authored)
`/auth` (session, SSO/SIWE) · `/jobs` (POST submit, GET list/detail/status/history, POST cancel) · `/printers` (CRUD, POST enroll, PATCH availability, GET health) · `/materials` (CRUD, PATCH stock) · `/users`,`/roles` (admin) · `/audit` (GET history, GET job-bundle, GET verification-evidence) · `/webhooks` (job.completed, job.failed, verification.result, alert.*) · `/mes` (OPC-UA AM / MTConnect bridge). All: auth scope per operation, pagination, rate limits, idempotency keys for POST.

---

## 14. Acceptance / demo scenarios
1. **Legitimate job** - sensor stream matches profile; all sampled snapshots pass → `Verified@tier`.
2. **Fake completion** - idle/near-zero telemetry → caught; funds not released.
3. **Tampered payload** - receipt hash ≠ anchored hash → rejected before printing.
4. **Unauthorized access** - non-Client tries to register/schedule → revert + `AccessDenied` event.
5. **Concurrent multi-printer** - two authorized jobs on two printers → both independently verified.
6. **Same-part replay (new)** - replayed recording of a prior genuine run → fails sensor-side freshness / beacon-round check.
7. **Localized sabotage (new)** - single-layer void within envelopes → caught by continuous screening + (safety-critical) 100% CT, **not** claimed caught by sampling.

---

## 15. Compliance & data-governance requirements
- **CG-1** - No personal data on-chain (EDPB 02/2025: a keyed hash of personal data is still personal data); on-chain = non-personal random tokens only.
- **CG-2** - Right-to-erasure via off-chain crypto-shredding; on-chain footprint is non-personal-by-construction.
- **CG-3** - Legal timestamps via eIDAS Art. 41 QTSP (not the chain itself).
- **CG-4 (ITAR)** - US-person-controlled GovCloud/Azure-Gov enclave; public anchoring off by default.
- **CG-5 (Medical)** - Default A0-deletable config; DPIA; Art. 9 basis; BAAs with node operators; FDA QMSR/CSA + 21 CFR Part 11 validation if the system gates device release.
- **CG-6** - Standards posture is "designed to support conformance," never "certified."

---

## 16. Risk register (top)
| ID | Risk | Sev | Mitigation |
|---|---|---|---|
| R-1 | Independent witness fictional (single-org) | High | Fail-closed to A0; don't offer/charge for A2/A3; on-chain independence attestation |
| R-2 | Genuine-decoy / internal sabotage on paid parts | High | 100% CT for safety-critical; payment gates at A3 only |
| R-3 | Consortium fails to form (A1) | Med | Ship A0 first; A1 is an upgrade gated by the honesty test |
| R-4 | Enclave attestation forgery (TEE.Fail) | Med | Enclave = confidentiality only; n-of-m heterogeneous quorum; CT ratifier |
| R-5 | drand liveness | Med | Pause-not-fail; proven-round-skip-gated fallback |
| R-6 | GDPR/ITAR/medical overreach | Med | Non-personal on-chain; GovCloud; A0-deletable medical default |
| R-7 | Contract vulnerability | High | Fuzzing + static analysis + external audit + immutable verifier |
| R-8 | Cost of full stack unjustified for low-value parts | Med | Tiering; A0 software-only; A2/A3 only for high-liability verticals |

---

## 17. Milestones (mapped to the 6-month plan)
- **Kickoff-M1 (Phase A, A0):** data model + datasets; Solidity AccessControl/JobRegistry/PrinterRegistry on a permissioned chain (Hardhat/Anvil demo; single-node Besu pilot); encrypted store + canonical hashing; tamper-evident audit log; dashboard + API. *Exit: FR-IA/ST/JOB/SC/LG-1-2/UI/MAT/DS/API acceptance for scenarios 1,3,4,5.*
- **M1-M2 (Phase B, A0+):** power-meter kWh/job + gross anti-false-completion; public-anchor + eIDAS timestamps. *Exit: scenario 2 (gross) + verified-timestamp export.*
- **M2-M4 (Phase C, A1; only if a distrusting counterparty exists):** Besu consortium (≥3-4 orgs), on-chain AccessManager, SettlementEscrow if payment disputes are real; governance charter. *Exit: A1 tamper-resistance + escrow invariants.*
- **M4-Closure (Phase D, A2/A3; regulated/high-liability, separately funded):** commit-then-beacon + drand; sensor-side freshness + multi-vendor sensors; continuous screening + reference signatures; n-of-m enclave; independent witness; mandatory A3 CT/PUF (100% for safety-critical). *Exit: scenarios 6,7 + empirical P_evade curve + security/performance report.*

---

## 18. Traceability (problem statement → requirements)
| PS item | Requirements |
|---|---|
| a Data collection + datasets | FR-DS-1, FR-MAT-1, FR-LG-1, §12 |
| b Distributed ledger | FR-LG-1/3/4, §5 |
| c Smart contracts (access + execution) | FR-IA-2, FR-JOB-1/2 |
| d Tamper-proof storage | FR-ST-1/2/3, FR-LG-1/2 |
| e Auth & job authorization | FR-IA-1/2/3, FR-JOB-2 |
| f Scheduling across printers | FR-SC-1..6 |
| g Querying & monitoring | FR-UI-1/2/3 |
| h Blockchain + off-chain | FR-ST-1/4, FR-LG-1, §Dependencies |
| i End-to-end scheduling+monitoring | FR-SC-*, FR-UI-*, FR-JOB-* |
| j Use-cases (upload→verified; history→no-tamper) | FR-ST-3, FR-JOB-3, FR-LG-1/2, FR-UI-2 |

---

## 19. Glossary
**A0-A3** assurance tiers · **drand/quicknet** threshold-BLS randomness beacon · **commit-then-beacon** unpredictable-audit protocol · **PUF** physical unclonable function · **QBFT** Besu BFT consensus · **DEK/KEK** data/key-encryption keys · **ERC-4337** account abstraction · **EAS/VC** attestations / verifiable credentials · **EIP-2537** on-chain BLS precompile · **eIDAS Art. 41** qualified electronic timestamp · **CT/NDT** X-ray computed tomography / non-destructive testing · **DPP** EU Digital Product Passport · **TEE** trusted execution environment.

*Companion: see the Solution Handbook for architecture, protocol internals, threat model, and the residual-trust ledger.*
