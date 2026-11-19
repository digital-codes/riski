# HF endpoint evaluation (2026-11-19) — not adopted (report)

Operator request: test the two `HF_*` models in `src/private.py`
(`HF_SUMMARY` = Nemotron-3.5-Lightning-30B chat endpoint,
`HF_SYSONE` = `vllm-d3-GGUF` SystemOne endpoint) as faster
replacements; adoption only after performance review.

## Results

### HF_SYSONE (`https://…huggingface.cloud/v1/systemone`)

| check | result |
|---|---|
| route | works at `/v1/systemone` (root 404 — the proposal's plain URL needed the `/v1/systemone` suffix) |
| latency (warm) | **0.32–0.42 s** — comparable to greenpt metis (0.32 s) |
| determinism | identical noul across repeats ✓ |
| **state-size bug** (corrected after operator's log hint) | states above the deployment's **physical batch size (512 tokens)** fail with HTTP 500 `"input (N tokens) is too large to process"` — measured: 384-token state OK, 657 and 1,937 fail. My earlier "silent truncation" conclusion was WRONG: the test states I used were accidentally near-empty (pair without statements → summary `(keine Angaben)`, source 0 chars), so the identical 103-token counts were legitimate. The operator's log line (`n_tokens = 103, truncated = 0`) corroborates: no truncation, small inputs simply counted. **Impact: real 5k-char document states CANNOT be served** — loud 500s, not silent wrong answers. Usable only with chunked pre-processing (score ≤400-token sections, aggregate) — extra pipeline complexity for a 0.37 s endpoint. |

The operator's server log snippet (`n_tokens = 103, truncated = 0`)
prompted the re-test that found the true behavior.

### HF_SUMMARY (chat)

- **HTTP 503 Service Unavailable** on every request over ~15 minutes
  (instant 503, `models` route also 503) — the endpoint is paused/errored
  on the HF side, cannot be woken from here. No performance measurement
  possible.

## Comparison vs. current production routes

| route | latency (real state) | state handling |
|---|---|---|
| greenpt metis (`SYSONE_*`) | 0.32 s @ 5k chars | full state ✓ (noul 0.195 on the same sample where HF gives 0.032 from a snippet) |
| **HF_SYSONE** | 0.37 s | **truncates at ~100 tokens ✗** |
| OLC_SUMMARY chat | 3–6 s | full state ✓ |

## Update (same day, later): HF_SUMMARY came online

The operator resumed the endpoint. Bench results:

| test | result |
|---|---|
| extraction JSON (German, fixture) | 2.8–3.7 s — **equal to OLC gpt-oss** (~3 s), correct German, correct values |
| 5k-char document | 3.2 s (no degradation vs short input) |
| diagnose (verdict+reason, real failed pair w/ real statement) | 4.2–8.5 s, **excellent reason quality** — named the exact field and the contradicting source fact ('Kurzfristig zusätzliche Kindergartenplätze schaffen … durch Beschluss zur Aufgabe des Container-Kindergartens widerlegt') |
| caveat seen | on a pair whose rendered summary was EMPTY it answered 'keine Angaben bereitgestellt' (correct behavior, not a defect) |

**Verdict revision:** HF_SUMMARY (Nemotron-3.5-Lightning-30B) is a
qualified replacement for **diagnose/verdict-with-reason** calls
(CCLLM role): equal latency to glm-5.3, richer reasons, and it does
not consume the ollama.com cloud budget. For statement extraction it
is at parity with OLC_SUMMARY — no pressing reason to switch the bulk
extractor mid-run. HF_SYSONE stays rejected (state truncation).

## Decision (final, operator 2026-11-19)

**HF endpoints not used for kg.** HF_SYSONE refuses states >512 tokens
(batch-size 512 in the vllm deployment) — full-document verdicts are
impossible without a chunk-and-aggregate wrapper. HF_SUMMARY would be
on-par for chat, but ollama.com OLC_SUMMARY stays within budget.

**Cost note (operator):** the highest kg cost driver is the *decision
model* (SystemOne calls per pair for cross-checks and per document for
tagging — many small calls), not the LLM extraction chat (fewer, larger
calls). The greenpt metis route was chosen for exactly that reason
(half the OLC_SYSONE price). Any future cost reduction should target
the decision-model volume first (e.g. batch more questions per call —
as the 23-tags-in-one-call tagger already does — or cache verdicts per
(pair, doc-state-hash)).
HF_SUMMARY is unavailable (503) and cannot be evaluated. Recommend:

1. keep greenpt metis for SystemOne verdicts, OLC_SUMMARY for
   extraction/diagnose chat;
2. re-test HF endpoints later if the operator restarts/rescales them
   (the 503 may just be an idle-paused endpoint; the state-truncation
   bug however looks like a model/serve configuration issue in the
   vllm-d3-GGUF deployment and would need fixing there first).
