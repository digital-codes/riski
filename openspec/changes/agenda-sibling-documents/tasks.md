# Tasks

## 1. Traversal-Erweiterung (find_related_objects)

- [ ] 1.1 Neuer Parameter `agenda_item_sids` (Name-Treffer-Seeds): TOPs werden vorab in `related_objects["AgendaItem"]` geladen; Unit-Test mit Stub-Tabellen (`pytest src/tests -m unit`).
- [ ] 1.2 Step 1.b: alle Dateien der gesammelten TOPs (`AgendaItem__auxiliaryFile__File`, tgtSid NOT IN Seed-sids) als `AuxFile` + Kanten; Block-Ermittlung (meetingSid + Nummern-Präfix) zieht die Geschwister-TOPs und deren Dateien nach; Dedup gegen Seeds und bereits gesammelte; Integrationstest (`pytest src/tests`).

## 2. Antwortmengen-Erweiterung (search_stage)

- [ ] 2.1 Seeds aus `matched_entities` (AgendaItem-oparlKeys → sids) an `find_related_objects` übergeben; Unit-Test (`pytest src/tests -m unit`).
- [ ] 2.2 TOP-Block-Erweiterung: Block = TOPs derselben Sitzung mit gleichem ganzzahligem Nummern-Präfix („13.2“ → 13, 13.1, 13.2, …); TOP→Dateien-Mapping aus den Kanten; Erweiterung von `top_files` (gleiche Feldform, `distance: None`, `via` = Block-Referenz), Dedup; Unit-Tests inkl. Nummern-Format-Fälle (13.2/13.10/leer) (`pytest src/tests -m unit`).
- [ ] 2.3 Integrationstest: reale Suche mit TOP-gebundenem Dokument — Geschwister in top_files, Graph (AuxFile-Knoten + Kanten), summary_files; Dedup geprüft (`pytest src/tests`).

## 3. Frontend-Kennzeichnung

- [ ] 3.1 `summary_files` reichen `via` durch; Dokumentenliste gruppiert TOP-Geschwister hinter den Suchtreffern mit Label („weitere Dokumente von TOP …“); `npm run build` + manuelle Prüfung.
- [ ] 3.2 Graph-Popup der Geschwister-Knoten zeigt TOP-Provenienz (Attr `via`), falls bereits Attr-Mechanik vorhanden (sonst zurückstellen).

## 4. Verifikation

- [ ] 4.1 Testsqueries: „sanierung theater“ (TOP-gebundene Dokumente), ein Query auf einen TOP-Namen — kompletter Block (13.1/13.2/13.3) in top_files, andere TOPs derselben Sitzung ausgeschlossen, Summarizer-Prompt enthält alle, Dokumentenliste nummeriert durchgehend.
- [ ] 4.2 Volltext-Suite grün (`python -m pytest src/tests -q`); `openspec validate agenda-sibling-documents --strict`.
