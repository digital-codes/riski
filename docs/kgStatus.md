# kg pipeline — status & resume guide

**Last checkpoint:** 2026-11-17 ~22:33 (end of session, change
`kg-statement-extraction`, schema spec-driven, **13/18 tasks complete**).

## Current store state (`results/kg_statements.sqlite`)

| table | rows | notes |
|---|---|---|
| `pairs` | 8,301 | 8,292 `identified` (pending), 9 `statements` (done) |
| `pair_documents` | full input-doc lists per pair (doc id + file name + role) |
| `file_meta` | chunk counts per paired doc |
| `pair_links` | 259 consecutive history links (design D10) |
| `pairs.pre_stage` | 259 pre-stage flags |
| `statements` | 17,718 `author` rows · 474 `link` rows · 9 `request` rows |
| `file_tags` | vector-tier tags (50-doc sample, threshold 0.55) |
| `tags` | 23 ris-ki tags with German descriptions |

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
* Extraction model: `mistral:latest` (~9 s, concise German),
  `granite4.2:8b` is quality-favorite but 8× slower; German-only output
  is enforced in the prompts (mistral mixed English otherwise).

## Resume — the bulk statements run (task 5 continuation)

```bash
cd /home/agent/projects/riski
nohup /home/agent/bin/python3.14 -m src.kg.kgStatements \
      --model mistral:latest > results/kg_statements_run3.log 2>&1 &
tail -f results/kg_statements_run3.log
```

* **Resume-safe:** pairs with `status='statements'` are skipped;
  the store **commits every 5 pairs** (`--commit-every`, default 5) —
  an interruption loses at most 4 pairs of LLM work.
* Throughput observed: ~10–25 s/pair (request stage only when the
  pair has no response docs; response stage runs on the 230
  protocol-attached pairs). Full corpus ≈ 25–55 h — consider
  `--limit 2000` for a representative prototype subset, or let it run
  over days in the background.
* A stuck run: `fuser results/kg_statements.sqlite` → kill PID, restart;
  the checkpoint keeps everything committed.

## Pipeline order (all stages idempotent/resumable)

```bash
python -m src.kg.kgIdentify          # 1. pair discovery        (DONE, 8301 pairs)
python -m src.kg.kgEscalate --tier 2 # 1b. regex outcome fill   (DONE)
python -m src.kg.kgChains --db       # 1c. pre_stage + links    (DONE, D10)
python -m src.kg.kgProtocols         # 1d. verified protocols   (DONE, 230 attached)
python -m src.kg.kgAuthors           # 2. party authors         (DONE, 5843 resolved)
python -m src.kg.kgTagSchema         # 3a. tag table seed       (DONE, 23 tags)
python -m src.kg.kgTags --limit N    # 3b. tagging              (sample done)
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
