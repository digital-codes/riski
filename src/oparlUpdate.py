
# Dual-mode import support: allow running this file directly as a script
# (``python src/<name>.py``) as well as importing it as ``src.<name>``.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass
# references/oparl/oparl_update.py
import os
import re
import json
import time
import hashlib
import logging
import requests
from collections import deque
from urllib.parse import urlparse, urlunparse, quote
from datetime import datetime, timedelta, timezone

# ----------------------------------------------------------------------
# CONFIGURATION (change: instance-agnostic-config)
#
# All instance-specific values come from the instance config
# (src/instanceConfig: env RISKI_*__* > config/instance.yaml > Karlsruhe
# defaults). The module constants below are the Karlsruhe defaults, kept
# for backwards-compatible imports (syncIncremental) and CLI help; the
# crawl reads the live config via _oparl()/_paths() so env/config-file
# overrides apply without code edits. CLI flags still win over both.
# ----------------------------------------------------------------------
from src.instanceConfig import section as _instance_section

DEFAULT_SYSTEM_URL = "https://web1.karlsruhe.de/ris/oparl"
DEFAULT_OUTPUT_FOLDER = "/mnt_ai/data/odd26/ris/ko"
DEFAULT_OUTPUT_PDF_FOLDER = "/mnt_ai/data/odd26/ris/ko_pdf"
DEFAULT_LOG_FILENAME = "ko_update_crawl.log"

# backwards-compatible aliases (Karlsruhe defaults; live values via config)
SYSTEM_URL = DEFAULT_SYSTEM_URL
OUTPUT_FOLDER = DEFAULT_OUTPUT_FOLDER
OUTPUT_PDF_FOLDER = DEFAULT_OUTPUT_PDF_FOLDER
LOG_FILENAME = DEFAULT_LOG_FILENAME


def _oparl() -> dict:
    """The instance config's ``oparl`` section (system URL, bodies, page
    size, delay, URL rewrites)."""
    return _instance_section("oparl")


def _paths() -> dict:
    """The instance config's ``paths`` section (data directories, log
    name)."""
    return _instance_section("paths")


def _configure_logging():
    """(Re)configure root logging with the configured log file name —
    idempotent, called at crawl start (not at import, so a second instance
    gets its own log file even when the module was imported earlier)."""
    filename = _paths()["log_filename"]
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "") != os.path.abspath(filename):
            root.removeHandler(h)
            h.close()
    if not any(isinstance(h, logging.FileHandler) for h in root.handlers):
        root.addHandler(logging.FileHandler(filename, encoding="utf-8"))
    root.setLevel(logging.INFO)
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in root.handlers):
        root.addHandler(logging.StreamHandler())


# ----------------------------------------------------------------------
# URL REWRITES (change: instance-agnostic-config)
# ----------------------------------------------------------------------
def rewrite_url(url: str, rules=None) -> str:
    """Apply the instance config's ordered regex rewrites to *url*.

    Each rule is ``{pattern, replacement}``. The Karlsruhe default restores
    the ``/ris`` prefix on web1.karlsruhe.de URLs that lack it (same effect
    as the former ``fix_karlsruhe_url``); an empty rule list means no
    rewriting (other backends). Pass *rules* to override the config
    (used by tests)."""
    if rules is None:
        rules = _oparl().get("url_rewrites") or []
    for rule in rules:
        try:
            new_url = re.sub(rule["pattern"], rule["replacement"], url)
        except (KeyError, TypeError, re.error):
            logging.warning("Skipping invalid URL rewrite rule: %r", rule)
            continue
        if new_url != url:
            logging.warning(
                "Rewrote URL:\n  Original: %s\n  Fixed:    %s", url, new_url
            )
            url = new_url
    return url


# former name, kept for backwards compatibility (Karlsruhe-specific fix is
# now the default rewrite rule)
fix_karlsruhe_url = rewrite_url


def fix_urls_in_data(data):
    """Recursively apply the configured URL rewrites to the supplied data
    structure."""
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, str) and v.startswith("http"):
                data[k] = rewrite_url(v)
            elif isinstance(v, (dict, list)):
                fix_urls_in_data(v)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, str) and item.startswith("http"):
                data[i] = rewrite_url(item)
            elif isinstance(item, (dict, list)):
                fix_urls_in_data(item)

