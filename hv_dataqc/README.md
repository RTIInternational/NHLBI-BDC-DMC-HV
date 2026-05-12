# HV-DataQC: Source vs. Harmonized Output Comparison Suite

Validates that the BDC dm-bip harmonized output faithfully preserves the
source dbGaP data — checking N preservation, distribution matching, clinical
ranges, visit structure, and cross-variable consistency.

---

## Components

| Folder | Script | Purpose | Runs where |
|--------|--------|---------|-----------|
| `extract_source/` | `extract_source_summaries.py` | Summarize raw dbGaP TSVs | **Inside enclave** |
| `extract_harmonized/` | `extract_harmonized_summaries.py` | Summarize dm-bip harmonized output | **Inside enclave** |
| `compare/` | `python -m hv_dataqc.compare` | Compare both summaries; run checks C1-C12 | Outside enclave |
| `cache_fetcher/` | `fetch_dbgap_cache.py` | Download dbGaP data dictionaries for PHV resolution | Outside enclave |
| `sb_scripts/` | Runner/analysis scripts | Ad-hoc scripts for enclave work | **Inside enclave** |
| `local_scripts/` | `compare.sh`, `fetch_cache.sh` | Convenience wrappers (auto-resolve paths) | Outside enclave |
| `sb_output/` | *(gitignored)* | Output produced on Seven Bridges | **Inside enclave** |
| `local_output/` | *(gitignored)* | Downloaded JSONs, dbgap-cache, comparison reports | Outside enclave |

---

## Design Principles

1. **Source extract is YAML-agnostic.** It summarizes every column in the raw
   TSV regardless of what the current HV YAMLs reference. This makes it a
   stable, reusable artifact — it never needs to be re-run when YAMLs change,
   only when the source study version changes or a new PHT table is added.

2. **Harmonized extract is also YAML-agnostic.** It reads entity TSVs produced
   by dm-bip and groups by `observation_type` / `condition_concept` columns —
   concept codes that are already baked into the pipeline output. Visit UUIDs
   are resolved to human-readable labels from `Visit.tsv` at extraction time.

3. **Comparison uses live YAMLs.** The crosswalk (source PHV → harmonized concept
   code) is built fresh from the current HV YAML checkout on every compare run.
   Re-run `python -m hv_dataqc.compare` as often as needed as YAMLs evolve — no
   re-entry to the enclave required.

4. **YAML transforms and dbGaP cache are both required.** `--yaml-dir` (HV
   transform YAMLs) and `--cache-dir` (dbGaP data-dict XMLs) are mandatory
   arguments to `python -m hv_dataqc.compare`. Use `cache_fetcher/fetch_dbgap_cache.py`
   to build the cache (deps: `requests`, `pyyaml`; one command per cohort,
   idempotent on re-runs).

5. **Reports are archived by commit + timestamp.** Every `compare.sh` run writes
   its outputs into `local_output/archive/<git-short-commit>_<UTC-timestamp>/`,
   and updates symlinks at `local_output/<cohort>_comparison_{report.md,results.json}`
   to point at the latest archive entry. Old reports are never overwritten.
   Each archive entry also contains a `manifest.json` recording the source
   and harmonized JSONs used and the git commit at the time of the run.

---

## Workflow

### Quick start (using convenience scripts)

**On Seven Bridges** (run extracts).
These instructions assume a fresh Data Studio session (no persisted state).
SB studio sessions often crash after a timeout and lose the workspace, so
"start from scratch" is the realistic default; if the repo is already
present and on the branch you want, you can skip the clone/checkout
steps.

