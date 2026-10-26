# Design

## Context

Siehe proposal.md. Relevanter Ist-Zustand:

- **Daten vorhanden**: `Paper` (reference, papertype, date), `AgendaItem.result`
  (Freitext-Ergebnis, >7.000 gefüllt), `Paper__subordinatedPaper__Paper` /
  `Paper__superordinatedPaper__Paper` (Folgevorlagen-Assoziationen), Geo-Links
  (Stadtteile), 177 kommende Sitzungen, 11.898 Protokolldateien.
  `Paper__underDirectionOf__Organization` = zuständige Fachbereiche/Ämter,
  **nicht** Einbringer (verifiziert: Join über `tgtSid` → Organisationen sind
  Ämter, keine Fraktionen) — Einbringer also regelbasiert aus Labels.
- **API**: FastAPI in `src/apiServer.py`, Facetten-Endpoint existiert
  (paperType, years, result, organization, tags); Sessions in-memory; die
  Read-Only-Engine bedient alle Lese-Endpoints.
- **Frontend**: Vue 3, hash-Router mit Menü-Button (SiteNav), Seiten als
  Komponenten in `app/src/components/`; kein Router-Framework (eigener
  `router.js`), kein State-Layer.
- **Vorbilder**: GemeinderatsRadar (Filter-/Detailstruktur), DIS
  (Einbringer-Chips, `vote_parse.py` Vision-Ansatz), offizieller
  Sitzungskalender (nicht kopieren).

## Goals / Non-Goals

**Goals:**
- Explorations-Sicht (Browse/Detail/Sitzungen) auf bestehenden Daten — ohne
  neue externe Dienste und ohne LLM-Kosten (Einbringer regelbasiert).
- Wiederverwendung der bestehenden Muster: Endpoints in `apiServer.py`
  (oder einem eigenen Router-Modul), Tests in `src/tests`, Frontend-Seiten
  analog LegalPage/WorkPage.
- Beschluss-Status und Einbringer als **facettierbare** Felder von Anfang an.

**Non-Goals:**
- Kein Ersatz des Sitzungskalenders (keine Gremien-/Mandatsverwaltung).
- Keine Volltextsuche-Neuerfindung — Browse nutzt strukturierte Filter, nicht
  den hybriden Recall.
- Keine Live-Ticker-/VOD-/Vision-Integration im Hauptumfang (Abstimmungs-
  parsing nur als separater Go/No-Go-Spike, Task 5).
- Keine Authentifizierung/User-Konzepte für Feeds/Abos (auf Feed-Task
  bewusst verzichtet).

## Decisions

### 1. Neue Lese-Endpoints in einem eigenen Modul, eingebunden in apiServer

`src/councilViews.py` (oder Ähnliches) liefert die Query-Helfer (Papers-Filter,
Detail, Meetings, ICS); `apiServer.py` bindet die Routes ein. Rationale: die
API-Datei ist bereits >600 Zeilen; Browse-Queries (Paginierung, Facettenzählung)
sind ein eigenes Themenfeld. Alternative — alles in apiServer — wird zu unübersichtlich.

### 2. Einbringer: regelbasiert, als Paper-Spalte, Backfill-Script

Parser mit Musterlisten auf Paper-/File-Bezeichnungen („Antrag CDU_014“,
„Anfrage FW-FÜR …“, „Antrag Nr. N <Fraktion>“, gemeinsame Einbringung per
Trenner). Fraktions-Vokabular wird aus dem Korpus selbst abgeleitet
(Häufigkeitsanalyse der Labelpräfixe — DIS zeigt, dass dieFraktionsnamen
konsistent in Labels auftreten). Speicherung als Spalte `submitter` (bzw.
`submitters` als kommagetrennte Liste für Joint Submissions) auf `Paper`
analog zum `File_tags`-Migrationsmuster; Backfill-Script idempotent/resumable.
Alternative — LLM-Klassifikation — verworfen: DIS zeigt, dass Regeln reichen,
und das vermeidet LLM-Kosten und Nichtdeterminismus.

### 3. Beschluss-Status: abgeleitet, nicht materialisiert (v1)

`AgendaItem.result` → kontrollierter Status via Funktionsmapping (inkl.
Heuristik „enthält ‚abgelehnt‘“ etc.), berechnet in den Endpoints/`build_graph`
statt einer neuen Spalte. Begründung: der Freitext ist stabil und klein
(~19k Zeilen); Materialisierung kann später folgen, falls Browse-Queries
zu langsam werden. Vokabular: approved, rejected, noted, withdrawn,
deferred, other (leer = kein Ergebnis).

### 4. Browse-Query-Form: ein Endpoint, strukturierte Filter