# ----------------------------------------------------------------------
# FILENAME / SAVING HELPERS (unchanged)
# ----------------------------------------------------------------------
def sanitize_filename(filename: str) -> str:
    """
    Remove characters that might be illegal on certain filesystems.
    Allow only letters, numbers, underscores, dashes, and periods.
    """
    return re.sub(r"[^A-Za-z0-9._-]", "_", filename)

def hash_filename_from_url(url: str) -> str:
    """
    Fallback: generate a unique filename from the URL using MD5.
    """
    md5_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
    return md5_hash + ".json"

def generate_descriptive_filename(data, url) -> str:
    """
    If 'data' is a dict with a 'type' or 'id', try to build a nicer filename.
    Otherwise, fallback to MD5 hash of 'url'.
    """
    if isinstance(data, dict):
        resource_type = parse_resource_type(data)
        resource_id = parse_resource_id(data)
        resource_date = parse_resource_date(data)
        if resource_type != "Unknown" or resource_id:
            parts = []
            if resource_type != "Unknown":
                parts.append(resource_type)
            if resource_date:
                parts.append(resource_date)
            if resource_id:
                parts.append(resource_id)
            filename = "_".join(parts) + ".json"
            return sanitize_filename(filename)

    # If 'data' is a list, or we didn't get meaningful fields,
    # fallback to hashing:
    return hash_filename_from_url(url)

def parse_resource_type(data: dict) -> str:
    """
    'https://schema.oparl.org/1.1/Meeting' -> 'Meeting', else 'Unknown'
    """
    t = data.get("type", "")
    if t.startswith("http"):
        return t.rstrip("/").split("/")[-1]
    return "Unknown"

def parse_resource_id(data: dict) -> str:
    """
    'https://web1.karlsruhe.de/ris/oparl/bodies/0001/meetings/1234' -> '1234'
    """
    rid = data.get("id", "")
    if rid.startswith("http"):
        return rid.rstrip("/").split("/")[-1]
    return ""

def parse_resource_date(data: dict) -> str:
    """
    Grab the first 10 chars of 'startDate', 'date', 'modified', etc.
    e.g. '2024-07-23T...' -> '2024-07-23'
    """
    for field in ["startDate", "date", "modified", "created"]:
        val = data.get(field)
        if isinstance(val, str) and len(val) >= 10:
            return val[:10]
    return ""

def save_json(data, url: str):
    """
    Save 'data' (could be dict or list) to a JSON file with a descriptive name if possible.
    """
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)
    filename = generate_descriptive_filename(data, url)
    filepath = os.path.join(OUTPUT_FOLDER, filename)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logging.info("Saved data from %s to %s", url, filename)
    except IOError as e:
        logging.error("Could not write to %s: %s", filepath, e)

# ----------------------------------------------------------------------
# TIMESTAMP HELPERS (new)
# ----------------------------------------------------------------------
def iso_to_dt(iso: str) -> datetime:
    """Convert an ISO‑8601 timestamp to a ``datetime`` object.

    The trailing ``Z`` (UTC designator) is stripped. If ``datetime.fromisoformat``
    cannot parse the string, a fallback using ``strptime`` for the common
    ``YYYY‑MM‑DDTHH:MM:SS`` format is attempted.
    """
    iso = iso.rstrip("Z")
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S")

def get_resource_timestamp(data) -> datetime:
    """Extract a timestamp from a resource JSON.

    The function looks for the first of ``modified``, ``created``, ``date`` or
    ``startDate`` fields that contains a string. If the resource is a *list* (e.g.
    a collection wrapper), the function falls back to ``datetime.utcnow()`` so the
    crawler can continue without raising an exception.
    """
    if isinstance(data, dict):
        for field in ["modified", "created", "date", "startDate"]:
            val = data.get(field)
            if isinstance(val, str):
                return iso_to_dt(val)
    # List or missing fields – use current time as a safe fallback
    return datetime.utcnow()

