#!/usr/bin/env bash
# Run source + harmonized extracts for a cohort on Seven Bridges.
# Auto-discovers the latest DataRun with mapped-data for the cohort,
# or uses a specific DataRun if --datarun is given.
#
# Usage:
#   ./run_extracts.sh COPDGene                              # latest DataRun
#   ./run_extracts.sh COPDGene --datarun DataRun_20260412_1830  # pinned
#   ./run_extracts.sh ARIC --list-dataruns                  # show available
set -euo pipefail

# --- Parse arguments ---
COHORT_INPUT=""
PINNED_DATARUN=""
LIST_ONLY=false

while [ $# -gt 0 ]; do
    case "$1" in
        --datarun)       PINNED_DATARUN="${2:?--datarun requires a value}"; shift 2 ;;
        --list-dataruns) LIST_ONLY=true; shift ;;
        -*)              echo "Unknown flag: $1" >&2; exit 1 ;;
        *)               [ -z "$COHORT_INPUT" ] && COHORT_INPUT="$1"; shift ;;
    esac
done
[ -z "$COHORT_INPUT" ] && { echo "Usage: ./run_extracts.sh <cohort> [--datarun NAME] [--list-dataruns]" >&2; exit 1; }

COHORT_LOWER="$(echo "$COHORT_INPUT" | tr '[:upper:]' '[:lower:]')"
COHORT_UPPER="$(echo "$COHORT_INPUT" | tr '[:lower:]' '[:upper:]')"
# Derive repo root from this script's location (sb_scripts/ -> hv-dataqc/ -> repo root)
HV="$(cd "$(dirname "$0")/../.." && pwd)"

# Discover the actual source directory name (case-insensitive)
SOURCE_ROOT="$(find /sbgenomics/project-files/PilotParentStudies_NoDRS -maxdepth 1 -type d -iname "$COHORT_INPUT" -print -quit 2>/dev/null)"
if [ -z "$SOURCE_ROOT" ]; then
    echo "ERROR: No source directory found matching '$COHORT_INPUT' under PilotParentStudies_NoDRS/" >&2
    exit 1
fi

# Use the discovered directory name as the canonical cohort name for output paths
COHORT="$(basename "$SOURCE_ROOT")"
OUTPUT_DIR="/sbgenomics/workspace/QC-output-files/$COHORT"

# --- Find DataRuns with mapped-data for this cohort ---
# Build an ordered list (newest first) of DataRuns that contain this cohort's data
ALL_DATARUNS=()
ALL_MAPPED_DIRS=()
for dr in $(ls -dr /sbgenomics/project-files/_QC_STAGING/DataRun_* 2>/dev/null); do
    found=$(find "$dr" -ipath "*${COHORT_INPUT}*BDCHM/mapped-data" -type d 2>/dev/null | sort)
    # TODO: confirm fix against other cohorts. This was changed to get WHI working.
    # found=$(find "$dr" -path "*${COHORT_LOWER}*BDCHM/mapped-data" -type d 2>/dev/null | sort)
    if [ -n "$found" ]; then
        ALL_DATARUNS+=("$(basename "$dr")")
        ALL_MAPPED_DIRS+=("$found")
    fi
done

if [ ${#ALL_DATARUNS[@]} -eq 0 ]; then
    echo "ERROR: No DataRun_* dirs found containing mapped-data for $COHORT" >&2
    echo "  Looked under /sbgenomics/project-files/_QC_STAGING/DataRun_*" >&2
    exit 1
fi

# --list-dataruns: show available and exit
if $LIST_ONLY; then
    echo "Available DataRuns for $COHORT (newest first):"
    for i in "${!ALL_DATARUNS[@]}"; do
        echo "  ${ALL_DATARUNS[$i]}"
    done
    exit 0
fi

# Select the DataRun
if [ -n "$PINNED_DATARUN" ]; then
    # Find the pinned DataRun in the list
    MATCHED=false
    for i in "${!ALL_DATARUNS[@]}"; do
        if [ "${ALL_DATARUNS[$i]}" = "$PINNED_DATARUN" ]; then
            CHOSEN_DATARUN="${ALL_DATARUNS[$i]}"
            MAPPED_DIRS="${ALL_MAPPED_DIRS[$i]}"
            MATCHED=true
            break
        fi
    done
    if ! $MATCHED; then
        echo "ERROR: DataRun '$PINNED_DATARUN' not found for $COHORT" >&2
        echo "  Available:" >&2
        for dr in "${ALL_DATARUNS[@]}"; do echo "    $dr" >&2; done
        exit 1
    fi
    echo "Using pinned DataRun: $CHOSEN_DATARUN"
else
    CHOSEN_DATARUN="${ALL_DATARUNS[0]}"
    MAPPED_DIRS="${ALL_MAPPED_DIRS[0]}"
    if [ ${#ALL_DATARUNS[@]} -gt 1 ]; then
        echo "NOTE: Found ${#ALL_DATARUNS[@]} DataRun dirs with $COHORT data; using latest: $CHOSEN_DATARUN"
        echo "  Use --datarun NAME to pin, or --list-dataruns to see all"
    else
        echo "Using DataRun: $CHOSEN_DATARUN"
    fi
fi

echo "Source root:  $SOURCE_ROOT"
echo "Mapped dirs:"
echo "$MAPPED_DIRS" | sed 's/^/  /'
echo "Output dir:   $OUTPUT_DIR"
echo

# --- Source extract ---
echo "=== Running source extract ==="
uv run python "$HV/hv-dataqc/extract-source/extract_source_summaries.py" \
    --cohort "$COHORT" \
    --source-root "$SOURCE_ROOT" \
    --output-dir "$OUTPUT_DIR"

echo

# --- Harmonized extract ---
echo "=== Running harmonized extract ==="
uv run python "$HV/hv-dataqc/extract-harmonized/extract_harmonized_summaries.py" \
    --cohort "$COHORT" \
    --mapped-data-dirs $MAPPED_DIRS \
    --output-dir "$OUTPUT_DIR"

echo

# --- Package for download ---
echo "=== Packaging output ==="
TGZ="/sbgenomics/workspace/dataqc_${COHORT_LOWER}_output.tgz"
# Dereference symlinks (-h) so the tgz contains actual files, not dangling links
tar czfh "$TGZ" -C "$OUTPUT_DIR" latest_source latest_harmonized
echo "Output packaged: $TGZ"
echo
echo "To download: right-click dataqc_${COHORT_LOWER}_output.tgz in the"
echo "JupyterLab file browser (/) and select Download."
