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

# Reports are archived by (commit, timestamp): the actual files live in
# local_output/archive/<commit>_<YYYYMMDDTHHMMSS>/, and top-level paths
# are symlinks to the most recent. Each archive dir has its own
# manifest.json with the source/harmonized inputs and the git commit.
GIT_COMMIT="$(cd "$HV" && git rev-parse --short HEAD 2>/dev/null || echo unknown)"
RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE_DIR="$OUT/archive/${GIT_COMMIT}_${RUN_TS}"
mkdir -p "$ARCHIVE_DIR"

REPORT="$ARCHIVE_DIR/${COHORT_LOWER}_comparison_report.md"
JSON_REPORT="$ARCHIVE_DIR/${COHORT_LOWER}_comparison_results.json"

# Top-level symlinks: <cohort>_comparison_{report.md,results.json}
LATEST_REPORT="$OUT/${COHORT_LOWER}_comparison_report.md"
LATEST_JSON="$OUT/${COHORT_LOWER}_comparison_results.json"

# Determine YAML dir with a case-insensitive lookup so
# casing does not matter and the script remains portable
# across sed variants.
YAML_DIR="$(find "$HV/priority_variables_transform" -maxdepth 1 -type d -iname "${COHORT}-ingest" -print -quit)"
if [ -z "$YAML_DIR" ]; then
    echo "ERROR: No YAML dir found for $COHORT in priority_variables_transform/" >&2
    exit 1
fi

CACHE_DIR="$OUT/dbgap-cache/$COHORT_LOWER"
if [ ! -d "$CACHE_DIR" ]; then
    echo "ERROR: dbGaP cache not found at $CACHE_DIR" >&2
    echo "  Run: ./fetch_cache.sh --cohort $COHORT_LOWER" >&2
    exit 1
fi

# The compare run returns nonzero when FAILs are present, but we still want
# to record the archive entry. Capture the exit code and re-raise after.
COMPARE_RC=0
(cd "$HV" && uv run python -m hv_dataqc.compare \
    --source "$SOURCE" \
    --harmonized "$HARMONIZED" \
    --cohort "$COHORT" \
    --yaml-dir "$YAML_DIR" \
    --cache-dir "$CACHE_DIR" \
    --report "$REPORT" \
    --json-report "$JSON_REPORT" \
    "$@") || COMPARE_RC=$?

# Only update the latest symlinks and write the manifest if compare actually
# produced both expected outputs. A pre-output crash (invalid input, schema
# mismatch, etc.) should leave the previous latest links pointing at the
# last successful run rather than at a half-written or missing archive.
if [ -f "$REPORT" ] && [ -f "$JSON_REPORT" ]; then
    # Manifest records the inputs used for this archive entry.
    cat > "$ARCHIVE_DIR/manifest.json" <<EOF
{
  "cohort": "$COHORT",
  "git_commit": "$GIT_COMMIT",
  "generated_at": "$RUN_TS",
  "source_json": "$(basename "$SOURCE")",
  "harmonized_json": "$(basename "$HARMONIZED")",
  "yaml_dir": "$(basename "$YAML_DIR")"
}
EOF

    # Update top-level symlinks to point at the latest archived report.
    ln -sfn "archive/${GIT_COMMIT}_${RUN_TS}/${COHORT_LOWER}_comparison_report.md" "$LATEST_REPORT"
    ln -sfn "archive/${GIT_COMMIT}_${RUN_TS}/${COHORT_LOWER}_comparison_results.json" "$LATEST_JSON"

    echo
    echo "Reports: $REPORT"
    echo "         $JSON_REPORT"
    echo "Latest:  $LATEST_REPORT -> archive/${GIT_COMMIT}_${RUN_TS}/"
else
    # Compare failed before writing output. Clean up the empty archive dir
    # (rmdir is safe — it only removes empty dirs) and leave existing
    # latest symlinks alone.
    rmdir "$ARCHIVE_DIR" 2>/dev/null || true
    echo >&2
    echo "ERROR: compare exited with $COMPARE_RC without producing output files." >&2
    echo "Existing latest symlinks (if any) are unchanged." >&2
    # Ensure we propagate a failure exit even if the compare process
    # somehow reported 0 but produced no output.
    [ "$COMPARE_RC" -eq 0 ] && COMPARE_RC=1
fi

# Preserve the compare exit code so callers (e.g., CI / regression-check)
# can still detect FAILs even though we did extra work after the run.
exit $COMPARE_RC
