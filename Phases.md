# Phases

This document is the build plan. It breaks the project into ordered phases and, inside each phase, into concrete work items that an engineering agent can pick up and build one at a time. Each work item lists what it produces and how to know it is done.

How to use this document:

- Build phases in order. Inside a phase, build work items roughly in the listed order, respecting the stated dependencies.
- Each work item has an identifier, a description, the module it belongs to (see [Features.md](Features.md)), and an acceptance check.
- Do not build a higher tier before its prerequisite tier is working. Tiers map to phases: A0 is Phase A, A1 is Phase C, A2 and A3 are Phase D.
- The requirements source of truth is [PRD.md](PRD.md). The architecture reference is [Architecture.md](Architecture.md).

## Phase 0: Foundation

Objective: a working development environment and repository skeleton.

| ID | Work item | Produces | Done when |
| --- | --- | --- | --- |
| 0-1 | Initialize the monorepo layout: contracts, backend, frontend, datasets, docs, scripts, tests. | Directory structure and a root readme for developers. | The tree exists and a developer readme explains how to run each part. |
| 0-2 | Set up the local chain tooling (Hardhat or Anvil) with a deploy script and a sample account set. | Local chain config and a deploy script. | A local chain starts and a hello contract deploys. |
| 0-3 | Set up the backend project (FastAPI or Node) with configuration, logging, and a health endpoint. | Backend skeleton. | The health endpoint returns ok. |
| 0-4 | Set up the frontend project (React or plain HTML and JavaScript) with routing and a layout shell. | Frontend skeleton. | The shell renders and can call the backend health endpoint. |
| 0-5 | Set up continuous integration: contract compile and test, backend lint and test, frontend build. | CI configuration. | CI runs green on an empty pass. |

Exit criteria: all skeletons build and talk to each other locally.

## Phase A: MVP core, tier A0

Objective: the base management product on a permissioned chain, plus a simulated verification preview. This is the investor MVP described in [MVP.md](MVP.md). Everything here is free to build.

### A.1 Smart contracts

| ID | Work item | Produces | Done when |
| --- | --- | --- | --- |
| A-1 | AccessControlHub contract with roles None, Client, Operator, Admin, Auditor, per-function permissions, and an AccessDenied event. Admin is a multisig-ready owner. | Access contract and tests. | Unauthorized calls revert and emit AccessDenied. Role grants and revokes work. |
| A-2 | PrinterRegistry contract: register printer, capabilities, status, availability. | Registry contract and tests. | Printers can be added, updated, and queried. |
| A-3 | JobRegistry contract: the job finite state machine, random non-personal job id, and lifecycle events as the audit stream. | Job contract and tests. | Legal transitions succeed, illegal transitions revert, and every transition emits an event. |
| A-4 | Deploy scripts and address wiring for the local chain. | Deploy pipeline. | One command deploys all three contracts and records addresses for the backend. |

### A.2 Backend and storage

| ID | Work item | Produces | Done when |
| --- | --- | --- | --- |
| A-5 | Chain bindings: read and write the three contracts, and index their events. | Chain client module. | The backend can call contracts and read event history. |
| A-6 | Encryption and hashing: envelope encryption with a per-job data key, and canonical content-addressed hashing of files. | Crypto module. | A file round-trips through encrypt and decrypt. Hash is stable and re-verifiable. |
| A-7 | Storage: store ciphertext in SQLite or local MinIO, return a content identifier, and re-verify the hash on retrieval. | Storage module. | Stored content re-verifies. A tampered blob is detected on retrieval. |
| A-8 | Job orchestration: the upload to authorize to schedule to run to complete flow, writing state to JobRegistry and emitting audit events. | Job service. | A job traverses the full happy path and is recorded on-chain. |
| A-9 | Scheduler: deterministic scoring and capability matching, reservations, and concurrency across simulated printers. | Scheduler module. | Given fixtures, routing is reproducible and never selects an incompatible printer. |
| A-10 | REST API: endpoints for auth, jobs, printers, materials, users, and audit, per the API summary in the PRD. | API layer. | Endpoints are documented and callable, with role scopes enforced. |

### A.3 Auth and access

| ID | Work item | Produces | Done when |
| --- | --- | --- | --- |
| A-11 | Login with single sign-on or a local identity provider for the MVP, issuing a session. | Auth module. | Users log in and receive a scoped session. |
| A-12 | Role enforcement mirrored to AccessControlHub, with separation of duties. | Access middleware. | A user cannot perform actions outside the role, and duties do not overlap. |

### A.4 Simulation and verification preview

| ID | Work item | Produces | Done when |
| --- | --- | --- | --- |
| A-13 | Printer simulator: drives a job through phases and exposes status. | Printer simulator. | A simulated job runs to completion with realistic status. |
| A-14 | Sensor simulator: per-second power, thermal, and flow series with legitimate, lazy-fake, and sabotaged profiles. | Sensor simulator. | The three profiles are distinguishable and labeled. |
| A-15 | Commit-then-beacon preview: generate a schedule, read the drand beacon (or a stub), commit snapshot hashes, reveal, and check envelopes. Record the result on-chain. | Verification preview module. | A legitimate job verifies. A fake-completion job is rejected. The probability bound is computed and shown. |

### A.5 Dashboard, datasets, and audit

