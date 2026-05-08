# sb_scripts — Seven Bridges Runner Scripts

Scripts that run **inside the Seven Bridges enclave**. These wrap the core
extract scripts with the right paths for SB project file layouts.

The scripts derive the repo root from their own location, so the repo
can be cloned anywhere on SB.

## Setup

At the start of each SB session:

```bash
cd <path-to>/NHLBI-BDC-DMC-HV
git pull
source hv-dataqc/sb_scripts/setup.sh
```

### `vi_defaults.sh`

SB doesn't persist dotfiles. Source this to set vi as editor and enable
vi keybindings:

```bash
source NHLBI-BDC-DMC-HV/hv-dataqc/sb_scripts/vi_defaults.sh
```

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

```bash
# Use latest DataRun
./NHLBI-BDC-DMC-HV/hv-dataqc/sb_scripts/run_extracts.sh COPDGene

# Pin to a specific DataRun (ensures source + harmonized use same data)
./NHLBI-BDC-DMC-HV/hv-dataqc/sb_scripts/run_extracts.sh COPDGene --datarun DataRun_20260412_1830

# List available DataRuns for a cohort
./NHLBI-BDC-DMC-HV/hv-dataqc/sb_scripts/run_extracts.sh COPDGene --list-dataruns
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
uv run python NHLBI-BDC-DMC-HV/hv-dataqc/extract-source/extract_source_summaries.py \
    --cohort COPDGene \
    --source-root /sbgenomics/project-files/PilotParentStudies_NoDRS/COPDGene \
    --output-dir /sbgenomics/workspace/QC-output-files/COPDGene

# Harmonized extract (use --mapped-data-dirs to avoid OOM)
uv run python NHLBI-BDC-DMC-HV/hv-dataqc/extract-harmonized/extract_harmonized_summaries.py \
    --cohort COPDGene \
    --mapped-data-dirs \
      /sbgenomics/project-files/DataRun_.../DMC_copdgene_..._c1_.../mapped-data \
      /sbgenomics/project-files/DataRun_.../DMC_copdgene_..._c2_.../mapped-data \
    --output-dir /sbgenomics/workspace/QC-output-files/COPDGene
```

**Note:** Use `--mapped-data-dirs` instead of `--harmonized-root` for the
harmonized extract — `--harmonized-root` tries to process all cohorts and
can OOM on SB.
