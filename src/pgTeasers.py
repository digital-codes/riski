#!/usr/bin/env python3
"""
riskiTeasers.py - Generate document teasers using OpenAI compatible API

Usage:
    RISKI_PASSWORD=*** python pgTeasers.py -u wiski -c 10
    RISKI_PASSWORD=*** python pgTeasers.py -u wiski -c 50 -l en --force

Teaser generation is chunk-aware (change: fix-result-summarizer): chunked
documents are summarized map-reduce style — per-chunk pre-summaries are
reduced into the single document teaser — so the teaser covers the whole
document, not just the head chunk stored in File.content. Every storage
path caps the teaser at 120% of the maximum chunk size (~9.600 chars),
because teasers are consumed as summarizer context.
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
LLM_MDL = os.environ.get('RISKI_LLM_MDL', 'granite4.1:8b')
LLM_API_KEY = os.environ.get('RISKI_LLM_API_KEY', "123")
MAX_RETRIES = 5
RETRY_DELAY = 2.0
DEFAULT_MAX_LEN = 200
TEXT_EXCERPT_MAXLEN = 16000
SUMMARY_TEMP = 0.2
SUMMARY_MAX_TOKENS = 500
API_TIMEOUT = 300
# teaser length ceiling (change: fix-result-summarizer): teasers are punted
# into the summarizer, so they must not exceed the max chunk size by a
# large factor — 120% of the chunk hard limit.
MAX_CHUNK_CHARS = int(os.environ.get('RISKI_CHUNK_HARD', '8000'))
TEASER_CEILING = int(MAX_CHUNK_CHARS * 1.2)
# map-reduce pre-summary budget per chunk (change: fix-result-summarizer)
CHUNK_PRE_SUMMARY_WORDS = 40
# reasoning-capable serving backends (vLLM) emit a separate `reasoning`
# phase that eats the token budget before any content — disabled via
# chat_template_kwargs when RISKI_LLM_NO_THINK is set
NO_THINK = os.environ.get('RISKI_LLM_NO_THINK', '') not in ('', '0', 'false')

print(f"Using LLM_URL={LLM_URL}, LLM_MDL={LLM_MDL}, MAX_RETRIES={MAX_RETRIES}, SUMMARY_MAX_TOKENS={SUMMARY_MAX_TOKENS}")

def parse_args():
    p = argparse.ArgumentParser(description="Generate document teasers using OpenAI compatible API")
    p.add_argument("-u", "--user", default=os.environ.get('RISKI_USER', 'wiski'), help="db user")
    p.add_argument("-p", "--password", default=os.environ.get('RISKI_PASSWORD', None), help="db password")
    p.add_argument("-c", "--count", type=int, default=None, help="number of files to process")
    p.add_argument("-l", "--lang", default="de", help="language for teaser (de=German, en=English)")
    p.add_argument("--ids", type=str, nargs='*', default=[], help="file ids")
    p.add_argument("--oparlid", type=str, default=None, help="process only files where column oparlId equals this value")
    p.add_argument("--force", action="store_true", help="overwrite existing teaser")
    p.add_argument("--chunked-only", action="store_true",
                   help="process only chunked documents (File_chunks rows exist) — "
                        "targeted backfill of head-only teasers (change: fix-result-summarizer)")
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
    if NO_THINK:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = requests.post(LLM_URL + "/v1/chat/completions",
                                     json=payload,
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {LLM_API_KEY}"},
                                     timeout=API_TIMEOUT)

            # Rate limiting: honour Retry-After before touching the body —
            # a 429 response has no choices and would otherwise produce an
            # empty/garbage teaser.
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and str(retry_after).replace(".", "", 1).isdigit() \
                    else RETRY_DELAY * (2 ** attempt)
                sys.stderr.write(f"  Rate limited (429) on attempt {attempt+1}: waiting {delay:.1f}s\n")
                if attempt < MAX_RETRIES:
                    time.sleep(delay)
                    continue
                return None

            response.raise_for_status()
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


def _cap_teaser(teaser):
    """Enforce the teaser length ceiling on every storage path (change:
    fix-result-summarizer): teasers are summarizer context and must not
    exceed the max chunk size by a large factor."""
    return (teaser or "")[:TEASER_CEILING]


def get_chunk_texts(cursor, oparl_key):
    """All chunk texts of a chunked document, in chunk order; ``None`` when
    the document has no chunk rows (non-chunked)."""
    cursor.execute(
        'SELECT fc.text FROM "File_chunks" fc '
        'JOIN "File" f ON f.sid = fc.file_sid '
        'WHERE f."oparlKey" = %s ORDER BY fc.chunk_index', (oparl_key,))
    texts = [r[0] for r in cursor.fetchall() if r[0]]
    return texts or None


def summarize_to_teaser(text, lang="de"):
    """Summarize document text into a teaser (single call, existing prompt
    and retry flow incl. the fallback truncation) — ceiling-capped."""
    text = text or ""
    words = text.split()
    if len(words) <= DEFAULT_MAX_LEN:
        return _cap_teaser(text.replace('\n', ' '))
    result = make_request(text, lang, DEFAULT_MAX_LEN)
    if result and len(result.split()) > 1:
        teaser = result
        if len(teaser.split()) > DEFAULT_MAX_LEN:
            teaser = ' '.join(teaser.split()[:DEFAULT_MAX_LEN])
    else:
        teaser = text[:TEXT_EXCERPT_MAXLEN].replace('\n', ' ')
    return _cap_teaser(teaser)


def generate_chunked_teaser(chunk_texts, lang="de"):
    """Aggressive map-reduce teaser for chunked documents (change:
    fix-result-summarizer): per-chunk pre-summaries reduced into the ONE
    document teaser. A chunk whose pre-summary call fails contributes a
    truncated text head instead — the document still gets a teaser. The
    reduce call always runs (pre-summaries are bullets, never the teaser);
    when it fails the concatenated pre-summaries serve as the teaser."""
    pre = []
    for i, chunk in enumerate(chunk_texts, 1):
        s = make_request(chunk, lang, CHUNK_PRE_SUMMARY_WORDS)
        if s and len(s.split()) > 1:
            pre.append(s.strip())
        else:
            sys.stderr.write(f"  chunk {i}/{len(chunk_texts)}: pre-summary failed, using text head\n")
            pre.append(' '.join((chunk or "").split()[:CHUNK_PRE_SUMMARY_WORDS * 2]))
        print(f"    chunk {i}/{len(chunk_texts)}: {len(s or '')} chars")
    reduction_input = "\n".join(f"- {p}" for p in pre if p)
    result = make_request(reduction_input, lang, DEFAULT_MAX_LEN)
    if result and len(result.split()) > 1:
        teaser = result
        if len(teaser.split()) > DEFAULT_MAX_LEN:
            teaser = ' '.join(teaser.split()[:DEFAULT_MAX_LEN])
    else:
        teaser = " ".join(pre)
    return _cap_teaser(teaser)


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

        where_clauses = ["content IS NOT NULL"]
        query_params = []

        # Filter out files with existing teasers before processing if not forcing.
        if not args.force:
            where_clauses.append("(teaser IS NULL OR LENGTH(teaser) = 0)")

        # Keep exact case in column name: "oparlId".
        if args.oparlid is not None:
            where_clauses.append("\"oparlKey\" = %s")
            query_params.append(args.oparlid)

        # targeted backfill: only chunked documents (change: fix-result-summarizer)
        if args.chunked_only:
            where_clauses.append(
                'EXISTS (SELECT 1 FROM "File_chunks" fc WHERE fc.file_sid = "File".sid)')

        query = f'''SELECT id, "oparlKey", content, length(content) FROM "File" WHERE {' AND '.join(where_clauses)} ORDER BY length(content) DESC'''
        cursor.execute(query, tuple(query_params))

        files = list(cursor.fetchall())

        if idset:
            files = [f for f in files if f[0] in idset]

        limit = min(count, len(files)) if count else len(files)
        files = files[:limit]

        print(f"\nProcessing {len(files)} documents... (language: {args.lang})")
        if not args.force:
            print("(filtered: only files without existing teaser)")
        if args.oparlid is not None:
            print(f"(filtered: only files with oparlId='{args.oparlid}')")
        print(f"Retries enabled: {MAX_RETRIES} attempts per file")
        print("="*60)

        processed = 0
        updated = 0
        skipped_api = 0
        total = len(files)

        for i, (file_id, oparl_key, content, size) in enumerate(files):

            try:
                text = str(content)
                words = text.split()
                word_count = len(words)
            except:
                text = ""
                word_count = 0

            # chunk-aware teaser (change: fix-result-summarizer): chunked
            # documents are summarized map-reduce over ALL chunks so the
            # single teaser covers the whole document, not just the head
            # chunk stored in content.
            chunk_texts = get_chunk_texts(cursor, oparl_key)
            if chunk_texts:
                print(f"[\n[{i+1:3d}] File #{file_id} ({oparl_key}): chunked, "
                      f"{len(chunk_texts)} chunks ({size} bytes) [l={args.lang}]...")
                teaser = generate_chunked_teaser(chunk_texts, args.lang)
                if not teaser:
                    print("  API failed permanently after retries")
                    skipped_api += 1
                    continue
            else:
                if word_count <= DEFAULT_MAX_LEN:
                    print(f"[\n[{i+1:3d}] File #{file_id}: short ({word_count} words)")
                    teaser = _cap_teaser(text.replace('\n', ' '))
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
                        teaser = _cap_teaser(text[:TEXT_EXCERPT_MAXLEN].replace('\n', ' '))

            print(f"  {len(teaser)} chars, {len(str(teaser).split())} words")
            preview = str(teaser)[:40] + "..." if len(str(teaser)) > 40 else (str(teaser) or "None")
            print(f"  Preview: {preview}")

            try:
                cursor.execute("UPDATE \"File\" SET teaser = %s WHERE id = %s",
                               (_cap_teaser(teaser), file_id))
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