```bash
# 1. Clone the repo if it's not already here (run in whatever dir you
#    want the clone to live under — /sbgenomics/workspace/ is typical).
[ -d NHLBI-BDC-DMC-HV ] || git clone https://github.com/RTIInternational/NHLBI-BDC-DMC-HV.git

# 2. Enter the repo and sync with origin.
cd NHLBI-BDC-DMC-HV
git fetch origin

# 3. Check out the branch you want. The active QC-refactor work lives on
#    a `refactor/phase-*` branch stacked on `feature/hv-dataqc-20260423`
#    (the umbrella). To list the most recently updated remotes:
#       git for-each-ref --sort=-committerdate \
#           --format='%(refname:short)  %(committerdate:short)  %(subject)' \
#           refs/remotes/origin/ | head -10
#    Then `git checkout <name>` using the short name (git creates a local
#    tracking branch automatically). Pick the latest `refactor/phase-*`
#    branch if you want the in-flight QC refactor; pick the umbrella if
#    you want everything that's merged so far. Example:
git checkout refactor/phase-b-json-cleanup   # most recent QC-refactor branch
git pull --ff-only

# 4. Install deps (once per session — uv isn't preinstalled on SB).
source hv_dataqc/sb_scripts/setup.sh

# 5. Optional: set vi as editor (SB doesn't persist dotfiles).
source hv_dataqc/sb_scripts/vi_defaults.sh

# 6. Optional sanity checks before kicking off a long extract:
uv run python -m pytest hv_dataqc/tests/ -q   # unit + integration tests
uv run python -m hv_dataqc.compare --help     # compare CLI sanity check

# 7. Run extracts for a cohort. Auto-discovers the latest DataRun and
#    packages a downloadable tgz when both extracts succeed.
hv_dataqc/sb_scripts/run_extracts.sh COPDGene
```

Download the resulting `dataqc_<cohort>_output.tgz` from `/sbgenomics/workspace/`
via JupyterLab's file browser (right-click → Download).

**Locally** (fetch cache, unpack, compare):
```bash
git pull
cd hv_dataqc/local_scripts/
./fetch_cache.sh copdgene                  # once per cohort
./unpack.sh                                # unpacks ~/Downloads/dataqc_*_output.tgz
./compare.sh COPDGene                      # auto-finds latest JSONs, YAML dir, cache
```

### Output layout

**Extract outputs** (on SB, in `/sbgenomics/workspace/QC-output-files/<COHORT>/`):
both extract scripts write into timestamped subdirectories with `latest_*`
symlinks, so you never need to type timestamps.

```
QC-output-files/<COHORT>/
  source_<ts>/copdgene_source_<ts>.json
  harmonized_<ts>/copdgene_harmonized_<ts>.json
  latest_source -> source_<ts>
  latest_harmonized -> harmonized_<ts>
```

**Comparison outputs** (locally, in `hv_dataqc/local_output/`): each
`compare.sh` run writes into a fresh archive directory and updates
top-level symlinks. Old reports are never overwritten.

```
hv_dataqc/local_output/
  <cohort>_comparison_report.md           -> archive/<commit>_<ts>/...
  <cohort>_comparison_results.json        -> archive/<commit>_<ts>/...
  archive/
    <git-commit>_<YYYYMMDDTHHMMSSZ>/
      copdgene_comparison_report.md
      copdgene_comparison_results.json
      manifest.json
```

### Full manual workflow

See [local_scripts/README.md](local_scripts/README.md) and
[sb_scripts/README.md](sb_scripts/README.md) for details on running
individual steps or without the convenience wrappers.

---

## Exported JSON Format

Both `extract_source_summaries.py` and `extract_harmonized_summaries.py` write
**aggregate-only** JSON — no individual participant rows.

### Source extract

Source variables are stored nested by PHT (no top-level flat dict — that was
removed in Phase B because column-name collisions across PHTs were ambiguous):

```json
{
  "metadata": { "source": "raw_dbgap", "cohort": "SPIROMICS", ... },
  "total_participants": 2973,
  "total_rows": 11892,
  "rows_per_visit": { "VISIT_1": 2973, ... },
  "participants_by_pht": { "pht002239": 2973, ... },
  "total_rows_by_pht": { "pht002239": 8919, ... },
  "variables_by_pht": {
    "pht002239": {
      "age_baseline": {
        "type": "continuous",
        "n_valid": 7757, "n_missing": 135,
        "mean": 59.1, "sd": 8.9, ...
      },
      "sex": {
        "type": "categorical",
        "distribution": { "1": {"n": 5000, "pct": 42.1}, ... }
      }
    },
    "pht016246": { ... }
  }
}
```

