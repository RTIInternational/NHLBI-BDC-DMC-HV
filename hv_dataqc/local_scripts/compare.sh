#!/usr/bin/env bash
# Convenience wrapper for `python -m hv_dataqc.compare`.
# Picks up the latest source/harmonized JSONs from local_output/ for the given cohort.
#
# Usage:
#   ./compare.sh copdgene
#   ./compare.sh spiromics
#   ./compare.sh copdgene --thresholds custom.yaml   # extra flags forwarded
set -euo pipefail
cd "$(dirname "$0")"
HV="$(cd ../.. && pwd)"
OUT="$(cd .. && pwd)/local_output"
mkdir -p "$OUT"

COHORT="${1:?Usage: ./compare.sh <cohort> [extra flags...]}"
shift
COHORT_LOWER="$(echo "$COHORT" | tr '[:upper:]' '[:lower:]')"

# Find source and harmonized JSONs.
# Try latest_source/ and latest_harmonized/ subdirs first (from unpack.sh),
# then fall back to flat files in local_output/ (legacy layout).
SOURCE=$(ls -t "$OUT/latest_source/${COHORT_LOWER}_source_"*.json 2>/dev/null | head -1 || true)
if [ -z "$SOURCE" ]; then
    SOURCE=$(ls -t "$OUT/${COHORT_LOWER}_source_"*.json 2>/dev/null | head -1 || true)
fi
HARMONIZED=$(ls -t "$OUT/latest_harmonized/${COHORT_LOWER}_harmonized_"*.json 2>/dev/null | head -1 || true)
if [ -z "$HARMONIZED" ]; then
    HARMONIZED=$(ls -t "$OUT/${COHORT_LOWER}_harmonized_"*.json 2>/dev/null | head -1 || true)
fi

if [ -z "$SOURCE" ]; then
    echo "ERROR: No source JSON found matching $OUT/${COHORT_LOWER}_source_*.json" >&2
    exit 1
fi
if [ -z "$HARMONIZED" ]; then
    echo "ERROR: No harmonized JSON found matching $OUT/${COHORT_LOWER}_harmonized_*.json" >&2
    exit 1
fi

echo "Source:     $(basename "$SOURCE")"
echo "Harmonized: $(basename "$HARMONIZED")"

# Report output goes into local_output/
REPORT="$OUT/${COHORT_LOWER}_comparison_report.md"
JSON_REPORT="$OUT/${COHORT_LOWER}_comparison_results.json"

# Determine YAML dir with a case-insensitive lookup so
# casing does not matter and the script remains portable
# across sed variants.
YAML_DIR="$(find "$HV/priority_variables_transform" -maxdepth 1 -type d -iname "${COHORT}-ingest" -print -quit)"

if [ -z "$YAML_DIR" ]; then
    echo "WARNING: No YAML dir found for $COHORT in priority_variables_transform/. Running without crosswalk." >&2
    (cd "$HV" && uv run python -m hv_dataqc.compare \
        --source "$SOURCE" \
        --harmonized "$HARMONIZED" \
        --cohort "$COHORT" \
        --report "$REPORT" \
        --json-report "$JSON_REPORT" \
        "$@")
else
    CACHE_DIR="$OUT/dbgap-cache/$COHORT_LOWER"
    if [ ! -d "$CACHE_DIR" ]; then
        echo "ERROR: dbGaP cache not found at $CACHE_DIR" >&2
        echo "  Run: ./fetch_cache.sh --cohort $COHORT_LOWER" >&2
        exit 1
    fi
    (cd "$HV" && uv run python -m hv_dataqc.compare \
        --source "$SOURCE" \
        --harmonized "$HARMONIZED" \
        --cohort "$COHORT" \
        --yaml-dir "$YAML_DIR" \
        --cache-dir "$CACHE_DIR" \
        --report "$REPORT" \
        --json-report "$JSON_REPORT" \
        "$@")
fi

echo
echo "Reports: $REPORT"
echo "         $JSON_REPORT"
