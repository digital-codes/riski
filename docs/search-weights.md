# Search recall weights

How hybrid search weights its recall signals (change: `fix-hybrid-search-ranking`).

> **Sync rule.** This document and the module docstring of
> `src/pgHybridSearch.py` (plus `rrf_fuse`) document the same behaviour.
> The code is the source of truth; any behavioural change to the weights,
> the fusion or the rerank gating **must update both in the same commit**.
> Config values live in `config/instance.yaml` (`search` section) and
> `src/instanceConfig.py` `DEFAULTS["search"]` — those two must also stay
> identical.

## Signals

| Signal | Key | Source | Direction |
|---|---|---|---|
| Lexical | `lex` | Trigram similarity over `name` columns (`lexical_candidates`) | higher similarity = better |
| Name vectors | `nv` | `{table}_name_vecs` pgvector cosine (`name_vector_candidates`) | lower distance = better |
| Content vectors | `vc` | `contentEmbeddings` best chunk per file (`content_vector_candidates`) | lower distance = better |

Signals run per item table (Paper, File, AgendaItem, Meeting) in parallel and produce ranked candidate lists.

## Weighted RRF formula

```
score(id) = Σ over contributing signals s:  w_s / (k + rank_s)
```

- `k = 60` (`RRF_K`)
- `rank` is the 1-based position in that signal's ranked list
- a signal that did not match the id contributes nothing — weights scale only what exists

**Worked example** (k=60, lexical tops first list, `b` hit by two signals):

```
lists: lex = ["a", "b"], nv = ["b"]
weights: lex = 1.5, nv = 1.2
score(a) = 1.5/61            = 0.02459
score(b) = 1.5/62 + 1.2/61   = 0.04379   → b first
```

Weights *re-scale within the rank window*; a big weight cannot push a deep
rank above a top rank of a hit-by-everything match — multi-signal matches
still win, plain RRF ordering is preserved between equal-weight items.

## Why lexical gets the highest weight

The query "beteiligungsplatform" should surface the file whose name is
literally "Beteiligungsplattform". Content embeddings score such
head-titled documents only mediocre (the body text dominates), and the old
hard rerank cutoff then dropped them entirely. So:

1. lexical 1.5 > nv 1.2 > vc 1.0 keeps exact-name hits near the top,
2. the rerank gate in `src/pgTimeline.search_stage` keeps lexically-certain
   files (see below) instead of discarding them.

## Configuration

Instance config `search` section (`config/instance.yaml`); every entry can
be overridden per environment with `RISKI_SEARCH__<KEY>` (nested keys via
double underscores, e.g. `RISKI_SEARCH__FUSION_WEIGHTS__LEX=2.0`).

```yaml
search:
  fusion_weights: {lex: 1.5, nv: 1.2, vc: 1.0}
  weighted_fusion: true           # false = plain unweighted RRF (kill switch)
  rerank_cutoff: 0.8              # rerank acceptance cutoff in search_stage
  lexical_rerank_override: true   # keep lexically-matching Files below the cutoff
```

Resolution order per entry: environment → `config/instance.yaml` → code
defaults (`src/instanceConfig.DEFAULTS["search"]`).

## Rerank gating

After reranking (`src/pgTimeline.search_stage`), files scoring below
`rerank_cutoff` are normally dropped. With
`search.lexical_rerank_override: true` a File whose recall provenance
includes `lexical` (i.e. `lexical_sim` above the similarity threshold —
always true if present) is kept with merged score
`fusion_score × min(rerank_score, rerank_cutoff)`, which ranks it *after*
all fully-accepted files; these files remain candidates for the summary.

## Tuning guidance

- Symptom "exact name = title not found": raise `lex` (try 2.0) and verify
  `lexical_sim` shows in `top_files[].match`.
- Symptom "generic keyword floods results": lower `lex` a little or raise
  `rerank_cutoff`; only the pairwise *ratio* of weights matters (scaling
  all three by the same factor changes nothing).
- Emergency rollback: `weighted_fusion: false` (plain RRF) and
  `lexical_rerank_override: false` (strict old rerank gate) independently.
