import os
import re
import json
import csv
from typing import List, Dict, Any

# Folder containing the JSON files from your OParl crawler
CRAWL_FOLDER = "ko"

# Which file extensions to look for in URLs
SUPPORTED_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv"}

# CSV file to store the output
OUTPUT_CSV = "file_references.csv"


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

def parse_year_from_data(data: dict) -> str:
    """
    Look for typical OParl date fields (e.g. 'startDate', 'created', 'modified', 'date').
    Extract the 4-digit year from something like '2024-07-23T...' or '2023-05-01'.
    Return 'Unknown' if none found.
    """
    possible_date_fields = ["startDate", "date", "created", "modified"]
    year_pattern = re.compile(r"(\d{4})-\d{2}-\d{2}")
    for field in possible_date_fields:
        val = data.get(field)
        if isinstance(val, str):
            match = year_pattern.search(val)
            if match:
                return match.group(1)  # e.g. "2024"
    return "Unknown"


def guess_file_extension(url_or_name: str) -> str:
    """
    Return the lowercase extension of a filename or URL if it's in SUPPORTED_EXTENSIONS,
    otherwise the extension if it matches a known pattern, else "".
    Example: "https://example.com/docs/something.pdf" -> ".pdf"
    """
    url_or_name = url_or_name.lower()
    # You might have query strings (e.g. ?x=1). Let's strip them:
    # e.g. "https://example.com/abc.pdf?x=1" -> "abc.pdf"
    main_part = url_or_name.split("?", 1)[0]
    _, ext = os.path.splitext(main_part)
    return ext


def extract_file_references_in_dict(
    data: dict, 
    source_json: str, 
    results: List[Dict[str, str]]
):
    """
    Recursively walk a dict, looking for strings that end in .pdf, .doc, .docx, etc.
    Also look for 'fileName' fields. Then gather info about year, etc.
    Append to 'results' as we find them.
    """
    # We'll parse year from the top-level object if it has typical date fields.
    # For nested references, you can adapt how the year is derived.
    resource_year = parse_year_from_data(data)

    for key, value in data.items():
        if isinstance(value, str):
            # If the string looks like a file link (ends with supported extension)
            # or is something like "downloadUrl", "accessUrl" with a known extension
            ext = guess_file_extension(value)
            if ext in SUPPORTED_EXTENSIONS:
                # For the fileName, we might find it in the same dict
                # or default to the last part of the URL
                file_name = data.get("fileName")
                if not file_name:
                    # fallback: last path segment from the URL
                    file_name = os.path.basename(value.split("?", 1)[0])
                
                # If extension isn't recognized in the file_name, we might unify them
                # But let's keep it straightforward
                resource_type = ext.lstrip(".")  # e.g. "pdf", "doc"
                
                results.append({
                    "resource_url": value,
                    "resource_filename": file_name,
                    "source_json": source_json,
                    "file_type": resource_type,
                    "year": resource_year
                })

        elif isinstance(value, dict):
            # Recurse
            extract_file_references_in_dict(value, source_json, results)
        elif isinstance(value, list):
            # Recurse into each element
            for item in value:
                if isinstance(item, dict):
                    extract_file_references_in_dict(item, source_json, results)
                elif isinstance(item, str):
                    # If strings in a list might also be direct file references
                    ext = guess_file_extension(item)
                    if ext in SUPPORTED_EXTENSIONS:
                        file_name = os.path.basename(item.split("?", 1)[0])
                        resource_type = ext.lstrip(".")
                        results.append({
                            "resource_url": fix_karlsruhe_url(item),
                            "resource_filename": file_name,
                            "source_json": source_json,
                            "file_type": resource_type,
                            "year": resource_year
                        })


def extract_file_references_in_json_file(
    json_path: str, 
    results: List[Dict[str, str]]
):
    """
    Load a JSON file (could be a dict or list) and find references
    to well-known file formats. Append to 'results'.
    """
    with open(json_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            # skip invalid JSON files
            return
    
    # data might be dict or list
    if isinstance(data, dict):
        extract_file_references_in_dict(data, os.path.basename(json_path), results)
    elif isinstance(data, list):
        # We'll parse each dict in the list
        for item in data:
            if isinstance(item, dict):
                extract_file_references_in_dict(item, os.path.basename(json_path), results)


def main():
    # 1) Gather all JSON files in CRAWL_FOLDER
    json_files = []
    for root, dirs, files in os.walk(CRAWL_FOLDER):
        for filename in files:
            if filename.lower().endswith(".json"):
                json_files.append(os.path.join(root, filename))

    # 2) Extract references
    results = []  # Will hold dicts like {resource_url, resource_filename, source_json, file_type, year}

    for json_path in json_files:
        extract_file_references_in_json_file(json_path, results)

    # 3) Write results to a CSV (or JSON) for easy consumption
    # CSV columns: resource_url, resource_filename, source_json, file_type, year
    fieldnames = ["resource_url", "resource_filename", "source_json", "file_type", "year"]
    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow(row)

    print(f"[INFO] Found {len(results)} file references in {len(json_files)} JSON files.")
    print(f"[INFO] Wrote output to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()


    """
    How It Works

    Walk the karlsruhe_oparl_crawl folder
        We collect a list of all .json files (which your crawler previously saved).

    Load each JSON
        Some JSON files are dict (single resource), others might be list (multiple resources).
        We parse them with json.load. If it fails (JSONDecodeError), we skip that file.

    extract_file_references_in_dict
        Recursively traverses the JSON structure. Whenever it encounters a string that ends with .pdf, .doc, etc., it builds a record with:
            resource_url: the full URL (e.g. https://web1.karlsruhe.de/ris/oparl/bodies/0001/downloadfiles/00647355.pdf).
            resource_filename: from the JSON’s "fileName" if present, else fallback to the last path segment of the URL ("00647355.pdf").
            source_json: the name of the JSON file where we found the reference (e.g. File_2023-05-17_647355.json).
            file_type: the extension (e.g. pdf, doc, csv).
            year: derived from typical date fields in the same object. If none found, it’s "Unknown".

    Write to CSV
        We produce a single CSV (file_references.csv) with columns:
            resource_url
            resource_filename
            source_json
            file_type
            year

You can then open this CSV in Excel or any other tool to see all extracted file references.
Customizing

    Supported Formats: Adjust SUPPORTED_EXTENSIONS to include or remove file endings.
    Date Fields: If your data uses different date fields, add them to parse_year_from_data.
    Year Extraction: Right now we just parse the year from a string like "2025-01-07T...". If you have a different format, tweak the regex or parse logic.
    Storing in JSON: If you prefer a JSON output instead of CSV, replace the CSV logic with json.dump(results, f, indent=2, ensure_ascii=False).

By running this script after your main crawler, you’ll end up with a list of all references to PDF/DOC/CSV/etc. files in the OParl data, along with which JSON resource object they came from.

    """

