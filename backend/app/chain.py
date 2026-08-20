"""On-chain bridge to the deployed registries (optional, APP_LEDGER=chain).

The generic audit stream stays the signed transparency log (ledger.py). This
module mirrors the domain lifecycle (roles, jobs) onto the real Solidity
contracts and enforces roles on-chain via AccessControlHub. It is used by the
chain integration test and, when enabled, best-effort by the job service.

If web3 is not installed, the deployment file is missing, or the node is
unreachable, get_bridge() returns None and the app runs on the log alone.
"""
from __future__ import annotations

import json
import os

from .config import settings

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_CONTRACTS = os.path.join(_REPO, "contracts")
_DEPLOYMENTS = os.path.join(_CONTRACTS, "deployments.local.json")
_ARTIFACTS = os.path.join(_CONTRACTS, "artifacts", "contracts")

# Role enum (mirror of AccessControlHub.Role)
ROLE = {"None": 0, "Client": 1, "Operator": 2, "Admin": 3, "Auditor": 4}


def _abi(name: str) -> list:
    with open(os.path.join(_ARTIFACTS, f"{name}.sol", f"{name}.json"), encoding="utf-8") as f:
        return json.load(f)["abi"]


class ChainBridge:
    def __init__(self, rpc: str | None = None, deployments_path: str | None = None):
        from web3 import Web3  # lazy import

        self.w3 = Web3(Web3.HTTPProvider(rpc or settings.chain_rpc))
        if not self.w3.is_connected():
            raise ConnectionError("chain RPC not reachable")
        with open(deployments_path or _DEPLOYMENTS, encoding="utf-8") as f:
            dep = json.load(f)
        self.acl = self.w3.eth.contract(address=dep["AccessControlHub"], abi=_abi("AccessControlHub"))
        self.printers = self.w3.eth.contract(address=dep["PrinterRegistry"], abi=_abi("PrinterRegistry"))
        self.jobs = self.w3.eth.contract(address=dep["JobRegistry"], abi=_abi("JobRegistry"))
        self.anchors = (
            self.w3.eth.contract(address=dep["AnchorRegistry"], abi=_abi("AnchorRegistry"))
            if dep.get("AnchorRegistry") else None
        )
        self.accounts = self.w3.eth.accounts

    # ---- helpers ----
    def _b32(self, text: str) -> bytes:
        from web3 import Web3

        return Web3.keccak(text=text)

    def _tx(self, fn, sender: str):
        tx_hash = fn.transact({"from": sender})
        return self.w3.eth.wait_for_transaction_receipt(tx_hash)

    # ---- roles ----
    def grant_role(self, who: str, role: str, admin: str | None = None):
        return self._tx(self.acl.functions.grantRole(who, ROLE[role]), admin or self.accounts[0])

    def role_of(self, who: str) -> int:
        return self.acl.functions.roleOf(who).call()

    # ---- printers ----
    def add_printer(self, printer_id: str, model: str, tolerance: str, sender: str):
        return self._tx(self.printers.functions.addPrinter(self._b32(printer_id), model, tolerance), sender)

    def printer_available(self, printer_id: str) -> bool:
        return self.printers.functions.isAvailable(self._b32(printer_id)).call()

    # ---- jobs ----
    def register_job(self, job_id: str, cid: str, commitment_hex: str, sender: str):
        return self._tx(
            self.jobs.functions.registerJob(self._b32(job_id), cid, bytes.fromhex(commitment_hex)), sender
        )

    def schedule_job(self, job_id: str, printer_id: str, sender: str):
        return self._tx(self.jobs.functions.scheduleJob(self._b32(job_id), self._b32(printer_id)), sender)

    def start_job(self, job_id: str, sender: str):
        return self._tx(self.jobs.functions.startJob(self._b32(job_id)), sender)

    def report_verdict(self, job_id: str, ok: bool, sender: str):
        return self._tx(self.jobs.functions.reportVerdict(self._b32(job_id), ok), sender)

    def job_status(self, job_id: str) -> int:
        return self.jobs.functions.statusOf(self._b32(job_id)).call()

    # ---- checkpoint anchoring ----
    def operator_account(self) -> str:
        """An account holding the Operator role.

        Never grants Operator to the admin account: roles are discrete, so
        making the admin an Operator would strip its Admin rights and break
        every later role grant.
        """
        for a in self.accounts:
            if self.role_of(a) == ROLE["Operator"]:
                return a
        admin = self.accounts[0]
        if len(self.accounts) > 1:
            candidate = self.accounts[1]
            self.grant_role(candidate, "Operator", admin)
            return candidate
        raise RuntimeError("no account available to hold the Operator role")

    def anchor(self, digest_hex: str, sender: str | None = None) -> str | None:
        """Anchor an audit checkpoint digest. Returns the transaction hash."""
        if self.anchors is None:
            return None
        who = sender or self.operator_account()
        digest = bytes.fromhex(digest_hex[-64:])
        receipt = self._tx(self.anchors.functions.anchor(digest), who)
        return receipt["transactionHash"].hex()

    def is_anchored(self, digest_hex: str) -> bool:
        if self.anchors is None:
            return False
        return self.anchors.functions.isAnchored(bytes.fromhex(digest_hex[-64:])).call()


_bridge: ChainBridge | None = None
_tried = False


def get_bridge() -> ChainBridge | None:
    """Return a connected bridge in chain mode, else None (log-only)."""
    global _bridge, _tried
    if settings.ledger != "chain":
        return None
    if _bridge is not None:
        return _bridge
    if _tried:
        return None
    _tried = True
    try:
        if not os.path.exists(_DEPLOYMENTS):
            return None
        _bridge = ChainBridge()
        return _bridge
    except Exception:
        return None


def reset_bridge_for_tests() -> None:
    global _bridge, _tried
    _bridge = None
    _tried = False
