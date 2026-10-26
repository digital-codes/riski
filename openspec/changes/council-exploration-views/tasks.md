# Tasks

## 1. Beschluss-Status (AgendaItem.result)

- [ ] 1.1 Normalisierung der `AgendaItem.result`-Freitexte auf einen kontrollierten Status (zugestimmt/beschlossen, abgelehnt, Kenntnisnahme, zurückgezogen, vertagt, sonstiges) inkl. Ja/Nein-Heuristik; Häufigkeitsverteilung gegen die Live-DB prüfen (>7.000 Werte); Einheit testen (`pytest src/tests -m unit`).
- [ ] 1.2 Status in der Pipeline verfügbar machen: AgendaItem-Knoten im Graph um `decision`-Attribut ergänzen (`build_graph`), Such-/Browse-Ergebnisse tragen den Status; Einheit + Integrationstest (`pytest src/tests`).
- [ ] 1.3 Facette `decision` am `GET /facets`-Endpoint + Filterunterstützung in Browse/Suche; API-Test (`pytest src/tests -m integration`).
- [ ] 1.4 Frontend: Status-Chip am TOP (DetailPanel/Zeitachse), Fazette in der Vorlagen-Browse (Task 3), Tests im Frontend-Build (manuell + `npm run build`).

## 2. Einbringer-Erkennung (regelbasiert)

- [ ] 2.1 Regel-Parser für Einbringer aus Paper-/Datei-Bezeichnungen (Muster „Antrag <Fraktion>_…“, „Anfrage <Fraktion> …“, „Antrag Nr. N <Fraktion>“, gemeinsame Einbringung); Fraktions-Vokabular aus den Labels selbst ableiten (Häufigkeitsanalyse gegen die Live-DB); Einheitstests mit realen Labelbeispielen (`pytest src/tests -m unit`).
- [ ] 2.2 Speicherung als Paper-Anreicherung (Spalte analog `File_tags`-Muster, oder Tabelle) + Backfill-Script über alle Papers; idempotent/resumable; Integrationstest (`pytest src/tests`).
- [ ] 2.3 Fazette `submitter` + Anzeige (farbige Chips wie bei DIS) in Browse und Suchergebnissen; API-Test (`pytest src/tests -m integration`).

## 3. Vorlagen-Browse und -Detail

- [ ] 3.1 Browse-Endpoint: `GET /papers` mit Filtern (Jahr, Typ, Einbringer, Beschluss-Status, Stadtteil), Paginierung, Sortierung; DB-Indizes prüfen/setzen; Integrationstest (`pytest src/tests -m integration`).
- [ ] 3.2 Detail-Endpoint: `GET /papers/{reference}` mit Metadaten, Consultation-Kette (Sitzungen/TOPs mit Datum + Beschluss-Status), zugehörigen Dateien (inkl. Anlagen) und Folgevorlagen-Kette (subordinatedPaper/superordinatedPaper — Assoc-Tabellen existieren, Join-Semantik verifizieren); Integrationstest (`pytest src/tests -m integration`).
- [ ] 3.3 Frontend `/vorlagen`-Seite: Filterleiste + Kartenliste (GemeinderatsRadar-Struktur als Vorbild, eigenes Styling); Detailseite mit Kette; Menu-Eintrag; `npm run build` + manuelle Prüfung.
- [ ] 3.4 Verifikation mit den Testsqueries: „klimaschutzkonzept“ → Jahrbrowse trennt 2013/2017/2020; „forum recht“ → Einbringer-Filter auf CDU/FW-FÜR; dokumentierte Smoke-Checks.

## 4. Sitzungs-Ansicht

- [ ] 4.1 Endpoint `GET /meetings/upcoming` (Datum, Gremium, öffentlich/nicht-öffentlich) + `GET /meetings/{id}` (Tagesordnung mit TOPs, Beschluss-Status, verknüpfte Dokumente); Integrationstest (`pytest src/tests -m integration`).
- [ ] 4.2 `.ics`-Download je Sitzung (`GET /meetings/{id}/calendar.ics`, öffentliche TOPs als Untereinträge, Europe/Berlin); Unit-Test auf ICS-Struktur (`pytest src/tests -m unit`).
- [ ] 4.3 Frontend `/sitzungen`: kommende Sitzungen, Agenda-Aufklapper, .ics-Button; Menu-Eintrag; `npm run build` + manuelle Prüfung.

## 5. SEPARAT: Abstimmungspanel-Parsing (Vision, Go/No-Go)

> Bewusst als eigener, vom Rest unabhängiger Task. Der Beschluss-Status (Task 1)
> deckt das Ergebnis-Level bereits ab; hier geht es um Namensaufrufe
> (ja/nein/enthaltung pro Mitglied) aus den bildbasierten
> „Abstimmungsergebnis“-PDFs und Live-Ticker-Panels.

- [ ] 5.1 Spike-Dokumentation: DIS-Ansatz präzise erfassen (`vote_parse.py`: PDF-Seite 1 → Bild → OpenRouter-Vision-Modell, deutscher Layout-Prompt mit Zähler + farbcodiertem Member-Raster, JSON `{ja, nein, enthaltung, members[]}`, Aliase-Normalisierung, PDF-Quelle autoritativ vor Live-Re-Parse); bekannte Grenzen: Layoutwechsel über Zeit, angeschnittene Zähler, Farb kodierung (GELB/ROT/GRAU) — reines OCR (auch Mistral-OCR-Endpoint) ist ungeeignet, da kein Farb-/Layoutverstehen. Lieferung: `docs/vote-parse-spike.md`.
- [ ] 5.2 Spike-Implementierung an 10–20 realen Panels aus unserer DB (Protokoll-/Abstimmungsdateien): (a) Mistral-Vision-Chatmodell (Bild-Content-Part im bestehenden `remote.chat`) gegen (b) OpenRouter + Gemini-Flash (wie DIS); Qualität = Zähler-Plausibilisierung (Summe der Member-Stimmen muss den drei Zählern entsprechen) + Stichproben gegen AgendaItem.result; Ergebnis dokumentiert (`docs/vote-parse-spike.md`).
- [ ] 5.3 Go/No-Go: nur bei nachweisbar stabiler Zähler-Genauigkeit Weiterbau (Speicherung pro Sitzung+TOP, PDF-Quelle autoritativ, Anzeige im DetailPanel). Bei No-Go: Task hier abhaken und im Spike-Dokument begründet beenden.

## 6. Verifikation

- [ ] 6.1 Gesamtdurchlauf: Browse → Detail → Sitzung mit den Testsqueries („sanierung theater“, „forum recht“, „klimaschutzkonzept“); Volltext-Suite grün (`python -m pytest src/tests -q`).
- [ ] 6.2 `openspec validate council-exploration-views --strict`; README (Site structure + API) ergänzen.
