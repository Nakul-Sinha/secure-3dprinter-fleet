// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;

/// @title SettlementEscrow
/// @notice Holds payment and a provider bond for a print job, and releases them
///         only against a physical verification verdict.
///
/// The economics follow rules that came out of adversarial review, because the
/// obvious design is exploitable in both directions:
///
/// 1. Only a VerifiedPhysical verdict releases payment. A telemetry-only
///    verdict is evidence the protocol ran, not evidence the right part exists,
///    so it routes to dispute instead of moving money.
/// 2. Both sides commit to BOTH numbers before the deal activates. Without that
///    a one-wei counterparty can activate a deal and capture the other side's
///    stake on a failure verdict.
/// 3. A deal is keyed by (jobId, buyer, provider), so a stranger cannot occupy
///    or brick another pair's slot, and an abandoned slot is deleted rather than
///    left in a terminal state that blocks reuse.
/// 4. A missing verdict holds funds for arbitration and never auto-refunds, and
///    a late but correct verdict can still settle while arbitration is open.
/// 5. Every terminal state has a defined disposition and both liveness escapes
///    are permissionless, so funds can never stick.
///
/// Honest limit: if arbitration itself expires the deal unwinds neutrally and
/// each side takes back its own stake. When a part was genuinely delivered, that
/// outcome favours the buyer. No on-chain rule can know whether atoms changed
/// hands, so the correct claim is that funds never stick indefinitely, not that
/// stalling can never pay. Keeping arbitration live is a governance duty.
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
        VerifiedPhysical,     // A3: physical ratification passed, pay the provider
        FailedHighConfidence, // clear fraud, slash the bond
        FailedLowConfidence,  // borderline, dispute rather than slash
        VerifiedTelemetryOnly,// protocol ran, part not physically ratified
        Unavailable           // no verdict could be produced, hold for arbitration
    }

    struct Deal {
        address buyer;
        address provider;
        uint256 amount;
        uint256 bond;
        uint256 requiredAmount;
        uint256 requiredBond;
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
    /// @notice Minimum bond as a fraction of payment, in basis points. A bond
    ///         that is trivially small makes slashing meaningless.
    uint16 public immutable minBondBps;

    uint64 public constant MIN_VERDICT_WINDOW = 1 hours;
    uint64 public constant MIN_ARBITRATION_WINDOW = 1 days;

    mapping(bytes32 => Deal) public deals;
    mapping(address => uint256) public claimable;

    event DealOpened(bytes32 indexed key, bytes32 indexed jobId, address indexed buyer, address provider, uint256 amount);
    event BondPosted(bytes32 indexed key, bytes32 indexed jobId, address indexed provider, uint256 bond);
    event DealFunded(bytes32 indexed key, uint64 verdictDeadline);
    event VerdictReported(bytes32 indexed key, Verdict verdict);
    event ArbitrationExtended(bytes32 indexed key, uint64 newDeadline);
    event Settled(bytes32 indexed key, State state, uint256 toProvider, uint256 toBuyer, uint256 slashed);
    event Claimed(address indexed who, uint256 amount);

    error NotAuthorized();
    error BadState(State current);
    error DeadlineNotReached();
    error DeadlinePassed();
    error NothingToClaim();
    error ZeroValue();
    error StakeMismatch(uint256 expected, uint256 provided);
    error BondTooSmall(uint256 bond, uint256 minimum);
    error BadCounterparty();

    constructor(
        address _verifier,
        address _arbiter,
        uint64 _verdictWindow,
        uint64 _arbitrationWindow,
        uint16 _minBondBps
    ) {
        require(_verifier != address(0) && _arbiter != address(0), "zero address");
        require(_verifier != _arbiter, "verifier must not be the arbiter");
        require(_verdictWindow >= MIN_VERDICT_WINDOW, "verdict window too short");
        require(_arbitrationWindow >= MIN_ARBITRATION_WINDOW, "arbitration window too short");
        verifier = _verifier;
        arbiter = _arbiter;
        verdictWindow = _verdictWindow;
        arbitrationWindow = _arbitrationWindow;
        minBondBps = _minBondBps;
    }

    /// @notice Deals are namespaced by both parties, so a stranger cannot
    ///         occupy the slot belonging to a real buyer and provider.
    function dealKey(bytes32 jobId, address buyer, address provider) public pure returns (bytes32) {
        return keccak256(abi.encode(jobId, buyer, provider));
    }

    // ---- funding ----

    /// @notice Buyer escrows payment and states the bond the provider must post.
    function openDeal(bytes32 jobId, address provider, uint256 requiredBond)
        external payable returns (bytes32 key)
    {
        if (msg.value == 0) revert ZeroValue();
        if (provider == address(0) || provider == msg.sender) revert BadCounterparty();
        _requireBondFloor(requiredBond, msg.value);

        key = dealKey(jobId, msg.sender, provider);
        Deal storage d = deals[key];
        if (d.state == State.None) {
            deals[key] = Deal({
                buyer: msg.sender, provider: provider, amount: msg.value, bond: 0,
                requiredAmount: msg.value, requiredBond: requiredBond,
                fundedAt: 0, verdictDeadline: 0, arbitrationDeadline: 0,
                state: State.AwaitingBond, verdict: Verdict.None
            });
            emit DealOpened(key, jobId, msg.sender, provider, msg.value);
        } else if (d.state == State.AwaitingPayment) {
            // The provider bonded first and named the price; match it exactly.
            if (msg.value != d.requiredAmount) revert StakeMismatch(d.requiredAmount, msg.value);
            if (requiredBond != d.requiredBond) revert StakeMismatch(d.requiredBond, requiredBond);
            d.amount = msg.value;
            emit DealOpened(key, jobId, msg.sender, provider, msg.value);
            _activate(key, d);
        } else {
            revert BadState(d.state);
        }
    }

    /// @notice Provider posts the bond and states the payment the buyer must escrow.
    /// @dev The bond locks when the deal activates, not when a job record is
    ///      created. Because the slot is namespaced by both parties, a stranger
    ///      cannot freeze a provider's capital by squatting the job id.
    function postBond(bytes32 jobId, address buyer, uint256 requiredAmount)
        external payable returns (bytes32 key)
    {
        if (msg.value == 0) revert ZeroValue();
        if (buyer == address(0) || buyer == msg.sender) revert BadCounterparty();
        _requireBondFloor(msg.value, requiredAmount);

        key = dealKey(jobId, buyer, msg.sender);
        Deal storage d = deals[key];
        if (d.state == State.None) {
            deals[key] = Deal({
                buyer: buyer, provider: msg.sender, amount: 0, bond: msg.value,
                requiredAmount: requiredAmount, requiredBond: msg.value,
                fundedAt: 0, verdictDeadline: 0, arbitrationDeadline: 0,
                state: State.AwaitingPayment, verdict: Verdict.None
            });
            emit BondPosted(key, jobId, msg.sender, msg.value);
        } else if (d.state == State.AwaitingBond) {
            if (msg.value != d.requiredBond) revert StakeMismatch(d.requiredBond, msg.value);
            if (requiredAmount != d.requiredAmount) revert StakeMismatch(d.requiredAmount, requiredAmount);
            d.bond = msg.value;
            emit BondPosted(key, jobId, msg.sender, msg.value);
            _activate(key, d);
        } else {
            revert BadState(d.state);
        }
    }

    function _requireBondFloor(uint256 bond, uint256 amount) internal view {
        uint256 minimum = (amount * minBondBps) / 10_000;
        if (bond < minimum) revert BondTooSmall(bond, minimum);
    }

    function _activate(bytes32 key, Deal storage d) internal {
        d.state = State.Funded;
        d.fundedAt = uint64(block.timestamp);
        d.verdictDeadline = uint64(block.timestamp) + verdictWindow;
        emit DealFunded(key, d.verdictDeadline);
    }

    /// @notice Withdraw before the deal is active. The record is deleted rather
    ///         than parked in a terminal state, so the same parties can open the
    ///         job again instead of finding the slot permanently unusable.
    function withdrawUnmatched(bytes32 key) external {
        Deal storage d = deals[key];
        if (d.state == State.AwaitingBond) {
            if (msg.sender != d.buyer) revert NotAuthorized();
            uint256 amt = d.amount;
            address buyer = d.buyer;
            delete deals[key];
            _credit(buyer, amt);
            emit Settled(key, State.None, 0, amt, 0);
        } else if (d.state == State.AwaitingPayment) {
            if (msg.sender != d.provider) revert NotAuthorized();
            uint256 bond = d.bond;
            address provider = d.provider;
            delete deals[key];
            _credit(provider, bond);
            emit Settled(key, State.None, bond, 0, 0);
        } else {
            revert BadState(d.state);
        }
    }

    // ---- verdicts ----

    function reportVerdict(bytes32 key, Verdict v) external {
        if (msg.sender != verifier) revert NotAuthorized();
        if (v == Verdict.None) revert BadState(State.None);
        Deal storage d = deals[key];

        // A late verdict still counts while arbitration is open. Without this a
        // clean CT result arriving after the window could never be recorded, and
        // an honest provider would lose the deal to a race.
        if (d.state == State.Disputed) {
            if (block.timestamp >= d.arbitrationDeadline) revert DeadlinePassed();
            d.verdict = v;
            emit VerdictReported(key, v);
            if (v == Verdict.VerifiedPhysical) _release(key, d);
            return;
        }
        if (d.state != State.Funded) revert BadState(d.state);

        d.verdict = v;
        emit VerdictReported(key, v);
        if (v == Verdict.VerifiedPhysical) {
            _release(key, d);
        } else if (v == Verdict.FailedHighConfidence) {
            uint256 amount = d.amount;
            uint256 bond = d.bond;
            d.amount = 0;
            d.bond = 0;
            d.state = State.Refunded;
            _credit(d.buyer, amount + bond); // refund plus the slashed bond
            emit Settled(key, State.Refunded, 0, amount + bond, bond);
        } else {
            // Low confidence, telemetry-only, or unavailable: hold everything
            // for arbitration. Never auto-refund, or stalling becomes profitable.
            _dispute(key, d);
        }
    }

    function _release(bytes32 key, Deal storage d) internal {
        uint256 amount = d.amount;
        uint256 bond = d.bond;
        d.amount = 0;
        d.bond = 0;
        d.state = State.Released;
        _credit(d.provider, amount + bond); // payment plus the bond back
        emit Settled(key, State.Released, amount + bond, 0, 0);
    }

    function _dispute(bytes32 key, Deal storage d) internal {
        d.state = State.Disputed;
        d.arbitrationDeadline = uint64(block.timestamp) + arbitrationWindow;
        emit Settled(key, State.Disputed, 0, 0, 0);
    }

    /// @notice Anyone may move a stalled deal into arbitration once the verdict
    ///         window has passed. Funds stay held; nobody is paid or slashed.
    function escalateStalled(bytes32 key) external {
        Deal storage d = deals[key];
        if (d.state != State.Funded) revert BadState(d.state);
        if (block.timestamp < d.verdictDeadline) revert DeadlineNotReached();
        d.verdict = Verdict.Unavailable;
        emit VerdictReported(key, Verdict.Unavailable);
        _dispute(key, d);
    }

    // ---- arbitration ----

    /// @notice Give arbitration more time. Expiry should mean the arbiter truly
    ///         failed, not that a party ran out the clock.
    function extendArbitration(bytes32 key) external {
        if (msg.sender != arbiter) revert NotAuthorized();
        Deal storage d = deals[key];
        if (d.state != State.Disputed) revert BadState(d.state);
        d.arbitrationDeadline = uint64(block.timestamp) + arbitrationWindow;
        emit ArbitrationExtended(key, d.arbitrationDeadline);
    }

    /// @param payProvider true to pay the provider, false to refund the buyer.
    /// @param slashBond   true to award the bond to the counterparty.
    function arbitrate(bytes32 key, bool payProvider, bool slashBond) external {
        if (msg.sender != arbiter) revert NotAuthorized();
        Deal storage d = deals[key];
        if (d.state != State.Disputed) revert BadState(d.state);
        uint256 amount = d.amount;
        uint256 bond = d.bond;
        d.amount = 0;
        d.bond = 0;
        if (payProvider) {
            d.state = State.Released;
            uint256 toProvider = amount + (slashBond ? 0 : bond);
            uint256 toBuyer = slashBond ? bond : 0;
            _credit(d.provider, toProvider);
            _credit(d.buyer, toBuyer);
            emit Settled(key, State.Released, toProvider, toBuyer, slashBond ? bond : 0);
        } else {
            d.state = State.Refunded;
            uint256 toBuyer = amount + (slashBond ? bond : 0);
            uint256 toProvider = slashBond ? 0 : bond;
            _credit(d.buyer, toBuyer);
            _credit(d.provider, toProvider);
            emit Settled(key, State.Refunded, toProvider, toBuyer, slashBond ? bond : 0);
        }
    }

    /// @notice Neutral unwind once arbitration itself has expired: each side
    ///         gets its own stake back, so funds can never be stuck forever.
    function unwindExpired(bytes32 key) external {
        Deal storage d = deals[key];
        if (d.state != State.Disputed) revert BadState(d.state);
        if (block.timestamp < d.arbitrationDeadline) revert DeadlineNotReached();
        uint256 amount = d.amount;
        uint256 bond = d.bond;
        d.amount = 0;
        d.bond = 0;
        d.state = State.Unwound;
        _credit(d.buyer, amount);
        _credit(d.provider, bond);
        emit Settled(key, State.Unwound, bond, amount, 0);
    }

    // ---- pull payments ----

    function _credit(address who, uint256 amount) internal {
        if (amount > 0) claimable[who] += amount;
    }

    function claim() external {
        _payout(msg.sender, payable(msg.sender));
    }

    /// @notice Escape hatch for a party that cannot receive ETH at its own
    ///         address, so a credit can never be permanently stranded.
    function claimTo(address payable to) external {
        require(to != address(0), "zero address");
        _payout(msg.sender, to);
    }

    function _payout(address owner, address payable to) internal {
        uint256 amount = claimable[owner];
        if (amount == 0) revert NothingToClaim();
        claimable[owner] = 0; // state before transfer: no re-entrancy
        (bool ok, ) = to.call{value: amount}("");
        require(ok, "transfer failed");
        emit Claimed(owner, amount);
    }

    function stateOf(bytes32 key) external view returns (State) {
        return deals[key].state;
    }
}
