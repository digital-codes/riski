# Search recall weights

How hybrid search weights its recall signals (change: `fix-hybrid-search-ranking`).

> **Sync rule.** This document and the module docstring of
> `src/search/pgHybridSearch.py` (plus `rrf_fuse`) document the same behaviour.
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

## Weighted RRF formula (`search.fusion_mode: "rrf"`)

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

## Score-blend fusion (`search.fusion_mode: "scores"`, default)

RRF discards within-signal strength: entries at ranks 1 and 50 differ by
`1/61 - 1/110` only, no matter whether the underlying cosine distances
are 0.33 vs 0.47. Score blending keeps that information:

```
norm_l(s)  = clamp((sim - lex_floor) / (1 - lex_floor), 0, 1)
norm_v(d)  = clamp((vec_far - d) / (vec_far - vec_near), 0, 1)
score(id)  = Σ over contributing signals s:  w_s · norm_s
```

- lexical (`lex`): trigram similarity, floor = `lex_floor` (default 0.4)
- name/content vectors (`nv`/`vc`): cosine distance, 1.0 at `vec_near`
  (0.30) → 0.0 at `vec_far` (0.90)
- weights: the same `fusion_weights`; ties broken deterministically on
  oparlKey
- anchors (`search.fusion_score_calibration`) are the calibration knobs —
  `vec_near`/"vec_far" reflect the empirically observed distance range of
  live queries; raise `lex_floor` for stricter name matching.

Measured effect (live corpus): "beteiligungsportal" lexical sim 0.83 →
norm 0.71 × 1.5 = 1.07 outranks an excellent content chunk (0.35 → 0.92 ×
1.0) — under plain RRF both would sit at nearly the same rank points.
`"rrf"` remains available as kill switch.

## Why lexical gets the highest weight

The query "beteiligungsplatform" should surface the file whose name is
literally "Beteiligungsplattform". Content embeddings score such
head-titled documents only mediocre (the body text dominates), and the old
hard rerank cutoff then dropped them entirely. So:

1. lexical 1.5 > nv 1.2 > vc 1.0 keeps exact-name hits near the top,
2. the rerank gate in `src/search/pgTimeline.py.search_stage` keeps lexically-certain
   files (see below) instead of discarding them.

## Configuration

Instance config `search` section (`config/instance.yaml`); every entry can
be overridden per environment with `RISKI_SEARCH__<KEY>` (nested keys via
double underscores, e.g. `RISKI_SEARCH__FUSION_WEIGHTS__LEX=2.0`).

```yaml
search:
  fusion_weights: {lex: 1.5, nv: 1.2, vc: 1.0}
  weighted_fusion: true           # false = plain RRF (kill switch)
  fusion_mode: "scores"           # scores = normalized blending; rrf = rank-only
  fusion_score_calibration:       # score-blend anchors below fusion_weights
    lex_floor: 0.4
    vec_near: 0.30
    vec_far: 0.90
  rerank_cutoff: 0.8              # rerank acceptance cutoff in search_stage
  lexical_rerank_override: true   # keep lexically-matching Files below the cutoff
```

Resolution order per entry: environment → `config/instance.yaml` → code
defaults (`src/instanceConfig.DEFAULTS["search"]`).

## Rerank gating

After reranking (`src/search/pgTimeline.py.search_stage`), files scoring below
`rerank_cutoff` are normally dropped. With
`search.lexical_rerank_override: true` a File whose recall provenance
includes `lexical` (i.e. `lexical_sim` above the similarity threshold —
always true if present) is kept with merged score
`fusion_score × min(rerank_score, rerank_cutoff)`, which ranks it *after*
all fully-accepted files; these files remain candidates for the summary.

## Recall depth and the rerank window

Two more `search` knobs control *how deep* recall reaches before the final
`top_k` cut (relevant for minutes protocols: their names are opaque —
"Protokoll GR 24.02.2026 TOP 3" — so lexical can't catch them and only a
well-ranked *content* match can; measured: the Feb-2026 Beteiligungs-
plattform budget minutes ranks ~85 in the content signal, previously culled
by the fixed 50-candidate depth and the `top_files` top_k cut):

