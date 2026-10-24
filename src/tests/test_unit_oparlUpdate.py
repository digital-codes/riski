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
        self.full_fetches = []
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

    def record_full_fetch(self, element_type):
        self.full_fetches.append(element_type)

    def set_end_state(self, state):
        self.end_state = state

    def finish(self, success=True):
        self.finished = success


@pytest.fixture()
def crawl_env(tmp_path, monkeypatch):
    """Shared crawl environment: output folders in tmp_path, request log."""
    monkeypatch.setattr(ou, "OUTPUT_FOLDER", str(tmp_path / "json"))
    monkeypatch.setattr(ou, "OUTPUT_PDF_FOLDER", str(tmp_path / "pdf"))
    requested = []
    return requested, tmp_path


class TestCrawlIncremental:
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

    def test_offset_aware_baseline_mixed_offsets_do_not_raise(self, crawl_env, monkeypatch):
        """A baseline with a numeric offset (as stored in the tracking table,
        e.g. '2026-02-19T00:00:00+01:00') must not crash timestamp extraction
        when resources carry 'Z' timestamps (found in the first real sync run)."""
        requested, _ = crawl_env
        recorder = _FakeRecorder()

        def fake_get(url, timeout=None):
            requested.append(url)
            return _json_response({
                "data": [],
                "links": {},
                "modified": "2026-10-24T08:00:00Z",
            })

        monkeypatch.setattr(ou.requests, "get", fake_get)
        ou.crawl_oparl("https://x/oparl", "2026-02-19T00:00:00+01:00", recorder=recorder)
        assert recorder.end_state.startswith("2026-10-24")


class TestCollectionFiltering:
    """Tasks 1.1/1.2: timestamp filter on every collection, with fallback."""

    def test_every_collection_requested_with_modifiedsince(self, crawl_env, monkeypatch):
        requested, _ = crawl_env
        recorder = _FakeRecorder()

        def fake_get(url, timeout=None):
            requested.append(url)
            return _json_response({"data": [], "links": {}})

        monkeypatch.setattr(ou.requests, "get", fake_get)
        ou.crawl_oparl("https://x/oparl", "2026-10-01T00:00:00Z", recorder=recorder)
        for collection in ou.COLLECTIONS:
            assert any(
                f"/bodies/0001/{collection}?modifiedSince=2026-10-01T00%3A00%3A00Z" in u
                for u in requested
            ), f"{collection} was not requested with modifiedSince"

    def test_filter_honoured_detection(self):
        baseline = ou.iso_to_dt("2026-10-01T00:00:00Z")
        honoured = {"data": [{"id": "https://x/1", "modified": "2026-10-05T00:00:00Z"}]}
        ignored = {"data": [{"id": "https://x/1", "modified": "2026-01-01T00:00:00Z"}]}
        assert ou._filter_honoured(honoured, baseline, "modifiedSince") is True
        assert ou._filter_honoured(ignored, baseline, "modifiedSince") is False
        # createdSince compares the 'created' field
        honoured_created = {"data": [{"id": "https://x/1", "created": "2026-10-05T00:00:00Z"}]}
        ignored_created = {"data": [{"id": "https://x/1", "created": "2025-01-01T00:00:00Z"}]}
        assert ou._filter_honoured(honoured_created, baseline, "createdSince") is True
        assert ou._filter_honoured(ignored_created, baseline, "createdSince") is False
        # empty page cannot be distinguished -> treated as honoured
        assert ou._filter_honoured({"data": []}, baseline, "modifiedSince") is True

    def test_fallback_to_full_fetch_when_filter_ignored(self, crawl_env, monkeypatch):
        """modifiedSince ignored -> createdSince tried; if also ignored the
        collection is fetched in full and recorded."""
        requested, tmp_path = crawl_env
        recorder = _FakeRecorder()

        def fake_get(url, timeout=None):
            requested.append(url)
            if "modifiedSince" in url:
                # provably ignored: contains an item older than the baseline
                return _json_response({"data": [
                    {"id": "https://x/papers/1",
                     "type": "https://schema.oparl.org/1.1/Paper",
                     "modified": "2020-01-01T00:00:00Z"},
                ], "links": {}})
            if "createdSince" in url and "papers" in url:
                return _json_response({"data": [
                    {"id": "https://x/papers/1",
                     "type": "https://schema.oparl.org/1.1/Paper",
                     "created": "2020-01-01T00:00:00Z"},
                ], "links": {}})
            return _json_response({"data": [], "links": {}})

        monkeypatch.setattr(ou.requests, "get", fake_get)
        ou.crawl_oparl("https://x/oparl", "2026-10-01T00:00:00Z", recorder=recorder)
        # both filter parameters were tried for papers ...
        assert any("papers?modifiedSince=" in u for u in requested)
        assert any("papers?createdSince=" in u for u in requested)
        # ... and the fallback was recorded for the run
        assert recorder.full_fetches == ["papers"]

    def test_created_since_used_when_modified_since_rejected(self, crawl_env, monkeypatch):
        """HTTP error on modifiedSince -> createdSince is used."""
        requested, _ = crawl_env
        recorder = _FakeRecorder()

        def fake_get(url, timeout=None):
            requested.append(url)
            if "modifiedSince" in url:
                raise requests.ConnectionError("400 unknown parameter")
            return _json_response({"data": [], "links": {}})

        monkeypatch.setattr(ou.requests, "get", fake_get)
        ou.crawl_oparl("https://x/oparl", "2026-10-01T00:00:00Z", recorder=recorder)
        assert any("papers?createdSince=" in u for u in requested)
        # createdSince was honoured (empty response) -> no full fetch recorded
        assert recorder.full_fetches == []

    def test_capability_decision_cached_per_run(self, crawl_env, monkeypatch):
        """A decision made for one collection is not re-probed within a run."""
        requested, _ = crawl_env
        recorder = _FakeRecorder()

        def fake_get(url, timeout=None):
            requested.append(url)
            if "modifiedSince" in url:
                return _json_response({"data": [], "links": {}})
            return _json_response({"data": [], "links": {}})

        monkeypatch.setattr(ou.requests, "get", fake_get)
        ou.crawl_oparl("https://x/oparl", "2026-10-01T00:00:00Z", recorder=recorder)
        # each collection was requested exactly once ( honoured first probe,
        # no repeated capability checks for the same collection type)
        for collection in ou.COLLECTIONS:
            n = sum(1 for u in requested if f"/bodies/0001/{collection}?" in u)
            assert n == 1, f"{collection} was probed {n} times"

    def test_crawl_without_finalise_leaves_run_open(self, crawl_env, monkeypatch):
        """finalise=False (sync entry point): end_state is set, run NOT finished."""
        requested, _ = crawl_env
        recorder = _FakeRecorder()

        def fake_get(url, timeout=None):
            requested.append(url)
            return _json_response({"data": [], "links": {}})

        monkeypatch.setattr(ou.requests, "get", fake_get)
        ou.crawl_oparl("https://x/oparl", "2026-10-01T00:00:00Z",
                       recorder=recorder, finalise=False)
        assert recorder.end_state is not None
        assert recorder.finished is None