| ID | Work item | Produces | Done when |
| --- | --- | --- | --- |
| A-16 | Dashboard screens: login, submit wizard, fleet monitor, job detail with tier-tagged status, print history, audit viewer, printer and material views, user admin. | Frontend. | Each screen works and enforces the role and action matrix. |
| A-17 | Audit viewer and export: the unified event stream with verifiable timestamps, plus a signed export bundle. | Audit feature. | The export re-verifies outside the application. |
| A-18 | Dataset generator: one hundred jobs across five printers and three materials, with materials, telemetry, and user records. | Datasets and generator. | Datasets regenerate deterministically and validate against the schema. |
| A-19 | Materials and inventory: lot registration, stock, reserve on schedule, decrement on consume, low-stock alerts. | Materials module. | Insufficient stock blocks scheduling and a low-stock alert fires. |

Exit criteria for Phase A: the seven investor demo steps in [MVP.md](MVP.md) run reliably, unauthorized actions are blocked, injected tampering is detected, and the fake-completion scenario is caught with the bound displayed honestly.

## Phase B: low-cost trust wins, still tier A0

Objective: add cheap, real trust signals without the full verification hardware.

| ID | Work item | Produces | Done when |
| --- | --- | --- | --- |
| B-1 | Real power signal: integrate one inexpensive smart-plug power meter per printer and record real energy per job. | Power integration. | Real kilowatt-hours per job appear on the dashboard. |
| B-2 | Power-based gross false-completion check: flag a done signal with idle power. | Real anti-false-completion signal. | A printer that reports done with no power draw is flagged. |
| B-3 | Public anchoring and qualified timestamps: anchor the audit-log root to a public chain and apply qualified timestamps to tree heads. | Anchoring service. | Anyone can verify the anchored root and the timestamp presumption. |
| B-4 | Real printer driver: integrate one open-firmware printer through the driver abstraction (Moonraker or OctoPrint). | First real driver. | A real print job runs and reports status through the platform. |

Exit criteria: a real printer can run a real job with a real power signal, and the audit log is externally anchored and timestamped.

## Phase C: multi-organization, tier A1

Objective: move from a solo chain to a consortium so tamper-resistance becomes real across parties. Requires the honesty gate: two or more adverse-interest organizations each running a validator.

| ID | Work item | Produces | Done when |
| --- | --- | --- | --- |
| C-1 | Governance charter and validator onboarding, defining membership, upgrade voting, and dispute resolution. | Governance documents. | A charter exists and validators can be onboarded and offboarded by policy. |
| C-2 | Deploy the same contracts on a Besu QBFT consortium with four or more validators across independent orgs. | Consortium deployment. | No organization holds one third or more of validators. Finality is instant. |
| C-3 | Move audit-log anchoring onto the consortium chain and keep periodic public anchoring. | Consortium anchoring. | Anchors are verifiable and no single member can rewrite history undetected. |
| C-4 | Smart-account identity and attestations: upgrade users to smart accounts with role attestations and gasless transactions. | Identity upgrade. | Non-crypto users transact without handling seed phrases or gas. |
| C-5 | SettlementEscrow, if payment disputes are real: release on Verified at A3, with the corrected economics from the PRD. | Escrow contract. | No party profits by misbehaving, funds never stick indefinitely, and honest operators are not slashed. |

Exit criteria: the platform runs on a multi-org consortium with tamper-resistant records and, optionally, safe settlement.

## Phase D: verifiable execution, tiers A2 and A3

Objective: prove that a job physically ran and, at A3, that the correct part was produced. Regulated and high-value verticals. Separately funded because it requires hardware and specialist work.

| ID | Work item | Produces | Done when |
| --- | --- | --- | --- |
| D-1 | Independent sensor set from two or more silicon vendors, sealed and enrolled on-chain, owned by a non-operator party. | Independent witness hardware. | Sensors sign readings at the source and are enrolled with a counterparty co-signature. |
| D-2 | Sensor-side freshness: sensors sign the reading combined with the current beacon, verified per sensor on-chain. | Freshness binding. | A replayed recording fails the beacon-round check. |
| D-3 | Hardened randomness: drand deadlines in beacon rounds, seed combined with a commit-reveal or verifiable-delay entropy source, permissionless draw, on-chain sampled-leaf verification. | Production randomness. | The draw is unpredictable to the gateway and re-derivable by anyone. |
| D-4 | Continuous screening: verify every bucket signature and run side-channel sabotage detectors over the full stream. | Screening engine. | Fabricated data on un-drawn buckets is detected. |
| D-5 | Reference signatures: per-G-code expected multi-modal profiles, generated, versioned, and calibrated. | Toolpath conformance. | In-envelope sabotage that a generic envelope would miss is flagged. |
| D-6 | Confidentiality enclave as an n of m heterogeneous quorum, hosted by the customer or consortium, releasing keys only to attested code after on-chain authorization. | Confidentiality layer. | A single enclave compromise cannot force a verdict or release a key. |
| D-7 | Physical part ratification: X-ray CT or PUF with an independent custody chain. One hundred percent CT for safety-critical parts. Customer-side PUF verification on receipt. | Physical ratifier. | A safety-critical job cannot reach Verified at A3 without a passing physical check. |
| D-8 | Wire payment to A3: escrow releases only against physical binding. | Payment gating. | No safety-critical payment releases on telemetry alone. |

Exit criteria: the same-part-replay and localized-sabotage acceptance scenarios pass, an empirical detection curve is produced, and a security and performance report is delivered.

## Feature distribution summary

- Contracts: Phase A for A0 contracts, Phase C for consortium and escrow, Phase D for the verification contract logic.
- Backend and storage: Phase A.
- Scheduler and materials: Phase A.
- Simulation and verification preview: Phase A.
- Real signals and anchoring: Phase B.
- Identity and governance upgrades: Phase C.
- Sensors, screening, enclave, and physical ratification: Phase D.

Build Phase A first. It is the whole MVP and it is free.