def should_save(data: dict, url: str) -> bool:
    """Determine whether a fetched resource should be written to disk.

    * If the target file does not exist, the resource is saved.
    * If the file exists, the function compares the ``modified``/``created``
      timestamps of the existing JSON and the newly fetched data. The newer
      resource wins.
    * Any error while reading or parsing the existing file results in the
      resource being saved (fail‑safe).
    """
    filename = generate_descriptive_filename(data, url)
    path = os.path.join(OUTPUT_FOLDER, filename)
    if not os.path.exists(path):
        return True
    try:
        with open(path, "r", encoding="utf-8") as f:
            existing = json.load(f)
        existing_ts = get_resource_timestamp(existing)
        incoming_ts = get_resource_timestamp(data)
        return incoming_ts > existing_ts
    except Exception:
        return True

# ----------------------------------------------------------------------
# FETCH / PDF / LINK EXTRACTION (unchanged)
# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# RATE LIMITING / RETRY (shared HTTP layer for fetch_json / fetch_pdf)
# ----------------------------------------------------------------------
# Politeness delay between consecutive API requests and 429 handling:
# the earlier full-graph crawls produced thousands of HTTP 429 errors,
# and every rate-limited resource was silently skipped ("No data").
# Delay and page size come from the instance config (oparl section);
# Karlsruhe defaults: 0.25 s / 1000 items per page.
MAX_RETRIES = 5       # 429 retries per request

_last_request_time = [0.0]


def _request_delay() -> float:
    """Politeness delay from the instance config (oparl.request_delay)."""
    return float(_oparl().get("request_delay", 0.25))


def _http_get(url: str, timeout: int = 15):
    """GET with politeness delay and 429/Retry-After handling.

    Honours the server's ``Retry-After`` header (exponential back-off up
    to 60 s otherwise). Raises ``requests.HTTPError`` on persistent 429s;
    other HTTP/network errors are left to the caller.
    """
    since = time.monotonic() - _last_request_time[0]
    delay = _request_delay()
    if 0.0 <= since < delay:
        time.sleep(delay - since)
    _last_request_time[0] = time.monotonic()

    resp = requests.get(url, timeout=timeout)
    attempt = 0
    while resp.status_code == 429 and attempt < MAX_RETRIES:
        retry_after = resp.headers.get("Retry-After")
        delay = float(retry_after) if retry_after and str(retry_after).replace(".", "", 1).isdigit() \
            else min(60.0, 2.0 ** attempt)
        logging.warning("Rate limited (429) on %s; retry %d/%d in %.1fs",
                        url, attempt + 1, MAX_RETRIES, delay)
        time.sleep(delay)
        _last_request_time[0] = time.monotonic()
        resp = requests.get(url, timeout=timeout)
        attempt += 1
    return resp


def fetch_json(url: str):
    """
    Fetch JSON from a URL. Catch network/HTTP errors and JSON decode errors.
    Fix all embedded Karlsruhe URLs. Return either a dict or a list (or empty).
    """
    fixed_url = fix_karlsruhe_url(url)
    try:
        logging.info("Fetching: %s", fixed_url)
        resp = _http_get(fixed_url)
        resp.raise_for_status()
        data = resp.json()
        fix_urls_in_data(data)
        return data
    except requests.RequestException as e:
        logging.error("Network/HTTP error for %s: %s", fixed_url, e)
        return {}
    except json.JSONDecodeError as e:
        logging.error("Invalid JSON from %s: %s", fixed_url, e)
        return {}

def fetch_pdf(url: str):
    """
    Fetch PDF from a URL. Catch network/HTTP errors. Return bytes or None.
    """
    fixed_url = fix_karlsruhe_url(url)
    try:
        logging.info("Fetching: %s", fixed_url)
        resp = _http_get(fixed_url)
        resp.raise_for_status()
        return resp.content
    except requests.RequestException as e:
        logging.error("Network/HTTP error for %s: %s", fixed_url, e)
        return None

def extract_links(obj) -> list:
    """
    Recursively find all URLs in 'obj'. 'obj' can be a dict, list, etc.
    Return a list of unique links as strings.
    """
    found = set()
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, str) and v.startswith("http"):
                found.add(v)
            elif isinstance(v, (dict, list)):
                found.update(extract_links(v))
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, str) and item.startswith("http"):
                found.add(item)
            elif isinstance(item, (dict, list)):
                found.update(extract_links(item))
    return list(found)

