# Quick run guide — S4, S5, QAQC reports

Cheat-sheet for regenerating the three deliverables. For background and
design, see the [main README](README.md). Assumes the
`NHLBI-BDC-DMC-HV` repo is already cloned (on SB and/or locally).

## The three deliverables

| Report | What it is | Runs where | All cohorts at once? |
|--------|-----------|-----------|----------------------|
| **S4** | Pre-harmonized phv counts + n per variable/cohort | **Local** | Yes (one run) |
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

## S4 — pre-harmonized phv report (local)

One command, all cohorts. Reads source sheets + `valid-phvs/` lists; no
enclave needed.

> **Why local?** Today's script gets both the phv list *and* the `n`
> counts from the Google Sheets (`var_report…stats.stat.n`), so nothing
> from SB is required. The proposed move to source S4 from the transform
> specs (see `transform_assessment/SPEC_SOURCED_S4_DESIGN.md`) would change
> this: phv list from specs, and `n` measured by `extract_source` **on
> SB**. That version is not built yet — the steps below are the current,
> sheet-based script.

```bash
cd transform_assessment
uv run python preharmonized_qaqc_report.py        # writes preharmonized_qaqc_report.csv
```

Inspect a single variable/cohort's phv set (e.g. to check a count):

```bash
uv run python preharmonized_qaqc_report.py --debug-variable "AST SGOT" --debug-cohort FHS
```

Paste the CSV (minus header) into the Table S4 template per
`transform_assessment/README.md`.

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
