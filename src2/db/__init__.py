import os
import logging
from contextlib import contextmanager
from typing import Any, Mapping

from sqlalchemy import create_engine, inspect, Table, text
from sqlalchemy.engine import Engine, Connection
from sqlalchemy.orm import scoped_session, sessionmaker, declarative_base

# ----------------------------------------------------------------------
# Configuration – read from private module (fallback to env vars)
# ----------------------------------------------------------------------
try:
    # Import private constants if available (project‑specific values)
    from src.private import DB_USER, DB_PWD, DB_NAME, DB_HOST
except Exception:
    DB_USER = os.getenv("DB_USER", "riski")
    DB_PWD = os.getenv("DB_PWD", "riski")
    DB_NAME = os.getenv("DB_NAME", "riski_agentic")
    DB_HOST = os.getenv("DB_HOST", "localhost")

POSTGRES_URL = os.getenv(
    "POSTGRES_URL",
    f"postgresql+psycopg2://{DB_USER}:{DB_PWD}@{DB_HOST}/{DB_NAME}",
)

_engine: Engine | None = None
Session = scoped_session(sessionmaker())
Base = declarative_base()


def get_engine(url: str | None = None) -> Engine:
    """Return a singleton SQLAlchemy Engine.

    The optional *url* overrides the default database URL. The engine is cached
    for the lifetime of the process, ensuring a single connection pool.
    """
    global _engine
    if _engine is None:
        _engine = create_engine(url or POSTGRES_URL, pool_pre_ping=True, future=True)
        Session.configure(bind=_engine)
    return _engine


def table_exists(name: str) -> bool:
    """Check whether *name* exists in the current database."""
    engine = get_engine()
    with engine.connect() as conn:
        return inspect(conn).has_table(name)


def upsert(table: Table, pk: Mapping[str, Any], values: Mapping[str, Any]) -> None:
    """Insert or update a row using ``ON CONFLICT DO UPDATE``.

    ``pk`` is a mapping of the primary‑key columns, ``values`` contains the
    columns to set on conflict.
    """
    insert_stmt = table.insert().values(**{**pk, **values})
    conflict_stmt = insert_stmt.on_conflict_do_update(
        index_elements=list(pk.keys()), set_=values
    )
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(conflict_stmt)
        conn.commit()


@contextmanager
def db_connection() -> Connection:
    """Yield a raw connection that commits on success, rolls back on error."""
    engine = get_engine()
    conn = engine.connect()
    trans = conn.begin()
    try:
        yield conn
        trans.commit()
    except Exception:
        trans.rollback()
        raise
    finally:
        conn.close()


def get_logger(name: str) -> logging.Logger:
    """Return a module‑level logger with a simple console handler."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "% (asctime)s %(levelname)s %(name)s: %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
