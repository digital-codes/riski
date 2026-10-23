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

# Marker appended to the markdown when OCR was truncated to the first pages.
_TRUNCATION_NOTE = "\n\n<!-- OCR truncated to the first {max_pages} pages of {total} -->"


def pdf_page_count(pdf_path: Path) -> int | None:
    """Number of pages in *pdf_path*, or None when it cannot be determined."""
    try:
        from pypdf import PdfReader
        with pdf_path.open("rb") as f:
            return len(PdfReader(f).pages)
    except Exception:  # noqa: BLE001 - malformed PDF: fall back to unlimited OCR
        return None


def ocr_pdf_to_markdown(pdf_path: Path, max_pages: int | None = None) -> str:
    """OCR *pdf_path* and return the joined page markdown.

    With *max_pages*, documents with more pages are OCR'd only up to that
    page and a truncation marker is appended.
    """
    pages = None
    note = ""
    if max_pages is not None:
        total = pdf_page_count(pdf_path)
        if total is not None and total > max_pages:
            pages = f"0-{max_pages - 1}"
            note = _TRUNCATION_NOTE.format(max_pages=max_pages, total=total)
    result = remote.ocr(str(pdf_path), pages=pages)
    pages_md = result.get("pages", [])
    return "\n\n".join(p.get("markdown", "") for p in pages_md).strip() + note


def find_missing(pdf_dir: Path, md_dir: Path) -> list[Path]:
    """PDFs in *pdf_dir* that have no ``<stem>.md`` in *md_dir*."""
    return sorted(
        p for p in pdf_dir.glob("*.pdf")
        if not (md_dir / (p.stem + ".md")).is_file()
    )


def run(pdf_dir: Path, md_dir: Path, limit: int | None = None,
        dry_run: bool = False, out_dir: Path | None = None,
        max_pages: int | None = 12) -> dict:
    """OCR all PDFs missing from *md_dir*. Markdown is written to
    *out_dir* (defaults to *md_dir*, e.g. when the canonical markdown
    folder is read-only and new files must land elsewhere).
    Returns a stats dict."""
    out_dir = out_dir or md_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    missing = find_missing(pdf_dir, md_dir)
    if limit is not None:
        missing = missing[:limit]
    stats = {"missing": len(missing), "ocr_ok": 0, "ocr_failed": 0, "empty": 0}
    print(f"{stats['missing']} PDFs without markdown in {md_dir}")

    for i, pdf_path in enumerate(missing, 1):
        out_path = out_dir / (pdf_path.stem + ".md")
        if out_path.exists():
            # Already OCR'd in a previous run (e.g. into a separate out_dir).
            stats["missing"] -= 1
            continue
        if dry_run:
            print(f"[dry-run] would OCR {pdf_path.name} -> {out_path.name}")
            continue
        print(f"[{i}/{len(missing)}] OCR {pdf_path.name} ...", flush=True)
        try:
            markdown = ocr_pdf_to_markdown(pdf_path, max_pages=max_pages)
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
    ap.add_argument("--out-dir", default=None,
                    help="Write markdown here instead of --md-dir (read-only canonical dir)")
    ap.add_argument("--limit", type=int, default=None, help="Max PDFs to OCR (testing)")
    ap.add_argument("--max-pages", type=int, default=12,
                    help="OCR only the first N pages of larger documents (0 = no limit)")
    ap.add_argument("--dry-run", action="store_true", help="Only list what would be OCR'd")
    args = ap.parse_args(argv)

    pdf_dir = Path(args.pdf_dir).expanduser().resolve()
    md_dir = Path(args.md_dir).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else None
    if not pdf_dir.is_dir():
        raise SystemExit(f"pdf_dir is not a directory: {pdf_dir}")

    run(pdf_dir, md_dir, limit=args.limit, dry_run=args.dry_run, out_dir=out_dir,
        max_pages=args.max_pages or None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
