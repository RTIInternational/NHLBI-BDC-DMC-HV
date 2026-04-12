# HV-Lint Data Maintenance Guide

This document covers the full lifecycle of dbGaP source data used by HV-Lint:
fetching from NCBI, building indexes, onboarding new cohorts, and version
upgrades. Fetched source XML and intermediate files stay local (git-ignored),
but the compressed indexes (`*.json.gz`) are committed so CI and local runs
work offline without NCBI access.

---

## Quick Reference

```bash
# First-time setup (after cloning):
pip install pyyaml requests-cache
python hv-lint/update_data.py

# Refresh one cohort after version bump:
python hv-lint/update_data.py --cohort aric --force

# Rebuild indexes only (no network):
python hv-lint/update_data.py --build-only

# Preview what would be downloaded:
python hv-lint/update_data.py --dry-run
```

---

## Architecture

```
hv-lint/
  cohorts.yaml          # Version pins (study_id + data_version per cohort)
  update_data.py        # Single entry point: fetch + build
  _http.py              # HTTP caching layer (requires requests-cache)
  build_phv_index.py    # Basic PHV-to-PHT index builder
  build_phv_detail_index.py  # Extended PHV detail index builder
  dbgap-cache/          # ALL intermediate data (.gitignore'd)
    .gitignore          # Blocks all XML, JSON, SQLite from commits
    aric/               # Source XML per cohort
      variables.xml     # CGI variable index (~5-30 MB)
      pheno_variable_summaries/
        *.data_dict.xml # FTP data dictionaries (~100-400 files per cohort)
    aric.json.gz        # Compressed PHV-to-PHT index (~50-300 KB)
    aric_detail.json.gz # Compressed PHV detail index (~100-800 KB)
    aric_visit.json     # Visit metadata extract (~10-50 KB)
    .http-cache.sqlite  # Transparent HTTP response cache
```

### Data Flow

```
NCBI CGI endpoint              --> variables.xml
NCBI FTP mirror                 --> *.data_dict.xml
                                        |
                    +-------------------+-------------------+
                    |                   |                   |
            build_phv_index    build_phv_detail_index   visit extract
                    |                   |                   |
                *.json.gz         *_detail.json.gz    *_visit.json
                    |                   |                   |
            Phase 3 (3.1-3.5)   Phase 3 (3.9-3.16)   Phase 5 (5.7-5.8)
```

### What Gets Downloaded

| Source | Size Per Cohort | Total (~11 cohorts) | Used By |
|--------|----------------|---------------------|---------|
| `variables.xml` (CGI) | 5-30 MB | ~150 MB | Basic index |
| `*.data_dict.xml` (FTP) | 10-200 MB | ~1 GB | Detail index, visit cache |
| **Total source** | | **~1.1 GB** | |
| **Compressed indexes** | 200 KB-1 MB | **~4 MB** | Lint phases 3, 5 |

The ~1.1 GB of source XML is cached locally and never re-downloaded
unless `--force` is used. The compressed indexes are ~4 MB total.

---

## Common Tasks

### First-Time Setup

After cloning the HV repo:

```bash
# Install dependencies (one-time)
pip install pyyaml requests-cache

# Fetch all data and build indexes (~30 min first time, network-dependent)
python hv-lint/update_data.py
```

This populates `hv-lint/dbgap-cache/` with everything needed to run all
lint phases. Subsequent runs skip already-cached files.

### Version Bump (Cohort Upgrade)

When dbGaP releases a new version for a cohort:

1. **Update `cohorts.yaml`**:
   ```yaml
   aric:
     study_id: phs000280
     data_version: v9.p3   # <-- was v8.p2
   ```

2. **Re-fetch and rebuild**:
   ```bash
   python hv-lint/update_data.py --cohort aric --force
   ```

3. **Run lint** to detect any PHV/PHT breakage from the version change:
   ```bash
   python hv-lint/phase-3/run_phase3.py --cohort ARIC --cache-dir hv-lint/dbgap-cache
   ```

What changes between versions:
- PHTs may be added or removed
- PHVs may be re-accessiond or retired
- Coded value lists may change
- New tables may appear

### New Cohort Onboarding

1. **Add entry to `cohorts.yaml`**:
   ```yaml
   newcohort:
     study_id: phs999999
     data_version: v1.p1
     display_name: "New Cohort Study Name"
   ```

2. **Fetch and build**:
   ```bash
   python hv-lint/update_data.py --cohort newcohort
   ```

3. **Verify**:
   ```bash
   python hv-lint/update_data.py --summary
   ```

That's it. The new cohort's indexes are ready for lint.

### Rebuild Without Network

If source XMLs are already present (e.g., copied from another machine):

```bash
python hv-lint/update_data.py --build-only
```

This skips all NCBI requests and just rebuilds the compressed indexes
from whatever XML is in `dbgap-cache/`.

---

## CLI Reference

```
python hv-lint/update_data.py [OPTIONS]

Options:
  --cohort KEY     Process single cohort (default: all)
  --fetch-only     Only download from NCBI, skip index building
  --build-only     Only rebuild indexes from existing XML (no network)
  --force          Re-download even if files are cached
  --dry-run        Preview what would be done
  --list           Show configured cohorts and exit
  --summary        Show cache contents and exit
```

---

## Dependencies

| Package | Required For | Install |
|---------|-------------|---------|
| `pyyaml` | Reading `cohorts.yaml` | `pip install pyyaml` |
| `requests-cache` | Fetching from NCBI (`--fetch` mode) | `pip install requests-cache` |

**Note**: `requests-cache` is only needed for fetch operations. If you
receive pre-built indexes (e.g., from a colleague), you can run all lint
phases with just `pyyaml` + stdlib.

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| Phase 3: "PHT not found" errors | Stale indexes | `python hv-lint/update_data.py --build-only` |
| Phase 3: many missing PHVs | Wrong dbGaP version in cohorts.yaml | Verify version pin matches YAML files |
| Fetch timeout / 503 | NCBI rate limiting | Wait and retry; cached files aren't re-fetched |
| `ImportError: requests-cache` | Missing optional dep | `pip install requests-cache` |
| "No data_dict.xml files found" | Study has no FTP summaries | Normal for some small studies; basic index still works |