`GET /papers?year=&type=&submitter=&decision=&district=&page=` — Filter als
AND-verknüpfte WHERE-Klauseln; Stadtteil-Filter über die bestehenden
`Districts_items_Files`-Links (auf File-Ebene, dann auf Paper gemappt) oder —
falls die Verknüpfung Paper↔Stadtteil über Files zu unpräzise ist — über
`Paper.location`-Referenzen, je nach Datenlage (Spike in Task 3.1 enthalten).
Paginierung serverseitig (offset/limit, Standard 25).

### 5. ICS-Generation im Backend, stdlib-only

`GET /meetings/{id}/calendar.ics` erzeugt iCalendar-Text (VEVENT mit
DTSTART/DTEND in Europe/Berlin, öffentliche TOPs als Untereinheiten oder
DESCRIPTION-Liste — v1: DESCRIPTION, simpler und parser-sicher). Keine neue
Abhängigkeit (ics-Bibliotheken unnötig für VEVENT-Basis). Content-Type
`text/calendar`.

### 6. Frontend: zwei neue Seiten, keine Router-Umstellung

`/vorlagen` und `/sitzungen` als Komponenten im bestehenden hash-Router
(`router.js` ROUTES erweitern, App.vueConditionen, Menü-Einträge in SiteNav).
Listen mit clientseitigem Filterzustand (URL-Query-Parameter sync wie im
GemeinderatsRadar — `?year=2020`), damit gefilterte Sichten teilbar sind.

### 7. Abstimmungs-Spike: zwei Vision-Routen, Zähler-Plausibilisierung als Güteschwelle

Task 5 vergleicht (a) Mistral-Vision-Chatmodell (Bild-Content-Part im
bestehenden `remote.chat` — der OCR-Endpoint taugt nicht: reiner
Textextraktor ohne Farb-/Layoutverstehen) gegen (b) OpenRouter+Gemini (DIS-
Setup, `vote_parse.py` als Vorlage). Güteschwelle vor Weiterbau: Summe der
Member-Stimmen = die drei Zähler bei ≥90 % der Testpanels; Stichproben gegen
`AgendaItem.result`. Bekannte Grenzen werden im Spike-Dokument festgehalten:
Layoutwechsel, angeschnittene Zähler, Farbähnlichkeit (GELB/ROT/GRAU),
Modell-„Raten“ bei unklaren Kacheln (DIS-Prompt: „nur klar erkennbare
Kacheln“). PDF-Quelle bleibt autoritativ vor Live-Re-Parses (DIS-Prinzip).

## Risks / Trade-offs

- [Stadtteil-Filter über File-Links könnte Paper↔Stadtteil unvollständig abbilden] →
  Task 3.1 beginnt mit einem Daten-Spike (Abdeckung Paper→District); falls
  unzureichend, Alternative `Paper`-Location-Felder nutzen oder den Filter
  auf File-Ebene anbieten.
- [`AgendaItem.result`-Freitext enthält Varianten jenseits des Vokabulars] →
  Mapping-Tabelle + „other“-Fallback; Häufigkeitsanalyse in Task 1.1
  deckt unbekannte Muster auf, bevor die Vokabular-Liste fixiert wird.
- [Einbringer-Regeln produzieren False Positives bei ungewöhnlichen Labels] →
  Vokabular nur aus bestätigten Fraktionsnamen; Unscharfe Fälle bleiben leer
  (permissive Prinzip wie beim GeoGate).
- [Browse-Queries ohne Materialisierung könnten bei 13k+ Papers langsam werden] →
  Indizes auf `reference`, `papertype`, `date` prüfen; falls nötig, ist die
  Materialisierung des Beschluss-Status ein nachziehbarer Folgeschritt.
- [Abstimmungs-Spike: Vision-Modelle raten bei unklaren Kacheln] →
  Zähler-Plausibilisierung als harte Güteschwelle; ohne Bestehen kein Weiterbau
  (Go/No-Go in Task 5.3).

## Migration Plan

1. Backend-Endpoints + Einbringer-Backfill (Tasks 1–2), unabhängig deploybar
   (nur additive Endpoints/Spalten).
2. Frontend-Seiten (Tasks 3–4) im selben Repo-Deploy wie das Backend.
3. Abstimmungs-Spike (Task 5) strikt getrennt; kein Deploy vor Go-Entscheid.
4. Rollback: revert — keine destruktiven Schemaänderungen (submitter-Spalte
   bleibt ohne Schaden).

## Open Questions

- Paper↔Stadtteil: Verknüpfung über File-Geo-Links präzise genug für den
  Filter? (Task 3.1 Daten-Spike)
- Kollation/Normalisierung der Fraktionsnamen (CDU vs. CDU-Fraktion vs.
  „CDU in Hebelstraße“-Gremium) — Vokabular-Liste in Task 2.1 festzulegen.
