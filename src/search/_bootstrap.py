"""Dual-mode support: running a module in this package directly as a
script (``python src/update/<name>.py``) puts the repository root on
sys.path so ``from src...`` imports resolve."""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
