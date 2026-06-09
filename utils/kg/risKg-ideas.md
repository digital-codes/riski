
# ratsinformations systeme z.b. mit oparl oder allris. gibt es ontologien oder Vokabulare? Deutschland, eu?

Es gibt für Ratsinformationssysteme selbst (OParl/ALLRIS \& Co.) nach aktuellem Stand keinen etablierten, allgemein genutzten RDF‑Ontologie-Standard – OParl ist primär ein JSON/REST-Datenmodell. [^1_1][^1_2][^1_3] Allerdings kannst du sehr gut bestehende allgemeine EU‑ und DE‑Vokabulare (DCAT, EU Vocabularies, DNB/GND usw.) damit kombinieren und dir eine eigene Domänenontologie ableiten. [^1_4][^1_5][^1_6][^1_7]

## Speziell zu OParl und Ratsinfos

- OParl definiert ein objektorientiertes Datenmodell (Body, Meeting, AgendaItem, Paper, Person, Organization etc.) und deren JSON-Schemata, aber ausdrücklich keine RDF-Ontologie. [^1_1][^1_2][^1_3]
- Viele Kommunen (z.B. Bonn, Münster, NRW-Verbund) nutzen OParl 1.1 als Standard-API für ihre Ratsinformationssysteme; es wird als klassische Open‑Data‑Schnittstelle verstanden, nicht als Linked‑Data‑Vokabular. [^1_6][^1_8][^1_9][^1_10]
- Bonn verweist explizit darauf, dass die Metadaten ihrer OParl‑API mit DCAT kompatibel sind, um Interoperabilität zwischen Datenkatalogen zu erreichen – die Semantik liegt also hauptsächlich auf Katalogebene, nicht innerhalb der OParl-Objekte. [^1_6]

Wenn du OParl-Daten als RDF modellieren willst, musst du praktisch selbst eine Ontologie entwerfen und dabei existierende Ontologien wiederverwenden.

## EU-Ebene: EU Vocabularies und DCAT

- Das Publications Office der EU betreibt „EU Vocabularies“: ein Katalog kontrollierter Vokabulare, Schemata, Ontologien und Datenmodelle für verschiedene Domänen (Institutionen, Geografie, Recht, Forschung, öffentliche Verwaltung). [^1_4]
- Für Open‑Data‑Kataloge ist DCAT (bzw. DCAT‑AP für Europa) der zentrale RDF‑Standard; Schulungsmaterial der EU beschreibt explizit, wie man RDF‑Vokabulare entwirft und existierende Vokabulare wiederverwendet. [^1_4][^1_7]
- Beispiele für EU-Ontologien sind etwa EURIO (EUropean Research Information Ontology) für Forschungsprojekte, die nach gängigen Semantic‑Web‑Standards modelliert ist und mit anderen EU‑Ontologien und schema.org/ORG aligniert ist. [^1_11]

Diese EU-Vokabularwelt kannst du z.B. für:

- Datensatz‑/Portalebene: DCAT‑AP für deinen Ratsdatenkatalog. [^1_6][^1_7]
- Organisationen, Personen, Rollen: W3C ORG, FOAF, EU‑org-spezifische Schemata aus EU Vocabularies. [^1_4][^1_11]


## Deutschland: DNB/GND und nationale Vokabulare

- Die Deutsche Nationalbibliothek pflegt mehrere RDF‑Vokabulare, u.a. die GND‑Ontologie (GNDO) für Entitäten der Gemeinsamen Normdatei (Personen, Körperschaften, Geografika etc.). [^1_12][^1_5]
- Zusätzlich gibt es DNB Metadata Terms (DNBT) sowie die Agent Relationship Ontology (AgRelOn) für Beziehungen zwischen Personen und Organisationen. [^1_5]
- Die DNB betont, dass eigene Vokabulare auf bestehenden Standards wie SKOS aufbauen sollen und unterscheidet zwischen strukturellen Vokabularen (Klassen/Relationen) und Value‑Vocabularies (z.B. Code‑Listen, Klassifikationen). [^1_5]

Für Ratsdaten kannst du z.B.:

- GND‑IDs/GNDO für Personen (Ratsmitglieder) und Körperschaften (Fraktionen, Verwaltungseinheiten) nutzen. [^1_5]
- AgRelOn oder eigene SKOS‑Vokabulare für Rollen (z.B. Fraktionsvorsitzende, Ausschussmitglied) einsetzen. [^1_5]


## Wie aus OParl eine Ontologie bauen?

Pragmatischer Ansatz:

- Mapping der OParl-Klassen auf RDF-Klassen: z.B. `oparl:Body` als Subklasse von `org:Organization`, `oparl:Person` als Subklasse von `foaf:Person` oder GND‑Person, `oparl:Meeting` als Event (Event‑Ontologien, schema.org/Event). [^1_1][^1_2][^1_3][^1_4][^1_5]
- Properties aus bestehenden Ontologien verwenden: Termine als Zeitangaben mit OWL‑Time, Links zu Dokumenten mit Dublin Core Terms (`dct:title`, `dct:created`, `dct:subject`) usw. [^1_4][^1_5][^1_7]
- SKOS‑Vokabulare für Gremientypen, Vorlagentypen, Status (eingebracht, beschlossen, vertagt), Drucksachentypen etc. definieren, die du an OParl‑Ressourcen hängst. [^1_5][^1_7]

Die EU‑Guides zum Entwerfen von RDF‑Vokabularen empfehlen explizit dieses Vorgehen: erst Wiederverwendung, dann maßvolle Erweiterungen. [^1_7]


## Grundidee von DCAT-AP

