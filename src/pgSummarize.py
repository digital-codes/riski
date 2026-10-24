"""
pgSummarize — batch summarisation script (migrated to src).

The original script performed data-frame filtering and called the Mistral chat
API directly with ``requests``.  The refactored version replaces the raw
request with the shared ``src.remote.chat`` helper and drops the hard-coded
URL/API-key constants (endpoint configuration now lives in ``src.remote`` /
``private.py``).  The data processing and prompt are unchanged.
"""

# Dual-mode import support: allow running this file directly as a script
# (``python src/<name>.py``) as well as importing it as ``src.<name>``.
try:
    import _bootstrap  # noqa: F401  (script mode: puts repo root on sys.path)
except ImportError:
    pass

import os
from pathlib import Path

import pandas as pd

# ----------------------------------------------------------------------
# Shared remote helper
# ----------------------------------------------------------------------
from src.remote import chat

# ----------------------------------------------------------------------
# Configuration – directories remain the same as original script
# ----------------------------------------------------------------------
SRC_DIR = Path("./ko_extracted")
DST_DIR = Path("./ko_sums")
CUTOFF = 8000
# ----------------------------------------------------------------------
# Prompt – unchanged (German instructions)
# ----------------------------------------------------------------------
PROMPT = """
Du bist ein Kommentator. Deine Aufgabe ist es, eine Zusammenfassung eines Bericht einer
Verwaltungssitzung oder einer Verwaltungsvorlage zu schreiben.
Wenn dir der Bericht vorgelegt wird, beantworte folgende Fragen dazu, sofern möglich:

 1) welche person legt den bericht vor
 2) was ist das datum des berichts
 3) bei welchem gremium war die sitzung oder bei welchem gremium wurde die vorlage behandelt
 4) was ist das thema des berichts
 5) was ist der titel des bericht. Leite einen passenden title vom thema ab, wenn keiner explizit angegeben wird
 6) Welches sind die wichtigstens Argumente im bericht
 7) Gibt es ein Ergebnis oder einen Beschluss? Wenn ja, welches.

Anschließend kombiniere alle Informationen und verfasse einen Zusammenfassung  im Markdown‑Format. Verwende keine
```markdown ... ``` code fence, sondern schreibe die Zusammenfassung direkt als Fließtext.

Antworte nur auf Deutsch, auch wenn der Bericht englischen Text enthält.
Verwende die Informationen im Bericht, um die Fragen zu beantworten,
und füge keine Informationen hinzu, die nicht im Bericht enthalten sind.
Wenn eine Information nicht im Bericht enthalten ist, lasse sie einfach weg.

Stelle sicher, dass Dein Bericht insgesamt nicht länger ist als CUTOFF Zeichen.

{report}

"""


def request_summary(report: str, thinking: bool = False) -> str:
    """Summarise *report* via the shared chat client and return the content."""
    messages = [
        {"role": "system", "content": PROMPT},
        {"role": "user", "content": report},
    ]
    result = chat(messages, thinking=thinking)
    return result.get("content", "")


def _strip_code_fence(summary: str) -> str:
    """Remove a surrounding `````...```` code fence, if present."""
    cleaned = summary.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def _run_summarizer(src_dir: Path | None = None, dst_dir: Path | None = None) -> None:
    src_dir = src_dir or SRC_DIR
    dst_dir = dst_dir or DST_DIR
    md_files = sorted([f for f in src_dir.iterdir() if f.suffix == ".md" and f.is_file()])
    print(len(md_files), md_files[:10])

    # Collect lengths/lines only — contents are read lazily per file below
    # (loading ~130k markdown files into memory at once is unnecessary).
    md_lengths, md_lines = [], []
    for f in md_files:
        text = f.read_text(encoding="utf-8", errors="replace")
        md_lengths.append(len(text))
        md_lines.append(text.count("\n") + 1)

    df = pd.DataFrame(
        {"file": [f.name for f in md_files], "length": md_lengths, "lines": md_lines}
    )

    # Drop empty / very small files
    df = df.drop(df[df["length"] < 20].index)
    # Drop files which contain only a single line, most likely an image link
    df = df.drop(df[df["lines"] < 5].index)
    df["ratio"] = df.length / df.lines
    # Drop files with bad ratio, probably an OCR issue
    df = df.drop(df[df["ratio"] < 10].index)

    print(df.describe())

    q98 = df["length"].quantile(0.98)
    print("98th percentile:", q98)

    df_q98 = df[df.length <= q98]
    print("DF Q98:", df_q98.describe())

    df_large = df_q98[df_q98.length > CUTOFF]
    print("DF large:", df_large.describe())

    df_small = df_q98[df_q98.length <= CUTOFF]
    print("DF small:", df_small.describe())

    os.makedirs(dst_dir, exist_ok=True)

    def read_source(name: str) -> str:
        return (src_dir / name).read_text(encoding="utf-8", errors="replace")

    # Small files – copy unchanged
    small_names = df_small["file"].values
    print("Small files:", len(small_names))
    for d in small_names:
        content = read_source(d).strip()
        print("Processing file:", d)
        out_path = dst_dir / d
        if out_path.exists():
            print("Skipping existing file:", d)
            continue
        out_path.write_text(content, encoding="utf-8")

    # Large files – generate summaries
    large_names = df_large["file"].values
    print("Large files:", len(large_names))
    for d in large_names:
        content = read_source(d)
        print("Processing file:", d)
        out_path = dst_dir / d
        if out_path.exists():
            print("Skipping existing file:", d)
            continue
        try:
            summary = request_summary(content)
            cleaned = _strip_code_fence(summary)
            print(f"Cleaned summary for {d}:\n{cleaned}\n\n")
            out_path.write_text(cleaned[:CUTOFF], encoding="utf-8")
        except Exception as e:
            print(f"Error processing {d}: {e}")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Summarise oversized markdown files into ko_sums")
    ap.add_argument("--src-dir", default=str(SRC_DIR), help="Directory with extracted markdown")
    ap.add_argument("--dst-dir", default=str(DST_DIR), help="Directory for (summarised) outputs")
    args = ap.parse_args()
    _run_summarizer(src_dir=Path(args.src_dir), dst_dir=Path(args.dst_dir))
