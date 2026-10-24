
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
# CONFIGURATION
# ----------------------------------------------------------------------
SYSTEM_URL = "https://web1.karlsruhe.de/ris/oparl"
# use same folders as initial fetch to allow overwriting with updated data; unchanged resources will be skipped
OUTPUT_FOLDER = "/mnt_ai/data/odd26/ris/ko"
OUTPUT_PDF_FOLDER = "/mnt_ai/data/odd26/ris/ko_pdf"
LOG_FILENAME = "ko_update_crawl.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILENAME, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# ----------------------------------------------------------------------
# URL FIXES (unchanged)
# ----------------------------------------------------------------------
def fix_karlsruhe_url(url: str) -> str:
    """
    If the URL is on web1.karlsruhe.de but missing '/ris/' in the path,
    insert '/ris' at the start of the path.
    """
    if "web1.karlsruhe.de" in url.lower():
        parsed = urlparse(url)
        if "/ris/" not in parsed.path.lower():
            new_path = "/ris" + parsed.path
            fixed_url = urlunparse((
                parsed.scheme,
                parsed.netloc,
                new_path,
                parsed.params,
                parsed.query,
                parsed.fragment
            ))
            logging.warning(
                "Fixed Karlsruhe URL:\n  Original: %s\n  Fixed:    %s",
                url, fixed_url
            )
            return fixed_url
    return url

def fix_urls_in_data(data):
    """Recursively fix all Karlsruhe URLs in the supplied data structure."""
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, str) and v.startswith("http"):
                data[k] = fix_karlsruhe_url(v)
            elif isinstance(v, (dict, list)):
                fix_urls_in_data(v)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, str) and item.startswith("http"):
                data[i] = fix_karlsruhe_url(item)
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
REQUEST_DELAY = 0.25  # seconds between requests
MAX_RETRIES = 5       # 429 retries per request

_last_request_time = [0.0]


def _http_get(url: str, timeout: int = 15):
    """GET with politeness delay and 429/Retry-After handling.

    Honours the server's ``Retry-After`` header (exponential back-off up
    to 60 s otherwise). Raises ``requests.HTTPError`` on persistent 429s;
    other HTTP/network errors are left to the caller.
    """
    since = time.monotonic() - _last_request_time[0]
    if 0.0 <= since < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - since)
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
# CRAWL (updated for incremental start)
# ----------------------------------------------------------------------
# Collections crawled under bodies/0001. Every collection is requested
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
# camelCase variant that earlier versions of this crawler used.
FILTER_PARAMS = ["modified_since", "created_since"]

# Karlsruhe accepts large page sizes: 1000 items/page instead of the
# default 10 (verified live; the syndication project uses the same).
PAGE_LIMIT = 1000

# Capability probe: a filter applied to a future baseline must return an
# EMPTY listing. A non-empty listing proves the parameter is ignored
# (listings are sorted newest-first, so a single real page cannot
# distinguish honoured from ignored).
PROBE_MARGIN = timedelta(days=1)

MODE_FULL = "full"


def _normalise_ts(ts: datetime) -> datetime:
    """Normalise to a naive UTC datetime for comparisons."""
    if ts.tzinfo is not None:
        return ts.astimezone(timezone.utc).replace(tzinfo=None)
    return ts


def _with_limit(url: str) -> str:
    """Ensure *url* requests the large page size (see PAGE_LIMIT)."""
    if "limit=" in url:
        return url
    return url + ("&" if "?" in url else "?") + f"limit={PAGE_LIMIT}"


def _probe_filter(collection_url: str, param: str, now: datetime | None = None) -> str:
    """Probe whether the endpoint honours *param* (``modified_since`` etc.).

    Requests the collection with a future baseline: an honouring endpoint
    must return an empty listing, a non-empty listing proves the parameter
    is ignored. Returns ``"supported"``, ``"ignored"`` or ``"error"``.
    """
    probe_ts = (now or datetime.now(timezone.utc)) + PROBE_MARGIN
    data = fetch_json(f"{collection_url}?{param}={quote(probe_ts.isoformat(), safe='')}&limit={PAGE_LIMIT}")
    if not data:
        return "error"
    return "ignored" if data.get("data") else "supported"


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
    ``COLLECTIONS`` is requested with ``modified_since`` first; whether the
    endpoint honours the parameter is decided per collection via a
    future-baseline probe (an honouring endpoint returns an empty listing
    for a future timestamp — listings are sorted newest-first, so real
    pages cannot be used for this check). If the parameter is ignored or
    rejected, ``created_since`` is tried, and as a last resort the
    collection is fetched in full (with the fallback recorded via
    ``recorder.record_full_fetch``). Per the OParl 1.1 update mechanism,
    only the filtered collections, their pagination and PDF downloads are
    fetched — resource references are not dereferenced. The function
    continues even when individual requests fail.

    When *recorder* is given, every new or modified resource is logged.
    With ``finalise=False`` (used by the combined sync entry point) the run
    row is NOT finished here — the caller is responsible for finalising it
    after the import phase.
    """
    visited = set()
    baseline_dt = iso_to_dt(start_from)
    capabilities: dict[str, str] = {}  # collection type -> decided mode

    def collection_url(collection: str, param: str | None = None) -> str:
        url = f"{root_url}/bodies/0001/{collection}"
        if param:
            url += f"?{param}=" + quote(start_from, safe='')
        return _with_limit(url)

    # Decide the filter capability per collection up front via the probe.
    queue = deque([f"{root_url}/bodies/0001?created_since=" + quote(start_from, safe='')])
    for collection in COLLECTIONS:
        mode = None
        for param in FILTER_PARAMS:
            probe = _probe_filter(f"{root_url}/bodies/0001/{collection}", param)
            if probe == "supported":
                mode = param
                break
            if probe == "ignored":
                logging.warning(
                    "Collection %s ignores %s (probe returned items for a "
                    "future baseline)", collection, param,
                )
            else:
                logging.warning(
                    "Collection %s rejected %s (HTTP error)", collection, param,
                )
        if mode is None:
            mode = MODE_FULL
            logging.warning(
                "Collection %s supports no timestamp filter; fetching in full",
                collection,
            )
            if recorder is not None:
                recorder.record_full_fetch(collection)
        capabilities[collection] = mode
        queue.append(collection_url(collection, mode if mode != MODE_FULL else None))

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

    global SYSTEM_URL, OUTPUT_FOLDER, OUTPUT_PDF_FOLDER
    parser = argparse.ArgumentParser(description="Incremental OParl crawler for Karlsruhe RIS.")
    parser.add_argument("--system-url", default=SYSTEM_URL, help="Base URL of the OParl system (default: %(default)s)")
    parser.add_argument("--output-folder", default=OUTPUT_FOLDER, help="Folder to save JSON files (default: %(default)s)")
    parser.add_argument("--output-pdf-folder", default=OUTPUT_PDF_FOLDER, help="Folder to save PDF files (default: %(default)s)")
    parser.add_argument("--last-date", default=None, help="ISO timestamp overriding the tracked baseline (default: latest tracked run)")
    args = parser.parse_args()
    SYSTEM_URL = args.system_url
    OUTPUT_FOLDER = args.output_folder
    OUTPUT_PDF_FOLDER = args.output_pdf_folder

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
