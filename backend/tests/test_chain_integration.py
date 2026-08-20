"""On-chain integration test (tier A0 real-blockchain path).

Skips unless web3 is installed, a local deployment file exists, and the node is
reachable. CI runs a Hardhat node + deploy, then runs this test, so the chain
path is proven end to end. Locally:

    cd contracts && npx hardhat node        # terminal 1
    cd contracts && npm run deploy:local    # terminal 2
    cd backend && APP_LEDGER=chain pytest tests/test_chain_integration.py
"""
import os

import pytest

pytest.importorskip("web3")

from app.chain import _DEPLOYMENTS, ChainBridge  # noqa: E402

pytestmark = pytest.mark.skipif(
    not os.path.exists(_DEPLOYMENTS),
    reason="no local deployment; start a Hardhat node and deploy first",
)


@pytest.fixture(scope="module")
def bridge():
    try:
        return ChainBridge()
    except Exception as e:  # node not reachable
        pytest.skip(f"chain not reachable: {e}")


def test_onchain_lifecycle(bridge):
    admin, operator, client = bridge.accounts[0], bridge.accounts[1], bridge.accounts[2]
    bridge.grant_role(operator, "Operator", admin)
    bridge.grant_role(client, "Client", admin)
    assert bridge.role_of(client) == 1  # Client

    bridge.add_printer("printer-int-1", "Prusa-MK4", "fine", admin)
    assert bridge.printer_available("printer-int-1") is True

    job = "job-int-1"
    bridge.register_job(job, "cid1-int", "aa" * 32, client)
    assert bridge.job_status(job) == 1  # Registered
    bridge.schedule_job(job, "printer-int-1", operator)
    bridge.start_job(job, operator)
    bridge.report_verdict(job, True, operator)
    assert bridge.job_status(job) == 4  # Verified


def test_onchain_checkpoint_anchoring(bridge):
    """Anchor a REAL checkpoint produced by the audit pipeline, not an arbitrary
    constant, and then confirm the cross-check finds it on-chain. This is what
    puts the commitment outside the server operator's control."""
    from app import anchor as anchor_mod
    from app.db import reset_db_for_tests, session_scope
    from app.ledger import get_ledger, reset_ledger_for_tests
    from app.users import bootstrap_admin

    reset_db_for_tests("sqlite:///:memory:")
    reset_ledger_for_tests()
    session = session_scope()
    bootstrap_admin(session)
    for i in range(3):
        get_ledger().append(session, "op", "Event", f"t{i}", {"i": i})
    session.commit()

    cp = anchor_mod.create_checkpoint(session, anchor=True)
    session.commit()
    assert cp is not None
    assert cp.anchor_tx, f"anchoring failed: {cp.anchor_error}"

    body = anchor_mod.checkpoint_body(cp.seq, cp.count, cp.head_hash, cp.tree_root)
    digest = anchor_mod.body_digest(body)
    assert bridge.is_anchored(digest) is True

    cross = anchor_mod.verify_against_chain(session)
    assert cross["checked"] is True and cross["ok"] is True
    session.close()


def test_onchain_rbac_rejects_unauthorized(bridge):
    admin, operator = bridge.accounts[0], bridge.accounts[1]
    bridge.grant_role(operator, "Operator", admin)  # operator, not client
    with pytest.raises(Exception):
        bridge.register_job("job-int-x", "cid", "bb" * 32, operator)
