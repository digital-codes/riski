"""Unit tests for src.oparlUpdate – HTTP stubbed, filesystem via tmp_path."""

import json

import pytest
import requests

from src import oparlUpdate as ou


# ---------------------------------------------------------------------------
# URL fixing
# ---------------------------------------------------------------------------


class TestFixKarlsruheUrl:
    def test_inserts_ris_segment(self):
        url = "https://web1.karlsruhe.de/oparl/bodies"
        fixed = ou.fix_karlsruhe_url(url)
        assert fixed == "https://web1.karlsruhe.de/ris/oparl/bodies"

    def test_leaves_correct_url_untouched(self):
        url = "https://web1.karlsruhe.de/ris/oparl/bodies"
        assert ou.fix_karlsruhe_url(url) == url

    def test_leaves_foreign_hosts_untouched(self):
        url = "https://schema.oparl.org/1.1/Meeting"
        assert ou.fix_karlsruhe_url(url) == url

    def test_fixes_urls_recursively_in_data(self):
        data = {
            "links": ["https://web1.karlsruhe.de/oparl/a", "https://other.example/x"],
            "nested": {"next": "https://web1.karlsruhe.de/oparl/b"},
        }
        ou.fix_urls_in_data(data)
        assert data["links"][0] == "https://web1.karlsruhe.de/ris/oparl/a"
        assert data["links"][1] == "https://other.example/x"
        assert data["nested"]["next"] == "https://web1.karlsruhe.de/ris/oparl/b"


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------


class TestFilenames:
    def test_sanitize_filename(self):
        assert ou.sanitize_filename("a b/c$d.pdf") == "a_b_c_d.pdf"

    def test_hash_filename(self):
        name = ou.hash_filename_from_url("https://x/y")
        assert name.endswith(".json") and len(name) == 32 + 5

    def test_descriptive_filename(self):
        data = {
            "id": "https://web1.karlsruhe.de/ris/oparl/bodies/0001/meetings/1234",
            "type": "https://schema.oparl.org/1.1/Meeting",
            "date": "2024-07-23T18:00:00",
        }
        name = ou.generate_descriptive_filename(data, "https://fallback")
        assert name == "Meeting_2024-07-23_1234.json"

    def test_fallback_for_non_dict(self):
        name = ou.generate_descriptive_filename([1, 2], "https://fallback")
        assert name.endswith(".json")


# ---------------------------------------------------------------------------
# Run-state bookkeeping
# ---------------------------------------------------------------------------


class TestRunState:
    def test_missing_file_returns_epoch(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ou, "LAST_RUN_FILE", str(tmp_path / "last_run.txt"))
        assert ou.load_last_run() == "1970-01-01T00:00:00Z"

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        path = tmp_path / "last_run.txt"
        monkeypatch.setattr(ou, "LAST_RUN_FILE", str(path))
        ou.save_last_run("2026-10-23T12:00:00+00:00")
        assert ou.load_last_run() == "2026-10-23T12:00:00+00:00"

    def test_empty_file_returns_epoch(self, tmp_path, monkeypatch):
        path = tmp_path / "last_run.txt"
        path.write_text("\n")
        monkeypatch.setattr(ou, "LAST_RUN_FILE", str(path))
        assert ou.load_last_run() == "1970-01-01T00:00:00Z"

    def test_get_resource_timestamp_fields(self):
        assert ou.get_resource_timestamp({"modified": "2024-01-02T03:04:05Z"}).year == 2024
        assert ou.get_resource_timestamp({"date": "2024-05-06"}).month == 5
        assert ou.get_resource_timestamp([]) is not None  # list fallback

    def test_should_save_newer_wins(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ou, "OUTPUT_FOLDER", str(tmp_path))
        # constant 'date' keeps the descriptive filename stable across versions
        base = {"id": "https://x/1", "type": "https://schema.oparl.org/1.1/Meeting",
                "date": "2024-07-23T18:00:00"}
        data = dict(base, modified="2025-01-01T00:00:00Z")
        assert ou.should_save(data, "https://x/1") is True
        ou.save_json(data, "https://x/1")
        older = dict(base, modified="2024-01-01T00:00:00Z")
        assert ou.should_save(older, "https://x/1") is False
        newer = dict(base, modified="2026-01-01T00:00:00Z")
        assert ou.should_save(newer, "https://x/1") is True


