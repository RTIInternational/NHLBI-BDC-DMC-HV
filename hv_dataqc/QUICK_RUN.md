# Quick run guide — S4, S5, QAQC reports

Cheat-sheet for regenerating the three deliverables. For background and
design, see the [main README](README.md).

## The three deliverables

| Report | What it is | Runs where | All cohorts at once? |
|--------|-----------|-----------|----------------------|
| **S4** | Pre-harmonized phv counts + source N per variable/cohort | **SB enclave** | Yes (one run) |
| **S5** | Harmonized summary stats (mean/min/max/…) per variable, pooled across cohorts | **SB enclave** | Yes (one run) |
| **QAQC** | Source-vs-harmonized comparison, checks C1–C12 | SB extract + **local** compare | **No — one cohort at a time** |

(If something else belongs here, add it — these are the three current
publication/QC outputs.)

## Getting started on SB (Data Studio)

S4, S5, and the QAQC extract all run in a Seven Bridges Data Studio terminal.

**Fresh Data Studio instance:** open a terminal, then

```bash
cd /sbgenomics/workspace
git clone https://github.com/RTIInternational/NHLBI-BDC-DMC-HV.git
cd NHLBI-BDC-DMC-HV
git checkout s4-docs-cleanup                 # temporary: until PR #749 merges, then stay on main
source hv_dataqc/sb_scripts/setup.sh
```

SB sessions can time out and lose the workspace, so expect to repeat this.

**Saved analysis, repo already cloned:** open a terminal, then

```bash
cd /sbgenomics/workspace/NHLBI-BDC-DMC-HV
git pull
source hv_dataqc/sb_scripts/setup.sh
```

`setup.sh` installs `uv` and the Python packages, and sets a sane umask and
`core.fileMode false` (SB rewrites file permissions). Source it in every new
terminal session; it ends by printing the run commands below.

Optional:

```bash
source hv_dataqc/sb_scripts/vi_defaults.sh       # vi as editor (SB doesn't persist dotfiles)
uv run python -m pytest hv_dataqc/tests/ -q      # sanity check before a long run
```

The reports read the transform specs in `priority_variables_transform/`, so
run from `main` (for now, `s4-docs-cleanup`) unless you were given a
specific branch.

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
> The old sheet-based `preharmonized_qaqc_report.py` and the whole count
> investigation were removed on 2026-08-12; recover from tag
> `pre-s4-doc-cleanup-20260812` if you ever need to audit the published table.
> Don't try to re-run that pipeline — it reads live Google Sheets that have
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

No all-cohorts wrapper; run the two steps per cohort. The extract reads raw
participant data, so it runs on SB; its output is aggregate summaries only,
which can be downloaded. The compare runs on your own machine because it
reads the transform specs fresh on every run, so you can re-run it as specs
change without going back into SB.

**1. On SB:** extract source + harmonized for the cohort, then download the
`dataqc_<cohort>_output.tgz` from `/sbgenomics/workspace/` (JupyterLab file
browser, right-click → Download).

```bash
hv_dataqc/sb_scripts/run_extracts.sh FHS          # --datarun to pin; --list-dataruns to see
```

**2. Locally:** in your own clone of the repo, on the same branch as on SB
(needs `uv` installed):

```bash
git pull
cd hv_dataqc/local_scripts
./unpack.sh                                       # newest ~/Downloads/dataqc_*_output.tgz into local_output/
./fetch_cache.sh FHS                              # once per cohort
./compare.sh FHS                                  # runs C1–C12, writes report.md + results.json
```

Reports archive under `local_output/archive/<commit>_<timestamp>/` with
stable symlinks at `local_output/<cohort>_comparison_{report.md,results.json}`.
Repeat per cohort.
