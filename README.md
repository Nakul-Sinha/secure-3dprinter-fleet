# Secure and Tamper-Evident Multi-3D-Printer Management System

A blockchain-based platform for securely managing a fleet of 3D printers. It gives design owners, fleet operators, and auditors a shared, tamper-evident record of every print job, protects design intellectual property, and can prove that a job physically ran without trusting the machine or its operator.

_[work in progress] The tier-A0 MVP is built, tested, and running; the higher-assurance tiers are the staged roadmap in [Phases.md](Phases.md)._

![CI](https://github.com/Nakul-Sinha/secure-3dprinter-fleet/actions/workflows/ci.yml/badge.svg)

## What this is

Distributed and outsourced manufacturing creates a trust gap: when a company sends a design to a printer it does not fully control, the design can be stolen, print files and logs can be altered, a defective part can be passed off as good, and no single record exists that a client, an operator, and a regulator all trust and none can secretly rewrite.

This platform closes that gap. It manages multiple printers end to end (upload, authorize, schedule, dispatch, monitor, audit), stores design files and logs so that any change is cryptographically detectable, enforces access control and the job lifecycle in smart contracts on a permissioned chain, and produces an immutable, queryable history with verifiable timestamps. On top of that base it adds a verification overlay that makes a fake "job complete" signal statistically very hard to forge.

## Core principle: honest, tiered assurance

The guiding rule of the project is strict: cryptography cannot vouch for physical reality it did not independently observe. Every guarantee is scoped to the trust configuration that earns it, and the system fails closed to the weaker honest claim rather than overclaiming. The blockchain is present at every level; what changes across levels is the strength of the claim you are allowed to make.

| Tier | Honest claim | What it needs |
| --- | --- | --- |
| A0 | Tamper-evident. Any edit or deletion is detectable. Not yet Byzantine-fault-tolerant. | The base product on a permissioned chain. Software only. |
| A1 | Tamper-resistant across mutually distrusting parties. | Two or more independent organizations each run a validator. |
| A2 | Quantified guarantee against gross false completion. | At least one genuinely independent witness sensor. |
| A3 | High assurance that the correct part was physically produced. Payment gates here. | Independent witness plus physical ratification (X-ray CT or PUF). |

The one sentence to remember: the chain is the deliverable, Byzantine-fault-tolerant trust is a tiered claim, and physically verified correctness is the top tier and the only basis for gating payment on safety-critical parts.

## Features

The tier-A0 build delivers the full base product:

- Role-based access control (Admin, Operator, Client, Auditor) enforced in smart contracts, with separation of duties.
- Encrypted, content-addressed storage of design files (envelope encryption with a per-job data key); tampering is detected before a printer ever runs the file.
- A hash-chained, signed, append-only audit log with verifiable timestamps, and a signed audit bundle that re-verifies offline.
- Secure job scheduling across multiple printers: capability and health matching, reservations, concurrency, and a real queue under capacity exhaustion.
- Material and inventory management with reserve, consume, and low-stock signals.
- A commit-then-beacon verification engine that bounds gross false completion with an unpredictable, publicly re-derivable sampling schedule, plus continuous screening that catches localized sabotage and gates the verdict (so a flagged part never shows as verified).
- A synthetic dataset generator (100 jobs across 5 printers and 3 materials, with labeled telemetry).
- A web dashboard for login, job submission, fleet monitoring, tier-tagged job status, user administration, and the audit viewer with an integrity check and CSV export.
- A real on-chain path (web3) that binds to the deployed registries and enforces roles, proven end to end in continuous integration against a live chain.

## Technology stack

- Smart contracts: Solidity, tested with Hardhat. Runs on a local chain for development and on Hyperledger Besu (QBFT) for a permissioned deployment.
- Backend: Python with FastAPI; SQLAlchemy; cryptography; web3 for the chain path.
- Randomness (A2 and above): the drand threshold beacon.
- Frontend: a vanilla HTML and JavaScript dashboard served by the backend.
- Continuous integration: GitHub Actions runs the contract tests, the backend test suite, and a chain-integration job that deploys to a Hardhat node.

## Quickstart

Prerequisites: Node.js 20 or newer and Python 3.12 or newer.

Contracts:

```
cd contracts
npm install
npx hardhat test
```

Backend, dashboard, and tests:

```
cd backend
pip install -r requirements.txt
pytest
uvicorn app.main:app --reload
```

The dashboard is served at http://127.0.0.1:8000. Sign in as `admin`, seed the demo data, then follow the walkthrough in [MVP.md](MVP.md): submit a job, run it, try tampering (detected), run a fake completion (rejected), and attempt an unauthorized action (blocked). The whole MVP runs on a laptop at zero cost.

Optional real-chain path:

```
cd contracts
npx hardhat node            # terminal 1: local chain
npm run deploy:local        # terminal 2: deploy the registries
cd ../backend && APP_LEDGER=chain pytest tests/test_chain_integration.py
```

## Repository structure

| Path | Contents |
| --- | --- |
| `contracts/` | Solidity smart contracts and Hardhat tests. |
| `backend/` | FastAPI application, domain logic, and the pytest suite. |
| `frontend/` | Vanilla HTML and JavaScript dashboard, served by the backend. |
| `datasets/` | Synthetic datasets and the generator. |
| `.github/workflows/` | Continuous integration. |

## Documentation

| Document | Purpose |
| --- | --- |
| [Architecture.md](Architecture.md) | System architecture, trust model, protocol, data model, and smart contracts. |
| [PRD.md](PRD.md) | Product requirements: enumerated functional and non-functional requirements with acceptance criteria. |
| [MVP.md](MVP.md) | The free, deployable MVP and the investor demo script. |
| [Phases.md](Phases.md) | The phase-by-phase build plan and feature distribution. |
| [Features.md](Features.md) | Full feature and building-block inventory. |
| [DEVELOPMENT.md](DEVELOPMENT.md) | How to build and run each part. |
| [KNOWN_GAPS.md](KNOWN_GAPS.md) | What tier A0 intentionally defers, stated plainly. |

## Status

- Phase 0 (foundation and CI): done.
- Phase A (the tier-A0 MVP): done, reviewed, and merged. Continuous integration is green across contracts, backend, and the chain-integration job.
- Phases B, C, and D (real sensors and printers, a multi-organization consortium, and the physical-ratification stack): planned and specified in [Phases.md](Phases.md). They require hardware and infrastructure and are the next build steps.

## Honest scope

This platform raises the cost and the detection probability of cheating by orders of magnitude. It does not make cheating cryptographically impossible: the first-mile physical measurement and the identity of the delivered part are irreducible trust roots. The A0 build uses simulated printers and sensors, its guarantee is tamper-evidence plus anti-false-completion in simulation, and every verdict shown to a user is tier-tagged so nothing overclaims. See [KNOWN_GAPS.md](KNOWN_GAPS.md) for the full, honest list.

## License

Copyright (c) 2026 Nakul Sinha. All rights reserved. Licensing terms to be finalized by the owner.
