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

try:
    from shapely.geometry import Point, shape, MultiPoint
    from shapely.prepared import prep
    from shapely.ops import polygonize, unary_union
    HAS_SHAPLEY = True
except ImportError:
    HAS_SHAPLEY = False
    print("CRITICAL: 'shapely' not found. Install with: pip install shapely")
    sys.exit(1)

# Configuration
PBF_URL = "https://download.geofabrik.de/europe/germany/baden-wuerttemberg/karlsruhe-regbez-latest.osm.pbf"
PBF_FILENAME = "karlsruhe.osm.pbf"
USER_AGENT = "Riski-Geo/1.0 (info@ok-lab-karlsruhe.de)"

BOUNDARY_URL = "https://nominatim.openstreetmap.org/search?format=geojson&polygon_geojson=1&q=Karlsruhe%20Germany"
TARGET_RELATION_ID = 62518  # Karlsruhe City Boundary

def build_polygon_from_geojson(geojson_data):
    """Convert GeoJSON to prepared Shapely geometry."""
    if not HAS_SHAPLEY:
        return None
    try:
        # The saved file has a single feature with the polygon geometry
        if not geojson_data.get('features'):
            return None
        geom = shape(geojson_data['features'][0]['geometry'])
        return prep(geom)
    except Exception as e:
        print(f"Error building polygon: {e}", file=sys.stderr)
        return None

def normalize_name(name):
    if not name:
        return ""
    name = name.lower()
    name = name.replace("ß", "ss")
    name = re.sub(r'[^\w\s]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name

class StreetGeoJSONHandler(osmium.SimpleHandler):
    def __init__(self, target_streets, output_dir=None, save_all=False, boundary_poly=None):
        super().__init__()
        self.target_streets = {normalize_name(s) for s in target_streets}
        self.target_map = {normalize_name(s): s for s in target_streets}
        self.found_streets = set()
        self.features = []
        self.all_city_features = []
        self.output_dir = output_dir
        self.save_all = save_all
        self.nodes = {}
        self.boundary_poly = boundary_poly

    def node(self, n):
        loc = n.location
        if loc.valid():
            self.nodes[n.id] = (float(loc.lon), float(loc.lat))

    def way(self, w):
        name_tag = w.tags.get('name')
        if not name_tag:
            return

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

        # FILTER: Check if center is inside the Karlsruhe boundary polygon
        if self.boundary_poly:
            point = Point(center_lon, center_lat)
            if not self.boundary_poly.contains(point):
                return
        else:
            print("CRITICAL: No boundary polygon available. Aborting.", file=sys.stderr)
            sys.exit(1)

        if self.save_all:
            coords = [self.nodes[nr.ref] for nr in w.nodes if nr.ref in self.nodes]
            if len(coords) >= 2:
                self.all_city_features.append({
                    "type": "Feature",
                    "properties": {"name": name_tag, "osm_id": w.id, "source": "All Karlsruhe"},
                    "geometry": {"type": "LineString", "coordinates": coords}
                })

        norm_name = normalize_name(name_tag)
        if norm_name in self.target_streets:
            self.found_streets.add(norm_name)
            
            coords = [self.nodes[nr.ref] for nr in w.nodes if nr.ref in self.nodes]
            if len(coords) < 2:
                return

            feature = {
                "type": "Feature",
                "properties": {
                    "name": name_tag,
                    "normalized_name": norm_name,
                    "highway": w.tags.get('highway', 'unknown'),
                    "osm_id": w.id,
                    "source": "Local PBF (Extracted Boundary)"
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

    # Load or Extract Boundary
    try:
        boundary_request = requests.get(BOUNDARY_URL, headers={'User-Agent': USER_AGENT})
        print("Boundary GeoJSON fetched from Nominatim.")
        boundary_geojson = boundary_request.json()
        
        # for karlsruhe, we need to add an upper boundary so no coordinate can get larger than 49.088
        boundary_top = 49.088
        print(f"!!NOTE: Adjusting Karlsruhe boundary to enforce upper latitude limit of {boundary_top}...")
        for feature in boundary_geojson.get('features', []):
            if feature['geometry']['type'] == 'Polygon':
                for i, coord in enumerate(feature['geometry']['coordinates'][0]):
                    if coord[1] > boundary_top:
                        feature['geometry']['coordinates'][0][i] = (coord[0], boundary_top)
        
    except Exception as e:
        print(f"Error loading boundary: {e}", file=sys.stderr)
        sys.exit(1)
    
    if not boundary_geojson:
        print("CRITICAL: Failed to extract or load boundary. Cannot proceed.", file=sys.stderr)
        sys.exit(1)

    boundary_poly = build_polygon_from_geojson(boundary_geojson)
    if not boundary_poly:
        print("CRITICAL: Failed to build polygon.", file=sys.stderr)
        sys.exit(1)
        
    print("Karlsruhe boundary loaded and prepared.")

    print(f"Processing {len(target_streets)} streets...")
    
    handler = StreetGeoJSONHandler(target_streets, output_dir, save_all, boundary_poly)
    
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

    # Report missing streets
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

    if output_dir:
        # 1. Individual Files
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

        # 2. Combined Found
        if handler.features:
            combined_file = Path(output_dir) / "all_found_streets.geojson"
            with open(combined_file, 'w', encoding='utf-8') as f:
                json.dump({"type": "FeatureCollection", "features": handler.features}, f, indent=2)
            print(f"Saved combined file: {combined_file.name} ({len(handler.features)} segments)")

        # 3. All City Streets
        if save_all and handler.all_city_features:
            all_file = Path(output_dir) / "all_karlsruhe_streets.geojson"
            with open(all_file, 'w', encoding='utf-8') as f:
                json.dump({"type": "FeatureCollection", "features": handler.all_city_features}, f, indent=2)
            print(f"Saved all city streets: {all_file.name} ({len(handler.all_city_features)} segments)")

    else:
        print(json.dumps({"type": "FeatureCollection", "features": handler.features}, indent=2))

def main():
    parser = argparse.ArgumentParser(description="Fetch street GeoJSON with local PBF boundary extraction.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--street', '-s', type=str)
    group.add_argument('--file', '-f', type=str)
    
    parser.add_argument('--output-dir', '-d', type=str)
    parser.add_argument('--pbf', type=str, default=PBF_FILENAME)
    parser.add_argument('--all', action='store_true', help="Save all streets in city boundary")
    
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
    