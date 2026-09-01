#!/usr/bin/env bash
# =============================================================================
# run_dcc_compare.sh
# -----------------------------------------------------------------------------
# Per-run driver: multi-cohort BDC harmonized output  ->  TOPMed DCC comparison.
#
# The TOPMed DCC side is a FIXED reference and is NOT extracted here. Build it
# once with extract_topmed_dcc.sh, then pass that stable summaries directory in
# via --topmed-summaries. This script only:
#   1. extract-harmonized  (BDC dm-bip DMC_*_Processed_* output -> bdc_*.json)
#   2. compare/compare.py --batch          -> per-cohort + cross-cohort reports
#   3. compare/batch_scorecard.py          -> letter-grade scorecards
#   4. compare/core_variable_coverage_table.py -> 19-core YAML coverage matrix
#
# All outputs are aggregate-only (safe to export from the enclave).
#
# -----------------------------------------------------------------------------
# USAGE
#   ./run_dcc_compare.sh --bdc-dir <dm-bip output root> \
#                        --topmed-summaries <dir of topmed_*_summary.json> \
#                        [--out <run dir>] [--cohorts "ARIC CHS WHI"] \
#                        [--all-vars] [--hv-repo <path>] [--skip-coverage]
#
# EXAMPLE
#   # one-time (rarely): build the fixed TOPMed reference
#   ./extract_topmed_dcc.sh --topmed-dir /data/topmed-dcc-eav \
#                           --out /data/topmed-dcc-summaries
#
#   # every dm-bip run: compare against that reference
#   ./run_dcc_compare.sh --bdc-dir /root \
#                        --topmed-summaries /data/topmed-dcc-summaries
# =============================================================================
set -euo pipefail

# --- locate the toolkit (this script lives at hv-dcc-compare/) ---------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Prefer uv (manages an isolated env from pyproject.toml + uv.lock). Override
# with e.g. PYTHON=python to use the ambient interpreter instead.
if [[ -n "${PYTHON:-}" ]]; then
    :
elif command -v uv >/dev/null 2>&1; then
    PYTHON="uv run python"
else
    PYTHON="python"
fi

# --- defaults ----------------------------------------------------------------
BDC_DIR=""
TOPMED_SUMMARIES=""
OUT_DIR=""
COHORTS=""
ALL_VARS=""
HV_REPO=""
SKIP_COVERAGE=""

die() { echo "ERROR: $*" >&2; exit 1; }
usage() { sed -n '2,31p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

# --- parse args --------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --bdc-dir)          BDC_DIR="$2"; shift 2 ;;
        --topmed-summaries) TOPMED_SUMMARIES="$2"; shift 2 ;;
        --out)              OUT_DIR="$2"; shift 2 ;;
        --cohorts)          COHORTS="$2"; shift 2 ;;
        --all-vars)         ALL_VARS="--all-vars"; shift ;;
        --hv-repo)          HV_REPO="$2"; shift 2 ;;
        --skip-coverage)    SKIP_COVERAGE="1"; shift ;;
        -h|--help)          usage 0 ;;
        *)                  die "Unknown argument: $1  (try --help)" ;;
    esac
done

# --- validate ----------------------------------------------------------------
[[ -n "$BDC_DIR" ]] || die "--bdc-dir is required (dm-bip output root holding DMC_*_Processed_* folders)."
[[ -d "$BDC_DIR" ]] || die "--bdc-dir not found: $BDC_DIR"
[[ -n "$TOPMED_SUMMARIES" ]] || die "--topmed-summaries is required (dir of topmed_*_summary.json from extract_topmed_dcc.sh)."
[[ -d "$TOPMED_SUMMARIES" ]] || die "--topmed-summaries not found: $TOPMED_SUMMARIES"
ls "$TOPMED_SUMMARIES"/topmed_*_summary.json >/dev/null 2>&1 \
    || die "No topmed_*_summary.json in $TOPMED_SUMMARIES. Build the reference first with extract_topmed_dcc.sh."

# Default HV repo = two levels up (hv-dcc-compare lives inside the HV checkout).
if [[ -z "$HV_REPO" ]]; then HV_REPO="$(cd "$SCRIPT_DIR/.." && pwd)"; fi

