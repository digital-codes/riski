"""Backward-compatibility shim — implementation moved to src.search.local_geo_matching (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.search.local_geo_matching import (  # noqa: F401
    NameMatch,
    literal_name_spans,
    name_matches,
    longest_non_overlapping_name_matches,
    PreparedStreetMatcher,
    prepare_street_matcher,
)
