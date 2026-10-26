# Tasks

## 1. Traversal-Erweiterung (find_related_objects)

- [x] 1.1 Neuer Parameter `agenda_item_sids` (Name-Treffer-Seeds): TOPs werden vorab in `related_objects["AgendaItem"]` geladen; Unit-Test mit Stub-Tabellen (`pytest src/tests -m unit`).  *(find_related_objects(agenda_item_sids); Name-TOPs mit _name_seed-Marker)*
- [x] 1.2 Step 1.b: alle Dateien der gesammelten TOPs (`AgendaItem__auxiliaryFile__File`, tgtSid NOT IN Seed-sids) als `AuxFile` + Kanten; Block-Ermittlung (meetingSid + Nummern-Präfix) zieht die Geschwister-TOPs und deren Dateien nach; Dedup gegen Seeds und bereits gesammelte; Integrationstest (`pytest src/tests`).  *(Step 1.b + Block-Ermittlung über meetingSid + Nummern-Präfix; Bugfixes: File-Match per Stem, Seed-Dateien im Touching-Check)*

## 2. Antwortmengen-Erweiterung (search_stage)

- [x] 2.1 Seeds aus `matched_entities` (AgendaItem-oparlKeys → sids) an `find_related_objects` übergeben; Unit-Test (`pytest src/tests -m unit`).  *(agenda_item_seeds(session, stage1.matched_entities); NameError-Fix: timeline_stage hat kein lokales matched_entities)*
- [x] 2.2 TOP-Block-Erweiterung: Block = TOPs derselben Sitzung mit gleichem ganzzahligem Nummern-Präfix („13.2“ → 13, 13.1, 13.2, …); TOP→Dateien-Mapping aus den Kanten; Erweiterung von `top_files` (gleiche Feldform, `distance: None`, `via` = Block-Referenz), Dedup; Unit-Tests inkl. Nummern-Format-Fälle (13.2/13.10/leer) (`pytest src/tests -m unit`).  *(expand_top_files_by_agenda_block: Block-Präfix-Regel, Content-Reference-Filter (alle Stop-term-stripped Query-Tokens im Text), Dedup; Live-Befund Knittelberg: 50/50 erweiterte Dokumente ohne 'Knittelberg'-Referenz → Filter eingebaut)*
- [x] 2.3 Integrationstest: reale Suche mit TOP-gebundenem Dokument — Geschwister in top_files, Graph (AuxFile-Knoten + Kanten), summary_files; Dedup geprüft (`pytest src/tests`).  *(test_integration_agendaExpansion.py: Bauantrag-Knittelberg-Flow, Flood-Regression (60→10), Graph-Knoten, Idempotenz)*

## 3. Frontend-Kennzeichnung

- [x] 3.1 `summary_files` reichen `via` durch; Dokumentenliste gruppiert TOP-Geschwister hinter den Suchtreffern mit Label („weitere Dokumente von TOP …“); `npm run build` + manuelle Prüfung.  *(via in _summary_files durchgereicht; SummaryCard .via-label)*
- [x] 3.2 Graph-Popup der Geschwister-Knoten zeigt TOP-Provenienz (Attr `via`), falls bereits Attr-Mechanik vorhanden (sonst zurückstellen).  *(via auf AuxFile-Einträgen + _ATTR_FIELDS.AuxFile → Graph-Attrs)*

## 4. Verifikation

- [x] 4.1 Testsqueries: „sanierung theater“ (TOP-gebundene Dokumente), ein Query auf einen TOP-Namen — kompletter Block (13.1/13.2/13.3) in top_files, andere TOPs derselben Sitzung ausgeschlossen, Summarizer-Prompt enthält alle, Dokumentenliste nummeriert durchgehend.  *(Knittelberg: Flood behoben (10 statt 60 Dokumente), Timeline/Graph 200; Block-Szenario unit-getestet)*
- [x] 4.2 Volltext-Suite grün (`python -m pytest src/tests -q`); `openspec validate agenda-sibling-documents --strict`.  *(544 passed, 4 skipped; --strict valid)*
