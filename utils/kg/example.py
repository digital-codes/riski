#!/usr/bin/env python3
"""
Example script for Knowledge Graph (KG) module for risKg
This script demonstrates how to use the KG module for managing SKOS-based vocabularies,
semantic triples, and LLM-gestützte query generation.

Example usage:
    python src/kg/example.py
"""
import sys
import os
import json
import logging

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import the module components
try:
    from src.kg.vocabulary import VocabularyManager
    from src.kg.query import QueryPlanParser
    from src.kg.triplestore import TripleStore
    from src.kg.migration import MigrationManager
except ImportError as e:
    from kg.vocabulary import VocabularyManager
    from kg.query import QueryPlanParser
    from kg.triplestore import TripleStore
    from kg.migration import MigrationManager
    
# Database connection

DB_USER = "riski"
DB_PWD = "riski"
DB_NAME = "riski_agentic"
DB_HOST = "localhost"

def get_db_connection():
    """Get a database connection to the PostgreSQL database."""
    import psycopg2
    
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PWD
        )
        return conn
    except psycopg2.Error as e:
        logger.error(f"Error connecting to database: {e}")
        raise

def example_vocabulary():
    """Example for vocabulary management."""
    logger.info("=== Example: Vocabulary Management ===")
    
    # Connect to the database
    conn = get_db_connection()
    
    # Initialize the vocabulary manager
    vocabulary_manager = VocabularyManager(conn)
    
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
    
    # Get a concept
    concept = vocabulary_manager.get_concept("https://ris-ki.de/ris/doc-types#Vorlage")
    print(json.dumps(concept, indent=2, ensure_ascii=False))
    # Create a vocabulary
    concepts = [
        {
            "uri": "https://ris-ki.de/ris/doc-types#Vorlage",
            "pref_label": "Vorlage",
            "definition": "Vorlage im parlamentarischen Verfahren"
        },
        {
            "uri": "https://ris-ki.de/ris/doc-types#Antrag",
            "pref_label": "Antrag",
            "definition": "Antrag im parlamentarischen Verfahren"
        }
    ]
    concept_ids = vocabulary_manager.create_vocabulary(
        scheme_uri="https://ris-ki.de/ris/doc-types",
        concepts=concepts
    )
    
    # Close the database connection
    conn.close()

def example_triple_store():
    """Example for triple store management."""
    logger.info("=== Example: Triple Store Management ===")
    
    # Connect to the database
    conn = get_db_connection()
    
    # Initialize the triple store
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
    conn.close()

def example_query_plan():
    """Example for query plan management."""
    logger.info("=== Example: Query Plan Management ===")
    
    # Connect to the database
    conn = get_db_connection()
    
    # Initialize the query plan parser
    query_parser = QueryPlanParser()
    
    # Define a query plan that traverses triples from the paper added in example_triple_store
    query_plan = {
        "query_id": "uuid-v4",
        "intent": "pattern_match",
        "start": {
            "entity_type": "paper",
            "entity_id": 123
        },
        "predicates": ["dct:type"],
        "constraints": {
            "max_depth": 3,
            "confidence_threshold": 0.8
        }
    }
    
    # Parse the query plan
    parsed_plan = query_parser.parse_query_plan(json.dumps(query_plan))
    logger.info(f"Parsed query plan: {json.dumps(parsed_plan, indent=2)}")
    
    # generate the sql, just for information
    generated_sql = query_parser.generate_sql(parsed_plan)
    logger.info(f"Generated SQL: {generated_sql}")
    
    # execute sql
    result = query_parser.execute(json.dumps(parsed_plan))
    logger.info(f"Query result: {result}")
    
    # Close the database connection
    conn.close()
    
if __name__ == "__main__":    
    example_triple_store()
    example_query_plan()
    # example_vocabulary()

    