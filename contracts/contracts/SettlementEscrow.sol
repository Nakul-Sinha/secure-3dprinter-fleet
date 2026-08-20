// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;

/// @title SettlementEscrow
/// @notice Holds payment and a provider bond for a print job, and releases them
///         only against a physical verification verdict.
///
/// The economics follow four rules that came out of adversarial review, because
/// the obvious design is exploitable in both directions:
///
/// 1. Payment releases only on a verdict of VerifiedPhysical (tier A3). A
///    telemetry-only verdict is evidence the protocol ran, not evidence the
///    right part exists, so it never moves money.
/// 2. A failure to reach a verdict is not a failure of the job. "Unavailable"
///    holds the funds for arbitration and never auto-refunds, otherwise a buyer
///    who can stall the verifier gets the part and their money back.
/// 3. A low-confidence or contested failure goes to dispute rather than
///    slashing, so an honest provider is not punished by a borderline reading.
/// 4. Every terminal state has a defined disposition, and no state is cheaper
///    for a misbehaving party than an honest failure. Arbitration is bounded:
///    once its deadline passes anyone may unwind the deal neutrally, so funds
///    can never stick indefinitely.
///
/// Payments are pull-based and state is written before any transfer, so a
/// malicious recipient cannot re-enter.
contract SettlementEscrow {
    enum State {
        None,
        AwaitingBond,     // buyer funded, provider has not bonded
        AwaitingPayment,  // provider bonded, buyer has not funded
        Funded,           // both present, work may proceed
        Released,         // provider paid
        Refunded,         // buyer refunded
        Disputed,         // awaiting arbitration
        Unwound           // neutral unwind after arbitration expired
    }

    enum Verdict {
        None,
        VerifiedPhysical,   // A3: physical ratification passed, pay the provider
        FailedHighConfidence, // clear fraud, slash the bond
        FailedLowConfidence,  // borderline, dispute rather than slash
        Unavailable           // no verdict could be produced, hold for arbitration
    }

    struct Deal {
        address buyer;
        address provider;
        uint256 amount;
        uint256 bond;
        uint64 fundedAt;
        uint64 verdictDeadline;
        uint64 arbitrationDeadline;
        State state;
        Verdict verdict;
    }

    address public immutable verifier; // reports verdicts; never the operator
    address public immutable arbiter;  // neutral governance, resolves disputes
    uint64 public immutable verdictWindow;
    uint64 public immutable arbitrationWindow;

    mapping(bytes32 => Deal) public deals;
    mapping(address => uint256) public claimable;

    event DealOpened(bytes32 indexed jobId, address indexed buyer, address indexed provider, uint256 amount);
    event BondPosted(bytes32 indexed jobId, address indexed provider, uint256 bond);
    event DealFunded(bytes32 indexed jobId, uint64 verdictDeadline);
    event VerdictReported(bytes32 indexed jobId, Verdict verdict);
    event Settled(bytes32 indexed jobId, State state, uint256 toProvider, uint256 toBuyer, uint256 slashed);
    event Claimed(address indexed who, uint256 amount);

    error NotAuthorized();
    error BadState(State current);
    error UnknownDeal();
    error DeadlineNotReached();
    error NothingToClaim();
    error ZeroValue();

    constructor(address _verifier, address _arbiter, uint64 _verdictWindow, uint64 _arbitrationWindow) {
        require(_verifier != address(0) && _arbiter != address(0), "zero address");
        require(_verifier != _arbiter, "verifier must not be the arbiter");
        verifier = _verifier;
        arbiter = _arbiter;
        verdictWindow = _verdictWindow;
        arbitrationWindow = _arbitrationWindow;
    }

    // ---- funding ----

    /// @notice Buyer escrows payment for a job.
    function openDeal(bytes32 jobId, address provider) external payable {
        if (msg.value == 0) revert ZeroValue();
        Deal storage d = deals[jobId];
        if (d.state == State.None) {
            deals[jobId] = Deal({
                buyer: msg.sender, provider: provider, amount: msg.value, bond: 0,
                fundedAt: 0, verdictDeadline: 0, arbitrationDeadline: 0,
                state: State.AwaitingBond, verdict: Verdict.None
            });
            emit DealOpened(jobId, msg.sender, provider, msg.value);
        } else if (d.state == State.AwaitingPayment) {
            require(d.provider == provider, "provider mismatch");
            d.buyer = msg.sender;
            d.amount = msg.value;
            emit DealOpened(jobId, msg.sender, provider, msg.value);
            _activate(jobId, d);
        } else {
            revert BadState(d.state);
        }
    }

    /// @notice Provider posts the bond that backs the job.
    /// @dev The bond locks here, at funding, not when a job record is created.
    ///      Locking earlier would let a buyer spam job records and freeze a
    ///      provider's capital without ever paying.
    function postBond(bytes32 jobId) external payable {
        if (msg.value == 0) revert ZeroValue();
        Deal storage d = deals[jobId];
        if (d.state == State.None) {
            deals[jobId] = Deal({
                buyer: address(0), provider: msg.sender, amount: 0, bond: msg.value,
                fundedAt: 0, verdictDeadline: 0, arbitrationDeadline: 0,
                state: State.AwaitingPayment, verdict: Verdict.None
            });
            emit BondPosted(jobId, msg.sender, msg.value);
        } else if (d.state == State.AwaitingBond) {
            require(d.provider == msg.sender, "not the named provider");
            d.bond = msg.value;
            emit BondPosted(jobId, msg.sender, msg.value);
            _activate(jobId, d);
        } else {
            revert BadState(d.state);
        }
    }

    function _activate(bytes32 jobId, Deal storage d) internal {
        d.state = State.Funded;
        d.fundedAt = uint64(block.timestamp);
        d.verdictDeadline = uint64(block.timestamp) + verdictWindow;
        emit DealFunded(jobId, d.verdictDeadline);
    }

    /// @notice Withdraw before the deal is active. Either side may back out
    ///         while the other has not committed, so no capital is trapped.
    function withdrawUnmatched(bytes32 jobId) external {
        Deal storage d = deals[jobId];
        if (d.state == State.AwaitingBond) {
            if (msg.sender != d.buyer) revert NotAuthorized();
            uint256 amt = d.amount;
            d.amount = 0;
            d.state = State.Refunded;
            _credit(d.buyer, amt);
            emit Settled(jobId, State.Refunded, 0, amt, 0);
        } else if (d.state == State.AwaitingPayment) {
            if (msg.sender != d.provider) revert NotAuthorized();
            uint256 bond = d.bond;
            d.bond = 0;
            d.state = State.Unwound;
            _credit(d.provider, bond);
            emit Settled(jobId, State.Unwound, bond, 0, 0);
        } else {
            revert BadState(d.state);
        }
    }

    // ---- verdicts ----

    function reportVerdict(bytes32 jobId, Verdict v) external {
        if (msg.sender != verifier) revert NotAuthorized();
        Deal storage d = deals[jobId];
        if (d.state != State.Funded) revert BadState(d.state);
        if (v == Verdict.None) revert BadState(d.state);
        d.verdict = v;
        emit VerdictReported(jobId, v);

        if (v == Verdict.VerifiedPhysical) {
            uint256 amount = d.amount;
            uint256 bond = d.bond;
            d.amount = 0;
            d.bond = 0;
            d.state = State.Released;
            _credit(d.provider, amount + bond); // payment plus the bond back
            emit Settled(jobId, State.Released, amount + bond, 0, 0);
        } else if (v == Verdict.FailedHighConfidence) {
            uint256 amount = d.amount;
            uint256 bond = d.bond;
            d.amount = 0;
            d.bond = 0;
            d.state = State.Refunded;
            _credit(d.buyer, amount + bond); // refund plus the slashed bond
            emit Settled(jobId, State.Refunded, 0, amount, bond);
        } else {
            // Low confidence or unavailable: hold everything for arbitration.
            // Never auto-refund, or stalling the verifier becomes profitable.
            d.state = State.Disputed;
            d.arbitrationDeadline = uint64(block.timestamp) + arbitrationWindow;
            emit Settled(jobId, State.Disputed, 0, 0, 0);
        }
    }

    /// @notice Anyone may move a stalled deal into arbitration once the verdict
    ///         window has passed. Funds stay held; nobody is paid or slashed.
    function escalateStalled(bytes32 jobId) external {
        Deal storage d = deals[jobId];
        if (d.state != State.Funded) revert BadState(d.state);
        if (block.timestamp < d.verdictDeadline) revert DeadlineNotReached();
        d.verdict = Verdict.Unavailable;
        d.state = State.Disputed;
        d.arbitrationDeadline = uint64(block.timestamp) + arbitrationWindow;
        emit VerdictReported(jobId, Verdict.Unavailable);
        emit Settled(jobId, State.Disputed, 0, 0, 0);
    }

    // ---- arbitration ----

    /// @param payProvider true to pay the provider, false to refund the buyer.
    /// @param slashBond   true to award the bond to the counterparty.
    function arbitrate(bytes32 jobId, bool payProvider, bool slashBond) external {
        if (msg.sender != arbiter) revert NotAuthorized();
        Deal storage d = deals[jobId];
        if (d.state != State.Disputed) revert BadState(d.state);
        uint256 amount = d.amount;
        uint256 bond = d.bond;
        d.amount = 0;
        d.bond = 0;
        if (payProvider) {
            d.state = State.Released;
            uint256 toProvider = amount + (slashBond ? 0 : bond);
            _credit(d.provider, toProvider);
            if (slashBond) _credit(d.buyer, bond);
            emit Settled(jobId, State.Released, toProvider, slashBond ? bond : 0, slashBond ? bond : 0);
        } else {
            d.state = State.Refunded;
            uint256 toBuyer = amount + (slashBond ? bond : 0);
            _credit(d.buyer, toBuyer);
            if (!slashBond) _credit(d.provider, bond);
            emit Settled(jobId, State.Refunded, slashBond ? 0 : bond, toBuyer, slashBond ? bond : 0);
        }
    }

    /// @notice Neutral unwind once arbitration itself has expired: each side
    ///         gets its own money back. No party profits from stalling, and
    ///         funds can never be stuck forever.
    function unwindExpired(bytes32 jobId) external {
        Deal storage d = deals[jobId];
        if (d.state != State.Disputed) revert BadState(d.state);
        if (block.timestamp < d.arbitrationDeadline) revert DeadlineNotReached();
        uint256 amount = d.amount;
        uint256 bond = d.bond;
        d.amount = 0;
        d.bond = 0;
        d.state = State.Unwound;
        _credit(d.buyer, amount);
        _credit(d.provider, bond);
        emit Settled(jobId, State.Unwound, bond, amount, 0);
    }

    // ---- pull payments ----

    function _credit(address who, uint256 amount) internal {
        if (amount > 0) claimable[who] += amount;
    }

    function claim() external {
        uint256 amount = claimable[msg.sender];
        if (amount == 0) revert NothingToClaim();
        claimable[msg.sender] = 0; // state before transfer: no re-entrancy
        (bool ok, ) = payable(msg.sender).call{value: amount}("");
        require(ok, "transfer failed");
        emit Claimed(msg.sender, amount);
    }

    function stateOf(bytes32 jobId) external view returns (State) {
        return deals[jobId].state;
    }
}