- DCAT-AP ist ein „Application Profile“ des W3C-Standards DCAT (Data Catalog Vocabulary), also eine Spezifikation, wie Datenkataloge und ihre Datensätze in RDF beschrieben werden sollen. [^2_2][^2_4]
- Es wurde im Auftrag der EU-Kommission speziell für europäische Datenportale entwickelt, um Metadatenstrukturen zu vereinheitlichen. [^2_2][^2_3]


## Was genau wird beschrieben?

- DCAT-AP beschreibt keine Fachdaten selbst, sondern Metadaten über Datensätze und deren Distributionen (z.B. Download-Links, Dienste, Formate, Lizenzen, Herausgeber, Themen). [^2_1][^2_3][^2_5]
- Kernobjekte sind u.a. „Catalog“, „Dataset“ und „Distribution“ mit Pflicht- und empfohlenen Feldern wie Titel, Beschreibung, Schlagworte, Lizenz, zeitliche und räumliche Abdeckung, Herausgeber usw. [^2_2][^2_3][^2_4]


## Zweck und Nutzen

- Haupteinsatzszenario ist die portalübergreifende Suche: Beschreibungen von Datensätzen werden zwischen Portalen ausgetauscht, sodass z.B. das Europäische Datenportal Datensätze aus vielen nationalen und kommunalen Portalen einheitlich indizieren kann. [^2_1][^2_2][^2_3]
- Durch die Harmonisierung mit DCAT-AP können Hunderttausende bis Millionen Datensätze trotz dezentraler Bereitstellung und verschiedener Sprachen/Länder über eine einzige Suche gefunden werden. [^2_1][^2_2][^2_3]


## Nationale Profile (z.B. DCAT-AP.de)

- DCAT-AP wird oft durch nationale Profile wie DCAT-AP.de (Deutschland) oder DCAT-AP AT (Österreich) konkretisiert, die zusätzliche Anforderungen oder Spezialisierungen für das jeweilige Land definieren. [^2_1][^2_4][^2_5]
- Diese Profile bleiben kompatibel mit DCAT-AP, sodass der europaweite Austausch von Metadatensätzen weiterhin funktioniert. [^2_3][^2_4]


# Beispiel speziell für OParl API

Hier ein minimales DCAT-AP-Beispiel in Turtle für einen Datensatz, der eine OParl-API einer Kommune beschreibt (also der Eintrag im Open‑Data‑Portal, nicht die einzelnen Ratsdokumente).

## Annahmen

- Fiktive Stadt: Beispielstadt
- OParl-System-URL: `https://oparl.beispielstadt.de/system`
- Open‑Data‑Portal: `https://open-data.beispielstadt.de`

Strukturell orientiert sich das an typischen DCAT-AP-Beispielen sowie Beschreibungen kommunaler OParl-Schnittstellen. [^3_1][^3_2][^3_3]

## DCAT-AP Turtle-Beispiel für eine OParl-API

```turtle
@prefix dcat:  <http://www.w3.org/ns/dcat#> .
@prefix dct:   <http://purl.org/dc/terms/> .
@prefix foaf:  <http://xmlns.com/foaf/0.1/> .
@prefix vcard: <http://www.w3.org/2006/vcard/ns#> .
@prefix xsd:   <http://www.w3.org/2001/XMLSchema#> .

# Katalog des kommunalen Open-Data-Portals
<https://open-data.beispielstadt.de/catalog>
    a dcat:Catalog ;
    dct:title "Open-Data-Katalog der Beispielstadt"@de ;
    dct:description "Katalog offener Verwaltungsdaten der Beispielstadt, inklusive Ratsinformationssystem (OParl-API)."@de ;
    dct:publisher <https://open-data.beispielstadt.de/org/od-stelle> ;
    dcat:dataset <https://open-data.beispielstadt.de/dataset/oparl-api> .

# Herausgeber (Open-Data-Stelle / Stadtverwaltung)
<https://open-data.beispielstadt.de/org/od-stelle>
    a foaf:Organization ;
    foaf:name "Stadt Beispielstadt, Open-Data-Koordination"@de .

# Datensatz-Beschreibung für die OParl-API
<https://open-data.beispielstadt.de/dataset/oparl-api>
    a dcat:Dataset ;
    dct:title "Ratsinformationssystem der Beispielstadt (OParl-API)"@de ;
    dct:description "Maschinenleserlicher Zugang zu allen öffentlichen Informationen des Ratsinformationssystems der Beispielstadt nach dem OParl-Standard."@de ;
    dct:publisher <https://open-data.beispielstadt.de/org/od-stelle> ;
    dct:issued "2020-01-15"^^xsd:date ;
    dct:modified "2026-05-31"^^xsd:date ;
    dct:language <http://publications.europa.eu/resource/authority/language/DEU> ;
    dct:spatial <http://www.geonames.org/1234567> ; # Beispiel-URI für die Kommune
    dct:accrualPeriodicity <http://publications.europa.eu/resource/authority/frequency/CONT> ; # kontinuierlich
    dct:license <https://creativecommons.org/licenses/by/4.0/> ;
    dcat:keyword "Ratsinformationssystem"@de ,
                 "OParl"@de ,
                 "Kommunalpolitik"@de ,
                 "Open Government"@de ;
    dcat:distribution <https://open-data.beispielstadt.de/dataset/oparl-api/distribution/json> .

# Distribution: eigentliche OParl-API (Basis-System-URL)
<https://open-data.beispielstadt.de/dataset/oparl-api/distribution/json>
    a dcat:Distribution ;
    dct:title "OParl-API der Beispielstadt (JSON/REST)"@de ;
    dct:description "REST-API nach OParl 1.1, JSON-Ausgabe für alle öffentlichen Ratsdokumente und Gremiendaten."@de ;
    dct:format <http://publications.europa.eu/resource/authority/file-type/JSON> ;
    dcat:accessURL <https://oparl.beispielstadt.de/system> ;
    dct:license <https://creativecommons.org/licenses/by/4.0/> .
```

