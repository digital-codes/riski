#!/usr/bin/env python3
"""
pass2_cluster_words.py - Cluster words from pass1 output using similarity

Usage:
    python pass2_cluster_words.py -i entities_tfidf.json -o clusters.json -t 85
    python pass2_cluster_words.py -i entities_tfidf.json -o clusters.json --threshold 0.80

Outputs JSON with:
{
    "clusters": [{"rep": "...", "members": ["...", ...], "size": N, "max_tfidf": score}, ...],
    "unclustered": [{"word": "...", "tfidf": score}, ...],
    "metadata": {"similarity_threshold": 0.85, "num_clusters": N, ...}
}
"""

import argparse
import os
import sys
import json
from collections import defaultdict
from datetime import datetime, timezone

try:
    from rapidfuzz import fuzz, process
except ImportError:
    print("Install rapidfuzz: pip install rapidfuzz")
    sys.exit(1)


def parse_args():
    p = argparse.ArgumentParser(description="Cluster words using similarity")
    p.add_argument("-u", "--user", default=os.environ.get('RISKI_USER', 'wiski'), help="db user")
    p.add_argument("-p", "--password", default=os.environ.get('RISKI_PASSWORD', None), help="db password")
    p.add_argument("-i", "--input", default="entities_tfidf.json", help="input JSON from pass1")
    p.add_argument("-o", "--output", default="word_clusters.json", help="output JSON file")
    p.add_argument("-t", "--threshold", type=float, default=85.0,
                   help="similarity threshold (0-100 for rapidfuzz, or 0-1)")
    p.add_argument("--min-cluster-size", type=int, default=2,
                   help="minimum cluster size to keep")
    p.add_argument("--top-n", type=int, default=500,
                   help="number of top words by TF-IDF to cluster")
    return p.parse_args()


def normalize_threshold(threshold):
    """Normalize threshold to 0-100 range for rapidfuzz."""
    if threshold <= 1.0:
        return threshold * 100
    return threshold


def cluster_words(words_data, threshold, min_cluster_size=2):
    """
    Cluster words using fuzzy similarity.
    
    Args:
        words_data: List of dicts [{'word': str, 'tfidf': float, ...}, ...]
        threshold: Similarity threshold (0-100)
        min_cluster_size: Minimum cluster size to keep
    
    Returns:
        (clusters, unclustered) where:
        - clusters: List of {'rep': str, 'members': [str, ...], 'size': int, 'max_tfidf': float}
        - unclustered: List of {'word': str, 'tfidf': float}
    """
    if not words_data:
        return [], []
    
    # Create word -> tfidf mapping
    word_tfidf = {w['word']: w['tfidf'] for w in words_data}
    words = [w['word'] for w in words_data]
    
    # Track which words have been assigned to clusters
    assigned = set()
    clusters = []
    
    # Simple clustering: for each word (sorted by original Tfidf), find similar matches
    for i, word_data in enumerate(words_data):
        word = word_data['word']
        tfidf = word_data['tfidf']
        
        if word in assigned:
            continue
        
        # Find similar words
        similar = []
        for j, other_word in enumerate(words):
            if other_word in assigned or i == j:
                continue
            
            # Check similarity
            score = fuzz.ratio(word.lower(), other_word.lower())
            if score >= threshold:
                similar.append((other_word, score, word_tfidf[other_word]))
        
        # Only create cluster if we have similar words
        if similar:
            # Sort by score descending, then by tfidf
            similar.sort(key=lambda x: (-x[1], -x[2]))
            
            # Choose representative: highest tfidf among similar + current
            cluster_words = [word] + [s[0] for s in similar]
            cluster_tfidfs = [tfidf] + [s[2] for s in similar]
            
            max_tfidf_idx = cluster_tfidfs.index(max(cluster_tfidfs))
            representative = cluster_words[max_tfidf_idx]
            
            # Mark all as assigned
            for cw in cluster_words:
                assigned.add(cw)
            
            clusters.append({
                "rep": representative,
                "members": cluster_words,
                "size": len(cluster_words),
                "max_tfidf": max(cluster_tfidfs)
            })
    
    # Filter clusters by minimum size
    clusters = [c for c in clusters if c["size"] >= min_cluster_size]
    
    # Sort clusters by size descending, then max_tfidf
    clusters.sort(key=lambda x: (-x["size"], -x["max_tfidf"]))
    
    # Unclustered words
    unclustered = [{"word": w, "tfidf": word_tfidf[w]} 
                   for w in words if w not in assigned]
    
    unclustered.sort(key=lambda x: -x["tfidf"])
    
    return clusters, unclustered


