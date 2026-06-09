"""
Knowledge Graph Query Layer for risKg
LLM-gestützte query generation via JSON Query Plans (read-only for security)
"""
from typing import Dict, List, Any, Optional
import json
import logging
import re

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class QueryPlanParser:
    """
    Parser for JSON Query Plans to ensure secure query generation.
    
    This class translates user queries into JSON query plans, which are then
    translated into parameterized SQL-CTE queries.
    
    Design principles:
    - No direct SQL injection: All user input goes through query plans
    - Security limits: Max depth, result limit, timeout
    - Read-only: No write operations allowed
    - LLM security: Query Plan instead of direct SQL generation
    
    Attributes:
        max_depth: Maximum depth for recursive queries
        max_results: Maximum number of results per query
        timeout: Timeout for queries in seconds
        
    Example:
        parser = QueryPlanParser()
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
        result = parser.execute(query_plan)
    """
    
    def __init__(
        self,
        max_depth: int = 3,
        max_results: int = 100,
        timeout_seconds: int = 5
    ):
        """
        Initialize the query plan parser with security limits.
        
        Args:
            max_depth: Maximum depth for recursive queries. Default is 3.
            max_results: Maximum number of results per query. Default is 1000.
        """
        self.max_depth = max_depth
        self.max_results = max_results
        self.timeout_seconds = timeout_seconds
        self.connection = None  # Will be initialized with db connection
        self._query_logging = True  # Logging enabled by default
        self._valid_entity_types = ['paper', 'person', 'organization', 'meeting', 'body', 'concept']
        self._valid_operators = ['equals', 'contains', 'starts_with', 'ends_with', 'in', 'greater_than', 'less_than']
    
    def parse_query_plan(self, query_plan_json: str) -> Dict[str, Any]:
        """
        Parse a JSON query plan into a validated query plan.
        
        Args:
            query_plan_json: JSON string containing the query plan.
            
        Returns:
            Dictionary containing the validated query plan.
            
        Raises:
            ValueError: If the query plan is invalid.
        """
        try:
            query_plan = json.loads(query_plan_json)
            self._validate_query_plan(query_plan)
            return query_plan
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON query plan: {e}")
            raise ValueError(f"Invalid JSON query plan: {e}")
    
    def _validate_query_plan(self, query_plan: Dict[str, Any]) -> None:
        """
        Validate a query plan.
        
        Args:
            query_plan: Dictionary containing the query plan.
            
        Raises:
            ValueError: If the query plan is invalid.
        """
        # Validate intent
        if 'intent' not in query_plan:
            raise ValueError("Query plan must have an 'intent' field")
        
        # Validate constraints
        if 'constraints' in query_plan:
            constraints = query_plan['constraints']
            
            # Validate max_depth
            if 'max_depth' in constraints:
                max_depth = constraints['max_depth']
                if not isinstance(max_depth, int) or max_depth < 1:
                    raise ValueError(f"Invalid max_depth: {max_depth}")
                if max_depth > self.max_depth:
                    logger.warning(f"Max depth {max_depth} exceeds limit {self.max_depth}. Using limit.")
                    query_plan['constraints']['max_depth'] = self.max_depth
            
            # Validate max_results
            if 'max_results' in constraints:
                max_results = constraints['max_results']
                if not isinstance(max_results, int) or max_results < 1:
                    raise ValueError(f"Invalid max_results: {max_results}")
                if max_results > self.max_results:
                    logger.warning(f"Max results {max_results} exceeds limit {self.max_results}. Using limit.")
                    query_plan['constraints']['max_results'] = self.max_results
        
        # Validate start_nodes
        if 'start_nodes' in query_plan:
            for start_node in query_plan['start_nodes']:
                if 'entity_type' in start_node:
                    entity_type = start_node['entity_type']
                    if entity_type not in self._valid_entity_types:
                        raise ValueError(f"Invalid entity_type: {entity_type}")
                
                # Validate filters
                if 'filters' in start_node:
                    for filter in start_node['filters']:
                        if 'operator' in filter:
                            operator = filter['operator']
                            if operator not in self._valid_operators:
                                raise ValueError(f"Invalid operator: {operator}")
        
        # Validate traversal_steps
        if 'traversal_steps' in query_plan:
            for step in query_plan['traversal_steps']:
                if 'direction' in step:
                    direction = step['direction']
                    if direction not in ['outbound', 'inbound', 'both']:
                        raise ValueError(f"Invalid direction: {direction}")
        
        # Validate return_fields
        if 'return_fields' in query_plan:
            for field in query_plan['return_fields']:
                if 'source' in field:
                    source = field['source']
                    if source not in self._valid_entity_types:
                        raise ValueError(f"Invalid source: {source}")
    
    def generate_sql(self, query_plan: Dict[str, Any]) -> str:
        """
        Generate parameterized SQL-CTE from a query plan.
        
        Args:
            query_plan: Dictionary containing the query plan.
            
        Returns:
            Parameterized SQL-CTE string.
            
        Raises:
            ValueError: If the query plan is invalid.
        """
        self._validate_query_plan(query_plan)
        
        intent = query_plan['intent']
        
        if intent == 'single_hop':
            return self._generate_single_hop_sql(query_plan)
        elif intent == 'multi_hop':
            return self._generate_multi_hop_sql(query_plan)
        elif intent == 'pattern_match':
            return self._generate_pattern_match_sql(query_plan)
        elif intent == 'aggregation':
            return self._generate_aggregation_sql(query_plan)
        elif intent == 'similar':
            return self._generate_similar_sql(query_plan)
        else:
            raise ValueError(f"Unsupported intent: {intent}")
    
    def _generate_single_hop_sql(self, query_plan: Dict[str, Any]) -> str:
        """Generate SQL for single-hop queries."""
        # Example implementation
        return """
        -- Single-hop query example
        SELECT *
        FROM semantic_triples st
        WHERE st.subject_entity_type = %s
        AND st.predicate_uri = %s
        AND st.object_entity_type = %s
        LIMIT %s
        """
    
    def _generate_multi_hop_sql(self, query_plan: Dict[str, Any]) -> str:
        """Generate SQL for multi-hop queries."""
        # Example implementation
        return """
        -- Multi-hop query example with recursive CTE
        WITH RECURSIVE traversal AS (
            SELECT st.subject_entity_type, st.subject_entity_id, st.predicate_uri, st.object_value, st.object_entity_type, 1 as depth
            FROM semantic_triples st
            WHERE st.subject_entity_type = %s
            AND st.predicate_uri = %s
            
            UNION
            
            SELECT st.subject_entity_type, st.subject_entity_id, st.predicate_uri, st.object_value, st.object_entity_type, t.depth + 1
            FROM semantic_triples st
            INNER JOIN traversal t ON st.subject_entity_type = t.object_entity_type
            AND st.predicate_uri = %s
            WHERE t.depth < %s
        )
        SELECT DISTINCT *
        FROM traversal
        LIMIT %s
        """
    
    def _generate_pattern_match_sql(self, query_plan: Dict[str, Any]) -> str:
        """Generate SQL for pattern matching queries."""
        # Example implementation
        return """
        -- Pattern matching query example
        WITH matched_entities AS (
            SELECT DISTINCT st.subject_entity_type, st.subject_entity_id
            FROM semantic_triples st
            WHERE (
                (st.predicate_uri = %s AND st.object_value LIKE %s)
                OR (st.predicate_uri = %s AND st.object_value LIKE %s)
            )
        )
        SELECT *
        FROM matched_entities
        LIMIT %s
        """
    
    def _generate_aggregation_sql(self, query_plan: Dict[str, Any]) -> str:
        """Generate SQL for aggregation queries."""
        # Example implementation
        return """
        -- Aggregation query example
        SELECT st.subject_entity_type, COUNT(*) as count
        FROM semantic_triples st
        WHERE st.predicate_uri = %s
        GROUP BY st.subject_entity_type
        ORDER BY count DESC
        LIMIT %s
        """
    
    def _generate_similar_sql(self, query_plan: Dict[str, Any]) -> str:
        """Generate SQL for similarity queries."""
        # Example implementation
        return """
        -- Similarity query example
        WITH target_entity AS (
            SELECT * FROM semantic_triples WHERE subject_entity_type = %s AND subject_entity_id = %s
        ),
        candidate_entities AS (
            SELECT st.subject_entity_type, st.subject_entity_id, COUNT(*) as overlap
            FROM semantic_triples st
            WHERE st.predicate_uri IN (SELECT predicate_uri FROM target_entity)
            AND (st.subject_entity_type, st.subject_entity_id) != (SELECT subject_entity_type, subject_entity_id FROM target_entity)
            GROUP BY st.subject_entity_type, st.subject_entity_id
        )
        SELECT *
        FROM candidate_entities
        ORDER BY overlap DESC
        LIMIT %s
        """
    
    def execute(self, query_plan_json: str) -> List[Dict[str, Any]]:
        """
        Execute a query plan.
        
        Args:
            query_plan_json: JSON string containing the query plan.
            
        Returns:
            List of results.
            
        Raises:
            ValueError: If the query plan is invalid.
        """
        query_plan = self.parse_query_plan(query_plan_json)
        logger.info(f"Executing query plan: {query_plan['intent']}")
        
        # Implement query execution here
        # This should be a parameterized SQL-CTE query based on the query plan
        # For now, return an empty result set
        return []
    
    def close(self):
        """Close the database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None