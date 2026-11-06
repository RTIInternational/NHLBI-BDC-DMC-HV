# HV-DataQC: Source vs. Harmonized Output Comparison Suite

Validates that the BDC dm-bip harmonized output faithfully preserves the
source dbGaP data — checking N preservation, distribution matching, clinical
ranges, visit structure, and cross-variable consistency.

> **Just need to regenerate a report?** See **[QUICK_RUN.md](QUICK_RUN.md)**
> for the easiest steps to produce the S4, S5, and QAQC reports. The rest
> of this README is background and architecture.

---

## Components

| Folder | Script | Purpose | Runs where |
|--------|--------|---------|-----------|
| `extract_source/` | `extract_source_summaries.py` | Summarize raw dbGaP TSVs | **Inside enclave** |
| `extract_harmonized/` | `extract_harmonized_summaries.py` | Summarize dm-bip harmonized output | **Inside enclave** |
| `compare/` | `python -m hv_dataqc.compare` | Compare both summaries; run checks C1-C12 | **Inside enclave** |
| `cache_fetcher/` | `fetch_dbgap_cache.py` | Download dbGaP data dictionaries for PHV resolution | **Inside enclave** |
| `sb_scripts/` | Runner/analysis scripts | Ad-hoc scripts for enclave work | **Inside enclave** |
| `sb_output/` | *(gitignored)* | Output produced on Seven Bridges | **Inside enclave** |
| `local_output/` | *(gitignored)* | dbGaP cache (`dbgap-cache/`) | **Inside enclave** |

---

## Design Principles

1. **Source extract is source-first, with optional YAML-guided joint counts.**
  It summarizes every column in the raw TSV regardless of what the current HV
  YAMLs reference. This makes the core source summaries stable and reusable.
  When `--yaml-dir` is supplied, the extractor also pre-scans transform YAMLs
  for multi-PHV `case()` conditions and emits aggregate pairwise crosstabs in
  `joint_distributions_by_pht`. Re-run the source extract when the dbGaP study
  version changes, a new PHT table is added, or YAML changes introduce/modify
  multi-PHV conditions that need exact comparison.

2. **Harmonized extract is also YAML-agnostic.** It reads entity TSVs produced
   by dm-bip and groups by `observation_type` / `condition_concept` columns —
   concept codes that are already baked into the pipeline output. Visit UUIDs
   are resolved to human-readable labels from `Visit.tsv` at extraction time.

3. **Comparison uses live YAMLs.** The crosswalk (source PHV → harmonized concept
   code) is built fresh from the current HV YAML checkout on every compare run.
   Re-run `python -m hv_dataqc.compare` as often as needed as YAMLs evolve,
   without re-running the extracts.

4. **YAML transforms and dbGaP cache are both required.** `--yaml-dir` (HV
   transform YAMLs) and `--cache-dir` (dbGaP data-dict XMLs) are mandatory
   arguments to `python -m hv_dataqc.compare`. Use `cache_fetcher/fetch_dbgap_cache.py`
   to build the cache (deps: `requests`, `pyyaml`; one command per cohort,
   idempotent on re-runs).

---

## Workflow

To run Tables S4 and S5, follow [QUICK_RUN.md](QUICK_RUN.md). QAQC runs per
cohort inside dm-bip's harmonization workflow
([`hv-dataqc-cohort.sh`](https://github.com/linkml/dm-bip/blob/main/scripts/workflow/hv-dataqc-cohort.sh)).

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

### Full manual workflow

See [sb_scripts/README.md](sb_scripts/README.md) for the extract commands and
[compare/README.md](compare/README.md) for running the comparison directly.

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
  "joint_distributions_by_pht": { "pht002239": { "phv...+phv...": { ... } } },
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

`joint_distributions_by_pht` is present only when the source extractor was run
with `--yaml-dir`. It enables exact aggregate comparisons for two-PHV `case()`
conditions without exporting row-level data. When the field is absent or a
condition needs more than a two-way crosstab, compare reports the affected
check as unsupported/SKIP rather than guessing.

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
- Two-PHV `case()` routing can be compared exactly when the source JSON includes
  `joint_distributions_by_pht`, produced by running the source extractor with
  `--yaml-dir`. Unsupported multi-PHV cases are reported as unsupported/SKIP.

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

---

## Requirements

```
pandas >= 1.3
pyyaml >= 5.4
requests >= 2.25  # cache_fetcher only
```

Install: `uv sync` (from repo root)
