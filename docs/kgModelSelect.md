# kgModelSelect — language-model selection for kg extraction (task 7.1/7.2)

Compares candidate language models for statement extraction + tagging
quality on a fixed sample pair set and records the recommendation.

## Verification harness

`src/kg/kgModelSelect.py` extracts request/response statements per
sample pair for each candidate and scores: field-fill rate, cross-check
verdict (noul), wall time per pair. A tuning report lands in
`results/kg_model_selection.md`.

## Selection history

| date | candidates | result |
|---|---|---|
| 2026-11-17 (local-era bench, 4 models) | granite4.2:8b 74 s/2295 tok · qwen3.5:4b 59 s/2191 tok · granite4.2:3b 26 s/1121 tok · mistral:latest 9 s/93 tok | mistral most concise+fastest; recorded but superseded a day later |
| 2026-11-18 (**cloud switch, decisive**) | OLC_SUMMARY `gpt-oss:20b-cloud` 3–6 s/pair · OLC_LLM glm 1.4 s | **selected: gpt-oss:20b-cloud** for extraction (German-correct, concise), OLC_LLM tried but kept as the more expensive option |

## Current default (task 7.2)

* `kgStatements` / `kgTagSystemOne` / `kgCrossCheck` default
  `--endpoint olc` → chat: `OLC_SUMMARY_MDL` (gpt-oss:20b-cloud);
  verdicts: `metis` via greenpt (SYSONE_*), switched for cost;
  diagnose-with-reason: CCLLM route (`CCLLM_MDL`).
* `--model` CLI flag overrides per run; `None` = endpoint default —
  a model offer check warns when the named model is not served.
* Local ollama candidates exist behind `kgModelSelect --include-local`
  (runner retired for kg per operator decision; see
  `docs/kgStatus.md`).

Report: `results/kg_model_selection.md`.