class TestSubLinkPolicy:
    """OParl 1.1 update mechanism: only pagination + PDFs are followed,
    plain resource references are not dereferenced."""

    def test_is_followable(self):
        assert ou._is_followable("https://x/papers?page=2") is True
        assert ou._is_followable("https://x/downloadfiles/a/1.pdf") is True
        assert ou._is_followable("https://x/consultations/38115") is False
        assert ou._is_followable("https://x/meetings/1/agendaitem") is False

    def test_references_not_dereferenced(self, crawl_env, monkeypatch):
        """A changed consultation referencing old entities must NOT trigger
        fetches of those references (spec: update = filtered collections)."""
        requested, _ = crawl_env
        recorder = _FakeRecorder()

        def fake_get(url, timeout=None):
            requested.append(url)
            if "modifiedSince" in url and "consultations" in url:
                return _json_response({"data": [{
                    "id": "https://x/consultations/38115",
                    "type": "https://schema.oparl.org/1.1/Consultation",
                    "modified": "2026-10-20T10:00:00Z",
                    "meeting": "https://x/meetings/999",
                    "paper": "https://x/papers/888",
                }], "links": {}})
            return _json_response({"data": [], "links": {}})

        monkeypatch.setattr(ou.requests, "get", fake_get)
        ou.crawl_oparl("https://x/oparl", "2026-10-01T00:00:00Z", recorder=recorder)
        # the referenced (unchanged) resources were NOT fetched
        assert not any("/meetings/999" in u for u in requested)
        assert not any("/papers/888" in u for u in requested)

    def test_pagination_is_followed(self, crawl_env, monkeypatch):
        requested, _ = crawl_env
        recorder = _FakeRecorder()

        def fake_get(url, timeout=None):
            requested.append(url)
            if "papers?modifiedSince=" in url:
                return _json_response({
                    "data": [{
                        "id": "https://x/papers/1",
                        "type": "https://schema.oparl.org/1.1/Paper",
                        "modified": "2026-10-20T10:00:00Z",
                    }],
                    "links": {"next": "https://x/papers?modifiedSince=X&page=2"},
                })
            if "page=2" in url:
                return _json_response({"data": [], "links": {}})
            return _json_response({"data": [], "links": {}})

        monkeypatch.setattr(ou.requests, "get", fake_get)
        ou.crawl_oparl("https://x/oparl", "2026-10-01T00:00:00Z", recorder=recorder)
        assert any("page=2" in u for u in requested)

    def test_pdf_downloads_are_followed(self, crawl_env, monkeypatch, tmp_path):
        requested, tmp_path = crawl_env
        recorder = _FakeRecorder()
        pdf_calls = []

        class _PdfResponse:
            def raise_for_status(self):
                pass

            content = b"%PDF-fake"

        def fake_get(url, timeout=None):
            requested.append(url)
            if url.lower().endswith(".pdf"):
                pdf_calls.append(url)
                return _PdfResponse()
            if "meetings?modifiedSince=" in url:
                return _json_response({"data": [{
                    "id": "https://x/meetings/1",
                    "type": "https://schema.oparl.org/1.1/Meeting",
                    "modified": "2026-10-20T10:00:00Z",
                    "auxiliaryFile": [{
                        "id": "https://x/files/7",
                        "type": "https://schema.oparl.org/1.1/File",
                        "downloadUrl": "https://x/downloadfiles/a/7.pdf",
                        "modified": "2026-10-20T10:00:00Z",
                    }],
                }], "links": {}})
            return _json_response({"data": [], "links": {}})

        monkeypatch.setattr(ou.requests, "get", fake_get)
        ou.crawl_oparl("https://x/oparl", "2026-10-01T00:00:00Z", recorder=recorder)
        assert any(u.endswith(".pdf") for u in pdf_calls)
        assert (tmp_path / "pdf" / "7.pdf").exists()

    def test_all_entity_types_have_collections(self):
        """Karlsruhe exposes filtered collections for every crawled type."""
        assert set(ou.COLLECTIONS) == {
            "consultations", "papers", "agendaItems", "meetings", "people",
            "files", "memberships", "organizations", "locations",
        }


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
