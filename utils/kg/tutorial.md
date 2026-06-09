# Tutorial: Using the Knowledge Graph (KG) Module for risKg

This tutorial provides step-by-step instructions on how to use the generated KG modules for the risKg Knowledge Graph implementation.

## Prerequisites

Before starting this tutorial, ensure you have:
- Python ≥3.12 installed
- PostgreSQL database "riski_agentic" running
- PostgreSQL credentials: `wiski`/`wiski` (read-only access)

Install required Python packages (only these are needed):
- `psycopg2` - PostgreSQL driver for Python
- `requests` - HTTP library (optional, for LLM integration)

## Architecture Overview

The risKg KG module follows a 3-layer model:

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
┌─────────────────────────────────────────────────────────────────────────────┐
│              Wissensgraph-Schicht (PostgreSQL)              │
│    Triples + Ontologie + Vokabulare + Tabellen             │
└─────────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────────┐
│                Basis-Datenschicht (Bestehend)               │
│      Body, Paper, File, Meeting, AgendaItem       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Design Principles
- **Reused before developed**: Prioritize EU and DE standards (DCAT-AP, GND, FOAF)
- **Structure and content separation**: Document type ≠ Content category ≠ File role
- **Extensibility**: SKOS concept schemes for controlled vocabularies
- **Read focus**: No write permissions for end users, performance-optimized
- **LLM security**: Query Plan instead of direct SQL generation

## Step-by-Step Usage

### Step 1: Setup

1. Navigate to your project directory:
   ```bash
   cd /home/agent/projects/risKg
   ```

2. Add the project to your Python path:
   ```bash
   export PYTHONPATH=$PYTHONPATH:/home/agent/projects/risKg/src
   ```

3. Verify the database connection:
   ```bash
   psql -h localhost -U wiski -d riski_agentic -c 'SELECT COUNT(*) FROM "Paper"'
   ```

### Step 2: Basic Usage

Here's a complete example showing all module capabilities:

