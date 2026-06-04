#!/usr/bin/env python3
import argparse
import json
import sys
import os
import time
import re
from pathlib import Path
import requests
import osmium

# Configuration
PBF_URL = "https://download.geofabrik.de/europe/germany/baden-wuerttemberg/karlsruhe-regbez-latest.osm.pbf"
PBF_FILENAME = "karlsruhe.osm.pbf"
USER_AGENT = "StreetGeoJSONFetcher/1.0 (your-email@example.com)"

# Bounding Box for Karlsruhe City
KARLSRUHE_CITY_BBOX = (48.980, 8.360, 49.030, 8.450)

def is_in_karlsruhe(lat, lon):
    min_lat, min_lon, max_lat, max_lon = KARLSRUHE_CITY_BBOX
    return (min_lat <= lat <= max_lat) and (min_lon <= lon <= max_lon)

def normalize_name(name):
    """Normalize street names for better matching."""
    if not name:
        return ""
    # Lowercase
    name = name.lower()
    # Remove common suffixes/prefixes variations
    # "straße" -> "strasse" (German eszett normalization)
    name = name.replace("ß", "ss")
    # Remove "straße", "str.", "str" from end to match base name? 
    # No, better to keep full name but normalize spelling.
    # Remove punctuation
    name = re.sub(r'[^\w\s]', '', name)
    # Collapse spaces
    name = re.sub(r'\s+', ' ', name).strip()
    return name

class StreetGeoJSONHandler(osmium.SimpleHandler):
    def __init__(self, target_streets, output_dir=None, save_all=False):
        super().__init__()
        # Normalize target streets
        self.target_streets = {normalize_name(s) for s in target_streets}
        self.target_map = {normalize_name(s): s for s in target_streets} # Map normalized -> original
        
        self.found_streets = set() # Will store NORMALIZED names
        self.features = []
        self.all_city_features = [] # For the "all streets" file
        self.output_dir = output_dir
        self.save_all = save_all
        self.nodes = {}

    def node(self, n):
        loc = n.location
        if loc.valid():
            self.nodes[n.id] = (float(loc.lon), float(loc.lat))

    def way(self, w):
        name_tag = w.tags.get('name')
        if not name_tag:
            return

        norm_name = normalize_name(name_tag)
        
        # 1. Check location first (optimization)
        if not w.nodes:
            return
        sum_lat, sum_lon, count = 0.0, 0.0, 0
        for node_ref in w.nodes:
            if node_ref.ref in self.nodes:
                lon, lat = self.nodes[node_ref.ref]
                sum_lat += lat
                sum_lon += lon
                count += 1
        if count == 0: return
        center_lat, center_lon = sum_lat/count, sum_lon/count
        
        if not is_in_karlsruhe(center_lat, center_lon):
            return

        # If we want to save ALL streets in the city
        if self.save_all:
            coords = [self.nodes[nr.ref] for nr in w.nodes if nr.ref in self.nodes]
            if len(coords) >= 2:
                self.all_city_features.append({
                    "type": "Feature",
                    "properties": {"name": name_tag, "osm_id": w.id, "source": "All Karlsruhe"},
                    "geometry": {"type": "LineString", "coordinates": coords}
                })

        # 2. Check if name matches target
        if norm_name in self.target_streets:
            self.found_streets.add(norm_name)
            
            coords = []
            for node_ref in w.nodes:
                if node_ref.ref in self.nodes:
                    coords.append(self.nodes[node_ref.ref])
            
            if len(coords) < 2:
                return

            # Get original name from map if possible, else use tag
            original_name = self.target_map.get(norm_name, name_tag)
            
            feature = {
                "type": "Feature",
                "properties": {
                    "name": name_tag, # Keep original OSM name
                    "normalized_name": norm_name,
                    "highway": w.tags.get('highway', 'unknown'),
                    "osm_id": w.id,
                    "source": "Local PBF (Filtered)"
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": coords
                }
            }
            self.features.append(feature)

