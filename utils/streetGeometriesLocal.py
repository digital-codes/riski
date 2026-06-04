#!/usr/bin/env python3
import argparse
import json
import sys
import os
import time
from pathlib import Path
import requests
import osmium

# Configuration
PBF_URL = "https://download.geofabrik.de/europe/germany/baden-wuerttemberg/karlsruhe-regbez-latest.osm.pbf"
PBF_FILENAME = "karlsruhe.osm.pbf"
USER_AGENT = "StreetGeoJSONFetcher/1.0 (your-email@example.com)"

# Bounding Box for Karlsruhe City (Approximate)
# Format: (min_lat, min_lon, max_lat, max_lon)
# You can refine these coordinates using a tool like https://bboxfinder.com/
# Current values cover the main urban area of Karlsruhe
KARLSRUHE_CITY_BBOX = (
    48.980,  # min_lat (South)
    8.360,   # min_lon (West)
    49.030,  # max_lat (North)
    8.450    # max_lon (East)
)

def is_in_karlsruhe(lat, lon):
    """Check if a coordinate is inside the Karlsruhe city bounding box."""
    min_lat, min_lon, max_lat, max_lon = KARLSRUHE_CITY_BBOX
    return (min_lat <= lat <= max_lat) and (min_lon <= lon <= max_lon)

class StreetGeoJSONHandler(osmium.SimpleHandler):
    def __init__(self, target_streets, output_dir=None):
        super().__init__()
        self.target_streets = {s.lower().strip() for s in target_streets}
        self.found_streets = set()
        self.features = []
        self.output_dir = output_dir
        self.nodes = {}

    def node(self, n):
        loc = n.location
        if loc.valid():
            self.nodes[n.id] = (float(loc.lon), float(loc.lat))

    def way(self, w):
        name_tag = w.tags.get('name')
        if not name_tag:
            return

        street_name_lower = name_tag.lower()
        
        # 1. Check if name matches
        if street_name_lower not in self.target_streets:
            return

        # 2. Calculate center point of the way to check location
        # We need at least one node to calculate a center
        if not w.nodes:
            return

        # Sum coordinates to find average
        sum_lat = 0.0
        sum_lon = 0.0
        count = 0
        
        for node_ref in w.nodes:
            if node_ref.ref in self.nodes:
                lon, lat = self.nodes[node_ref.ref]
                sum_lat += lat
                sum_lon += lon
                count += 1
        
        if count == 0:
            return

        center_lat = sum_lat / count
        center_lon = sum_lon / count

        # 3. Filter by City BBox
        if not is_in_karlsruhe(center_lat, center_lon):
            # Optional: Uncomment to see skipped segments
            # print(f"  [SKIP] Way {w.id} '{name_tag}' is outside Karlsruhe city limits.")
            return

        # If we passed the filter, add the feature
        self.found_streets.add(name_tag)
        
        coords = []
        for node_ref in w.nodes:
            if node_ref.ref in self.nodes:
                coords.append(self.nodes[node_ref.ref])
        
        if len(coords) < 2:
            return

        feature = {
            "type": "Feature",
            "properties": {
                "name": name_tag,
                "highway": w.tags.get('highway', 'unknown'),
                "osm_id": w.id,
                "center_lat": center_lat,
                "center_lon": center_lon,
                "source": "Local PBF (Geofabrik) - Filtered by Karlsruhe City"
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

    print(f"Downloading {filename} (~100MB)... This may take a minute.")
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

def process_streets_from_pbf(pbf_file, target_streets, output_dir):
    if not os.path.exists(pbf_file):
        print(f"Error: PBF file '{pbf_file}' not found.", file=sys.stderr)
        return

    print(f"Processing {len(target_streets)} streets from local PBF (filtered to Karlsruhe City)...")
    
    handler = StreetGeoJSONHandler(target_streets, output_dir)
    
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
    print(f"Total segments found (within city limits): {len(handler.features)}")
    print(f"Unique street names found: {len(handler.found_streets)}")

    # Identify Missing Streets
    missing_streets = []
    for original_name in target_streets:
        if original_name.lower() not in handler.found_streets:
            missing_streets.append(original_name)

    if missing_streets:
        print("\n--- STREETS NOT FOUND IN KARLSRUHE CITY ---")
        print(f"The following {len(missing_streets)} street(s) were not found within the city limits:")
        for street in missing_streets:
            print(f"  - {street}")
        print("Possible reasons: Spelling error, name variation, or street is outside the defined city box.\n")
    else:
        print("\nAll requested streets were found within Karlsruhe city limits.")

    if not handler.features:
        print("No matching street segments found.")
        return

    # Group and Save
    grouped_features = {}
    for feat in handler.features:
        name = feat['properties']['name']
        if name not in grouped_features:
            grouped_features[name] = []
        grouped_features[name].append(feat)

    if output_dir:
        for name, feats in grouped_features.items():
            safe_name = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in name)
            out_file = Path(output_dir) / f"{safe_name}.geojson"
            
            collection = {
                "type": "FeatureCollection",
                "features": feats
            }
            
            with open(out_file, 'w', encoding='utf-8') as f:
                json.dump(collection, f, indent=2)
            
            print(f"  -> Saved {len(feats)} segments for '{name}' to {out_file.name}")
    else:
        print(json.dumps({"type": "FeatureCollection", "features": handler.features}, indent=2))

def main():
    parser = argparse.ArgumentParser(description="Fetch street GeoJSON from local OSM PBF file (Karlsruhe City Filter).")
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--street', '-s', type=str, help="Single street name")
    group.add_argument('--file', '-f', type=str, help="File with street names (one per line)")
    
    parser.add_argument('--output-dir', '-d', type=str, help="Output directory for GeoJSON files")
    parser.add_argument('--pbf', type=str, default=PBF_FILENAME, help=f"PBF filename (default: {PBF_FILENAME})")
    
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

    process_streets_from_pbf(args.pbf, target_streets, args.output_dir)

if __name__ == "__main__":
    main()
    