// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;

/// @title AccessControlHub
/// @notice Central role registry. Roles are discrete (not a hierarchy), which
///         is what enforces separation of duties: the Admin that grants roles
///         cannot register or run jobs, and the Operator that runs jobs cannot
///         grant roles. The registries call requireRole to gate their functions.
contract AccessControlHub {
    enum Role {
        None,
        Client,
        Operator,
        Admin,
        Auditor
    }

    mapping(address => Role) public roleOf;

    event RoleGranted(address indexed who, Role role, address indexed by);

    error Unauthorized(address who, Role needed);

    constructor() {
        roleOf[msg.sender] = Role.Admin;
        emit RoleGranted(msg.sender, Role.Admin, msg.sender);
    }

    modifier onlyAdmin() {
        if (roleOf[msg.sender] != Role.Admin) revert Unauthorized(msg.sender, Role.Admin);
        _;
    }

    function grantRole(address who, Role role) external onlyAdmin {
        roleOf[who] = role;
        emit RoleGranted(who, role, msg.sender);
    }

    /// @notice Reverts unless `who` holds exactly `role`.
    function requireRole(address who, Role role) external view {
        if (roleOf[who] != role) revert Unauthorized(who, role);
    }

    function has(address who, Role role) external view returns (bool) {
        return roleOf[who] == role;
    }
}
