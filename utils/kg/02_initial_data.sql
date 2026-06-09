-- =============================================================================
-- Riski Knowledge Graph - Initial Data Population
-- Populates initial vocabularies and mappings
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Initialize concept schemes
-- -----------------------------------------------------------------------------
INSERT INTO concept_schemes (uri, title, description, language) VALUES
('https://ris-ki.de/ris/doc-types', 'RIS Dokumententypen', 'Fachliche Typen von Ratsdokumenten', 'de'),
('https://ris-ki.de/ris/content-categories', 'RIS Inhaltskategorien', 'Thematische Einordnung von Ratsinhalten', 'de'),
('https://ris-ki.de/ris/file-roles', 'RIS Dateirollen', 'Rollen von Dateien innerhalb von Dokumenten', 'de'),
('https://ris-ki.de/ris/procedure-types', 'RIS Verfahrenstypen', 'Art des parlamentarischen Verfahrens', 'de'),
('https://ris-ki.de/ris/decision-status', 'RIS Beschlussstatus', 'Status von Entscheidungen/Vorlagen', 'de');

-- -----------------------------------------------------------------------------
-- 2. Initial document types (SKOS)
-- -----------------------------------------------------------------------------
INSERT INTO concepts (scheme_uri, uri, pref_label, definition) VALUES
('https://ris-ki.de/ris/doc-types', 'https://ris-ki.de/ris/doc-types#Vorlage', 'Vorlage', 'Vorlage im parlamentarischen Verfahren'),
('https://ris-ki.de/ris/doc-types', 'https://ris-ki.de/ris/doc-types#Antrag', 'Antrag', 'Antrag im parlamentarischen Verfahren'),
('https://ris-ki.de/ris/doc-types', 'https://ris-ki.de/ris/doc-types#Beschluss', 'Beschluss', 'Beschluss im parlamentarischen Verfahren'),
('https://ris-ki.de/ris/doc-types', 'https://ris-ki.de/ris/doc-types#Niederschrift', 'Niederschrift', 'Niederschrift im parlamentarischen Verfahren'),
('https://ris-ki.de/ris/doc-types', 'https://ris-ki.de/ris/doc-types#Protokoll', 'Protokoll', 'Protokoll im parlamentarischen Verfahren'),
('https://ris-ki.de/ris/doc-types', 'https://ris-ki.de/ris/doc-types#Anfrage', 'Anfrage', 'Anfrage im parlamentarischen Verfahren'),
('https://ris-ki.de/ris/doc-types', 'https://ris-ki.de/ris/doc-types#Meldung', 'Meldung', 'Meldung im parlamentarischen Verfahren'),
('https://ris-ki.de/ris/doc-types', 'https://ris-ki.de/ris/doc-types#Mitteilung', 'Mitteilung', 'Mitteilung im parlamentarischen Verfahren'),
('https://ris-ki.de/ris/doc-types', 'https://ris-ki.de/ris/doc-types#Bericht', 'Bericht', 'Bericht im parlamentarischen Verfahren'),
('https://ris-ki.de/ris/doc-types', 'https://ris-ki.de/ris/doc-types#Empfehlung', 'Empfehlung', 'Empfehlung im parlamentarischen Verfahren'),
('https://ris-ki.de/ris/doc-types', 'https://ris-ki.de/ris/doc-types#Plan', 'Plan', 'Plan im parlamentarischen Verfahren'),
('https://ris-ki.de/ris/doc-types', 'https://ris-ki.de/ris/doc-types#Gutachten', 'Gutachten', 'Gutachten im parlamentarischen Verfahren'),
('https://ris-ki.de/ris/doc-types', 'https://ris-ki.de/ris/doc-types#Studie', 'Studie', 'Studie im parlamentarischen Verfahren'),
('https://ris-ki.de/ris/doc-types', 'https://ris-ki.de/ris/doc-types#Analyse', 'Analyse', 'Analyse im parlamentarischen Verfahren'),
('https://ris-ki.de/ris/doc-types', 'https://ris-ki.de/ris/doc-types#Auswertung', 'Auswertung', 'Auswertung im parlamentarischen Verfahren'),
('https://ris-ki.de/ris/doc-types', 'https://ris-ki.de/ris/doc-types#Bewertung', 'Bewertung', 'Bewertung im parlamentarischen Verfahren'),
('https://ris-ki.de/ris/doc-types', 'https://ris-ki.de/ris/doc-types#Fazit', 'Fazit', 'Fazit im parlamentarischen Verfahren'),
('https://ris-ki.de/ris/doc-types', 'https://ris-ki.de/ris/doc-types#Resümee', 'Resümee', 'Resümee im parlamentarischen Verfahren'),
('https://ris-ki.de/ris/doc-types', 'https://ris-ki.de/ris/doc-types#Zusammenfassung', 'Zusammenfassung', 'Zusammenfassung im parlamentarischen Verfahren'),
('https://ris-ki.de/ris/doc-types', 'https://ris-ki.de/ris/doc-types#Überblick', 'Überblick', 'Überblick im parlamentarischen Verfahren'),
('https://ris-ki.de/ris/doc-types', 'https://ris-ki.de/ris/doc-types#Einführung', 'Einführung', 'Einführung im parlamentarischen Verfahren');