Dieses Muster folgt dem üblichen DCAT-AP-Aufbau mit `Catalog → Dataset → Distribution` und beschreibt die OParl-API als eine Distribution (Zugangsform) zu den Ratsdaten. [^3_2][^3_3][^3_4] In der Praxis kannst du für Deutschland auf DCAT‑AP.de aufsetzen, das dieselbe Grundstruktur nutzt, aber einige Properties präzisiert. [^3_3][^3_4]


# für Datensätze

Für DCAT-AP beschreibt man auch die eigentlichen Datensätze (z.B. „alle Sitzungsdokumente als ZIP“) als `dcat:Distribution` desselben `dcat:Dataset`. [^4_1][^4_2][^4_3] Hier ein erweitertes Beispiel, das zum vorherigen OParl‑Dataset passt.

## Kontext

- Kommunales Open‑Data‑Dataset: „Ratsinformationssystem der Beispielstadt (OParl‑API)“.
- Technisch gibt es mehrere Zugänge: die Live‑API und z.B. einen periodischen ZIP‑Export von Dokumenten.
- Städte wie Bonn, Köln, Düsseldorf beschreiben ihre OParl‑Schnittstellen in DCAT‑kompatiblen Metadaten; dort werden genau solche Distributionsinformationen gepflegt. [^4_3][^4_4][^4_5][^4_6]


## DCAT-AP Turtle: zusätzliche Distribution für Datensätze

Aufbauend auf dem vorherigen Snippet (Dataset‑Ressource unverändert):

```turtle
@prefix dcat:  <http://www.w3.org/ns/dcat#> .
@prefix dct:   <http://purl.org/dc/terms/> .
@prefix foaf:  <http://xmlns.com/foaf/0.1/> .
@prefix vcard: <http://www.w3.org/2006/vcard/ns#> .
@prefix xsd:   <http://www.w3.org/2001/XMLSchema#> .

# Datensatz-Beschreibung für die OParl-API (wie zuvor)
<https://open-data.beispielstadt.de/dataset/oparl-api>
    a dcat:Dataset ;
    dct:title "Ratsinformationssystem der Beispielstadt (OParl-API)"@de ;
    dct:description "Maschinenleserlicher Zugang zu allen öffentlichen Informationen des Ratsinformationssystems der Beispielstadt nach dem OParl-Standard."@de ;
    dct:publisher <https://open-data.beispielstadt.de/org/od-stelle> ;
    dct:issued "2020-01-15"^^xsd:date ;
    dct:modified "2026-05-31"^^xsd:date ;
    dct:language <http://publications.europa.eu/resource/authority/language/DEU> ;
    dct:spatial <http://www.geonames.org/1234567> ;
    dct:accrualPeriodicity <http://publications.europa.eu/resource/authority/frequency/CONT> ;
    dct:license <https://creativecommons.org/licenses/by/4.0/> ;
    dcat:keyword "Ratsinformationssystem"@de ,
                 "OParl"@de ,
                 "Kommunalpolitik"@de ,
                 "Open Government"@de ;
    # mehrere Distributionen: Live-API + periodischer ZIP-Export
    dcat:distribution
        <https://open-data.beispielstadt.de/dataset/oparl-api/distribution/json> ,
        <https://open-data.beispielstadt.de/dataset/oparl-api/distribution/zip-sitzungen> .

# Distribution 1: Live-OParl-API (wie zuvor)
<https://open-data.beispielstadt.de/dataset/oparl-api/distribution/json>
    a dcat:Distribution ;
    dct:title "OParl-API der Beispielstadt (JSON/REST)"@de ;
    dct:description "REST-API nach OParl 1.1, JSON-Ausgabe für alle öffentlichen Ratsdokumente und Gremiendaten."@de ;
    dct:format <http://publications.europa.eu/resource/authority/file-type/JSON> ;
    dcat:accessURL <https://oparl.beispielstadt.de/system> ;
    dct:license <https://creativecommons.org/licenses/by/4.0/> .

```

- `dcat:distribution` verweist nun auf zwei unterschiedliche Angebote („Live‑API“ und „ZIP‑Export“), die jeweils eigene Metadaten (Format, Aktualisierungsintervall, Zugriffs‑URL) haben. [^4_1][^4_2][^4_7]
- Dieses Muster entspricht der Praxis in Portalen wie Bonn/Open.NRW, wo OParl‑Schnittstellen als Dataset geführt und die Zugänge (API, Dateien) als Distributionen modelliert werden. [^4_3][^4_4][^4_5][^4_6]

Brauchst du als Nächstes ein Beispiel, wie man in DCAT-AP.de zusätzlich Kontaktinformationen (`dcat:contactPoint`) und einen spezifischen Lizenzhinweis (Namensnennungspflicht wie bei Köln) ausformuliert?

# abbildung von Inhalten. vorlagen, anträge, protokolle mit Inhalts Kategorie

Ja — für die **Abbildung von Inhalten** wie Vorlagen, Anträgen und Protokollen brauchst du meist zwei Ebenen: den fachlichen Objekttyp und eine inhaltliche Kategorie. [^5_1][^5_2][^5_3] In OParl ist das Grundobjekt für solche Inhalte vor allem `Paper` und das eigentliche Dateidokument `File`; fachliche Feinkategorien wie „Antrag“ oder „Niederschrift“ musst du in der Regel zusätzlich modellieren. [^5_1][^5_2][^5_4]

