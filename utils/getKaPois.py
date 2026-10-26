#!/usr/bin/env python3
"""
Fetch all group names from the Karlsruhe Kultur POI layer and
save each group’s features as a separate GeoJSON file.

Requirements:
    pip install requests
"""

import json
import os
import sys
import requests

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
BASE_URL = (
    "https://geoportal.karlsruhe.de/ags04/rest/services/Hosted/"
    "Stadtplan_POIs_Kultur/FeatureServer/0/query"
)
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pois")

# ----------------------------------------------------------------------
# Helper – create a safe filename from a group name
# ----------------------------------------------------------------------
def safe_filename(name: str) -> str:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_/()")
    return "".join(ch if ch in allowed else "_" for ch in name)

# ----------------------------------------------------------------------
# Step 1 – get distinct group names
# ----------------------------------------------------------------------
def fetch_groups() -> list[str]:
    params = {
        "where": "1=1",                 # all records
        "outFields": "gruppenname_de",   # only the group field
        "returnDistinctValues": "true", # deduplicate
        "returnGeometry": "false",
        "f": "json",
    }
    r = requests.get(BASE_URL, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "features" not in data:
        raise RuntimeError("Unexpected response structure")
    return [f["attributes"]["gruppenname_de"] for f in data["features"]]

# ----------------------------------------------------------------------
# Step 2 – for each group, download its features as GeoJSON
# ----------------------------------------------------------------------
def download_group(group: str) -> None:
    where_clause = f"gruppenname_de='{group}'"
    params = {
        "where": where_clause,
        "outFields": "*",
        "returnGeometry": "true",
        "f": "geojson",
    }
    r = requests.get(BASE_URL, params=params, timeout=30)
    r.raise_for_status()

    filename = safe_filename(group) + ".geojson"
    path = os.path.join(OUT_DIR, filename)

    try:
        data = r.json()
    except Exception as e:
        print(f"Failed to parse JSON for group {group}: {e}")
        return

    with open(path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)

    print(f"Wrote {path}")

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    groups = fetch_groups()
    print("Found groups:", groups)

    for g in groups:
        download_group(g)

    print("All done.")


if __name__ == "__main__":
    main()
