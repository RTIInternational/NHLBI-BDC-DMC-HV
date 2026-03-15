# CLAUDE.md

## Maintenance

### Known-issues lists
`validate_ingest_yamls.py` and `check_phv_dedup.py` both have `KNOWN_ISSUES` that suppress CI failures for tracked problems. `validate_ingest_yamls.py` uses a dict (path → reason), while `check_phv_dedup.py` uses a set of PHV IDs. When pulling in new changes from main, check whether any known-issues entries have been resolved and can be removed.