## OParl-Grundmodell

- OParl bildet Ratsinhalte über Objekte wie `Meeting`, `AgendaItem`, `Paper` und `File` ab; kommunale RIS enthalten typischerweise Vorlagen, Tagesordnungen und Niederschriften. [^5_1][^5_2][^5_3]
- In der Praxis zeigen kommunale OParl-Instanzen genau diese Inhalte: Münster nennt ausdrücklich Vorlagen, Tagesordnungen und Niederschriften; OParl selbst versteht sich als maschinenlesbarer Zugang zu öffentlichen Ratsinhalten. [^5_3][^5_5]
- ALLRIS zeigt auf Oberflächenebene ähnliche fachliche Typen wie „Vorlage“, Dokumente und Sammeldokumente, was gut zur OParl-Abbildung über `Paper` plus `File` passt. [^5_6][^5_7][^5_8]


## Fachtyp und Kategorie

Sinnvoll ist eine Trennung wie folgt:

- **Fachtyp**: Was ist das Objekt institutionell? z.B. Vorlage, Antrag, Niederschrift/Protokoll, Beschlussvorlage, Anfrage. [^5_3][^5_6][^5_7]
- **Inhaltskategorie**: Worum geht es thematisch? z.B. Haushalt, Mobilität, Schule, Bauleitplanung, Personal, Umwelt. [^5_9]
- **Dokumentart/Dateirolle**: Welche Datei ist es genau? z.B. Hauptdokument, Anlage, Sammeldokument, öffentliche Fassung, nichtöffentliche Fassung. [^5_6][^5_7][^5_8]

Damit vermeidest du, dass „Antrag“ und „Haushalt“ in derselben Achse landen.

## RDF-Modellierung

Für RDF/OWL oder auch JSON-LD würde ich das so schneiden:

- `oparl:Paper` für das parlamentarische Stück als Kernressource, `dct:title`, `dct:description`, `dct:created`, `dct:identifier` für Metadaten. [^5_1][^5_2]
- `rdf:type` oder besser `dct:type` für den **fachlichen Dokumenttyp**; die Werte kommen aus einem kontrollierten SKOS-Vokabular wie `risdoc:Antrag`, `risdoc:Vorlage`, `risdoc:Niederschrift`. [^5_10][^5_11]
- `dcat:theme` oder `dct:subject` für die **Inhaltskategorie**; Werte ebenfalls aus einem SKOS-Konzeptschema wie `risthema:Haushalt`, `risthema:Verkehr`, `risthema:Bauen`. [^5_12][^5_10][^5_9]
- Zugehörige Dateien als `oparl:File` bzw. Distribution/Dateiressourcen mit eigener Rollenklassifikation, etwa `risfile:Hauptdokument`, `risfile:Anlage`, `risfile:Sammeldokument`. [^5_1][^5_2][^5_7]


## Beispielstruktur

Ein pragmatisches Muster wäre:

```turtle
@prefix ex: <https://ris-ki.de/ris/> .
@prefix oparl: <https://oparl.org/ontology/> .   # fiktiver Namespace für eigenes Mapping
@prefix dct: <http://purl.org/dc/terms/> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .

ex:paper-123
    a oparl:Paper ;
    dct:title "Antrag zur Einrichtung von Fahrradstraßen im Bezirk Mitte"@de ;
    dct:type ex:docType-antrag ;
    dct:subject ex:topic-mobilitaet ;
    ex:fileRole ex:fileRole-hauptdokument ;
    ex:hasFile ex:file-123-pdf .

ex:docType-antrag
    a skos:Concept ;
    skos:prefLabel "Antrag"@de ;
    skos:inScheme ex:document-types .

ex:topic-mobilitaet
    a skos:Concept ;
    skos:prefLabel "Mobilität"@de ;
    skos:inScheme ex:content-topics .

ex:fileRole-hauptdokument
    a skos:Concept ;
    skos:prefLabel "Hauptdokument"@de ;
    skos:inScheme ex:file-roles .
```

Das trennt sauber zwischen dem Objekt selbst, seinem formalen Typ und seiner thematischen Einordnung. Die EU-Leitlinien zu RDF-Vokabularen empfehlen genau diese Wiederverwendung plus kontrollierte Code-Listen. [^5_10][^5_13]

## Empfohlene Kategorien

Für kommunale Ratsdaten funktioniert meist ein kleines kontrolliertes Schema:


| Ebene | Beispiele |
| :-- | :-- |
| Fachtyp | Vorlage, Antrag, Änderungsantrag, Anfrage, Mitteilung, Niederschrift, Beschluss |
| Inhaltskategorie | Haushalt, Finanzen, Mobilität, Bildung, Klima, Soziales, Bauen, Digitalisierung |
| Dateirolle | Hauptdokument, Anlage, Sammeldokument, Beschlussauszug, öffentliche Fassung |

Diese Dreiteilung passt gut zu den realen Inhalten in RIS/OParl und zu offenen Datenportalen, die oft ebenfalls thematische Kategorien führen. [^5_3][^5_9][^5_7]

Wenn du willst, skizziere ich dir als Nächstes ein kleines SKOS-Vokabular in Turtle mit genau diesen Klassen: `Vorlage`, `Antrag`, `Protokoll/Niederschrift` plus Inhaltskategorien für deutsche Kommunen.



# Implementation Proposal

Wissensgraph-Implementierung für Ratsinformationssystem
Architektur- und Vokabular-Proposal
Basierend auf den angehängten Ideen und unserer PostgreSQL-Grafik-Diskussion folgt ein detaillierter Plan zur Erweiterung Ihres bestehenden Systems um semantische Schichten.

