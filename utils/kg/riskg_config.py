"""
risKg Domain Configuration
All references should use this domain for global accessibility
"""
# Base URI for risKg
RISKG_BASE_URI = "https://ris-ki.de/ris/"

# Concept scheme URIs
DOC_TYPES_SCHEME = f"{RISKG_BASE_URI}doc-types"
CONTENT_CATEGORIES_SCHEME = f"{RISKG_BASE_URI}content-categories"
FILE_ROLES_SCHEME = f"{RISKG_BASE_URI}file-roles"
PROCEDURE_TYPES_SCHEME = f"{RISKG_BASE_URI}procedure-types"
DECISION_STATUS_SCHEME = f"{RISKG_BASE_URI}decision-status"

# Concept URIs
DOC_TYPES = {
    "Vorlage": f"{DOC_TYPES_SCHEME}#Vorlage",
    "Antrag": f"{DOC_TYPES_SCHEME}#Antrag",
    "Beschluss": f"{DOC_TYPES_SCHEME}#Beschluss",
    "Niederschrift": f"{DOC_TYPES_SCHEME}#Niederschrift",
    "Mitteilung": f"{DOC_TYPES_SCHEME}#Mitteilung",
    "Bericht": f"{DOC_TYPES_SCHEME}#Bericht",
    "Anfrage": f"{DOC_TYPES_SCHEME}#Anfrage",
}

CONTENT_CATEGORIES = {
    "Haushalt": f"{CONTENT_CATEGORIES_SCHEME}#Haushalt",
    "Finanzen": f"{CONTENT_CATEGORIES_SCHEME}#Finanzen",
    "Mobilität": f"{CONTENT_CATEGORIES_SCHEME}#Mobilität",
    "Bauen": f"{CONTENT_CATEGORIES_SCHEME}#Bauen",
    "Bildung": f"{CONTENT_CATEGORIES_SCHEME}#Bildung",
    "Soziales": f"{CONTENT_CATEGORIES_SCHEME}#Soziales",
    "Klima": f"{CONTENT_CATEGORIES_SCHEME}#Klima",
    "Umwelt": f"{CONTENT_CATEGORIES_SCHEME}#Umwelt",
    "Digitalisierung": f"{CONTENT_CATEGORIES_SCHEME}#Digitalisierung",
}

FILE_ROLES = {
    "Hauptdokument": f"{FILE_ROLES_SCHEME}#Hauptdokument",
    "Anlage": f"{FILE_ROLES_SCHEME}#Anlage",
    "Sammeldokument": f"{FILE_ROLES_SCHEME}#Sammeldokument",
    "Beschlussauszug": f"{FILE_ROLES_SCHEME}#Beschlussauszug",
    "ÖffentlicheFassung": f"{FILE_ROLES_SCHEME}#ÖffentlicheFassung",
}

# Mappings to external ontologies
EXTERNAL_ONTOLOGIES = {
    "dcat": "http://www.w3.org/ns/dcat#",
    "dct": "http://purl.org/dc/terms/",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "org": "http://www.w3.org/ns/org#",
    "gn": "https://d-nb.info/standards/elementset/gnd#",
    "schema": "http://schema.org/",
    "time": "http://www.w3.org/2006/time/",
}

# Default ontology mapping prefixes
DEFAULT_ONTOLOGY_PREFIX = "ris"