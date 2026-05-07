#!/usr/bin/env bash
# Convenience wrapper for cache-fetcher with output to local_output/dbgap-cache.
#
# Usage:
#   ./fetch_cache.sh copdgene              # positional cohort name
#   ./fetch_cache.sh --cohort copdgene     # also works
#   ./fetch_cache.sh --list
#   ./fetch_cache.sh copdgene --dry-run    # extra flags forwarded
cd "$(dirname "$0")"
HV="$(cd ../.. && pwd)"

# If the first arg doesn't start with '-', treat it as a positional cohort name
ARGS=("$@")
if [ $# -ge 1 ] && [[ "$1" != -* ]]; then
    ARGS=("--cohort" "$@")
fi

mkdir -p ../local_output/dbgap-cache
uv run python "$HV/hv-dataqc/cache-fetcher/fetch_dbgap_cache.py" \
    --output-dir ../local_output/dbgap-cache \
    "${ARGS[@]}"
