#!/usr/bin/env bash
# Build the spec-sourced Table S4 (phv counts + source N) for all cohorts.
#
# S4 is sourced from the transform specs (priority_variables_transform/
# <cohort>-ingest/) for phv lists/counts, joined to per-cohort source-extract
# JSONs for N.  No spreadsheets involved.
#
# By default it REUSES each cohort's existing latest_source extract under
# QC-output-files/<COHORT>/.  Pass --extract to (re-)run the source extract
# for any cohort first (slow; reads raw source TSVs in the enclave).
#
# Usage:
#   ./run_s4_report.sh                       # all cohorts with spec dirs
#   ./run_s4_report.sh --cohorts FHS,MESA    # subset
#   ./run_s4_report.sh --extract             # run source extracts first
#   ./run_s4_report.sh --list-cohorts        # show cohorts that have spec dirs
set -euo pipefail

# --- Parse arguments ---
COHORT_FILTER=""
DO_EXTRACT=false
LIST_ONLY=false
while [ $# -gt 0 ]; do
    case "$1" in
        --cohorts)       COHORT_FILTER="${2:?--cohorts requires a value}"; shift 2 ;;
        --extract)       DO_EXTRACT=true; shift ;;
        --list-cohorts)  LIST_ONLY=true; shift ;;
        -h|--help)       sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        -*)              echo "Unknown flag: $1" >&2; exit 1 ;;
        *)               echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

# Derive repo root from this script's location (sb_scripts/ -> hv_dataqc/ -> repo root)
HV="$(cd "$(dirname "$0")/../.." && pwd)"
SPECS_ROOT="$HV/priority_variables_transform"
OUT_BASE="/sbgenomics/workspace/QC-output-files"
S4_OUT="/sbgenomics/workspace/S4-output-files"

