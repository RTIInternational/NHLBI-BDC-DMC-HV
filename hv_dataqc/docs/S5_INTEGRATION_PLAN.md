# Table S5 report — integration plan

Port the S5 paste-ready report from the personal `sb_for_bdc` repo into
`hv_dataqc/`, reusing the existing harmonized extractor instead of
re-globbing TSVs. Branch: `feature/S5-report-20260603`.

Plan last refreshed 2026-06-08 against PR #570 head (`f55d8d70`).

## Background

"S5" is the [Data Harmonization Supplementary Data - Table
S5](https://docs.google.com/spreadsheets/d/1PDaX266_H0haa0aabMYQ6UNtEKT5-ClMarP0FvNntN8/edit?gid=1605543644#gid=1605543644)
spreadsheet. The current generator lives at
`Sigfried/sb_for_bdc:harmonized_qaqc/generate_qaqc_data.py` and was never
finished — partly due to var-naming drift, partly because it hardcodes
the old `/sbgenomics/project-files/DataRun_*` layout (the active path
is now `/sbgenomics/project-files/_QC_STAGING/DataRun_*`).

## What the existing S5 script does

1. Globs `DataRun_*/DMC_*/<study>_BDCHM/mapped-data/MeasurementObservation.tsv`
   across all cohorts under one hardcoded DataRun. Loads all rows into
   a single combined DataFrame.
2. Resolves `observation_type` → `var_label` via `harmonized_vars.tsv`
   using three forms: `OMOP:<n>`, `OBA:<id>`, and bare uppercase
   `var_name` (with a `BARE_NAME_ALIASES` exception map for the few
   bare codes that don't match `var_name.upper()`).
3. Groups the combined-cohort DataFrame by `var_label` and emits exact
   stats: n, nulls_missing, mean, median, min, max, sd, participants.
4. Formats for the spreadsheet using `TABLE_S5_LABELS` (hardcoded row
   order, ~100 labels) and `S5_LABEL_ALIASES` (spreadsheet label →
   TSV `var_label` for cases where the two drift, mostly casing).
5. Writes `table_s5_paste_<ts>.tsv` (paste into cell B3 of the
   template) plus an `s5_coverage_<ts>.tsv` that reports which S5
   labels matched / aliased / were missing from the data.

## What's in this repo already (2026-06-08 check)

- `hv_dataqc/extract_harmonized/extract_harmonized_summaries.py`
  loads `MeasurementObservation.tsv` per-cohort and emits per-`observation_type`
  summaries with full stats (n, mean, sd, min, max, plus p5/p25/p50/p75/p95).
- The output JSON's variable shape already includes a `bdc_label` field.
  It's populated for demographics (`sex`, `race`, `ethnicity`) but `None`
  for all measurement entries — the field exists, just isn't filled in
  yet for the measurement path.
- `hv_dataqc/extract_harmonized/config/` directory exists (currently
  holds `harmonized_extract.yaml`). Natural place for a label map.
- `transform_assessment/harmonized_qaqc/harmonized_vars.tsv` exists
  but `transform_assessment/preharmonized_qaqc_report.py` doesn't read
  it (the `transform_assessment/` work runs against pre-harmonized data,
  different concern).
- `hv_dataqc/sb_scripts/run_extracts.sh` still does DataRun discovery
  inline with `_${COHORT}_`-anchored globs against `_QC_STAGING/DataRun_*`
  and supports `--datarun NAME` / `--list-dataruns`. Not yet refactored
  into a sourced helper.

## Key technical wrinkle: cross-cohort median

The original `sb_for_bdc` script computes an exact cross-cohort median by
loading every cohort's row-level data into one big DataFrame and calling
`groupby('label').median()`. The aggregate per-cohort JSONs the extractor
emits don't have row-level data, so reproducing that exact median
post-extraction isn't possible.

**However**: within a single cohort, each measurement's `observation_type`
CURIE is unique (ARIC's "Albumin in blood" appears under one CURIE, FHS's
under possibly a different CURIE). So the per-cohort median is *already*
exact-from-row-data for the cohort. The pooling step is across cohorts.

Three options for cross-cohort pooling:

- **Median-of-medians weighted by n.** Strictly an approximation but
  often within 1-2% of the row-level median in practice. Easiest.
- **n-weighted interpolation from percentile distributions.** The
  extractor already emits p5/p25/p50/p75/p95. Use those to build an
  approximate pooled CDF and interpolate the 50th percentile. More
  principled; still approximate.
- **Re-load row data at S5-aggregation time.** Exact, but requires
  either (a) running inside the SB enclave, or (b) doing it during
  the harmonized extract pass and shipping a per-`bdc_label`
  summary section alongside the existing per-`observation_type` one.

Cross-cohort medians for these variables are already statistically
suspect (different assays, different units in some cases, different
populations across cohorts). The Table S5 "row-level exact" median is
"exact" only in the sense that it's the median of the concatenated rows,
not in any deeper sense. **The approximation gap is probably smaller
than the cross-cohort comparability gap that already exists.**

## Plan

The lightest-touch approach exploits two things the previous plan
hadn't noticed:

1. **`bdc_label` is already a field** in the harmonized JSON's variable
   shape — it's just not populated for measurements.
2. **Cross-cohort pooling can be approximate** via percentile interpolation
   without sacrificing meaningful precision.

So the refactor is smaller than originally scoped: populate the existing
`bdc_label` field, then aggregate post-hoc.

### Steps

1. **Move `harmonized_vars.tsv` to `hv_dataqc/extract_harmonized/config/`.**
   It's S5-aggregation input. Drop the copy at
   `transform_assessment/harmonized_qaqc/` (the `transform_assessment/`
   work doesn't use it).

2. **Add label-map loading to `extract_harmonized_summaries.py`.**
   New optional `--label-map PATH` argument. When supplied:
   - Load `harmonized_vars.tsv` and build the OMOP/OBA/bare → `var_label`
     lookup (the `get_var_label_lookup()` logic from `sb_for_bdc`).
   - In `process_measurements()`, populate `summary["bdc_label"]` from
     the label-map lookup keyed by the row's `observation_type`.
   - In `process_observations()` likewise, since some entries route
     through the Observation entity instead of MeasurementObservation.
   No new JSON section; just fills in an existing `None`.

3. **New `hv_dataqc/extract_harmonized/table_s5/` package** with:
   - `s5_report.py` — takes one or more harmonized-extract JSONs
     (one per cohort), groups variables by `bdc_label` across cohorts,
     emits pooled stats and writes `table_s5_paste.tsv` + `s5_coverage.tsv`.
   - The S5 spec lives here: `TABLE_S5_LABELS`, `S5_LABEL_ALIASES`,
     `BARE_NAME_ALIASES`.
   - Pooled median via percentile-interpolation (documented as
     approximate in the coverage report).

4. **New `hv_dataqc/sb_scripts/run_s5_report.sh`** wrapper. Mirrors
   `run_extracts.sh`'s shape: discover the DataRun, iterate cohorts
   present in it, invoke `extract_harmonized_summaries.py --label-map`
   for each, then invoke `s5_report.py` over all the produced JSONs.

5. **Archive `sb_for_bdc`** once ported. The useful commits are recent
   and easy to cite by hash; `git subtree add` is probably overkill.

6. **Defer naming-mismatch debugging.** Once it runs against the
   current `_QC_STAGING/DataRun_*` layout, the `s5_coverage.tsv` will
   identify exactly which S5 labels still need an alias entry, a
   `BARE_NAME_ALIASES` entry, a `TABLE_S5_LABELS` correction, or a
   real upstream fix.

### Optional: extract discovery helper

The previous plan called for extracting `run_extracts.sh`'s discovery
logic into a sourced helper used by both `run_extracts.sh` and
`run_s5_report.sh`. **Defer this** — it's a refactor in its own right
and the duplication is small (~20 lines). Better to ship S5 first and
extract the helper if/when the duplication actually causes pain.

## Things to keep verbatim from `sb_for_bdc`

- `get_var_label_lookup()` logic (OMOP/OBA/bare-name → label,
  including `BARE_NAME_ALIASES`) — moves into the extractor's
  `--label-map` path.
- `S5_LABEL_ALIASES`, `TABLE_S5_LABELS`, `format_for_sheets()` — these
  *are* the S5 spec; they move into `table_s5/s5_report.py`.
- The coverage report — surfaces the naming-mismatch issues so they
  can be debugged.

## Things to drop

- `sb_for_bdc/setup` — already superseded by
  `hv_dataqc/sb_scripts/setup.sh` + `vi_defaults.sh`.
- `sb_for_bdc/harmonized_qaqc/generate_qaqc_data.py`'s row-level
  loader — replaced by the existing extractor with `--label-map`.
- The hardcoded `BASE_DIR = '/sbgenomics/project-files/DataRun_...'`
  — `run_s5_report.sh` handles discovery.

## Open questions

- Should `S5_LABEL_ALIASES` and `TABLE_S5_LABELS` live in a TSV/CSV
  config rather than as Python constants? Probably yes — they're
  spreadsheet-shape data, not code. Defer until the first iteration
  runs cleanly and we know what shape the data is settling into.
- Same question for `BARE_NAME_ALIASES` — currently 2 entries; if more
  turn up, fold into `harmonized_vars.tsv` as an extra "bare alias"
  column rather than a separate map.
- Once cross-cohort medians are produced (approximate), worth comparing
  one or two against the original `sb_for_bdc` script's row-level
  medians to confirm the approximation gap is small. If it's
  consistently within ~2%, ship as-is and note in the coverage report.
  If it's larger, revisit the row-level path.
