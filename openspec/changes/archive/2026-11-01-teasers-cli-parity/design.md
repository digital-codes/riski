# Design

## Context

`pgTeasers.py` predates the shared layers: it opens `psycopg2.connect(
host='localhost', database='riski_agentic', user=..., password=...)` directly
(taking `-u`/`-p` CLI credentials) and implements its own HTTP client
(`make_request`: manual retry loop, 429 handling, finish_reason=length
re-growth) against `RISKI_LLM_URL`/`RISKI_LLM_MDL`. Every other backfill
script uses `src.db.get_engine()` and `src.remote`, which resolves the
summary model via `SUMMARY_URL`/`SUMMARY_MDL` with `LLM_URL`/`LLM_MDL`
fallbacks (see `src/remote/__init__.py:55-66`). The teaser content logic
(chunk-aware map-reduce, ceilings, filters) is current and stays.

## Goals / Non-Goals

**Goals:**
- pgTeasers connects like every other script: `src.db.get_engine()`, zero
  credential flags.
- Teaser LLM calls go through `src.remote.chat()` (summary model by default),
  inheriting shared retry/backoff/429 handling.
- `--model` passthrough for one-off runs, mirroring `remote.chat(model=...)`.

**Non-Goals:**
- No changes to teaser content behavior: map-reduce pipeline, word budget,
  120% teaser ceiling, `--force`/`--chunked-only`/`--ids`/`--oparlid`
  filters, `File.teaser` storage, per-file commit + rollback fix.
- No changes to `src.remote` or `src.db` themselves.
- No backfill/rerun of existing teasers (already-generated teasers stand).

## Decisions

1. **SQLAlchemy connection instead of raw psycopg2**
   The chunk-selection queries and the teaser `UPDATE` become SQLAlchemy
   `text()` statements on one engine connection. Rationale: the hand-rolled
   psycopg2 block exists only to avoid the shared layer; rewriting the
   queries 1:1 keeps the diff mechanical. Alternative considered: keeping
   psycopg2 but deriving credentials from `src.db` — rejected because it
   leaves two connection idioms in the codebase and the SQL is trivial.

2. **`remote.chat()` replaces `make_request`, pre-summary retry loop retired**
   `remote._post` already does exponential backoff, `Retry-After` handling
   and `REMOTE_MAX_RETRIES`. The `finish_reason=length` re-growth path from
   `make_request` is dropped: `remote.chat` returns content only, and the
   existing word-budget truncation (`' '.join(words[:maxlen])`) plus the
   ceiling cap already bound the output. Alternative: port the re-growth
   logic — rejected as dead weight; truncation has been the effective
   behavior in practice.

3. **`--model` as the only new flag**
   `pgTeasers -m/--model` forwards to `remote.chat(model=...)`. `None`
   (default) keeps the configured summary model. `RISKI_LLM_URL`/`RISKI_LLM_MDL`
   env support is removed — deployments configure the summary model via
   `SUMMARY_URL`/`SUMMARY_MDL` (or legacy `LLM_URL`/`LLM_MDL`, which
   `src.remote` still honours), so nothing is lost.

4. **Failure semantics unchanged, mapped onto `remote.chat` return shape**
   `remote.chat` never raises — it returns a dummy response on final failure.
   The existing per-chunk/per-document "failed" checks become content
   emptiness checks (dummy content `[dummy response]` is treated as failure),
   preserving the current "pre-summary failed → text head", "reduce failed →
   concatenated pre-summaries", "teaser failed → skip file" behavior.

## Risks / Trade-offs

- [Dummy-response masking: `remote.chat` swallows errors] → Treat
  `[dummy response]` content as an API failure in the failed-detection
  helpers; error detail is logged by `src.remote` anyway.
- [Behavioral drift: model change may alter teaser voice/length] → Word
  budget and ceiling caps are model-independent; existing teasers are not
  regenerated unless `--force`.
- [README/deployment docs reference `-u wiski`] → Update usage examples in
  the same change; `RISKI_PASSWORD`-based invocation stops working, which is
  the intended breaking change.

## Migration Plan

1. Rewrite `pgTeasers.py` (DB + LLM plumbing only).
2. Update README usage examples (`-u wiski` → plain invocation, note
   `--model`).
3. Run unit tests; smoke-run `--count 2` against the live DB.
4. Rollback: single-file revert (`git revert`); DB state unaffected.

## Open Questions

(none)
