# kgProtocols — verified protocol attachment (response documents)

Stage 1b of the kg prototype (design D9). The corpus carries response
evidence in two places:

* per-TOP protocol files attached to Gemeinderat agenda items
  ("Protokoll GR … TOP n")
* meeting-level results protocols (`Meeting__resultsProtocol__File`,
  mostly "Anwesenheit (Protokoll)" in recent years)

Most of the 8,6k "Protokoll … TOP n" files carry **no structural link**
to papers, so they are located by name pattern
(`Protokoll … <DD.MM.YYYY> … TOP <n>`) and keyed by
**(meeting date, TOP number)** in a one-time registry.

A protocol is attached to a pair (role `response`) **only when both
checks pass** (spec: protocol verification and response attachment):

1. **TOP match** — the protocol head text references the pair's agenda
   item TOP number (`Punkt <n> der Tagesordnung`).
2. **Result match** — the outcome wording in the protocol's
   `Beschluss:` section is compatible with the pair's outcome
   (vocabulary mapping, e.g. "Kenntnisnahme" → `kenntnisnahme`).

Unverified protocols are never attributed — they are counted as
`not_attached` in the run summary instead.

## Live-corpus verification baseline (2026-11-17)

| check | result |
|---|---|
| TOP-number reference found | 219/244 structural-attachment sample (90 %) |
| Beschluss outcome wording matches | 54/81 first-pass regex (67 %); misses are heading-split artifacts, non-outcome result values ("keine Mitteilungen", "Aushang im Foyer") |
| final run (registry path, all pairs) | top_match 770/823, outcome 236 → **230 attached** with role `response` |

## Usage

```bash
# full run (resumable, upserts only)
python -m src.kg.kgProtocols

# limit the number of pairs processed
python -m src.kg.kgProtocols --limit 500

# custom store
python -m src.kg.kgProtocols --store path/to/kg_statements.sqlite
```

## Output

* `pair_documents` — new rows with role `response` (protocol files)
* `results/kg_protocols_stats.json` — verification/attachment counters

## Notes

* Outcome vocabulary files live in `config/kg_vocabulary.yaml`
  (`results` / `outcome_anchors`); extend them to catch new wording.
* The decision-model fallback for ambiguous "Beschluss:" sections is
  planned in the kgStatements stage.
