# Instruction prompt registry

> change: centralize-llm-instruction-prompts — every instruction part of the
> prompts sent to `/chat/completions` or `/systemone` endpoints lives in one
> JSON catalog; every prompt-bearing model call carries a prompt id + call id
> and is recorded — with full prompt and full result — in a per-call debug
> log.

## Catalog

`config/instruction_prompts.json`, loaded by `src/remote` at import
(resolution order for endpoint config: env → `src/private.py` → default; the
catalog follows the same spirit):

```json
{
  "version": 1,
  "prompts": {
    "<prompt-id>": {
      "description": "<short human description>",
      "text": "<verbatim instruction text>",
      "source": "<file:line the text was extracted from>"
    }
  }
}
```

Rules that keep the catalog trustworthy:

- **Texts are verbatim.** Instruction wording stays exactly as it was inlined
  in code — tuning prompt wording is an explicit, catalog-only edit
  (call sites no longer carry instructional text).
- **Ids are stable and unique** (kebab-case, capability-prefixed, e.g.
  `teaser-summarize`, `kg-contradiction-question`). Similar texts keep
  separate ids unless verbatim-equal.
- **Dynamic data never enters the catalog.** Templates carry `{placeholder}`
  tokens only where the site already interpolated values
  (`{maxlen}/{lang_setting}`, `{max_words}`, `{summary}/{source}`,
  tag/intent question templates); purely static texts are stored untouched.
  Formatting happens at the call site, never inside the loader.
- A missing/unparseable catalog file is logged as an error at startup;
  prompt ids then fail resolution (error log + raise) — no silent fallback
  prompt.

## Access from code

Public API in `src.remote`:

```python
from src.remote import get_prompt, has_prompt

prompt = get_prompt("teaser-summarize").format(maxlen=200, lang_setting="German")
```

## Call identification

Every prompt-bearing call to `/chat/completions` or `/systemone` carries:

- **`prompt_id`** — the catalog id of the call's instruction part.
- **`call_id`** — origin of the request in the format
  `<script>.<function>.<call-index>` (1-based, static ordinal of the call
  site within the function, stable across runs), e.g.
  `pgTeasers.make_request.1`, `kgCrossCheck.check_pair.2`.

Covered client surfaces (identification + logging flow into the shared
helpers in `src.remote`):

| client | calls |
|---|---|
| `src.remote` | `chat()`, `_post()` (direct-transport callers, e.g. benchmarks) |
| `src/kg/kgRemote.py` | `chat()`, `chat_json()` (both routes), `systemone()` |
| `src/pgIntentRouter.py` | `SystemOneDecoder.decode()` |

Enforcement (`REMOTE_PROMPT_ENFORCE`):

- default (**soft**): a call missing ids proceeds but is logged as an error,
  and the call-debug entry is flagged;
- **strict** (`REMOTE_PROMPT_ENFORCE=strict`): the request is refused with a
  `ValueError` before it is sent — for CI/verification runs.

## Per-call debug log

`log/llm_debug.log` (repo-root anchored; on by default, opt-out
`REMOTE_LLM_LOG=0`, path override `REMOTE_LLM_LOG_PATH`). One single-line
JSON entry per call, full fidelity:

```json
{"ts": "2026-11-21T19:44:37.123+01:00", "call_id": "pgResultSummarizer.summarize.1",
 "prompt_id": "result-summary", "endpoint": "https://api.mistral.ai/v1/chat/completions",
 "model": "mistral-small-2603", "prompt": {...payload...}, "result": {...},
 "status": "ok", "duration_ms": 4211.9}
```

Log-write failures never alter a call (single warning, then the log latches
off). Inspect with, for example:

```bash
jq 'select(.prompt_id=="kg-contradiction-question")' log/llm_debug.log   # one prompt everywhere
jq 'select(.call_id=="pgTeasers.make_request.1") | .result' log/llm_debug.log
jq -r 'select(.error != null) | [.ts, .error] | @tsv' log/llm_debug.log  # flagged/failed calls
```

This stream is deliberately separate from the API flow trace
(`src/search/apiTrace.py` → `log/api_debug.log`), which keeps truncated,
size-capped entries for the HTTP request path.

## Adding a new LLM call site

1. Add a catalog entry (verbatim text, kebab-case id, `source` pointer).
2. Resolve it at the call site: `remote.get_prompt("<id>")[.format(**values)]`.
3. Pass `prompt_id="<id>", call_id="<script>.<function>.<index>"` on the
   call (`remote.chat`, `remote._post`, or the KgRemote/decoder equivalents).
4. Keep `get_prompt` raising on unknown ids — that is the intended
   no-wrong-prompt safety net.
