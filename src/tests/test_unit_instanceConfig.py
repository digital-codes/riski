"""Unit tests for the instance config loader (src.instanceConfig,
change: instance-agnostic-config)."""

from __future__ import annotations

import pytest
import yaml

import src.instanceConfig as ic
from src.instanceConfig import (
    DEFAULTS,
    _deep_merge,
    _env_overrides,
    clear_cache,
    config_path,
    get_instance_config,
    section,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """No stray RISKI_* overrides and no instance config file: every test
    starts from the pure defaults."""
    for key in list(__import__("os").environ):
        if key.startswith("RISKI_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(ic, "DEFAULT_CONFIG_PATH", "/nonexistent/instance.yaml")
    clear_cache()
    yield
    clear_cache()


class TestDefaults:
    def test_no_config_means_karlsruhe_defaults(self):
        cfg = get_instance_config()
        assert cfg == DEFAULTS
        assert cfg["oparl"]["system_url"] == "https://web1.karlsruhe.de/ris/oparl"
        assert cfg["oparl"]["bodies"] == []
        assert cfg["geo"]["city"] == "Karlsruhe"
        assert cfg["geo"]["map_center"] == [49.0069, 8.4037]
        assert cfg["paths"]["log_filename"] == "ko_update_crawl.log"
        assert cfg["rules"]["haushalt_codes"] is True

    def test_section_helper(self):
        assert section("geo")["map_zoom"] == 12
        assert section("does_not_exist") == {}

    def test_shipped_example_file_equals_defaults(self):
        """config/instance.yaml documents the defaults — it must parse to
        exactly them (parity guard against drift)."""
        path = ic.DEFAULT_CONFIG_PATH.replace("/nonexistent/", "")  # sanity
        with open("config/instance.yaml") as f:
            data = yaml.safe_load(f)
        assert data == DEFAULTS

    def test_shipped_file_loads_identically(self, tmp_path, monkeypatch):
        import shutil

        target = tmp_path / "instance.yaml"
        shutil.copy("config/instance.yaml", target)
        monkeypatch.setenv("RISKI_INSTANCE_CONFIG", str(target))
        clear_cache()
        assert get_instance_config() == DEFAULTS


class TestEnvOverride:
    def test_env_wins_over_defaults(self, monkeypatch):
        monkeypatch.setenv("RISKI_OPARL__SYSTEM_URL", "https://oparl.dresden.de/system")
        monkeypatch.setenv("RISKI_GEO__CITY", "München")
        monkeypatch.setenv("RISKI_OPARL__PAGE_LIMIT", "100")
        monkeypatch.setenv("RISKI_RULES__HAUSHALT_CODES", "false")
        cfg = get_instance_config()
        assert cfg["oparl"]["system_url"] == "https://oparl.dresden.de/system"
        assert cfg["geo"]["city"] == "München"
        assert cfg["oparl"]["page_limit"] == 100  # scalar parsed as int
        assert cfg["rules"]["haushalt_codes"] is False

    def test_env_preserves_unset_keys(self, monkeypatch):
        monkeypatch.setenv("RISKI_GEO__CITY", "Dresden")
        cfg = get_instance_config()
        assert cfg["geo"]["map_center"] == [49.0069, 8.4037]
        assert cfg["oparl"]["system_url"] == DEFAULTS["oparl"]["system_url"]

    def test_non_riski_env_ignored(self, monkeypatch):
        monkeypatch.setenv("RISKI_INSTANCE_CONFIG", "/x/y")
        monkeypatch.setenv("OPARL__SYSTEM_URL", "https://evil")
        cfg = get_instance_config()
        # RISKI_INSTANCE_CONFIG only changes the file path (nonexistent →
        # defaults), never becomes a config value
        assert cfg == DEFAULTS


class TestConfigFile:
    def test_file_overrides_defaults(self, tmp_path):
        p = tmp_path / "instance.yaml"
        p.write_text(yaml.safe_dump({"geo": {"city": "Dresden"}}))
        monkey = pytest.MonkeyPatch()
        monkey.setenv("RISKI_INSTANCE_CONFIG", str(p))
        try:
            clear_cache()
            cfg = get_instance_config()
            assert cfg["geo"]["city"] == "Dresden"
            assert cfg["geo"]["map_zoom"] == 12  # untouched default
        finally:
            monkey.undo()
            clear_cache()

    def test_env_beats_file(self, tmp_path, monkeypatch):
        p = tmp_path / "instance.yaml"
        p.write_text(yaml.safe_dump({"geo": {"city": "Dresden"}}))
        monkeypatch.setenv("RISKI_INSTANCE_CONFIG", str(p))
        monkeypatch.setenv("RISKI_GEO__CITY", "Hamburg")
        clear_cache()
        assert get_instance_config()["geo"]["city"] == "Hamburg"

    def test_malformed_file_raises(self, tmp_path):
        p = tmp_path / "instance.yaml"
        p.write_text("- just\n- a\n- list\n")
        monkey = pytest.MonkeyPatch()
        monkey.setenv("RISKI_INSTANCE_CONFIG", str(p))
        try:
            clear_cache()
            with pytest.raises(ValueError, match="mapping"):
                get_instance_config()
        finally:
            monkey.undo()
            clear_cache()


class TestHelpers:
    def test_deep_merge_nested(self):
        out = _deep_merge({"a": {"b": 1, "c": 2}, "d": 3}, {"a": {"b": 9}})
        assert out == {"a": {"b": 9, "c": 2}, "d": 3}

    def test_env_overrides_empty_without_riski_vars(self, monkeypatch):
        assert _env_overrides() == {}

    def test_config_path_from_env(self, monkeypatch):
        monkeypatch.setenv("RISKI_INSTANCE_CONFIG", "/tmp/other.yaml")
        assert config_path() == "/tmp/other.yaml"

    def test_cache_cleared_by_helper(self, monkeypatch):
        monkeypatch.setenv("RISKI_GEO__CITY", "A")
        assert get_instance_config()["geo"]["city"] == "A"
        monkeypatch.setenv("RISKI_GEO__CITY", "B")
        assert get_instance_config()["geo"]["city"] == "A"  # cached
        clear_cache()
        assert get_instance_config()["geo"]["city"] == "B"


class TestEnvBeatsPrivate:
    """change: instance-agnostic-config (task 5.3): every private.py
    credential/endpoint is resolvable via environment variable, and the
    environment wins — a second instance needs no edited source file."""

    def test_remote_env_wins_over_private(self, monkeypatch):
        import src.private as pr
        import src.remote as remote

        monkeypatch.setattr(remote, "_pr", pr)
        monkeypatch.setenv("EMBED_BASE_URL", "https://env.example/v1")
        assert remote._get("EMB_URL", "EMBED_BASE_URL") == "https://env.example/v1"

    def test_remote_private_when_no_env(self, monkeypatch):
        import src.private as pr
        import src.remote as remote

        monkeypatch.delenv("EMBED_BASE_URL", raising=False)
        monkeypatch.setattr(remote, "_pr", pr)
        private_value = getattr(pr, "EMB_URL", None)
        if not private_value:
            pytest.skip("private.py has no EMB_URL")
        assert remote._get("EMB_URL", "EMBED_BASE_URL") == private_value

    def test_db_env_wins_over_private(self, monkeypatch):
        import src.db as db

        monkeypatch.setenv("DB_NAME", "riski_dresden")
        assert db._resolve_config()["DB_NAME"] == "riski_dresden"

    def test_db_private_when_no_env(self, monkeypatch):
        import src.db as db
        import src.private as pr

        for key in ("DB_NAME", "DB_USER", "DB_PWD", "DB_HOST", "RO_USER", "RO_PWD"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("POSTGRES_URL", "")
        monkeypatch.setenv("POSTGRES_RO_URL", "")
        monkeypatch.setattr(db, "_load_private", lambda: pr)
        cfg = db._resolve_config()
        assert cfg["DB_NAME"] == getattr(pr, "DB_NAME", "riski_agentic")
