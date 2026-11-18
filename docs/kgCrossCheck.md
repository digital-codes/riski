# kgCrossCheck — round-trip fact verification

Stage 5 (task 6.1, design D12): renders extracted statements to a short
German sample text and asks a model whether the statement set is
fact-compatible with the pair's source chunks (style irrelevant, facts
count). Verdicts land in the `crosschecks` table.

## Tuning loop (design D12)

The stage runs **right after each extraction batch** on the same sample
pairs; recurring mismatch classes drive extraction/checker adjustments
(max 3 iterations). Each run appends an iteration summary to
`results/kg_crosscheck_tuning.md`.

### Iteration history (2026-11-18)

| iteration | change | result |
|---|---|---|
| 0 | chat/generate against d3:2b | fails — the d3-renderer model serves ONLY the SystemOne route (`POST /v1/systemone`, cf. https://ollama.com/library/d3) |
| 0-fix | verdict via language model (`mistral:latest`, `--verdict-model`) | baseline 7/9 passed (77%) |
| 1→2 | checker fixes, not extraction fixes: (a) verdict prompt only fails on real contradictions — missing facts are a shortening, not an error; (b) metadata fields (meeting_date/document_id/file_names/author) are no longer rendered into the compared text — DB provenance must not be judged as model output | **9/9 passed (100%)** |
| 3 | **d3:2b via SystemOne as primary verdict** (`KgRemote.systemone`, noul score ≥ 0.5 = contradiction), language-model fallback if unreachable | **9/9 passed (100%)** with noul scores 0.019–0.182 — the spec's decision model is now the first-class verdict path |

## Usage

```bash
# sample batch (appends to the tuning report)
python -m src.kg.kgCrossCheck --limit 20 --tuning-report --iteration 1

# re-check pairs with existing verdicts
python -m src.kg.kgCrossCheck --force --limit 9

# verdict model (default mistral:latest — see note above re d3:2b)
python -m src.kg.kgCrossCheck --verdict-model qwen3.5:4b

# language-model tie-break when the default verdict is not passed/failed
python -m src.kg.kgCrossCheck --tiebreak-model granite4.2:8b
```

## Output

* `crosschecks` — `pair_key → verdict (passed|failed) + reason`
* mismatch classes in the tuning report: english-leakage,
  invented-cost, wrong-date, wrong-executor, hallucinated-fact, other
* checkpoint-commits every 10 pairs
