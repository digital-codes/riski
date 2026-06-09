# Knowledge Graph (KG) Module for risKg

This module provides the Knowledge Graph infrastructure for risKg, including:
- SKOS-based vocabularies
- Semantic triples
- LLM-gestützte query generation via JSON Query Plans
- Data migration from OParl tables

## Architecture

The module follows a 3-layer model:

```
┌─────────────────────────────────────────────────────────────┐
│                    Anfragelage (LLM)                        │
│         Natürlichsprachliche Eingabe → Query Plan           │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────┐
│                  Übersetzungsschicht              │
│         Query Plan → Parameterisierte SQL-CTE      │
└─────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────┐
│              Wissensgraph-Schicht                │
│    Triples + Ontologie + Vokabulare + Tabellen   │
└─────────────────────────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────┐
│                Basis-Datenschicht                 │
│      Body, Paper, File, Meeting, AgendaItem       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Design Principles
- **Reused before developed**: Prioritize EU and DE standards (DCAT-AP, GND, FOAF)
- **Structure and content separation**: Document type ≠ Content category ≠ File role
- **Extensibility**: SKOS concept schemes for controlled vocabularies
- **Read focus**: No write permissions for end users, performance-optimized
- **LLM security**: Query Plan instead of direct SQL generation

## Database Schema

The module adds the following tables to the existing OParl PostgreSQL database:

### Core Triples Table (for flexible semantics)
These tables complement your existing tables, not replace them.

```sql
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
    );
```

### Vocabularies (SKOS-based)
```sql
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
```

## Usage

### Basic Usage

```python
from src.kg.vocabulary import VocabularyManager
from src.kg.query import QueryPlanParser
from src.kg.triplestore import TripleStore
from src.kg.migration import MigrationManager

# Connect to the database
db_connection = ...  # Your database connection

# Initialize the module components
vocabulary_manager = VocabularyManager(db_connection)
query_parser = QueryPlanParser()
triple_store = TripleStore(db_connection)
migration_manager = MigrationManager(db_connection)

# Create a concept scheme
scheme_id = vocabulary_manager.create_scheme(
    uri="https://ris-ki.de/ris/doc-types",
    title="RIS Dokumententypen",
    description="Fachliche Typen von Ratsdokumenten",
    language="de"
)

# Create a concept
concept_id = vocabulary_manager.create_concept(
    scheme_uri="https://ris-ki.de/ris/doc-types",
    uri="https://ris-ki.de/ris/doc-types#Vorlage",
    pref_label="Vorlage",
    definition="Vorlage im parlamentarischen Verfahren"
)

# Add a semantic triple
triple_id = triple_store.add_triple(
    subject_entity_type="paper",
    subject_entity_id=123,
    predicate_uri="dct:type",
    object_entity_type="concept",
    object_entity_id=456,
    confidence_score=0.95,
    provenance_source="LLM"
)

# Execute a query plan
query_plan = {
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

result = query_parser.execute(query_plan)

# Migrate papers with concepts
papers_count = migration_manager.migrate_papers_with_concepts(
    concepts={
        'https://ris-ki.de/ris/content-categories#Mobilität': ['dct:subject']
    }
)

# Get all triples matching the specified criteria
triples = triple_store.get_triples(
    subject_entity_type="paper",
    subject_entity_id=123,
    predicate_uri="dct:type",
    object_entity_type="concept",
    object_entity_id=456,
    limit=100,
    offset=0
)

# Close the database connection
db_connection.close()
```

## Dependencies

The module has the following dependencies:
- Python >= 3.12
- PostgreSQL database
- LLM integration (for LLM-gestützte query generation)

## Installation

To install the module, add the module to your Python path:
```bash
export PYTHONPATH=$PYTHONPATH:/path/to/risKg/src
```

## Configuration

The module is configured through the `src/private.py` file:
- Database connection parameters
- LLM integration parameters

## Security

The module follows the following security principles:
- Read-only access to the database
- Query Plan instead of direct SQL generation
- Security limits (max depth, result limit, timeout)
- Query logging for audit and debugging

## Performance

The module is optimized for performance through:
- Indexes on frequently used columns
- Caching for frequently accessed data
- Query Plan caching for frequently used query plans

## Monitoring

The module is monitored through:
- Query execution time
- Query result size
- Query cache hit rate
- Error rate
- Throughput

## Troubleshooting

### Common Issues

1. **Connection Issues**
   - Check the database connection parameters in `src/private.py`
   - Check the network connectivity to the database
   - Check the firewall rules for the database

2. **Query Issues**
   - Check the query plan syntax
   - Check the query plan constraints
   - Check the query cache
   - Check the query logs

3. **Performance Issues**
   - Check the query execution time
   - Check the query result size
   - Check the query cache hit rate
   - Check the query logs

### Logging

The module logs the following information:
- Query execution time
- Query result size
- Query cache hit rate
- Error rate
- Throughput

## License

The module is licensed under the MIT License.

## Support

For support, please open an issue in the repository.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## Authors

- Your Name - *Initial work*

## Acknowledgments

- OpenSpec - *OpenSpec for spec-driven development