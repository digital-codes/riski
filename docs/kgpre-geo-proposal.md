# Geo-Reference Resolution with Strict Scrutiny & Human-Review Alerts

*Proposal — 2026-11-18. Extends the KG-Pre pipeline proposal
(`docs/kgpre-pipeline-proposal.md`, stage 4 "classify" / stage 5
"ground") and supersedes the current write-time heuristic gate
(`src/geoGate.py` boilerplate/content split), which already proved the
need: 44,918 links gated, 2,765 boilerplate verdicts — but the
*target-vs-reference* confusion was never addressed.*

---

## 1. The problem, precisely

Geo references today are extracted by name scanning
(`pgAddFileGeoRefs`, `pgAddStreetRefs`, `pgAddDistrictRefs`) and only
**filtering** happens afterwards (boilerplate vs content). What is
missing is a **role decision**: documents routinely carry *two or more*
geolocations with different discourse roles:

* **target** — the item the document decides/builds/forbids *for*
  ("Sanierung der Herrenalber Straße", "Bebauungsplan … Karlsruhe-
  Nordstadt");
* **reference / comparison** — locations used as precedent or analogy:
  *„wie es dort am Friedrichsplatz gehandhabt wird"* → Friedrichsplatz
  is NOT the target;
* **administrative boilerplate** — letterhead, contact block, venue of
  the meeting, PLZ/footer mentions (already gated today).

The prototype handling is wrong exactly for the second class: both get
`content` verdicts, both appear on the map — the „we do here what we
did there" case the operator describes.

## 2. Design principles

1. **Role is derived, not just filtered** — every resolved geo
   reference gets a *role* verdict: `target | reference | context |
   boilerplate`, each with evidence span(s) and a confidence.
2. **Grounding over naming** — a reference is only as good as its
   evidence span; the span decides, not the string. Re-tokenized
   chunks from the KG-Pre statement layer are reused (span-first).
3. **Hierarchical confirmation** — strong signals below can veto weak
   ones (rule-out cascade), and any *ambiguity below threshold is
   escalated, never guessed* — into a **review queue** with
   human-in-the-loop.
4. **Precedence is cross-checked against the document set** — a
   document with 5 candidate streets and a title naming exactly one is
   a textbook target/boilerplate split; multi-true-target documents
   exist (regional projects) and are *allowed* after scrutiny, not
   suppressed.

## 3. Extraction & classification pipeline (per document)

```
candidates = gazetteer match (streets, districts, POIs, venues)
                + address-regex candidates (house-number + PLZ blocks)
        ↓ dedupe (street alias table: "Herrenalber Str." ≈ "Herrenalber Straße")
for each candidate span:
    features = {
        position:    title | agenda-item-name | first-content-chunk |
                     content | boilerplate-zone(address/contact/venue)
        binding:     verb-class in span window ± 2 sentences
                     (target-verbs: Sanierung/Neubau/Rückbau/Aufstellung/
                      Rückbau von/sperren/errichten; vs comparison-verbs:
                      wie am/in/vgl/ähnlich/bereits dort/beispielhaft)
        deixis:      deixis word class in window (hier/dort/ebenda/daselbst)
        cardinality: how many candidates share the binding context
        section:     does the span sit inside a dedicated
                     "Maßnahme/Anlage/Baubeschreibung" section? (KG-Pre
                     content stage already marks heading spans)
        corroboration: does the same candidate also appear linked in
                     agenda item name, paper title or Anlage filename
                     (the strongest target evidence the corpus offers)?
    }
        ↓
rule scorer (fast, deterministic) → verdict + confidence
        ↓ if confidence ∈ [θ_low, θ_high]  →  REVIEW QUEUE (human)
        ↓ else verdict published (target/reference/context/boilerplate)
```

**Deterministic first pass** catches ~70–80 % (the common cases:
title/agenda-bound single candidate = target; address block =
boilerplate; deixis-bound comparison = reference). Anything the rules
cannot separate goes to a **decision pass** — a SystemOne round:

* state = document content (target section first, then the candidate
  windows),
* `noul` question **per candidate** — "Ist <cand> der *Gegenstand* der
  geplanten Maßnahme des Dokuments?
  (`criteria: target / reference / boilerplate /`) — calibrated exactly
  like the tag/outcome verdicts; plus a `noul` question per
  competing candidate for pairwise ratio (the „hier vs dort" case is
  inherently comparative).

Confidence fusion: rule score × model score; the pairwise model
question resolves candidate-set ties deterministically (the
highest-scoring candidate wins `target`, the others drop to
`reference` unless their own score is within ε).

## 4. The alert mechanism (human-in-the-loop)

New table (KG-Pre store, additive — same pattern as `verify_note`):

```sql
CREATE TABLE geo_review_queue (
  id            INTEGER PRIMARY KEY,
  doc_key       TEXT NOT NULL,        -- File
  candidate     TEXT NOT NULL,        -- street/district uri/name
  role_guess    TEXT NOT NULL,        -- target|reference|context|boilerplate
  confidence    REAL,
  evidence      TEXT NOT NULL,        -- spans + reason (JSON)
  state         TEXT NOT NULL DEFAULT 'open',  -- open|resolved|discarded
  resolution    TEXT,                 -- human verdict
  reviewed_by   TEXT, reviewed_at TIMESTAMP,
  UNIQUE (doc_key, candidate)
);
```

Triggering rules (scrutiny thresholds, tuned from the 2,765 known
boilerplate verdicts + the false map entries observed):

* rule+model confidence **< θ_high is > θ_low** → `open` review item;
* **conflict family**: two candidates with near-equal model scores
  (ratio < 1.15) → open (the „here vs there" borderline);
* **trust inversion**: new verdict disagrees with an existing gating
  verdict (e.g. previously `boilerplate`, now `target`) → open, with
  both evidence sets attached;
* **novel role for repeated candidate**: a street that always acted as
  `reference` suddenly scores `target` → open (drift alarm);
* every decision-model verdict **carries its noul score** — scores in
  the uncertain band (0.35–0.65) always escalate, mirroring the D12
  ⌀-verdict rule.

**Feedback loop**: human resolutions are stored *with spans* and
become few-shot anchors — (a) added to the deterministic rule table
(vocabulary/exception list), (b) replayed into the decision model as
anchor exemplars. The queue drains; automation gets stricter over
time. Exit criterion: review item creation rate < 2 % of documents on
a rolling week.

**Alert delivery** integration with the existing habits of this
repo (Matrix): batched "N neue Geo-Review-Fälle" messages summarizing
type + top evidence, and a `--review-summary` CLI for the operator;
the web app gains a small review panel later (P4), the queue is fully
API-drivable before that.

## 4b. Affected code (implementation backlog — separate session)

The current geo layer lives in `src/` and would be touched as follows:

| file | today | change under this proposal |
|---|---|---|
| `src/pgGeo.py`, `src/local_geo_matching.py` | gazetteer loading + matching | role-aware candidate hints attached at match time (position, binding window) |
| `src/pgAddFileGeoRefs.py`, `pgAddStreetRefs.py`, `pgAddDistrictRefs.py` | write assoc rows on name scan | write spans + candidate hints alongside; verdicts move to the kg pre layer |
| `src/geoGate.py` + `pgGeoGateCleanup.py` | binary boilerplate/content write-time gate (2-layer: regex heuristic + LLM) | gateway becomes the role classifier (target/reference/context/boilerplate) — same 4 assoc tables, richer verdict column |
| `src/pgAddStreets.py`, `pgAddDistricts.py` | GML/GDAL loaders of the WFS/GeoJSON geometries | unchanged |
| API/frontend (`/geo/{session}`, `GeoMap.vue`) | layers filtered on `gate_status` | filter additionally on `role_verdict` (target/context only) |

Scope decision 2026-11-18: the role classifier and review queue
(geo_review_queue table + systematic escalation rules + processing
feedback loop) are designed here but deferred to a separate working
session — this proposal stays the design record.

## 5. Migration from the current geo layer

1. Keep the existing four assoc tables + `gate_status` (read layer
   unchanged) — KG-Pre writes the **role verdicts** into a parallel
   `geo_references(role_verdict, span_evidence, confidence, review_id)`
   structure keyed on the same (doc, street/district) pair identity.
2. One-time re-run over the 2026-10-25 gate corpus (rules are cheap;
   model pass ≈ 2–5 s/doc on OLC) → diff report old verdict vs new:
   the mismatch set *is* the review-queue seed (the operator can
   validate the classifier against previously known-good verdicts
   — good test set).
3. Consistency rule: reference-role links stay in the DB (never
   deleted) but are excluded from map layers and location-search
   recall (same philosophy as `gate_status='boilerplate'` — permissive,
   reversible).

## 6. Measured targets (acceptance criteria)

| metric | current | target |
|---|---|---|
| boilerplate false-positives on map | 2,765 / 44,918 (≈6 %) | < 1 % |
| target/role accuracy on known-good sample (title-bound single-candidate docs) | n/a | ≥ 95 % |
| review queue creation rate | n/a | < 2 % per doc, ≤ 15 items/day |
| „here vs there" dual-map entries | common | ≤ 5 % of multi-candidate docs, conflict-family escalated |
| human cost | full-time hand curation | batch reviews (≤ 5 min/day via panel/CLI) |

## 7. Honest limits

* Multi-target documents (regional list decisions touching 5+ streets
  with equal binding) are inherently ambiguous — they escalate and the
  human resets them as documented multi-target (a legit verdict the
  queue supports).
* Extraction is German-only in v1 (consistent with the corpus).
* The gazetteer needs POI/venue names as first-class entries (the
  `Location.description` field already carries Bürgersaal etc.) —
  venue boilerplate and venue-*targets* (e.g. an event decision about
  the Festsaal Durlach) cannot be told apart without the discourse
  classifier either; same mechanism covers both.
