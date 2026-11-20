# Spec Delta

## Purpose

Let intent routing benefit from the kg-topic layer: a topic-focus step
based on the query embedding narrows (or boosts) retrieval for the
intents where topical precision pays off.

## ADDED Requirements

### Requirement: Topic-focus step for retrieval intents
The intent router SHALL derive a topic focus for `search_topic` and
`ask_decision_date` queries: the query is embedded once (existing
bge-m3 endpoint) and compared against the 23 ris-ki topic description
vectors (precomputed once, cached in-process); the best-matching topic
with a cosine ≥ configured threshold becomes the query's topic focus.
Intents without benefit (location, gremium) skip the step.

#### Scenario: Topic derived for a decision question
- **WHEN** the query "wann wurde über die Straßenbahnlinie 1
  verhandelt" embeds closest to the `Mobility` topic (score ≥
  threshold)
- **THEN** the topic focus is `Mobility` and the retrieval joins
  `File_tags_assoc` (scheme `kg-topic`, tag `Mobility`) to boost
  documents carrying that tag

#### Scenario: No topic above threshold
- **WHEN** the query "was macht der Gemeinderat" does not match any
  topic ≥ threshold
- **THEN** retrieval runs unscoped (previous behaviour) and the focus
  is marked `none`

### Requirement: Topic-boost is non-destructive
Topic focus SHALL boost or filter (configurable per intent, constant
in v1: boost only) — meaning documents without the focus tag still
appear when their lexical/vector signals are strong; search coverage
SHALL not shrink below today's behaviour, only compress.

#### Scenario: Strong lexical result keeps ranking
- **WHEN** a document without the focus tag matches the query
  lexically at rank 2 while only rank-6 documents carry the focus tag
- **THEN** the boosted retrieval keeps the rank-2 document in front of
  the rank-6 documents (boost multiplies score, does not rearrange
  aggressively)

## REMOVED Requirements

(none)