def process_resource(data, url: str, recorder=None) -> list:
    """Save *data* if newer than the stored copy and record the change.

    The file-level semantics of ``should_save`` determine the tracked status:
    a resource with no existing output file is ``new``, a resource replacing
    an older stored copy is ``modified``.
    """
    if should_save(data, url):
        path = os.path.join(OUTPUT_FOLDER, generate_descriptive_filename(data, url))
        is_new = not os.path.exists(path)
        save_json(data, url)
        if recorder is not None and isinstance(data, dict):
            element_type = parse_resource_type(data)
            oparl_id = data.get("id") if isinstance(data, dict) else None
            oparl_key = str(oparl_id).rstrip("/").split("/")[-1] if oparl_id else None
            recorder.record_item(
                element_type or "Unknown",
                oparl_id or url,
                oparl_key,
                "new" if is_new else "modified",
            )
    else:
        logging.info("Skipping unchanged resource: %s", url)
    return extract_links(data)

# ----------------------------------------------------------------------
# CRAWL (updated for incremental start; bodies enumerated from the system,
# change: instance-agnostic-config)
# ----------------------------------------------------------------------
def resolve_body_ids(root_url: str) -> list[str]:
    """The body IDs to crawl, enumerated from the OParl system's bodies
    collection (never constructed from a hardcoded ID — e.g. Dresden's
    IDs are zero-padded and a non-padded request fails with HTTP 500).

    The bodies collection URL is resolved spec-conformantly: from the
    system object's ``bodies`` link (the root may be the base URL as for
    Karlsruhe or the system URL itself as for Dresden). Falls back to
    ``{root}/bodies`` when the system object cannot be fetched.

    The instance config's ``oparl.bodies`` list optionally filters the
    discovered bodies (empty list = all). Raises RuntimeError when
    enumeration fails or yields no bodies: silently crawling a wrong body
    would poison the whole instance.
    """
    root = root_url.rstrip("/")
    bodies_url = None
    system_url = root if root.endswith("/system") else root + "/system"
    system = fetch_json(_with_limit(system_url))
    if isinstance(system, dict):
        # spec-conformant systems advertise "bodies"; some backends
        # (Dresden/SOMACOS) use the singular "body" for the collection
        bodies_url = system.get("bodies") or system.get("body")
    if not bodies_url:
        bodies_url = f"{root}/bodies"

    url = _with_limit(bodies_url)
    ids: list[str] = []
    while url:
        data = fetch_json(url)
        if not isinstance(data, dict):
            raise RuntimeError(f"bodies collection {url} returned no JSON object")
        for body in data.get("data", []) or []:
            bid = str(body.get("id") or "").rstrip("/").rsplit("/", 1)[-1]
            if bid:
                ids.append(bid)
        url = data.get("next")
        if url:
            url = _with_limit(url)
    if not ids:
        raise RuntimeError(
            f"no OParl bodies discovered under {bodies_url} — aborting "
            "(check the configured system_url; refusing to guess a body ID)")
    configured = _oparl().get("bodies") or []
    if configured:
        filtered = [b for b in ids if b in {str(x) for x in configured}]
        if not filtered:
            raise RuntimeError(
                f"configured bodies {configured} not among discovered bodies {ids}")
        return filtered
    return ids


# Collections crawled under each body. Every collection is requested
# with a timestamp filter (modified_since first, created_since fallback);
# endpoints that provably ignore the filter fall back to a full fetch.
# OParl 1.1 update mechanism: the filtered collections are the ONLY
# source of changed objects — all entity types Karlsruhe exposes are
# covered here, so resource references inside items need not be
# dereferenced during updates (see _is_followable).
COLLECTIONS = [
    "consultations",
    "papers",
    "agendaItems",
    "meetings",
    "people",
    "files",
    "memberships",
    "organizations",
    "locations",
]