```python
#!/usr/bin/env python3
"""Complete usage example for risKg KG module."""

import json
import logging
import sys
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import the KG modules
from kg.vocabulary import VocabularyManager
from kg.query import QueryPlanParser
from kg.triplestore import TripleStore
from kg.migration import MigrationManager

def main():
    """Main function demonstrating all KG module features."""
    
    # --- 1. Database Connection ---
    logger.info("=== Connecting to PostgreSQL database ===")
    
    try:
        import psycopg2
        conn = psycopg2.connect(
            host="localhost",
            database="riski_agentic",
            user="wiski",
            password="wiski"
        )
        logger.info("Connected successfully")
        
    except psycopg2.Error as e:
        logger.error(f"Database connection failed: {e}")
        logger.error("Please ensure:")
        logger.error("- PostgreSQL is running")
        logger.error("- Database 'riski_agentic' exists")
        logger.error("- User 'wiski' with password 'wiski' has read access")
        sys.exit(1)
    
    try:
        # --- 2. Vocabulary Management ---
        logger.info("=== Vocabulary Management ===")
        
        # Initialize vocabulary manager
        vocabulary_manager = VocabularyManager(conn)
        
        # Create a document type concept scheme
        doc_scheme_id = vocabulary_manager.create_scheme(
            uri="https://ris-ki.de/ris/doc-types",
            title="RIS Dokumententypen",
            description="Fachliche Typen von Ratsdokumenten",
            language="de"
        )
        logger.info(f"Created concept scheme: {doc_scheme_id}")
        
        # Create a content category concept scheme
        category_scheme_id = vocabulary_manager.create_scheme(
            uri="https://ris-ki.de/ris/content-categories",
            title="RIS Inhaltskategorien",
            description="Thematische Einordnung von Ratsinhalten",
            language="de"
        )
        logger.info(f"Created concept scheme: {category_scheme_id}")
        
        # Create document type concepts
        doc_concepts = [
            {"uri": "https://ris-ki.de/ris/doc-types#Vorlage", "pref_label": "Vorlage", "definition": "Vorlage im parlamentarischen Verfahren"}
        ]
        vocabulary_manager.create_vocabulary(
            scheme_uri="https://ris-ki.de/ris/doc-types",
            concepts=doc_concepts
        )
        
        # Create content category concepts
        category_concepts = [
            {"uri": "https://ris-ki.de/ris/content-categories#Mobilität", "pref_label": "Mobilität", "definition": "Mobilitätsangelegenheiten"}
        ]
        vocabulary_manager.create_vocabulary(
            scheme_uri="https://ris-ki.de/ris/content-categories",
            concepts=category_concepts
        )
        
        # --- 3. Triple Store Operations ---
        logger.info("=== Triple Store Operations ===")
        
        # Initialize triple store
        triple_store = TripleStore(conn)
        
        # Add a semantic triple linking a paper to a document type
        paper_id = 1  # Existing paper ID from your database
        doc_type_id = 1  # Concept ID from concepts table
        triple_id = triple_store.add_triple(
            subject_entity_type="paper",
            subject_entity_id=paper_id,
            predicate_uri="dct:type",
            object_entity_type="concept",
            object_entity_id=doc_type_id,
            confidence_score=0.95,
            provenance_source="LLM"
        )
        logger.info(f"Added triple: {triple_id}")
        
        # Add a triple linking a paper to a content category
        content_category_id = 1  # Concept ID from concepts table
        triple_id = triple_store.add_triple(
            subject_entity_type="paper",
            subject_entity_id=paper_id,
            predicate_uri="dct:subject",
            object_entity_type="concept",
            object_entity_id=content_category_id,
            confidence_score=0.85,
            provenance_source="LLM"
        )
        logger.info(f"Added triple: {triple_id}")
        
        # Retrieve triples for a paper
        triples = triple_store.get_triples(
            subject_entity_type="paper",
            subject_entity_id=paper_id,
            limit=100,
            offset=0
        )
        logger.info(f"Retrieved {len(triples)} triples for paper {paper_id}")
        
        # --- 4. Query Plan Execution ---
        logger.info("=== Query Plan Execution ===")
        
        # Initialize query plan parser
        query_parser = QueryPlanParser()
        
        # Define a query plan for graph traversal
        query_plan = {
            "query_id": "tutorial-query-1",
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
                        {"property": "id", "operator": "equals", "value": paper_id}
                    ]
                }
            ],
            "traversal_steps": [
                {
                    "step": 1,
                    "predicate_uri": "dct:subject",
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
        
        # Execute query plan
        results = query_parser.execute(json.dumps(query_plan))
        logger.info(f"Query plan executed: {len(results)} results")
        
        # --- 5. Data Migration ---
        logger.info("=== Data Migration ===")
        
        # Initialize migration manager
        migration_manager = MigrationManager(conn)
        
        # Migrate papers with document types
        papers_count = migration_manager.migrate_papers_with_concepts(
            concepts={
                "https://ris-ki.de/ris/doc-types#Vorlage": ["dct:type"]
            }
        )
        logger.info(f"Migrated {papers_count} papers with document types")
        
        # Migrate papers with content categories
        papers_count = migration_manager.migrate_papers_with_concepts(
            concepts={
                "https://ris-ki.de/ris/content-categories#Mobilität": ["dct:subject"]
            }
        )
        logger.info(f"Migrated {papers_count} papers with content categories")
        
        # --- 6. Advanced Operations ---
        logger.info("=== Advanced Operations ===")
        
        # Batch add triples for multiple papers
        for paper_id in [1, 2, 3]:
            triple_id = triple_store.add_triple(
                subject_entity_type="paper",
                subject_entity_id=paper_id,
                predicate_uri="dct:subject",
                object_entity_type="concept",
                object_entity_id=content_category_id,
                confidence_score=0.85,
                provenance_source="LLM"
            )
        
        # Advanced query with pattern matching
        query_plan_pattern = {
            "query_id": "tutorial-pattern-1",
            "intent": "pattern_match",
            "constraints": {
                "max_depth": 2,
                "max_results": 50,
                "timeout_seconds": 3
            },
            "start_nodes": [
                {
                    "entity_type": "paper",
                    "filters": [
                        {"property": "title", "operator": "contains", "value": "Mobilität"}
                    ]
                }
            ],
            "traversal_steps": [
                {
                    "step": 1,
                    "predicate_uri": "dct:subject",
                    "direction": "outbound",
                    "target_entity_type": "concept"
                }
            ],
            "return_fields": [
                {"source": "paper", "field": "title"},
                {"source": "concept", "field": "pref_label"}
            ]
        }
        
        # Execute pattern matching query
        pattern_results = query_parser.execute(json.dumps(query_plan_pattern))
        logger.info(f"Pattern matching query: {len(pattern_results)} results")
        
        # --- 7. Final Summary ---
        logger.info("=== Final Summary ===")
        logger.info("Tutorial completed successfully!")
        logger.info("Key features demonstrated:")
        logger.info("- Vocabulary management (concept schemes, concepts)")
        logger.info("- Triple store operations (add, retrieve)")
        logger.info("- Query plan execution (graph traversal, pattern matching)")
        logger.info("- Data migration (papers with concepts)")
        
    finally:
        # Close the database connection
        conn.close()
        logger.info("Database connection closed")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

### Step 3: Save and Run the Example

1. Save the code above as `kg_tutorial.py` in the project root:
   ```bash
   cat > kg_tutorial.py << 'EOF'
   # Paste the complete Python code here
   EOF
   ```

2. Make the script executable:
   ```bash
   chmod +x kg_tutorial.py
   ```

3. Run the tutorial:
   ```bash
   python kg_tutorial.py
   ```

## Common Tasks

### Task 1: Add a New Concept Scheme

```python
from kg.vocabulary import VocabularyManager

