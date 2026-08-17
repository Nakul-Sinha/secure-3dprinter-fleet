// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;

import "./AccessControlHub.sol";

/// @title PrinterRegistry
/// @notice On-chain printer identities and availability. Admin adds printers,
///         Operators set availability. The scheduler reads availability.
contract PrinterRegistry {
    AccessControlHub public immutable acl;

    struct Printer {
        bool exists;
        bool available;
        string model;
        string tolerance;
    }

    mapping(bytes32 => Printer) public printers;

    event PrinterAdded(bytes32 indexed id, string model, string tolerance);
    event AvailabilitySet(bytes32 indexed id, bool available);

    error UnknownPrinter(bytes32 id);

    constructor(address _acl) {
        acl = AccessControlHub(_acl);
    }

    function addPrinter(bytes32 id, string calldata model, string calldata tolerance) external {
        acl.requireRole(msg.sender, AccessControlHub.Role.Admin);
        printers[id] = Printer({exists: true, available: true, model: model, tolerance: tolerance});
        emit PrinterAdded(id, model, tolerance);
    }

    function setAvailability(bytes32 id, bool available) external {
        acl.requireRole(msg.sender, AccessControlHub.Role.Operator);
        if (!printers[id].exists) revert UnknownPrinter(id);
        printers[id].available = available;
        emit AvailabilitySet(id, available);
    }

    function isAvailable(bytes32 id) external view returns (bool) {
        return printers[id].exists && printers[id].available;
    }
}