# Filter parameters tried in order — NOTE the underscore spelling from the
# OParl 1.1 spec ("modified_since"); Karlsruhe silently ignores the
# camelCase variant that earlier versions of this crawler used, and it
# rejects future-dated baselines with HTTP 401 (so no future-baseline
# probing is possible). Instead, every collection page is validated while
# it is processed: an honouring filter can never return an item older than
# the baseline. Pages are sorted newest-first, so a silently ignored filter
# is detected as soon as the walk reaches items older than the baseline.
FILTER_PARAMS = ["modified_since", "created_since"]

# Karlsruhe accepts large page sizes: 1000 items/page instead of the
# default 10 (verified live; the syndication project uses the same).
# The live value comes from the instance config (oparl.page_limit).
def _page_limit() -> int:
    """Page size from the instance config (oparl.page_limit)."""
    return int(_oparl().get("page_limit", 1000))

MODE_FULL = "full"


def _normalise_ts(ts: datetime) -> datetime:
    """Normalise to a naive UTC datetime for comparisons."""
    if ts.tzinfo is not None:
        return ts.astimezone(timezone.utc).replace(tzinfo=None)
    return ts


def _with_limit(url: str) -> str:
    """Ensure *url* requests the configured page size (see _page_limit)."""
    if "limit=" in url:
        return url
    return url + ("&" if "?" in url else "?") + f"limit={_page_limit()}"


def _param_of(url: str) -> str | None:
    """The timestamp filter parameter used by *url*, if any."""
    for param in FILTER_PARAMS:
        if f"{param}=" in url:
            return param
    return None


def _page_filter_ok(data, baseline: datetime, param: str) -> bool:
    """Validate one collection page against the filter baseline.

    An honouring endpoint cannot return an item whose timestamp is older
    than the baseline — if it does, the filter was silently ignored (this
    is how the camelCase ``modifiedSince`` variant behaves). Items without
    the filtered timestamp field are ignored by the check.
    """
    field = {"modified_since": "modified", "created_since": "created"}.get(param, param)
    items = data.get("data", []) if isinstance(data, dict) else data if isinstance(data, list) else []
    baseline = _normalise_ts(baseline)
    for item in items:
        if not isinstance(item, dict):
            continue
        val = item.get(field)
        if not isinstance(val, str):
            continue
        try:
            if _normalise_ts(iso_to_dt(val)) < baseline:
                return False
        except Exception:
            continue
    return True


def _is_followable(url: str) -> bool:
    """Whether *url* is worth fetching during an incremental crawl.

    Followed: pagination links (``page=``) and PDF downloads. Everything
    else (plain resource references) is skipped — all entity types are
    covered by the filtered collections (see COLLECTIONS).
    """
    if url.lower().endswith(".pdf"):
        return True
    if "page=" in url:
        return True
    return False


