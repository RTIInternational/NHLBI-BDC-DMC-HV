# Quick run guide — S4, S5, QAQC reports

Cheat-sheet for regenerating the three deliverables. For background and
design, see the [main README](README.md). Assumes the
`NHLBI-BDC-DMC-HV` repo is already cloned (on SB and/or locally).

## The three deliverables

| Report | What it is | Runs where | All cohorts at once? |
|--------|-----------|-----------|----------------------|
| **S4** | Pre-harmonized phv counts + source N per variable/cohort | **SB enclave** | Yes (one run) |
| **S5** | Harmonized summary stats (mean/min/max/…) per variable, pooled across cohorts | **SB enclave** | Yes (one run) |
| **QAQC** | Source-vs-harmonized comparison, checks C1–C12 | SB extract + **local** compare | **No — one cohort at a time** |

(If something else belongs here, add it — these are the three current
publication/QC outputs.)

## Common first steps

1. **Be on the right branch with the latest specs merged in.** S4/S5/QAQC
   all read the transform specs in `priority_variables_transform/`, so the
   branch must contain the current `main` plus any pending spec fixes.

   ```bash
   git fetch origin
   git checkout feature/S5-report-20260603      # or your working branch
   git merge origin/main                        # latest specs + code
   git merge origin/thessen-s5-fixes            # pending S5 spec fixes
   # resolve conflicts if any, then commit the merge
   ```

   > As of this writing the working branch is **behind** main (2 commits)
   > and does **not** contain `thessen-s5-fixes` (33 commits). Both must be
   > merged and committed before re-running, or the reports reflect stale
   > specs.

2. **SB session setup** (only for steps that run in the enclave — S5, QAQC
   extract):

   ```bash
   source hv_dataqc/sb_scripts/setup.sh         # uv + deps, once per session
   ```

## S4 — pre-harmonized phv report (SB enclave)

Spec-sourced: phv list/count from the transform specs, source `N` measured
by `extract_source` from the raw TSVs. No spreadsheets. One command, all
cohorts.

`run_s4_report.sh` **reuses** each cohort's existing `latest_source` extract
(under `QC-output-files/<COHORT>/`). Pass `--extract` to (re-)run the source
extract first — slow, reads raw source TSVs.

```bash
hv_dataqc/sb_scripts/run_s4_report.sh --list-cohorts          # cohorts with spec dirs
hv_dataqc/sb_scripts/run_s4_report.sh --extract               # full run: extract + build
hv_dataqc/sb_scripts/run_s4_report.sh                         # reuse existing extracts
# subset: --cohorts FHS,MESA
```

Output: `/sbgenomics/workspace/S4-output-files/s4_report_<ts>.csv` (+ a
`latest_s4_report.csv` symlink). Paste it (minus header) into the Table S4
template.

Inspect one variable's resolved phvs + per-phv N:

```bash
uv run python transform_assessment/spec_phv_report.py \
    --specs-root priority_variables_transform \
    --cohort FHS \
    --source-json <QC-output-files/FHS/latest_source/fhs_source_*.json> \
    --cache-dir hv_dataqc/local_output/dbgap-cache/fhs \
    --debug-variable ast_sgot
```

> The old sheet-based `preharmonized_qaqc_report.py` is retained for now as
> a cross-check; it will be removed once the spec-sourced report is
> validated against it. See `transform_assessment/SPEC_SOURCED_S4_DESIGN.md`.

## S5 — harmonized summary table (SB enclave)

One command, all cohorts in the chosen DataRun. Reads existing dm-bip
harmonized output — it does **not** re-run dm-bip.

```bash
hv_dataqc/sb_scripts/run_s5_report.sh --list-dataruns       # pick the newest
hv_dataqc/sb_scripts/run_s5_report.sh --datarun DataRun_20260624_1200
# or, for the latest automatically:
hv_dataqc/sb_scripts/run_s5_report.sh
# subset: --cohorts ARIC,MESA
```

Output tgz lands in `/sbgenomics/workspace/`; download via the JupyterLab
file browser. The `table_s5_paste_*.tsv` inside is the paste-ready table.

> **S5 reflects the DataRun's harmonized data, not the specs directly.**
> If a value looks wrong, confirm the DataRun was harmonized *after* the
> relevant spec fix. Picking an older DataRun reproduces old values.

## QAQC — source-vs-harmonized comparison (per cohort)

No all-cohorts wrapper; run the two steps per cohort.

```bash
# 1. SB enclave: extract source + harmonized for the cohort
hv_dataqc/sb_scripts/run_extracts.sh FHS          # --datarun to pin; --list-dataruns to see
# download the output tgz, unpack locally:
cd hv_dataqc/local_scripts && ./unpack.sh         # into local_output/

# 2. Local: fetch dbGaP cache (once per cohort) then compare
./fetch_cache.sh FHS                              # skip if already cached
./compare.sh FHS                                  # runs C1–C12, writes report.md + results.json
```

Reports archive under `local_output/archive/<commit>_<timestamp>/` with
stable symlinks at `local_output/<cohort>_comparison_{report.md,results.json}`.
Repeat per cohort.
