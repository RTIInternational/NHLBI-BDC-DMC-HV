#!/usr/bin/env bash
# Build the Table S5 paste-ready TSV from a DataRun's harmonized output.
#
# For each cohort present in the chosen DataRun, runs the harmonized
# extractor (with the bdc_label map) to produce a per-cohort JSON, then
# runs the S5 post-processor over all the JSONs to emit the paste-ready
# TSV, a formatted .xlsx, and a coverage report.
#
# Resumable: each cohort's harmonized extract is cached per DataRun under
# QC-output-files/<COHORT>/harmonized_<DataRun>/ and reused on re-run.
#
# Usage:
#   ./run_s5_report.sh                              # latest DataRun, all cohorts
#   ./run_s5_report.sh --datarun DataRun_20260412_1830  # pinned
#   ./run_s5_report.sh --list-dataruns              # show available DataRuns
#   ./run_s5_report.sh --cohorts ARIC,MESA          # restrict to two cohorts
#   ./run_s5_report.sh --force                      # re-extract even if cached
set -euo pipefail

# --- Parse arguments ---
PINNED_DATARUN=""
LIST_ONLY=false
COHORT_FILTER=""
FORCE=false        # re-extract cohorts even if a same-DataRun extract exists

while [ $# -gt 0 ]; do
    case "$1" in
        --datarun)       PINNED_DATARUN="${2:?--datarun requires a value}"; shift 2 ;;
        --list-dataruns) LIST_ONLY=true; shift ;;
        --cohorts)       COHORT_FILTER="${2:?--cohorts requires a value}"; shift 2 ;;
        --force)         FORCE=true; shift ;;
        -h|--help)       sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        -*)              echo "Unknown flag: $1" >&2; exit 1 ;;
        *)               echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

# Derive repo root from this script's location (sb_scripts/ -> hv_dataqc/ -> repo root)
HV="$(cd "$(dirname "$0")/../.." && pwd)"

# --- List available DataRuns ---
ALL_DATARUNS=()
for dr in $(ls -dr /sbgenomics/project-files/_QC_STAGING/DataRun_* 2>/dev/null); do
    ALL_DATARUNS+=("$(basename "$dr")")
done