-- -----------------------------------------------------------------------------
-- 3. Initial content categories (SKOS)
-- -----------------------------------------------------------------------------
INSERT INTO concepts (scheme_uri, uri, pref_label, definition) VALUES
('https://ris-ki.de/ris/content-categories', 'https://ris-ki.de/ris/content-categories#Verwaltung', 'Verwaltung', 'Verwaltungsangelegenheiten'),
('https://ris-ki.de/ris/content-categories', 'https://ris-ki.de/ris/content-categories#Finanzen', 'Finanzen', 'Finanzangelegenheiten'),
('https://ris-ki.de/ris/content-categories', 'https://ris-ki.de/ris/content-categories#Infrastruktur', 'Infrastruktur', 'Infrastruktur'),
('https://ris-ki.de/ris/content-categories', 'https://ris-ki.de/ris/content-categories#Gesellschaft', 'Gesellschaft', 'Gesellschaft'),
('https://ris-ki.de/ris/content-categories', 'https://ris-ki.de/ris/content-categories#Umwelt', 'Umwelt', 'Umwelt'),
('https://ris-ki.de/ris/content-categories', 'https://ris-ki.de/ris/content-categories#Bildung', 'Bildung', 'Bildung'),
('https://ris-ki.de/ris/content-categories', 'https://ris-ki.de/ris/content-categories#Wirtschaft', 'Wirtschaft', 'Wirtschaft'),
('https://ris-ki.de/ris/content-categories', 'https://ris-ki.de/ris/content-categories#Gesundheit', 'Gesundheit', 'Gesundheit'),
('https://ris-ki.de/ris/content-categories', 'https://ris-ki.de/ris/content-categories#Soziales', 'Soziales', 'Soziales'),
('https://ris-ki.de/ris/content-categories', 'https://ris-ki.de/ris/content-categories#Bauen', 'Bauen', 'Bauen'),
('https://ris-ki.de/ris/content-categories', 'https://ris-ki.de/ris/content-categories#Mobilität', 'Mobilität', 'Mobilität'),
('https://ris-ki.de/ris/content-categories', 'https://ris-ki.de/ris/content-categories#Digitalisierung', 'Digitalisierung', 'Digitalisierung'),
('https://ris-ki.de/ris/content-categories', 'https://ris-ki.de/ris/content-categories#Energie', 'Energie', 'Energie'),
('https://ris-ki.de/ris/content-categories', 'https://ris-ki.de/ris/content-categories#Personal', 'Personal', 'Personal'),
('https://ris-ki.de/ris/content-categories', 'https://ris-ki.de/ris/content-categories#Organisation', 'Organisation', 'Organisation'),
('https://ris-ki.de/ris/content-categories', 'https://ris-ki.de/ris/content-categories#Klima', 'Klima', 'Klima'),
('https://ris-ki.de/ris/content-categories', 'https://ris-ki.de/ris/content-categories#Naturschutz', 'Naturschutz', 'Naturschutz'),
('https://ris-ki.de/ris/content-categories', 'https://ris-ki.de/ris/content-categories#Kultur', 'Kultur', 'Kultur');

