# Tasks

## 1. Prompt catalog

- [x] 1.1 Create `config/instruction_prompts.json` (schema per design D1) holding every verbatim instruction text from the call-site inventory: `doc-classify-teaser` (pgCategorise), `geo-gate-verdict` (geoGate), `teaser-summarize` (pgTeasers), `result-summary` + `result-summary-refine` (pgResultSummarizer), `report-summarize` (pgSummarize), `kg-statement-request` + `kg-statement-response` (kgStatements), `kg-contradiction-question` + `kg-verdict-tiebreak` (kgCrossCheck), `kg-tag-question` template + one id per `_QUALIFIER_QUESTIONS` entry (kgTagSystemOne), `kg-diagnose-tune` (kgTune), `kg-model-select-extraction` (kgModelSelect), `kg-field-flags` (kgFlagFailures), `kg-followup-questions` (kgFollowups), `intent-decision-question` + `intent-gremium-slot-question` templates (pgIntentRouter), `rerank-relevance` (pgTimeline) — each entry with `description`, `text` (verbatim; dynamic templates keep `{placeholder}` tokens), `source` (file:line). Verify: `python -c "import json;...json.load(...)"` parses, ids unique, spot-check several texts against source lines.

## 2. Registry loader in src/remote

- [x] 2.1 Implement in `src/remote/__init__.py`: `_load_prompts()` at import (repo-root-anchored default path `config/instruction_prompts.json`, env override `RISKI_PROMPTS_CONFIG`, error log + empty registry on missing/unparseable file) and public `get_prompt(prompt_id)` / `has_prompt(prompt_id)`; unknown id → error log + raise. Verify with new unit tests.
- [x] 2.2 Add unit tests (new `src/tests/test_unit_prompt_registry.py` or extension of `test_unit_remote.py`): catalog loads successfully, `RISKI_PROMPTS_CONFIG` override honored, missing/broken file logs an error and registry is empty, `get_prompt` on unknown id logs error and raises, text returned verbatim. Verify: `python -m pytest src/tests/test_unit_prompt_registry.py -m unit`.

## 3. Call identification, enforcement, and call-log core in src/remote

- [x] 3.1 Add to `src/remote/__init__.py`: `validate_call_ids(prompt_id, call_id, context)` (soft mode: error log + flagged entry; strict mode via env `REMOTE_PROMPT_ENFORCE=strict`: raises before send) and extend `chat()` / `_post()` with `prompt_id=` / `call_id=` kwargs; `chat()` echoes `prompt_id`/`call_id` in its returned dict. Verify with unit tests.
- [x] 3.2 Add shared `log_llm_call(endpoint, model, payload, result, prompt_id, call_id, status, duration_ms)` writing single-line JSON entries to `log/llm_debug.log` (repo-root-anchored like apiTrace, thread-locked single `write()`, full fidelity, opt-out env `REMOTE_LLM_LOG=0`, every write in try/except → warning on failure, never alters the call). Verify with unit tests.
- [x] 3.3 Unit tests in `src/tests/test_unit_remote.py` (extend, HTTP mocked): chat call with ids → `log/llm_debug.log` entry (temp dir override) contains call_id, prompt_id, endpoint, model, full prompt payload, full result; missing ids → error-level log + flagged entry, call proceeds (soft); strict env → call raises without HTTP request; logging failure does not alter the result; response dict contains the echoed ids. Verify: `python -m pytest src/tests/test_unit_remote.py -m unit`.

## 4. Migrate src.remote chat call sites

- [x] 4.1 `src/pgTeasers.py`: resolve system prompt via `get_prompt("teaser-summarize")` (keep existing `.format`-style interpolation of `{maxlen}`/`{lang_setting}` at the call site), add `prompt_id` + `call_id` (`pgTeasers.make_request.1`, and chunked map-reduce site index) to the `remote.chat` call; update `src/tests/test_unit_pgTeasers.py`. Verify: `python -m pytest src/tests/test_unit_pgTeasers.py -m unit`.
- [x] 4.2 `src/pgCategorise.py`: replace `LLM_SYSTEM_PROMPT` with `get_prompt("doc-classify-teaser")`, add ids (`pgCategorise._llm_classify.1`); update affected unit test. Verify: `python -m pytest src/tests -k categorise -m unit`.
- [x] 4.3 `src/geoGate.py`: resolve prompt template via `get_prompt("geo-gate-verdict")` in `build_prompt()`, add ids (`geoGate._chat.1`); update affected tests. Verify: `python -m pytest src/tests -k geogate -m unit`.
- [x] 4.4 `src/pgSummarize.py`: replace system prompt with `get_prompt("report-summarize")` (report placeholder formatted at call site), add ids (`pgSummarize.request_summary.1`); update `src/tests/test_unit_pgSummarize.py`. Verify: `python -m pytest src/tests/test_unit_pgSummarize.py -m unit`.
- [x] 4.5 `src/pgResultSummarizer.py`: replace `_SYSTEM_PROMPT` / `_REFINE_SYSTEM_PROMPT` with `get_prompt("result-summary")` / `get_prompt("result-summary-refine")`, add ids for both call paths (`pgResultSummarizer.summarize.1` / `.2`); update `src/tests/test_unit_pgResultSummarizer.py`. Verify: `python -m pytest src/tests/test_unit_pgResultSummarizer.py -m unit`.
- [x] 4.6 `src/pgTimeline.py`: resolve rerank chat prompt via `get_prompt("rerank-relevance")`, add ids on the chat-path `requests.post` call (`pgTimeline.call_reranking_chat_model.1`), keep native rerank path unchanged; update affected tests if the chat path is unit-tested. Verify: `python -m pytest src/tests -k timeline -m unit`.
- [x] 4.7 `utils/bench_summary_models.py`: forward the captured prompt ids/call ids (from the ResultSummarizer spy) into the direct `remote._post("chat/completions", ...)` call. Verify: script imports cleanly (`python -c "import utils.bench_summary_models"` style check) and ids are present in the captured payload.

