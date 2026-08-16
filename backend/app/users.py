"""User and role management."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import require
from .constants import Role
from .ledger import get_ledger
from .models import User


def bootstrap_admin(session: Session, admin_id: str = "admin") -> User:
    """Create the initial admin without an actor. Setup only."""
    existing = session.get(User, admin_id)
    if existing:
        return existing
    u = User(id=admin_id, role=Role.ADMIN, org="fleet", granted_by="system")
    session.add(u)
    session.flush()
    get_ledger().append(session, "system", "AdminBootstrapped", admin_id, {"role": Role.ADMIN})
    return u


def create_user(session: Session, actor: User, *, id: str, role: str, org: str = "default") -> User:
    require(actor, "user.manage")
    if role not in Role.ALL:
        raise ValueError(f"unknown role: {role}")
    u = User(id=id, role=role, org=org, granted_by=actor.id)
    session.merge(u)
    session.flush()
    get_ledger().append(session, actor.id, "UserCreated", id, {"role": role, "org": org})
    return session.get(User, id)


def grant_role(session: Session, actor: User, user_id: str, role: str) -> User:
    require(actor, "role.grant")
    if role not in Role.ALL:
        raise ValueError(f"unknown role: {role}")
    u = session.get(User, user_id)
    if u is None:
        raise ValueError("user not found")
    old = u.role
    u.role = role
    u.granted_by = actor.id
    session.flush()
    get_ledger().append(session, actor.id, "RoleGranted", user_id, {"from": old, "to": role})
    return u


def list_users(session: Session) -> list[User]:
    return list(session.execute(select(User).order_by(User.id)).scalars())
