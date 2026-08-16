# Features

This is the full inventory of features and building blocks. Each item is tagged with the module it belongs to, the assurance tier at which it becomes active, the phase that builds it (see [Phases.md](Phases.md)), and whether it is part of the MVP.

The MVP is the set of items marked MVP yes. Completing all of them delivers the investor-ready product described in [MVP.md](MVP.md).

Priority key: M is must, S is should, C is could.

## Block 1: Smart contracts

| ID | Feature | Tier | Phase | MVP | Priority |
| --- | --- | --- | --- | --- | --- |
| SC-1 | AccessControlHub: roles, per-function permissions, AccessDenied event | A0 | A | yes | M |
| SC-2 | PrinterRegistry: printer identity, capabilities, status, availability | A0 | A | yes | M |
| SC-3 | JobRegistry: job finite state machine, random non-personal id, lifecycle events | A0 | A | yes | M |
| SC-4 | Deploy scripts and address wiring for the local chain | A0 | A | yes | M |
| SC-5 | Events as the canonical audit stream, hash-chained and monotonic | A0 | A | yes | M |
| SC-6 | Merkle-root-per-job commitment pattern for snapshots | A2 | D | no | M |
| SC-7 | VerificationContract: draw, sampled-leaf verification, quorum verdict, tier stamping, immutable | A2 | D | no | M |
| SC-8 | SettlementEscrow: release on Verified at A3, dispute path, bond disposition | A1 | C | no | S |
| SC-9 | Proxy and governance: upgradeable operational contracts, immutable verifier, storage discipline | A1 | C | no | M |
| SC-10 | Certification-gated authorization in JobRegistry | A2 | D | no | S |

## Block 2: Backend and API

| ID | Feature | Tier | Phase | MVP | Priority |
| --- | --- | --- | --- | --- | --- |
| BE-1 | Chain client: read and write contracts, index events | A0 | A | yes | M |
| BE-2 | Job orchestration service: full lifecycle flow | A0 | A | yes | M |
| BE-3 | REST API: jobs, printers, materials, users, audit, with role scopes | A0 | A | yes | M |
| BE-4 | OpenAPI documentation, pagination, rate limiting, idempotency keys | A0 | A | yes | S |
| BE-5 | Webhooks: job completed, job failed, verification result, alerts | A0 | A | no | S |
| BE-6 | Northbound MES and ERP bridge (OPC-UA AM or MTConnect) | A1 | C | no | C |

## Block 3: Authentication and access control

| ID | Feature | Tier | Phase | MVP | Priority |
| --- | --- | --- | --- | --- | --- |
| AC-1 | Login via single sign-on or a local identity provider, scoped sessions | A0 | A | yes | M |
| AC-2 | Role enforcement mirrored to AccessControlHub | A0 | A | yes | M |
| AC-3 | Separation of duties across run, grant, and pay | A0 | A | yes | M |
| AC-4 | Admin multisig with timelock and guardian | A0 | A | no | S |
| AC-5 | Forward-safe revocation: freeze in-flight, never invalidate settled | A0 | A | no | S |
| AC-6 | Smart-account identity, attestations, gasless transactions | A1 | C | no | S |
| AC-7 | Machine identity: secure-element device keys enrolled on-chain | A2 | D | no | M |
| AC-8 | Certification credentials for operators and printers | A2 | D | no | S |

## Block 4: Storage and cryptography

| ID | Feature | Tier | Phase | MVP | Priority |
| --- | --- | --- | --- | --- | --- |
| ST-1 | Encrypted design upload, ciphertext at rest | A0 | A | yes | M |
| ST-2 | Envelope encryption: per-job data key wrapped by a key encryption key | A0 | A | yes | M |
| ST-3 | Canonical content-addressed hashing, hash re-verification on receipt | A0 | A | yes | M |
| ST-4 | On-chain minimization: only non-personal salted commitments anchored | A0 | A | yes | M |
| ST-5 | Provenance chain: design to slice to G-code, hashes anchored | A0 | A | no | S |
| ST-6 | Crypto-shredding of off-chain payloads for erasure | A0 | A | no | S |
| ST-7 | Permanent anchor copy for the final verified artifact | A1 | C | no | C |
| ST-8 | Enclave-gated decryption for printing, released after authorization | A3 | D | no | M |

