# Table S5 integration — completed, kept for the median rationale

**The integration described by the original plan is done.** All six of its steps
landed: the `--label-map` flag, the `table_s5/` package (as
`report.py` / `aggregate.py` / `spec.py`, not the planned `s5_report.py`),
`run_s5_report.sh`, and the label-alias cleanup that left `S5_LABEL_ALIASES`
empty. The one step that was *superseded* rather than completed: the plan
proposed moving `harmonized_vars.tsv` into `config/`, but that file was deleted
outright and replaced by `config/TableS1.tsv` — see
[`../../transform_assessment/history/S1_LABEL_SOURCE_MIGRATION.md`](../../transform_assessment/history/S1_LABEL_SOURCE_MIGRATION.md).

The rest of the plan (a to-do list, a stale branch name, and status notes about
`bdc_label` being unpopulated) was deleted on 2026-08-12 rather than archived —
it described the state of code that has since shipped, and reading it would
mislead. Recover from git history or the `pre-s4-doc-cleanup-20260812` tag if
needed.

What follows is the one section still worth having: **why the pooled
cross-cohort median is an approximation.** This reasoning governs
`extract_harmonized/table_s5/aggregate.py`, which implements the first of the
three options below (n-weighted average of contributor medians).

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
  **← this is what was implemented.**
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
