#!/usr/bin/env python3
"""
riskiTeasers.py - Generate document teasers using OpenAI compatible API

Usage:
    RISKI_PASSWORD=*** python pgTeasers.py -u wiski -c 10
    RISKI_PASSWORD=*** python pgTeasers.py -u wiski -c 50 -l en --force
    
"""

import argparse
import os
import sys
import json
import time

try:
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
except ImportError:
    print("Install psycopg2: pip install psycopg2-binary")
    sys.exit(1)

try:
    import urllib.request
except ImportError:
    import urllib.request

LLM_URL = os.environ.get('RISKI_LLM_URL', 'http://localhost:11434')
LLM_MDL = os.environ.get('RISKI_LLM_MDL', 'granite4.1:3b')
MAX_RETRIES = 3
RETRY_DELAY = 2.0
DEFAULT_MAX_LEN = 200
TEXT_EXCERPT_MAXLEN = 2000
SUMMARY_TEMP = 0.2
SUMMARY_MAX_TOKENS = 500
API_TIMEOUT = 90


def parse_args():
    p = argparse.ArgumentParser(description="Generate document teasers using OpenAI compatible API")
    p.add_argument("-u", "--user", default=os.environ.get('RISKI_USER', 'wiski'), help="db user")
    p.add_argument("-p", "--password", default=os.environ.get('RISKI_PASSWORD', None), help="db password")
    p.add_argument("-c", "--count", type=int, default=None, help="number of files to process")
    p.add_argument("-l", "--lang", default="de", help="language for teaser (de=German, en=English)")
    p.add_argument("--ids", type=str, nargs='*', default=[], help="file ids")
    p.add_argument("--force", action="store_true", help="overwrite existing teaser")
    p.add_argument("--no-fallback", action="store_true", help="no fallback for API failures")
    p.add_argument("--max-bar", type=int, default=50, help="progress bar width")
    return p.parse_args()


def getcreds(args):
    if not args.password:
        sys.stderr.write("error: no password. Use RISKI_PASSWORD or -p\n")
        sys.exit(1)
    return args.user, args.password


def make_request(text, lang="de", maxlen=DEFAULT_MAX_LEN):
    """Make API request to OpenAI compatible endpoint with retry logic."""
    lang_map = {"de": "German", "en": "English"}
    lang_setting = lang_map.get(lang.lower(), "German")
    
    prompt = f"""Summarize this document in 3-5 sentences. 
Maximum {maxlen} words. Focus on main topic.
Language must be: {lang_setting} (do not mix languages)

Text excerpt:
{text[:TEXT_EXCERPT_MAXLEN] if len(text) > TEXT_EXCERPT_MAXLEN else text}

Summary:"""

    payload = {
        "model": LLM_MDL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": SUMMARY_TEMP,
        "max_tokens": SUMMARY_MAX_TOKENS
    }
    
    for attempt in range(MAX_RETRIES + 1):
        try:
            result = json.loads(urllib.request.urlopen(
                urllib.request.Request(LLM_URL + "/v1/chat/completions",
                                       data=json.dumps(payload).encode(),
                                       headers={"Content-Type": "application/json"},
                                       method="POST"),
                timeout=90).read())

            response = result.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
            response = response.strip('"""') if response.strip().startswith('"') else response

            if response and len(response.split()) > maxlen:
                response = ' '.join(response.split()[:maxlen])
            
            return response.strip()
            
        except urllib.error.HTTPError as e:
            sys.stderr.write(f"  HTTP {e.code} on attempt {attempt+1}: {str(e)[:80]}\n")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue
            return None
            
        except Exception as e:
            error_type = "network" if isinstance(e, urllib.error.URLError) else "other"
            error_msg = str(e) + (" on attempt " + str(attempt+1) if attempt < MAX_RETRIES else "")
            sys.stderr.write(f"  {error_type} error: {str(e)[:80]}{error_msg}\n")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue
    
    return None


def has_existing_teaser(cursor, file_id):
    """Check if file has teaser content."""
    try:
        cursor.execute("""SELECT EXISTS(SELECT 1 FROM File_with_teasers WHERE id = %s AND teaser IS NOT NULL AND LENGTH(teaser) > 0)""", (file_id,))
        return cursor.fetchone()[0]
    except:
        try:
            cursor.execute("""SELECT EXISTS(SELECT 1 FROM "File" WHERE id = %s AND teaser IS NOT NULL AND LENGTH(teaser) > 0)""", (file_id,))
            return cursor.fetchone()[0]
        except:
            return False


