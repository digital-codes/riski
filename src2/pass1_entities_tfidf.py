#!/usr/bin/env python3
"""
pass1_entities_tfidf.py - Extract entities and compute TF-IDF from teasers

Usage:
    RISKI_PASSWORD=*** python pass1_entities_tfidf.py -u wiski -l de -o entities_tfidf.json
    RISKI_PASSWORD=*** python pass1_entities_tfidf.py -u wiski -l en -o output.json

Outputs JSON with:
{
    "entities": {"person": [...], "organization": [...], "street": [...], ...},
    "words": [{"word": "...", "total": N, "docs": N, "tfidf": score}, ...],
    "metadata": {"num_docs": N, "language": "de|en", "timestamp": "..."}
}
"""

import argparse
import os
import sys
import json
from collections import Counter, defaultdict
import math
from datetime import datetime, timezone

try:
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
except ImportError:
    print("Install psycopg2: pip install psycopg2-binary")
    sys.exit(1)

try:
    import nltk
    from nltk.corpus import stopwords
    from nltk.tokenize import word_tokenize
except ImportError:
    print("Install nltk: pip install nltk")
    sys.exit(1)


def parse_args():
    p = argparse.ArgumentParser(description="Extract entities and compute TF-IDF from teasers")
    p.add_argument("-u", "--user", default=os.environ.get('RISKI_USER', 'wiski'), help="db user")
    p.add_argument("-p", "--password", default=os.environ.get('RISKI_PASSWORD', None), help="db password")
    p.add_argument("-l", "--lang", default="de", help="language for stopwords (de=German, en=English, fr=French)")
    p.add_argument("-c", "--count", type=int, default=None, help="number of teasers to process")
    p.add_argument("-t","--text", default="teaser", help="Column to extract text from (default: teaser)")
    p.add_argument("--ids", type=str, nargs='*', default=[], help="file ids")
    p.add_argument("-o", "--output", default="entities_tfidf.json", help="output JSON file")
    p.add_argument("--min-doc-freq", type=int, default=2, help="minimum documents a word must appear in")
    p.add_argument("--min-tfidf", type=float, default=0.1, help="minimum TF-IDF score to include")
    p.add_argument("--entity-types", type=str, nargs='+',
                   default=["person", "organization", "street", "location", "date"],
                   help="entity types to extract")
    p.add_argument("--max-bar", type=int, default=50, help="progress bar width")
    return p.parse_args()


def getcreds(args):
    if not args.password:
        sys.stderr.write("error: no password. Use RISKI_PASSWORD or -p\n")
        sys.exit(1)
    return args.user, args.password


def ensure_nltk_resources():
    """Download required NLTK resources."""
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        nltk.download('punkt', quiet=True)
    
    try:
        nltk.data.find('corpora/stopwords')
    except LookupError:
        nltk.download('stopwords', quiet=True)


def get_stopwords(lang):
    """Get stopwords for language."""
    lang_map = {
        "de": "german",
        "en": "english", 
        "fr": "french",
        "es": "spanish",
        "cs": "czech"
    }
    lang_code = lang_map.get(lang.lower(), "german")
    try:
        return set(stopwords.words(lang_code))
    except:
        sys.stderr.write(f"Warning: stopwords for {lang_code} not available\n")
        return set()


def getEntities(text, type):
    """
    Entity extraction hook - REPLACE THIS FUNCTION with your actual implementation.
    
    This is a placeholder that will be replaced by your actual entity extraction function.
    For now, returns empty list.
    
    Args:
        text: Teaser text to extract entities from
        type: Entity type (person, organization, street, location, date, etc.)
    
    Returns:
        List of entity strings
    """
    # TODO: Replace with actual entity extraction implementation
    # Example: return your_entity_extractor.extract(text, type)
    return []


def preprocess_text(text, stopwords):
    """Tokenize and remove stopwords."""
    if not text:
        return []
    
    try:
        tokens = word_tokenize(text.lower())
    except:
        # Fallback if NLTK tokenization fails
        tokens = text.lower().split()
    
    # Remove stopwords and non-alphabetic tokens
    filtered = [token for token in tokens 
                if token.isalpha() and 
                len(token) > 2 and 
                token not in stopwords]
    
    return filtered


def compute_tfidf(documents, stopwords):
    """
    Compute TF-IDF scores for all words across documents.
    
    Args:
        documents: List of token lists (one per teaser)
        stopwords: Set of stopwords to exclude
    
    Returns:
        List of dicts: [{"word": str, "total": int, "docs": int, "tfidf": float}, ...]
    """
    # Preprocess documents - stopword filtering is delegated to preprocess_text,
    # but we also ensure no tokens are stopwords on the way in.
    docs = [preprocess_text(doc, stopwords) for doc in documents]
    
    # Total documents
    N = len(docs)
    if N == 0:
        return []
    
    # Word frequency per document
    doc_frequencies = []
    word_doc_counts = Counter()
    word_total_counts = Counter()
    
    for doc in docs:
        if not doc:
            doc_frequencies.append({})
            continue
        
        # Count words in this document
        doc_counter = Counter(doc)
        doc_frequencies.append(doc_counter)
        
        # Track which words appear in which document
        for word in set(doc):
            word_doc_counts[word] += 1
            word_total_counts[word] += doc_counter[word]
    
    # Compute TF-IDF for each word
    results = []
    for word in word_total_counts:
        total_count = word_total_counts[word]
        doc_count = word_doc_counts[word]
        
        # Skip if below thresholds
        if doc_count < 1:
            continue
        
        # IDF: log(N / doc_freq)
        idf = math.log(N / doc_count)
        
        # tfidf: average tf across docs * idf
        avg_tf = total_count / doc_count
        tfidf = avg_tf * idf
        
        results.append({
            "word": word,
            "total": total_count,
            "docs": doc_count,
            "tfidf": round(tfidf, 6)
        })
    
    # Sort by TF-IDF descending
    results.sort(key=lambda x: x["tfidf"], reverse=True)
    
    return results


