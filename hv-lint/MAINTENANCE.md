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

Version pins (study_id + data_version per cohort) are read from the hv_dataqc
cache-fetcher manifests
(`hv_dataqc/cache_fetcher/manifests/_manifest-<cohort>.yaml`, the
`current_version` block) — the single source of truth shared with the hv_dataqc
compare pipeline, so the two tools can never pin different dbGaP versions.

```
hv-lint/
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

1. **Bump the cohort manifest** (`hv_dataqc/cache_fetcher/manifests/_manifest-aric.yaml`):
   ```yaml
   current_version:
     study_id: "phs000280"
     data_version: "v9.p3"   # <-- was v8.p2
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
- PHVs may be re-accessioned or retired
- Coded value lists may change
- New tables may appear

### New Cohort Onboarding

1. **Add a cohort manifest** (`hv_dataqc/cache_fetcher/manifests/_manifest-newcohort.yaml`):
   ```yaml
   current_version:
     study_id: "phs999999"
     data_version: "v1.p1"
     study_name: "New Cohort Study Name"
   ```

2. **Fetch and build**:
   ```bash
   python hv-lint/update_data.py --cohort newcohort
   ```

3. **Verify** -- both that the indexes exist and that they record which study version
   they were built from:
   ```bash
   python hv-lint/update_data.py --summary
   python -c "import sys; sys.path.insert(0,'hv-lint'); import _cohorts;        print(_cohorts.study_label('hv-lint/dbgap-cache', 'newcohort'))"
   ```
   A `PROVENANCE UNKNOWN` answer means the cache exists but cannot say which dbGaP release it
   holds -- rebuild it with `build_phv_index.py` rather than shipping it.

That's it. **No code change is needed to onboard a cohort**, and that is new as of
2026-09-10 -- this section previously ended here and was wrong. Onboarding also required
editing four hard-coded `COHORT_TO_CACHE_KEY` dicts (three in `phase-3/`, one in `phase-5/`)
and two `COHORTS` lists enforced as argparse `choices=` in `phase-1/run_yamllint.py` and
`phase-1/check_quoting_rules.py`. Measured against a cohort staged as `LTRC-ingest`:

| symptom | cause |
|---|---|
| Phase 1 FAILED having read no files | the two `choices=` lists rejected `--cohort LTRC`, exit 2 |
| `ERROR: No dbGaP indexes found. Run build_phv_index.py.` | the cohort was absent from the dicts; the cache was irrelevant |
| `--cohort all` scanned 0 files and exited 0 | `all` expanded to the fixed ten-cohort list |

The cohort set is now derived: `_cohorts.ingest_cohorts()` reads `*-ingest/` directories and
`_cohorts.discover_cache_keys()` reads `dbgap-cache/*.json.gz`, which is how the CI workflow
already picked the cohort (it `sed`s the name out of the PR's changed paths and consults no
list).

### Cache artifacts are named by STUDY RELEASE, not by cohort

As of 2026-09-10 the three cache artifacts for a study are keyed `<phs######>.<v#>`:

```
phs000280.v8.json.gz          PHV -> PHT index          (Phase 3, Phase 5 checks 5.3 + 5.4)
phs000280.v8_detail.json.gz   + name/type/desc/codes    (Phase 3, check 5.8)
```

There is deliberately **no visit cache**. `update_data.py` step 5 can generate one by
regex-matching variable names and table descriptions, and Phase 5 checks 5.5 and 5.7 used to
read it -- both were removed on 2026-09-10, because a regex inference cannot be the oracle a
transform spec is validated against. Check 5.3 now reads its PHT set from the PHV index, which
is a fact. `data/visit-cache/` is not an authoritative alternative: it holds the same generated
regex output in a different shape.

Why: a cohort-named file (`aric.json.gz`) cannot hold two releases of one study, and its name
records nothing about which release it is. Keyed by release, `phs000280.v8` and `phs000280.v9`
sit side by side, a version bump is additive rather than destructive, and a migration can lint
the old release against the new one. Caches built before the rename still resolve.

