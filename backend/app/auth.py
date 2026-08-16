"""Authentication, role-based access control, and separation of duties.

The permission matrix is the on-chain-mirrored access policy. Separation of
duties is structural: the role that grants roles (Admin) is not permitted to
register or run jobs; the role that runs jobs (Operator) cannot grant roles.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .constants import Role
from .crypto import hmac_sign, hmac_verify
from .models import User

# action -> set of roles permitted to perform it
PERMISSIONS: dict[str, set[str]] = {
    "user.manage": {Role.ADMIN},
    "role.grant": {Role.ADMIN},
    "printer.add": {Role.ADMIN},
    "printer.remove": {Role.ADMIN},
    "printer.availability": {Role.OPERATOR},
    "material.manage": {Role.ADMIN},
    "job.register": {Role.CLIENT},
    "job.schedule": {Role.OPERATOR},
    "job.dispatch": {Role.OPERATOR},
    "job.cancel": {Role.CLIENT, Role.OPERATOR, Role.ADMIN},
    "audit.read": {Role.AUDITOR, Role.ADMIN, Role.OPERATOR, Role.CLIENT},
    "fleet.read": {Role.AUDITOR, Role.ADMIN, Role.OPERATOR, Role.CLIENT},
}


class AccessDenied(Exception):
    def __init__(self, actor: str, action: str):
        self.actor = actor
        self.action = action
        super().__init__(f"access denied: {actor} cannot {action}")


def can(role: str, action: str) -> bool:
    return role in PERMISSIONS.get(action, set())


def require(user: User, action: str) -> None:
    if not can(user.role, action):
        raise AccessDenied(user.id, action)


# ---- separation-of-duties invariant (used by tests and startup checks) ----

def separation_of_duties_holds() -> bool:
    grant = PERMISSIONS["role.grant"]
    register = PERMISSIONS["job.register"]
    run = PERMISSIONS["job.schedule"] | PERMISSIONS["job.dispatch"]
    # The granting role must not also register or run jobs.
    if grant & register:
        return False
    if grant & run:
        return False
    return True


# ---- sessions (stateless signed tokens for the MVP) ----

def issue_token(user_id: str) -> str:
    return f"{user_id}.{hmac_sign(user_id.encode())}"


def parse_token(token: str) -> str | None:
    if not token or "." not in token:
        return None
    uid, sig = token.rsplit(".", 1)
    return uid if hmac_verify(uid.encode(), sig) else None


def user_from_token(session: Session, token: str) -> User | None:
    uid = parse_token(token)
    if uid is None:
        return None
    return session.get(User, uid)
