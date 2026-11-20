# Model limitations & remaining failures in the kg pipeline (status 2026-11-20)

Cross-check totals: 8,094 verdicts — **7,758 passed (95.9 %)**, 277
failed (3.4 %), 59 skipped (no source text). Remaining-failure
breakdown and the model characteristics behind them.

## 1. The models in the pipeline and their known limits

| role | model | strengths observed | limitations observed |
|---|---|---|---|
| statement extraction | **gpt-oss:20b-cloud** (OLC_SUMMARY) | concise correct German JSON, 3–6 s/pair, 0.25 % hard errors over 8,301 pairs | occasionally infers dates/costs from context rather than verbatim text (prompt now enforces verbatim-only; residual rate ≈ 1–2 %) |
| inline verdict | **metis** via greenpt (SystemOne noul) | 0.2–0.4 s, deterministic, cheap enough for per-pair verdicts | **over-strict on long bilingual states**: noul ≥ 0.65 even when statement matches source verbatim (measured 1/3 of strong-failures judged `passed` by the LLM re-check); produces no reason — failures need the diagnose pass |
| failure diagnosis | **glm-5.3-flash:cloud** (CCLLM) | names the exact field + contradicting source fact (best reason quality of all tested) | 8–10 s/pair; also flags plausible-but-not-verbatim costs (strictness closer to the spec than metis) |
| tagging | **clef:27b-cloud** (SystemOne, 23 questions/1 call) | one call per doc, calibrated confidences, qualifiers | generic Beschlussvorlagen/procurement texts score 0.2–0.4 — correctly untagged, but the doc_key-ascending queue front-loads them (starvation optics) |

## 2. Remaining 277 failures — classes

| class | count | nature | disposition |
|---|---|---|---|
| noul ≥ 0.65, undiagnosed | 133 | metis over-strictness + real cost/date slips mixed (sampled: 1/3 passed on LLM re-check, 2/3 genuine field errors — mostly `involved_cost` attributed to plan-account numbers and `start_date` confusions) | candidates for the glm diagnose pass (kgTune) — the D12 loop has 1 iteration left in its budget |
| noul 0.5–0.65, undiagnosed | 132 | borderline zone | same; expect majority to pass on re-check |
| tune: model-limitation | 10 | real date/cost extraction slips (diagnosed, pairs reset for re-extraction) | re-extracted with sharpened prompts; verdicts refresh on next apply |
| tune: other | 2 | verdicts without class | individually reviewable |

## 3. What we deliberately accept

* **Statements are extractive summaries, not transcriptions** — fields
  stay empty when the source is silent; the cross-check enforces
  "no contradiction" rather than "no omission".
* **Verdict≠extractor disagreement is the QA signal, not noise** — the
  D12 loop uses it to tune; a fully green board would mean the checker
  is under-sensitive.
* **59 skipped** = documents without text (scanned PDFs without OCR
  text or empty attachments) — correctly untagged/unverdicted.
* **Ballot OCR numbers** (JA/NEIN/ENTHALTUNG) carry explicit
  clipped-digit warnings in `pair_documents.verify_note`; they are
  hints, never `kgps:decides` evidence.

## 4. Recommended next steps (optional, not blocking archive)

1. Run `kgTune --limit 265` (1 diagnose pass over both undiagnosed
   classes — ~35 min on CCLLM): expected to move 60–70 % of the
   borderline class to passed and turn the rest into actionable
   field-error statistics.
2. If a strong-noul bias persists after that, lower the metis
   contradiction threshold for long states (state-length-aware
   threshold, e.g. 0.5 → 0.6 above 3k chars) — one-line change in
   `kgCrossCheck`, empirically grounded in the KSC/MIRO false
   positives.
3. Consider a "cost/source" re-check pass for `involved_cost` values:
   the recurring genuine-error class is plan-account vs project-cost
   confusion (40 M € case) — a targeted prompt line costs nothing.
