#!/usr/bin/env bash
# Run once per SB session to install uv and project dependencies.

# SB's default umask is permissive (everything lands 0777, shown green in
# listings). Set a normal umask so files we create are 644 and dirs 755.
umask 022

pip install uv
# Derive repo root from this script's location (sb_scripts/ -> hv_dataqc/ -> repo root)
HV="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$HV"
export UV_LINK_MODE=copy
uv sync
git config core.fileMode false  # because SB changes file permissions and then git status says every file has changed

cat <<'BANNER'

────────────────────────────────────────────────────────────────────────
  HV-DataQC — run commands (all from the repo root)
────────────────────────────────────────────────────────────────────────
  Table S4 (pre-harmonization phv counts + source N):
    hv_dataqc/sb_scripts/run_s4_report.sh            # do everything
    hv_dataqc/sb_scripts/run_s4_report.sh --check    # readiness, run nothing
      (fetches caches, then resumes: extracts only cohorts missing one)

  Table S5 (post-harmonization summary stats):
    hv_dataqc/sb_scripts/run_s5_report.sh                  # latest DataRun
    hv_dataqc/sb_scripts/run_s5_report.sh --list-dataruns  # pick a DataRun

  QAQC (source-vs-harmonized, per cohort) — see hv_dataqc/QUICK_RUN.md:
    hv_dataqc/sb_scripts/run_extracts.sh <COHORT>    # then compare.sh locally

  Output lands in /sbgenomics/workspace/{S4,S5}-output-files/ (download the
  .xlsx). Re-running resumes from completed cohorts; --force redoes them.
────────────────────────────────────────────────────────────────────────
BANNER