# Timestamped run directory keeps each run's BDC JSONs isolated (Phase-2 globs
# the latest bdc_*_summary_*.json, so never mix runs in one dir).
if [[ -z "$OUT_DIR" ]]; then OUT_DIR="$SCRIPT_DIR/runs/$(date +%Y%m%d_%H%M%S)"; fi
BDC_OUT="$OUT_DIR/bdc"
REPORTS_OUT="$OUT_DIR/reports"
SCORECARDS_OUT="$OUT_DIR/scorecards"
COVERAGE_OUT="$OUT_DIR/coverage"
mkdir -p "$BDC_OUT" "$REPORTS_OUT" "$SCORECARDS_OUT" "$COVERAGE_OUT"

# Optional cohort restriction, forwarded to the BDC extractor / scorecard.
COHORT_ARGS=()
if [[ -n "$COHORTS" ]]; then
    # shellcheck disable=SC2206
    COHORT_ARR=($COHORTS)
    COHORT_ARGS=(--cohorts "${COHORT_ARR[@]}")
fi

banner() { echo; echo "============================================================"; echo "  $*"; echo "============================================================"; }

banner "hv-dcc-compare run"
echo "  toolkit     : $SCRIPT_DIR"
echo "  bdc-dir     : $BDC_DIR"
echo "  topmed ref  : $TOPMED_SUMMARIES  (fixed reference; not re-extracted)"
echo "  hv-repo     : $HV_REPO"
echo "  out-dir     : $OUT_DIR"
[[ -n "$COHORTS" ]]  && echo "  cohorts     : $COHORTS"
[[ -n "$ALL_VARS" ]] && echo "  all-vars    : yes"

# --- 1. BDC harmonized extract ----------------------------------------------
banner "[1/4] Extracting BDC harmonized summaries"
$PYTHON extract-harmonized/extract_harmonized_summaries.py \
    --base-dir   "$BDC_DIR" \
    --output-dir "$BDC_OUT" \
    "${COHORT_ARGS[@]}"

ls "$BDC_OUT"/bdc_*_summary_*.json >/dev/null 2>&1 \
    || die "No bdc_*_summary_*.json produced. Check that --bdc-dir points at the level containing DMC_*_<COHORT>_Processed_* folders."

# --- 2. Comparison reports (batch) — reads the fixed TOPMed reference in place
banner "[2/4] Building comparison reports (TXT + MD)"
$PYTHON compare/compare.py --batch \
    --bdc-dir    "$BDC_OUT" \
    --topmed-dir "$TOPMED_SUMMARIES" \
    --output-dir "$REPORTS_OUT"

# --- 3. Scorecard ------------------------------------------------------------
banner "[3/4] Building letter-grade scorecards"
$PYTHON compare/batch_scorecard.py \
    --bdc-dir    "$BDC_OUT" \
    --topmed-dir "$TOPMED_SUMMARIES" \
    --output-dir "$SCORECARDS_OUT" \
    ${ALL_VARS} \
    "${COHORT_ARGS[@]}"

# --- 4. Coverage matrix (needs HV YAML checkout; no participant data) --------
if [[ -z "$SKIP_COVERAGE" && -d "$HV_REPO/priority_variables_transform" ]]; then
    banner "[4/4] Building 19-core-variable coverage matrix"
    $PYTHON compare/core_variable_coverage_table.py \
        --hv-repo    "$HV_REPO" \
        --topmed-dir "$TOPMED_SUMMARIES" \
        > "$COVERAGE_OUT/core_variable_coverage.txt" 2>&1 \
        && echo "  wrote $COVERAGE_OUT/core_variable_coverage.txt" \
        || echo "  WARN: coverage table failed (non-fatal); see $COVERAGE_OUT/core_variable_coverage.txt"
else
    banner "[4/4] Coverage matrix skipped"
    echo "  (no priority_variables_transform/ under $HV_REPO, or --skip-coverage set)"
fi

# --- done --------------------------------------------------------------------
banner "DONE"
echo "  Run directory: $OUT_DIR"
echo "    bdc/         $(ls "$BDC_OUT"/bdc_*_summary_*.json 2>/dev/null | wc -l) cohort summaries"
echo "    reports/     $(ls "$REPORTS_OUT" 2>/dev/null | wc -l) files"
echo "    scorecards/  $(ls "$SCORECARDS_OUT" 2>/dev/null | wc -l) files"
echo "    coverage/    $(ls "$COVERAGE_OUT" 2>/dev/null | wc -l) files"
echo "  TOPMed reference (unchanged): $TOPMED_SUMMARIES"
echo
echo "  All outputs are aggregate-only and safe to export from the enclave."