# ---------------------------------------------------------------------------
# Crawling with stubbed HTTP
# ---------------------------------------------------------------------------


class TestCrawlIncremental:
    @pytest.fixture()
    def crawl_env(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ou, "OUTPUT_FOLDER", str(tmp_path / "json"))
        monkeypatch.setattr(ou, "OUTPUT_PDF_FOLDER", str(tmp_path / "pdf"))
        monkeypatch.setattr(ou, "LAST_RUN_FILE", str(tmp_path / "last_run.txt"))
        requested = []
        return requested

    def test_first_run_crawls_and_records_state(self, crawl_env, monkeypatch, tmp_path):
        requested = crawl_env
        body = {"id": "https://x/body/1", "type": "https://schema.oparl.org/1.1/Body",
                "modified": "2026-10-23T10:00:00Z"}

        def fake_get(url, timeout=None):
            requested.append(url)
            if "bodies/0001" in url and "consultations" in url:
                return _json_response({"data": [], "links": {}})
            if url.endswith("bodies/0001") or "createdSince" in url:
                return _json_response({"data": [body], "links": {}})
            return _json_response({"data": [], "links": {}})

        monkeypatch.setattr(ou.requests, "get", fake_get)
        ou.crawl_oparl("https://x/oparl", "2026-10-01T00:00:00Z")
        # the run state advanced beyond the baseline (collection wrappers
        # without timestamps fall back to 'now', which still moves forward)
        assert ou.load_last_run() != "2026-10-01T00:00:00"
        assert ou.load_last_run().startswith("2026-10-23")
        # the createdSince parameter contained the initial baseline
        assert any("createdSince=2026-10-01T00%3A00%3A00Z" in u for u in requested)
        # collection response was saved (body arrives inside the wrapper)
        saved = list((tmp_path / "json").iterdir())
        assert saved
        assert all(f.suffix == ".json" for f in saved)

    def test_second_run_requests_from_last_state(self, crawl_env, monkeypatch):
        requested = crawl_env
        ou.save_last_run("2026-10-20T00:00:00+00:00")

        def fake_get(url, timeout=None):
            requested.append(url)
            return _json_response({"data": [], "links": {}})

        monkeypatch.setattr(ou.requests, "get", fake_get)
        ou.crawl_oparl("https://x/oparl", ou.load_last_run())
        # the incremental query uses the stored run state, not the epoch
        assert any("createdSince=2026-10-20T00%3A00%3A00%2B00%3A00" in u for u in requested)
        assert not any("1970" in u for u in requested)

    def test_network_error_does_not_crash_crawl(self, crawl_env, monkeypatch):
        requested = crawl_env

        def fake_get(url, timeout=None):
            requested.append(url)
            if "bodies/0001" in url and "papers" in url:
                raise requests.ConnectionError("down")
            return _json_response({"data": [], "links": {}})

        monkeypatch.setattr(ou.requests, "get", fake_get)
        ou.crawl_oparl("https://x/oparl", "2026-10-01T00:00:00Z")  # must not raise
        assert requested  # it still tried

    def test_failed_fetch_does_not_advance_state(self, crawl_env, monkeypatch):
        requested = crawl_env

        def fake_get(url, timeout=None):
            raise requests.ConnectionError("down")

        monkeypatch.setattr(ou.requests, "get", fake_get)
        # fetch_json swallows network errors -> crawl completes without raising
        ou.crawl_oparl("https://x/oparl", "2026-10-01T00:00:00Z")
        # state stays at the baseline (no newer timestamps were seen)
        assert ou.load_last_run() == "2026-10-01T00:00:00"


class _JsonResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _json_response(payload):
    return _JsonResponse(payload)

pytestmark = pytest.mark.unit
