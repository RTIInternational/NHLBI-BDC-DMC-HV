#!/usr/bin/env bash
# Regression check used during the compare refactor (Phase A file split).
#
# Compares the current compare.sh output against pre-captured baselines for
# COPDGene, ARIC, and HCHS. Run before starting a refactor step to capture
# baselines, then re-run after to verify parity.
#
# The MD report (after stripping the `**Generated:**` line) is the parity
# gate — it's deterministic and user-facing. JSON output has pre-existing
# nondeterministic array ordering on some cohorts; we report JSON diffs
# as informational only.
#
# Usage:
#   ./regression_check.sh capture  # capture current output as baselines
#   ./regression_check.sh check    # diff current output against baselines (default)
set -u

HV="$(cd "$(dirname "$0")/../.." && pwd)"
COMPARE="$HV/hv_dataqc/local_scripts/compare.sh"
OUT="$HV/hv_dataqc/local_output"
BASELINE="${REGRESSION_BASELINE_DIR:-/tmp/phase_a_baseline}"
MODE="${1:-check}"

strip_json() { jq -S 'del(.metadata.generated_at)' "$1"; }
strip_md()   { sed -E 's/^\*\*Generated:\*\*.*$/<timestamp>/' "$1"; }

run_compare_for() {
    local name="$1"
    local slug="$2"
    # Remove output files first so a crashed compare leaves no stale output
    # that could be misread as a successful run.
    rm -f "$OUT/${slug}_comparison_results.json" "$OUT/${slug}_comparison_report.md"
    # compare.sh exits nonzero when findings include FAILs; that's normal.
    "$COMPARE" "$name" > "/tmp/compare_${slug}.log" 2>&1 || true
}

if [ "$MODE" = "capture" ]; then
    mkdir -p "$BASELINE"
    for spec in "COPDGene copdgene" "ARIC aric" "hchs hchs"; do
        set -- $spec
        NAME="$1"; SLUG="$2"
        echo "Capturing $SLUG (cohort=$NAME)..."
        run_compare_for "$NAME" "$SLUG"
        if [ ! -f "$OUT/${SLUG}_comparison_results.json" ]; then
            echo "  ERROR: no output JSON for $SLUG — see /tmp/compare_${SLUG}.log"
            exit 1
        fi
        strip_json "$OUT/${SLUG}_comparison_results.json" > "$BASELINE/${SLUG}.sorted.json"
        cp "$OUT/${SLUG}_comparison_report.md" "$BASELINE/${SLUG}.md"
    done
    echo "Baselines written to $BASELINE"
    exit 0
fi

if [ "$MODE" != "check" ]; then
    echo "Usage: $0 [capture|check]" >&2
    exit 2
fi

FAIL=0
for spec in "COPDGene copdgene" "ARIC aric" "hchs hchs"; do
    set -- $spec
    NAME="$1"; SLUG="$2"

    echo "--- $SLUG ---"
    run_compare_for "$NAME" "$SLUG"

    if [ ! -f "$OUT/${SLUG}_comparison_results.json" ]; then
        echo "  compare run FAILED (no JSON output) — see /tmp/compare_${SLUG}.log"
        FAIL=1
        continue
    fi

    if diff -q <(strip_md "$OUT/${SLUG}_comparison_report.md") <(strip_md "$BASELINE/${SLUG}.md") > /dev/null; then
        echo "  MD:   match"
    else
        echo "  MD:   DIFF"
        FAIL=1
    fi

    if diff -q <(strip_json "$OUT/${SLUG}_comparison_results.json") "$BASELINE/${SLUG}.sorted.json" > /dev/null; then
        echo "  JSON: match"
    else
        echo "  JSON: diff (informational — JSON array ordering can be nondeterministic)"
    fi
done

exit $FAIL
