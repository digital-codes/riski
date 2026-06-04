#!/usr/bin/env python3
import argparse
import json
import sys
import time
from pathlib import Path
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

import requests
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError, GeocoderUnavailable

# ==============================================================================
# CONFIGURATION - UPDATE THIS BEFORE RUNNING
# ==============================================================================
USER_EMAIL = "info@digital-codes.de" 
USER_AGENT = f"RIS-Geo/1.0 ({USER_EMAIL})"

NOMINATIM_TIMEOUT = 15
NOMINATIM_RETRY_COUNT = 3
RATE_LIMIT_DELAY = 1.5
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# ==============================================================================

def validate_config():
    if "your-actual-email" in USER_EMAIL or "@" not in USER_EMAIL:
        print("CRITICAL ERROR: You must update USER_EMAIL in the script with a valid email address.", file=sys.stderr)
        sys.exit(1)

def create_session_with_retries():
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session

def get_street_coordinates(street_name, city="Karlsruhe", country="Germany"):
    validate_config()
    
    geolocator = Nominatim(
        user_agent=USER_AGENT,
        timeout=NOMINATIM_TIMEOUT
    )
    
    query = f"{street_name}, {city}, {country}"
    
    for attempt in range(NOMINATIM_RETRY_COUNT):
        try:
            location = geolocator.geocode(
                query,
                addressdetails=True,
                language="de"
            )
            
            if not location:
                print(f"  [WARN] Could not geocode: '{query}'", file=sys.stderr)
                return None
            
            bbox = location.raw.get('boundingbox')
            if not bbox:
                print(f"  [WARN] No bounding box found for: '{query}'", file=sys.stderr)
                return None
                
            min_lat, max_lat, min_lon, max_lon = bbox
            return {
                "min_lat": float(min_lat),
                "max_lat": float(max_lat),
                "min_lon": float(min_lon),
                "max_lon": float(max_lon),
                "display_name": location.address
            }
            
        except GeocoderServiceError as e:
            if "403" in str(e):
                print(f"  [ERROR] 403 Forbidden. Check your USER_EMAIL in the script.", file=sys.stderr)
                return None
            if attempt < NOMINATIM_RETRY_COUNT - 1:
                wait_time = (attempt + 1) * 2
                print(f"  [RETRY] Service error on attempt {attempt + 1}, waiting {wait_time}s...", file=sys.stderr)
                time.sleep(wait_time)
            else:
                print(f"  [ERROR] Geocoding failed after {NOMINATIM_RETRY_COUNT} attempts: {e}", file=sys.stderr)
                return None
        except (GeocoderTimedOut, GeocoderUnavailable) as e:
            if attempt < NOMINATIM_RETRY_COUNT - 1:
                wait_time = (attempt + 1) * 2
                print(f"  [RETRY] Timeout on attempt {attempt + 1}, waiting {wait_time}s...", file=sys.stderr)
                time.sleep(wait_time)
            else:
                print(f"  [ERROR] Geocoding timeout after {NOMINATIM_RETRY_COUNT} attempts: {e}", file=sys.stderr)
                return None

