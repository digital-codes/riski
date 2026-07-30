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

import requests

LLM_URL = os.environ.get('RISKI_LLM_URL', 'http://localhost:11434')
LLM_MDL = os.environ.get('RISKI_LLM_MDL', 'granite4.1:3b')
MAX_RETRIES = 3
RETRY_DELAY = 2.0
DEFAULT_MAX_LEN = 200
TEXT_EXCERPT_MAXLEN = 16000
SUMMARY_TEMP = 0.2
SUMMARY_MAX_TOKENS = 500
API_TIMEOUT = 300


def parse_args():
    p = argparse.ArgumentParser(description="Generate document teasers using OpenAI compatible API")
    p.add_argument("-u", "--user", default=os.environ.get('RISKI_USER', 'wiski'), help="db user")
    p.add_argument("-p", "--password", default=os.environ.get('RISKI_PASSWORD', None), help="db password")
    p.add_argument("-c", "--count", type=int, default=None, help="number of files to process")
    p.add_argument("-l", "--lang", default="de", help="language for teaser (de=German, en=English)")
    p.add_argument("--ids", type=str, nargs='*', default=[], help="file ids")
    p.add_argument("--force", action="store_true", help="overwrite existing teaser")
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
    """

    payload = {
        "model": LLM_MDL,
        "messages": [{"role": "system", "content": prompt},{"role": "user", "content": f"Document text: {text[:TEXT_EXCERPT_MAXLEN] if len(text) > TEXT_EXCERPT_MAXLEN else text}"}],
        "temperature": SUMMARY_TEMP,
        "max_tokens": SUMMARY_MAX_TOKENS
    }
    
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = requests.post(LLM_URL + "/v1/chat/completions",
                                     json=payload,
                                     headers={"Content-Type": "application/json"},
                                     timeout=API_TIMEOUT)
            result = response.json()

            # need to check which type of response we got, and extract the content accordingly
            if 'choices' in result and len(result['choices']) > 0:
                finish_reason = result.get('choices', [{}])[0].get('finish_reason', '')
                if finish_reason == 'length':
                    sys.stderr.write(f"  Warning: response truncated (finish_reason=length), retrying with increased max_tokens\n")
                    if attempt < MAX_RETRIES:
                        payload["max_tokens"] = int(SUMMARY_MAX_TOKENS * 2)
                        time.sleep(RETRY_DELAY * (attempt + 1))
                        continue
                response = result.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
            else:
                print(f"  Unexpected API response format: {result}")
                response = ''
                
            response = response.strip('"""') if response.strip().startswith('"') else response

            if response and len(response.split()) > maxlen:
                response = ' '.join(response.split()[:maxlen])
            
            return response.strip()
            
        except requests.exceptions.HTTPError as e:
            sys.stderr.write(f"  HTTP {e.response.status_code} on attempt {attempt+1}: {str(e)[:80]}\n")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue
            return None

        except requests.exceptions.RequestException as e:
            error_type = "network"
            error_msg = str(e) + (" on attempt " + str(attempt+1) if attempt < MAX_RETRIES else "")
            sys.stderr.write(f"  {error_type} error: {str(e)[:80]}{error_msg}\n")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue
        except Exception as e:
            error_type = "other"
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
                print("  Adding column failed...")
                raise(Exception("Failed to add teaser column to File table"))

        conn.commit()

        # Filter out files with existing teasers before processing if not forcing
        if not args.force:
            cursor.execute("""SELECT id, content, length(content) FROM "File" WHERE content IS NOT NULL AND (teaser IS NULL OR LENGTH(teaser) = 0) ORDER BY length(content) DESC""")
        else:
            cursor.execute("""SELECT id, content, length(content) FROM "File" WHERE content IS NOT NULL ORDER BY length(content) DESC""")

        files = list(cursor.fetchall())

        if idset:
            files = [(f[0], f[1], f[2]) for f in files if f[0] in idset]

        limit = min(count, len(files)) if count else len(files)
        files = files[:limit]

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
                    print(f"  API failed permanently after {MAX_RETRIES} retries")
                    skipped_api += 1
                    continue
                else:
                    print(f"  Success: {len(result)} chars, {len(result.split())} words")
                    if len(result.split()) == 1:
                        print(f"  API returned only one word, skipping")
                        print("result:", result)
                        result = None
                
                if result:
                    teaser = result
                    if len(teaser.split()) > DEFAULT_MAX_LEN:
                        teaser = ' '.join(teaser.split()[:DEFAULT_MAX_LEN])
                else:
                    teaser = text[:TEXT_EXCERPT_MAXLEN].replace('\n', ' ')

            print(f"  {len(teaser)} chars, {len(str(teaser).split())} words")
            preview = str(teaser)[:40] + "..." if len(str(teaser)) > 40 else (str(teaser) or "None")
            print(f"  Preview: {preview}")

            try:
                cursor.execute("UPDATE \"File\" SET teaser = %s WHERE id = %s", (teaser, file_id))
                updated += 1

                conn.commit()
                processed += 1
            except Exception as e:
                print(f"  Failed to update file #{file_id}: {e}")

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
