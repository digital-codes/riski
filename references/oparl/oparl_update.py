import os
import re
import json
import hashlib
import logging
import requests
from collections import deque
from urllib.parse import urlparse, urlunparse
from datetime import datetime
from urllib.parse import quote

##############################################################################
# CONFIGURATION
##############################################################################

SYSTEM_URL = "https://web1.karlsruhe.de/ris/oparl"
OUTPUT_FOLDER = "ko_update"
OUTPUT_PDF_FOLDER = "ko_update_pdf"
LOG_FILENAME = "ko_update_crawl.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILENAME, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

##############################################################################
# KARLSRUHE URL FIXES
##############################################################################

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
    """
    Recursively fix all strings that are Karlsruhe URLs missing '/ris/'.
    Modifies 'data' in place.
    """
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

##############################################################################
# FILENAME AND SAVING
##############################################################################

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
        # Attempt to parse something meaningful.
        # e.g. 'type': 'https://schema.oparl.org/1.1/Meeting'
        resource_type = parse_resource_type(data)  # "Meeting", "Paper", ...
        resource_id = parse_resource_id(data)       # "1234"
        resource_date = parse_resource_date(data)   # "2024-07-23"

        # If we got a type or id, build a name
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

##############################################################################
# FETCH, LINK EXTRACTION, AND CRAWL
##############################################################################

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

        data = resp.json()  # can be a dict or a list
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
    """
    Save the resource to file, then extract and return sub-links.
    'data' can be a dict or a list.
    """
    # 1) Save to file
    save_json(data, url)

    # 2) Extract sub-links from the entire data (dict or list)
    return extract_links(data)

def crawl_oparl(root_url: str, start_from: str = None):
    """
    BFS crawl of the OParl system. 
    - Keep track of visited URLs
    - For each URL, fetch JSON (dict or list), process, and queue sub-links
    - Continue even if errors occur
    """
    if not start_from:
        raise ValueError("start_from is None, but this function requires a start_from value.")

    visited = set()
    queue = deque([root_url + "/bodies/0001?createdSince=" + start_from])
    queue = deque([root_url + "/bodies/0001/consultations?createdSince=" + start_from])
    queue = deque([root_url + "/bodies/0001/papers?createdSince=" + start_from])
    queue = deque([root_url + "/bodies/0001/agendaItems?createdSince=" + start_from])


    while queue:
        current_url = queue.popleft()
        if current_url in visited:
            continue

        visited.add(current_url)
        print(f"Processing: {current_url}")

        if current_url.lower().endswith(".pdf"):
            logging.info("Saving PDF URL: %s", current_url)
            pdf_data = fetch_pdf(current_url)
            try:
                with open(os.path.join(OUTPUT_PDF_FOLDER, sanitize_filename(current_url.split("/")[-1])), "wb") as f:
                    f.write(pdf_data)
            except IOError as e:
                logging.error("Could not write PDF for %s: %s", current_url, e)
            except TypeError as e:
                logging.error("No PDF data for %s: %s", current_url, e)
            continue
        else:
            data = fetch_json(current_url)
            if not data:
                logging.warning("No data for %s; skipping.", current_url)
                continue
            # data could be a dict or a list
            sub_links = process_resource(data, current_url)
            for link in sub_links:
                if link not in visited:
                    queue.append(link)

##############################################################################
# MAIN
##############################################################################

def main():
    logging.info("Starting OParl crawl at root: %s", SYSTEM_URL)

    with open("ko_crawl.log") as f:
        start_from = f.readline().strip().split(",")[0]  # Get the last URL from the log
        # Format current time as ISO 8601 with URL encoding
        encoded_time = quote(start_from.replace(" ", "T"), safe='')
        print(f"Resuming crawl from: {start_from}")
        

    try:
        crawl_oparl(SYSTEM_URL,start_from)
    except Exception as ex:
        logging.exception("Unexpected error during crawl: %s", ex)

    logging.info("Done! Check '%s' folder for all downloaded JSON; logs in '%s'.",
                 OUTPUT_FOLDER, LOG_FILENAME)

if __name__ == "__main__":
    main()


