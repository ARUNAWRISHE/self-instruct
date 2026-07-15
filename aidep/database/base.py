"""
SQLAlchemy 2.0 async-ready database engine and session factory.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


def _build_engine(database_url: str, echo: bool = False):
    return create_engine(
        database_url,
        pool_size=5,
        max_overflow=10,
        echo=echo,
        pool_pre_ping=True,
    )


def create_session_factory(database_url: str, echo: bool = False) -> sessionmaker:
    engine = _build_engine(database_url, echo=echo)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


# ── Convenience singleton access (populated in app lifespan) ─────────────────
_engine = None
_SessionLocal: sessionmaker | None = None


def init_db(database_url: str, echo: bool = False) -> None:
    """Initialize the module-level engine and session factory."""
    global _engine, _SessionLocal
    _engine = _build_engine(database_url, echo=echo)
    _SessionLocal = sessionmaker(
        bind=_engine, autocommit=False, autoflush=False, class_=Session
    )
    # Create all tables that are not yet present
    Base.metadata.create_all(bind=_engine)


def get_session() -> Session:
    """Yield a database session (for use in FastAPI dependency injection)."""
    if _SessionLocal is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    session: Session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_engine():
    """Return the module-level SQLAlchemy engine."""
    if _engine is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    return _engine