conn = psycopg2.connect(host="localhost", database="riski_agentic", user="wiski", password="wiski")
vocabulary_manager = VocabularyManager(conn)

# Add a new concept scheme
vocabulary_manager.create_scheme(
    uri="https://ris-ki.de/ris/new-scheme",
    title="New Scheme Title",
    description="Description of new scheme",
    language="de"
)

conn.close()
```

### Task 2: Add a New Concept

```python
from kg.vocabulary import VocabularyManager

conn = psycopg2.connect(host="localhost", database="riski_agentic", user="wiski", password="wiski")
vocabulary_manager = VocabularyManager(conn)

# Add a new concept
vocabulary_manager.create_concept(
    scheme_uri="https://ris-ki.de/ris/doc-types",
    uri="https://ris-ki.de/ris/doc-types#Antrag",
    pref_label="Antrag",
    definition="Antrag im parlamentarischen Verfahren"
)

conn.close()
```

### Task 3: Add a Semantic Triple

```python
from kg.triplestore import TripleStore

conn = psycopg2.connect(host="localhost", database="riski_agentic", user="wiski", password="wiski")
triple_store = TripleStore(conn)

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

print(f"Added triple: {triple_id}")
conn.close()
```

### Task 4: Execute a Query Plan

```python
import json
from kg.query import QueryPlanParser

conn = psycopg2.connect(host="localhost", database="riski_agentic", user="wiski", password="wiski")
query_parser = QueryPlanParser()

# Define a query plan
query_plan = {
    "query_id": "my-query",
    "intent": "graph_traversal",
    "constraints": {
        "max_depth": 3,
    }
}




# Postgres 
sudo -u postgres psql
postgres=# \c riski_agentic
postgres=# ALTER DEFAULT PRIVILEGES FOR ROLE riski IN SCHEMA public GRANT SELECT ON TABLES TO wiski;
postgres=# GRANT SELECT ON ALL TABLES IN SCHEMA public TO wiski;
postgres=# GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO wiski;
postgres=# 
\q

