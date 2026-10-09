# CLAUDE.md

## Maintenance

### Known-issues lists
`validate_ingest_yamls.py` and the root `check_phv_dedup.py` each have a `KNOWN_ISSUES` dict that suppresses CI failures for tracked problems: path → reason, and PHV → issue number (empty today; a stale entry fails). HV-Lint keeps its own list in `hv-lint/known_issues.yaml` (one entry per finding, with its issue and status) and its WARNINGs in `hv-lint/warning_baseline.json`; CI fails on an entry or row that no longer matches. After a PR that fixes tracked problems, `HVLINT_PRUNE=1 python hv-lint/run_all.py --cohort all` removes exactly the fixed entries (hv-lint/HV-Lint-Reference.md, A7).