1. Gesamtarchitektur
1.1 Schichtenmodell
┌─────────────────────────────────────────────────────────────┐
│                    Anfragelage (LLM)                        │
│         Natürlichsprachliche Eingabe → Query Plan           │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                  Übersetzungsschicht                        │
│         Query Plan → Parameterisierte SQL-CTE               │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│              Wissensgraph-Schicht (PostgreSQL)              │
│    Triples + Ontologie + Vokabulare + Relationstabellen     │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                Basis-Datenschicht (Bestehend)               │
│      Body, Paper, File, Meeting, AgendaItem, Person         │
└─────────────────────────────────────────────────────────────┘

1.2 Design-Prinzipien
PrinzipBegründungWiederverwendung vor NeuentwicklungEU- und DE-Standards priorisieren (DCAT-AP, GND, FOAF)Trennung von Struktur und InhaltFachtyp ≠ Inhaltskategorie ≠ DateirolleErweiterbarkeitSKOS-Konzeptpläne für kontrollierte VokabulareLesefokusKeine Schreibrechte für Endnutzer, Performance-OptimierungLLM-SicherheitQuery-Plan statt direkter SQL-Erzeugung

2. Datenbank-Schema-Erweiterung
2.1 Kern-Tripel-Tabelle (für flexible Semantik)
Diese Tabelle ergänzt Ihre bestehenden Tabellen, ohne sie zu ersetzen.
-- Semantische Tripel für zusätzliche Beziehungen
CREATE TABLE semantic_triples (
    id BIGSERIAL PRIMARY KEY,
    subject_entity_type VARCHAR(100) NOT NULL,  -- 'paper', 'meeting', 'body'
    subject_entity_id BIGINT NOT NULL,          -- FK zu bestehender Tabelle
    predicate_uri VARCHAR(500) NOT NULL,        -- URI des Prädikats
    object_value TEXT,                          -- Literal-Wert (falls vorhanden)
    object_entity_type VARCHAR(100),            -- 'paper', 'person', 'topic'
    object_entity_id BIGINT,                    -- Referenz zu anderer Entität
    confidence_score FLOAT DEFAULT 1.0,         -- Für LLM-generierte Fakten
    provenance_source VARCHAR(200),             -- Woher stammt diese Information?
    created_at TIMESTAMP DEFAULT NOW(),
    
    CONSTRAINT chk_object_either_value_or_ref CHECK (
        (object_value IS NOT NULL AND object_entity_id IS NULL) OR
        (object_value IS NULL AND object_entity_id IS NOT NULL)
    )
);

