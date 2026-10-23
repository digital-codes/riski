# Design: query-guided-summary

## Context

`ResultSummarizer.summarize(result)` receives the full search result —
including `result["query"]` and all `top_files` — but currently truncates
context to `top=5` files and sends a query-blind generic summary prompt.
The interactive frontend renders the summary as an answer aid; a generic
corpus condensation doesn't serve that role.

## Goals / Non-Goals

**Goals:**
- Query-guided German summary: the model condenses the teasers *in view
  of* the user's question
- Context = all `top_files` (whatever the search fetched)
- Keep the teaser-first layering and per-file cap (size guard)
- Zero changes to callers (`search_and_summarize`, `/summarize`, App.vue)

**Non-Goals:**
- Map-reduce summarization for very large answer sets (if `top_k` grows
  to dozens, context grows linearly — revisit with chunked summarization
  only when that becomes a real usage pattern)
- Streaming, caching, or query rewriting (latter is the descoped `/ask`)

## Decisions

### 1. Context assembly: all files, teaser-first

```
for file in result["top_files"]:            # ALL — no [:top] slice
    text = teaser or content                # existing _file_text
    prompt += f"\nDatei {i}: {name} ({fileName})\nInhalt: {text[:cap]}\n"
```

- `top` constructor parameter **removed** (breaking for no caller —
  nothing else passes it).
- Per-file cap stays (`content_chars`, 5000) — with teasers it's inert,
  with content fallback it prevents runaway prompts.
- Scale guard: at `top_k=100` all-teasers ≈ 90k chars ≈ 23k tokens —
  within modern model context; if a deployment raises `top_k` beyond
  that, the cap is the lever (documented, not code).

### 2. Prompt: query in the system message, structure in the user message

```python
_SYSTEM_PROMPT = (
    "Du bist ein Assistent für das Ratsinformationssystem. Fasse die "
    "vorgelegten Dokumente auf Deutsch zusammen — in Hinblick auf die "
    "gestellte Frage. Nenne die für die Frage wichtigsten Dokumente und "
    "Ergebnisse. Bleibe unter 500 Wörtern. Keine Emojis. Antworte nur mit "
    "der Zusammenfassung."
)
user message:
    f"Frage: {result['query']}\n\n"
    "Dokumente (Teaser):\n" + <per-file blocks>
```

- Query lives in the user message (it is the request); system prompt
  carries the role/behavior. Both stable across calls.
- "Nenne die wichtigsten Dokumente" gives the model an anchor to cite
  files by name — the frontend detail panel links by document anyway.
- Missing query (defensive): fall back to the old generic prompt shape.

### 3. Robustness unchanged

Skip conditions stay: no top files, no model, dummy response, existing
summary unless `force=True`. Tests keep the FakeSession pattern, now
returning (teaser, content) tuples.

## Risks / Trade-offs

- **Token growth with large `top_k`** — linear in files; mitigated by
  teaser layering + per-file cap; documented lever.
- **Guided summaries may downweight relevant-but-off-question material**
  — acceptable: the summary's role is answering; the graph/timeline show
  the full picture.
- **Prompt is German-only** — consistent with the product language and
  the existing summarizer.

## Migration Plan

1. Rewrite prompt assembly + remove `top` in `pgResultSummarizer.py`.
2. Update unit tests (query in prompt, all-files coverage, teaser
   preference).
3. Manual check: one live `/summarize` run; summary visibly answers the
   question.
