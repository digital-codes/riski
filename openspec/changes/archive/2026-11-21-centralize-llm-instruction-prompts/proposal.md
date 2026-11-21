# Proposal

## Why

Every script that calls a model endpoint builds its instruction prompt verbatim in code, so prompt wording is scattered across ~15 call sites and there is no single place to see (or tune) what is being sent. There is also no way to trace an LLM call back to its origin: when a response is wrong, we cannot tell which script, function, and call site produced which prompt on which endpoint. Centralizing the instruction parts in a JSON catalog loaded next to the endpoint config (`src/remote`), and tagging every call with a prompt id + call id, makes prompts maintainable and every LLM call fully inspectable in a debug log — including results.

## What Changes

- Add a JSON prompt catalog (`config/instruction_prompts.json`) holding every instruction part currently inlined in code for prompts sent to endpoints ending in `/chat/completions` or `/systemone` (chat + decision).
- `src/remote` loads this catalog alongside its existing base-URL/key configuration and exposes prompt lookup (prompt id → instruction text) to all clients (`src.remote.chat` / `KgRemote` / `SystemOneDecoder`).
- All prompt-bearing call sites (teasers, categorise, result summarizer, report summarize, kg statement extraction, kg cross-check, kg tag SystemOne, kg tune/model-select/flag-failures, follow-ups, intent decoding, geo gate, rerank chat path) resolve their instruction from the catalog and pass a `prompt_id` plus a `call_id` (script + function + call index) as additional call parameters.
- **BREAKING**: prompt-bearing client calls (`remote.chat`, `KgRemote.chat` / `chat_json` / `systemone`, `SystemOneDecoder.decode`) now require `prompt_id` and `call_id` keyword arguments; calls made without them are flagged and logged as errors. Default mode logs the error and proceeds (soft enforcement), with an optional strict mode that raises.
- Add debug logging in `src/remote` that records every prompt-bearing call to a fixed log file with: call id, prompt id, endpoint, model, the full resolved prompt (instruction + data messages), and the full result — so any call can be inspected end-to-end.

## Capabilities

### New Capabilities
- `llm-prompt-registry`: The instruction-prompt catalog and call identification policy — catalog file schema and location, prompt-id semantics, call-id format, mandatory resolution of instruction parts from the catalog for all `/chat/completions` and `/systemone` calls, error flagging of calls without ids, and the request/result debug log for prompt-bearing LLM calls.

### Modified Capabilities
- `remote-llm-client`: The chat call surface gains `prompt_id` / `call_id` parameters, resolves instruction parts from the prompt registry instead of caller-inlined text, flags calls missing ids, and emits the debug call log entries (full prompt and result) required by the registry policy.

## Impact

- **Code**: `src/remote/__init__.py` (registry loader + enforcement + call logging + `chat()` signature), `src/kg/kgRemote.py` (chat/chat_json/systemone signatures + logging), `src/kg/kgStatements.py`, `src/kg/kgCrossCheck.py`, `src/kg/kgTagSystemOne.py`, `src/kg/kgTune.py`, `src/kg/kgModelSelect.py`, `src/kg/kgFlagFailures.py`, `src/kg/kgFollowups.py`, `src/geoGate.py`, `src/pgCategorise.py`, `src/pgTeasers.py`, `src/pgSummarize.py`, `src/pgResultSummarizer.py`, `src/pgTimeline.py` (rerank chat path), `src/pgIntentRouter.py` (`SystemOneDecoder`), `utils/bench_summary_models.py`.
- **Config**: new `config/instruction_prompts.json` catalog (built from existing verbatim prompts); no changes to `src/private.py` or env handling.
- **Logs**: new fixed debug log file under `log/` (single-line JSON entries).
- **Tests**: existing unit tests that patch/monkeypatch `remote.chat`, `KgRemote`, or `SystemOneDecoder` need updates for the new required params; new unit tests for registry loading, enforcement, and call-log output.
- **Out of scope**: embeddings and OCR calls (no instruction prompts), `KgRemote.native_chat` (ollama-native `/api/chat` route, not a `/chat/completions` endpoint; only inherits ids if trivial), ad-hoc test harnesses (`utils/test_intent_decoder_extended.py`), and any prompt-wording changes (texts are migrated verbatim).
