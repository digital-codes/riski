# kgAbstimmung — ballot-screenshot vote evidence (design D13)

Stage 1c (design D13, 2026-11-18): the 2,299 `File.name LIKE
'Abstimmung%'` files are per-TOP **ballot screenshots** — KPanel/QUINTA
format with the TOP number, a session timestamp, and the vote tallies
(JA / NEIN / ENTHALTUNG counts plus party seat maps). This is the
"ballot result with votes" evidence class the spec calls out for the
Karlsruhe deployment.

## Attachment gate (no outcome-wording check — the screenshot IS the result)

1. **TOP match** — the file name (97 %+ carry a TOP number, e.g.
   "Abstimmungsergebnis GR_TOP 23") or the screenshot text names the
   pair's agenda-item TOP.
2. **Session match** — the screenshot text date (e.g. "21 Oct 2025",
   "27.06.2018", ISO) equals the pair's meeting date, **or** the
   deterministic `File.date` equals it (preferred signal — verified to
   be the session date on samples), or the paper link ties the file to
   the pair's paper.
3. **OCR vote-count cross-check** (operator requirement: numbers in the
   JA/NEIN/ENTHALTUNG blobs may suffer clipped digits — an 8 read as a
   0 or vice versa). The parsed majority is compared with the pair's
   textual outcome:
   * `zugestimmt` / `beschlossen` → JA must dominate,
   * `abgelehnt` → NEIN must dominate.
   * consistent → `ok` (note recorded), contradiction → `warn` (the
     attachment is KEPT — the screenshot is the evidence — but the note
     explicitly says the counts are a hint only), no expectation → `n/a`.

## Persistence (schema note)

Per-attachment detail lives in **`pair_documents.verify_note`** — an
additive idempotent column (`KgStore.ensure_verify_note`, same pattern
as `pairs.pre_stage`). No table rebuild, no rerun of kgIdentify
(upserts enrich existing pairs). Example notes:

```
ok:   OCR-votes consistent (mehrheit_ja): JA=45, NEIN=0, ENTHALTUNG=0
warn: OCR-votes CONTRADICT outcome 'zugestimmt' (mehrheit_nein vs
      mehrheit_ja); likely clipped digits — counts kept as hint only:
      JA=40, NEIN=80, ENTHALTUNG=0
```

## Full-corpus run (2026-11-18)

| metric | value |
|---|---|
| pairs scanned | 6,047 |
| candidates seen | 266k name-registry hits (TOP-keyed) |
| session matches | 633 |
| **attached ballot screenshots** | **631** (205 ok / 25 warn / 401 n.a.) |
| pairs with response docs (total, all mechanisms) | **792** |

Stats: `results/kg_abstimmung_stats.json` · runtime ≈ 4 min (read-only
PG + SQLite upserts), fully resumable.

## Usage

```bash
python -m src.kg.kgAbstimmung                  # full run (idempotent)
python -m src.kg.kgAbstimmung --limit 250      # sample
python -m src.kg.kgAbstimmung --report results/kg_abstimmung_stats.json
```

## Restart note

The statement-extraction queue is built at process start — after
kgAbstimmung attaches new response documents, **restart the bulk
extractor** so the pairs join the response-first queue:

```bash
kill $(cat results/kg_statements_run.pid)
nohup /home/agent/bin/python3.14 -m src.kg.kgStatements \
      --endpoint olc > results/kg_statements_run5.log 2>&1 &
```
