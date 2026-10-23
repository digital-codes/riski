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
# Run-state bookkeeping (no file-based state; tracking table is the only source)
# ---------------------------------------------------------------------------


class TestRunState:
    def test_no_file_based_state_exists(self):
        """last_run.txt support must be fully removed from the crawler."""
        assert not hasattr(ou, "load_last_run")
        assert not hasattr(ou, "save_last_run")
        assert not hasattr(ou, "LAST_RUN_FILE")

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


class _FakeRecorder:
    """Minimal recorder capturing all interactions (no DB)."""

    def __init__(self):
        self.started = None
        self.end_state = None
        self.finished = None
        self.items = []
        self.errors = 0
        self.available = True

    def start(self, baseline):
        self.started = baseline

    def record_item(self, element_type, oparl_id, oparl_key=None, status="modified"):
        self.items.append({
            "element_type": element_type,
            "oparl_id": oparl_id,
            "oparl_key": oparl_key,
            "status": status,
        })

    def record_error(self):
        self.errors += 1

    def set_end_state(self, state):
        self.end_state = state

    def finish(self, success=True):
        self.finished = success


class TestCrawlIncremental:
    @pytest.fixture()
    def crawl_env(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ou, "OUTPUT_FOLDER", str(tmp_path / "json"))
        monkeypatch.setattr(ou, "OUTPUT_PDF_FOLDER", str(tmp_path / "pdf"))
        requested = []
        return requested, tmp_path

    def test_first_run_crawls_and_records_state(self, crawl_env, monkeypatch, tmp_path):
        requested, _ = crawl_env
        recorder = _FakeRecorder()
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
        ou.crawl_oparl("https://x/oparl", "2026-10-01T00:00:00Z", recorder=recorder)
        # run recorded: baseline, end state, success
        assert recorder.started == "2026-10-01T00:00:00Z"
        assert recorder.end_state is not None and recorder.end_state != "2026-10-01T00:00:00"
        assert recorder.end_state.startswith("2026-10-2") or recorder.end_state.startswith("2026-10-23T10")
        assert recorder.finished is True
        # the createdSince parameter contained the initial baseline
        assert any("createdSince=2026-10-01T00%3A00%3A00Z" in u for u in requested)
        # collection response was saved (body arrives inside the wrapper)
        saved = list((tmp_path / "json").iterdir())
        assert saved
        assert all(f.suffix == ".json" for f in saved)

    def test_second_run_uses_end_state_as_baseline(self, crawl_env, monkeypatch):
        requested, _ = crawl_env
        recorder = _FakeRecorder()
        recorder.end_state = "2026-10-20T00:00:00"

        def fake_get(url, timeout=None):
            requested.append(url)
            return _json_response({"data": [], "links": {}})

        monkeypatch.setattr(ou.requests, "get", fake_get)
        ou.crawl_oparl("https://x/oparl", recorder.end_state, recorder=recorder)
        # the incremental query uses the tracked end state, not the epoch
        assert any("createdSince=2026-10-20T00%3A00%3A00" in u for u in requested)
        assert not any("1970" in u for u in requested)

    def test_epoch_baseline_fetches_everything(self, crawl_env, monkeypatch):
        """With no tracked state the baseline is the epoch (fetch everything)."""
        from src.oparlRunLog import resolve_baseline

        requested, _ = crawl_env

        class NoRows:
            """Engine whose baseline query finds no rows."""

            def connect(self):
                raise RuntimeError("no rows")

        baseline, source = resolve_baseline(engine=NoRows())
        assert source == "epoch"
        assert baseline.startswith("1970-01-01")
        # the crawl receives the epoch baseline -> createdSince contains it
        recorder = _FakeRecorder()

        def fake_get(url, timeout=None):
            requested.append(url)
            return _json_response({"data": [], "links": {}})

        monkeypatch.setattr(ou.requests, "get", fake_get)
        ou.crawl_oparl("https://x/oparl", baseline, recorder=recorder)
        assert any("createdSince=1970-01-01T00%3A00%3A00Z" in u for u in requested)
        assert recorder.started == baseline

    def test_network_error_does_not_crash_crawl(self, crawl_env, monkeypatch):
        requested, _ = crawl_env

        def fake_get(url, timeout=None):
            requested.append(url)
            if "bodies/0001" in url and "papers" in url:
                raise requests.ConnectionError("down")
            return _json_response({"data": [], "links": {}})

        monkeypatch.setattr(ou.requests, "get", fake_get)
        ou.crawl_oparl("https://x/oparl", "2026-10-01T00:00:00Z")  # must not raise
        assert requested  # it still tried

    def test_failed_fetch_recorded_as_error(self, crawl_env, monkeypatch):
        requested, _ = crawl_env
        recorder = _FakeRecorder()

        def fake_get(url, timeout=None):
            raise requests.ConnectionError("down")

        monkeypatch.setattr(ou.requests, "get", fake_get)
        ou.crawl_oparl("https://x/oparl", "2026-10-01T00:00:00Z", recorder=recorder)
        # state stays at the baseline (no newer timestamps were seen) and the
        # fetch failures are visible in the run record
        assert recorder.end_state == "2026-10-01T00:00:00"
        assert recorder.errors > 0
        assert recorder.finished is True

    def test_process_resource_records_new_vs_modified(self, crawl_env, monkeypatch, tmp_path):
        _, tmp_path = crawl_env
        recorder = _FakeRecorder()
        base = {"id": "https://x/meetings/7", "type": "https://schema.oparl.org/1.1/Meeting",
                "name": "Rat", "date": "2024-07-23T18:00:00",
                "modified": "2025-01-01T00:00:00Z"}

        # first save: file does not exist -> 'new'
        ou.process_resource(base, "https://x/meetings/7", recorder=recorder)
        assert recorder.items == [{
            "element_type": "Meeting",
            "oparl_id": "https://x/meetings/7",
            "oparl_key": "7",
            "status": "new",
        }]

        # unchanged resource: skipped, not recorded
        ou.process_resource(base, "https://x/meetings/7", recorder=recorder)
        assert len(recorder.items) == 1

        # newer version replaces the stored copy -> 'modified'
        newer = dict(base, modified="2026-01-01T00:00:00Z")
        ou.process_resource(newer, "https://x/meetings/7", recorder=recorder)
        assert len(recorder.items) == 2
        assert recorder.items[1]["status"] == "modified"

    def test_mixed_offset_timestamps_do_not_raise(self, crawl_env, monkeypatch):
        """Resources with '+02:00' offsets must not break baseline comparison
        against the naive epoch baseline (pre-existing bug, now fixed)."""
        requested, _ = crawl_env
        recorder = _FakeRecorder()

        def fake_get(url, timeout=None):
            requested.append(url)
            return _json_response({
                "data": [],
                "links": {},
                "modified": "2026-10-23T10:00:00+02:00",
            })

        monkeypatch.setattr(ou.requests, "get", fake_get)
        ou.crawl_oparl("https://x/oparl", "1970-01-01T00:00:00Z", recorder=recorder)
        # end state advanced past the epoch despite the mixed offsets
        assert recorder.end_state.startswith("2026-10-23")


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