-- Kritische Indizes für Graph-Traversierung
CREATE INDEX idx_triples_subject ON semantic_triples(subject_entity_type, subject_entity_id);
CREATE INDEX idx_triples_predicate ON semantic_triples(predicate_uri);
CREATE INDEX idx_triples_object_ref ON semantic_triples(object_entity_type, object_entity_id);
CREATE INDEX idx_triples_composite ON semantic_triples(subject_entity_type, subject_entity_id, predicate_uri);
2.2 Vokabular-Tabellen (SKOS-basiert)
-- Konzept-Schemata (entspricht SKOS ConceptScheme)
CREATE TABLE concept_schemes (
    uri VARCHAR(500) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    language CHAR(2) DEFAULT 'de',
    version VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Konzepte (entspricht SKOS Concept)
CREATE TABLE concepts (
    id BIGSERIAL PRIMARY KEY,
    scheme_uri VARCHAR(500) REFERENCES concept_schemes(uri),
    uri VARCHAR(500) UNIQUE,
    pref_label VARCHAR(255) NOT NULL,
    alt_labels JSONB, -- Array von Alternativbegriffen
    definition TEXT,
    broader_concept_id BIGINT REFERENCES concepts(id),
    narrower_concepts JSONB, -- Array von child-URIs
    related_concepts JSONB,  -- Assoziative Beziehungen
    in_scheme BOOLEAN DEFAULT TRUE,
    deprecated BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Verknüpfung von Entitäten mit Konzepten
CREATE TABLE entity_concepts (
    entity_type VARCHAR(100) NOT NULL,
    entity_id BIGINT NOT NULL,
    concept_uri VARCHAR(500) NOT NULL,
    relation_type VARCHAR(50) DEFAULT 'skos:subject', -- 'skos:subject', 'dct:type', etc.
    confidence_score FLOAT DEFAULT 1.0,
    PRIMARY KEY (entity_type, entity_id, concept_uri, relation_type)
);

CREATE INDEX idx_entity_concepts ON entity_concepts(entity_type, entity_id);
CREATE INDEX idx_concept_entities ON entity_concepts(concept_uri);
2.3 Ontologie-Referenztabelle
-- Registrierte Ontologien und Vokabulare
CREATE TABLE registered_ontologies (
    uri VARCHAR(500) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    namespace VARCHAR(200) NOT NULL,
    version VARCHAR(20),
    provider VARCHAR(200), -- z.B. "EU Publications Office", "DNB"
    status VARCHAR(20) DEFAULT 'active', -- 'active', 'deprecated', 'draft'
    documentation_url TEXT,
    last_verified DATE,
    notes TEXT
);

-- Mapping zwischen lokalen und externen URIs
CREATE TABLE uri_mappings (
    local_uri VARCHAR(500) PRIMARY KEY,
    external_uri VARCHAR(500) NOT NULL,
    mapping_type VARCHAR(50) DEFAULT 'owl:equivalentClass', -- 'owl:equivalentClass', 'skos:closeMatch', etc.
    confidence FLOAT DEFAULT 1.0,
    verified_by VARCHAR(100),
    verified_at TIMESTAMP
);

3. Vokabular-Strategie
3.1 Externe Referenzontologien (Priorisiert)
OntologieURI-NamespaceVerwendungszweckStatusDCAT-APhttp://www.w3.org/ns/dcat#Katalog-Metadaten⭐ Priorität 1Dublin Core Termshttp://purl.org/dc/terms/Allgemeine Metadaten⭐ Priorität 1FOAFhttp://xmlns.com/foaf/0.1/Personen⭐ Priorität 1W3C ORGhttp://www.w3.org/ns/org#Organisationen/Körperschaften⭐ Priorität 1GND (DNB)https://d-nb.info/standards/elementset/gnd#Normierte Entitäten⭐ Priorität 2EU Vocabularieshttp://publications.europa.eu/resource/authority/Kontrollierte Listen⭐ Priorität 2Schema.orghttp://schema.org/Allgemeine Begriffe⭐ Priorität 2OWL Timehttp://www.w3.org/2006/time#Zeitangaben⭐ Priorität 3SKOShttp://www.w3.org/2004/02/skos/core#Vokabular-Struktur⭐ Priorität 1
3.2 Lokale Domänenontologie (Erweiterbar)
Namespace: https://ris-ki.de/ris/ontology#

Klassen:
├── ris:DocumentType (Fachtyp)
│   ├── ris:Vorlage
│   ├── ris:Antrag
│   ├── ris:Änderungsantrag
│   ├── ris:Niederschrift
│   ├── ris:Beschluss
│   └── ris:Anfrage
│
├── ris:ContentCategory (Inhaltskategorie)
│   ├── ris:Haushalt
│   ├── ris:Finanzen
│   ├── ris:Mobilität
│   ├── ris:Bildung
│   ├── ris:Klima
│   ├── ris:Soziales
│   ├── ris:Bauen
│   └── ris:Digitalisierung
│
└── ris:FileRole (Dateirolle)
    ├── ris:Hauptdokument
    ├── ris:Anlage
    ├── ris:Sammeldokument
    ├── ris:Beschlussauszug
    └── ris:ÖffentlicheFassung

3.3 Initialer SKOS-Aufbau (Konzeptpläne)
-- Konzept-Schemata initialisieren
INSERT INTO concept_schemes (uri, title, description, language) VALUES
('https://ris-ki.de/ris/doc-types', 'RIS Dokumententypen', 'Fachliche Typen von Ratsdokumenten', 'de'),
('https://ris-ki.de/ris/content-categories', 'RIS Inhaltskategorien', 'Thematische Einordnung von Ratsinhalten', 'de'),
('https://ris-ki.de/ris/file-roles', 'RIS Dateirollen', 'Rollen von Dateien innerhalb von Dokumenten', 'de'),
('https://ris-ki.de/ris/procedure-types', 'RIS Verfahrenstypen', 'Art des parlamentarischen Verfahrens', 'de'),
('https://ris-ki.de/ris/decision-status', 'RIS Beschlussstatus', 'Status von Entscheidungen/Vorlagen', 'de');

4. Integration mit Bestehenden Tabellen
4.1 Mapping-Tabelle (OParl-Entitäten → Semantische Schicht)
-- Mapping zwischen OParl-Objekten und semantischen URIs
CREATE TABLE oparl_semantic_mapping (
    oparl_object_type VARCHAR(100) NOT NULL, -- 'Body', 'Paper', 'Meeting', etc.
    oparl_property VARCHAR(200) NOT NULL,    -- z.B. 'type', 'category'
    target_predicate_uri VARCHAR(500) NOT NULL, -- z.B. 'dct:type', 'dct:subject'
    target_value_type VARCHAR(50) NOT NULL,  -- 'concept', 'literal', 'external_uri'
    transformation_rule TEXT,                 -- Optional: JSON-Rule für Transformation
    priority INT DEFAULT 1,
    PRIMARY KEY (oparl_object_type, oparl_property)
);

-- Beispiel-Einträge
-- Body → org:Organization
-- Paper → dct:type (mit ris:DocumentType Konzept)
-- Paper → dct:subject (mit ris:ContentCategory Konzept)
-- Meeting → time:Instant (mit OWL Time)
4.2 Materialisierte Ansichten für Häufige Abfragen
-- Dokument mit allen semantischen Tags
CREATE MATERIALIZED VIEW mv_paper_enriched AS
SELECT 
    p.id as paper_id,
    p.title,
    p.created_at,
    ec.concept_uri as topic_uri,
    c.pref_label as topic_label,
    ec.relation_type,
    st.predicate_uri as additional_predicate,
    st.object_value as predicate_value
FROM paper p
LEFT JOIN entity_concepts ec ON ec.entity_type = 'paper' AND ec.entity_id = p.id
LEFT JOIN concepts c ON c.uri = ec.concept_uri
LEFT JOIN semantic_triples st ON st.subject_entity_type = 'paper' AND st.subject_entity_id = p.id;

-- Personen mit Rollen und Zugehörigkeiten
CREATE MATERIALIZED VIEW mv_person_roles AS
SELECT 
    per.id as person_id,
    per.name,
    ec.concept_uri as role_uri,
    c.pref_label as role_label,
    ec2.concept_uri as organization_uri,
    c2.pref_label as organization_label
FROM person per
LEFT JOIN entity_concepts ec ON ec.entity_type = 'person' AND ec.entity_id = per.id AND ec.relation_type = 'ris:role'
LEFT JOIN concepts c ON c.uri = ec.concept_uri
LEFT JOIN entity_concepts ec2 ON ec2.entity_type = 'person' AND ec2.entity_id = per.id AND ec2.relation_type = 'org:memberOf'
LEFT JOIN concepts c2 ON c2.uri = ec2.concept_uri;

-- Regelmäßige Aktualisierung
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_paper_enriched;
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_person_roles;

5. Implementierungsphasen
Phase 1: Fundament (Woche 1-4)
AufgabeBeschreibungErfolgskriteriumSchema-ErstellungTriples, Concepts, ConceptSchemes TabellenAlle Tabellen erstellt, Indizes optimiertOntologie-RegistrierungExterne Ontologien in registered_ontologies eintragenMindestens 5 externe Ontologien registriertBasis-VokabulareSKOS-Konzeptpläne für DocTypes, Categories, RolesMindestens 20 Konzepte pro SchemeMapping-TabelleOParl-Properties zu semantischen Prädikaten mappenAlle OParl-Objekttypen gemappt
Phase 2: Datenmigration (Woche 5-8)
AufgabeBeschreibungErfolgskriteriumEntity-Concept-LinkingBestehende Daten mit Konzepten verknüpfen80% der Papers haben ≥1 TopicTriple-ErstellungAbhängigkeiten in semantic_triples übertragenAlle File-AgendaItem-Beziehungen migriertGND-IntegrationPersonen/Organisationen mit GND-IDs anreichern50% der Personen haben GND-URIQualitätsprüfungPlausibilitätschecks für Konsistenz≤5% inkonsistente Triples
Phase 3: Query-Layer (Woche 9-12)
AufgabeBeschreibungErfolgskriteriumQuery-Plan-ParserJSON-Pläne zu SQL übersetzenAlle 5 Grundmuster unterstütztSicherheitslimitsDepth, Limit, Timeout implementierenKeine Query >5s, Depth ≤3CTE-GeneratorenRekursive Traversierung vorbereiten3 Traversal-Patterns getestetLLM-Prompt-EngineeringQuery-Plan-Schema für LLM definierenLLM generiert validen JSON-Plan
Phase 4: Erweiterung (Woche 13+)
AufgabeBeschreibungErfolgskriteriumDCAT-AP ExportRDF/Turtle für Open DataValidierter DCAT-AP.de OutputVolltext-Suchepgvector für semantische SucheTop-10 Ergebnisse <2sInferenz-RegelnSubclass-Relationships auflösenowl:subClassOf korrekt gehandhabtMonitoringQuery-Performance, NutzungDashboard mit Metriken

6. Vokabular-Details (Initial)
6.1 Dokumententypen (SKOS)
Scheme: https://ris-ki.de/ris/doc-types

Konzepte:
├── ris:Vorlage (prefLabel: "Vorlage")
│   ├── ris:Beschlussvorlage
│   └── ris:Informationsvorlage
├── ris:Antrag (prefLabel: "Antrag")
│   ├── ris:Änderungsantrag
│   └── ris:Große Anfrage
├── ris:Niederschrift (prefLabel: "Niederschrift")
│   ├── ris:Protokoll
│   └── ris:Auszug
├── ris:Beschluss (prefLabel: "Beschluss")
└── ris:Mitteilung (prefLabel: "Mitteilung")

6.2 Inhaltskategorien (SKOS)
Scheme: https://ris-ki.de/ris/content-categories

Konzepte (hierarchisch):
├── ris:Verwaltung
│   ├── ris:Personal
│   └── ris:Organisation
├── ris:Finanzen
│   ├── ris:Haushalt
│   └── ris:Steuern
├── ris:Infrastruktur
│   ├── ris:Mobilität
│   ├── ris:Bauen
│   └── ris:Energie
├── ris:Gesellschaft
│   ├── ris:Bildung
│   ├── ris:Soziales
│   └── ris:Gesundheit
└── ris:Umwelt
    ├── ris:Klima
    └── ris:Naturschutz

6.3 Dateirollen (SKOS)
Scheme: https://ris-ki.de/ris/file-roles

Konzepte:
├── ris:Hauptdokument
├── ris:Anlage
├── ris:Sammeldokument
├── ris:Beschlussauszug
├── ris:ÖffentlicheFassung
└── ris:NichtöffentlicheFassung


7. Externe Vokabular-Integration
7.1 EU Vocabularies (Priorisierte Code-Listen)
VokabularURIVerwendungLanguagehttp://publications.europa.eu/resource/authority/language/dct:languageFrequencyhttp://publications.europa.eu/resource/authority/frequency/dct:accrualPeriodicityFile Typehttp://publications.europa.eu/resource/authority/file-type/dct:formatCountryhttp://publications.europa.eu/resource/authority/country/dct:spatialCorporate Bodyhttp://publications.europa.eu/resource/authority/corporate-body/org:Organization
7.2 GND-Integration (Deutsche Nationalbibliothek)
-- GND-IDs für Personen und Körperschaften speichern
ALTER TABLE person ADD COLUMN gnd_id VARCHAR(20);
ALTER TABLE body ADD COLUMN gnd_id VARCHAR(20);

-- GND-Ontologie-URI für Mapping
INSERT INTO registered_ontologies (uri, title, namespace, provider) VALUES
('https://d-nb.info/standards/elementset/gnd#', 'GND Ontology', 'https://d-nb.info/standards/elementset/gnd#', 'Deutsche Nationalbibliothek');

-- Mapping-Tabelle für GND-Relationen
INSERT INTO uri_mappings (local_uri, external_uri, mapping_type) VALUES
('ris:person', 'https://d-nb.info/standards/elementset/gnd#Person', 'owl:equivalentClass'),
('ris:organization', 'https://d-nb.info/standards/elementset/gnd#CorporationOrBody', 'owl:equivalentClass');

8. LLM-Query-Plan-Schema
8.1 JSON-Struktur für sichere Query-Generierung
{
  "query_id": "uuid-v4",
  "intent": "graph_traversal",
  "constraints": {
    "max_depth": 3,
    "max_results": 100,
    "timeout_seconds": 5
  },
  "start_nodes": [
    {
      "entity_type": "paper",
      "filters": [
        {"property": "title", "operator": "contains", "value": "Fahrrad"},
        {"property": "concept_uri", "operator": "equals", "value": "https://ris-ki.de/ris/content-categories#Mobilität"}
      ]
    }
  ],
  "traversal_steps": [
    {
      "step": 1,
      "predicate_uri": "http://www.w3.org/ns/dcat#theme",
      "direction": "outbound",
      "target_entity_type": "concept"
    },
    {
      "step": 2,
      "predicate_uri": "http://www.w3.org/2004/02/skos/core#broader",
      "direction": "outbound",
      "target_entity_type": "concept"
    }
  ],
  "return_fields": [
    {"source": "paper", "field": "title"},
    {"source": "concept", "field": "pref_label"}
  ],
  "aggregations": [
    {"function": "count", "group_by": "concept_uri"}
  ]
}
8.2 Unterstützte Query-Muster
MusterBeschreibungUse CaseSingle-HopDirekte Tripel-Abfrage"Welche Themen hat diese Vorlage?"Multi-HopRekursive Traversierung"Wer ist mit diesem Antrag verbunden?"Pattern-MatchMehrere Bedingungen"Anträge zu Mobilität seit 2024"AggregationGruppierung und Zählung"Wie viele Vorlagen pro Kategorie?"SimilarityVektor-basierte Suche"Ähnliche Anträge finden"

9. Sicherheit und Performance
9.1 Read-Only Schutzmaßnahmen
MaßnahmeImplementierungZweckStatement TimeoutSET statement_timeout = '5s'Verhindert lange QueriesDepth LimitHard-Coded Max-Depth im CompilerVerhindert zyklische TraversierungResult LimitMax 1000 Zeilen pro QueryVerhindert DatenexfiltrationConnection PoolPgBouncer mit LimitVerhindert Connection-FloodingQuery LoggingAlle generierten SQLs protokollierenAudit und Debugging
9.2 Performance-Optimierung
TechnikBeschreibungErwarteter GewinnMaterialized ViewsHäufige Traversierungen vorberechnen10-100x schnellerCovering IndexesAlle benötigten Spalten im Index5-10x schnellerPartitionierungTriples nach entity_type partitionierenBessere Cache-NutzungQuery CachingRedis für häufige Query-Pläne<100ms AntwortzeitParallel Executionmax_parallel_workers_per_gather erhöhen2-4x bei Aggregationen

10. Nächste Schritte und offene Fragen
10.1 Unmittelbare Entscheidungen
EntscheidungOptionenEmpfehlungTriples vs. Property GraphReine Tripel-Tabelle vs. Node/Edge-TabellenHybrid (Triples für Flexibilität)GND-IntegrationVollständig vs. Opt-inOpt-in (nur wenn GND-ID verfügbar)DCAT-AP ExportEchtzeit vs. BatchBatch (nächtlich refresh)LLM-ProviderEigenes Modell vs. ExternEigenes (Datenschutz)
10.2 Offene Untersuchungen

OParl-OParl-Mapping: Gibt es bereits Community-Mappings von OParl zu RDF?
DCAT-AP.de Profil: Welche deutschen Spezifikationen müssen berücksichtigt werden?
GND-Abgleich: Wie automatisiert können GND-IDs für lokale Personen gefunden werden?
Performance-Benchmark: Wie skalieren rekursive CTEs bei 1M+ Triples?
LLM-Qualität: Wie genau generieren Modelle korrekte Query-Pläne?

10.3 Empfohlene Sofortmaßnahmen
Woche 1:
├── [ ] Schema erstellen (Triples, Concepts, Mappings)
├── [ ] Externe Ontologien registrieren (DCAT, FOAF, ORG, GND)
└── [ ] Basis-SKOS-Vokabulare importieren (20+ Konzepte)

Woche 2:
├── [ ] Materialisierte Views für häufige Muster erstellen
├── [ ] Index-Strategie finalisieren
└── [ ] Query-Plan-Schema dokumentieren

Woche 3:
├── [ ] LLM-Prompt für Query-Plan-Generierung entwickeln
├── [ ] Sicherheitslimits implementieren
└── [ ] Test-Datensatz mit 100+ Entitäten aufsetzen


11. Zusammenfassung
Dieses Proposal bietet:

PostgreSQL-native Graph-Implementierung ohne externe Triple-Store-Abhängigkeit
Semantische Schicht über bestehenden OParl-Tabellen hinweg
Wiederverwendung externer Ontologien (DCAT-AP, GND, FOAF, EU Vocabularies)
SKOS-basierte Vokabulare für Dokumententypen, Themen und Dateirollen
LLM-sichere Query-Generierung via JSON Query Plans statt direktem SQL
Phasenweise Implementierung mit klaren Meilensteinen
Performance- und Sicherheitsmaßnahmen für Read-Only-Umgebung

Die Architektur ist erweiterbar (neue Vokabulare, neue Ontologien) und wartbar (klare Trennung von Basisdaten und Semantik).
Empfehlung: Mit Phase 1 beginnen, parallel externe Ontologien evaluieren und LLM-Query-Plan-Schema mit Stakeholdern abstimmen.


