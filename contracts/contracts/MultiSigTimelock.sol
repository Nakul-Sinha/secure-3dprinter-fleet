// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;

/// @title MultiSigTimelock
/// @notice Governance for the fleet: privileged actions need M of N signers and
///         then a mandatory delay before they can execute.
///
/// This exists because a single admin key is the most common way these systems
/// actually fail. The multisig means no one person can act alone; the delay
/// means an action is visible before it takes effect, so a compromised set of
/// signers can still be caught. A guardian can cancel a queued action but can
/// never execute one, which is deliberately an asymmetric power: stopping
/// something is safe, starting something is not.
contract MultiSigTimelock {
    struct Operation {
        address target;
        uint256 value;
        bytes data;
        uint64 readyAt;
        uint8 approvals;
        bool executed;
        bool cancelled;
    }

    mapping(address => bool) public isSigner;
    mapping(address => bool) public isGuardian;
    address[] public signers;
    uint8 public threshold;
    uint64 public delay;

    mapping(bytes32 => Operation) public operations;
    /// @dev Approvals are recorded per epoch. Cancelling bumps the epoch, so a
    ///      cancelled action can be proposed again from a clean slate instead of
    ///      being dead forever.
    mapping(bytes32 => uint256) public epoch;
    mapping(bytes32 => mapping(uint256 => mapping(address => bool))) public approvedAt;

    uint64 public constant MIN_DELAY = 24 hours;

    event Queued(bytes32 indexed id, address indexed target, uint256 value, uint64 readyAt);
    event Approved(bytes32 indexed id, address indexed signer, uint8 approvals);
    event Executed(bytes32 indexed id);
    event Cancelled(bytes32 indexed id, address indexed by);
    event SignerAdded(address indexed who);
    event SignerRemoved(address indexed who);
    event ThresholdChanged(uint8 threshold);
    event DelayChanged(uint64 delay);
    event GuardianChanged(address indexed who, bool enabled);

    error NotSigner();
    error NotGuardian();
    error AlreadyApproved();
    error UnknownOperation();
    error NotReady();
    error NotEnoughApprovals(uint8 have, uint8 need);
    error AlreadyFinalized();
    error CallFailed();

    constructor(address[] memory _signers, uint8 _threshold, uint64 _delay, address[] memory _guardians) {
        require(_signers.length > 0, "no signers");
        require(_threshold > 0 && _threshold <= _signers.length, "bad threshold");
        require(_delay >= MIN_DELAY, "delay too short");
        for (uint256 i = 0; i < _signers.length; i++) {
            require(_signers[i] != address(0), "zero signer");
            require(!isSigner[_signers[i]], "duplicate signer");
            isSigner[_signers[i]] = true;
            signers.push(_signers[i]);
        }
        for (uint256 i = 0; i < _guardians.length; i++) {
            isGuardian[_guardians[i]] = true;
        }
        threshold = _threshold;
        delay = _delay;
    }

    modifier onlySigner() {
        if (!isSigner[msg.sender]) revert NotSigner();
        _;
    }

    function operationId(address target, uint256 value, bytes calldata data, bytes32 salt)
        public pure returns (bytes32)
    {
        return keccak256(abi.encode(target, value, data, salt));
    }

    /// @notice Queue an action and cast the first approval.
    function queue(address target, uint256 value, bytes calldata data, bytes32 salt)
        external onlySigner returns (bytes32 id)
    {
        id = operationId(target, value, data, salt);
        Operation storage op = operations[id];
        require(op.readyAt == 0, "already queued");
        op.target = target;
        op.value = value;
        op.data = data;
        op.readyAt = uint64(block.timestamp) + delay;
        op.approvals = 1;
        op.cancelled = false;
        approvedAt[id][epoch[id]][msg.sender] = true;
        emit Queued(id, target, value, op.readyAt);
        emit Approved(id, msg.sender, 1);
    }

    function approve(bytes32 id) external onlySigner {
        Operation storage op = operations[id];
        if (op.readyAt == 0) revert UnknownOperation();
        if (op.executed || op.cancelled) revert AlreadyFinalized();
        if (approvedAt[id][epoch[id]][msg.sender]) revert AlreadyApproved();
        approvedAt[id][epoch[id]][msg.sender] = true;
        op.approvals += 1;
        emit Approved(id, msg.sender, op.approvals);
    }

    function approved(bytes32 id, address signer) external view returns (bool) {
        return approvedAt[id][epoch[id]][signer];
    }

    function execute(bytes32 id) external onlySigner {
        Operation storage op = operations[id];
        if (op.readyAt == 0) revert UnknownOperation();
        if (op.executed || op.cancelled) revert AlreadyFinalized();
        if (op.approvals < threshold) revert NotEnoughApprovals(op.approvals, threshold);
        if (block.timestamp < op.readyAt) revert NotReady();
        op.executed = true;
        (bool ok, ) = op.target.call{value: op.value}(op.data);
        if (!ok) revert CallFailed();
        emit Executed(id);
    }

    /// @notice A guardian can stop a queued action but can never start one.
    /// @dev Restricted to guardians. Letting any signer cancel would turn an
    ///      M-of-N multisig into a 1-of-N veto, because one holdout could kill
    ///      every action the majority proposed.
    function cancel(bytes32 id) external {
        if (!isGuardian[msg.sender]) revert NotGuardian();
        Operation storage op = operations[id];
        if (op.readyAt == 0) revert UnknownOperation();
        if (op.executed || op.cancelled) revert AlreadyFinalized();
        // Bump the epoch and clear the slot so the same action can be proposed
        // again from scratch rather than being permanently unusable.
        epoch[id] += 1;
        delete operations[id];
        emit Cancelled(id, msg.sender);
    }

    // ---- self-administration ----
    // These are callable only by the timelock itself, so changing the signer set
    // requires the same M-of-N approval and delay as any other action. Without
    // them a lost or compromised key could never be rotated out.

    modifier onlySelf() {
        if (msg.sender != address(this)) revert NotSigner();
        _;
    }

    function addSigner(address who) external onlySelf {
        require(who != address(0) && !isSigner[who], "bad signer");
        isSigner[who] = true;
        signers.push(who);
        emit SignerAdded(who);
    }

    function removeSigner(address who) external onlySelf {
        require(isSigner[who], "not a signer");
        require(signers.length - 1 >= threshold, "would drop below threshold");
        isSigner[who] = false;
        for (uint256 i = 0; i < signers.length; i++) {
            if (signers[i] == who) {
                signers[i] = signers[signers.length - 1];
                signers.pop();
                break;
            }
        }
        emit SignerRemoved(who);
    }

    function setThreshold(uint8 newThreshold) external onlySelf {
        require(newThreshold > 0 && newThreshold <= signers.length, "bad threshold");
        threshold = newThreshold;
        emit ThresholdChanged(newThreshold);
    }

    function setDelay(uint64 newDelay) external onlySelf {
        require(newDelay >= MIN_DELAY, "delay too short");
        delay = newDelay;
        emit DelayChanged(newDelay);
    }

    function setGuardian(address who, bool enabled) external onlySelf {
        isGuardian[who] = enabled;
        emit GuardianChanged(who, enabled);
    }

    function signerCount() external view returns (uint256) {
        return signers.length;
    }

    receive() external payable {}
}
