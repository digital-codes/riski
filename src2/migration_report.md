# Migration Report

This document records the proposal, changes, and outcomes for each module migrated from `src/` to `src2/`.

## pgTagMgr.py

**Proposal:** Centralise PostgreSQL engine/metadata via `src2.db`. Make `engine` optional; fallback to shared engine. Replace per‑instance table‑existence checks with `table_exists`.

**Changes:** Imported `get_engine`, `Base`, `table_exists`; adjusted `__init__` signature; removed direct `create_engine` usage; kept original public API.

**Result:** File imported without errors (tested with `python - <<''\nimport src2.pgTagMgr\n''`).

## pgNameVecs.py

**Proposal:** Use shared DB utilities and centralised embedding call `src2.remote.embed`.

**Changes:** Imported `get_engine`, `Base`, `table_exists`, `embed`; removed custom `_embed`; optional engine argument; vector column defined lazily.

**Result:** Imported successfully; basic `NameVecs` instantiation works with default DB URL.
## pgSummarize.py

**Proposal:** Replace the raw ``requests`` chat call with the shared ``src2.remote.chat`` helper and remove hard‑coded endpoint / API‑key constants.

**Changes:** Imported ``chat`` from ``src2.remote``; created ``request_summary`` wrapper; removed ``MISTRAL_*`` environment variables and manual retry logic.

**Result:** Script runs (import‑time check passes).  Summaries are generated using the configured localhost chat service (granite‑4.1‑3b‑Q8_0).


