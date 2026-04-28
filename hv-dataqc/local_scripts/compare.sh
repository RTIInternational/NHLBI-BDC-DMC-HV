#!/usr/bin/env bash
# Convenience wrapper for compare_source_harmonized.py.
# Picks up the latest source/harmonized JSONs from local_output/ for the given cohort.
#
# Usage:
#   ./compare.sh copdgene
#   ./compare.sh spiromics
#   ./compare.sh copdgene --thresholds custom.yaml   # extra flags forwarded
set -euo pipefail
cd "$(dirname "$0")"
HV="$(cd ../.. && pwd)"
OUT=../local_output

COHORT="${1:?Usage: ./compare.sh <cohort> [extra flags...]}"
shift
COHORT_LOWER="$(echo "$COHORT" | tr '[:upper:]' '[:lower:]')"

# Find the most recent source and harmonized JSONs.
# Append `|| true` so that under `set -euo pipefail`, an empty match (ls
# returning non-zero) does not abort the script before the `-z` checks below
# can emit a friendly error message.
SOURCE=$(ls -t "$OUT/${COHORT_LOWER}_source_"*.json 2>/dev/null | head -1 || true)
HARMONIZED=$(ls -t "$OUT/${COHORT_LOWER}_harmonized_"*.json 2>/dev/null | head -1 || true)

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

# Determine YAML dir — try common casing patterns
YAML_DIR=""
for candidate in \
    "$HV/priority_variables_transform/${COHORT}-ingest" \
    "$HV/priority_variables_transform/${COHORT_LOWER}-ingest" \
    "$HV/priority_variables_transform/$(echo "$COHORT" | sed 's/.*/\u&/')-ingest"; do
    if [ -d "$candidate" ]; then
        YAML_DIR="$candidate"
        break
    fi
done

if [ -z "$YAML_DIR" ]; then
    echo "WARNING: No YAML dir found for $COHORT in priority_variables_transform/. Running without crosswalk." >&2
    python "$HV/hv-dataqc/compare/compare_source_harmonized.py" \
        --source "$SOURCE" \
        --harmonized "$HARMONIZED" \
        --cohort "$COHORT" \
        "$@"
else
    CACHE_DIR="$OUT/dbgap-cache/$COHORT_LOWER"
    if [ ! -d "$CACHE_DIR" ]; then
        echo "ERROR: dbGaP cache not found at $CACHE_DIR" >&2
        echo "  Run: ./fetch_cache.sh --cohort $COHORT_LOWER" >&2
        exit 1
    fi
    python "$HV/hv-dataqc/compare/compare_source_harmonized.py" \
        --source "$SOURCE" \
        --harmonized "$HARMONIZED" \
        --cohort "$COHORT" \
        --yaml-dir "$YAML_DIR" \
        --cache-dir "$CACHE_DIR" \
        "$@"
fi