## 5. Migrate KgRemote family (kg pipeline)

- [x] 5.1 `src/kg/kgRemote.py`: extend `chat()`, `chat_json()` (both fallback routes per design D6), and `systemone()` with `prompt_id=` / `call_id=` kwargs; delegate validation to `src.remote.validate_call_ids` and result/payload logging to `src.remote.log_llm_call` (systemone payload = full questions dict; result = returned answers); keep retries/timeouts/raise behavior unchanged. Unit tests: call with ids logged to call log; missing ids flagged (soft) / raise (strict). Verify: `python -m pytest src/tests -k kg_remote or -k kgremote -m unit`.
- [x] 5.2 `src/kg/kgStatements.py`: resolve `_REQUEST_PROMPT` / `_RESPONSE_PROMPT` via `get_prompt`, add ids (`kgStatements.extract.1` / `.2`); update `src/tests/test_unit_kg_*` covering statements. Verify: `python -m pytest src/tests -k statement -m unit`.
- [x] 5.3 `src/kg/kgCrossCheck.py`: add ids on `remote.systemone` (`kgCrossCheck.<fn>.1`, prompt id `kg-contradiction-question`) and the chat fallback + tiebreak retry (`kg-verdict-tiebreak`; distinct call indices); update `src/tests/test_unit_kg_crosscheck.py`. Verify: `python -m pytest src/tests/test_unit_kg_crosscheck.py -m unit`.
- [x] 5.4 `src/kg/kgTagSystemOne.py`: format `kg-tag-question` template per tag, resolve qualifier questions via their catalog ids, pass ids on `systemone` call (`kgTagSystemOne.assign.1`); update affected tests. Verify: `python -m pytest src/tests -k tagsystemone -m unit`.
- [x] 5.5 `src/kg/kgTune.py`, `src/kg/kgModelSelect.py`, `src/kg/kgFlagFailures.py`, `src/kg/kgFollowups.py`: resolve their prompts from the catalog (`kg-diagnose-tune`, `kg-model-select-extraction`, `kg-field-flags`, `kg-followup-questions`) and add ids at each call site (including `kgModelSelect` request/response indices and `kgTune.for_diagnose` route); remove the dead `remote_chat` import in `kgFollowups`; update related `test_unit_kg_*`. Verify: `python -m pytest src/tests -k kg -m unit`.

## 6. Migrate SystemOneDecoder (intent routing)

- [x] 6.1 `src/pgIntentRouter.py`: `SystemOneDecoder.decode()` accepts `prompt_id` / `call_id` (`pgIntentRouter.IntentRouter.decode.1` / `ask` call site index, prompt id `intent-decision-question`), validates + logs via the shared `src.remote` helpers; `build_questions()` formats the catalog templates (`intent-decision-question`, `intent-gremium-slot-question`) with intent name/description; update `src/tests/test_unit_pgIntentRouter.py`. Verify: `python -m pytest src/tests/test_unit_pgIntentRouter.py -m unit`.

## 7. Integration verification and docs

- [x] 7.1 Run the full unit suite green: `python -m pytest src/tests -m unit`; fix any fallout from the new required ids in patched tests. Verify: exit code 0.
- [x] 7.2 End-to-end smoke: with a reachable chat endpoint, issue one migrated call (e.g. via `src/tests/test_core.py` chat smoke, or `python -m src.pgTeasers` on a small doc if credentials exist); inspect `log/llm_debug.log` and confirm one entry with `call_id`, `prompt_id`, endpoint, model, full prompt, and full result; grep the catalog id for that site. Verify: log entry is a valid single-line JSON with all fields.
- [x] 7.3 Compliance check: search `src/` for remaining un-migrated prompt-bearing definitions (e.g. residual inline system prompts at `/chat/completions` / `/systemone` call sites) and confirm each of `remote.chat`, `remote._post` (chat/systemone paths), `KgRemote.chat/chat_json/systemone`, `SystemOneDecoder.decode` now requires ids (error-log test exists). Verify: grep shows no verbatim instruction constants left at those call sites.
- [x] 7.4 Document in `README.md` (section covering `src/remote`): the `config/instruction_prompts.json` catalog, `prompt_id`/`call_id` contract, `RISKI_PROMPTS_CONFIG`, `REMOTE_PROMPT_ENFORCE`, `REMOTE_LLM_LOG`, and `log/llm_debug.log` inspection. Verify: documented env-var names appear in code and the doc matches implementation.

## Workflow follow-up

- Archive the change after review requirements are satisfied (`openspec archive` flow).
- Consider switching `REMOTE_PROMPT_ENFORCE` default to strict once all call sites are migrated (design open question).