-- -----------------------------------------------------------------------------
-- 4. Initial file roles (SKOS)
-- -----------------------------------------------------------------------------
INSERT INTO concepts (scheme_uri, uri, pref_label, definition) VALUES
('https://ris-ki.de/ris/file-roles', 'https://ris-ki.de/ris/file-roles#Hauptdokument', 'Hauptdokument', 'Das Hauptdokument'),
('https://ris-ki.de/ris/file-roles', 'https://ris-ki.de/ris/file-roles#Anlage', 'Anlage', 'Eine Anlage'),
('https://ris-ki.de/ris/file-roles', 'https://ris-ki.de/ris/file-roles#Sammeldokument', 'Sammeldokument', 'Ein Sammeldokument'),
('https://ris-ki.de/ris/file-roles', 'https://ris-ki.de/ris/file-roles#Beschlussauszug', 'Beschlussauszug', 'Ein Beschlussauszug'),
('https://ris-ki.de/ris/file-roles', 'https://ris-ki.de/ris/file-roles#ÖffentlicheFassung', 'Öffentliche Fassung', 'Eine öffentliche Fassung'),
('https://ris-ki.de/ris/file-roles', 'https://ris-ki.de/ris/file-roles#NichtöffentlicheFassung', 'Nichtöffentliche Fassung', 'Eine nichtöffentliche Fassung'),
('https://ris-ki.de/ris/file-roles', 'https://ris-ki.de/ris/file-roles#Entwurf', 'Entwurf', 'Ein Entwurf'),
('https://ris-ki.de/ris/file-roles', 'https://ris-ki.de/ris/file-roles#Vorschlag', 'Vorschlag', 'Ein Vorschlag'),
('https://ris-ki.de/ris/file-roles', 'https://ris-ki.de/ris/file-roles#Empfehlung', 'Empfehlung', 'Eine Empfehlung'),
('https://ris-ki.de/ris/file-roles', 'https://ris-ki.de/ris/file-roles#Beratung', 'Beratung', 'Eine Beratung'),
('https://ris-ki.de/ris/file-roles', 'https://ris-ki.de/ris/file-roles#Beschluss', 'Beschluss', 'Ein Beschluss'),
('https://ris-ki.de/ris/file-roles', 'https://ris-ki.de/ris/file-roles#Mitteilung', 'Mitteilung', 'Eine Mitteilung'),
('https://ris-ki.de/ris/file-roles', 'https://ris-ki.de/ris/file-roles#Meldung', 'Meldung', 'Eine Meldung'),
('https://ris-ki.de/ris/file-roles', 'https://ris-ki.de/ris/file-roles#Bericht', 'Bericht', 'Ein Bericht'),
('https://ris-ki.de/ris/file-roles', 'https://ris-ki.de/ris/file-roles#Studie', 'Studie', 'Eine Studie'),
('https://ris-ki.de/ris/file-roles', 'https://ris-ki.de/ris/file-roles#Analyse', 'Analyse', 'Eine Analyse'),
('https://ris-ki.de/ris/file-roles', 'https://ris-ki.de/ris/file-roles#Bewertung', 'Bewertung', 'Eine Bewertung'),
('https://ris-ki.de/ris/file-roles', 'https://ris-ki.de/ris/file-roles#Gutachten', 'Gutachten', 'Ein Gutachten'),
('https://ris-ki.de/ris/file-roles', 'https://ris-ki.de/ris/file-roles#Fazit', 'Fazit', 'Ein Fazit'),
('https://ris-ki.de/ris/file-roles', 'https://ris-ki.de/ris/file-roles#Resümee', 'Resümee', 'Ein Resümee'),
('https://ris-ki.de/ris/file-roles', 'https://ris-ki.de/ris/file-roles#Zusammenfassung', 'Zusammenfassung', 'Eine Zusammenfassung'),
('https://ris-ki.de/ris/file-roles', 'https://ris-ki.de/ris/file-roles#Überblick', 'Überblick', 'Ein Überblick'),
('https://ris-ki.de/ris/file-roles', 'https://ris-ki.de/ris/file-roles#Einführung', 'Einführung', 'Eine Einführung');

