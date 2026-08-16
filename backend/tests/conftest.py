import pytest

from app.constants import Role
from app.db import reset_db_for_tests, session_scope
from app.ledger import reset_ledger_for_tests
from app.models import User
from app.users import bootstrap_admin


@pytest.fixture()
def session():
    reset_db_for_tests("sqlite:///:memory:")
    reset_ledger_for_tests()
    with session_scope() as s:
        bootstrap_admin(s)
        s.commit()
    s = session_scope()
    try:
        yield s
    finally:
        s.close()


def make_user(session, uid: str, role: str, org: str = "test") -> User:
    u = User(id=uid, role=role, org=org, granted_by="admin")
    session.merge(u)
    session.flush()
    return session.get(User, uid)


@pytest.fixture()
def actors(session):
    return {
        "admin": session.get(User, "admin"),
        "operator": make_user(session, "op-1", Role.OPERATOR),
        "client": make_user(session, "client-1", Role.CLIENT),
        "auditor": make_user(session, "auditor-1", Role.AUDITOR),
    }
