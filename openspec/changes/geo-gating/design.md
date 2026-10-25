# Design

## Context

Geo file links are produced by `pgAddFileGeoRefs.match_files`: a literal,
boundary-aware matcher over `File.name + teaser` (the `_VENUE_NOISE`
regex already strips the known "Rathaus am Marktplatz" boilerplate — the
address-block problem is the same *class* of defect, but too varied for a
regex). Teasers are built from the content start (`pgTeasers`), and
council documents begin with a Briefkopf — sender/recipient address blocks
("SPD-Fraktion Karlsruhe, Hebelstraße …", "Landratsamt Karlsruhe,
Beiertheimer Allee 2 …"). The matcher therefore links address streets.
`File.content` (≤ 8000 chars, the markdown-derived text) is available per
file and gives the LLM enough context to distinguish header from body.

Agenda-item links (`pgAddStreetRefs`/`pgAddDistrictRefs`) match item names
— much shorter, but item titles like "Antrag der SPD-Fraktion" can still
carry organisation addresses in the full name string, so the same gate
applies with the item name as context.

## Goals / Non-Goals

**Goals:**
- Kill Briefkopf/footer/venue boilerplate links without losing genuine
  content mentions.
- Keep the map correct for *enabled* documents only, updating live as the
  user toggles the list.
- Clean up the existing link inventory in one bounded, resumable pass.
- No deletion of evidence: marks, not purges (purge optional).

**Non-Goals:**
- No re-matching mechanism change (the literal matcher stays; the gate is
  a filter on its output).
- No restructuring of the teaser to exclude the Briefkopf (worth doing
  later, but the gate fixes data and display regardless of teaser
  provenance).
- No per-link LLM calls (too expensive) — batching per document.

## Decisions

**D1 — Gate input: `File.content` + match contexts, batched per file.**
One prompt per document: the (bounded) content plus the list of matched
names with a short context excerpt around each match. The model classifies
each name once per document. Alternative: per-link classification from the
match context only — rejected (loses document-level view: "Hebelstraße" in
the address block AND in the body is *content*, the same name in only the
address block is boilerplate; a context-window-only model cannot see the
body usage).

**D2 — The prompt (summary model via `src.remote.chat`).**

```
Du prüfst Georeferenzen in Dokumenten des Ratsinformationssystems der
Stadt Karlsruhe.

Gegeben: der Inhalt eines Dokuments und eine Liste von Straßennamen bzw.
Stadtteilen, die automatisiert im Text gefunden wurden.

Aufgabe: Entscheide für jeden Namen, ob er zum HAUPTINHALT des Dokuments
gehört oder nur aus Beilage-/Metadaten-Text stammt.

Als HAUPTINHALT gilt: der eigentliche Text des Antrags / der Anfrage / der
Beschlussvorlage / des Protokolls — z. B. eine Straße als Ort einer
geplanten Maßnahme, als betroffener Bereich oder als Thema.

Als BEILAGE/METADATEN gelten und werden als "boilerplate" eingestuft:
- Absender- und Empfängeradressen im Briefkopf (Antragsteller, Fraktion,
  Amt, Behörde, Unternehmen)
- Fußzeilen, Impressum, Kontakt- und Signaturblöcke
- Veranstaltungsort-Boilerplate (z. B. "Bürgersaal, Rathaus am Marktplatz")
- Wiederkehrende Formulare/Deckblatt-Angaben ohne inhaltlichen Bezug

Antworte AUSSCHLIESSLICH mit JSON, keine weiteren Texte:
{"verdicts": [
  {"name": "<Name>", "verdict": "content"|"boilerplate"|"unsure",
   "reason": "<kurzer deutscher Grund, max. 1 Satz>"}
]}

Regeln:
- Genau ein Eintrag pro gegebenem Namen, Namen unverändert übernehmen.
- "content": der Name wird im Haupttext inhaltlich verwendet — auch wenn
  er zusätzlich in einer Adresse vorkommt.
- "boilerplate": der Name kommt NUR in Kopf-/Fuß-/Adressbestandteilen vor.
- Wenn du nicht sicher entscheiden kannst: "unsure".
```

Karlsruhe-specific rule added after ops review: many parties share the
"Haus der Fraktionen" on Hebelstraße, so submitter address lines cluster
on that street across *all* fractions. The prompt must prevent the model
from reasoning "politically relevant street → content": an address line of
a submitter ("Fraktion X, Hebelstraße 21, 76133 Karlsruhe") is boilerplate
regardless of which party sits there; only the main text treating the
street itself (e.g. the sale of the "ehemaliges Haus der Fraktionen in der
Hebelstraße 13") makes it content.

Model: the configured summary model (`SUMMARY_*` / `src.remote`), JSON
parsed defensively (strip code fences; on parse failure → all verdicts
`unsure` with reason "parse error" — never crash the matching pipeline on
a malformed LLM answer).

**D3 — `GeoGate` class (`src/geoGate.py`).**

```python
class GeoGate:
    """LLM gate for street/district geo references (change: geo-gating)."""

    def __init__(self, engine=None, model=None, max_content_chars=6000,
                 context_chars=160):
        # engine for File.content lookups; model overrides SUMMARY_MDL

    def gate_file(self, file_sid: int, mentions: list[dict]) -> dict[str, dict]:
        """mentions: [{"entity": "Hebelstraße", "context": "..."}]
        Returns {entity: {"verdict": ..., "reason": ...}} — one batched
        LLM call per document; LLM failure => all 'unsure'/'llm error'."""

    def gate_agenda_item(self, item_sid, item_name, mentions) -> dict
        # same, context = item name (short input)

    def write_verdicts(self, assoc_table, rows: list[dict]) -> None
        # UPDATE ... SET gate_status, gate_reason, gated_at, gate_model
```

Gate at write time in `match_files`: after `flush()` of new links for a
file, collect the file's new `(entity, context)` pairs → one `gate_file`
call → `write_verdicts`. Wrapped in try/except: any gate failure leaves
`gate_status = NULL` (row shown until cleaned) — the pipeline never fails
because of the gate.

**D4 — Storage: additive columns, NULL = ungated. Permissive principle.**
`gate_status VARCHAR(16)`, `gate_reason VARCHAR(255)`, `gated_at`,
`gate_model` on all four association tables, created on demand
(`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` pattern already used by
`pgTagMgr`). Governing principle: **the gate may only suppress when it is
confident** — everything it is not sure about stays visible:

- `NULL` (ungated: legacy, LLM down, parse failure) → **shown**
- `unsure` → **shown**
- `content` → **shown**
- `boilerplate` → **hidden** (the only suppressing verdict)

Only an explicit, confident `boilerplate` verdict hides a link. Strict
hiding of `unsure` was rejected: a false "boilerplate" would silently drop
a genuine location; `unsure` stays visible with its reason in the popup
for the operator to spot systematic errors.

**D5 — Map gating in `/geo` (defect 2).**
`/geo` already excludes `summary_refused`; it now also excludes
`result["summary_excluded"]` — the authoritative exclusion set the
frontend maintains. The frontend already re-fetches `/geo` after every
toggle/refine (`App.vue: fetchGeo()` in the summarize handlers), so the
map updates live with **no frontend change**. Edge case: files present in
the graph but not yet in `summary_files` (summary not yet run) are *shown*
— the user cannot have disabled a document they have not seen.
`collect_geo` additionally filters `gate_status <> 'boilerplate'` (D4).

**D6 — Cleanup (`src/pgGeoGateCleanup.py`).**
Iterates association rows with `gate_status IS NULL` in batches
(`--batch 50` documents), loads `File.content`, builds mentions from the
`name_match` evidence column (format `[source] evidence`), gates, writes
verdicts. Flags: `--dry-run` (report verdict distribution without
writing), `--limit`, `--table` (restrict to one assoc table),
`--reprocess` (re-gate `unsure` rows too, e.g. after a model upgrade),
`--purge-boilerplate` (optional DELETE instead of mark). Resumable by
construction: the NULL query is the cursor; interrupted runs simply
continue. Estimated volume: current link count is modest (streets/districts
are selective), so the one-off pass is minutes of summary-model time.

**D7 — Deterministic pre-filter stays.** `_VENUE_NOISE` (and a small
addition: a PLZ+street address-line heuristic for the evidence column,
e.g. matching `^.*\b\d{5}\s+Karlsruhe\b` line blocks) runs *before* the
LLM — cheap wins first, LLM only for what survives. The heuristic only
*annotates* (context excerpts), never deletes.

## Risks / Trade-offs

- [LLM misclassifies content as boilerplate] → `unsure` shown by default;
  verdicts are marks (recoverable via `--reprocess`); reason strings are
  visible in the assoc table and can be audited.
- [Summary model unavailable during matching] → rows NULL, shown, cleaned
  by the next cleanup run — matching never blocks on the LLM.
- [Cleanup cost] → batched per document; `--table`/`--limit` allow partial
  runs; dry-run reports volume first.
- [User confusion when toggling changes the map] → intended (that's the
  fix); the popup already names the referencing document.

## Migration Plan

1. `src/geoGate.py` + unit tests (stubbed chat client: verdict parsing,
   batching, failure fallback).
2. Assoc-table column migration (on demand) + `collect_geo` gate filter +
   `/geo` exclusion filter + tests.
3. `pgAddFileGeoRefs` / `pgAddStreetRefs` / `pgAddDistrictRefs` write-time
   gating + tests.
4. `pgGeoGateCleanup.py` cleanup pass + tests; run against the live DB.
5. Verify with the default query: Hebelstraße gone from the map; toggling
   documents updates the map immediately.

Rollback: revert the commit — the columns are additive and harmless;
boilerplate marks remain but `/geo` without the filter simply shows them
again.

## Open Questions

- Should `pgTeasers` also learn to strip the Briefkopf before teaser
  generation (root cause rather than symptom)? Deferred — the gate
  suffices; teaser hygiene would *additionally* reduce noisy teasers in
  the result list.
