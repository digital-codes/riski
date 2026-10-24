# Design

## Context

`ResultSummarizer.summarize(result, force)` builds the prompt from
`result["top_files"]`, prefers `teaser` over `content` per file
(`_file_text`), and appends the refused-documents note plus the provenance
footer. `/summarize` (apiServer) returns early when a summary already exists
and never passes `force`. The frontend (`App.vue` → `SummaryCard.vue`) stores
the summary string; the search result already carries `top_files` with
`oparlKey`/`name`/`fileName` but no download URL. `File.downloadurl` exists
in the DB.

## Goals / Non-Goals

**Goals:**
- One backend path for "run the summarizer" with three axes: context layer
  (teaser/full), file selection (exclusions), and force.
- Structured per-file metadata (name, download URL, refused) both embedded in
  the summary markdown and returned as data for interactive UI.
- Minimal frontend change: SummaryCard gains a refine button and a toggle
  list; App.vue wires the re-run.

**Non-Goals:**
- No persistence of exclusions beyond the session store.
- No background job queue — the refine call blocks its request like the
  initial one (the frontend keeps the old summary visible with a spinner on
  the button).
- No changes to the map view gating (summary_refused semantics stay).
- No per-file "summarize this single file" view.

## Decisions

**D1 — Request shape.** `SummarizeRequest` gains
`refine: bool = False` and `exclude: list[str] = []` (oparlKeys). `refine`
implies `force` (re-run even though a summary exists) and full content.
Exclusions are merged into the session result (`result["summary_excluded"]`)
so subsequent calls honour them without resending.

**D2 — Context mode.** `ResultSummarizer.summarize(result, force=False,
use_full_content=False)`: `_file_text(oparl_key, full=False)` returns
`content` first when `full` (capped at `full_content_chars`, default
4 × `_MAX_CONTENT_CHARS`, overridable per request later if needed), teaser
first otherwise. The prompt header names the layer
("Dokumente (Teaser):" vs "Dokumente (Volltext):") so the model and the
provenance trail show what was summarised.

**D3 — Exclusion filter.** Excluded oparlKeys are removed from the working
`top_files` copy before the prompt is built; the original `top_files` stays
intact in the session. `summary_refused` is parsed from the new run's output
over the included set (indices shift accordingly — parsing already maps
Datei numbers back to the passed list).

**D4 — File list placement.** A new `_file_list_section(files, refused)`
renders markdown lines `- Datei <N>: [<name>](<downloadUrl>) — berücksichtigt|nicht berücksichtigt`
before `_footer(response)`. The section is built from the INCLUDED working
set plus refused flags (refused ⊆ included set of the current run; files the
user excluded do not appear in the LLM prompt, but the interactive list the
frontend renders comes from the structured response, not the markdown).

**D5 — Structured response.** `/summarize` returns
`{"summary": str, "files": [{oparlKey, name, fileName, downloadUrl, refused,
excluded}]}`. `refused` from the last run; `excluded` from the session's
exclusion set (refused files are auto-added to it on the first refine —
spec: refused start excluded). downloadUrl comes from the File row (fetched
in the same query as teaser/content — extend `_file_text`'s SELECT).

**D6 — Frontend.** `SummaryCard.vue` gains: a "Verfeinern" button (visible
when a summary exists) emitting `refine`, and a collapsible file list
rendered from the `files` prop with include/exclude toggles emitting
`toggle-file`. `App.vue` keeps the current summary visible while refining,
shows a button spinner, calls `/summarize {sessionId, refine: true,
exclude}` on either action, and replaces `summary`/`files` on response.
First-load list: refused files pre-excluded (D5).

**D7 — Concurrency guard.** The API ignores a second concurrent refine for
the same session (returns the in-flight state) — the session store gains a
simple `summarizing` flag; the frontend disables the button anyway.

## Risks / Trade-offs

- [Full content can exceed model context] → per-file cap (D2) plus the
  existing top_k answer-set size keep the prompt bounded; worst case the
  model truncates a file's context.
- [Blocking request during refine] → accepted (same as initial pass);
  previous summary stays visible.
- [Exclusion state in session only] → a new search resets it (consistent
  with summary reset today).
- [Refused-parse fragility] → unchanged mechanism, already spec'd as
  best-effort; the toggle list degrades to "no pre-exclusions".

## Migration Plan

1. Backend: context mode + exclusions + file list + structured response
   (unit tests).
2. API: request model + session state (unit/integration test).
3. Frontend: SummaryCard + App.vue wiring.
4. README "Summaries" section note.

Rollback: revert — no schema/data changes.

## Open Questions

(none)
