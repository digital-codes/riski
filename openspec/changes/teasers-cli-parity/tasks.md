# Tasks

## 1. Database plumbing

- [x] 1.1 Replace the psycopg2 block in `src/pgTeasers.py` with
      `src.db.get_engine()` + one SQLAlchemy connection; port the schema
      guard (`File.teaser` column check/`ALTER TABLE ... ADD IF NOT EXISTS`),
      candidate-file query, `get_chunk_texts` and teaser `UPDATE` to
      `text()` statements 1:1. Verify: `python -m py_compile src/pgTeasers.py`
      and `python src/pgTeasers.py --help` no longer lists `-u`/`-p`.
- [x] 1.2 Keep per-file commit + rollback-on-failure semantics in the new
      connection handling. Verify: code review against
      src/pgTeasers.py:351-364 (commit in try, rollback in except).

## 2. LLM plumbing

- [x] 2.1 Delete `make_request` and the script-local retry/429/`finish_reason`
      logic; route `make_request` call sites through `remote.chat()` using
      the existing prompts (system prompt, temperature, max_tokens,
      `NO_THINK` → drop the ollama-only `chat_template_kwargs` in favour of
      plain `remote.chat` semantics). Verify: `rg RISKI_LLM src/pgTeasers.py`
      finds nothing.
- [x] 2.2 Map the failure checks onto `remote.chat`'s return shape: empty
      content and the `[dummy response]` placeholder count as API failure,
      preserving pre-summary → text head, reduce → concatenated
      pre-summaries, teaser failure → skip file. Verify: unit test with a
      monkeypatched `remote.chat` returning a dummy response produces the
      fallback/skip behavior.
- [x] 2.3 Add `--model` flag forwarding to `remote.chat(model=...)`; default
      `None` = configured summary model. Verify: `--help` shows the flag;
      smoke test with an invalid model name logs the remote error and the
      run continues with fallback/skip.

## 3. Tests

- [x] 3.1 Add/adjust unit tests for the teaser generator with monkeypatched
      `src.db.get_engine` and `src.remote.chat` (SQLite or fake connection):
      one pass over short/tiny documents, one map-reduce pass, dummy-response
      fallback, `--model` passthrough. Verify: `pytest src/tests -m unit -q`
      green (excluding the two known collection-error files).

## 4. Docs + integration check

- [x] 4.1 Update README usage examples for `pgTeasers` (drop
      `RISKI_PASSWORD=*** ... -u wiski`, document plain invocation and
      `--model`). Verify: `rg -- '-u wiski' README.md` finds nothing.
- [x] 4.2 Integration smoke run against the live DB:
      `python src/pgTeasers.py --count 2` (files without teasers) —
      teasers written, run summary printed, no InFailedSqlTransaction.
      Verify: output shows 2 processed and `SELECT teaser FROM "File" WHERE
      id = ...` non-empty.
- [x] 4.3 Full unit test suite + `openspec validate teasers-cli-parity`.
      Verify: no new failures vs. baseline
      (test_unit_oparlUpdate pre-existing failure exempt).
