# Design

## Context

- `find_related_objects` (pgTimeline): step 1 sammelt TOPs der Seed-Dateien
  (via `AgendaItem__auxiliaryFile__File`, srcSid = TOP, tgtSid = Datei);
  step 2.b sammelt für Papers alle zugehörigen Dateien als `AuxFile` — das
  Gegenstück für TOPs fehlt. `AuxFile`-Einträge tragen dieselben Felder wie
  Seed-Dateien (sid, oparlKey, name, fileName …).
- `search_stage`: `matched_entities` aus `hybrid_candidates` enthalten
  AgendaItem-Treffer (Namenssuche) mit `oparlKey` — bislang ungenutzt für
  die Traversierung.
- `ResultSummarizer.summarize` konsumiert `result["top_files"]`
  (nummeriert, keine Cap); Zusammenfassungs-Liste und Map-Scope folgen
  `summary_files` ⊂ `top_files` — Erweiterung muss daher in `top_files`
  geschehen, nicht in einem Seitenkanal.
- Chunk-Ebene (content-chunking): Geschwister-Dokumente >8k haben bereits
  Chunk-Vektoren; ≤8k Einzel-Vektoren — `_file_text` im Summarizer liest
  `File.content`/Teaser, beides vorhanden.

## Goals / Non-Goals

**Goals:** vollständige TOP-Dokumentmengen in Zusammenfassung, Liste, Map
und Graph; TOP-Name-Treffer werden „antwortfähig“; Provenienz sichtbar.

**Non-Goals:** keine weitergehende Traversierung der Geschwister-Dokumente
(Papers/Sitzungen der Geschwister bleiben außerhalb); keine Änderung an
Reranking/Fusion; keine dauerhafte Speicherung der Erweiterung
(Ableitung zur Laufzeit).

## Decisions

### 1. Step 1.b als Spiegel von step 2.b

Für alle in related_objects gesammelten TOPs (aus Seed-Dateien **und** aus
Name-Treffern) werden alle verknüpften Dateien geladen
(`AgendaItem__auxiliaryFile__File` where srcSid in agenda_sids, tgtSid NOT
IN seed-sids) und als `AuxFile` + Kanten (`AgendaItem --auxiliaryFile-->
AuxFile`) aufgenommen. Dedup gegen bereits gesammelte Dateien.

### 2. Name-Treffer als Traversal-Seeds

`search_stage` extrahiert aus `hyb["matched_entities"]` die
AgendaItem-oparlKeys und reicht deren sids (Lookup per oparlKey) als neuen
Parameter `agenda_item_sids` an `find_related_objects` weiter. Dort werden
diese TOPs vorab in `related_objects["AgendaItem"]` geladen (mit denselben
Feldern wie step 1), damit step 1.b sie einsammelt.

### 3. Erweiterung von `top_files` nach dem Graph-Build — TOP-Block-Ebene

Betroffen ist der gesamte **TOP-Block**: Trifft ein Seed-File (oder ein
Name-Treffer) TOP 13.2, umfasst die Erweiterung alle TOPs derselben
Sitzung mit gleichem Nummern-Präfix (13, 13.1, 13.2, 13.3, …). Gruppierung:
`meetingSid` gleich UND ganzzahliger Präfix von `number` vor dem ersten
Punkt identisch; TOPs ohne Nummer bleiben Einzelobjekte. Andere TOPs der
Sitzung (3, 5, 11, …) zählen nicht als verwandt (User-Klarstellung:
Dokumente unter einem Block sind verwandt, die TOPs der Sitzung darunter
nicht).

Umsetzung: die Traversierung (step 1 + 1.b) sammelt je Meeting bereits die
Block-Nummern — nach dem Graph-Build wird das TOP→Dateien-Mapping aus den
Kanten (`edges`: source = `AgendaItem_<key>`, target = `AuxFile_<key>`)
um die Block-Präfixregel erweitert. Die nicht-seed-Dateien aller Block-TOPs
werden als vollständige top_files-Einträge (gleiche Feldform,
`distance: None`, `match: None`, `via: "TOP 13"`) **angehängt** —
Reihenfolge: Suchtreffer, dann Geschwister gruppiert je Block.
`full_index`/Nummerierung im Summarizer bleibt unangetastet
(kontinuierlich über beide Gruppen).

### 4. Keine Cap, kein Reranking der Geschwister

`top_k` begrenzt nur die Suchtreffer (User-Vorgabe). Geschwister erhalten
keinen Rerank-Score (kommen hinter allen Treffern). Prompt-Wachstum ist
durch die TOP-Dateianzahl natürlich begrenzt (typ. 2–10).

### 5. Frontend-Kennzeichnung minimal

`summary_files`-Einträge bekommen `via` durchgereicht; die Dokumentenliste
rendert ein Gruppierungs-Label („weitere Dokumente von TOP 13.2“). Map/
Netzwerk folgen der bestehenden Logik ohne Änderung.

## Risks / Trade-offs

- [Prompt wächst (mehr Dateien je TOP)] → natürlich begrenzt; Summarizer
  hat Teaser-Ebene (kurze Texte) — worst case ein paar tausend Zeichen mehr.
- [Map-Scope wächst um TOP-Geschwister] → konsistent mit „Antwortmenge =
  Dokumentenliste“; Nutzersteuerung (Abwählen) greift wie bisher.
- [Doppelte Traversierung von TOP↔Dateien bei vielen Seeds] → eine SQL-
  Abfrage mit IN-Liste je Schritt; Kardinalität wie step 2.b.
- [Nummern-Formate variieren („13.2“, „13.2a“, „13 “, leere Nummer)] →
  Präfix-Regel: ganzzahliger Teil vor dem ersten Punkt; leere/unklare
  Nummern bleiben Einzelobjekte (kein Block); Häufigkeitsanalyse der
  Nummernformate in Task 1.2.

## Migration Plan

Rein laufzeitseitige Ableitung; kein Deploy-Risiko für Bestandsdaten.
Rollback = revert.

## Open Questions

- Soll die Kennzeichnung im Graph (`AuxFile`-Attrs) zusätzlich `via`
  tragen (Popup „aus TOP 13.2“)? — Implementierungsdetail, Task 3.