def extract_entities_from_texts(texts, entity_types):
    """
    Extract entities from texts using getEntities hook.
    
    Args:
        texts: List of text strings
        entity_types: List of entity types to extract
    
    Returns:
        Dict mapping entity type to list of unique entities
    """
    entities = defaultdict(list)
    
    for text in texts:
        if not text:
            continue
        
        for entity_type in entity_types:
            try:
                type_entities = getEntities(text, entity_type)
                entities[entity_type].extend(type_entities)
            except Exception as e:
                sys.stderr.write(f"Warning: entity extraction failed for {entity_type}: {e}\n")
    
    # Deduplicate entities per type
    for entity_type in entities:
        entities[entity_type] = list(set(entities[entity_type]))
    
    return dict(entities)


def main():
    args = parse_args()
    user, password = getcreds(args)
    
    # Setup NLTK
    ensure_nltk_resources()
    stopwords = get_stopwords(args.lang)
    
    conn = None
    cursor = None
    
    try:
        conn = psycopg2.connect(host='localhost', database='riski_agentic',
                                user=user, password=password, port=5432)
        cursor = conn.cursor()

        # Check which schema/table to use
        cursor.execute(f"""SELECT EXISTS(SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'File' AND column_name = '{args.text}')""")
        has_col = cursor.fetchone()[0]

        if not has_col:
            sys.stderr.write(f"Error: {args.text} column not found in File table\n")
            sys.exit(1)

        # Fetch texts matching pgTeasers.py pattern
        cursor.execute(f"""SELECT id, {args.text} FROM "File" 
                         WHERE {args.text} IS NOT NULL AND LENGTH({args.text}) > 0""")
        rows = cursor.fetchall()

        # Build deduped text list (one per file id)
        text_map = {}
        for file_id, text in rows:
            if text:
                text_map[file_id] = text

        files = [(fid, text_map[fid]) for fid in text_map.keys()]
        texts = [text for _, text in files]

        # Filter by IDs if specified
        if args.ids:
            idset = set(int(i.strip()) for i in args.ids)
            files = [(fid, text) for fid, text in files if fid in idset]
            texts = [text for _, text in files]

        # Limit by count if specified
        limit = min(args.count, len(files)) if args.count else len(files)
        files = files[:limit]
        texts = texts[:limit]

        if not files:
            print("No texts found matching criteria")
            sys.exit(0)

        print(f"Loaded {len(texts)} texts from database")

        # Extract entities
        print(f"Extracting entities for types: {', '.join(args.entity_types)}")
        entities = extract_entities_from_texts(texts, args.entity_types)
        print(f"Extracted entities: {', '.join(f'{k}: {len(v)}' for k, v in entities.items())}")

        # Compute TF-IDF
        print("Computing TF-IDF scores...")
        tfidf_results = compute_tfidf(texts, stopwords)

        # Filter by thresholds
        filtered_results = [
            r for r in tfidf_results 
            if r["docs"] >= args.min_doc_freq and r["tfidf"] >= args.min_tfidf
        ]

        print(f"Found {len(tfidf_results)} unique words, {len(filtered_results)} after filtering")

        # Build output
        output = {
            "entities": entities,
            "words": filtered_results[:1000],  # Limit to top 1000 words
            "metadata": {
                "num_docs": len(texts),
                "num_unique_words": len(tfidf_results),
                "num_filtered_words": len(filtered_results),
                "language": args.lang,
                "min_doc_freq": args.min_doc_freq,
                "min_tfidf": args.min_tfidf,
                "entity_types": args.entity_types,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        }

        # Write output
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"Results written to {args.output}")

        # Print summary
        print("\nTop 10 words by TF-IDF:")
        for i, word_data in enumerate(filtered_results[:10]):
            print(f"  {i+1:2d}. {word_data['word']:20s} | docs: {word_data['docs']:3d} | "
                  f"total: {word_data['total']:3d} | tfidf: {word_data['tfidf']:.4f}")

        if entities:
            print("\nEntities summary:")
            for entity_type, entity_list in entities.items():
                print(f"  {entity_type}: {len(entity_list)} entities")

    except KeyboardInterrupt:
        print("\nInterrupted")
    except Exception as e:
        sys.stderr.write(f"Fatal error: {e}\n")
        import traceback
        sys.stderr.write(traceback.format_exc())
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


if __name__ == "__main__":
    main()