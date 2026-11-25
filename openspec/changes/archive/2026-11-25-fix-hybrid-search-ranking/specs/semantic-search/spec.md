# semantic-search Delta

## MODIFIED Requirements

### Requirement: Lexical name recall
Search SHALL produce lexical candidates using trigram similarity over the
indexed `name` columns of Paper, File, AgendaItem, and Meeting (indexes
already created by pgGen), with a configurable similarity threshold and
per-table candidate count. Every lexical candidate SHALL carry its trigram
similarity in the candidate provenance so downstream stages (fusion
weighting, rerank override, output `match` block) can use it. A candidate
whose only signal is a lexical hit SHALL NOT be excluded from the final
`top_files` list solely because its rerank score is below the acceptance
cutoff; such candidates SHALL be ranked by the combined fusion/rerank
score and remain eligible for the summary stage.

#### Scenario: Exact name fragment is recalled
- **WHEN** a query contains a name fragment (e.g. committee or paper title substring) whose embedding distance is mediocre
- **THEN** the matching entities enter the candidate set via the lexical signal

#### Scenario: Lexical-only File is not rerank-dropped
- **WHEN** a File matches the query with trigram similarity above the lexical threshold but scores below the rerank cutoff
- **THEN** the File stays in `top_files` (ranked by the combined score) and is available to the summary stage

#### Scenario: Lexical similarity in provenance
- **WHEN** a File or entity is recalled via the lexical signal
- **THEN** its `match` provenance includes `lexical_sim` with the similarity value

### Requirement: Signal fusion
Hybrid recall SHALL fuse per-signal ranked lists with reciprocal-rank
fusion using signal-type weights, applied to the default fusion in the API
search path: the lexical signal SHALL receive the highest weight, the
name-vector signal a medium weight, and the content-vector signal the
base weight (defaults 1.5 / 1.2 / 1.0, configurable). The weighted fusion
SHALL be the default for `hybrid_candidates` and SHALL NOT change the
result-contract shapes. All fusion weights SHALL be deployment-
configurable via the instance config `search` section (env → config
file → code defaults).

#### Scenario: Weighted fusion ranks lexical hits above weak vector hits
- **WHEN** a File has a direct lexical hit and other files rank higher only by content-vector proximity
- **THEN** the lexically-matching File outranks the vector-only files in `file_candidates`

#### Scenario: Weights tuned per instance
- **WHEN** an instance config (or `RISKI_SEARCH__FUSION_WEIGHTS__LEX` env override) sets custom fusion weights
- **THEN** fusion uses those weights and the code defaults are untouched

#### Scenario: Kill switch restores unweighted behaviour
- **WHEN** `search.weighted_fusion: false` is set for the instance
- **THEN** fusion uses plain RRF as before and no other stage changes

### Requirement: Recall depth and rerank window
Search SHALL produce `per_signal` candidates per signal (instance-config
`search.per_signal`, default 100) and expose up to `max(top_k,
per_signal)` fused file candidates to the rerank stage. The rerank gate
SHALL run over the first `search.rerank_max_candidates` (default 60)
candidates by fused score *before* the final `top_k` cut; candidates
beyond that window SHALL receive the fallback score `fusion × rerank_cutoff`
(at or below every reranked file). The final `top_files` list SHALL be
sorted by kept score and cut to `top_k` after the gate.

#### Scenario: Deep content match survives default top_k
- **WHEN** a relevant document's best chunk ranks inside the per-signal candidate set but its fused rank is beyond top_k, and the reranker scores it well
- **THEN** the document appears in `top_files` for the default API `top_k`

#### Scenario: Candidates beyond the rerank window keep a clamped score
- **WHEN** a candidate's fused rank is beyond `rerank_max_candidates`
- **THEN** it keeps score `fusion × rerank_cutoff` and cannot outrank an accepted file
