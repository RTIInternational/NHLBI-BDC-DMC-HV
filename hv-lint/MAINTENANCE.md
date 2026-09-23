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
  dbgap-cache/          # Source XML (ignored) + built indexes (committed)
    .gitignore          # Blocks source XML and the HTTP cache; indexes are committed
    aric/               # Source XML per staging directory
      variables.xml     # CGI variable index (~5-30 MB)
      pheno_variable_summaries/
        *.data_dict.xml # FTP data dictionaries (~100-400 files per cohort)
    phs000280.v8.json.gz        # Compressed PHV-to-PHT index (~50-300 KB)
    phs000280.v8_detail.json.gz # Compressed PHV detail index (~100-800 KB)
    manifest.json               # Which release each cache key holds -- committed
    .http-cache.sqlite  # Transparent HTTP response cache
```

### Data Flow

```
NCBI FTP mirror                 --> *.data_dict.xml    (the only source; carries the release)
                                        |
                    +-------------------+-------------------+
                    |                                       |
            build_phv_index.build_one         build_phv_detail_index.build_one
                    |                                       |
            phs######.v#.json.gz              phs######.v#_detail.json.gz
                    |                                       |
        Phase 3 (3.1-3.5), Phase 5 (5.3/5.4)   Phase 3 (3.9-3.16), Phase 5 (5.8)

                          both also write --> manifest.json
```

`update_data.py` calls those same two `build_one` functions rather than building its own
indexes, so the fetch path and a direct builder invocation cannot diverge. The release in each
artifact's name comes from the `phs######.v#.` prefix on the data dictionaries, never from the
version a cohort declares -- provenance taken from a declaration would make the release check
confirm itself.

**Only inputs carrying that prefix contribute.** A dictionary from another release, or one
whose name cannot be attributed to any release, is skipped with a note. The CGI `variables.xml`
bulk index was merged as a supplement until 2026-09-23 and is no longer fetched or read: it
carries no release, so a copy left from an earlier one silently turned the artifact into a
union of releases. Dropping it changed nothing -- verified byte-for-byte against the staging
layout every committed cache was built from, which contains no `variables.xml` at all.

There is no visit extract. It guessed visit metadata by regex into `*_visit.json`; checks 5.5
and 5.7 were its only readers and both were removed.

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
   holds, and the mandatory release check will reject it. As of 2026-09-23 `update_data.py`
   records provenance itself, so this is now a genuine anomaly rather than the expected
   outcome: until then it built its own unprovenanced, cohort-named indexes and this step was
   a workaround telling you to rebuild with `build_phv_index.py`. If you see it now, the data
   dictionaries in `dbgap-cache/<cohort>/` do not name one `phs######.v#` release -- check what
   was fetched rather than rebuilding.

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
edits. So bumping a version means: edit that file, build the new release's artifacts, done.

#### Which releases to keep -- the one you are migrating TO, not the one you came FROM

Only the declared release is reachable. `candidate_keys` puts it first, and the manifest-match
fallback is skipped when a study has two entries, so a non-declared release is not even a
candidate. `--expect-study` does not reach one either: it overrides the EXPECTATION, not which
cache is loaded, so `--cohort FHS --expect-study phs000007.v33` loads v35 and then fails for not
being v33. Verified 2026-09-22.

So a second release earns its ~0.5-2 MB only across a migration window:

| keep | because |
|---|---|
| the release the cohort is migrating **to**, staged ahead of the bump | it becomes reachable the moment `_manifest-<cohort>.yaml` is edited, with no rebuild |
| the release it came **from**, until the bump has landed and been reviewed | it is what a diff compares against |

After that, **drop the old one**: reaching it again would mean un-declaring the new release,
which is a rollback, not a plan. `phs000007.v33` was kept past this point and removed on
2026-09-22 -- 1,871 KB, 74% of the directory's growth, and no invocation could load it, FHS
having declared v35. `phs000280.v9` is the other side of the same rule: ARIC declares v8, so v9
is unreachable today and is kept because the v8 -> v9 migration is next.

The `_detail` index is where the weight is -- name, type, description and coded values per PHV,
against a bare `{phv: pht}` map. FHS v33 was 204 KB of index and 1,667 KB of detail, a ratio that
holds across the fleet. A retained release that will only ever be cross-referenced, never
value-checked, does not need its detail companion.

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
`data_version` describes, while `_manifest-aric.yaml` declared `v8.p2`. A union cache cannot fail
a cross-reference check: every PHV of every release is in it, so it reports what the specs
reference rather than what the declared release contains, which is the one thing check 3.1 exists
to distinguish.

Measured 2026-09-22 against the 100 ARIC spec files, which reference 1,327 distinct PHVs:

| index | PHVs the specs reference that are absent from it |
|---|---:|
| `phs000280.v8` -- the declared release | **0** |
| `phs000280.v9` | **32** |

So the specs are exactly v8-aligned, and linting them against v9 would report 32 mapping errors
that are not errors. That asymmetry is the whole argument for pinning the release.

*(Claim correction, 2026-09-22: this paragraph said the v8 rebuild "surfaces 16 error-level
cross-reference findings that the union cache had masked", 14 of them PHVs outside v8, measured
2026-09-10. That was true when measured and is no longer: those PHVs were corrected on `main`,
and the merge at `9a500249` brought the fixes onto this branch. ARIC now passes the enforced
Phase 3 gate at v8 with 26 INFO findings and zero at error level. The 32-PHV v9 figure is
unchanged, and the structural argument above never depended on the count.)*

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
