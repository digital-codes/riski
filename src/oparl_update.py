# references/oparl/oparl_update.py
import os
import re
import json
import hashlib
import logging
import requests
from collections import deque
from urllib.parse import urlparse, urlunparse, quote
from datetime import datetime

# ----------------------------------------------------------------------
# CONFIGURATION
# ----------------------------------------------------------------------
SYSTEM_URL = "https://web1.karlsruhe.de/ris/oparl"
# use same folders as initial fetch to allow overwriting with updated data; unchanged resources will be skipped
OUTPUT_FOLDER = "/mnt_ai/data/odd26/ris/ko"
OUTPUT_PDF_FOLDER = "/mnt_ai/data/odd26/ris/ko_pdf"
LOG_FILENAME = "ko_update_crawl.log"
LAST_RUN_FILE = "last_run.txt"          # stores the most recent ISO‑timestamp

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
def load_last_run() -> str:
    """Read the stored timestamp from ``LAST_RUN_FILE``.

    Returns an ISO‑8601 string. If the file does not exist, the epoch
    ``1970-01-01T00:00:00Z`` is returned so that the first crawl fetches all
    resources.
    """
    if not os.path.exists(LAST_RUN_FILE):
        return "1970-01-01T00:00:00Z"
    with open(LAST_RUN_FILE, "r", encoding="utf-8") as f:
        return f.readline().strip() or "1970-01-01T00:00:00Z"

def save_last_run(ts: str):
    """Persist the newest timestamp processed to ``LAST_RUN_FILE``.

    ``ts`` must be an ISO‑8601 string. The file is overwritten each time, so the
    crawl always starts from the most recent successful timestamp.
    """
    with open(LAST_RUN_FILE, "w", encoding="utf-8") as f:
        f.write(ts + "\n")

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
def fetch_json(url: str):
    """
    Fetch JSON from a URL. Catch network/HTTP errors and JSON decode errors.
    Fix all embedded Karlsruhe URLs. Return either a dict or a list (or empty).
    """
    fixed_url = fix_karlsruhe_url(url)
    try:
        logging.info("Fetching: %s", fixed_url)
        resp = requests.get(fixed_url, timeout=15)
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
        resp = requests.get(fixed_url, timeout=15)
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

def process_resource(data, url: str) -> list:
    if should_save(data, url):
        save_json(data, url)
    else:
        logging.info("Skipping unchanged resource: %s", url)
    return extract_links(data)

# ----------------------------------------------------------------------
# CRAWL (updated for incremental start)
# ----------------------------------------------------------------------
def crawl_oparl(root_url: str, start_from: str):
    """Breadth‑first crawl of the OParl system starting from ``start_from``.

    ``start_from`` is an ISO‑8601 timestamp used to request only resources that
    have been created or modified after that moment. The function respects the
    same pagination mechanism as the original fetch script and continues even
    when individual requests fail.
    """
    visited = set()
    collections = [
        "bodies/0001/consultations",
        "bodies/0001/papers",
        "bodies/0001/agendaItems",
        "bodies/0001?createdSince=" + quote(start_from, safe='')
    ]
    queue = deque([f"{root_url}/{c}" for c in collections])

    # Keep the latest timestamp seen during this run – start with the provided
    # baseline so that we only ever move forward.
    latest_ts = iso_to_dt(start_from)

    while queue:
        current_url = queue.popleft()
        if current_url in visited:
            continue
        visited.add(current_url)

        # PDF handling – unchanged from original script
        if current_url.lower().endswith('.pdf'):
            logging.info("Saving PDF URL: %s", current_url)
            pdf_data = fetch_pdf(current_url)
            if pdf_data:
                if not os.path.exists(OUTPUT_PDF_FOLDER):
                    os.makedirs(OUTPUT_PDF_FOLDER)
                pdf_path = os.path.join(
                    OUTPUT_PDF_FOLDER,
                    sanitize_filename(current_url.split('/')[-1])
                )
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
            continue

        sub_links = process_resource(data, current_url)

        # Extract timestamp safely – ``get_resource_timestamp`` returns a datetime
        # for both dicts and list fallbacks.
        try:
            ts_dt = get_resource_timestamp(data)
            if ts_dt > latest_ts:
                latest_ts = ts_dt
        except Exception as e:
            logging.error("Failed to extract timestamp from %s: %s", current_url, e)

        for link in sub_links:
            if link not in visited:
                queue.append(link)

    # Persist the newest timestamp after the crawl finishes.
    save_last_run(latest_ts.isoformat())

# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------
def main():
    """Entry point for the incremental OParl crawl.

    Sets up logging, loads the last run timestamp, and invokes ``crawl_oparl``.
    A ``KeyboardInterrupt`` (Ctrl‑C) is caught to allow a graceful shutdown – the
    latest processed timestamp is still persisted before exiting.
    """
    logging.info("Starting OParl incremental crawl at %s", SYSTEM_URL)
    last_ts = load_last_run()
    logging.info("Last run timestamp: %s", last_ts)
    try:
        crawl_oparl(SYSTEM_URL, last_ts)
    except KeyboardInterrupt:
        logging.warning("Crawl interrupted by user (Ctrl‑C). Saving progress and exiting.")
    except Exception as ex:
        logging.exception("Unexpected error during crawl: %s", ex)
    finally:
        # Ensure the latest timestamp is saved (crawl_oparl already does this,
        # but we call it again to be safe in case of early interruption.)
        try:
            # ``load_last_run`` returns the timestamp we persisted before; if the
            # crawl was interrupted before any update, this is a no‑op.
            latest = load_last_run()
            logging.info("Final timestamp stored: %s", latest)
        except Exception:
            pass
        logging.info("Done! JSON → %s, PDFs → %s, last timestamp saved to %s",
                     OUTPUT_FOLDER, OUTPUT_PDF_FOLDER, LAST_RUN_FILE)

if __name__ == "__main__":
    main()
