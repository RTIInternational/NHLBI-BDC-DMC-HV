#!/usr/bin/env bash
# Build the spec-sourced Table S4 (phv counts + source N) for all cohorts.
#
# S4 is sourced from the transform specs (priority_variables_transform/
# <cohort>-ingest/) for phv lists/counts, joined to per-cohort source-extract
# JSONs for N.  No spreadsheets involved.
#
# With NO arguments it runs the whole idempotent pipeline:
#   fetch dbGaP caches -> preflight -> extract any cohort whose extract is
#   missing or stale (reuse the rest) -> build CSV + xlsx. Re-running only
#   does missing work. Stale = the specs now reference a PHV the extract
#   wasn't scoped to. Extracts live in S4-output-files/extracts/<COHORT>.
#
# Usage:
#   ./run_s4_report.sh                       # do everything (idempotent)
#   ./run_s4_report.sh --check               # preflight only: readiness, run nothing
#   ./run_s4_report.sh --no-fetch            # skip the cache fetch (use existing caches)
#   ./run_s4_report.sh --no-extract          # build from existing extracts only
#   ./run_s4_report.sh --force               # re-extract every cohort (even current ones)
#   ./run_s4_report.sh --cohorts FHS,MESA    # subset
#   ./run_s4_report.sh --list-cohorts        # show cohorts that have spec dirs
set -euo pipefail

# --- Parse arguments ---
# Defaults make a no-arg run do the whole idempotent pipeline:
#   fetch caches -> preflight -> extract any missing cohort -> build CSV+xlsx.
COHORT_FILTER=""
DO_EXTRACT=true     # extract cohorts lacking a current extract; --no-extract to skip
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
        -h|--help)       sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        -*)              echo "Unknown flag: $1" >&2; exit 1 ;;
        *)               echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

# Derive repo root from this script's location (sb_scripts/ -> hv_dataqc/ -> repo root)
HV="$(cd "$(dirname "$0")/../.." && pwd)"
SPECS_ROOT="$HV/priority_variables_transform"
S4_OUT="/sbgenomics/workspace/S4-output-files"
# S4's own extracts: scoped to spec PHVs, so not shared with QAQC's full
# extracts in QC-output-files/.
OUT_BASE="$S4_OUT/extracts"

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

# Why COHORT's extract ($2) doesn't cover its current specs; empty if it does.
stale_reason() {
    local out rc=0
    out="$(cd "$HV" && uv run python -m hv_dataqc.extract_source.extract_coverage \
        --source-json "$2" --yaml-dir "$SPECS_ROOT/$1-ingest")" || rc=$?
    case "$rc" in
        0) ;;
        1) printf '%s' "$out" ;;
        *) printf 'coverage check failed (exit %s)' "$rc" ;;
    esac
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
    echo "=== Fetching dbGaP caches (idempotent, quiet) ==="
    # --quiet keeps the per-file/per-cohort chatter out of the runner output;
    # warnings + the final cache summary still print.
    if ! "$HV/hv_dataqc/sb_scripts/fetch_cache.sh" --quiet; then
        echo "WARNING: fetch_cache.sh returned non-zero; continuing with whatever caches exist." >&2
    fi
    echo
fi

