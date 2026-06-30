#!/usr/bin/env bash
# Build the spec-sourced Table S4 (phv counts + source N) for all cohorts.
#
# S4 is sourced from the transform specs (priority_variables_transform/
# <cohort>-ingest/) for phv lists/counts, joined to per-cohort source-extract
# JSONs for N.  No spreadsheets involved.
#
# With NO arguments it runs the whole idempotent pipeline:
#   fetch dbGaP caches -> preflight -> extract any cohort missing an extract
#   (reuse the rest) -> build CSV + xlsx. Re-running only does missing work.
#
# Usage:
#   ./run_s4_report.sh                       # do everything (idempotent)
#   ./run_s4_report.sh --check               # preflight only: readiness, run nothing
#   ./run_s4_report.sh --no-fetch            # skip the cache fetch (use existing caches)
#   ./run_s4_report.sh --no-extract          # build from existing extracts only
#   ./run_s4_report.sh --force               # re-extract every cohort (ignore existing)
#   ./run_s4_report.sh --cohorts FHS,MESA    # subset
#   ./run_s4_report.sh --list-cohorts        # show cohorts that have spec dirs
set -euo pipefail

# --- Parse arguments ---
# Defaults make a no-arg run do the whole idempotent pipeline:
#   fetch caches -> preflight -> extract any missing cohort -> build CSV+xlsx.
COHORT_FILTER=""
DO_EXTRACT=true     # extract cohorts that lack an extract; --no-extract to skip
DO_FETCH=true       # fetch_cache.sh first (idempotent); --no-fetch to skip
LIST_ONLY=false
CHECK_ONLY=false
FORCE=false
while [ $# -gt 0 ]; do
    case "$1" in
        --cohorts)       COHORT_FILTER="${2:?--cohorts requires a value}"; shift 2 ;;
        --extract)       DO_EXTRACT=true; shift ;;          # accepted (already default)
        --no-extract)    DO_EXTRACT=false; shift ;;
        --no-fetch)      DO_FETCH=false; shift ;;
        --force)         FORCE=true; shift ;;
        --check)         CHECK_ONLY=true; shift ;;
        --list-cohorts)  LIST_ONLY=true; shift ;;
        -h|--help)       sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
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

