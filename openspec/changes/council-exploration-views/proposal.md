# Proposal: council-exploration-views

## Why

riski beantwortet Fragen, bietet aber keine Explorations- und Stöber-Sicht auf den
Ratsinformationsbestand. Ein Vergleich mit dem offiziellen Sitzungskalender
(nur Stichwortsuche mit Zeitraum und vier Bereichen), dem GemeinderatsRadar
(karlsruhe-oparl-viewer: Vorlagen-Browse mit Filtern, Bezirksansicht, Feeds,
.ics) und dem Desinformationssystem (DIS: Facetten inkl. Einbringer,
Abstimmungsergebnisse, Live-Ticker) zeigt: die Daten für eine echte
Explorations-Ebene liegen bei riski bereits vollständig in der Datenbank
(Paper.reference, AgendaItem.result mit ~7.000 Beschlussausgängen, 177 kommende
Sitzungen, Folgevorlagen-Assoziationen, Stadtteil-Verknüpfungen) — es fehlt
nur die Sicht darauf. Das ergänzt unsere QA-Stärke (Frage → belegte Antwort)
um das, was die anderen Systeme gut können, ohne den Sitzungskalender zu
kopieren: unsere Alleinstellung (fragegeleitete Zusammenfassung, semantische
Hybridsuche, nutzergesteuerte Dokumentenmenge) bleibt bestehen.

## What Changes

- **Beschluss-Status sichtbar und filterbar** — der strukturierte
  `AgendaItem.result` („einstimmig beschlossen“, „mehrheitlich abgelehnt“,
  „Kenntnisnahme“, …) wird als normalisierter Beschluss-Status exponiert:
  Filter-Fazette, Anzeige am Tagesordnungspunkt (Netzwerk-Detail, Zeitachse)
  und Berücksichtigung in den Suchergebnissen.
- **Einbringer-Erkennung (regelbasiert)** — Einbringende Fraktion/Gruppe wird
  aus Vorlagen-/Datei-Bezeichnungen geparst („Antrag CDU_014“, „Antrag 149
  KULT …“; DIS zeigt, dass das regelbasiert zuverlässig geht). Speicherung als
  Anreicherung, Fazette + farbige Kennzeichnung. (Hinweis: OParl
  `underDirectionOf` = zuständige Fachbereiche/Ämter, *nicht* Fraktionen —
  regelbasiertes Label-Parsing ist der richtige Weg.)
- **Vorlagen-Browse und -Detail** — Stöber-Seite für Beschlussvorlagen/Anträge
  mit Filtern (Jahr, Dokumenttyp, Einbringer, Beschluss-Status, Stadtteil) und
  Detailansicht (Vorlagen-Nummer, Beratungskette über Consultations, zugehörige
  Dateien, Folgevorlagen-Kette via `subordinatedPaper`/`superordinatedPaper`).
- **Sitzungs-Ansicht** — kommende Sitzungen (177 in der DB), Tagesordnung der
  Sitzung, Download einer Sitzung als `.ics`-Kalendereintrag.
- **Update-Feeds** — RSS-Feeds pro Gremium und pro Stadtteil (neue/geänderte
  Vorlagen und Sitzungen), abonnierbar.
- **SEPARAT / EXPERIMENTELL — Abstimmungspanel-Parsing**: Abstimmungsergebnisse
  mit Namensaufruf aus den bildbasierten „Abstimmungsergebnis“-PDFs und
  Live-Ticker-Panels rekonstruieren. Das Panel ist farbcodiert (GELB = Ja,
  ROT = Nein, GRAU = Enthaltung/abwesend), das Layout hat sich mehrfach
  geändert, Zähler sind teils angeschnitten — reines OCR reicht nicht. DIS
  löst das mit einem Vision-Modell (Prompt beschreibt das Panel-Layout,
  JSON-Rückgabe `{ja, nein, enthaltung, members[]}`, Zähler exakt ablesen,
  Member-Kacheln „nur klar erkennbar“). Als eigener Task mit
  Go/No-Go-Entscheidung nach einem Spike (siehe tasks.md).

## Capabilities

### New Capabilities

- `paper-exploration`: Stöber-Sicht auf Vorlagen — Browse mit Filtern
  (Jahr, Typ, Einbringer, Beschluss-Status, Stadtteil), Vorlagen-Detail mit
  Beratungskette, Dateien und Folgevorlagen-Kette.
- `meeting-calendar`: kommende Sitzungen mit Tagesordnung und `.ics`-Download
  je Sitzung.
- `update-feeds`: RSS-Feeds pro Gremium und Stadtteil für neue/geänderte
  Vorlagen und Sitzungen.

### Modified Capabilities

- `data-enrichment`: Einbringer-Erkennung (regelbasiert) und normalisierter
  Beschluss-Status als zusätzliche Anreicherungen.
- `search-api`: Facetten-Endpoint um Beschluss-Status und Einbringer
  erweitert; Such-/Browse-Ergebnisse tragen beide Felder.

## Impact

- **Backend**: neuer Browse-/Feed-/Kalender-Endpoint-Bereich in
  `src/apiServer.py` (oder eigenes Modul), Regel-Parser für Einbringer
  (neu, ohne LLM), Beschluss-Status-Normalisierung, Facetten-Erweiterung.
- **Frontend**: neue Seiten (Vorlagen, Sitzungen, Feeds) im Menü,
  Detailansichten, Fazetten-UI; Erweiterung der Ergebnis-Anzeige um
  Beschluss-Status und Einbringer-Chips.
- **Datenbank**: keine Schemaänderung zwingend (Einbringer als Anreicherungs-
  spalte auf Paper analog `File_tags`-Muster; Beschluss-Status aus
  `AgendaItem.result` abgeleitet, ggf. materialisierte Normform).
- **Abhängigkeiten**: keine neuen externen Dienste für 1–5; der separate
  Abstimmungs-Spike braucht wahlweise ein Vision-Modell (Mistral-Vision-
  Chatmodell testen; OCR-Endpoint taugt nicht — kein Farb-/Layoutverstehen).
