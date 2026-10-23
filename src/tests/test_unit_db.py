"""Unit tests for src.db – no live database required."""

import os
import types

import pytest

from src import db


def test_logger_emission_does_not_raise():
    logger = db.get_logger("unit.db.logtest")
    logger.info("hello %s", "world")
    logger.warning("warning without args")


def test_get_engine_singleton():
    e1 = db.get_engine()
    e2 = db.get_engine()
    assert e1 is e2


def test_build_url_format():
    url = db.build_url("u", "p", "h", "n")
    assert url == "postgresql+psycopg2://u:p@h/n"


def test_get_engine_explicit_url():
    engine = db.get_engine(url="sqlite://")
    assert str(engine.url) == "sqlite://"


def test_get_engine_readonly_uses_ro_url(monkeypatch):
    db._engines.pop("sqlite://", None)
    monkeypatch.setattr(db, "POSTGRES_RO_URL", "sqlite://")
    engine = db.get_engine(readonly=True)
    assert str(engine.url) == "sqlite://"


def test_get_engine_readonly_distinct_from_default(monkeypatch):
    db._engines.pop("sqlite://", None)
    monkeypatch.setattr(db, "POSTGRES_RO_URL", "sqlite://")
    ro = db.get_engine(readonly=True)
    default = db.get_engine()
    assert ro is not default


def _fake_private(**attrs):
    return types.SimpleNamespace(**attrs)


def test_precedence_private_module(monkeypatch):
    fake = _fake_private(DB_USER="privuser", DB_PWD="privpwd", DB_HOST="privhost", DB_NAME="privdb")
    monkeypatch.setattr(db, "_load_private", lambda: fake)
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.delenv("POSTGRES_RO_URL", raising=False)
    cfg = db._resolve_config()
    assert cfg["POSTGRES_URL"] == "postgresql+psycopg2://privuser:privpwd@privhost/privdb"


def test_precedence_explicit_url_wins(monkeypatch):
    fake = _fake_private(DB_USER="privuser", DB_PWD="privpwd", DB_HOST="privhost", DB_NAME="privdb")
    monkeypatch.setattr(db, "_load_private", lambda: fake)
    monkeypatch.setenv("POSTGRES_URL", "postgresql+psycopg2://envuser:envpwd@envhost/envdb")
    monkeypatch.delenv("POSTGRES_RO_URL", raising=False)
    cfg = db._resolve_config()
    assert cfg["POSTGRES_URL"] == "postgresql+psycopg2://envuser:envpwd@envhost/envdb"
    # RO URL still falls back to private.py role
    assert cfg["POSTGRES_RO_URL"] == "postgresql+psycopg2://privuser:privpwd@privhost/privdb"


def test_precedence_env_over_default(monkeypatch):
    monkeypatch.setattr(db, "_load_private", lambda: None)
    monkeypatch.setenv("DB_USER", "envuser")
    monkeypatch.setenv("DB_PWD", "envpwd")
    monkeypatch.setenv("DB_HOST", "envhost")
    monkeypatch.setenv("DB_NAME", "envdb")
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.delenv("POSTGRES_RO_URL", raising=False)
    cfg = db._resolve_config()
    assert cfg["POSTGRES_URL"] == "postgresql+psycopg2://envuser:envpwd@envhost/envdb"


def test_precedence_defaults(monkeypatch):
    monkeypatch.setattr(db, "_load_private", lambda: None)
    for key in ("DB_USER", "DB_PWD", "DB_HOST", "DB_NAME",
                "RO_USER", "RO_PWD", "POSTGRES_URL", "POSTGRES_RO_URL"):
        monkeypatch.delenv(key, raising=False)
    cfg = db._resolve_config()
    assert cfg["POSTGRES_URL"] == "postgresql+psycopg2://riski:riski@localhost/riski_agentic"
    # read-only role falls back to the write credentials
    assert cfg["POSTGRES_RO_URL"] == cfg["POSTGRES_URL"]


def test_ro_role_falls_back_to_db_creds(monkeypatch):
    fake = _fake_private(DB_USER="wuser", DB_PWD="wpwd", DB_HOST="h", DB_NAME="n")
    monkeypatch.setattr(db, "_load_private", lambda: fake)
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.delenv("POSTGRES_RO_URL", raising=False)
    cfg = db._resolve_config()
    assert cfg["POSTGRES_RO_URL"] == "postgresql+psycopg2://wuser:wpwd@h/n"


def test_private_py_ignored_by_git():
    import subprocess

    repo_root = os.path.abspath(os.path.join(os.path.dirname(db.__file__), "..", ".."))
    result = subprocess.run(
        ["git", "check-ignore", "-v", "src/private.py"],
        cwd=repo_root, capture_output=True, text=True,
    )
    assert result.returncode == 0, "src/private.py must stay git-ignored"

pytestmark = pytest.mark.unit
