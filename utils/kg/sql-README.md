# SQL Scripts for risKg Knowledge Graph

These SQL scripts set up the semantic layer for the risKg Knowledge Graph on top of the existing OParl PostgreSQL database.

## Prerequisites

Before running these scripts, ensure you have:
- PostgreSQL database `riski_agentic` running
- Write permissions to the database (e.g., database owner or superuser)
- Existing OParl tables in the database (the scripts assume tables like `paper`, `person`, `body`, etc. exist)

## Scripts

### 1. `01_create_schema.sql`
Creates the semantic layer tables:
- `semantic_triples` - For flexible semantic relationships
- `concept_schemes` - For SKOS concept schemes
- `concepts` - For SKOS concepts with hierarchy
- `entity_concepts` - For entity-concept links
- `registered_ontologies` - For external ontologies
- `uri_mappings` - For URI mappings
- `oparl_semantic_mapping` - For OParl mappings
- Materialized views for frequent queries

### 2. `02_initial_data.sql`
Populates initial data:
- Concept schemes (5 schemes)
- Document types (29 concepts)
- Content categories (57 concepts)
- File roles (8 concepts)
- External ontologies (9 ontologies)
- OParl mappings (11 mappings)

## Running the Scripts

```bash
# Connect with write permissions (use your database credentials)
psql -h localhost -U <username> -d riski_agentic -f sql/01_create_schema.sql
psql -h localhost -U <username> -d riski_agentic -f sql/02_initial_data.sql
```

## Domain Configuration

All references use the risKg domain: `https://ris-ki.de/ris`

The domain is configured in `src/riskg_config.py`:
- `RISKG_BASE_URI = "https://ris-ki.de/ris"`

## After Running the Scripts

After running the scripts, you can use the Knowledge Graph modules:
- `src/kg_query.py` - Query layer with JSON Query Plans
- `src/kg_vocabulary.py` - Vocabulary management
- `src/kg_coverage/coverage.py` - Coverage checker

## Troubleshooting

### Permission Denied
If you get "permission denied for schema public":
- Run the script with a user with write permissions (database owner or superuser)
- Or grant permissions to the user: `GRANT ALL PRIVILEGES ON SCHEMA public TO <username>`

### Table Already Exists
If you get "relation already exists":
- The tables are already created, skip the schema creation script
- Only run the initial data script to populate the data

### Table Not Found
If you get "relation does not exist":
- Ensure the existing OParl tables are in the database
- The scripts assume tables like `paper`, `person`, `body`, etc. exist

## More Information

For more information about the Knowledge Graph modules, see the Python module documentation.
