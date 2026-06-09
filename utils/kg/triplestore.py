"""
Knowledge Graph Triple Store Management for risKg
Triple store management for semantic triples
"""
from typing import Dict, List, Any, Optional
import logging
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TripleStore:
    """
    Manager for semantic triples for knowledge graph.
    
    This class provides functionality for managing triples:
    - Semantic triples (subject, predicate, object)
    
    Attributes:
        db_connection: Database connection for reading/writing triples
        query_parser: Query parser for secure query generation
        
    Example:
        store = TripleStore(db_connection)
        # Add a triple
        triple_id = store.add_triple(
            subject_entity_type="paper",
            subject_entity_id=123,
            predicate_uri="dct:type",
            object_entity_type="concept",
            object_entity_id=456
        )
    """
    
    def __init__(self, db_connection):
        """
        Initialize the triple store manager.
        
        Args:
            db_connection: Database connection for reading/writing triples
        """
        self.db_connection = db_connection
        self._max_results = 1000
    
    def add_triple(self, subject_entity_type: str, subject_entity_id: int, predicate_uri: str, object_value: Optional[str] = None, object_entity_type: Optional[str] = None, object_entity_id: Optional[int] = None, confidence_score: float = 1.0, provenance_source: Optional[str] = None) -> int:
        """
        Add a semantic triple.
        
        Args:
            subject_entity_type: Type of the subject entity (e.g. 'paper', 'person')
            subject_entity_id: ID of the subject entity
            predicate_uri: URI of the predicate (e.g. 'dct:type', 'dct:subject')
            object_value: Value of the object (text value)
            object_entity_type: Type of the object entity (if object is an entity)
            object_entity_id: ID of the object entity (if object is an entity)
            confidence_score: Confidence score (default 1.0)
            provenance_source: Source of the triple (e.g. 'LLM', 'Human')
            
        Returns:
            ID of the created triple
        """
        cursor = self.db_connection.cursor()
        cursor.execute(
            """
            INSERT INTO semantic_triples (
                subject_entity_type, subject_entity_id, predicate_uri, object_value, object_entity_type, object_entity_id, confidence_score, provenance_source
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (subject_entity_type, subject_entity_id, predicate_uri, object_value, object_entity_type, object_entity_id, confidence_score, provenance_source)
        )
        triple_id = cursor.fetchone()[0]
        self.db_connection.commit()
        cursor.close()
        logger.info(f"Added triple: {subject_entity_type}/{subject_entity_id} -> {predicate_uri} -> {object_entity_type or object_value[:50]}")
        return triple_id
    
    def get_triples(self, subject_entity_type: Optional[str] = None, subject_entity_id: Optional[int] = None, predicate_uri: Optional[str] = None, object_entity_type: Optional[str] = None, object_entity_id: Optional[int] = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get triples matching the specified criteria.
        
        Args:
            subject_entity_type: Type of the subject entity (e.g. 'paper', 'person')
            subject_entity_id: ID of the subject entity
            predicate_uri: URI of the predicate (e.g. 'dct:type', 'dct:subject')
            object_entity_type: Type of the object entity (if object is an entity)
            object_entity_id: ID of the object entity (if object is an entity)
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of triples matching the criteria
        """
        cursor = self.db_connection.cursor()
        query = """
            SELECT * FROM semantic_triples WHERE 1=1
        """
        params = []
        
        if subject_entity_type:
            query += " AND subject_entity_type = %s"
            params.append(subject_entity_type)
        if subject_entity_id:
            query += " AND subject_entity_id = %s"
            params.append(subject_entity_id)
        if predicate_uri:
            query += " AND predicate_uri = %s"
            params.append(predicate_uri)
        if object_entity_type:
            query += " AND object_entity_type = %s"
            params.append(object_entity_type)
        if object_entity_id:
            query += " AND object_entity_id = %s"
            params.append(object_entity_id)
        if limit:
            query += " LIMIT %s"
            params.append(limit)
        if offset:
            query += " OFFSET %s"
            params.append(offset)
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        cursor.close()
        
        triples = []
        for result in results:
            triples.append({
                "id": result[0],
                "subject_entity_type": result[1],
                "subject_entity_id": result[2],
                "predicate_uri": result[3],
                "object_value": result[4],
                "object_entity_type": result[5],
                "object_entity_id": result[6],
                "confidence_score": result[7],
                "provenance_source": result[8],
                "created_at": result[9]
            })
        return triples