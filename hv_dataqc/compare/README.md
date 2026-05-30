# compare — Source vs. Harmonized Comparison Engine

Compares aggregate JSON summaries produced by `extract_source/` and
`extract_harmonized/`. Runs checks C1-C12 and produces a Markdown + JSON
report. Runs **outside the enclave** — no participant-level data.

Re-run as often as needed as HV YAMLs evolve. Only the two JSON summary files
and the current HV YAML checkout are required.

---

## Quick start

Use the convenience wrapper in `local_scripts/` which auto-finds the latest
JSONs, YAML dir, and cache:

```bash
cd ../local_scripts/
./compare.sh COPDGene
```

## Usage (direct)

```bash
# Standard run
python -m hv_dataqc.compare \
    --source  spiromics_source_20250101T120000.json \
    --harmonized  spiromics_harmonized_20250101T120000.json \
    --cohort  SPIROMICS \
    --yaml-dir /path/to/HV-repo/priority_variables_transform/SPIROMICS-ingest/ \
    --cache-dir /path/to/data/dbgap-cache/spiromics/

# Custom tolerances and output paths
python -m hv_dataqc.compare \
    --source  src.json --harmonized out.json --cohort CARDIA \
    --yaml-dir /HV/priority_variables_transform/CARDIA-ingest/ \
    --cache-dir /dbgap-cache/cardia/ \
    --thresholds config/thresholds.yaml \
    --report cardia_compare_report.md \
    --json-report cardia_compare_results.json
```

### All Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--source JSON` | Yes | Source summary JSON from extract_source_summaries.py |
| `--harmonized JSON` | Yes | Harmonized summary JSON from extract_harmonized_summaries.py |
| `--cohort NAME` | Yes | Cohort name (used in report title) |
| `--yaml-dir DIR` | Yes | HV transform directory for YAML-driven crosswalk (e.g. `priority_variables_transform/SPIROMICS-ingest/`). |
| `--cache-dir DIR` | Yes | dbGaP cache dir for PHV→name and PHV→PHT resolution (`pheno_variable_summaries/*.data_dict.xml`). Build the cache with `../cache_fetcher/fetch_dbgap_cache.py`. |
| `--clinical-ranges YAML` | No | Clinical ranges file (default: `config/clinical_ranges.yaml`) |
| `--thresholds YAML` | No | Statistical thresholds file (default: `config/thresholds.yaml`) |
| `--report FILE` | No | Markdown report output path (default: `<cohort>_comparison_report.md`) |
| `--json-report FILE` | No | JSON report output path (default: `<cohort>_comparison_results.json`) |