`compare.py` builds `variables_by_name[col][pht]` at startup for column-name
lookups; when a YAML's PHV maps to a column that exists in multiple PHTs and
the PHV→PHT route can't disambiguate, the comparison emits a per-variable
`CROSSWALK` FAIL rather than silently picking one PHT.

### Harmonized extract

```json
{
  "metadata": { "source": "bdc_dmbip", "cohort": "SPIROMICS", ... },
  "total_participants": 2973,
  "total_rows": 11892,
  "rows_per_visit": { "VISIT_1": 2973, ... },
  "variables": {
    "measurement_OBA:VT0001253": {
      "type": "continuous",
      "n_valid": 7757, ...
    },
    "condition_MONDO:0004981": {
      "type": "categorical",
      "distribution": { "PRESENT": {"n": 500, "pct": 6.5}, ... }
    }
  }
}
```

---

## Checks

| Check | What it validates |
|-------|------------------|
| `CROSSWALK` | Source-column lookups that the YAML/cache couldn't resolve to a single PHT (FAIL) |
| C1 | Total participant N preserved |
| C2 | Per-variable valid N (no silent row loss) |
| C3 | Missing value rates stable |
| C4 | Continuous mean preserved (same unit) |
| C5 | Continuous mean preserved after unit conversion |
| C6 | Standard deviation preserved |
| C7 | Categorical distributions match (with value_mappings translation) |
| C8 | Visit N distribution preserved |
| C9 | Harmonized values within clinical plausible range |
| C10 | Cross-variable consistency (SBP > DBP, FEV1 < FVC) |
| C11 | Source/harmonized type consistency (continuous vs categorical) |
| C12 | YAML value_mappings cover dbGaP coded values |

Recent comparison report details:

- C7 includes full source/harmonized categorical distribution tables, with many-to-one
  YAML value mappings aggregated before percentages are compared.
- C9 annotates range findings as `[out+src]`, `[out only]`, or `[src only]` when
  source min/max context is available.
- C10 reads `_cross_variable_rules` from `clinical_ranges.yaml`; simple two-variable
  mean comparisons run automatically, while formula rules are reported as `SKIP`
  until implemented.

---

## Tests

The test suite covers crosswalk construction, individual check functions,
YAML parsing edge cases, and end-to-end integration scenarios for the
ambiguous-PHT detection path. All tests are pure Python — no external
fixtures or live data.

```bash
# All tests, terse output
uv run python -m pytest hv_dataqc/tests/ -q

# Single test class
uv run python -m pytest hv_dataqc/tests/test_compare_source_harmonized.py::AmbiguousColumnIntegrationTests -v

# Single test
uv run python -m pytest \
    hv_dataqc/tests/test_compare_source_harmonized.py::C1NPreservationTests::test_c1_pass_exact_match_no_pht \
    -v
```

### Regression check (local only)

`hv_dataqc/tests/regression_check.sh` compares the current Markdown +
JSON comparison-report output for COPDGene, ARIC, and HCHS against
pre-captured baselines (in `/tmp/phase_a_baseline/` by default). Used
during refactor work to verify that mechanical changes preserve output
behavior; not part of the regular test suite.

```bash
# Capture baselines from the current code state.
hv_dataqc/tests/regression_check.sh capture

# Diff current output against the captured baselines.
hv_dataqc/tests/regression_check.sh check
```

Requires `compare.sh` to be runnable for all three cohorts, which means
the source/harmonized JSONs must be present under `local_output/` and
the dbGaP cache must be fetched for each cohort. Doesn't run on Seven
Bridges (different paths, no harmonized download).

---

## Requirements

```
pandas >= 1.3
pyyaml >= 5.4
requests >= 2.25  # cache_fetcher only
```

Install: `uv sync` (from repo root)