- `search.per_signal` (default 100, per signal & table) — recall depth;
  `file_candidates` exposes up to `max(top_k, per_signal)` fused entries.
- `search.rerank_max_candidates` (default 60) — rerank (and thus any
  combined-score reordering) runs over the first N candidates by fused
  score *before* the `top_k` cut. Candidates beyond the window keep the
  clamped fallback score `fusion × rerank_cutoff`, at/below every reranked
  file. Batch reranker reranks the window in one HTTP call; chat reranker
  makes N LLM calls — lower the window for chat deployments.

Real rerank quality (not the pass-through fallback) is what lifts deep
matches like the minutes into the visible top ranks.

## Listwise chat rerank (fragment B, `search.listwise_rerank`, default on)

With the cross-encoder reranker dropped in favour of the SystemOne
decision model, `search_stage` uses **one** `SUMMARY_MDL` chat call
(`rerank-listwise` / `rerank-listwise-user` prompts in
`config/instruction_prompts.json`) to rank the fused-first candidates:

- `search.listwise_window` (default 50) — how many candidates the model
  sees; 50 because minutes protocols fuse at rank 30–45 behind
  name-vector ghost matches (one call ≈ 8k prompt tokens at 600-char
  snippets).
- Each candidate shows a **keyword-centred snippet** of its best chunk
  (`_listwise_snippet`, 600 chars): the window is centred on the first
  query-term hit (progressive suffix walk handles German compounds —
  the minutes say "Beteiligungsplattform" while the query was
  "Bürgerbeteiligungsplattform"); without a hit the naive head window
  applies.
- Model answer: strict JSON `{"relevant": [numbers]}`; listed candidates
  get decaying rerank scores (1.0 … 0.5, floored at `rerank_cutoff` so
  they pass the gate), model-judged "not relevant" candidates get a weak
  score (rejected unless the lexical override applies). Any failure
  (endpoint, JSON) silently falls back to fused order.
- Fired only when `RERANK_MODE is None` (i.e. no cross-encoder); a real
  reranker keeps precedence and listwise stays dormant.
- Kill switches: `search.listwise_rerank: false`; metric ordering —
  `rerank_max_candidates` remains the classical rerank window
  (disjoint from `listwise_window`).

Measured effect (live, Feb-2026 decision package: minutes 677051 /
Beschlussvorlage 675635 / Anhang 676268 / Informationsvorlage 665090 /
Zwischenbericht 654359): all query variants
("bürgerbeteiligung", "beteiligungsportal", "öffentlichkeitsbeteiligung",
"Bürgerbeteiligungsplattform", "beteiligungsplatform") surface the
decision package in the top 10, "Bürgerbeteiligungsplattform" lands the
minutes at rank 6.

**Deployment status:** we dropped reranking in favour of the SystemOne
decision model (query understanding lives in `src/pgIntentRouter` /
`config/intents.yaml`, `RERANK_URL` unset → `RERANK_MODE = None` and the
batch branch passes everything through at 1.0). With the reranker absent:

- ordering = weighted fusion (fusion weights + `lexical_sim` override),
- `rerank_cutoff` / `rerank_max_candidates` are dormant,
- the recall-depth knobs (`per_signal`, window) still broaden/future-proof
  recall but deep matches cannot be *promoted* — promotion needs a real
  reranker or a follow-up fusion-level mechanism (e.g. signal-score
  blending instead of pure RRF ranks).

## Tuning guidance

- Symptom "exact name = title not found": raise `lex` (try 2.0) and verify
  `lexical_sim` shows in `top_files[].match`.
- Symptom "generic keyword floods results": lower `lex` a little or raise
  `rerank_cutoff`; only the pairwise *ratio* of weights matters (scaling
  all three by the same factor changes nothing).
- Emergency rollback: `weighted_fusion: false` (plain RRF) and
  `lexical_rerank_override: false` (strict old rerank gate) independently.
