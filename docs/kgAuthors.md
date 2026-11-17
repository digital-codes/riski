# kgAuthors — party author identification

Stage 3: identifies the authoring party of request items from the paper
name and the head document text, with era-valid normalization of an
inconsistent party landscape (docs/kg_building.md explicitly calls for
effort here — party compositions change over time).

## Approach

* Vocabulary-driven: every party has a list of variant patterns
  (`config/kg_vocabulary.yaml::party_variants`), matched case- and
  form-insensitively (CDU, CDU-Fraktion, BÜNDNIS 90/DIE GRÜNEN, KAL, …).
* **Era validity**: a variant may be bound to a date range
  (`era: [[from, to]]`); the paper's date decides which
  historical formation a text belongs to. `era: null` = always valid.
* Scope: request classes only (Antrag, Anfrage,
  Änderungs-/Ergänzungsantrag, Beschlussvorlage) — administrative
  response classes are skipped.
* **Never guess**: if no variant matches, the author stays empty/unknown
  and is counted in the summary (`unknown`).

## Usage

```bash
# all pairs (resumable: upserts into the statement store)
python -m src.kg.kgAuthors

# limit
python -m src.kg.kgAuthors --limit 200

# print the party vocabulary labels
python -m src.kg.kgAuthors --list-parties
```

## Output

* `statements` rows (stage `author`) with
  `{author, pattern, meeting_date, provenance}` JSON
* console summary: pairs / authors_found / unknown / skipped

## Observed run (full corpus, 2026-11-17)

- 5,843 resolved vs 2,390 unknown on 8,233 pairs; distribution CDU
  dominant (reflects Beschlussvorlage wording "Antrag der
  CDU-Fraktion"XXX being carried into vote names) — per-distribution
  refinement of the MLA variant vocabulary is expected during QA.
- Unknowns concentrate on Bekanntgaben and patterns without permission
  naming ("Bekanntgabe nichtöffentlich gefasster Beschlüsse") which is
  correct behaviour (no author to attribute).
