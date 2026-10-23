## 1. Setup

- [ ] 1.1 Add a Python script `src/generate_report.py` that reads the relevant OpenSpec artifacts and writes `docs/pg_report.md`
- [ ] 1.2 Ensure the script is executable and listed in the project `README.md`

## 2. Implementation

- [ ] 2.1 Implement reading of `docs/pg_report.md` (existing migration report) and prepend it with a generated header containing the RISKI Report overview
- [ ] 2.2 Parse `openspec/changes/postgres-migration/tasks.md` to extract completed and pending tasks, and include a summary section in the generated report
- [ ] 2.3 Optionally read an `OPEN_ISSUES.md` file (if present) and append its contents as the "Open Issues" section

## 3. CI Integration

- [ ] 3.1 Add a step in the CI workflow to run `python src/generate_report.py` after successful builds
- [ ] 3.2 Verify that `docs/pg_report.md` is updated in the CI artifacts

## 4. Documentation

- [ ] 4.1 Update `README.md` with instructions on how to run the report generation script locally
- [ ] 4.2 Document the purpose of the RISKI report and where to find the generated file