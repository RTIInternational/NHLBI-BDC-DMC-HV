# sb_scripts — Seven Bridges Runner Scripts

Scripts that run **inside the Seven Bridges enclave**. These wrap the core
extract scripts with the right paths for SB project file layouts.

The scripts derive the repo root from their own location, so the repo
can be cloned anywhere on SB.

## Setup

At the start of each SB session — see the top-level
[README's SB quick-start](../README.md#quick-start-using-convenience-scripts)
for the full clone/fetch/checkout walkthrough. Once the repo is in place
and you're on the branch you want:

```bash
source hv_dataqc/sb_scripts/setup.sh        # uv + project deps (once per session)
source hv_dataqc/sb_scripts/vi_defaults.sh  # optional: vi as editor + vi keybindings
```

SB doesn't persist dotfiles between sessions, so `vi_defaults.sh` exists
for that.

## Scripts

### `find_participant_gap.py`

One-off investigation script written to diagnose the 12-participant gap
found in the first COPDGene source-vs-harmonized comparison (C1 check).
It loads participant IDs from each PHT table across consent groups and
reports which tables contain participants that are missing from the
anchor table (Demographics_Baseline / pht016246).

Currently hardcoded for COPDGene's PHT tables. If a similar participant
count gap appears for another cohort, edit the `PHT_LABELS` dict at the
top of the script to map that cohort's PHT IDs and table names, and
update the `--source-root` default.

```bash
# COPDGene (default source root)
uv run python find_participant_gap.py

# Custom source root
uv run python find_participant_gap.py --source-root /sbgenomics/project-files/.../COPDGene
```

Output is aggregate-only (counts + PHT membership patterns) — safe to export.

## Running extracts on SB

### `run_extracts.sh <cohort>` (recommended)

Runs both source and harmonized extracts in one command. Auto-discovers
the latest `DataRun_*` directory containing mapped-data for the cohort.
Packages output into a tgz for download.

The source extract is run with both `--yaml-dir` (checked-out cohort transform
directory) and `--cache-dir` (the cohort's local dbGaP cache). Both are required
for `joint_distributions_by_pht` to be emitted, which enables exact aggregate
comparison of two-PHV `case()` conditions.

The script auto-resolves the cache path to
`hv_dataqc/local_output/dbgap-cache/<cohort>/` and **aborts with a clear error**
if the cache has not been fetched yet. Fetch it first with:

```bash
cd hv_dataqc/local_scripts && ./fetch_cache.sh <cohort>
```

```bash
# Use latest DataRun
./NHLBI-BDC-DMC-HV/hv_dataqc/sb_scripts/run_extracts.sh COPDGene

# Pin to a specific DataRun (ensures source + harmonized use same data)
./NHLBI-BDC-DMC-HV/hv_dataqc/sb_scripts/run_extracts.sh COPDGene --datarun DataRun_20260412_1830

# List available DataRuns for a cohort
./NHLBI-BDC-DMC-HV/hv_dataqc/sb_scripts/run_extracts.sh COPDGene --list-dataruns
```

Output goes to `/sbgenomics/workspace/QC-output-files/<COHORT>/` with
timestamped subdirectories and `latest_source`/`latest_harmonized` symlinks.
The packaged tgz lands at `/sbgenomics/workspace/dataqc_<cohort>_output.tgz`
— right-click it in the JupyterLab file browser to download.

If multiple `DataRun_*` directories contain data for the cohort and no
`--datarun` is specified, the script uses the latest one and prints a note.

### Manual extract commands

If you need more control (e.g., a custom output dir):

```bash
# Source extract
uv run python NHLBI-BDC-DMC-HV/hv_dataqc/extract_source/extract_source_summaries.py \
    --cohort COPDGene \
    --source-root /sbgenomics/project-files/PilotParentStudies_NoDRS/COPDGene \
    --output-dir /sbgenomics/workspace/QC-output-files/COPDGene \
    --yaml-dir NHLBI-BDC-DMC-HV/priority_variables_transform/COPDGene-ingest \
    --cache-dir NHLBI-BDC-DMC-HV/hv_dataqc/local_output/dbgap-cache/copdgene

# Harmonized extract (use --mapped-data-dirs to avoid OOM)
uv run python NHLBI-BDC-DMC-HV/hv_dataqc/extract_harmonized/extract_harmonized_summaries.py \
    --cohort COPDGene \
    --mapped-data-dirs \
      /sbgenomics/project-files/DataRun_.../DMC_copdgene_..._c1_.../mapped-data \
      /sbgenomics/project-files/DataRun_.../DMC_copdgene_..._c2_.../mapped-data \
    --output-dir /sbgenomics/workspace/QC-output-files/COPDGene
```

**Note:** Use `--mapped-data-dirs` instead of `--harmonized-root` for the
harmonized extract — `--harmonized-root` tries to process all cohorts and
can OOM on SB.

## Building Table S4

### `run_s4_report.sh`

Builds the pre-harmonized phv report — one row per harmonized variable, with
per-cohort phv counts and source `N`. Sourced from the transform specs in
`priority_variables_transform/` plus per-cohort source extracts; **no
spreadsheets**.

Takes no arguments and is idempotent. It fetches dbGaP caches, runs a preflight
that reports each cohort's cache/extract status, extracts any cohort that lacks
an extract, reuses the ones that have one, and builds the CSV + xlsx.

```bash
./NHLBI-BDC-DMC-HV/hv_dataqc/sb_scripts/run_s4_report.sh                 # the normal run
./NHLBI-BDC-DMC-HV/hv_dataqc/sb_scripts/run_s4_report.sh --list-cohorts  # cohorts with spec dirs
./NHLBI-BDC-DMC-HV/hv_dataqc/sb_scripts/run_s4_report.sh --no-extract    # skip extraction entirely
./NHLBI-BDC-DMC-HV/hv_dataqc/sb_scripts/run_s4_report.sh --force         # re-extract every cohort (slow)
./NHLBI-BDC-DMC-HV/hv_dataqc/sb_scripts/run_s4_report.sh --cohorts FHS,MESA
```

Extraction is the **default** — `--extract` is accepted but redundant.

Output: `/sbgenomics/workspace/S4-output-files/s4_report_<ts>.csv` plus a
`latest_s4_report.csv` symlink. Paste it (minus the header row) into the Table
S4 template.

> **Expect the counts to be higher than the published Table S4** — the old
> pipeline's two phv filters were retired on 2026-08-12 and the published table
> is now a frozen historical artifact. An increase is correct; a decrease is
> worth investigating. See
> [`../../transform_assessment/README.md`](../../transform_assessment/README.md).

A local run is not a substitute — only 5 cohorts have dbGaP caches locally.

## Building Table S5

### `run_s5_report.sh` (recommended)

Builds the paste-ready TSV for the Data Harmonization Supplementary Data –
Table S5 spreadsheet. For each cohort present in the chosen DataRun, runs
the harmonized extractor (with the shipped `bdc_label` map) to produce a
per-cohort JSON, then aggregates across cohorts by `bdc_label` and emits
the paste-ready TSV plus a coverage report.

```bash
# Use latest DataRun, all cohorts present
./NHLBI-BDC-DMC-HV/hv_dataqc/sb_scripts/run_s5_report.sh

# Pin to a specific DataRun
./NHLBI-BDC-DMC-HV/hv_dataqc/sb_scripts/run_s5_report.sh \
    --datarun DataRun_20260412_1830

# Restrict to a subset of cohorts
./NHLBI-BDC-DMC-HV/hv_dataqc/sb_scripts/run_s5_report.sh \
    --cohorts ARIC,MESA

# List available DataRuns
./NHLBI-BDC-DMC-HV/hv_dataqc/sb_scripts/run_s5_report.sh --list-dataruns
```

Output goes to `/sbgenomics/workspace/S5-output-files/<RUN_TS>/` with
per-cohort harmonized JSONs, the final `table_s5_paste_<ts>.tsv` (paste
into cell B3 of the template), and `s5_coverage_<ts>.tsv` showing which
S5 labels matched / aliased / went missing. The whole run dir is also
packaged as `/sbgenomics/workspace/s5_report_<RUN_TS>.tgz` for download.
