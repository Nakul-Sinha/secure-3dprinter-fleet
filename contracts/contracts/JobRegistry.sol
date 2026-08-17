// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;

import "./AccessControlHub.sol";

/// @title JobRegistry
/// @notice On-chain job lifecycle and the canonical, append-only event log.
///         A Client registers a job (anchoring the file hash and off-chain CID),
///         an Operator schedules, starts, and reports the verdict. Transitions
///         are guarded, so the event stream is a tamper-evident audit trail.
contract JobRegistry {
    AccessControlHub public immutable acl;

    enum Status {
        None,
        Registered,
        Scheduled,
        Printing,
        Verified,
        Failed
    }

    struct Job {
        address client;
        bytes32 printerId;
        bytes32 fileHash;
        string cid;
        Status status;
        uint256 createdAt;
    }

    mapping(bytes32 => Job) public jobs;

    event JobRegistered(bytes32 indexed jobId, address indexed client, string cid, bytes32 fileHash);
    event JobScheduled(bytes32 indexed jobId, bytes32 indexed printerId);
    event JobStarted(bytes32 indexed jobId);
    event JobVerified(bytes32 indexed jobId, bool ok);

    error BadTransition(bytes32 jobId, Status from, Status to);
    error UnknownJob(bytes32 jobId);

    constructor(address _acl) {
        acl = AccessControlHub(_acl);
    }

    function registerJob(bytes32 jobId, string calldata cid, bytes32 fileHash) external {
        acl.requireRole(msg.sender, AccessControlHub.Role.Client);
        if (jobs[jobId].status != Status.None) revert BadTransition(jobId, jobs[jobId].status, Status.Registered);
        jobs[jobId] = Job({
            client: msg.sender,
            printerId: bytes32(0),
            fileHash: fileHash,
            cid: cid,
            status: Status.Registered,
            createdAt: block.timestamp
        });
        emit JobRegistered(jobId, msg.sender, cid, fileHash);
    }

    function scheduleJob(bytes32 jobId, bytes32 printerId) external {
        acl.requireRole(msg.sender, AccessControlHub.Role.Operator);
        _requireStatus(jobId, Status.Registered);
        jobs[jobId].printerId = printerId;
        jobs[jobId].status = Status.Scheduled;
        emit JobScheduled(jobId, printerId);
    }

    function startJob(bytes32 jobId) external {
        acl.requireRole(msg.sender, AccessControlHub.Role.Operator);
        _requireStatus(jobId, Status.Scheduled);
        jobs[jobId].status = Status.Printing;
        emit JobStarted(jobId);
    }

    function reportVerdict(bytes32 jobId, bool ok) external {
        acl.requireRole(msg.sender, AccessControlHub.Role.Operator);
        _requireStatus(jobId, Status.Printing);
        jobs[jobId].status = ok ? Status.Verified : Status.Failed;
        emit JobVerified(jobId, ok);
    }

    function statusOf(bytes32 jobId) external view returns (Status) {
        return jobs[jobId].status;
    }

    function _requireStatus(bytes32 jobId, Status expected) internal view {
        Status s = jobs[jobId].status;
        if (s == Status.None) revert UnknownJob(jobId);
        if (s != expected) revert BadTransition(jobId, s, expected);
    }
}
