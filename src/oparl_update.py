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
OUTPUT_FOLDER = "ko_update"
OUTPUT_PDF_FOLDER = "ko_update_pdf"
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
    """Insert missing '/ris' into Karlsruhe URLs."""
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
    return re.sub(r"[^A-Za-z0-9._-]", "_", filename)

def hash_filename_from_url(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest() + ".json"

def generate_descriptive_filename(data, url) -> str:
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
    return hash_filename_from_url(url)

def parse_resource_type(data: dict) -> str:
    t = data.get("type", "")
    if t.startswith("http"):
        return t.rstrip("/").split("/")[-1]
    return "Unknown"

def parse_resource_id(data: dict) -> str:
    rid = data.get("id", "")
    if rid.startswith("http"):
        return rid.rstrip("/").split("/")[-1]
    return ""

def parse_resource_date(data: dict) -> str:
    for field in ["startDate", "date", "modified", "created"]:
        val = data.get(field)
        if isinstance(val, str) and len(val) >= 10:
            return val[:10]
    return ""

def save_json(data, url: str):
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
    if not os.path.exists(LAST_RUN_FILE):
        return "1970-01-01T00:00:00Z"
    with open(LAST_RUN_FILE, "r", encoding="utf-8") as f:
        return f.readline().strip() or "1970-01-01T00:00:00Z"

def save_last_run(ts: str):
    with open(LAST_RUN_FILE, "w", encoding="utf-8") as f:
        f.write(ts + "\n")

def iso_to_dt(iso: str) -> datetime:
    iso = iso.rstrip("Z")
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S")

def get_resource_timestamp(data: dict) -> datetime:
    for field in ["modified", "created", "date", "startDate"]:
        val = data.get(field)
        if isinstance(val, str):
            return iso_to_dt(val)
    return datetime.utcnow()

def should_save(data: dict, url: str) -> bool:
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
    visited = set()
    collections = [
        "bodies/0001/consultations",
        "bodies/0001/papers",
        "bodies/0001/agendaItems",
        "bodies/0001?createdSince=" + quote(start_from, safe='')
    ]
    queue = deque([f"{root_url}/{c}" for c in collections])
    while queue:
        current_url = queue.popleft()
        if current_url in visited:
            continue
        visited.add(current_url)
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
        data = fetch_json(current_url)
        if not data:
            logging.warning("No data for %s; skipping.", current_url)
            continue
        sub_links = process_resource(data, current_url)
        ts = get_resource_timestamp(data).isoformat()
        if ts > load_last_run():
            save_last_run(ts)
        for link in sub_links:
            if link not in visited:
                queue.append(link)

# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------
def main():
    logging.info("Starting OParl incremental crawl at %s", SYSTEM_URL)
    last_ts = load_last_run()
    logging.info("Last run timestamp: %s", last_ts)
    try:
        crawl_oparl(SYSTEM_URL, last_ts)
    except Exception as ex:
        logging.exception("Unexpected error during crawl: %s", ex)
    logging.info("Done! JSON → %s, PDFs → %s, last timestamp saved to %s",
                 OUTPUT_FOLDER, OUTPUT_PDF_FOLDER, LAST_RUN_FILE)

if __name__ == "__main__":
    main()