def crawl_oparl(root_url: str, start_from: str, recorder=None,
                finalise: bool = True):
    """Breadth‑first crawl of the OParl system starting from ``start_from``.

    ``start_from`` is an ISO‑8601 timestamp used to request only resources that
    have been created or modified after that moment. Every collection in
    ``COLLECTIONS`` is requested with ``modified_since`` first. Whether the
    endpoint honours the parameter is validated on every fetched collection
    page: an honouring filter cannot return items older than the baseline
    (listings are sorted newest-first, so a silently ignored filter is
    detected as soon as the walk reaches older items). On detection the
    crawler falls back — first to ``created_since``, then to a full fetch
    (recorded via ``recorder.record_full_fetch``). Per the OParl 1.1 update
    mechanism, only the filtered collections, their pagination and PDF
    downloads are fetched — resource references are not dereferenced. The
    function continues even when individual requests fail.

    When *recorder* is given, every new or modified resource is logged.
    With ``finalise=False`` (used by the combined sync entry point) the run
    row is NOT finished here — the caller is responsible for finalising it
    after the import phase.
    """
    visited = set()
    _configure_logging()
    baseline_dt = iso_to_dt(start_from)
    capabilities: dict[tuple[str, str], str] = {}  # (body, collection) -> decided mode

    body_ids = resolve_body_ids(root_url)
    logging.info(
        "Crawling %d OParl body(ies): %s", len(body_ids), ", ".join(body_ids)
    )

    def collection_url(collection: str, param: str | None = None,
                       body_id: str | None = None) -> str:
        url = f"{root_url}/bodies/{body_id or body_ids[0]}/{collection}"
        if param:
            url += f"?{param}=" + quote(start_from, safe='')
        return _with_limit(url)

    def collection_of(url: str) -> str | None:
        """The collection a (first-page or pagination) URL belongs to.

        Matches ``/<collection>?`` at a path boundary so both first-page
        URLs and server-generated pagination links (which may use shorter
        or relative path shapes) are recognised.
        """
        for collection in COLLECTIONS:
            if re.search(rf"/{collection}\?", url):
                return collection
        return None

    queue = deque()
    for bid in body_ids:
        queue.append(f"{root_url}/bodies/{bid}?created_since=" + quote(start_from, safe=''))
    for bid in body_ids:
        for collection in COLLECTIONS:
            queue.append(collection_url(collection, FILTER_PARAMS[0], body_id=bid))

    # Keep the latest timestamp seen during this run – start with the provided
    # baseline so that we only ever move forward.
    # Normalise the baseline to naive UTC: resources carry mixed offsets
    # ("Z" vs "+02:00") and their timestamps are normalised below, so an
    # offset-aware baseline (e.g. "2026-02-19T00:00:00+01:00" from the
    # tracking table) would raise on comparison.
    latest_ts = _normalise_ts(baseline_dt)
    if recorder is not None:
        recorder.start(start_from)

    while queue:
        current_url = queue.popleft()
        if current_url in visited:
            continue
        visited.add(current_url)

        # PDF handling
        if current_url.lower().endswith('.pdf'):
            logging.info("Saving PDF URL: %s", current_url)
            pdf_path = os.path.join(
                OUTPUT_PDF_FOLDER,
                sanitize_filename(current_url.split('/')[-1])
            )
            if os.path.exists(pdf_path):
                logging.info("Skipping existing PDF: %s", pdf_path)
                continue

            pdf_data = fetch_pdf(current_url)
            if pdf_data:
                if not os.path.exists(OUTPUT_PDF_FOLDER):
                    os.makedirs(OUTPUT_PDF_FOLDER)
                try:
                    with open(pdf_path, 'wb') as f:
                        f.write(pdf_data)
                except IOError as e:
                    logging.error("Could not write PDF for %s: %s", current_url, e)
            continue

        # JSON resources
        data = fetch_json(current_url)

        # Filter validation on collection pages: a page carrying a filter
        # parameter must not contain items older than the baseline.
        collection = collection_of(current_url)
        attempted = _param_of(current_url)
        body_match = re.search(r"/bodies/([^/?]+)/", current_url)
        page_body = body_match.group(1) if body_match else (body_ids[0] if body_ids else None)
        cap_key = (page_body, collection) if page_body else collection
        if collection is not None and attempted is not None \
                and capabilities.get(cap_key) != MODE_FULL and data:
            if not _page_filter_ok(data, baseline_dt, attempted):
                idx = FILTER_PARAMS.index(attempted)
                next_param = FILTER_PARAMS[idx + 1] if idx + 1 < len(FILTER_PARAMS) else None
                if next_param:
                    logging.warning(
                        "Collection %s ignores %s (page contains items older "
                        "than the baseline); falling back to %s",
                        collection, attempted, next_param,
                    )
                    capabilities[cap_key] = next_param
                    queue.appendleft(collection_url(collection, next_param,
                                                    body_id=page_body))
                    continue
                logging.warning(
                    "Collection %s ignores all timestamp filters; fetching in full",
                    collection,
                )
                capabilities[cap_key] = MODE_FULL
                if recorder is not None:
                    recorder.record_full_fetch(collection)
                # fall through: this page is part of the full listing

        if not data:
            logging.warning("No data for %s; skipping.", current_url)
            if recorder is not None:
                recorder.record_error()
            continue

        sub_links = process_resource(data, current_url, recorder=recorder)

        # Extract timestamp safely – ``get_resource_timestamp`` returns a datetime
        # for both dicts and list fallbacks. Normalise to naive UTC: resources
        # carry mixed offsets (``Z`` vs ``+02:00``) and ``latest_ts`` (from the
        # baseline) is naive, so an aware timestamp would raise on comparison.
        try:
            ts_dt = get_resource_timestamp(data)
            ts_dt = _normalise_ts(ts_dt)
            if ts_dt > latest_ts:
                latest_ts = ts_dt
        except Exception as e:
            logging.error("Failed to extract timestamp from %s: %s", current_url, e)

        # OParl 1.1 update mechanism: the filtered collections (and their
        # pagination) are the sole source of changed objects. Plain
        # resource references inside items are already on disk and in the
        # DB — dereferencing them re-validated the whole graph on every
        # incremental run (~170k fetches). Only pagination links and PDF
        # downloads are followed.
        skipped_refs = 0
        for link in sub_links:
            if link in visited:
                continue
            if _is_followable(link):
                # pagination links get the large page size; PDFs must stay
                # untouched (the .pdf suffix drives the download branch)
                queue.append(link if link.lower().endswith(".pdf") else _with_limit(link))
            else:
                skipped_refs += 1
        if skipped_refs:
            logging.debug("Skipped %d resource references from %s", skipped_refs, current_url)

    logging.info("Collection filter capabilities: %s", capabilities)

    # The tracking table is the source of truth for the next run baseline.
    if recorder is not None:
        recorder.set_end_state(latest_ts.isoformat())
        if finalise:
            recorder.finish(success=True)

# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------
def main():
    """Entry point for the incremental OParl crawl.

    Resolves the crawl baseline (``--last-date`` override > latest row in
    the tracking table > epoch), records the run in the database, and invokes
    ``crawl_oparl``. A ``KeyboardInterrupt`` (Ctrl‑C) is caught to allow a
    graceful shutdown – the run is recorded with ``success=false`` and the
    items collected so far. ``last_run.txt`` is ignored completely.
    """
    import argparse
    from src.oparlRunLog import RunRecorder, resolve_baseline

    global OUTPUT_FOLDER, OUTPUT_PDF_FOLDER
    parser = argparse.ArgumentParser(description="Incremental OParl crawler (instance-configurable).")
    parser.add_argument("--system-url", default=None, help="Base URL of the OParl system (default: instance config, Karlsruhe: %(default)s)")
    parser.add_argument("--output-folder", default=None, help="Folder to save JSON files (default: instance config)")
    parser.add_argument("--output-pdf-folder", default=None, help="Folder to save PDF files (default: instance config)")
    parser.add_argument("--last-date", default=None, help="ISO timestamp overriding the tracked baseline (default: latest tracked run)")
    args = parser.parse_args()
    # resolution order: CLI flag > instance config (env > file > default)
    SYSTEM_URL = args.system_url or _oparl()["system_url"]
    OUTPUT_FOLDER = args.output_folder or _paths()["json_dir"]
    OUTPUT_PDF_FOLDER = args.output_pdf_folder or _paths()["pdf_dir"]
    _configure_logging()

    logging.info("Starting OParl incremental crawl at %s", SYSTEM_URL)

    recorder = RunRecorder()
    if args.last_date:
        last_ts = args.last_date
        baseline_source = "--last-date override"
    else:
        last_ts, baseline_source = resolve_baseline(engine=recorder._engine)
    logging.info("Crawl baseline (%s): %s", baseline_source, last_ts)

    success = True
    try:
        crawl_oparl(SYSTEM_URL, last_ts, recorder=recorder)
    except KeyboardInterrupt:
        success = False
        logging.warning("Crawl interrupted by user (Ctrl‑C). Recording partial run and exiting.")
    except Exception as ex:
        success = False
        logging.exception("Unexpected error during crawl: %s", ex)
    finally:
        if success and recorder.available and recorder.run_id is not None:
            # normal path: crawl_oparl already finished the run
            pass
        else:
            recorder.finish(success=success)
        if not recorder.available:
            logging.error(
                "Run tracking was unavailable (%s); the baseline for the next "
                "crawl could NOT be advanced in the tracking table.",
                recorder.last_error,
            )
        logging.info("Done! JSON → %s, PDFs → %s", OUTPUT_FOLDER, OUTPUT_PDF_FOLDER)

if __name__ == "__main__":
    main()