if [ ${#ALL_DATARUNS[@]} -eq 0 ]; then
    echo "ERROR: No DataRun_* dirs found under /sbgenomics/project-files/_QC_STAGING/" >&2
    exit 1
fi

if $LIST_ONLY; then
    echo "Available DataRuns (newest first):"
    for dr in "${ALL_DATARUNS[@]}"; do
        echo "  $dr"
    done
    exit 0
fi

# --- Select the DataRun ---
if [ -n "$PINNED_DATARUN" ]; then
    MATCHED=false
    for dr in "${ALL_DATARUNS[@]}"; do
        if [ "$dr" = "$PINNED_DATARUN" ]; then
            CHOSEN_DATARUN="$dr"
            MATCHED=true
            break
        fi
    done
    if ! $MATCHED; then
        echo "ERROR: DataRun '$PINNED_DATARUN' not found" >&2
        echo "  Available:" >&2
        for dr in "${ALL_DATARUNS[@]}"; do echo "    $dr" >&2; done
        exit 1
    fi
    echo "Using pinned DataRun: $CHOSEN_DATARUN"
else
    CHOSEN_DATARUN="${ALL_DATARUNS[0]}"
    if [ ${#ALL_DATARUNS[@]} -gt 1 ]; then
        echo "NOTE: Found ${#ALL_DATARUNS[@]} DataRun dirs; using latest: $CHOSEN_DATARUN"
        echo "  Use --datarun NAME to pin, or --list-dataruns to see all"
    else
        echo "Using DataRun: $CHOSEN_DATARUN"
    fi
fi
DATARUN_PATH="/sbgenomics/project-files/_QC_STAGING/$CHOSEN_DATARUN"

# --- Discover cohorts in the DataRun ---
# Each cohort's mapped-data dir is at
#   <DataRun>/DMC_<lowercase_study>_<COHORT>_*BDCHM/mapped-data/
# The lowercase study prefix can itself contain underscores (e.g. hchs_sol),
# so we match against a known list of cohort names by checking for
# `_${COHORT}_` as a delimited substring in the DMC dir basename.  Same
# approach run_extracts.sh uses on the input side.
KNOWN_COHORTS=(ARIC CARDIA CHS COPDGene FHS HCHS JHS LTRC MESA SPIROMICS WHI)
declare -A COHORT_MAPPED_DIRS=()  # cohort -> space-separated list of mapped-data dirs
for mapped_dir in $(find "$DATARUN_PATH" -ipath "*BDCHM/mapped-data" -type d 2>/dev/null | sort); do
    bdchm_dir=$(dirname "$mapped_dir")
    dmc_dir=$(basename "$(dirname "$bdchm_dir")")
    cohort=""
    for candidate in "${KNOWN_COHORTS[@]}"; do
        # Use case-insensitive _COHORT_ delimiter matching.  Same logic as
        # run_extracts.sh's find -ipath "*_${COHORT}_*BDCHM/mapped-data".
        candidate_lower=$(echo "$candidate" | tr '[:upper:]' '[:lower:]')
        dmc_lower=$(echo "$dmc_dir" | tr '[:upper:]' '[:lower:]')
        if [[ "$dmc_lower" == *"_${candidate_lower}_"* ]]; then
            cohort="$candidate"
            break
        fi
    done
    if [ -z "$cohort" ]; then
        echo "NOTE: skipping $dmc_dir (no known cohort name matched)" >&2
        continue
    fi
    # Accumulate mapped-data dirs per cohort
    if [ -n "${COHORT_MAPPED_DIRS[$cohort]:-}" ]; then
        COHORT_MAPPED_DIRS[$cohort]="${COHORT_MAPPED_DIRS[$cohort]} $mapped_dir"
    else
        COHORT_MAPPED_DIRS[$cohort]="$mapped_dir"
    fi
done

if [ ${#COHORT_MAPPED_DIRS[@]} -eq 0 ]; then
    echo "ERROR: No mapped-data dirs found under $DATARUN_PATH" >&2
    exit 1
fi

# Apply --cohorts filter if given
if [ -n "$COHORT_FILTER" ]; then
    IFS=',' read -r -a FILTER_LIST <<< "$COHORT_FILTER"
    declare -A FILTERED=()
    for c in "${FILTER_LIST[@]}"; do
        c_upper=$(echo "$c" | tr '[:lower:]' '[:upper:]')
        for cohort in "${!COHORT_MAPPED_DIRS[@]}"; do
            if [ "$(echo "$cohort" | tr '[:lower:]' '[:upper:]')" = "$c_upper" ]; then
                FILTERED[$cohort]="${COHORT_MAPPED_DIRS[$cohort]}"
            fi
        done
    done
    if [ ${#FILTERED[@]} -eq 0 ]; then
        echo "ERROR: --cohorts filter '$COHORT_FILTER' matched no cohorts in $CHOSEN_DATARUN" >&2
        echo "  Available: ${!COHORT_MAPPED_DIRS[*]}" >&2
        exit 1
    fi
    # Replace COHORT_MAPPED_DIRS with the filtered map
    unset COHORT_MAPPED_DIRS
    declare -A COHORT_MAPPED_DIRS=()
    for k in "${!FILTERED[@]}"; do
        COHORT_MAPPED_DIRS[$k]="${FILTERED[$k]}"
    done
fi

echo "Cohorts to extract: ${!COHORT_MAPPED_DIRS[*]}"
echo

# --- Per-cohort harmonized extract (resumable, keyed by DataRun) ---
# Each cohort's harmonized extract is written to a stable, DataRun-stamped dir:
#   QC-output-files/<COHORT>/harmonized_<DataRun>/
# so a re-run reuses an existing same-DataRun extract instead of redoing it
# (a checkpoint). --force redoes them. The S5 paste TSV / xlsx still go to a
# fresh timestamped S5-output-files/<ts>/.
RUN_TS=$(date -u +%Y%m%dT%H%M%SZ)
S5_OUTPUT_DIR="/sbgenomics/workspace/S5-output-files/$RUN_TS"
mkdir -p "$S5_OUTPUT_DIR"
QC_BASE="/sbgenomics/workspace/QC-output-files"
COHORT_JSONS=()

TOTAL=${#COHORT_MAPPED_DIRS[@]}
i=0
for cohort in "${!COHORT_MAPPED_DIRS[@]}"; do
    i=$((i + 1))
    cohort_lower=$(echo "$cohort" | tr '[:upper:]' '[:lower:]')
    cohort_out="$QC_BASE/$cohort/harmonized_$CHOSEN_DATARUN"

    # Reuse an existing same-DataRun extract unless --force.
    existing=""
    if ! $FORCE; then
        existing=$(find "$cohort_out" -name "${cohort_lower}_harmonized_*.json" -type f 2>/dev/null | sort | tail -1 || true)
    fi
    if [ -n "$existing" ]; then
        echo "[$i/$TOTAL] $cohort — reusing harmonized extract ($CHOSEN_DATARUN)"
        cohort_json="$existing"
    else
        echo "[$i/$TOTAL] $cohort — harmonized extract ($CHOSEN_DATARUN)..."
        mkdir -p "$cohort_out"
        (cd "$HV" && uv run python -m hv_dataqc.extract_harmonized.extract_harmonized_summaries \
            --cohort "$cohort" \
            --mapped-data-dirs ${COHORT_MAPPED_DIRS[$cohort]} \
            --output-dir "$cohort_out")
        cohort_json=$(find "$cohort_out" -name "${cohort_lower}_harmonized_*.json" -type f -print | sort | tail -1)
    fi

    if [ -z "$cohort_json" ]; then
        echo "WARNING: no harmonized JSON for $cohort; skipping it in S5 aggregation"
    else
        COHORT_JSONS+=("$cohort_json")
    fi
    echo
done

if [ ${#COHORT_JSONS[@]} -eq 0 ]; then
    echo "ERROR: no per-cohort JSONs produced; cannot run S5 aggregation" >&2
    exit 1
fi

# --- S5 aggregation ---
echo "=== S5 aggregation across ${#COHORT_JSONS[@]} cohort(s) ==="
(cd "$HV" && uv run python -m hv_dataqc.extract_harmonized.table_s5.report \
    "${COHORT_JSONS[@]}" \
    --output-dir "$S5_OUTPUT_DIR")
echo

# --- Package for download ---
echo "=== Packaging output ==="
TGZ="/sbgenomics/workspace/s5_report_${RUN_TS}.tgz"
tar czfh "$TGZ" -C "$(dirname "$S5_OUTPUT_DIR")" "$(basename "$S5_OUTPUT_DIR")"
echo "Output packaged: $TGZ"
echo
echo "To download: right-click s5_report_${RUN_TS}.tgz in the JupyterLab file"
echo "browser (/) and select Download.  The table_s5_paste_*.tsv inside is the"
echo "file to paste into cell B3 of the Table S5 template spreadsheet."
