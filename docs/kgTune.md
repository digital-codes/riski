# kgTune — failure diagnosis & prompt tuning (design D14)

> change: centralize-llm-instruction-prompts — the diagnose instruction
> lives in `config/instruction_prompts.json` (id `kg-diagnose-tune`); the
> call carries `prompt_id`/`call_id` and is inspectable in
> `log/llm_debug.log` (see `docs/prompt-registry.md`). Prompt wording
> itself is tuned in the catalog now, not in module code.

The inline cross-check verdict (d3:2b/metis via SystemOne) yields only a
noul score — no reason. The first tuning report was therefore empty of
substance. `kgTune.py` closes that gap: failed pairs are re-examined by
a **reason-generating language model on the dedicated CCLLM route**
(`CCLLM_URL/MDL/KEY` in `src/private.py`, operator-added 2026-11-19;
`KgRemote.for_diagnose()` returns None while unset and both call sites
fall back to the generic OLC chat).

## What a diagnose pass does (per failed pair)

1. renders the statement summary vs. source spans,
2. asks the diagnose model for `verdict / reason / system_issue`
   (`prompt | checker | ocr | model`),
3. writes `tune:<class>: <reason>` into `crosschecks.reason`
   (replacing the bare `systemone noul=…`),
4. **upgrades** verdicts that the sharper criteria judge compatible
   (checker strictness was the largest failure class — 24 of 40 in the
   first pass),
5. **resets** genuinely-failed pairs to `identified` (with
   `--apply-reset`) so the next `kgStatements` run re-extracts them
   with the sharpened prompts.

## Tuning loop ledger (D12, max 3 iterations)

| iteration | change | effect |
|---|---|---|
| 1 | diagnose pass over 40 failed pairs (was: blind noul) | 24 checker-strictness → passed; real issues: session-dates in start/end_date, partially invented costs |
| 2 | extraction prompts sharpened: verbatim-only costs/dates, planned-measure dates only; 7 model-limitation pairs reset | pending re-extraction (queued for next run) |
| 3 | (reserved) | |

Report ledger: `results/kg_crosscheck_tuning.md`.

## The 429 fix (operational, same session)

`KgRemote.systemone()` had no 429 handling; the tagger and the inline
cross-check share the decision endpoint, and rate-limit storms silently
zeroed tagging batches (`docs=300 tagged=0`). `systemone()` now
retries with `Retry-After`/backoff. Additional operational note: the
untagged `doc_key`-ascending tail (10k–60k range) is dominated by
generic Beschlussvorlagen/procurement documents that legitimately score
below the 0.5 threshold — queue reordering or a second lower-confidence
pass are the proposed remedies (decision open).

## Usage

```bash
python -m src.kg.kgTune --limit 40 --apply-reset   # diagnose + reset
python -m src.kg.kgTune --limit 0                  # all failed pairs
```

Safe in parallel with the bulk runs (SQLite busy_timeout 300 s after
the run9 lock lesson — keep concurrent writers' commit windows short).


## Field-level failure flagging (2026-11-20, post-archive hardening)

Operator requirement: failure modes SHALL be flagged at the *statement
level*; hallucination-suspect facts must never stand as plain field
values. `kgFlagFailures.py` implements this by injecting two blocks
into `statements.fields_json` (JSONB absorbs the growth in SQLite and
PostgreSQL alike — no DDL):

```json
"_flags":   { "start_date": "hallucination",
              "involved_cost": "cost-misattribution" },
"_flagged": { "start_date": {"value": "Mitte 2017",
                             "reason": "Dokument datiert 03.02.2015 …",
                             "origin": "crosscheck"} }
```

**The affected VALUE is blanked from the plain field** — consumers can
never mistake it for an extracted fact; the original value + the
diagnose reason live in the `_flagged` note block. Modes: hallucination,
date-mismatch, cost-misattribution, executor-mismatch, other. Fields
already flagged are skipped on re-runs; statements without flags pass
untouched.

```bash
/home/agent/bin/python3.14 -m src.kg.kgFlagFailures             # dry run
/home/agent/bin/python3.14 -m src.kg.kgFlagFailures --apply      # write
```

Migrate afterwards (`kgMigrate --apply`) so the PostgreSQL layer picks
up the flagged/blanked fields — the upserts refresh `fields_json`.

`kgExport` exposes the blocks on every pair as `flags` (request/_flags,
response/_flags plus the `_flagged` note blocks), so downstream
consumers can filter or render them without touching the JSONB.
