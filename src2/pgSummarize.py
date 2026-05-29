"""
pgSummarize — batch summarisation script (migrated to src2).

Original script performed data‑frame filtering and called the Mistral chat API
directly using ``requests``.  The refactored version replaces the raw request
with the shared ``src2.remote.chat`` helper and drops the hard‑coded URL/API‑
key constants.
"""

import os
import json
import time
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

# ----------------------------------------------------------------------
# Shared remote helper
# ----------------------------------------------------------------------
from src2.remote import chat

# ----------------------------------------------------------------------
# Configuration – directories remain the same as original script
# ----------------------------------------------------------------------
def _run_summarizer():
    src_dir = Path("./ko_extracted")
    dst_dir = Path("./ko_sums")

    md_files = sorted([f for f in src_dir.iterdir() if f.suffix == ".md" and f.is_file()])
    print(len(md_files), md_files[:10])

    # Load file contents
    md_contents = {f.name: f.read_text(encoding="utf-8") for f in md_files}
    md_lengths = [len(md_contents[f.name]) for f in md_files]
    md_lines = [md_contents[f.name].count("\n") + 1 for f in md_files]

    df = pd.DataFrame({"file": [f.name for f in md_files], "length": md_lengths, "lines": md_lines})

    # Drop empty / very small files
    df = df.drop(df[df["length"] < 20].index)
    df = df.drop(df[df["lines"] < 5].index)
    df["ratio"] = df.length / df.lines
    df = df.drop(df[df["ratio"] < 10].index)  # filter out rows with low ratio
    # Note: original had a bug, fixing to proper syntax
    df = df.drop(df[df["ratio"] < 10].index)

    print(df.describe())

    q98 = df["length"].quantile(0.98)
    print("98th percentile:", q98)

    df_q98 = df[df.length <= q98]
    print("DF Q98:", df_q98.describe())

    df_large = df_q98[df_q98.length > 10000]
    print("DF large:", df_large.describe())

    df_small = df_q98[df_q98.length <= 10000]
    print("DF small:", df_small.describe())

    # ----------------------------------------------------------------------
    # Prompt – unchanged (German instructions)
    # ----------------------------------------------------------------------
    prompt = """
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

    Antworte nur auf Deutsch, auch wenn der Bericht englishcen Text enthält. 
    Verwende die Informationen im Bericht, um die Fragen zu beantworten, 
    und füge keine Informationen hinzu, die nicht im Bericht enthalten sind. 
    Wenn eine Information nicht im Bericht enthalten ist, lasse sie einfach weg.

    Stelle sicher, dass Dein Bericht insgesamt nicht länger ist als 8000 Zeichen.

    {report}
    
    """

    # ----------------------------------------------------------------------
    # Helper – request summary via shared ``chat`` function
    # ----------------------------------------------------------------------
def request_summary(report: str, thinking: bool = False) -> str:
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": report},
    ]
    result = chat(messages, thinking=thinking)
    return result.get("content", "")

    # ----------------------------------------------------------------------
    # Main processing loop
    # ----------------------------------------------------------------------
    os.makedirs(dst_dir, exist_ok=True)

    # Small files – copy unchanged
    for d in df_small["file"]:
        content = md_contents[d].strip()
        out_path = dst_dir / d
        if out_path.exists():
            print("Skipping existing file:", d)
            continue
        out_path.write_text(content, encoding="utf-8")

    # Large files – generate summaries
    for d in df_large["file"]:
        content = md_contents[d]
        out_path = dst_dir / d
        if out_path.exists():
            print("Skipping existing file:", d)
            continue
        try:
            summary = request_summary(content)
            cleaned = summary.strip()
            if cleaned.startswith("```"):
                lines = cleaned.splitlines()
                if lines and lines[0].strip().startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip().startswith("```"):
                    lines = lines[:-1]
                cleaned = "\n".join(lines).strip()
            out_path.write_text(cleaned, encoding="utf-8")
            print(f"Wrote summary for {d}")
        except Exception as e:
            print(f"Error processing {d}: {e}")

if __name__ == "__main__":
    _run_summarizer()
