# Development

This repository is a monorepo. It is built phase by phase, following [Phases.md](Phases.md).

## Layout

| Path | Contents |
| --- | --- |
| `contracts/` | Solidity smart contracts and Hardhat tests. |
| `backend/` | FastAPI application, domain logic, and pytest suite. |
| `frontend/` | Vanilla HTML and JavaScript dashboard, served by the backend. |
| `datasets/` | Generated synthetic datasets (output of the generator). |
| `.github/workflows/` | Continuous integration. |

## Prerequisites

- Node.js 20 or newer, with npm.
- Python 3.12 or newer.

## Contracts

```
cd contracts
npm install
npx hardhat compile
npx hardhat test
```

Run a local chain and deploy:

```
npx hardhat node          # terminal 1
npm run deploy:local      # terminal 2
```

## Backend

```
cd backend
pip install -r requirements.txt
pytest
```

Run the API and dashboard locally:

```
uvicorn app.main:app --reload
```

The dashboard is served at the root path. The API health probe is at `/health`.

## Continuous integration

Every push to `main` and every pull request runs two jobs: the Hardhat contract
tests and the backend pytest suite. See `.github/workflows/ci.yml`.

## Ledger and chain path

The generic audit stream is always a local signed transparency log
(`app/ledger.py`): a hash-chained, HMAC-signed, append-only event stream that
provides the tier-A0 tamper evidence and needs no chain. It is the default and
is what the unit suite exercises.

The real on-chain path lives in `app/chain.py` (`ChainBridge`, web3). With
`APP_LEDGER=chain` and a reachable node, it mirrors the domain lifecycle onto
the deployed Solidity registries and enforces roles through `AccessControlHub`.
This path is proven end to end by the `integration` CI job, which starts a
Hardhat node, deploys the contracts, and runs `tests/test_chain_integration.py`.

This mirrors the tiered design in [Architecture.md](Architecture.md): the same
logic runs on-chain, where it is consensus enforced, or on the log, where it is
evidenced. See [KNOWN_GAPS.md](KNOWN_GAPS.md) for what A0 intentionally defers.
