# sb_scripts — Seven Bridges Runner Scripts

Scripts that run **inside the Seven Bridges enclave**. These wrap the core
extract scripts with the right paths for SB project file layouts.

**Assumed layout:** This repo is cloned at `/sbgenomics/workspace/NHLBI-BDC-DMC-HV`.
All commands below assume you are running from `/sbgenomics/workspace/`.

## Setup

### `setup.sh`

Run once per SB session to install `uv` and sync project dependencies:

```bash
source NHLBI-BDC-DMC-HV/hv-dataqc/sb_scripts/setup.sh
```

### `vi_defaults.sh`

SB doesn't persist dotfiles. Source this to set vi as editor and enable
vi keybindings:

```bash
source NHLBI-BDC-DMC-HV/hv-dataqc/sb_scripts/vi_defaults.sh
```

## Scripts

### `find_participant_gap.py`

Investigates participant count discrepancies between source PHT tables.
For COPDGene, this checks whether participants missing from
`Demographics_Baseline` (pht016246) appear in other PHT tables
(Subject, Subject_Phenotypes, Subject_Images).

```bash
# Default: COPDGene source root on SB
uv run python find_participant_gap.py

# Custom source root
uv run python find_participant_gap.py --source-root /sbgenomics/project-files/.../COPDGene
```

Output is aggregate-only (counts + PHT membership patterns) — safe to export.

## Running extracts on SB

The core extract scripts live in `extract-source/` and `extract-harmonized/`.
Run them from the SB workspace:

```bash
# Source extract
uv run python NHLBI-BDC-DMC-HV/hv-dataqc/extract-source/extract_source_summaries.py \
    --cohort COPDGene \
    --source-root /sbgenomics/project-files/PilotParentStudies_NoDRS/COPDGene \
    --output-dir /sbgenomics/workspace/COPDGene/dataqc-runs

# Harmonized extract (use --mapped-data-dirs to avoid OOM)
uv run python NHLBI-BDC-DMC-HV/hv-dataqc/extract-harmonized/extract_harmonized_summaries.py \
    --cohort COPDGene \
    --mapped-data-dirs \
      /sbgenomics/project-files/DataRun_.../DMC_copdgene_..._c1_.../mapped-data \
      /sbgenomics/project-files/DataRun_.../DMC_copdgene_..._c2_.../mapped-data \
    --output-dir /sbgenomics/workspace/COPDGene/dataqc-runs
```

**Note:** Use `--mapped-data-dirs` instead of `--harmonized-root` for the
harmonized extract — `--harmonized-root` tries to process all cohorts and
can OOM on SB.
