# Response-document coverage in the kg pairs — investigation report

**Date:** 2026-11-18 · **Author:** kg pipeline investigation (change
`kg-statement-extraction`)
**Question raised by operator:** *"I count 6,764 `Consultation.role =
'Entscheidung'` rows and expect all of them to be the decision of some
request. Why do so few pairs have response documents, and where do the
items get dropped?"*

---

## 1. The structural funnel (PostgreSQL, `riski_agentic`)

Counts as of 2026-11-18 (read-only):

| stage | rows | note |
|---|---|---|
| `Consultation` total | 15,217 | |
| `Paper__consultation__Consultation` rows | 14,858 | 359 consultations unlinked to any paper |
| by `role` | Entscheidung **6,764** · unbekannt 4,063 · Kenntnisnahme 3,090 · Vorberatung 512 · Behandlung 315 · Beratung 306 · Anhörung 163 · NULL 4 | |
| by organization of meeting | **Gemeinderat 3,797** · 'Antragsliste DHH' 367 · Bauausschuss 363 · Hauptausschuss 336 · Ortschaftsräte (6 × 89–286) · 'GR Beratungen zum DHH' 247 · Planungsausschuss 113 … | the spec scopes pairs to Gemeinderat — everything else is deliberately out |
| by `Paper.papertype` on Entscheidung consultations | Beschlussvorlage 4,141 · Antrag 1,416 · Änderungs-/Ergänzungsantrag 502 · Anfrage 59 · Haushalt THH* ~433 | THH family excluded (budget-line documents, no request/decision semantics) |

`Gemeinderat` join filter (`m.name LIKE 'Gemeinderat%'`) at kgIdentify
time gave **8,301 pairs** (paper × meeting granularity) — of which
**4,009** decision-bearing pair rows on request-class papers.

**Conclusion 1:** out of 6,764 Entscheidung consultations, ~2,755 are
*not* Gemeinderat (Ortschaftsrat/Ausschüsse/DHH lists — excluded by
spec) and ~433 are Haushalt THH rows; **4,009 remain** as the
request/decision pool. This part behaves as expected.

## 2. Where the RESPONSE documents actually live

| candidate source | rows | usable? |
|---|---|---|
| `AgendaItem__auxiliaryFile__File` on GR decision items | 417 files, **3 distinct on decision items** | effectively empty — attachments live on papers, not agenda items |
| `Meeting__resultsProtocol__File` (Niederschrift per meeting) | 297 (142 on GR) | recent years are all "Anwesenheit (Protokoll)" — attendance only |
| **`File__paper__Paper` with `File.name ~ 'Protokoll.*TOP'`** | **3,444 files on 3,444 papers** | ✅ the real mass: per-TOP protocol extracts ("Protokoll GR 17.12.2024 TOP 31", committee variants) |
| `File__meeting__Meeting` prot files | 1,274 | per-meeting, not pair-addressable |
| `Meeting__auxiliaryFile__File` (GR) | 1,471 | not TOP-granular |

The earlier prototype (registry by name/(date,TOP)) saw only ~830
pair-protocol candidates. **The missing mass was `File__paper__Paper`**
— a link type the kg traversal had not included.

## 3. Verification gate: coverage vs. strictness

kgProtocols attaches a response document to a pair only when all three
checks pass (spec: protocol verification and response attachment):

1. **TOP match** — `Punkt <n> der Tagesordnung` in the protocol text
   equals the pair's agenda-item number (219/244 = 90 % on the
   structural sample);
2. **Result match** — outcome wording in the `Beschluss:` section is
   compatible with the pair outcome (54/81 = 67 % first-pass; misses:
   heading-split artifacts, non-outcome column values like "keine
   Mitteilungen", "Aushang im Foyer");
3. **Session guard** (added 2026-11-18) — session date in text/name or
   "GR" in the name, to keep committee protocols off GR pairs.

Latest full pass (2026-11-18): protocols_seen 1,796 · top_match 1,047 ·
result_match 285 · **attached 239** · outcome_derived +45 ·
not_attached 1,557.

### Reasons for dropping items (not_attached, per-reason share)

| reason | share | kind of miss |
|---|---|---|
| no TOP reference in text (attendance protocols, foreign-topic extracts) | ~40 % | file belongs to another TOP/body — correctly dropped |
| outcome wording mismatch / non-outcome wording | ~45 % | checker fragility (formatting, 'Kenntnisnahme' sections inside zugestimmt-protocols), partially recoverable |
| session guard | ~15 % | committee protocol at same TOP number — correctly dropped |

**Conclusion 2:** the drop is *verification-gated by spec*. Pairs are
not dropped arbitrarily — each miss carries a class in
`results/kg_protocols_stats.json` + the tuning report. The 1,557
not-attached are dominated by outcome-wording misses on paper-attached
protocols, i.e. checker-fragility recoverable within the 3-iteration
D12 loop — not structural absence.

## 4. Actual pair/response coverage after the fixes (SQLite store)

| metric | value |
|---|---|
| pairs with ≥ 1 verified response doc | **267** (236 pending at extraction time) |
| decision consultations covered | 267/4,009 ≈ **6.7 %** |
| outcome coverage | column ≈ 60 % + role rule + protocol-derived (signal 'protocol') |
| GR Entscheidung consultations whose paper has a prot file | **350** (this is the realistic near-term ceiling with text verification) |

**Conclusion 3:** structural coverage is bounded by the corpus: per-TOP
protocol extracts exist for ≈350 GR decision pairs (older years use
full-session Niederschrift — attendance-only or not per-TOP). The
verified-attachment rate can approach ~350, not 4,000, without
loosening the spec. The remaining ~3,650 pairs legitimately have their
outcome only in `AgendaItem.result` / consultation role / the
(named-extracted) registry path.

## 5. Recommendations

1. **Do not chase 100 % response-doc attachment.** The corpus simply
   doesn't carry per-decision documents for most years; the spec's
   "plus" source is `File_chunks` of the *session Niederschrift*, not
   per-pair files.
2. **Checker improvement (D12 iteration):** normalize the
   `Beschluss:`-section extraction (multi-chunk joining, '##'-heading
   splits) and treat non-outcome column values as "unknown" instead of
   forcing a verdict — should lift result_match from ~285 to an
   estimated 600–800 and raise attached pairs toward the ~350 ceiling.
3. **Registry path upgrade:** for papers whose paper-prot file lacks
   the date in the name ("Protokoll TOP 40"), correlate `File.date` and
   the paper's consultation meeting instead of requiring the name date —
   recovers a subset of today's session-guard drops without weakening
   the guard.
4. **Statement layer compensates:** pairs without response docs still
   get their outcome statements from `AgendaItem.result` (+ role
   fallback + protocol-derived), so the downstream statements/grounding
   layer doesn't starve.
5. Keep `pairs.pre_stage` + `pair_links` (D10) so a pair's "outcome"
   can be resolved by chaining to the meeting where the decision
   actually happened — this is the recommended primary fix for the
   outcome-gap pool, ahead of any checker relaxation.


---

## Addendum 2 (2026-11-18, operator's File_chunks observations)

Operator checked `File_chunks LIKE '%zugestimmt%'/%abgelehnt%'/
%beschlossen%'` (3,803 / 3,434 / 8,528 chunks) and `File.name LIKE
'Abstimmung%'` (2,299 files) and asked whether those hint at
pair-relevant evidence beyond section 1–2 — including whether
"not TOP-granular" meeting-level files can be addressed by text
segmentation.

### A. `Abstimmung%` files (2,299) — per-TOP BALLOT RESULTS

Sampled heads show a uniform KPanel/QUINTA screenshot format: the TOP
number (ST `## TOP 19` or in the name "Abstimmungsergebnis TOP 7"),
session timestamp ("16:54 21 Oct 2025"), and the vote tallies —
`JA/NEIN/ENTHALTUNG` counts plus the party seat maps (GRÜNE, CDU, SPD,
AfD, FDP, FW, VOLT, LINKE, KAL, FÜR). 39/40 sampled names carry a TOP
number. Attachment distribution:

