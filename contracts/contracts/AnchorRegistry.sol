// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;

import "./AccessControlHub.sol";

/// @title AnchorRegistry
/// @notice Anchors signed audit-log checkpoints on-chain. Anchoring puts the
///         commitment somewhere the server operator does not control, which is
///         what turns a locally consistent log into externally checkable
///         evidence and makes tail truncation detectable by a third party.
contract AnchorRegistry {
    AccessControlHub public immutable acl;

    struct Anchor {
        bytes32 digest;
        uint256 blockNumber;
        uint256 timestamp;
        address submitter;
    }

    Anchor[] public anchors;
    mapping(bytes32 => uint256) public indexOfDigest; // digest => index + 1

    event Anchored(uint256 indexed index, bytes32 indexed digest, address indexed submitter, uint256 timestamp);

    error AlreadyAnchored(bytes32 digest);

    constructor(address _acl) {
        acl = AccessControlHub(_acl);
    }

    /// @notice Anchor a checkpoint digest. Operators submit; anyone can verify.
    function anchor(bytes32 digest) external returns (uint256 index) {
        acl.requireRole(msg.sender, AccessControlHub.Role.Operator);
        if (indexOfDigest[digest] != 0) revert AlreadyAnchored(digest);
        anchors.push(Anchor({
            digest: digest,
            blockNumber: block.number,
            timestamp: block.timestamp,
            submitter: msg.sender
        }));
        index = anchors.length - 1;
        indexOfDigest[digest] = index + 1;
        emit Anchored(index, digest, msg.sender, block.timestamp);
    }

    function isAnchored(bytes32 digest) external view returns (bool) {
        return indexOfDigest[digest] != 0;
    }

    function anchorCount() external view returns (uint256) {
        return anchors.length;
    }

    /// @notice Timestamp recorded by the chain for a digest, 0 if not anchored.
    function anchoredAt(bytes32 digest) external view returns (uint256) {
        uint256 idx = indexOfDigest[digest];
        return idx == 0 ? 0 : anchors[idx - 1].timestamp;
    }
}
