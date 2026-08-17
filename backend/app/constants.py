"""Frozen enumerations shared across the application (see Architecture.md 6)."""
from __future__ import annotations


class Role:
    NONE = "None"
    CLIENT = "Client"
    OPERATOR = "Operator"
    ADMIN = "Admin"
    AUDITOR = "Auditor"
    ALL = {NONE, CLIENT, OPERATOR, ADMIN, AUDITOR}


class JobStatus:
    DRAFT = "Draft"
    SUBMITTED = "Submitted"
    AUTHORIZED = "Authorized"
    SCHEDULED = "Scheduled"
    DISPATCHED = "Dispatched"
    PRINTING = "Printing"
    VERIFIED_A0 = "Verified@A0"
    FAILED = "Failed"
    CANCELLED = "Cancelled"
    EXPIRED = "Expired"
    # Higher-tier terminal states exist in the design; A0 uses the set above.


# Legal forward transitions for the A0 happy path plus terminal branches.
JOB_TRANSITIONS = {
    JobStatus.DRAFT: {JobStatus.SUBMITTED, JobStatus.CANCELLED},
    JobStatus.SUBMITTED: {JobStatus.AUTHORIZED, JobStatus.FAILED, JobStatus.CANCELLED},
    JobStatus.AUTHORIZED: {JobStatus.SCHEDULED, JobStatus.CANCELLED, JobStatus.EXPIRED},
    JobStatus.SCHEDULED: {JobStatus.DISPATCHED, JobStatus.CANCELLED},
    JobStatus.DISPATCHED: {JobStatus.PRINTING, JobStatus.FAILED},
    JobStatus.PRINTING: {JobStatus.VERIFIED_A0, JobStatus.FAILED},
    JobStatus.VERIFIED_A0: set(),
    JobStatus.FAILED: set(),
    JobStatus.CANCELLED: set(),
    JobStatus.EXPIRED: set(),
}

TERMINAL_STATES = {
    JobStatus.VERIFIED_A0,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
    JobStatus.EXPIRED,
}


class PrinterStatus:
    IDLE = "idle"
    PRINTING = "printing"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"
    COMPROMISED = "compromised"


class Tier:
    A0 = "A0"
    A1 = "A1"
    A2 = "A2"
    A3 = "A3"


class Verdict:
    NONE = "none"
    VERIFIED_A0 = "VerifiedA0"
    VERIFIED_A2 = "VerifiedA2"
    VERIFIED_A3 = "VerifiedA3"
    FAILED = "Failed"
    DISPUTED = "Disputed"


class Phase:
    IDLE = "idle"
    HEATING = "heating"
    PRINTING = "printing"
    COOLING = "cooling"


class Scenario:
    LEGITIMATE = "legitimate"
    LAZY_FAKE = "lazy-fake"
    SABOTAGED = "sabotaged"


class Plane:
    MACHINE = "machine"
    INDEPENDENT = "independent"