When run via `local_scripts/compare.sh`, the wrapper sets `--report` /
`--json-report` to a fresh `local_output/archive/<commit>_<ts>/` directory
and updates both stable and timestamped `local_output/<cohort>_comparison_*`
symlinks afterward. The Markdown report header records the source JSON file,
harmonized JSON file, and YAML directory used. See the top-level
[README](../README.md#output-layout) for the archive layout.

---

## Check Descriptions

| Check | Name | What It Tests |
|-------|------|---------------|
| `CROSSWALK` | Crosswalk Resolution Failures | Per-variable FAIL when a source-column lookup is ambiguous across PHTs and the YAML/cache can't pin it. Emitted before C1–C12 and causes those checks to skip for the affected harmonized variable. |
| C1 | N Preservation | Harmonized participant count matches the mapped source participant universe |
| C2 | N Loss Detection | Per-variable valid-N: harmonized should preserve source N |
| C3 | Missing Value Accounting | Missing rate stable between source and harmonized |
| C4 | Mean Preservation | Continuous mean within tolerance (no unit conversion) |
| C5 | Mean After Conversion | Mean correct after known unit conversion factor |
| C6 | SD Preservation | Standard deviation within tolerance |
| C7 | Categorical Distribution | Category percentages match after YAML-derived expected-summary normalization, including status aliases such as `N`/`Y` → `ABSENT`/`PRESENT` when the transform emits status values. |
| C8 | Visit N Distribution | Per-visit row counts preserved when source and harmonized labels share a namespace. For table-based cohorts (CHS, ARIC, etc.) where source TSVs have no visit column, source visit counts are synthesized from `total_rows_by_pht` + `visit.yaml` mappings. Incompatible label namespaces are WARN/unsupported rather than hard FAIL because aggregate totals cannot prove visit semantics. PHTs absent from `visit.yaml` (not being harmonized) are reported as a single INFO item. |
| C9 | Clinical Range | Harmonized min/max within clinically plausible bounds |
| C10 | Cross-Variable Consistency | SBP > DBP, FEV1 < FVC, etc. |
| C11 | Variable Type Consistency | Source/harmonized agree on continuous vs categorical; numeric-coded dbGaP `encoded` sources compared to continuous outputs are INFO rather than WARN. |
| C12 | Value Mapping Coverage | YAML value_mappings cover dbGaP coded values and observed source categories, distinguishing semantic codes from null/sentinel codes. |

Notes:

- C1 uses `participant_denominators.mapped_source_union_n` when present. This is
    the exact union of participants across source PHTs referenced by YAML
    mappings, computed inside the enclave by the source extractor. The
    all-source union and largest single-PHT count remain in the detail payload
    as context because source extracts often include roster/admin tables that
    are not the harmonization denominator. Older source JSON files without the
    exact mapped union fall back to mapped-PHT max as a WARN-level diagnostic.
- C2-C7 compare actual harmonized summaries against a YAML-derived expected
    harmonized summary when transform semantics are available. This expected
    summary may account for value_mappings, concept routing, case() expressions,
    scalar unit conversion, static YAML values, and pooled multi-block transforms.
- Two-PHV `case()` value-routing expressions can be compared exactly when the
    source JSON includes `joint_distributions_by_pht`, produced by running
    `extract_source_summaries.py --yaml-dir <transform-dir>`. Missing crosstabs
    or conditions involving more than two PHVs remain unsupported/SKIP rather
    than guessed.
- C7 translates YAML `value_mappings` before comparison and aggregates many source
    categories that map to the same harmonized category. For status-like transforms,
    pooled expected summaries normalize raw source aliases (`N`, `Y`, `T`, etc.) into
    harmonized status labels when the YAML entries indicate the output is status-valued.
- C7 report sections include a full source/harmonized distribution table for every
    compared categorical variable.
- C8 synthesizes source visit counts for table-based cohorts by combining
    `total_rows_by_pht` from the source summary with the `populated_from` + `name`
    slot in `visit.yaml`. PHTs present in the source data but absent from `visit.yaml`
    (i.e., tables not being harmonized in the current scope) are not FAILed — they
    appear as a single INFO entry listing the PHT IDs and total row count. When source
    and harmonized visit labels have no overlap, the result is WARN/unsupported instead
    of FAIL because aggregate label totals cannot establish harmonization correctness.
- C9 annotates violations with `[out+src]`, `[out only]`, or `[src only]` when the
    source summary contains min/max values for the same range.
- C10 is driven by `_cross_variable_rules` in `clinical_ranges.yaml`. Simple
    two-variable mean comparisons run automatically; formula rules are emitted as
    `SKIP` with an explanatory message until implemented.
- C11 demotes categorical→continuous mismatches to INFO when the source is encoded as
    categorical but all observed non-sentinel values are numeric. This prevents ARIC-like
    dbGaP type metadata from drowning out real comparison findings.
- C12 is deliberately separate from before/after preservation checks. An unmapped
    source code can be expected transform behavior, but still indicate a YAML
    completeness issue that should be reviewed. Null/sentinel-only gaps are INFO;
    missing semantic source codes remain WARN.

### Status Codes

| Status | Meaning |
|--------|---------|
| `PASS` | Check passed |
| `WARN` | Minor deviation (within warning threshold) |
| `FAIL` | Significant discrepancy requiring investigation |
| `SKIP` | Check could not run (missing data, not applicable) |
| `INFO` | Informational — e.g., unmatched variables |

Exit code is `1` if any `FAIL` result exists, `0` otherwise.

---

## Variable Crosswalk Strategy

The engine builds a source-to-harmonized crosswalk by parsing the HV
transform YAMLs (every match comes from YAML; the older PHV-ID and
name-match fallback strategies were removed in Phase B):

1. For each `class_derivations` block, extracts:
   - `observation_type` / `condition_concept` value → harmonized entity key
   - `populated_from` PHV accessions → resolved to variable names via dbGaP cache
   - `value_mappings` → used for C7 categorical translation
   - simple `case()` expressions in value slots → used to derive expected
     categorical comparison distributions for split blocks without YAML changes
   - `method_type` → retained as crosswalk metadata when present

2. For `MeasurementObservationSet` (blood pressure, spirometry), recurses into
   `observations.object_derivations` to extract each nested `MeasurementObservation`.

3. Builds an expected post-transform source summary for each harmonized key.
   Exact aggregate expectations are produced for direct copies, value_mappings,
   concept routing where the concept and value PHVs align, simple case()
    routing, two-PHV case() routing with precomputed joint distributions, scalar
    arithmetic, common `unit_conversion` blocks, static YAML values, and pooled
    independent blocks. Cases that require unavailable row-level joint counts are
    marked as partial/unsupported rather than guessed.

4. Groups multiple YAML blocks that emit the same harmonized key and compares
   against the pooled or YAML-derived source basis instead of a single first PHV.

5. Source-column lookups go through the dbGaP cache's PHV→PHT map first.
   If that fails and the column name exists in multiple source PHTs, the
   match records an `_ambiguous_columns` diagnostic and the orchestrator
   emits a `CROSSWALK` FAIL for that harmonized variable rather than
   silently picking one PHT's stats.

---

## Clinical Ranges Config

`config/clinical_ranges.yaml` defines plausible and red-flag ranges per
variable, matched by OBA/OMOP concept code or common variable name. Edit
this file to add new variables or adjust thresholds.

The compare script validates this config at startup and prints non-fatal
warnings for malformed ranges or cross-variable rules that reference undefined
range names.

### `config/thresholds.yaml`

Controls the PASS / WARN / FAIL boundaries for statistical checks C1-C8.
All thresholds are calibrated against COPDGene real-world data where
cleanly-mapped variables have exact (d=0.000) preservation.

| Check | Threshold param | Default | Old default | Effect |
|-------|----------------|---------|-------------|--------|
| C1 | `fail_pct` | 1.0% | 5.0% | Tighter FAIL on participant loss |
| C2 | `pass_pct` / `warn_pct` | 0.5% / 2.0% | 1% / 5% | WARN and FAIL at lower N drift |
| C3 | `pass_pp` / `warn_pp` | 0.5 pp / 3.0 pp | 1 pp / 5 pp | Earlier flag on missing rate change |
| C4 | `pass_rel` / `warn_rel` | 0.1% / 1.0% | 1% / 5% | Pre-BD FEV1 drift now FAIL not WARN |
| C5 | `pass_rel` | 0.1% | 1% | Tighter conversion check |
| C6 | `pass_rel` / `warn_rel` | 0.2% / 1.0% | 2% / 10% | Tighter SD check |
| C7 | `pass_pct` | 0.5 pp | 2.0 pp | Tighter categorical shift |
| C8 | `warn_lo_ratio` / `warn_hi_ratio` | 0.95 / 1.05 | 0.90 / 1.10 | Tighter visit count band |

Override any check's thresholds with `--thresholds /path/to/custom.yaml`.
The custom file only needs to include the keys you want to override.

Format:
```yaml
c4:
    pass_rel: 0.001
    warn_rel: 0.01
c7:
    pass_pct: 0.5
```

---

## Requirements

```
pandas >= 1.3
pyyaml >= 5.4
```
