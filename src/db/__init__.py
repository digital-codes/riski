import os
import logging
from contextlib import contextmanager
from typing import Any, Mapping

from sqlalchemy import create_engine, inspect, Table, text
from sqlalchemy.engine import Engine, Connection
from sqlalchemy.orm import scoped_session, sessionmaker, declarative_base

# ----------------------------------------------------------------------
# Configuration – resolution order:
#   1. POSTGRES_URL / POSTGRES_RO_URL env vars (full URL, wins everything)
#   2. src/private.py module attributes (DB_*, RO_*)
#   3. environment variables (DB_*, RO_*)
#   4. safe local defaults
# ----------------------------------------------------------------------


def _load_private():
    try:
        import src.private as pr

        return pr
    except Exception:
        return None


def build_url(user: str, pwd: str, host: str, name: str) -> str:
    return f"postgresql+psycopg2://{user}:{pwd}@{host}/{name}"


def _resolve_config() -> dict:
    """Resolve connection settings.

    Order: private.py attribute -> environment variable -> safe default.
    The full-URL env vars ``POSTGRES_URL`` / ``POSTGRES_RO_URL`` override
    everything.
    """
    pr = _load_private()

    def _get(attr: str, env_key: str, default: str | None = None) -> str | None:
        if pr is not None:
            value = getattr(pr, attr, None)
            if value:
                return value
        return os.getenv(env_key, default)

    user = _get("DB_USER", "DB_USER", "riski")
    pwd = _get("DB_PWD", "DB_PWD", "riski")
    name = _get("DB_NAME", "DB_NAME", "riski_agentic")
    host = _get("DB_HOST", "DB_HOST", "localhost")
    ro_user = _get("RO_USER", "RO_USER", user)
    ro_pwd = _get("RO_PWD", "RO_PWD", pwd)

    return {
        "DB_USER": user,
        "DB_PWD": pwd,
        "DB_NAME": name,
        "DB_HOST": host,
        "RO_USER": ro_user,
        "RO_PWD": ro_pwd,
        "POSTGRES_URL": os.getenv("POSTGRES_URL") or build_url(user, pwd, host, name),
        "POSTGRES_RO_URL": os.getenv("POSTGRES_RO_URL")
        or build_url(ro_user, ro_pwd, host, name),
    }


globals().update(_resolve_config())

_engines: dict[str, Engine] = {}
Session = scoped_session(sessionmaker())
Base = declarative_base()


def get_engine(url: str | None = None, readonly: bool = False) -> Engine:
    """Return a cached SQLAlchemy Engine.

    The optional *url* overrides the default database URL. Engines are cached
    per URL for the lifetime of the process, ensuring a single connection pool
    per target database. With ``readonly=True`` the read-only role URL is used
    (unless an explicit *url* is given).
    """
    if url is None:
        url = POSTGRES_RO_URL if readonly else POSTGRES_URL
    engine = _engines.get(url)
    if engine is None:
        engine = create_engine(url, pool_pre_ping=True, future=True)
        _engines[url] = engine
        if not readonly:
            Session.configure(bind=engine)
    return engine


def table_exists(name: str, engine: Engine | None = None) -> bool:
    """Check whether *name* exists in the current database."""
    engine = engine or get_engine()
    with engine.connect() as conn:
        return inspect(conn).has_table(name)


def upsert(table: Table, pk: Mapping[str, Any], values: Mapping[str, Any]) -> None:
    """Insert or update a row using ``ON CONFLICT DO UPDATE``.

    ``pk`` is a mapping of the primary-key columns, ``values`` contains the
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
def db_connection(readonly: bool = False) -> Connection:
    """Yield a raw connection that commits on success, rolls back on error."""
    engine = get_engine(readonly=readonly)
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
    """Return a module-level logger with a simple console handler."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
