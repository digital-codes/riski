#!/usr/bin/env python
"""Pick 100 sample markdown documents (Beschluesse, Antraege, Beschlussvorlagen).

Document-type identification (docs: docs/kgIdentify.md, docs/pgTags.md,
src/pgCategorise.py; OParL model in the README):
  - Chain: File → File__paper__Paper → Paper → Paper__consultation__Consultation
    → Consultation (Consultation carries role + agendaItemSid/meetingSid).
  - Paper.papertype ('Antrag', 'Beschlussvorlage', ...) is the authoritative
    paper type; File.name mirrors the RIS document label; File.oparlKey is
    numeric and maps 1:1 to the 8-digit zero-padded markdown stem in
    /mnt_ai/data/odd26/ris/ko_extracted (e.g. 680170 -> 00680170.md).

Pools:
  - antrag           : parent Paper.papertype='Antrag' AND File.name ~ '^Antrag'
  - beschlussvorlage : parent Paper.papertype='Beschlussvorlage' AND File.name
                       ILIKE 'Beschlussvorlage%'/'Beschlusssvorlage%'
  - beschluss        : decision records — UNION of
                       a) agenda-item files of consultations with
                          Consultation.role='Entscheidung' whose AgendaItem
                          result is a decision (beschlossen/zugestimmt/
                          abgelehnt/einverstanden/genehmigt/gewählt) — the
                          per-TOP Protokollauszug/Niederschrift excerpts,
                       b) name-based decision-list documents (standalone
                          'Beschluss'/'Beschlüsse'/'Wortlaut' names; compound
                          vorlage packets, 'ohne Beschluss', drafts and all
                          'vorlag*' excluded).

Selection is deterministic (order by md5(oparlKey)) with caps of 4 samples
per identical document name and 10 per name family (leading dates stripped)
so repeated series cannot dominate the sample. Every candidate needs an
existing, non-empty markdown file in ko_extracted whose text contains its
own type keyword (content gate: catches mislabeled attachments, e.g. a file
named 'Beschlussvorlage ...' whose markdown is an Informationsvorlage). 33 x
Antrag, 33 x Beschlussvorlage, 34 x Beschluss = 100 files, copied unchanged
into ./samples/ and documented in samples/manifest.csv.

Run from the repo root:  python tmp/samples/pick_samples.py
"""
import csv
import hashlib
import os
import shutil
import subprocess
import sys

REPO = "/mnt_ai/agent/riski"
KO_DIR = "/mnt_ai/data/odd26/ris/ko_extracted"
TMP = os.path.join(REPO, "tmp", "samples")
OUT = os.path.join(REPO, "samples")

sys.path.insert(0, REPO)
from src import private  # DB credentials; never printed

QUOTA = {"antrag": 33, "beschlussvorlage": 33, "beschluss": 34}
NAME_CAP = 4    # max samples sharing one identical File.name
FAMILY_CAP = 10  # max samples per name family (leading date tokens stripped)

# content gate: the markdown text must contain one of these (lowercase)
CONTENT_KEYWORDS = {
    "antrag": ("antrag",),
    "beschlussvorlage": ("beschlussvorlage",),
    "beschluss": ("beschluss", "beschlüsse", "beschlossen", "entscheid"),
}

QUERIES = {
    "antrag": """
        SELECT f."oparlKey", f.name, coalesce(to_char(f."date", 'YYYY-MM-DD'), ''),
               'papertype=Antrag + File.name~Antrag', ''
        FROM "File" f
        JOIN "File__paper__Paper" fp ON fp."srcSid" = f.sid
        JOIN "Paper" p ON p.sid = fp."tgtSid"
        WHERE p.papertype = 'Antrag' AND f.name ~* '^antrag\\y'
    """,
    "beschlussvorlage": """
        SELECT f."oparlKey", f.name, coalesce(to_char(f."date", 'YYYY-MM-DD'), ''),
               'papertype=Beschlussvorlage + File.name~Beschlussvorlage*', ''
        FROM "File" f
        JOIN "File__paper__Paper" fp ON fp."srcSid" = f.sid
        JOIN "Paper" p ON p.sid = fp."tgtSid"
        WHERE p.papertype = 'Beschlussvorlage'
          AND (f.name ILIKE 'Beschlussvorlage%' OR f.name ILIKE 'Beschlusssvorlage%')
    """,
    "beschluss": """
        SELECT f."oparlKey", f.name, coalesce(to_char(f."date", 'YYYY-MM-DD'), ''),
               'consultation role=Entscheidung', coalesce(ai.result, '')
        FROM "Consultation" c
        JOIN "AgendaItem__auxiliaryFile__File" af ON af."srcSid" = c."agendaItemSid"
        JOIN "AgendaItem" ai ON ai.sid = c."agendaItemSid"
        JOIN "File" f ON f.sid = af."tgtSid"
        WHERE c.role = 'Entscheidung'
          AND lower(coalesce(ai.result, '')) ~ 'beschlossen|zugestimmt|abgelehnt|einverstanden|genehmigt|gewählt'
          AND f.name !~* '^(test|blanko)$' AND f.name !~* '^[0-9][0-9 ._-]*$'
          -- request/response documents attached to the same agenda item are
          -- no decision records (Antrag/Stellungnahme/Anfrage/Änderungsantrag)
          AND f.name !~* 'antrag|anfrage|stellungnahme'
        UNION ALL
        SELECT f."oparlKey", f.name, coalesce(to_char(f."date", 'YYYY-MM-DD'), ''),
               'name: Beschluss/Beschlüsse/Wortlaut', ''
        FROM "File" f
        -- standalone-word Beschluss names; '[üu]' char classes are
        -- unreliable in the DB locale, so 'beschlüsse' is a literal
        -- alternative (substring 'beschlu' misses the ü-spelling)
        WHERE (f.name ~* '(^|[[:punct:][:space:]])beschlu'
               OR f.name ~* 'beschlüsse' OR f.name ~* 'wortlaut')
          AND f.name !~* 'vorlag' AND f.name !~* 'ohne beschluss'
          AND f.name !~* 'entwurf'
          -- documents that only mention a GR-Beschluss are other types
          -- (Antrag/Anfrage/Stellungnahme lead-ins, optionally after 'TOP n:')
          AND f.name !~* '^(top[[:space:]]*[0-9]+[:,]?[[:space:]]*)?(antrag|anfrage|stellungnahme)'
          AND f.name !~* 'vorl[.]?nr'
    """,
}