# --- Preflight: assess each cohort (cache present? extract present?) ---
echo "=== Preflight (${#ALL_COHORTS[@]} cohort(s)) ==="
PREFLIGHT_OK=()      # cohorts that can contribute to the report now
TO_EXTRACT=()        # cohorts to (re-)extract before building
for COHORT in "${ALL_COHORTS[@]}"; do
    OUT_DIR="$OUT_BASE/$COHORT"
    CACHE_DIR="$HV/hv_dataqc/local_output/dbgap-cache/$(cache_subdir "$COHORT")"
    SRC_JSON="$(find_src_json "$OUT_DIR")"
    SOURCE_ROOT="$(find_source_root "$COHORT")"

    # A cache dir alone is not enough: PHV -> column resolution reads
    # pheno_variable_summaries/*.data_dict.xml, and an extract made without
    # them is near-empty yet looks current to the staleness check.
    have_cache="no"
    if [ -d "$CACHE_DIR/pheno_variable_summaries" ] \
        && [ -n "$(find "$CACHE_DIR/pheno_variable_summaries" -maxdepth 1 -name '*.data_dict.xml' -print -quit 2>/dev/null)" ]; then
        have_cache="yes"
    fi
    have_extract="no"; [ -n "$SRC_JSON" ] && have_extract="yes"
    have_source="no"; [ -n "$SOURCE_ROOT" ] && have_source="yes"
    stale=""; [ "$have_extract" = "yes" ] && stale="$(stale_reason "$COHORT" "$SRC_JSON")"
    needs_extract=false
    { [ "$have_extract" = "no" ] || $FORCE || [ -n "$stale" ]; } && needs_extract=true

    # Decide status. The dbGaP cache is required either way (to resolve PHV ->
    # column for the N join), so a missing cache is BLOCKED in every mode — the
    # actionable first step regardless of --extract.
    status="" ; note=""
    if [ "$have_cache" = "no" ]; then
        status="BLOCKED"; note="no cache or empty pheno_variable_summaries/ (fetch_cache.sh $(cache_subdir "$COHORT"))"
    elif $needs_extract && $DO_EXTRACT && [ "$have_source" = "yes" ]; then
        status="WILL-EXTRACT"
        if [ "$have_extract" = "no" ]; then note="extract then build"
        elif [ -n "$stale" ]; then note="re-extract: $stale"
        else note="re-extract (--force)"; fi
        TO_EXTRACT+=("$COHORT")
    elif [ "$have_extract" = "yes" ]; then
        status="READY"; note="reuse extract"
        [ -n "$stale" ] && note="reuse STALE extract, N may undercount: $stale"
        $needs_extract && $DO_EXTRACT && note="$note (no source dir to re-extract)"
    elif $DO_EXTRACT; then
        status="BLOCKED"; note="no source dir under PilotParentStudies_NoDRS"
    else
        status="MISSING"; note="cache present but no extract; drop --no-extract"
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

    # Restart-safe: preflight queued only cohorts lacking a current extract.
    if [[ " ${TO_EXTRACT[*]-} " == *" $COHORT "* ]]; then
        SOURCE_ROOT="$(find_source_root "$COHORT")"
        echo "[$i/$TOTAL] $COHORT — source extract (this is the slow step)..."
        # S4 only needs variables_by_pht for spec PHVs: scope columns to them
        # and skip the multi-PHV joint-distribution crosstabs (QAQC-only; FHS
        # ~33k pairs dominate memory). Console is quiet by default; full log is
        # in the run's *.log file.
        (cd "$HV" && uv run python -m hv_dataqc.extract_source.extract_source_summaries \
            --cohort "$COHORT" \
            --source-root "$SOURCE_ROOT" \
            --output-dir "$OUT_DIR" \
            --yaml-dir "$SPECS_ROOT/${COHORT}-ingest" \
            --cache-dir "$CACHE_DIR" \
            --scope-to-yaml \
            --no-joint-distributions)
        SRC_JSON="$(find_src_json "$OUT_DIR")"
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

# Stable symlinks to the latest CSV and xlsx.
XLSX="${CSV%.csv}.xlsx"
ln -sfn "$(basename "$CSV")" "$S4_OUT/latest_s4_report.csv"
[ -f "$XLSX" ] && ln -sfn "$(basename "$XLSX")" "$S4_OUT/latest_s4_report.xlsx"

echo
echo "S4 written:"
echo "  CSV : $CSV"
[ -f "$XLSX" ] && echo "  XLSX: $XLSX   (template-shaped + formatted — open or use directly)"
echo "Latest: $S4_OUT/latest_s4_report.{csv,xlsx}"
echo "Download the .xlsx from the JupyterLab file browser (right-click -> Download)."
