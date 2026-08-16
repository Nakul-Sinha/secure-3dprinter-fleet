// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;

/// @title PlatformInfo
/// @notice Minimal on-chain marker used to verify the contract toolchain in Phase 0.
///         Replaced in function by the registries in Phase A, kept as a deployment probe.
contract PlatformInfo {
    string public constant platform = "Secure 3D-Printer Fleet";
    string public version;
    address public immutable deployer;

    event Deployed(address indexed deployer, string version);

    constructor(string memory _version) {
        version = _version;
        deployer = msg.sender;
        emit Deployed(msg.sender, _version);
    }

    /// @notice Liveness probe.
    function ping() external pure returns (string memory) {
        return "ok";
    }
}