# --- Discover cohorts that have an ingest spec dir ---
ALL_COHORTS=()
for d in "$SPECS_ROOT"/*-ingest; do
    [ -d "$d" ] || continue
    name="$(basename "$d")"
    ALL_COHORTS+=("${name%-ingest}")
done
if [ ${#ALL_COHORTS[@]} -eq 0 ]; then
    echo "ERROR: no <cohort>-ingest dirs under $SPECS_ROOT" >&2
    exit 1
fi

if $LIST_ONLY; then
    echo "Cohorts with transform spec dirs:"
    printf '  %s\n' "${ALL_COHORTS[@]}"
    exit 0
fi

# Apply --cohorts filter
if [ -n "$COHORT_FILTER" ]; then
    IFS=',' read -r -a WANT <<< "$COHORT_FILTER"
    SELECTED=()
    for w in "${WANT[@]}"; do
        matched=""
        for c in "${ALL_COHORTS[@]}"; do
            [ "$(echo "$c" | tr '[:upper:]' '[:lower:]')" = "$(echo "$w" | tr '[:upper:]' '[:lower:]')" ] && matched="$c"
        done
        if [ -n "$matched" ]; then SELECTED+=("$matched");
        else echo "WARNING: no spec dir for cohort '$w' — skipping" >&2; fi
    done
    ALL_COHORTS=("${SELECTED[@]}")
fi

# Map cohort -> dbGaP cache subdir (mirror run_extracts.sh: hchs -> hchs_sol)
cache_subdir() {
    local lc; lc="$(echo "$1" | tr '[:upper:]' '[:lower:]')"
    case "$lc" in
        hchs) echo "hchs_sol" ;;
        *)    echo "$lc" ;;
    esac
}

# --- Per-cohort: ensure source extract, collect triples ---
TRIPLE_ARGS=()
USED_COHORTS=()
for COHORT in "${ALL_COHORTS[@]}"; do
    LC="$(echo "$COHORT" | tr '[:upper:]' '[:lower:]')"
    OUT_DIR="$OUT_BASE/$COHORT"
    CACHE_DIR="$HV/hv_dataqc/local_output/dbgap-cache/$(cache_subdir "$COHORT")"

    if $DO_EXTRACT; then
        SOURCE_ROOT="$(find /sbgenomics/project-files/PilotParentStudies_NoDRS -maxdepth 1 -type d -iname "$COHORT" -print -quit 2>/dev/null)"
        if [ -z "$SOURCE_ROOT" ]; then
            echo "WARNING: no source dir for $COHORT under PilotParentStudies_NoDRS — skipping" >&2
            continue
        fi
        if [ ! -d "$CACHE_DIR" ]; then
            echo "WARNING: no dbGaP cache for $COHORT ($CACHE_DIR) — skipping. Fetch: hv_dataqc/local_scripts/fetch_cache.sh $(cache_subdir "$COHORT")" >&2
            continue
        fi
        echo "=== [$COHORT] source extract ==="
        # S4 only needs variables_by_pht.  Skip the multi-PHV joint-distribution
        # crosstabs (QAQC-only; FHS produces ~33k pairs that dominate memory).
        (cd "$HV" && uv run python -m hv_dataqc.extract_source.extract_source_summaries \
            --cohort "$COHORT" \
            --source-root "$SOURCE_ROOT" \
            --output-dir "$OUT_DIR" \
            --yaml-dir "$SPECS_ROOT/${COHORT}-ingest" \
            --cache-dir "$CACHE_DIR" \
            --no-joint-distributions)
    fi

    # Locate the cohort's source-extract JSON. The extractor writes to
    # <OUT_DIR>/source_<ts>/ and points a `latest_source` *symlink* at it; use
    # `find -L` so the symlinked dir is followed (GNU find does not follow a
    # symlink start-point without -L). Fall back to scanning the run subdirs
    # directly if the symlink is missing.
    SRC_JSON="$(find -L "$OUT_DIR/latest_source" -maxdepth 1 -name "*_source_*.json" 2>/dev/null | sort | tail -n1)"
    if [ -z "$SRC_JSON" ]; then
        SRC_JSON="$(find "$OUT_DIR" -path "*/source_*/*_source_*.json" 2>/dev/null | sort | tail -n1)"
    fi
    if [ -z "$SRC_JSON" ]; then
        echo "WARNING: no source extract for $COHORT under $OUT_DIR — run with --extract or run_extracts.sh $COHORT first; skipping" >&2
        continue
    fi
    if [ ! -d "$CACHE_DIR" ]; then
        echo "WARNING: no dbGaP cache for $COHORT ($CACHE_DIR) — skipping" >&2
        continue
    fi

    TRIPLE_ARGS+=(--cohort "$COHORT" --source-json "$SRC_JSON" --cache-dir "$CACHE_DIR")
    USED_COHORTS+=("$COHORT")
done

if [ ${#USED_COHORTS[@]} -eq 0 ]; then
    echo "ERROR: no cohorts had a usable source extract + cache. Run with --extract." >&2
    exit 1
fi

# --- Build the combined S4 CSV ---
mkdir -p "$S4_OUT"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
CSV="$S4_OUT/s4_report_${TS}.csv"

echo
echo "=== Building S4 over: ${USED_COHORTS[*]} ==="
# Run as a module (-m) from the repo root so the hv_dataqc and
# transform_assessment packages are both importable, regardless of whether
# the project is pip-installed in the environment. (Running the file by path
# only puts the script's own dir on sys.path, so `import hv_dataqc` fails.)
(cd "$HV" && uv run python -m transform_assessment.spec_phv_report \
    --specs-root "$SPECS_ROOT" \
    "${TRIPLE_ARGS[@]}" \
    --output "$CSV")

# Stable symlink to the latest
ln -sfn "$(basename "$CSV")" "$S4_OUT/latest_s4_report.csv"

echo
echo "S4 written: $CSV"
echo "Latest symlink: $S4_OUT/latest_s4_report.csv"
echo "Paste the CSV (minus header) into the Table S4 template."
