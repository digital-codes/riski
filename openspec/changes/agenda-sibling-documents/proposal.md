# Proposal: agenda-sibling-documents

## Why

Die Zusammenfassung betrachtet heute ausschließlich die ≤ `top_k` (10)
Suchtreffer — selbst wenn ein Treffer nachweislich zu einem Tagesordnungspunkt
gehört, dessen weitere Dokumente relevant sind. Zwei Lücken:

1. **Geschwister-Dokumente eines TOP** — für Papers werden alle zugehörigen
   Dateien eingesammelt (pgTimeline step 2.b → `AuxFile`), für Tagesordnungs-
   punkte fehlt das Gegenstück: ein Dokument unter TOP 13.2 findet zwar seinen
   TOP, aber nicht die übrigen Dokumente desselben TOP.
2. **TOP-Treffer über Namenssuche** — die hybride Suche matcht AgendaItem-
   Namen (lexikalisch + Namensvektoren) in `matched_entities`, aber nur
   File-Zeilen werden zu Kandidaten: ein Treffer auf „TOP 13.2 Sanierung …“
   liefert null Dokumente, und der Knoten taucht nicht einmal im Graphen auf
   (die Traversierung wird nur über File-sids gespeist).

Damit fasst der Summarizer die Antwortmenge unvollständig zusammen, obwohl
alle Daten eine Join-Ebene entfernt liegen.

## What Changes

- **Traversal-Erweiterung (step 1.b)** — für alle gefundenen
  Tagesordnungspunkte werden sämtliche verknüpften Dateien eingesammelt
  (`AgendaItem__auxiliaryFile__File`, beide Richtungen; noch nicht enthaltene
  als `AuxFile` + Kante — Spiegelbild zu step 2.b für Papers).
- **AgendaItem-Name-Treffer als Traversal-Seeds** — AgendaItems, die per
  Namenssuche getroffen wurden, werden als zusätzliche Seeds an
  `find_related_objects` übergeben; ihre Knoten und Dokumente gelangen in
  Graph und Antwortmenge.
- **Erweiterte Antwortmenge für den Summarizer** — `top_files` wird um die
  Dokumente des gesamten TOP-Blocks erweitert: trifft die Suche ein Dokument
  von TOP 13.2, kommen alle Dokumente von 13.1, 13.2, 13.3, … derselben
  Sitzung dazu (gleicher Nummern-Präfix vor dem ersten Punkt). Andere TOPs
  derselben Sitzung (3, 5, 11, …) gelten als unverwandt und bleiben
  ausgeschlossen. Dedup gegen die Suchtreffer, angehängt hinter den
  relevanzsortierten Treffern, mit Provenienz-Marker `via` = TOP-Block;
  `top_k` gilt nur für die Suchtreffer, nicht für die erweiterte Menge.
  Der Summarizer selbst bleibt unverändert — er konsumiert weiterhin
  `top_files`.
- **Frontend-Kennzeichnung** — Dokumente aus der TOP-Erweiterung sind in der
  Dokumentenliste gekennzeichnet (gruppiert hinter den Suchtreffern).

## Capabilities

### New Capabilities

- `agenda-answer-expansion`: Erweiterung der Antwortmenge um alle Dokumente
  betroffener Tagesordnungspunkte (Geschwister-Dokumente) und um Dokumente
  von per Namenssuche getroffenen TOPs; Provenienz-Marker und Dedup.

### Modified Capabilities

- `result-summarizer`: Die Zusammenfassungs-Eingabemenge ist die erweiterte
  Antwortmenge (Suchtreffer + TOP-Geschwister), nicht mehr auf `top_k`
  begrenzt; die Dokumentenliste nummeriert beide Gruppen konsistent.

## Impact

- **Backend**: `pgTimeline.find_related_objects` (neuer Parameter
  `agenda_item_sids`, neuer Schritt 1.b), `search_stage` (Seeds aus
  `matched_entities`, Erweiterung von `top_files` nach dem Graph-Build).
- **Frontend**: Dokumentenliste gruppiert/kennzeichnet TOP-Erweiterungen;
  kein Verfahrenswechsel (Liste, Karte, Netzwerk folgen der bestehenden
  summary_files/top_files-Logik).
- **Kosten/Risiko**: Prompt wächst um die Zusatzdokumente (Teaser-Ebene —
  begrenzt; TOPs haben typischerweise 2–10 Dateien); Karte/Netzwerk-Menge
  wächst entsprechend der erweiterten Antwortmenge (Konsistenz statt
  Überraschung — die Dokumente gehören nachweislich zum selben TOP).