def psql_rows(sql: str) -> list:
    env = dict(os.environ)
    env["PGPASSWORD"] = private.DB_PWD
    cmd = ["psql", "-h", private.DB_HOST, "-U", private.DB_USER,
           "-d", private.DB_NAME, "-AtF", "\t", "-c", sql]
    out = subprocess.run(cmd, env=env, capture_output=True, text=True, check=True)
    return [line.split("\t") for line in out.stdout.splitlines() if "\t" in line]


def md_path(key: str) -> str:
    return os.path.join(KO_DIR, f"{int(key):08d}.md")


def main() -> None:
    os.makedirs(TMP, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    picked = []  # (md_filename, oparlKey, doc_type, file_name, papertype, ai_result, date, md_bytes)
    used_keys = set()

    for doc_type in ["antrag", "beschlussvorlage", "beschluss"]:
        rows = psql_rows(QUERIES[doc_type])
        with open(os.path.join(TMP, f"pool_{doc_type}.tsv"), "w", newline="") as fh:
            for r in rows:
                fh.write("\t".join(r) + "\n")

        # dedupe per oparlKey; first occurrence wins — for 'beschluss' the
        # UNION ALL puts consultation-sourced rows first, so those are kept
        # when a key appears in both branches
        best = {}
        for parts in rows:
            key = parts[0]
            if key not in best:
                best[key] = parts

        cands = []
        for row in best.values():
            key, name, date = row[0], row[1], row[2]
            extra, ai_result = row[3], row[4]
            p = md_path(key)
            try:
                size = os.path.getsize(p)
            except OSError:
                continue
            if size <= 0:
                continue
            with open(p, errors="replace") as fh:
                text = fh.read().lower()
            if not any(kw in text for kw in CONTENT_KEYWORDS[doc_type]):
                continue
            cands.append((key, name, date, extra, ai_result, size))

        cands.sort(key=lambda c: hashlib.md5(c[0].encode()).hexdigest())
        per_name, per_family = {}, {}
        chosen = []

        def family(name: str) -> str:
            import re
            s = re.sub(r"^[0-9][0-9 :._:-]*", "", name.lower())
            s = re.sub(r"^top[\s_.]*[0-9][0-9.]*[\s_-]*", "", s)
            return s.strip() or name.lower()

        for key, name, date, extra, ai_result, size in cands:
            if key in used_keys:
                continue
            if per_name.get(name, 0) >= NAME_CAP:
                continue
            fam = family(name)
            if per_family.get(fam, 0) >= FAMILY_CAP:
                continue
            chosen.append((key, name, date, extra, ai_result, size))
            per_name[name] = per_name.get(name, 0) + 1
            per_family[fam] = per_family.get(fam, 0) + 1
            if len(chosen) >= QUOTA[doc_type]:
                break

        years = sorted({(date or "")[:4] for _, _, date, _, _, _ in chosen})
        print(f"{doc_type}: pool={len(best)} with_markdown={len(cands)} "
              f"picked={len(chosen)} years={years[0]}..{years[-1]}")
        for key, name, date, extra, ai_result, size in chosen:
            picked.append((f"{int(key):08d}.md", key, doc_type, name, extra, ai_result, date, size))
            used_keys.add(key)

    manifest = os.path.join(OUT, "manifest.csv")
    with open(manifest, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["md_file", "oparlKey", "doc_type", "file_name",
                    "identification", "ai_result", "file_date", "md_bytes"])
        w.writerows(sorted(picked))

    copied = 0
    for md_file, *_ in picked:
        dst = os.path.join(OUT, md_file)
        if not os.path.exists(dst):
            shutil.copyfile(os.path.join(KO_DIR, md_file), dst)
            copied += 1

    types = {}
    for _, _, t, *_ in picked:
        types[t] = types.get(t, 0) + 1
    print(f"total picked={len(picked)} copied={copied} (rest already present) types={types}")
    print(f"manifest: {manifest}")


if __name__ == "__main__":
    main()
