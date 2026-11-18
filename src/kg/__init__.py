"""kg — knowledge extraction prototype layer (change: kg-statement-extraction).

Read-only over the PostgreSQL OParl database, output into a local SQLite
store under ``results/``. Scripts (one per stage):

* ``kgIdentify.py``   — discover request/response document pairs
* ``kgTagSchema.py``  — ris-ki tag table seed
* ``kgTagSystemOne.py`` — tag assignment via SystemOne (one call,
                         all tags + qualifiers, noul = confidence)
* ``kgAuthors.py``    — party author identification
* ``kgStatements.py`` — request/response statement extraction
* ``kgCrossCheck.py`` — round-trip fact verification
* ``kgModelSelect.py``— language model comparison harness
* ``kgExport.py``     — JSON export view of the store

Shared helpers live in ``kgStore`` (SQLite), ``kgStatus`` (console
status reporter) and ``kgRemote`` (ollama-bounded model client).
"""

from src.kg.kgStore import KgStore
from src.kg.kgStatus import StatusTicker

__all__ = ["KgStore", "StatusTicker"]
