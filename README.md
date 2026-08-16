# Secure and Tamper-Evident Multi-3D-Printer Management System

A blockchain-based platform for securely managing a fleet of 3D printers. It gives design owners, fleet operators, and auditors a shared, tamper-evident record of every print job, protects design intellectual property, and can prove that a job physically ran without trusting the machine or its operator.

This repository is the design and build source for the project. It contains the full requirements, architecture, a free and deployable MVP plan for investor demos, a phased build plan that engineering agents can follow one step at a time, and a complete feature inventory.

## The problem

Distributed and outsourced manufacturing creates a trust gap. When a company sends a design file to a printer it does not fully control, four risks appear:

1. Intellectual property theft. The design file (CAD or G-code) can be intercepted or copied by whoever runs the printer.
2. Tampering. Print files and logs can be altered, and defects can be introduced into a part that still looks correct from the outside.
3. False completion. An operator or a faulty machine can claim a job was printed and demand payment without the work actually happening.
4. No shared audit trail. There is no single record that a client, an operator, and a regulator can all trust and none can secretly rewrite.

## The aim

Build one system that:

- Manages multiple printers securely: upload, authorize, schedule, dispatch, monitor, and audit.
- Stores print files and logs so that any change is cryptographically detectable.
- Enforces access control and job rules in smart contracts on a permissioned blockchain.
- Produces an immutable, queryable history with verifiable timestamps.
- Can be upgraded, without re-architecture, to prove that a job physically ran and that the correct part was produced.

## The direction: honest, tiered assurance

The guiding principle of this project is simple and strict: cryptography cannot vouch for physical reality it did not independently observe. Every guarantee is scoped to the trust configuration that actually earns it, and the system fails closed to the weaker honest claim rather than overclaiming.

The blockchain is present at every level. What changes across levels is the strength of the claim you are allowed to make.

| Tier | Honest claim | What it needs |
| --- | --- | --- |
| A0 (base) | Tamper-evident. Any edit or deletion is detectable. Timeline carries an EU rebuttable legal presumption of time. Not yet Byzantine-fault-tolerant. | The base product on a permissioned chain. Ships in weeks, software only. |
| A1 | Tamper-resistant across mutually distrusting parties. | Two or more independent organizations each run a validator (four or more for fault tolerance). |
| A2 | Quantified guarantee against gross false completion (a job that mostly did not run). | At least one genuinely independent witness sensor. |
| A3 | High assurance that the correct part was physically produced. Payment gates here. | Independent witness plus independent physical ratification (X-ray CT or PUF). One hundred percent CT for safety-critical parts. |

The core sentence to remember: the chain is the deliverable, Byzantine-fault-tolerant trust is a tiered claim, and physically verified correctness is the top tier and the only basis for gating payment on safety-critical parts.

## What makes this different

Provenance and licensing for additive manufacturing already exist commercially. The differentiator here is verifiable physical execution: a protocol that makes a fake "job complete" signal statistically very hard to forge, using an unpredictable, publicly re-derivable sampling schedule and independent sensors, without trusting the printer. The design is honest about the limit of that guarantee and pairs it with physical part ratification for the cases that require certainty.

## Repository structure

| Document | Purpose |
| --- | --- |
| [README.md](README.md) | This file. Project overview, aim, and direction. |
| [Architecture.md](Architecture.md) | System architecture, trust model, protocol, data model, and smart contracts. |
| [MVP.md](MVP.md) | A free to build, deployable MVP for investor demos, with a demo script and a zero-cost stack. |
| [Phases.md](Phases.md) | Detailed phase by phase build plan and feature distribution for engineering agents to build one step at a time. |
| [Features.md](Features.md) | Full feature and building-block inventory, tagged by module, tier, and phase. |
| [PRD.md](PRD.md) | Product Requirements Document. Enumerated functional and non-functional requirements with acceptance criteria and traceability. |

Suggested reading order: README, then MVP for the near-term goal, then Phases and Features to build, with Architecture and PRD as the reference specifications.

## Technology stack

- Smart contracts: Solidity.
- Chain: Hyperledger Besu (QBFT) for pilots and production. Hardhat or Anvil for local development and the MVP.
- Backend: Python (FastAPI) or Node. Web3 bindings for chain interaction.
- Storage: encrypted object store (MinIO or S3 compatible) with content addressing. Local storage for the MVP.
- Encryption: envelope encryption, AES-256-GCM data keys wrapped by a key management service.
- Randomness (A2 and above): drand threshold randomness beacon.
- Frontend: React or a light HTML and JavaScript dashboard.
- Printer integration: driver abstraction over Moonraker, OctoPrint, Duet, and others.

## MVP at a glance

The MVP is the A0 tier, built entirely with free and local tooling, deployable on a single laptop or a free tier host. It demonstrates the working management product and a simulated anti-false-completion check, and it establishes the credible path to the defensible verification moat. See [MVP.md](MVP.md) for the full plan and the investor demo script.

## Roadmap

- Phase A: the base management product on a permissioned chain (the MVP, tier A0).
- Phase B: low-cost trust wins, including a power meter signal and public anchoring with qualified timestamps.
- Phase C: multi-organization deployment, tier A1.
- Phase D: the verifiable-execution stack, tiers A2 and A3.

See [Phases.md](Phases.md) for detailed, buildable work.

## Honest scope and disclaimer

This system raises the cost and the detection probability of cheating by orders of magnitude. It does not make cheating cryptographically impossible. The first-mile physical measurement and the identity of the delivered part are irreducible trust roots. The design states these limits openly and never uses the words trustless or tamper-proof to describe what is in fact tamper-evident and probabilistic. Claims shown to a user always reflect the tier that the deployment actually earns.

## Status

Design complete and reviewed. The MVP (Phase A) is the next build step.

## License

Copyright (c) 2026 Nakul Sinha. All rights reserved. Licensing terms to be finalized by the owner.