**Which release a cohort uses is its DECLARED release** -- `current_version` in
`hv_dataqc/cache_fetcher/manifests/_manifest-<cohort>.yaml`, the file a version bump already
edits. So bumping a version means: edit that file, build the new release's artifacts, done; the
old ones stay for comparison.

Build both from any dbGaP staging tree (each discovers cohorts by globbing the source):

```bash
python hv-lint/build_phv_index.py        --source-cache <dbgap staging dir>
python hv-lint/build_phv_detail_index.py --source-cache <dbgap staging dir>
```

A staging directory may carry the release in its name (`aric-v8`, `fhs-v33`); the suffix is
stripped when recording the cohort, so `aric-v8` records `cohort: ARIC`.

### The release check is MANDATORY

Phase 3 always verifies that the cache it loaded is the cohort's declared release. There is no
"lint against whatever is present" mode, because that is how a superseded release goes
unnoticed:

| situation | result |
|---|---|
| cache release == declared release | passes, and prints `[phs000280.v8, built ...]` |
| cache release != declared release | **hard failure**, naming both |
| cache records no release | **hard failure** -- an unpinnable cache cannot be checked |
| cohort declares no release | **hard failure** -- add `_manifest-<cohort>.yaml` or pass `--expect-study` |

`--expect-study phs000280.v9` overrides the declaration for a one-off (a migration dry-run, say).
A bare accession (`phs000280`) accepts any version of that study.

### Cache provenance -- which dbGaP version am I linting against?

`dbgap-cache/manifest.json` records, per cache key, the `phs######` accession and `v#` version
the builders actually parsed out of the `*.data_dict.xml` filenames, plus PHV/PHT counts. Phase 3
prints it on every load:

```
  Loaded LTRC: 1,577 PHVs across 27 PHTs [phs001662.v4]
```

This matters because a cache payload is a bare `{phv: pht}` mapping with no metadata, and Phase 3
validates spec PHVs against it: a cache built from a superseded release reports PHVs that exist
only in the newer release as absent, which is indistinguishable from a real mapping error.

To enforce it rather than merely report it:

```bash
python hv-lint/run_all.py --cohort LTRC --expect-study phs001662.v4     # Phase 3
python hv-lint/phase-3/run_phase3.py --cohort CHS --expect-study phs000287
```

A bare accession ignores the version. **A cache with no recorded provenance FAILS the pin
rather than passing it** -- an unpinnable cache is the case the pin exists to catch.

**ARIC is why this exists.** The cache committed before the rename held 34,155 PHVs and was a
strict SUPERSET of both `phs000280.v8` (27,987) and `phs000280.v9` (32,388) -- 0 PHVs absent from
it, every shared PHV on the identical PHT -- so it was a union of releases that no single
`data_version` describes, while `_manifest-aric.yaml` declared `v8.p2`. Rebuilt at the declared
v8, Phase 3 surfaces **16 error-level cross-reference findings that the union cache had masked**:
of the 1,341 PHVs ARIC's specs reference, 14 are outside v8. Measured 2026-09-10; note that v9 is
missing *more* of them (32), so the specs really are v8-aligned.

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
| `pyyaml` | Reading cohort manifests | `pip install pyyaml` |
| `requests-cache` | Fetching from NCBI (`--fetch` mode) | `pip install requests-cache` |

**Note**: `requests-cache` is only needed for fetch operations. If you
receive pre-built indexes (e.g., from a colleague), you can run all lint
phases with just `pyyaml` + stdlib.

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| Phase 3: "PHT not found" errors | Stale indexes | `python hv-lint/update_data.py --build-only` |
| Phase 3: many missing PHVs | Wrong dbGaP version in cohort manifest | Verify version pin matches YAML files |
| Fetch timeout / 503 | NCBI rate limiting | Wait and retry; cached files aren't re-fetched |
| `ImportError: requests-cache` | Missing optional dep | `pip install requests-cache` |
| "No data_dict.xml files found" | Study has no FTP summaries | Normal for some small studies; basic index still works |
