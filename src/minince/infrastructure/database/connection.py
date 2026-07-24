from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from minince.config import settings


class Base(DeclarativeBase):
    pass


def create_db_engine() -> Engine:
    engine_kwargs: dict[str, object] = {
        "pool_pre_ping": True,
    }

    if settings.is_sqlite:
        engine_kwargs["connect_args"] = {"check_same_thread": False}

    return create_engine(settings.database_url, **engine_kwargs)


engine = create_db_engine()

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session() -> Session:
    return SessionLocal()
