#!/usr/bin/env bash
# Run source + harmonized extracts for a cohort on Seven Bridges.
# Auto-discovers the latest DataRun with mapped-data for the cohort.
#
# Usage:
#   ./run_extracts.sh COPDGene
#   ./run_extracts.sh ARIC
# discovers DataRun_* files under the top level subfolder, _QC_STAGING in order to flag data run files that are ready for QC vs. not
set -euo pipefail

COHORT="${1:?Usage: ./run_extracts.sh <cohort>}"
COHORT_LOWER="$(echo "$COHORT" | tr '[:upper:]' '[:lower:]')"
HV="/sbgenomics/workspace/NHLBI-BDC-DMC-HV"
OUTPUT_DIR="/sbgenomics/workspace/QC-output-files/$COHORT"
SOURCE_ROOT="/sbgenomics/project-files/PilotParentStudies_NoDRS/$COHORT"

# --- Auto-discover latest DataRun with mapped-data for this cohort ---
MAPPED_DIRS=""
CHOSEN_DATARUN=""
CANDIDATE_COUNT=0
for dr in $(ls -dr /sbgenomics/project-files/_QC_STAGING/DataRun_* 2>/dev/null); do
    found=$(find "$dr" -path "*${COHORT_LOWER}*BDCHM/mapped-data" -type d 2>/dev/null | sort)
    if [ -n "$found" ]; then
        CANDIDATE_COUNT=$((CANDIDATE_COUNT + 1))
        if [ -z "$MAPPED_DIRS" ]; then
            MAPPED_DIRS="$found"
            CHOSEN_DATARUN="$(basename "$dr")"
        fi
    fi
done

if [ "$CANDIDATE_COUNT" -eq 0 ]; then
    echo "ERROR: No DataRun_* dirs found containing mapped-data for $COHORT" >&2
    echo "  Looked under /sbgenomics/project-files/_QC_STAGING/DataRun_*" >&2
    exit 1
elif [ "$CANDIDATE_COUNT" -gt 1 ]; then
    echo "NOTE: Found $CANDIDATE_COUNT DataRun dirs with $COHORT data; using latest: $CHOSEN_DATARUN"
else
    echo "Using DataRun: $CHOSEN_DATARUN"
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
