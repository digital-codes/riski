import os
import json
import random
import collections
from typing import Dict, Any, List

CRAWL_FOLDER = "ko"

def get_resource_type(resource: dict) -> str:
    """
    e.g. 'type': 'https://schema.oparl.org/1.1/Paper' -> 'Paper'
    fallback: 'Unknown'
    """
    t = resource.get("type", "")
    if t.startswith("http"):
        return t.rstrip("/").split("/")[-1]
    return "Unknown"

def load_all_resources(crawl_folder: str) -> Dict[str, dict]:
    """
    Reads all JSON files in 'crawl_folder'. 
    Each file can be:
     - A single resource (dict) with an 'id'
     - A list of resources (dicts)
    We store them by resource['id'] in a global dictionary.
    Returns { resource_id: resource_dict, ... }
    """
    resources_by_id = {}
    count_files = 0

    for root, dirs, files in os.walk(crawl_folder):
        for filename in files:
            if not filename.lower().endswith(".json"):
                continue
            filepath = os.path.join(root, filename)
            count_files += 1

            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue  # skip invalid JSON

            if isinstance(data, dict):
                # single resource or unknown
                rid = data.get("id")
                if rid:
                    resources_by_id[rid] = data
            elif isinstance(data, list):
                # possibly multiple resources
                for item in data:
                    if isinstance(item, dict):
                        rid = item.get("id")
                        if rid:
                            resources_by_id[rid] = item
    print(f"[INFO] Read {count_files} JSON files, collected {len(resources_by_id)} resources with 'id'.")
    return resources_by_id

def analyze_resources(resources_by_id: Dict[str, dict]):
    """
    Group resources by their 'type' and gather statistics:
    - How many resources of each type
    - Which fields appear, and how often
    - The data types of those fields (str, dict, list, etc.)
    - A small random sample of values for each field
    """

    # 1) Group by resource type
    resources_by_type = collections.defaultdict(list)
    for rid, data in resources_by_id.items():
        rtype = get_resource_type(data)
        resources_by_type[rtype].append(data)

    # 2) For each resource type, gather field stats
    for rtype, items in resources_by_type.items():
        print("=" * 80)
        print(f"[TYPE] {rtype}  (count={len(items)})")
        print("=" * 80)

        # Collect all field occurrences
        field_counts = collections.Counter()
        # Also track the data types we see in each field
        field_types = collections.defaultdict(lambda: collections.Counter())

        # We'll store examples for each field
        max_examples = 5  # store up to 5 random examples
        field_examples = collections.defaultdict(list)

        for resource in items:
            for key, val in resource.items():
                field_counts[key] += 1
                # Record the type name: "str", "dict", "list", "NoneType", etc.
                tname = type(val).__name__
                field_types[key][tname] += 1

                # Possibly store an example
                if len(field_examples[key]) < max_examples:
                    # We'll store a *stringified* version of the value (truncated for printing)
                    example_str = str(val)
                    if len(example_str) > 200:
                        example_str = example_str[:200] + "..."
                    field_examples[key].append(example_str)

        # 3) Print stats
        # Sort fields by frequency
        sorted_fields = sorted(field_counts.items(), key=lambda x: x[1], reverse=True)

        for field, count_ in sorted_fields:
            percent = 100.0 * count_ / len(items)
            # gather type distribution
            types_count = field_types[field]
            type_dist_str = ", ".join(f"{tn}:{cnt}" for tn, cnt in types_count.items())
            print(f"  Field '{field}': {count_} / {len(items)} ({percent:.1f}%)")
            print(f"    Types: {type_dist_str}")

            # Print up to a few examples
            if field_examples[field]:
                print("    Examples:")
                for ex in field_examples[field]:
                    print(f"      - {ex}")
            print()

        print()  # blank line between types

def main():
    resources_by_id = load_all_resources(CRAWL_FOLDER)
    analyze_resources(resources_by_id)

if __name__ == "__main__":
    main()