def main():
    args = parse_args()
    user, password = getcreds(args)
    conn = None
    cursor = None
    schema = "File"
    files = []
    idset = set(int(i.strip()) for i in args.ids) if args.ids else set()
    count = args.count

    print(f"Connecting to riski_agentic (language: {args.lang}, retries: {MAX_RETRIES})...")

    try:
        conn = psycopg2.connect(host='localhost', database='riski_agentic', user=user, password=password, port=5432)
        cursor = conn.cursor()

        cursor.execute("SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name = 'File' AND column_name = 'teaser')")
        has_col = cursor.fetchone()[0]

        if not has_col:
            print("  Attempting to add teaser column...")
            try:
                cursor.execute("ALTER TABLE \"File\" ADD COLUMN IF NOT EXISTS teaser TEXT")
                cursor.execute(f"GRANT UPDATE ON \"File\" TO {user}")
            except psycopg2.errors.UndefinedColumn:
                print("  Creating File_with_teasers table...")
                cursor.execute("""CREATE TABLE IF NOT EXISTS File_with_teasers (id BIGINT PRIMARY KEY, content TEXT, teaser TEXT)""")
                schema = "File_with_teasers"

        conn.commit()

        if schema == "File_with_teasers":
            cursor.execute("""SELECT id, content, length(content) FROM File_with_teasers ORDER BY length(content) DESC""")
        else:
            cursor.execute("""SELECT id, content, length(content) FROM "File" WHERE content IS NOT NULL ORDER BY length(content) DESC""")

        files = list(cursor.fetchall())

        if idset:
            files = [(f[0], f[1], f[2]) for f in files if f[0] in idset]

        limit = min(count, len(files)) if count else len(files)
        files = files[:limit]

        # Filter out files with existing teasers before processing if not forcing
        if not args.force:
            files = [f for f in files if not has_existing_teaser(cursor, f[0])]

        print(f"\nProcessing {len(files)} documents... (language: {args.lang})")
        if not args.force:
            print("(filtered: only files without existing teaser)")
        print(f"Retries enabled: {MAX_RETRIES} attempts per file")
        print("="*60)

        processed = 0
        updated = 0
        skipped_api = 0
        total = len(files)

        for i, (file_id, content, size) in enumerate(files):

            try:
                text = str(content)
                words = text.split()
                word_count = len(words)
            except:
                text = ""
                word_count = 0

            if word_count <= DEFAULT_MAX_LEN:
                print(f"[\n[{i+1:3d}] File #{file_id}: short ({word_count} words)")
                teaser = text.replace('\n', ' ')
            else:
                print(f"[\n[{i+1:3d}] File #{file_id}: processing ({size} bytes) [l={args.lang}]...")
                result = make_request(text, args.lang, DEFAULT_MAX_LEN)
                if result is None:
                    if args.no_fallback:
                        print(f"  API failed permanently after {MAX_RETRIES} retries")
                        skipped_api += 1
                        continue
                    else:
                        print(f"  API failed, using fallback")
                else:
                    print(f"  Success: {len(result)} chars, {len(result.split())} words")
                
                if result:
                    teaser = result
                    if len(teaser.split()) > DEFAULT_MAX_LEN:
                        teaser = ' '.join(teaser.split()[:DEFAULT_MAX_LEN])
                else:
                    teaser = text[:1500].replace('\n', ' ')

            print(f"  {len(teaser)} chars, {len(str(teaser).split())} words")
            preview = str(teaser)[:40] + "..." if len(str(teaser)) > 40 else (str(teaser) or "None")
            print(f"  Preview: {preview}")

            if schema == "File_with_teasers":
                cursor.execute("INSERT INTO File_with_teasers(id, content, teaser) VALUES (%s, %s, %s) ON CONFLICT(id) DO UPDATE SET teaser = excluded.teaser",
                              (file_id, str(content)[:200000], teaser))
            else:
                cursor.execute("UPDATE \"File\" SET teaser = %s WHERE id = %s", (teaser, file_id))
                updated += 1

            conn.commit()
            processed += 1

            pct = int(100 * processed / total) if total > 0 else 0
            bar = '#' * int(50 * processed / total) if total > 0 else '#' * 50
            bar += '.' * (50 - len(bar))
            sys.stdout.write(f'\r[{bar}] {processed:3d}/{total:3d} ({pct:3d}%)')
            sys.stdout.flush()

        sys.stdout.write('\n')
        print(f"\nDone: {processed} processed, {updated} updated, {skipped_api} skipped (API failures)")
        print(f"==========================")

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
