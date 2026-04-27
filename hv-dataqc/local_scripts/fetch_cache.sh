#!/usr/bin/env bash
# Convenience wrapper for cache-fetcher with output to local_output/dbgap-cache.
# Pass any fetch_dbgap_cache.py flags, e.g.:
#   ./fetch_cache.sh --cohort copdgene
#   ./fetch_cache.sh --list
#   ./fetch_cache.sh --cohort mesa --dry-run
cd "$(dirname "$0")"
HV="$(cd ../.. && pwd)"
python "$HV/hv-dataqc/cache-fetcher/fetch_dbgap_cache.py" \
    --output-dir ../local_output/dbgap-cache \
    "$@"