## Block 5: Job lifecycle

| ID | Feature | Tier | Phase | MVP | Priority |
| --- | --- | --- | --- | --- | --- |
| JB-1 | Finite state machine with guarded transitions and audit events | A0 | A | yes | M |
| JB-2 | Authorization guard: role, entitlement, material, capability, quota | A0 | A | yes | M |
| JB-3 | Tier-tagged status everywhere, never a bare Verified | A0 | A | yes | M |
| JB-4 | Degraded and offline states with store and forward | A2 | D | no | S |

## Block 6: Scheduler

| ID | Feature | Tier | Phase | MVP | Priority |
| --- | --- | --- | --- | --- | --- |
| SD-1 | Deterministic scoring and capability matching | A0 | A | yes | M |
| SD-2 | Reservations and concurrency across printers | A0 | A | yes | M |
| SD-3 | Capacity exhaustion queueing with an SLA | A0 | A | yes | S |
| SD-4 | Failover re-route on printer fault | A0 | A | no | S |
| SD-5 | Verification header population at dispatch | A2 | D | no | M |
| SD-6 | Scheduling-integrity cross-check against the independent plane | A2 | D | no | S |

## Block 7: Materials and inventory

| ID | Feature | Tier | Phase | MVP | Priority |
| --- | --- | --- | --- | --- | --- |
| MT-1 | Material lot registration and stock levels | A0 | A | yes | M |
| MT-2 | Reserve on schedule and decrement on consume | A0 | A | yes | S |
| MT-3 | Low-stock alerts and material to job matching | A0 | A | yes | S |
| MT-4 | Material provenance binding into the digital thread | A2 | D | no | C |

## Block 8: Dashboard and user interface

| ID | Feature | Tier | Phase | MVP | Priority |
| --- | --- | --- | --- | --- | --- |
| UI-1 | Login and role-aware navigation | A0 | A | yes | M |
| UI-2 | Job submit wizard | A0 | A | yes | M |
| UI-3 | Fleet monitor with live status | A0 | A | yes | M |
| UI-4 | Job detail with tier-tagged status | A0 | A | yes | M |
| UI-5 | Print history and audit viewer with verifiable timestamps | A0 | A | yes | M |
| UI-6 | Verification result view | A0 | A | yes | S |
| UI-7 | Printer detail, material inventory, user admin | A0 | A | yes | S |
| UI-8 | Alerts and notifications panel | A0 | A | no | S |
| UI-9 | Role by screen and action permission matrix | A0 | A | yes | M |

## Block 9: Audit, query, and reporting

| ID | Feature | Tier | Phase | MVP | Priority |
| --- | --- | --- | --- | --- | --- |
| AU-1 | Unified event stream query with verifiable timestamps | A0 | A | yes | M |
| AU-2 | Signed audit-bundle export that re-verifies offline | A0 | A | yes | M |
| AU-3 | CSV and PDF export | A0 | A | yes | S |
| AU-4 | Reports: utilization, energy and cost, quality pass, audit | A0 | A | no | S |
| AU-5 | Event indexing with a subgraph or custom indexer | A0 | A | no | S |
| AU-6 | Public anchoring and qualified timestamps | A0 | B | no | M |

## Block 10: Datasets

| ID | Feature | Tier | Phase | MVP | Priority |
| --- | --- | --- | --- | --- | --- |
| DS-1 | Synthetic dataset generator: jobs, materials, telemetry, users | A0 | A | yes | M |
| DS-2 | Labeled telemetry: legitimate, lazy-fake, sabotaged | A0 | A | yes | M |
| DS-3 | Fixed counts: one hundred jobs, five printers, three materials | A0 | A | yes | S |
| DS-4 | Empirical detection-probability validation set | A2 | D | no | S |

## Block 11: Simulation and verification preview (MVP differentiator)

