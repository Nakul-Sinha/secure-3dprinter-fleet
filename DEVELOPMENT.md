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

## Ledger abstraction

The backend talks to a ledger through an adapter interface. Two adapters exist:
a local signed transparency log (default, no chain required, used by the test
suite) and a chain adapter that binds to the deployed contracts through web3.
This mirrors the tiered design in [Architecture.md](Architecture.md): the same
logic runs on-chain, where it is consensus enforced, or on the log, where it is
evidenced.