# Locate a cohort's newest source-extract JSON (follows the latest_source
# symlink; falls back to scanning source_<ts>/ run dirs). Empty if none.
find_src_json() {
    local out_dir="$1" j
    # `|| true` guards against find exiting non-zero (missing dir / dangling
    # symlink) under `set -e` inside command substitution.
    j="$(find -L "$out_dir/latest_source" -maxdepth 1 -name "*_source_*.json" 2>/dev/null | sort | tail -n1 || true)"
    [ -z "$j" ] && j="$(find "$out_dir" -path "*/source_*/*_source_*.json" 2>/dev/null | sort | tail -n1 || true)"
    printf '%s' "$j"
}

find_source_root() {
    # `|| true`: find exits non-zero if the search root is absent (e.g. running
    # off-enclave), which would trip `set -e` inside a command substitution.
    find /sbgenomics/project-files/PilotParentStudies_NoDRS -maxdepth 1 -type d -iname "$1" -print -quit 2>/dev/null || true
}

# --- Fetch dbGaP caches (idempotent; fast when already cached) ---
# Skipped for --check (read-only) and --no-fetch. fetch_cache.sh is the
# existing, tested fetcher; with no cohort arg it fetches/refreshes all.
if $DO_FETCH && ! $CHECK_ONLY; then
    echo "=== Fetching dbGaP caches (idempotent) ==="
    if ! "$HV/hv_dataqc/local_scripts/fetch_cache.sh"; then
        echo "WARNING: fetch_cache.sh returned non-zero; continuing with whatever caches exist." >&2
    fi
    echo
fi

# --- Preflight: assess each cohort (cache present? extract present?) ---
echo "=== Preflight (${#ALL_COHORTS[@]} cohort(s)) ==="
PREFLIGHT_OK=()      # cohorts that can contribute to the report now
for COHORT in "${ALL_COHORTS[@]}"; do
    OUT_DIR="$OUT_BASE/$COHORT"
    CACHE_DIR="$HV/hv_dataqc/local_output/dbgap-cache/$(cache_subdir "$COHORT")"
    SRC_JSON="$(find_src_json "$OUT_DIR")"
    SOURCE_ROOT="$(find_source_root "$COHORT")"

    have_cache="no"; [ -d "$CACHE_DIR" ] && have_cache="yes"
    have_extract="no"; [ -n "$SRC_JSON" ] && have_extract="yes"
    have_source="no"; [ -n "$SOURCE_ROOT" ] && have_source="yes"

    # Decide status. The dbGaP cache is required either way (to resolve PHV ->
    # column for the N join), so a missing cache is BLOCKED in every mode — the
    # actionable first step regardless of --extract.
    status="" ; note=""
    if [ "$have_cache" = "no" ]; then
        status="BLOCKED"; note="no cache (fetch_cache.sh $(cache_subdir "$COHORT"))"
    elif [ "$have_extract" = "yes" ] && { ! $DO_EXTRACT || ! $FORCE; }; then
        status="READY"; note="reuse extract"
        $DO_EXTRACT && [ "$FORCE" = "false" ] && note="reuse extract (skip re-extract; --force to redo)"
    elif $DO_EXTRACT; then
        if [ "$have_source" = "yes" ]; then
            status="WILL-EXTRACT"; note="extract then build"
        else
            status="BLOCKED"; note="no source dir under PilotParentStudies_NoDRS"
        fi
    else
        status="MISSING"; note="cache present but no extract; run with --extract (or run_extracts.sh $COHORT)"
    fi

    printf '  %-10s %-12s cache=%-3s extract=%-3s  %s\n' "$COHORT" "$status" "$have_cache" "$have_extract" "$note"
    case "$status" in
        READY|WILL-EXTRACT) PREFLIGHT_OK+=("$COHORT") ;;
    esac
done
echo "  ----"
echo "  ${#PREFLIGHT_OK[@]}/${#ALL_COHORTS[@]} cohort(s) will contribute: ${PREFLIGHT_OK[*]:-none}"
echo

if $CHECK_ONLY; then
    echo "(--check: preflight only, nothing run)"
    exit 0
fi
if [ ${#PREFLIGHT_OK[@]} -eq 0 ]; then
    echo "ERROR: no cohort is ready. See preflight notes above (usually missing cache or extract)." >&2
    exit 1
fi

# --- Per-cohort: extract if needed (restart-safe), collect triples ---
TRIPLE_ARGS=()
USED_COHORTS=()
TOTAL=${#PREFLIGHT_OK[@]}
i=0
for COHORT in "${PREFLIGHT_OK[@]}"; do
    i=$((i + 1))
    OUT_DIR="$OUT_BASE/$COHORT"
    CACHE_DIR="$HV/hv_dataqc/local_output/dbgap-cache/$(cache_subdir "$COHORT")"
    SRC_JSON="$(find_src_json "$OUT_DIR")"

    # Restart-safe: only extract when asked AND (no extract yet OR --force).
    if $DO_EXTRACT && { [ -z "$SRC_JSON" ] || $FORCE; }; then
        SOURCE_ROOT="$(find_source_root "$COHORT")"
        echo "[$i/$TOTAL] $COHORT — source extract (this is the slow step)..."
        # S4 only needs variables_by_pht.  Skip the multi-PHV joint-distribution
        # crosstabs (QAQC-only; FHS ~33k pairs dominate memory). Console is quiet
        # by default; full log is in the run's *.log file.
        (cd "$HV" && uv run python -m hv_dataqc.extract_source.extract_source_summaries \
            --cohort "$COHORT" \
            --source-root "$SOURCE_ROOT" \
            --output-dir "$OUT_DIR" \
            --yaml-dir "$SPECS_ROOT/${COHORT}-ingest" \
            --cache-dir "$CACHE_DIR" \
            --no-joint-distributions)
        SRC_JSON="$(find_src_json "$OUT_DIR")"
    elif $DO_EXTRACT; then
        echo "[$i/$TOTAL] $COHORT — extract already present, skipping (--force to redo)"
    else
        echo "[$i/$TOTAL] $COHORT — reusing existing extract"
    fi

    if [ -z "$SRC_JSON" ]; then
        echo "WARNING: $COHORT has no source extract after preflight — skipping" >&2
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
