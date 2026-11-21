# Design

## Context

Three independent clients issue prompt-bearing calls today:

- `src/remote` (`chat()` → `_post("chat/completions", ...)`): used by `pgCategorise`, `geoGate`, `pgTeasers`, `pgResultSummarizer`, `pgSummarize`, and `utils/bench_summary_models.py` (direct `_post`).
- `src/kg/kgRemote.py` (`chat`, `chat_json`, `systemone`): used by `kgStatements`, `kgCrossCheck`, `kgTagSystemOne`, `kgTune`, `kgModelSelect`, `kgFlagFailures`, `kgFollowups`.
- `src/pgIntentRouter.py` `SystemOneDecoder` (httpx → `/v1/systemone`): serves `apiServer` `/ask`.

Instruction texts are inlined at each call site (catalog in proposal.md). `src/remote` already centralizes endpoint config by loading git-ignored `src/private.py` (env → attribute → default). Debug tracing exists (`src/apiTrace.py` → `log/api_debug.log`) but covers API request flow only and deliberately truncates payloads — it does not record prompts or results. Existing tests monkeypatch `remote.chat` / `KgRemote` with calls carrying no id parameters.

Constraints carried into this design: texts migrate **verbatim** (prompt-wording changes are out of scope), unit tests must run without network, and `src/remote` must stay import-clean (it imports only stdlib + requests; `kgRemote` and `pgIntentRouter` may import `src.remote` without cycles).

## Goals / Non-Goals

**Goals:**
- One JSON catalog holding every instruction part, loaded by `src/remote` next to the endpoint config.
- `prompt_id` + `call_id` on every prompt-bearing `/chat/completions` and `/systemone` call, enforced with error flagging (soft default, strict mode).
- One debug log (written by code living in `src/remote`) exposing every prompt-bearing call: ids, endpoint, model, full prompt, full result.
- Keep per-client HTTP behavior (retries, timeouts, fallbacks, dummy responses) unchanged.

**Non-Goals:**
- No prompt rewording; no consolidation of near-identical instruction texts into shared ids unless verbatim-equal.
- No unification of the three HTTP clients into one transport (see D4).
- Embeddings, OCR, and `KgRemote.native_chat` (ollama-native `/api/chat`) are untouched; embeddings/OCR carry no instruction prompts.
- Ad-hoc harnesses (`utils/test_intent_decoder_extended.py`, `scripts/test_kg_api.py`) are not migrated; they are test tooling outside the production call graph.

## Decisions

**D1 — Catalog format and location**: `config/instruction_prompts.json`, schema:
```json
{
  "version": 1,
  "prompts": {
    "<prompt-id>": {
      "description": "<short human description>",
      "text": "<verbatim instruction text>",
      "source": "<file:line of the original inlined text>"
    }
  }
}
```
Rationale: the user explicitly asked for JSON; `config/` already holds the other declarative inputs; `version` allows future schema evolution like `_get_first` did for endpoint names. Alternative (YAML) rejected despite YAML precedent in `config/` — JSON keeps the file copy-pasteable into log tools and matches the request. Dynamic instruction templates (per-intent questions, per-tag questions, `{max_words}` limits) are stored with `{placeholder}` tokens; only call sites that already interpolated values call `.format(**values)` on the resolved text. Static texts are never formatted.

Prompt id inventory (kebab-case, capability-prefixed; exact texts extracted at implementation time):
`doc-classify-teaser`, `geo-gate-verdict`, `teaser-summarize`, `result-summary`, `result-summary-refine`, `report-summarize`, `kg-statement-request`, `kg-statement-response`, `kg-contradiction-question`, `kg-verdict-tiebreak`, `kg-tag-question` (template), `kg-tag-qualifier-*` (one id per qualifier question), `kg-diagnose-tune`, `kg-model-select-extraction`, `kg-field-flags`, `kg-followup-questions`, `intent-decision-question` (template), `intent-gremium-slot-question`, `rerank-relevance`. Unique ids even for similar texts; dedupe only if verbatim-equal.

**D2 — Loader in `src/remote`**: `_load_prompts()` runs at module import next to `_load_private()`, reading `config/instruction_prompts.json` anchored at the repo root (`Path(__file__).resolve().parents[2]`, same anchoring approach as `apiTrace` for `log/`), overridable via `RISKI_PROMPTS_CONFIG`. Public API: `get_prompt(prompt_id)` → text, plus `has_prompt(prompt_id)`. Missing/unparseable file: error log, empty registry; `get_prompt` on an unknown id logs an error and raises — an unresolvable id is a code bug and must not silently send a wrong prompt (spec: no silent fallback). Alternative (lazy per-call file read) rejected: one consistent in-memory copy, matching private.py behavior.

**D3 — Call id format**: `<script>.<function>.<index>`, e.g. `pgTeasers.make_request.1`, `kgCrossCheck.crosscheck_doc.1`. Script = importable module filename stem, function = function/method name, index = 1-based static ordinal of the distinct call site within that function (loop iterations share the site). Rationale: statically defined ids make log entries correlatable across runs and greppable in code, matching "script name + function name + call index". Alternative (runtime sequence counter) rejected: unstable across reruns and restarts.