def download_pbf(url, filename):
    if os.path.exists(filename):
        print(f"PBF file '{filename}' already exists. Skipping download.")
        return True
    print(f"Downloading {filename}...")
    try:
        response = requests.get(url, stream=True, headers={'User-Agent': USER_AGENT})
        response.raise_for_status()
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Download complete: {filename}")
        return True
    except Exception as e:
        print(f"Error downloading PBF: {e}", file=sys.stderr)
        return False

def process_streets_from_pbf(pbf_file, target_streets, output_dir, save_all=False):
    if not os.path.exists(pbf_file):
        print(f"Error: PBF file '{pbf_file}' not found.", file=sys.stderr)
        return

    print(f"Processing {len(target_streets)} streets (with normalization)...")
    
    handler = StreetGeoJSONHandler(target_streets, output_dir, save_all)
    
    start_time = time.time()
    try:
        handler.apply_file(pbf_file)
    except Exception as e:
        print(f"Error processing PBF: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return

    elapsed = time.time() - start_time
    print(f"Processing complete in {elapsed:.2f}s.")
    print(f"Total segments found: {len(handler.features)}")
    print(f"Unique normalized names found: {len(handler.found_streets)}")

    # --- FIX: Correct Missing Streets Report ---
    missing_streets = []
    for original_name in target_streets:
        norm = normalize_name(original_name)
        if norm not in handler.found_streets:
            missing_streets.append(original_name)

    if missing_streets:
        print(f"\n--- {len(missing_streets)} STREETS NOT FOUND ---")
        for street in missing_streets:
            print(f"  - {street}")
        print()
    else:
        print("\nAll requested streets found!")

    # Save Individual Files
    if output_dir:
        grouped = {}
        for feat in handler.features:
            name = feat['properties']['name']
            if name not in grouped: grouped[name] = []
            grouped[name].append(feat)
        
        for name, feats in grouped.items():
            safe_name = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in name)
            out_file = Path(output_dir) / f"{safe_name}.geojson"
            with open(out_file, 'w', encoding='utf-8') as f:
                json.dump({"type": "FeatureCollection", "features": feats}, f, indent=2)
            # print(f"  -> Saved {len(feats)} segments for '{name}'")

        # Save ALL Streets in City
        if save_all and handler.all_city_features:
            all_file = Path(output_dir) / "all_karlsruhe_streets.geojson"
            with open(all_file, 'w', encoding='utf-8') as f:
                json.dump({"type": "FeatureCollection", "features": handler.all_city_features}, f, indent=2)
            # print(f"\n-> Saved ALL {len(handler.all_city_features)} streets in city to {all_file.name}")

    else:
        pass
        # print(json.dumps({"type": "FeatureCollection", "features": handler.features}, indent=2))

def main():
    parser = argparse.ArgumentParser(description="Fetch street GeoJSON with normalization and city filter.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--street', '-s', type=str, help="Single street name")
    group.add_argument('--file', '-f', type=str, help="File with street names")
    
    parser.add_argument('--output-dir', '-d', type=str, help="Output directory")
    parser.add_argument('--pbf', type=str, default=PBF_FILENAME)
    parser.add_argument('--all', action='store_true', help="Also save a file with ALL streets in the city")
    
    args = parser.parse_args()

    target_streets = []
    if args.street:
        target_streets = [args.street]
    elif args.file:
        if not os.path.exists(args.file):
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        with open(args.file, 'r') as f:
            target_streets = [line.strip() for line in f if line.strip()]

    if not target_streets:
        print("No streets to process.")
        sys.exit(1)

    if args.output_dir:
        Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    if not download_pbf(PBF_URL, args.pbf):
        sys.exit(1)

    process_streets_from_pbf(args.pbf, target_streets, args.output_dir, save_all=args.all)

if __name__ == "__main__":
    main()
    