def merge_clusters(clusters, threshold):
    """
    Merge clusters that share representative similarity.
    
    Args:
        clusters: List of cluster dicts from cluster_words()
        threshold: Similarity threshold for merging (0-100)
    
    Returns:
        Merged clusters list
    """
    if not clusters:
        return []
    
    # Build rep -> cluster index
    cluster_by_rep = {c["rep"]: idx for idx, c in enumerate(clusters)}
    
    # Track merged clusters
    merged = []
    merged_indices = set()
    
    for i, cluster1 in enumerate(clusters):
        if i in merged_indices:
            continue
        
        # Start new merged cluster
        merged_members = set(cluster1["members"])
        merged_reps = [cluster1["rep"]]
        
        # Find other clusters with similar representatives
        for j, cluster2 in enumerate(clusters):
            if j <= i or j in merged_indices:
                continue
            
            # Check if reps are similar
            score = fuzz.ratio(cluster1["rep"].lower(), cluster2["rep"].lower())
            if score >= threshold:
                # Merge
                merged_members.update(cluster2["members"])
                merged_reps.append(cluster2["rep"])
                merged_indices.add(j)
        
        merged_indices.add(i)
        
        # Choose representative: highest original tfidf among members
        max_tfidf = 0
        best_rep = cluster1["rep"]
        # Note: We'd need original tfidf for this, using cluster1's max_tfidf for now
        # In practice, might pass word_tfidf dict
        
        merged_cluster = {
            "rep": best_rep,
            "members": sorted(list(merged_members)),
            "size": len(merged_members),
            "merged_from": merged_reps,
            "max_tfidf": cluster1.get("max_tfidf", 0)
        }
        
        merged.append(merged_cluster)
    
    # Sort by size
    merged.sort(key=lambda x: -x["size"])
    
    return merged


def load_with_schema_check(args):
    """
    Load pass1 JSON. Optionally re-query DB if needed.
    Currently returns the loaded pass1 dict.
    """
    input_path = args.input
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Validate structure
        if "words" not in data:
            sys.stderr.write(f"Error: input JSON missing 'words' key\n")
            sys.exit(1)
        
        return data
    except FileNotFoundError:
        sys.stderr.write(f"Error: input file not found: {input_path}\n")
        sys.exit(1)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"Error: invalid JSON: {e}\n")
        sys.exit(1)


def main():
    args = parse_args()
    threshold = normalize_threshold(args.threshold)
    
    # Load pass1 output
    print(f"Loading pass1 results from {args.input}...")
    pass1_data = load_with_schema_check(args)
    
    words_data = pass1_data.get("words", [])
    print(f"Found {len(words_data)} words from pass1")
    
    # Limit to top-n if specified
    if args.top_n and args.top_n < len(words_data):
        words_data = words_data[:args.top_n]
        print(f"Using top {args.top_n} words by TF-IDF")
    
    # Cluster words
    print(f"Clustering words with similarity threshold {threshold:.1f}%...")
    clusters, unclustered = cluster_words(words_data, threshold, args.min_cluster_size)
    
    print(f"Found {len(clusters)} clusters (min size: {args.min_cluster_size})")
    print(f"Unclustered words: {len(unclustered)}")
    
    # Optionally merge clusters with similar representatives
    if len(clusters) > 1:
        print("Merging similar clusters...")
        clusters = merge_clusters(clusters, threshold)
        print(f"After merging: {len(clusters)} clusters")
    
    # Build metadata
    metadata = pass1_data.get("metadata", {})
    metadata.update({
        "similarity_threshold": threshold,
        "min_cluster_size": args.min_cluster_size,
        "top_n_clustered": args.top_n,
        "num_clusters": len(clusters),
        "num_unclustered": len(unclustered),
        "pass1_file": args.input,
        "pass1_timestamp": metadata.get("timestamp"),
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    
    # Build output
    output = {
        "clusters": clusters[:200],  # Limit to top 200 clusters
        "unclustered": unclustered[:500],  # Limit unclustered
        "metadata": metadata
    }
    
    # Write output
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"Results written to {args.output}")
    
    # Print summary
    print("\nTop 10 clusters:")
    for i, cluster in enumerate(clusters[:10]):
        members_str = ", ".join(cluster["members"][:5])
        if len(cluster["members"]) > 5:
            members_str += f" ... ({len(cluster['members'])-5} more)"
        print(f"  {i+1:2d}. Rep: {cluster['rep']:15s} | Size: {cluster['size']:2d} | "
              f"Max Tfidf: {cluster['max_tfidf']:.4f}")
        print(f"      Members: {members_str}")
    
    # Print stats
    avg_cluster_size = sum(c["size"] for c in clusters) / len(clusters) if clusters else 0
    max_cluster_size = max(c["size"] for c in clusters) if clusters else 0
    
    print("\nCluster statistics:")
    print(f"  Total clusters: {len(clusters)}")
    print(f"  Average size: {avg_cluster_size:.1f}")
    print(f"  Max size: {max_cluster_size}")
    print(f"  Unclustered words: {len(unclustered)}")


if __name__ == "__main__":
    main()