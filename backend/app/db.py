"""Database engine and session management (SQLAlchemy 2.0)."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        url = settings.database_url
        if url in ("sqlite://", "sqlite:///:memory:"):
            # a single shared in-memory connection so tables persist across sessions
            _engine = create_engine(url, connect_args={"check_same_thread": False},
                                    poolclass=StaticPool, future=True)
        else:
            connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
            _engine = create_engine(url, connect_args=connect_args, future=True)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False, future=True)
    return _engine


def init_db() -> None:
    """Create all tables. Idempotent."""
    from . import models  # noqa: F401  (register models)

    get_engine()
    Base.metadata.create_all(bind=_engine)


def session_scope() -> Session:
    get_engine()
    return _SessionLocal()


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    get_engine()
    s = _SessionLocal()
    try:
        yield s
    finally:
        s.close()


def reset_db_for_tests(url: str = "sqlite:///:memory:") -> None:
    """Point the engine at a fresh database. Test helper only."""
    global _engine, _SessionLocal
    from .config import settings as _s

    _s.database_url = url
    _engine = None
    _SessionLocal = None
    init_db()
