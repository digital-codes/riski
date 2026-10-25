"""Backward-compatibility shim — implementation moved to src.update.pgSummarize (change: unified-update-pipeline, task 4.2)."""
# Dual-mode import support (shim): puts the repo root on sys.path when
# run directly as a script (python src/<name>.py).
try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass

from src.update.pgSummarize import (  # noqa: F401
    CUTOFF,
    DST_DIR,
    PROMPT,
    SRC_DIR,
    _run_summarizer,
    request_summary,
)

if __name__ == "__main__":
    # original CLI: python src/pgSummarize.py [--src-dir ...] [--dst-dir ...]
    import argparse
    from pathlib import Path as _Path

    ap = argparse.ArgumentParser(description="Summarise oversized markdown files into ko_sums")
    ap.add_argument("--src-dir", default=str(SRC_DIR), help="Directory with extracted markdown")
    ap.add_argument("--dst-dir", default=str(DST_DIR), help="Directory for (summarised) outputs")
    args = ap.parse_args()
    _run_summarizer(src_dir=_Path(args.src_dir), dst_dir=_Path(args.dst_dir))
