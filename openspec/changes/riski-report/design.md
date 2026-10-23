## Context

The RISKI project currently contains a PostgreSQL migration report (`docs/pg_report.md`) generated manually after the `postgres-migration` change. Stakeholders need a cohesive, automatically‑generated report that aggregates the migration status, schema mapping, and any open issues across the project.

## Goals / Non-Goals

**Goals:**
- Produce a Markdown report (`docs/pg_report.md`) that combines:
  - OParl → PostgreSQL schema overview
  - Current status of the `postgres-migration` OpenSpec change (tasks completed, pending)
  - High‑level next steps and open issues for the RISKI project
- The report generation should be repeatable (scripted) and runnable locally or in CI.

**Non-Goals:**
- The report will not replace detailed unit‑test documentation.
- It will not automatically pull data from the live database; it aggregates existing artifacts.

## Decisions

1. **Source of truth** – Use existing OpenSpec artifacts (`postgres-migration` proposal, design, tasks) and the generated `docs/pg_report.md` as inputs. No additional data extraction from the database is required.
2. **Implementation** – Provide a small Python script (`src/generate_report.py`) that reads the relevant files, concatenates sections, and writes `docs/pg_report.md`.
3. **CI Integration** – Add a step in the CI workflow to run the script after each successful build, ensuring the report stays current.
4. **Formatting** – Stick to GitHub‑flavored Markdown with clear headings for each section; keep the file under 5 KB for readability.

## Risks / Trade-offs

- **Risk:** The report may become stale if the script is not executed after changes. *Mitigation:* Enforce the script execution in the CI pipeline and add a pre‑commit hook that warns when `pg_report.md` is out‑of‑date.
- **Risk:** Manual edits to `pg_report.md` could be overwritten. *Mitigation:* Treat the file as generated artifact only; document that manual changes will be lost.

## Migration Plan

1. Add `src/generate_report.py` with the aggregation logic.
2. Update `README.md` with usage instructions (`python generate_report.py`).
3. Add CI step (`run: python generate_report.py`).
4. Verify the generated `docs/pg_report.md` matches expectations.

## Open Questions

- Should the script also pull the latest `git log` summary for the project?
- Is a separate `docs` sub‑directory required for generated reports, or should they live directly under `docs/`?
