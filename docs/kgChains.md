# kgChains — item history reconstruction (pre-stage linking)

Post-processing stage (design D10 amendment, 2026-11-17): papers
discussed in several Gemeinderat meetings produce several pairs; this
stage makes the history explicit so statements can distinguish
"discussed here" from "decided here".

## What it does

| rule | effect |
|---|---|
| all but the LAST pair of a paper's meeting-history | `pairs.pre_stage = 1` |
| consecutive history pairs (sorted by meeting date) | `pair_links` rows, relation `next` |
| consultation role `Kenntnisnahme` **and** no derived outcome | outcome = `kenntnisnahme`, signal `db-partial`, confidence 0.6 |

Verified rule constraint: a present `AgendaItem.result` always wins —
role-Kenntnisnahme consultations also carry results like 'einstimmig
beschlossen' (7), 'einstimmig zugestimmt' (13) or 'Beratung im
Fachgremium' (214) in the corpus, so the role is only a fallback when
the result column is empty.

Corpus numbers (2026-11-17 full run): 239 multi-meeting chains, 259
pre-stage pairs, 259 links, 262 role-derived outcomes.

## Usage

```bash
python -m src.kg.kgChains            # store-only (fast; idempotent)
python -m src.kg.kgChains --db       # additionally read PostgreSQL for
                                     # the role-outcome rule
python -m src.kg.kgChains --store path.sqlite
```

## Schema additions

* `pairs.pre_stage` (INTEGER 0/1) — added idempotently
  (`ensure_pre_stage`), default 0
* `pair_links` — `(prev_pair_key, next_pair_key, relation='next')`
