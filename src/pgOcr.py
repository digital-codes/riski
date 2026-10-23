"""pgOcr — OCR missing PDFs into markdown files.

For every PDF in the PDF folder without a corresponding markdown file in
the markdown folder, runs Mistral OCR via the shared ``src.remote.ocr``
helper (endpoint/keys configurable in ``private.py``: ``OCR_URL``,
``OCR_KEY``, ``OCR_MDL``) and writes the concatenated page markdown as
``<stem>.md`` next to the other extracted documents.

Resumable: existing markdown files are skipped, failures are logged and
do not abort the run.
"""

# Dual-mode import support: allow running this file directly as a script
# (``python src/<name>.py``) as well as importing it as ``src.<name>``.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

import argparse
from pathlib import Path

from src import remote


def ocr_pdf_to_markdown(pdf_path: Path) -> str:
    """OCR *pdf_path* and return the joined page markdown."""
    result = remote.ocr(str(pdf_path))
    pages = result.get("pages", [])
    return "\n\n".join(p.get("markdown", "") for p in pages).strip()


def find_missing(pdf_dir: Path, md_dir: Path) -> list[Path]:
    """PDFs in *pdf_dir* that have no ``<stem>.md`` in *md_dir*."""
    return sorted(
        p for p in pdf_dir.glob("*.pdf")
        if not (md_dir / (p.stem + ".md")).is_file()
    )


def run(pdf_dir: Path, md_dir: Path, limit: int | None = None,
        dry_run: bool = False) -> dict:
    """OCR all missing PDFs. Returns a stats dict."""
    md_dir.mkdir(parents=True, exist_ok=True)
    missing = find_missing(pdf_dir, md_dir)
    if limit is not None:
        missing = missing[:limit]
    stats = {"missing": len(missing), "ocr_ok": 0, "ocr_failed": 0, "empty": 0}
    print(f"{stats['missing']} PDFs without markdown in {md_dir}")

    for i, pdf_path in enumerate(missing, 1):
        out_path = md_dir / (pdf_path.stem + ".md")
        if dry_run:
            print(f"[dry-run] would OCR {pdf_path.name} -> {out_path.name}")
            continue
        print(f"[{i}/{len(missing)}] OCR {pdf_path.name} ...", flush=True)
        try:
            markdown = ocr_pdf_to_markdown(pdf_path)
        except Exception as e:  # noqa: BLE001 - keep going on single failures
            print(f"  ERROR {pdf_path.name}: {e}", flush=True)
            stats["ocr_failed"] += 1
            continue
        if not markdown:
            print(f"  EMPTY result for {pdf_path.name}, not written", flush=True)
            stats["empty"] += 1
            continue
        out_path.write_text(markdown, encoding="utf-8")
        stats["ocr_ok"] += 1

    print("Summary:", stats)
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="OCR PDFs missing markdown via src.remote.ocr (Mistral)")
    ap.add_argument("--pdf-dir", default="/mnt_ai/data/odd26/ris/ko_pdf")
    ap.add_argument("--md-dir", default="/mnt_ai/data/odd26/ris/ko_extracted")
    ap.add_argument("--limit", type=int, default=None, help="Max PDFs to OCR (testing)")
    ap.add_argument("--dry-run", action="store_true", help="Only list what would be OCR'd")
    args = ap.parse_args(argv)

    pdf_dir = Path(args.pdf_dir).expanduser().resolve()
    md_dir = Path(args.md_dir).expanduser().resolve()
    if not pdf_dir.is_dir():
        raise SystemExit(f"pdf_dir is not a directory: {pdf_dir}")

    run(pdf_dir, md_dir, limit=args.limit, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