**D4 — Enforcement + logging point: shared helpers in `src/remote`, per-client parameters**: extend each client's signature (`remote.chat`, `remote._post`, `KgRemote.chat/chat_json/systemone`, `SystemOneDecoder.decode`) with `prompt_id=` / `call_id=` keyword args, all funneling into two shared `src/remote` functions:
- `validate_call_ids(prompt_id, call_id, context)` → error log + debug-log flagged entry (soft) or `ValueError` (strict, env `REMOTE_PROMPT_ENFORCE=strict`).
- `log_llm_call(endpoint, model, payload, result, prompt_id, call_id, status, duration_ms)` → the single writing implementation of the call log.

Rationale: satisfies "debug logging in remote" for *all* three clients literally in `src/remote`, keeps signatures additive and HTTP behavior intact. Alternative (route every client's HTTP through `remote._post`) deferred — it would change retry/timeout/httpx semantics in one sweep and risks silent regressions in the kg pipeline; revisit later.

**D5 — Call debug log**: file `log/llm_debug.log` (separate from `api_debug.log` — different stream, different retention needs; apiTrace keeps its truncated API-flow contract). One entry per call, written after the result arrives:
```json
{"ts": "<ISO-8601>", "call_id": "...", "prompt_id": "...", "endpoint": "...", "model": "...",
 "prompt": {...payload sent...}, "result": {...parsed response...}, "status": "ok|error", "duration_ms": 0, "error": "..."}
```
Rules: enabled by default (opt-out env `REMOTE_LLM_LOG=0`), full fidelity (no truncation — the log exists to inspect payloads), single-line JSON written with a single `write()` + thread lock (same append-safety approach as apiTrace), all writes wrapped in try/except so logging can never break a call (failure → warning via the regular logger). Missing-id calls get an entry with `"error": "missing prompt_id/call_id"` immediately, plus a second entry after completion when proceeding in soft mode.

**D6 — What counts as "prompt-bearing"**: every call through `remote.chat` / `remote._post("chat/completions")` / `KgRemote.chat` / `KgRemote.chat_json` / `KgRemote.systemone` / `SystemOneDecoder.decode`. `embed*`, `ocr`, and `native_chat` are exempt (no instruction-prompt endpoints in scope). `KgRemote.chat_json` may fall back to `native_chat`; when it does, the same prompt id travels with the call for logging continuity but no enforcement change is added to native_chat itself.

**D7 — Response correlation**: `remote.chat` adds `prompt_id` and `call_id` into its returned dict (and the bench tool passes them through `_post`), so downstream code and tests can assert the origin of a result.

**D8 — Migration of inlined texts**: implementation runs in two passes per module: (1) extract the verbatim text into the catalog with a `source` pointer; (2) replace the inlined constant with `get_prompt("<id>")` (plus `.format(**values)` where the site already interpolated) and add `prompt_id=` / `call_id=` to the call. This guarantees wording is untouched — extraction is a copy, verified by unit tests that compare call-time instruction text to the catalog value.

## Risks / Trade-offs

- [Log volume: full 16k-char prompts × every call grows `log/llm_debug.log` quickly] → opt-out env `REMOTE_LLM_LOG=0`; document rotation (plain append, no rotation in scope — same as existing `results/*.log` habit).
- [Placeholder formatting on catalog text can crash on stray braces in verbatim text] → only sites that already format their text use `.format`; `.format` is applied by the call site, never inside the loader; static texts stored/used as-is.
- [Soft default could leave non-compliant calls unnoticed] → error-level log entries plus flagged debug entries; strict mode (`REMOTE_PROMPT_ENFORCE=strict`) available for CI/verification runs, satisfying "calls … must be flagged".
- [Signature churn breaks existing monkeypatched tests] → migration updates each affected test file in the same task as its module; ids become part of the tested contract (new unit tests assert errors when omitted).
- [kgTagSystemOne / pgIntentRouter generate many per-noun questions from vocab data] → only the sentence templates enter the catalog (`kg-tag-question`, `intent-decision-question`); runtime values are formatted in; one prompt id stays stable even as vocab/intents.yaml content changes.

## Migration Plan

1. Add catalog file + loader + `validate_call_ids` + `log_llm_call` + extended signatures in `src/remote` (purely additive; no call site changes yet — soft enforcement logs existing un-id'd calls as errors, nothing breaks).
2. Migrate call sites module by module (`src.remote` users first, then `KgRemote` users, then `SystemOneDecoder`), updating the tests of each module in the same step.
3. Run `python -m pytest src/tests -m unit`; run integration suite only where live credentials exist.
4. Rollback: revert is trivial — ids are additive kwargs, log file is independent, catalog unused if call sites are reverted; no data or API-contract changes.

## Open Questions

None blocking. Post-implementation question (do not affect specs or tasks): whether strict mode should become the default once all call sites are migrated.