| ID | Feature | Tier | Phase | MVP | Priority |
| --- | --- | --- | --- | --- | --- |
| SM-1 | Printer simulator driving jobs through phases | A0 | A | yes | M |
| SM-2 | Sensor simulator with realistic profiles | A0 | A | yes | M |
| SM-3 | Commit-then-beacon preview using drand, with schedule, commit, reveal, and envelope check | A0 | A | yes | M |
| SM-4 | Fake-completion detection with the probability bound displayed | A0 | A | yes | M |
| SM-5 | Tampered-payload detection before execution | A0 | A | yes | M |

## Block 12: Printer integration

| ID | Feature | Tier | Phase | MVP | Priority |
| --- | --- | --- | --- | --- | --- |
| PI-1 | Printer driver abstraction interface | A0 | A | yes | S |
| PI-2 | First real driver: Moonraker or OctoPrint | A0 | B | no | M |
| PI-3 | Additional drivers: Duet, PrusaLink, and others | A0 | B | no | C |
| PI-4 | G-code safety linting at the gateway | A0 | B | no | S |
| PI-5 | Digital thread with signed 3MF, QIF quality, and a product passport | A2 | D | no | C |

## Block 13: Verifiable execution (funded roadmap)

| ID | Feature | Tier | Phase | MVP | Priority |
| --- | --- | --- | --- | --- | --- |
| VE-1 | Independent sensor set from two or more vendors, sealed and enrolled | A2 | D | no | M |
| VE-2 | Sensor-side freshness signing | A2 | D | no | M |
| VE-3 | Hardened randomness with round deadlines and combined entropy | A2 | D | no | M |
| VE-4 | Continuous screening over every bucket | A2 | D | no | M |
| VE-5 | Reference signatures for toolpath conformance | A2 | D | no | S |
| VE-6 | Confidentiality enclave as a heterogeneous quorum | A2 | D | no | M |
| VE-7 | Physical part ratification, CT or PUF, with independent custody | A3 | D | no | M |
| VE-8 | Payment gated on physical binding | A3 | D | no | M |

## Block 14: Governance, keys, and operations (funded roadmap)

| ID | Feature | Tier | Phase | MVP | Priority |
| --- | --- | --- | --- | --- | --- |
| GV-1 | Governance charter and validator onboarding | A1 | C | no | M |
| GV-2 | Besu QBFT consortium with four or more validators | A1 | C | no | M |
| GV-3 | Consortium anchoring and public checkpoints | A1 | C | no | M |
| GV-4 | Key custody by class: KMS or multi-party computation, secure elements | A1 | C | no | S |
| GV-5 | Incident response runbooks and disaster recovery | A1 | C | no | S |

## Block 15: Quality and delivery

| ID | Feature | Tier | Phase | MVP | Priority |
| --- | --- | --- | --- | --- | --- |
| QA-1 | Contract unit and invariant tests | A0 | A | yes | M |
| QA-2 | Backend and integration tests | A0 | A | yes | M |
| QA-3 | Tamper, replay, and sabotage acceptance scenarios | A0 | A | partial | M |
| QA-4 | Static analysis and continuous integration gates | A0 | A | yes | S |
| QA-5 | External smart-contract audit before production | A1 | C | no | M |

## Definition of done for the MVP

The MVP is complete when all of the following are true:

1. Contracts SC-1 through SC-5 are deployed on a local chain and pass their tests.
2. Backend BE-1 through BE-3 and storage ST-1 through ST-4 work end to end.
3. Auth AC-1 through AC-3 enforce roles and separation of duties.
4. Job lifecycle JB-1 through JB-3 and scheduler SD-1 through SD-3 run across simulated printers.
5. Materials MT-1 through MT-3 gate scheduling on stock.
6. Dashboard UI-1 through UI-5, UI-7, and UI-9 are usable, with audit AU-1 and AU-2 working.
7. Datasets DS-1 through DS-3 generate and validate.
8. Simulation and verification preview SM-1 through SM-5 demonstrate legitimate verification, fake-completion detection with the bound, and tampered-payload rejection.
9. Quality QA-1, QA-2, and the tamper, replay, and sabotage scenarios in QA-3 pass, and QA-4 gates the build.
10. The seven investor demo steps in [MVP.md](MVP.md) run reliably at zero build cost.
