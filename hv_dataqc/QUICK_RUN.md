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
   git checkout <your working branch>
   git merge origin/main                        # latest specs + code
   git merge origin/thessen-s5-fixes            # pending S5 spec fixes (still unmerged to main)
   # resolve conflicts if any, then commit the merge
   ```

   > Merge both before re-running, or the reports reflect stale specs.
   > `thessen-s5-fixes` is mostly spirometry/method_type fixes and is still
   > unmerged to `main` as of 2026-08-12. Don't start from
   > `feature/S5-report-20260603` — it is a stale, unmerged feature branch
   > kept only for its granular history.

2. **SB session setup** (only for steps that run in the enclave — S5, QAQC
   extract):

   ```bash
   source hv_dataqc/sb_scripts/setup.sh         # uv + deps, once per session
   ```

## S4 — pre-harmonized phv report (SB enclave)

Spec-sourced: phv list/count from the transform specs, source `N` measured
by `extract_source` from the raw TSVs. No spreadsheets. One command, all
cohorts.

`run_s4_report.sh` takes no arguments and is idempotent: it fetches dbGaP
caches, extracts any cohort that lacks an extract, reuses the ones that have
one, and builds the table. Extraction is the **default** — you only need a flag
to opt out of it or to force it.

```bash
hv_dataqc/sb_scripts/run_s4_report.sh                 # the normal run
hv_dataqc/sb_scripts/run_s4_report.sh --list-cohorts  # cohorts with spec dirs
hv_dataqc/sb_scripts/run_s4_report.sh --no-extract    # build from existing extracts only
hv_dataqc/sb_scripts/run_s4_report.sh --force         # re-extract every cohort (slow)
# subset: --cohorts FHS,MESA
```

Output: `/sbgenomics/workspace/S4-output-files/s4_report_<ts>.csv` (+ a
`latest_s4_report.csv` symlink). Paste it (minus header) into the Table S4
template.

Inspect one variable's resolved phvs + per-phv N:

```bash
uv run python -m transform_assessment.spec_phv_report \
    --specs-root priority_variables_transform \
    --cohort FHS \
    --source-json <QC-output-files/FHS/latest_source/fhs_source_*.json> \
    --cache-dir hv_dataqc/local_output/dbgap-cache/fhs \
    --debug-variable ast_sgot
```

> **The new counts will be higher than the published Table S4. That is
> correct, not a bug.** The old pipeline filtered phvs two ways — hand-made
> `valid-phvs/` allow lists and an "out of scope" column in the curator
> spreadsheets — and both were retired on 2026-08-12 as unmaintainable. The
> published table is a frozen historical artifact; reproducing it is not a
> goal. An *increase* needs no explanation; a *decrease* is worth a look.
> Background: [`../transform_assessment/README.md`](../transform_assessment/README.md).
>
> The old sheet-based `preharmonized_qaqc_report.py` (a symlink into
> `transform_assessment/s4_count_investigation/old_pipeline/`) is **evidence,
> not a cross-check**. Don't run it — it reads live Google Sheets that have
> since moved.

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
