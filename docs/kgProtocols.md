# kgProtocols — verified protocol attachment (response documents)

*Updated 2026-11-18: the "Investigation" section below explains where
the response-document mass actually lives (`File__paper__Paper`) and
what changed in the identification (structural path B, session guard,
outcome derivation).*

Stage 1b of the kg prototype (design D9). The corpus carries response
evidence in three structural places:

* per-TOP protocol files attached to Gemeinderat agenda items
  ("Protokoll GR … TOP n" — only 3 decision agenda items carry files!)
* **per-TOP protocol files linked directly to PAPERS**
  (`File__paper__Paper` — 3,346 papers, the real mass; includes
  committee variants "Protokoll_HA…", "Protokoll TOP n")
* meeting-level results protocols (`Meeting__resultsProtocol__File`,
  mostly "Anwesenheit (Protokoll)" in recent years)

Most protocol files carry no parseable structural context, so they are
located by name pattern (`Protokoll … <DD.MM.YYYY> … TOP <n>`) and
keyed by **(meeting date, TOP number)** in a one-time registry.

## Why so few pairs had response documents (investigation, 2026-11-18)

`Consultation.role = 'Entscheidung'` counts 6,764 rows; decomposition:

| slice | count | fate |
|---|---|---|
| GR consultations on request-class papers | 4,009 | pair-relevant mass |
| Ortschaftsrat/Hauptausschuss/other bodies | 2,109 | excluded (scope) |
| Haushalt THH papertypes | ~430 | excluded (class) |
| no paper link / no paper | 102 | excluded |

Of the 4,009 GR decision consultations the agenda items exist (4,285)
but carry almost no files — the per-TOP protocols hang on the **Papers**
(`File__paper__Paper`), which the earlier kgProtocols version missed.

## Identification changes (2026-11-18)

1. **Structural path B** — paper-linked protocol files are response
   candidates for that paper's pairs (same TOP/outcome verification
   gate as before).
2. **Session-date guard** — a protocol is attributed to a pair only if
   the pair's session date appears in the protocol text (or file name),
   or the name carries "GR" — otherwise a Hauptausschuss "Protokoll HA
   TOP n" could match a same-numbered GR TOP.
3. **Outcome derivation** — pairs without a resolvable outcome now get
   one from the protocol's Beschluss wording when TOP + session date
   match (stored with `signal='protocol'`, confidence 0.7; a present
   DB result always wins). +45 outcomes derived so far.

## Live-corpus verification baselines

**2026-11-17 (registry path):** TOP-number reference 219/244 (90 %);
Beschluss outcome wording match 54/81 first-pass regex (67 %); final
run: top_match 770/823, outcome 236 → **230 attached**.

**2026-11-18 (structural path B + outcome derivation):** protocols_seen
1,796, top_match 1,047, outcome match 285 → **239 attached**; +45
outcomes derived across two passes (signal `protocol`). 1,557
unattached (mostly outcome-verification misses on paper-attached
committee protocols — candidate for a later verification pass).

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
