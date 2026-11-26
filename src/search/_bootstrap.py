"""Ensure the repository root is on sys.path when a module is run directly
(e.g. ``python src/pgTimeline.py``), so ``from src.db import ...`` resolves.

When the module is imported as part of the ``src`` package, the parent
directory is already on sys.path and this import is a no-op.
"""

import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)