| link | rows | addressable |
|---|---|---|
| `File__paper__Paper` | 1,298 | ✅ direct pair path |
| `File__meeting__Meeting` | 281 | via meeting date + TOP |
| `AgendaItem__auxiliaryFile__File` | 2 | |
| unattached | 1,739 | name TOP + text timestamp → registry path |

This is exactly the *" ballot result with votes" evidence class the
spec calls out for Karlsruhe (single-page PDF poll screenshots) — and
it maps to the *request/response vote weight* (noul-style tallies per
request). Integration: kgProtocols candidate class `Abstimmung` —
paper-linked files direct, the rest via (meeting date, TOP); verification
== TOP number + session date (outcome wording does not exist here — the
SCREENSHOT *IS* the result; JA/NEIN counts parse deterministically).

### B. `File__meeting__Meeting` prot files (1,274) — mixed

Random samples: Ortschaftsrat full-session Niedschriften (out of GR
scope), HA per-TOP extracts (out of scope but same mechanism), and GR
single-TOP extracts ("Protokoll TOP 29.2" 2016 — pair-relevant when GR +
TOP resolvable). Not a separate mechanism; the existing TOP+OUTCOME
verification plus the `File__meeting` link extends per-TOP coverage to
files that never attached to papers.

### C. `Meeting__auxiliaryFile__File` GR (1,471) — segmentation candidates

Random samples: 1-chunk "Sitzungseröffnung" extracts (no results — skip
correctly), but ALSO full-session Niedschriften (e.g. "Protokoll TOP 4",
22.02.2011: 111 chunks, 636k chars, zugestimmt×18, abgelehnt×52). GR
Meeting-aux prot files with chunks: **320**; of those, **14 multi-TOP
candidates (>5 chunks)**. Text segmentation on `Punkt <n> der
Tagesordnung` boundaries yields per-TOP slices → pair-addressable via
(existing) session date + TOP + outcome wording verification. Small but
real coverage win, mostly for 2010s sessions where per-TOP extracts are
absent.

### Verdict

The operator's four counts confirm the missing evidence classes were
**not secret** — they were attachment-model blind spots:
- `Abstimmung%` (2,299) = vote-weight evidence → NEW highest-value
  candidate class (name TOP 97 %+; 1,298 paper-linked; 1,739 recoverable
  via name/text registry).
- Multi-TOP session Niedschriften → segmentable (14 large GR files,
  plus the single-TOP GR extracts inside `File__meeting` 1,274).
- `zugestimmt/abgelehnt/beschlossen` chunk counts (3.4k–8.5k) reflect
  mostly protocol body text, already reachable through the kgProtocols
  text verification — no new mechanism needed beyond what D12 checker
  tuning collects.