def fetch_overpass_geojson(street_name, bbox):
    """
    Fetch GeoJSON for the street within the bounding box using Overpass API.
    Fixed: Added proper headers for 406 error.
    """
    # Escape special characters in street name for Overpass QL
    safe_name = street_name.replace('"', '\\"').replace('\\', '\\\\')
    
    query = f"""
    [out:json][timeout:25];
    (
      way["name"="{safe_name}"]({bbox['min_lat']},{bbox['min_lon']},{bbox['max_lat']},{bbox['max_lon']});
    );
    out geom;
    """

    session = create_session_with_retries()
    
    # CRITICAL FIX: Add proper headers for Overpass API
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'User-Agent': USER_AGENT
    }
    
    try:
        response = session.post(
            OVERPASS_URL,
            data={'data': query},  # Use form-encoded data
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        features = []
        for element in data.get('elements', []):
            if element['type'] == 'way' and 'geometry' in element:
                coords = [(pt['lon'], pt['lat']) for pt in element['geometry']]
                
                feature = {
                    "type": "Feature",
                    "properties": {
                        "name": element.get('tags', {}).get('name', street_name),
                        "highway": element.get('tags', {}).get('highway', 'unknown'),
                        "osm_id": element.get('id'),
                        "source": "OpenStreetMap"
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": coords
                    }
                }
                features.append(feature)
        
        if not features:
            print(f"  [INFO] No road segments found for '{street_name}' in the area.", file=sys.stderr)
            return None
            
        return {
            "type": "FeatureCollection",
            "features": features
        }

    except requests.exceptions.HTTPError as e:
        print(f"  [ERROR] Overpass API HTTP error: {e.response.status_code} {e.response.reason}", file=sys.stderr)
        if e.response.status_code == 406:
            print(f"  [TIP] 406 error usually means wrong Content-Type header. Check headers in script.", file=sys.stderr)
        return None
    except requests.exceptions.Timeout:
        print(f"  [ERROR] Overpass API timeout", file=sys.stderr)
        return None
    except requests.exceptions.RequestException as e:
        print(f"  [ERROR] Overpass API request failed: {e}", file=sys.stderr)
        return None

def process_single_street(street_name, city, country, output_file):
    print(f"Processing: {street_name}")
    
    bbox_data = get_street_coordinates(street_name, city, country)
    if not bbox_data:
        return False

    geojson = fetch_overpass_geojson(street_name, bbox_data)
    
    if geojson:
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(geojson, f, indent=2)
            print(f"  -> Saved to {output_file}")
        else:
            print(json.dumps(geojson, indent=2))
        return True
    return False

def process_batch_file(file_path, city, country, output_dir):
    path = Path(file_path)
    if not path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        return

    with open(path, 'r', encoding='utf-8') as f:
        streets = [line.strip() for line in f if line.strip()]

    if not streets:
        print("No streets found in file.")
        return

    print(f"Found {len(streets)} streets to process.")
    
    success_count = 0
    for i, street in enumerate(streets):
        print(f"[{i+1}/{len(streets)}] Processing: {street}")
        
        if i > 0:
            time.sleep(RATE_LIMIT_DELAY)
            
        if output_dir:
            safe_name = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in street)
            out_file = str(Path(output_dir) / f"{safe_name}.geojson")
        else:
            out_file = None
            
        if process_single_street(street, city, country, out_file):
            success_count += 1
            
    print(f"\nBatch complete. {success_count}/{len(streets)} successful.")

def main():
    parser = argparse.ArgumentParser(
        description="Fetch GeoJSON for streets in Karlsruhe using OpenStreetMap.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python street_geojson.py --street "Karolinenstrasse"
  python street_geojson.py --file streets.txt --output-dir ./output
        """
    )
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--street', '-s', type=str, help="Name of a single street to fetch")
    group.add_argument('--file', '-f', type=str, help="Path to a text file containing street names (one per line)")
    
    parser.add_argument('--city', '-c', type=str, default="Karlsruhe", help="City name (default: Karlsruhe)")
    parser.add_argument('--country', type=str, default="Germany", help="Country name (default: Germany)")
    parser.add_argument('--output-file', '-o', type=str, help="Output file path (for single street mode)")
    parser.add_argument('--output-dir', '-d', type=str, help="Output directory for batch mode (creates .geojson files)")
    
    args = parser.parse_args()
    
    if args.file and not args.output_dir:
        print("Error: --output-dir is required when using --file mode.", file=sys.stderr)
        sys.exit(1)
        
    if args.street and args.output_dir:
        print("Warning: --output-dir ignored in single street mode. Use --output-file.", file=sys.stderr)

    if args.street:
        process_single_street(args.street, args.city, args.country, args.output_file)
    elif args.file:
        process_batch_file(args.file, args.city, args.country, args.output_dir)

if __name__ == "__main__":
    main()
    