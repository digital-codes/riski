-- =============================================================================
-- Riski Knowledge Graph - Database Schema
-- Creates semantic layer tables for knowledge graph functionality
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Core triples table (for flexible semantics)
-- -----------------------------------------------------------------------------
-- Semantic triples for additional relationships
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

-- Critical indexes for graph traversal
CREATE INDEX idx_triples_subject ON semantic_triples(subject_entity_type, subject_entity_id);
CREATE INDEX idx_triples_predicate ON semantic_triples(predicate_uri);
CREATE INDEX idx_triples_object_ref ON semantic_triples(object_entity_type, object_entity_id);
CREATE INDEX idx_triples_composite ON semantic_triples(subject_entity_type, subject_entity_id, predicate_uri);

-- -----------------------------------------------------------------------------
-- 2. Vocabularies (SKOS-based)
-- -----------------------------------------------------------------------------
-- Concept schemes (corresponds to SKOS ConceptScheme)
CREATE TABLE concept_schemes (
    uri VARCHAR(500) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    language CHAR(2) DEFAULT 'de',
    version VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Concepts (corresponds to SKOS Concept)
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

-- Links entities to concepts
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

-- -----------------------------------------------------------------------------
-- 3. Ontology Reference Tables
-- -----------------------------------------------------------------------------
-- Registered ontologies and vocabularies
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

-- Mapping between local and external URIs
CREATE TABLE uri_mappings (
    local_uri VARCHAR(500) PRIMARY KEY,
    external_uri VARCHAR(500) NOT NULL,
    mapping_type VARCHAR(50) DEFAULT 'owl:equivalentClass', -- 'owl:equivalentClass', 'skos:closeMatch', etc.
    confidence FLOAT DEFAULT 1.0,
    verified_by VARCHAR(100),
    verified_at TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 4. Mappings for Existing OParl Tables
-- -----------------------------------------------------------------------------
-- Mappings between OParl objects and semantic URIs
CREATE TABLE oparl_semantic_mapping (
    oparl_object_type VARCHAR(100) NOT NULL, -- 'Body', 'Paper', 'Meeting', etc.
    oparl_property VARCHAR(200) NOT NULL,    -- z.B. 'type', 'category'
    target_predicate_uri VARCHAR(500) NOT NULL, -- z.B. 'dct:type', 'dct:subject'
    target_value_type VARCHAR(50) NOT NULL,  -- 'concept', 'literal', 'external_uri'
    transformation_rule TEXT,                 -- Optional: JSON-Rule für Transformation
    priority INT DEFAULT 1,
    PRIMARY KEY (oparl_object_type, oparl_property)
);

-- -----------------------------------------------------------------------------
-- 5. Materialized Views for Frequent Queries
-- -----------------------------------------------------------------------------
-- Documents with all semantic tags
CREATE MATERIALIZED VIEW mv_paper_enriched AS
SELECT
    p.id as paper_id,
    p.created,
    p.name,
    ec.concept_uri as topic_uri,
    c.pref_label as topic_label,
    ec.relation_type,
    st.predicate_uri as additional_predicate,
    st.object_value as predicate_value
FROM "Paper" p
LEFT JOIN entity_concepts ec ON ec.entity_type = 'paper' AND ec.entity_id = p.id
LEFT JOIN concepts c ON c.uri = ec.concept_uri
LEFT JOIN semantic_triples st ON st.subject_entity_type = 'paper' AND st.subject_entity_id = p.id;

-- Persons with roles and affiliations
CREATE MATERIALIZED VIEW mv_person_roles AS
SELECT
    per.id as person_id,
    per.name,
    ec.concept_uri as role_uri,
    c.pref_label as role_label,
    ec2.concept_uri as organization_uri,
    c2.pref_label as organization_label
FROM "Person" per
LEFT JOIN entity_concepts ec ON ec.entity_type = 'person' AND ec.entity_id = per.id AND ec.relation_type = 'ris:role'
LEFT JOIN concepts c ON c.uri = ec.concept_uri
LEFT JOIN entity_concepts ec2 ON ec2.entity_type = 'person' AND ec2.entity_id = per.id AND ec2.relation_type = 'org:memberOf'
LEFT JOIN concepts c2 ON c2.uri = ec2.concept_uri;

 
 