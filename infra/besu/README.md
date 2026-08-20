# Besu QBFT consortium

Infrastructure for the tier-A1 deployment: the same Solidity contracts, moved
from a single development chain onto a permissioned network whose validators are
operated by different organizations.

## Why four validators

QBFT tolerates `f` faulty validators with `3f+1` nodes. Four is therefore the
smallest set that survives one bad or offline validator. Three tolerate none,
and two are strictly worse than one, because either party can halt the network.

This is the arithmetic behind the honesty gate in the design: a "consortium" of
two parties provides no Byzantine fault tolerance, so it does not earn the
tamper-resistant claim.

## Bootstrap

Generate validator keys and the genesis file:

```
mkdir -p nodes
cat > qbft-config.json <<'JSON'
{
  "genesis": {
    "config": {
      "chainId": 1337,
      "berlinBlock": 0,
      "qbft": { "blockperiodseconds": 2, "epochlength": 30000, "requesttimeoutseconds": 4 }
    },
    "nonce": "0x0",
    "gasLimit": "0x1fffffffffffff",
    "difficulty": "0x1",
    "alloc": {}
  },
  "blockchain": { "nodes": { "generate": true, "count": 4 } }
}
JSON

docker run --rm -v "$PWD":/work -w /work hyperledger/besu:24.12.2 \
  operator generate-blockchain-config \
  --config-file=qbft-config.json --to=networkFiles --private-key-file-name=key

cp networkFiles/genesis.json .
i=1; for d in networkFiles/keys/*/; do mkdir -p "nodes/validator$i"; cp "$d"key "nodes/validator$i/"; i=$((i+1)); done
```

Start the network and point the backend at it:

```
docker compose up -d
cd ../../contracts && npx hardhat run scripts/deploy.js --network besu
cd ../backend && APP_LEDGER=chain APP_CHAIN_RPC=http://localhost:8545 uvicorn app.main:app
```

## Distributing the validators

The compose file runs all four locally so the topology can be exercised. A real
A1 deployment moves each service to a different organization: the fleet owner,
a client or design owner, the print farm, and a neutral auditor or insurer. Until
that is true, the deployment is a single administrative domain and the honest
claim remains tamper-evident.

Governance for validator membership and contract upgrades is defined in
[GOVERNANCE.md](../../GOVERNANCE.md).