-- -----------------------------------------------------------------------------
-- 5. Register external ontologies (DCAT-AP, FOAF, GND, etc.)
-- -----------------------------------------------------------------------------
-- DCAT-AP
INSERT INTO registered_ontologies (uri, title, namespace, provider) VALUES
('http://www.w3.org/ns/dcat#', 'DCAT - Data Catalog Vocabulary', 'http://www.w3.org/ns/dcat#', 'W3C');
-- Dublin Core Terms
INSERT INTO registered_ontologies (uri, title, namespace, provider) VALUES
('http://purl.org/dc/terms/', 'Dublin Core Terms', 'http://purl.org/dc/terms/', 'Dublin Core Metadata Initiative');
-- FOAF
INSERT INTO registered_ontologies (uri, title, namespace, provider) VALUES
('http://xmlns.com/foaf/0.1/', 'FOAF - Friend of a Friend', 'http://xmlns.com/foaf/0.1/', 'FOAF project');
-- W3C ORG
INSERT INTO registered_ontologies (uri, title, namespace, provider) VALUES
('http://www.w3.org/ns/org#', 'W3C ORG', 'http://www.w3.org/ns/org#', 'W3C');
-- GND
INSERT INTO registered_ontologies (uri, title, namespace, provider) VALUES
('https://d-nb.info/standards/elementset/gnd#', 'GND Ontology', 'https://d-nb.info/standards/elementset/gnd#', 'Deutsche Nationalbibliothek');
-- EU Vocabularies
INSERT INTO registered_ontologies (uri, title, namespace, provider) VALUES
('http://publications.europa.eu/resource/authority/', 'EU Vocabularies', 'http://publications.europa.eu/resource/authority/', 'Publications Office of the European Union');
-- Schema.org
INSERT INTO registered_ontologies (uri, title, namespace, provider) VALUES
('http://schema.org/', 'Schema.org', 'http://schema.org/', 'Schema.org community');
-- OWL Time
INSERT INTO registered_ontologies (uri, title, namespace, provider) VALUES
('http://www.w3.org/2006/time#', 'OWL Time', 'http://www.w3.org/2006/time#', 'W3C');
-- SKOS
INSERT INTO registered_ontologies (uri, title, namespace, provider) VALUES
('http://www.w3.org/2004/02/skos/core#', 'SKOS', 'http://www.w3.org/2004/02/skos/core#', 'W3C');

-- -----------------------------------------------------------------------------
-- 6. Mappings between OParl properties to semantic properties
-- -----------------------------------------------------------------------------
-- Mappings between OParl properties to semantic properties
INSERT INTO oparl_semantic_mapping (oparl_object_type, oparl_property, target_predicate_uri, target_value_type) VALUES
('Paper', 'type', 'dct:type', 'concept'),
('Paper', 'category', 'dct:subject', 'concept'),
('Meeting', 'type', 'dct:type', 'concept'),
('Meeting', 'category', 'dct:subject', 'concept'),
('Person', 'role', 'org:role', 'concept'),
('Person', 'memberOf', 'org:memberOf', 'concept'),
('Organization', 'type', 'org:Organization', 'concept'),
('Organization', 'memberOf', 'org:memberOf', 'concept');