#!/usr/bin/env bash
# =============================================================================
# extract_topmed_dcc.sh
# -----------------------------------------------------------------------------
# ONE-TIME reference build of the TOPMed DCC side.
#
# The TOPMed DCC harmonized phenotypes are a FIXED external reference — they do
# not change between dm-bip runs. Extract them ONCE into a stable directory,
# then point run_dcc_compare.sh at that directory for every subsequent BDC run.
# You only need to re-run this when the TOPMed DCC release itself changes.
#
# Output: <out>/topmed_<cohort>_summary.json (aggregate-only; safe to keep and
# re-use). These files are the "never changes" reference the comparison reads.
#
# -----------------------------------------------------------------------------
# USAGE
#   ./extract_topmed_dcc.sh --topmed-dir <DCC EAV dir> --out <reference dir> \
#                           [--cohorts "ARIC CHS WHI"] [-- <extra python args>]
#
# EXAMPLE
#   ./extract_topmed_dcc.sh \
#       --topmed-dir /data/topmed-dcc-eav \
#       --out        /data/topmed-dcc-summaries
#
# Anything after a literal `--` is forwarded verbatim to
# extract-topmed/extract_topmed_summaries.py (e.g. explicit --demographics-file
# overrides). Run that script with --help to see all per-dataset file flags.
# =============================================================================
set -euo pipefail

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

TOPMED_DIR=""
OUT_DIR=""
COHORTS=""
PASSTHRU=()

die() { echo "ERROR: $*" >&2; exit 1; }
usage() { sed -n '2,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --topmed-dir) TOPMED_DIR="$2"; shift 2 ;;
        --out)        OUT_DIR="$2"; shift 2 ;;
        --cohorts)    COHORTS="$2"; shift 2 ;;
        --)           shift; PASSTHRU=("$@"); break ;;
        -h|--help)    usage 0 ;;
        *)            die "Unknown argument: $1  (try --help)" ;;
    esac
done

[[ -n "$TOPMED_DIR" ]] || die "--topmed-dir is required (directory of DCC EAV files / *.tar.gz bundles)."
[[ -d "$TOPMED_DIR" ]] || die "--topmed-dir not found: $TOPMED_DIR"
[[ -n "$OUT_DIR"    ]] || die "--out is required (stable reference directory for topmed_*_summary.json)."
mkdir -p "$OUT_DIR"

COHORT_ARGS=()
if [[ -n "$COHORTS" ]]; then
    # shellcheck disable=SC2206
    COHORT_ARR=($COHORTS)
    COHORT_ARGS=(--cohorts "${COHORT_ARR[@]}")
fi

echo "============================================================"
echo "  TOPMed DCC reference extraction (one-time)"
echo "============================================================"
echo "  input (EAV) : $TOPMED_DIR"
echo "  output ref  : $OUT_DIR"
[[ -n "$COHORTS" ]] && echo "  cohorts     : $COHORTS"
echo

$PYTHON extract-topmed/extract_topmed_summaries.py \
    --base-dir   "$TOPMED_DIR" \
    --output-dir "$OUT_DIR" \
    "${COHORT_ARGS[@]}" \
    ${PASSTHRU[@]+"${PASSTHRU[@]}"}

echo
n=$(ls "$OUT_DIR"/topmed_*_summary.json 2>/dev/null | wc -l)
[[ "$n" -gt 0 ]] || die "No topmed_*_summary.json produced — check --topmed-dir contents."
echo "  Wrote $n TOPMed reference summary file(s) to: $OUT_DIR"
echo "  Pass this directory to run_dcc_compare.sh via --topmed-summaries."
