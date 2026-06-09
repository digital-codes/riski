"""
Knowledge Graph Vocabulary Management for risKg
SKOS-based vocabularies for document types, content categories, and file roles
"""
from typing import Dict, List, Any, Optional
import logging
import json
import hashlib

from .query import QueryPlanParser

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VocabularyManager:
    """
    Manager for SKOS-based vocabularies for knowledge graph.
    
    This class provides functionality for managing vocabularies for:
    - Document types (Vorlage, Antrag, Beschluss, etc.)
    - Content categories (Haushalt, Mobilität, etc.)
    - File roles (Hauptdokument, Anlage, etc.)
    
    Attributes:
        db_connection: Database connection for reading/writing vocabularies
        query_parser: Query parser for secure query generation
        
    Example:
        manager = VocabularyManager(db_connection)
        # Create a document type scheme
        scheme_id = manager.create_scheme(
            uri="https://ris-ki.de/ris/doc-types",
            title="RIS Dokumententypen",
            description="Fachliche Typen von Ratsdokumenten",
            language="de"
        )
        # Create a concept
        concept_id = manager.create_concept(
            scheme_uri="https://ris-ki.de/ris/doc-types",
            uri="https://ris-ki.de/ris/doc-types#Vorlage",
            pref_label="Vorlage",
            definition="Vorlage im parlamentarischen Verfahren"
        )
    """
    
    def __init__(self, db_connection):
        """
        Initialize the vocabulary manager.
        
        Args:
            db_connection: Database connection for reading/writing vocabularies
        """
        self.db_connection = db_connection
        self.query_parser = QueryPlanParser()
    
    def create_scheme(self, uri: str, title: str, description: str, language: str = "de") -> int:
        """
        Create a concept scheme.
        
        Args:
            uri: URI for the scheme
            title: Title for the scheme
            description: Description for the scheme
            language: Language code for the scheme. Default is 'de'
            
        Returns:
            ID of the created scheme
        """
        # Insert the scheme
        cursor = self.db_connection.cursor()
        cursor.execute(
            """
            INSERT INTO concept_schemes (uri, title, description, language)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (uri, title, description, language)
        )
        scheme_id = cursor.fetchone()[0]
        self.db_connection.commit()
        cursor.close()
        logger.info(f"Created concept scheme: {uri}")
        return scheme_id
    
    def create_concept(self, scheme_uri: str, uri: str, pref_label: str, definition: str, broader_concept_uri: Optional[str] = None) -> int:
        """
        Create a concept.
        
        Args:
            scheme_uri: URI of the scheme
            uri: URI of the concept
            pref_label: Preferred label for the concept
            definition: Definition for the concept
            broader_concept_uri: URI of the broader concept. Default is None
            
        Returns:
            ID of the created concept
        """
        # Insert the concept
        cursor = self.db_connection.cursor()
        
        # Get broader concept ID
        broader_concept_id = None
        if broader_concept_uri:
            cursor.execute(
                """
                SELECT id FROM concepts WHERE uri = %s
                """,
                (broader_concept_uri)
            )
        result = cursor.fetchone()
        if result:
            broader_concept_id = result[0]
        
        cursor.execute(
            """
            INSERT INTO concepts (scheme_uri, uri, pref_label, definition, broader_concept_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (scheme_uri, uri, pref_label, definition, broader_concept_id)
        )
        concept_id = cursor.fetchone()[0]
        self.db_connection.commit()
        cursor.close()
        logger.info(f"Created concept: {uri}")
        return concept_id
    
    def get_concept(self, concept_uri: str) -> Optional[Dict[str, Any]]:
        """
        Get a concept by URI.
        
        Args:
            concept_uri: URI of the concept
            
        Returns:
            Dictionary containing the concept
        """
        cursor = self.db_connection.cursor()
        cursor.execute(
            """
            SELECT * FROM concepts WHERE uri = %s
            """,
            (concept_uri)
        )
        result = cursor.fetchone()
        cursor.close()
        
        if result:
            return {
                "id": result[0],
                "scheme_uri": result[1],
                "uri": result[2],
                "pref_label": result[3],
                "definition": result[4]
            }
        
        return None
    
    def create_vocabulary(self, scheme_uri: str, concepts: List[Dict[str, str]]) -> List[int]:
        """
        Create a vocabulary.
        
        Args:
            scheme_uri: URI of the scheme
            concepts: List of concepts
            
        Returns:
            List of IDs of the created concepts
        """
        concept_ids = []
        
        # Create each concept
        for concept in concepts:
            concept_id = self.create_concept(
                scheme_uri=scheme_uri,
                uri=concept["uri"],
                pref_label=concept["pref_label"],
                definition=concept.get("definition", "")
            )
            concept_ids.append(concept_id)
        
        logger.info(f"Created vocabulary: {scheme_uri}")
        return concept_ids