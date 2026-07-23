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
