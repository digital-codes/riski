# Design: summary-temporal-context

## Context

`top_files[].date` is already in the stage-1 payload (the UI timeline uses
it); the summarizer ignores it. The refine pass claims relevance order —
after a refine, an older decision can present as the current state.

## Decisions

1. **Header date, numbering stable**: header `Datei N (TT.MM.JJJJ): name
   (fileName)` — N from `full_index` (the user-visible list position).
   Sorting is presentational only — the numbering (and thus the "(Datei N)"
   references, the "Nicht berücksichtigt" tail and the UI's per-file list)
   stays bound to the visible list.
2. **Chronological presentation in BOTH passes**: sort the context rows by
   `date` ascending (missing dates sort last, stable sort). The refine
   pass drops the "nach Relevanz sortiert" sentence.
3. **Temporal instruction in both prompts**: "Der Kontext ist
   chronologisch sortiert (älteste zuerst); neuere Bescheide/Dokumente
   überlagern ältere — die Zusammenfassung gibt den JETZT gültigen Stand
   wieder und nennt ältere Entscheidungen nur als Historie (mit Zahl)."
4. Score/grounding blocks follow their file's row after sorting (the
   grounding blocks attach per oparlKey — unaffected by ordering).

## Risks / Trade-offs

- [The numbered list mismatch (chronological presentation vs. visible
  number) could confuse the model] → each header carries its number; the
  prompt states that numbers belong to the document list, not to the
  chrono position.

## Migration Plan

Prompt-registry + summarizer code change; no data/schema/API change.

## Open Questions

None.
