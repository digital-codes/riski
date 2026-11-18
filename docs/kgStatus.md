# kg pipeline — status & resume guide

**Last checkpoint:** 2026-11-17 ~22:33 (end of session, change
`kg-statement-extraction`, schema spec-driven, **13/18 tasks complete**).

## Current store state (`results/kg_statements.sqlite`)

*Updated 2026-11-18 ~11:00 — bulk extraction running (see below).*

| table | rows | notes |
|---|---|---|
| `pairs` | 8,301 | two groups: ~216 response-bearing pairs processed FIRST, then the response-less mass; checkpoint-commits every 5 pairs |
| `pair_documents` | full input-doc lists per pair; response role = verified protocols (267 pairs) |
| `file_meta` | chunk counts per paired doc |
| `pair_links` | 259 consecutive history links (design D10) |
| `pairs.pre_stage` | 259 pre-stage flags |
| `statements` | `author` 17,718 · `link` 474 · `request`/`response` growing with the bulk run |
| `crosschecks` | d3:2b SystemOne verdicts (noul) — task 6.1 done, extension runs on demand |
| `file_tags` | vector-tier tags (50-doc sample, threshold 0.55) |
| `tags` | 23 ris-ki tags with German descriptions |

Key events since the last checkpoint:

* **d3:2b integrated via `POST /v1/systemone`** (the model's ONLY
  serving route — chat/generate/completions unsupported by design, see
  https://ollama.com/library/d3): cross-checks 9/9 + 10/10 passed with
  noul scores ≤ 0.18. Language-model fallback kept (`--verdict-model`).
* **Response-document mass found** (`File__paper__Paper`, 3,346
  papers): kgProtocols structural path B + session-date guard + outcome
  derivation from protocol wording → 267 verified-response pairs
  (details in `docs/kgProtocols.md`).
* **Ballot screenshots integrated** (`kgAbstimmung.py`, design D13):
  631 per-TOP vote screenshots attached (with OCR-clipped-digit
  cross-checks vs the textual outcome; `pair_documents.verify_note`
  carries the detail) → **792 pairs with response docs**;
  `docs/kgAbstimmung.md`.
* **Extraction order**: response-bearing pairs first (user decision);
  restart commands below.

Stats JSONs: `results/kg_identification_stats.json`,
`results/kg_protocols_stats.json` · run logs:
`results/kg_statements_run.log`, `results/kg_statements_run2.log`.

## Verified ollama facts (important for resume)

* Runner context must be bounded: `kgRemote` uses **native**
  `/api/chat` with `options.num_ctx` (default 16384; smoke tests at
  8192). A hot model with 80k ctx eats 15.9 GB VRAM — unload first:
  `curl -s localhost:11434/api/generate -d '{"model":"<m>","keep_alive":0}' -X POST`
* **Stop the previous model before switching** — concurrent hot models
  share GPU/CPU and stall everything.
* Extraction model (2026-11-18, user decision): **local ollama is
  retired for kg** — everything runs on the OLC cloud models:
  extraction `gpt-oss:20b-cloud` (OLC_SUMMARY, ~3–6 s/pair, concise
  German), cross-check verdicts `metis` via greenpt SYSONE_URL (SystemOne —
  **switched 2026-11-18: same protocol, half the OLC_SYSONE cost,
  verified on 8 live pairs — 7/8 identical verdict directions, the one
  deviation a borderline 0.548/0.158 case**),
  tagging `clef:27b-cloud` one-call-all-tags. `--endpoint olc` is the
  scripts' default; german-only output is enforced in the prompts
  (the earlier mistral runs mixed English otherwise). Local candidates
  remain documented for history + `kgModelSelect --include-local`.

## Resume — the bulk statements run (task 5 continuation)

**Running since 2026-11-18 10:46** (`results/kg_statements_run4.log`,
PID file `results/kg_statements_run.pid`): response-bearing pairs
first, then the rest; `--commit-every 5` keeps every interruption loss
below 5 pairs. Monitor with:

```bash
tail -f results/kg_statements_run4.log
python -m src.kg.kgStats   # or quick check:
python3 -c "from src.kg.kgStore import KgStore; s=KgStore('results/kg_statements.sqlite'); print(s.pair_counts_by_status())"
```

**Restart after new protocol attachments** (the queue is built at
start; new response pairs need a restart to join the front):

```bash
kill $(cat results/kg_statements_run.pid)   # stops at next checkpoint
# restart:
nohup /home/agent/bin/python3.14 -m src.kg.kgStatements \
      --model mistral:latest > results/kg_statements_run4.log 2>&1 &
```

**Cross-check a batch anytime** (concurrent with extraction; store has
busy_timeout 120 s):

```bash
python -m src.kg.kgCrossCheck --limit 20 --tuning-report --iteration <n>
```

## Tagging: SystemOne one-call tier (2026-11-18)

`kgTagSystemOne.py` assigns ALL 23 ris-ki tags in a single
`/v1/systemone` call per document (noul score 0..1 = tag confidence,
default threshold 0.5) plus qualifier sub-questions (Neubau / Sanierung
= reconstruction / Erweiterung / Rückbau / Ausbau for the construction
tags). Verified on a 20-doc sample: 17 tagged, 37 assignments, high
confidences (0.91–0.96), plausible topics (Rahmenplan → city
development 0.96, Sanierung qualifier 0.94). Endpoint `olc` ≈ 1.1–4 s
per doc (≈ 4.4k input tokens); `ollama` local d3:2b works but is much
slower (24 s, poor token packing). Cross-check extraction verdicts use
the same SystemOne route.

```bash
python -m src.kg.kgTagSystemOne --endpoint olc          # bulk (resumable)
python -m src.kg.kgTagSystemOne --endpoint olc --limit 50
python -m src.kg.kgTagSystemOne --min-confidence 0.6     # stricter re-run
```

## Pipeline order (all stages idempotent/resumable)

```bash
python -m src.kg.kgIdentify          # 1. pair discovery        (DONE, 8301 pairs)
python -m src.kg.kgEscalate --tier 2 # 1b. regex outcome fill   (DONE)
python -m src.kg.kgChains --db       # 1c. pre_stage + links    (DONE, D10)
python -m src.kg.kgProtocols         # 1d. verified protocols   (DONE, 230 attached)
python -m src.kg.kgAuthors           # 2. party authors         (DONE, 5843 resolved)
python -m src.kg.kgTagSchema         # 3a. tag table seed       (DONE, 23 tags)
python -m src.kg.kgTagSystemOne --endpoint olc  # 3b. tagging (bulk-ready)
python -m src.kg.kgStatements        # 4. statements            (IN PROGRESS — bulk run)
python -m src.kg.kgCrossCheck        # 5. round-trip check      (task 6.1, TODO)
python -m src.kg.kgModelSelect       # 6. model comparison      (task 7.1, TODO)
python -m src.kg.kgExport            # 7. JSON export           (task 8.1, TODO)
python -m src.kg.kgStats             # stats report refresh
```

## Remaining tasks (openspec/changes/kg-statement-extraction/tasks.md)

- [ ] 6.1 `kgCrossCheck.py` — render response statements to sample text,
      fact-compat verdict vs source chunks (d3:2b first pass)
- [ ] 7.1/7.2 `kgModelSelect.py` — granite4.2:8b vs qwen3.5:4b vs
      mistral:latest on a fixed sample; record choice in docs
- [ ] 8.1 `kgExport.py` — JSON export of the store
- [ ] 8.2 End-to-end integration run + summary report

Unit tests: `/home/agent/bin/python3.14 -m pytest src/tests/test_unit_kg_*.py -q`
(44 tests, all green at checkpoint).
