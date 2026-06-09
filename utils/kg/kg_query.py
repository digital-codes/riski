"""
Knowledge Graph Query Layer for risKg
LLM-gestützte query generation via JSON Query Plans (read-only for security)
"""
from typing import Dict, List, Any, Optional
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class KGQueryPlanParser:
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
        parser = KGQueryPlanParser()
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
        max_results: int = 1000,
        timeout_seconds: int = 5
    ):
        """
        Initialize the query plan parser with security limits.
        
        Args:
            max_depth: Maximum depth for recursive queries. Default is 3.
            max_results: Maximum number of results per query. Default is 1000.
            timeout_seconds: Timeout for queries in seconds. Default is 5.
        """
        self.max_depth = max_depth
        self.max_results = max_results
        self.timeout_seconds = timeout_seconds
        self.connection = None  # Will be initialized with db connection
        self._query_logging = True  # Logging enabled by default
    
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
        except ValueError as e:
            logger.error(f"Invalid query plan: {e}")
            raise
    
    def _validate_query_plan(self, query_plan: Dict[str, Any]) -> None:
        """
        Validate a query plan.
        
        Args:
            query_plan: Dictionary containing the query plan.
            
        Raises:
            ValueError: If the query plan is invalid.
        """
        # Validate query plan structure
        if "constraints" in query_plan:
            constraints = query_plan["constraints"]
            
            # Validate max_depth
            if "max_depth" in constraints:
                max_depth = constraints["max_depth"]
                if not isinstance(max_depth, int) or max_depth < 1:
                    raise ValueError(f"Invalid max_depth: {max_depth}")
                # Enforce max allowed depth
                if max_depth > self.max_depth:
                    logger.warning(f"Max depth {max_depth} exceeds limit {self.max_depth}. Using limit.")
                    query_plan["constraints"]["max_depth"] = self.max_depth
            
            # Validate max_results
            if "max_results" in constraints:
                max_results = constraints["max_results"]
                if not isinstance(max_results, int) or max_results < 1:
                    raise ValueError(f"Invalid max_results: {max_results}")
                # Enforce max results
                if max_results > self.max_results:
                    logger.warning(f"Max results {max_results} exceeds limit {self.max_results}. Using limit.")
                    query_plan["constraints"]["max_results"] = self.max_results
            
            # Validate timeout
            if "timeout_seconds" in constraints:
                timeout_seconds = constraints["timeout_seconds"]
                if not isinstance(timeout_seconds, int) or timeout_seconds < 1:
                    raise ValueError(f"Invalid timeout_seconds: {timeout_seconds}")
                # Enforce timeout
                if timeout_seconds > self.timeout_seconds:
                    logger.warning(f"Timeout {timeout_seconds} exceeds limit {self.timeout_seconds}. Using limit.")
                    query_plan["constraints"]["timeout_seconds"] = self.timeout_seconds
    
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