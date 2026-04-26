"""
batch_scorecard.py — DCCCompareBatch: Cross-cohort match quality scorecards
============================================================================
Processes multiple BDC summary JSONs at once, matches each to its TOPMed
reference JSON, runs per-variable A/B/C/D grading, and produces:
  1. Per-cohort scorecard (text file)
  2. Cross-cohort summary table (single file, all cohorts side-by-side)

USAGE:
    # Auto-discover all BDC JSONs in the default BDC_Output directory
    python batch_scorecard.py

    # Specify BDC directory explicitly
    python batch_scorecard.py --bdc-dir /path/to/BDC_Output

    # Specify both directories
    python batch_scorecard.py \
        --bdc-dir /path/to/BDC_Output \
        --topmed-dir /path/to/TOPMed_Output \
        --output-dir /path/to/scorecard_output

    # Process only specific cohorts
    python batch_scorecard.py --cohorts ARIC CHS FHS

    # Score all matched variables instead of the core comparison scope
    python batch_scorecard.py --all-vars
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from match_quality_table import CORE_VARIABLES, KNOWN_METHODOLOGICAL_DIFFS

# ─────────────────────────────────────────────────────────────────────────────
# DEFAULTS — relative to the current working directory
# Run from an output directory where topmed/ and bdc/ subdirs exist, or
# supply --topmed-dir, --bdc-dir, and --output-dir explicitly.
# ─────────────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_TOPMED_DIR = Path("topmed")
DEFAULT_BDC_DIR = Path("bdc")
DEFAULT_OUTPUT_DIR = Path("scorecards")

# Cohort key normalization: filenames use lowercase with underscores
COHORT_ALIASES = {
    "aric": "ARIC",
    "cardia": "CARDIA",
    "chs": "CHS",
    "copdgene": "COPDGene",
    "fhs": "FHS",
    "hchs_sol": "HCHS_SOL",
    "hchs-sol": "HCHS_SOL",
    "hchssol": "HCHS_SOL",
    "jhs": "JHS",
    "mesa": "MESA",
    "whi": "WHI",
}


# ─────────────────────────────────────────────────────────────────────────────
# GRADING (same thresholds as match_quality_table.py)
# ─────────────────────────────────────────────────────────────────────────────

def grade_continuous(t_stats: dict, b_stats: dict) -> tuple[str, dict]:
    """Grade a continuous variable. Returns (grade, detail_dict)."""
    t_mean = t_stats.get("mean")
    b_mean = b_stats.get("mean")
    t_pm = t_stats.get("pct_missing", 0)
    b_pm = b_stats.get("pct_missing", 0)
    miss_diff = abs(b_pm - t_pm)

    if t_mean is None or b_mean is None:
        return "?", {"reason": "missing mean"}

    delta = abs(b_mean - t_mean)
    t_sd = t_stats.get("sd", 1) or 1
    norm_delta = delta / t_sd if t_sd > 0 else 0

    if norm_delta < 0.005 and miss_diff < 1:
        grade = "A+"
    elif norm_delta < 0.02 and miss_diff < 5:
        grade = "A"
    elif norm_delta < 0.05 and miss_diff < 10:
        grade = "B"
    elif norm_delta < 0.1 and miss_diff < 20:
        grade = "C"
    else:
        grade = "D"

    return grade, {
        "t_mean": t_mean,
        "b_mean": b_mean,
        "delta": delta,
        "norm_delta": norm_delta,
        "miss_diff": miss_diff,
    }


def grade_categorical(t_stats: dict, b_stats: dict) -> tuple[str, dict]:
    """Grade a categorical variable. Returns (grade, detail_dict)."""
    t_dist = t_stats.get("distribution", {})
    b_dist = b_stats.get("distribution", {})
    t_pm = t_stats.get("pct_missing", 0)
    b_pm = b_stats.get("pct_missing", 0)
    miss_diff = abs(b_pm - t_pm)

    all_cats = set(list(t_dist.keys()) + list(b_dist.keys()))
    max_pct_diff = 0
    for cat in all_cats:
        tp = t_dist.get(cat, {}).get("pct", 0)
        bp = b_dist.get(cat, {}).get("pct", 0)
        max_pct_diff = max(max_pct_diff, abs(bp - tp))

    if max_pct_diff < 0.5 and miss_diff < 1:
        grade = "A+"
    elif max_pct_diff < 1 and miss_diff < 5:
        grade = "A"
    elif max_pct_diff < 3 and miss_diff < 10:
        grade = "B"
    elif max_pct_diff < 10 and miss_diff < 20:
        grade = "C"
    else:
        grade = "D"

    return grade, {
        "max_pct_diff": max_pct_diff,
        "miss_diff": miss_diff,
    }


def grade_variable(var_name: str, t_stats: dict, b_stats: dict, cohort: str = "") -> tuple[str, dict]:
    """Grade a single variable. Appends * for known methodological diffs."""
    if t_stats.get("type") == "continuous":
        grade, detail = grade_continuous(t_stats, b_stats)
    else:
        grade, detail = grade_categorical(t_stats, b_stats)

    if cohort and KNOWN_METHODOLOGICAL_DIFFS.get((cohort.upper(), var_name)):
        entry = KNOWN_METHODOLOGICAL_DIFFS[(cohort.upper(), var_name)]
        if not entry.get("no_override"):
            grade = grade + "*"
            detail["reason"] = entry["code"]

    return grade, detail


# ─────────────────────────────────────────────────────────────────────────────
# FILE DISCOVERY
# ─────────────────────────────────────────────────────────────────────────────

def discover_bdc_jsons(bdc_dir: Path) -> dict[str, Path]:
    """Find the latest BDC summary JSON for each cohort in bdc_dir.

    Returns dict mapping cohort key (e.g. 'ARIC') to file path.
    """
    pattern = re.compile(r"bdc_(\w+)_summary_(\d{8}_\d{6})\.json")
    cohort_files: dict[str, list[tuple[str, Path]]] = {}

    for f in sorted(bdc_dir.glob("bdc_*_summary_*.json")):
        m = pattern.match(f.name)
        if not m:
            continue
        raw_cohort = m.group(1).lower()
        timestamp = m.group(2)
        cohort_key = COHORT_ALIASES.get(raw_cohort)
        if not cohort_key:
            continue
        cohort_files.setdefault(cohort_key, []).append((timestamp, f))

    # Pick latest timestamp per cohort
    result = {}
    for cohort_key, entries in cohort_files.items():
        entries.sort(key=lambda x: x[0], reverse=True)
        result[cohort_key] = entries[0][1]

    return result


def find_topmed_json(topmed_dir: Path, cohort_key: str) -> Path | None:
    """Find the TOPMed reference JSON for a cohort."""
    # Naming convention: topmed_<cohort>_summary.json
    candidates = [
        topmed_dir / f"topmed_{cohort_key.lower()}_summary.json",
        topmed_dir / f"topmed_{cohort_key}_summary.json",
    ]
    # Handle HCHS_SOL variant
    if cohort_key == "HCHS_SOL":
        candidates.extend([
            topmed_dir / "topmed_hchs_sol_summary.json",
            topmed_dir / "topmed_hchssol_summary.json",
        ])
    for c in candidates:
        if c.exists():
            return c
    return None


# ─────────────────────────────────────────────────────────────────────────────
# PER-COHORT SCORECARD
# ─────────────────────────────────────────────────────────────────────────────

def run_cohort_scorecard(topmed_path: Path, bdc_path: Path, all_vars: bool = False) -> dict:
    """Run scorecard for one cohort. Returns structured result dict."""
    with open(topmed_path) as f:
        t = json.load(f)
    with open(bdc_path) as f:
        b = json.load(f)

    tv = t["variables"]
    bv = b["variables"]
    intersection = set(tv) & set(bv)

    cohort_name = t.get("metadata", {}).get("cohort", bdc_path.stem.split("_")[1].upper())

    if all_vars:
        matched = sorted(intersection)
    else:
        matched = sorted(intersection & CORE_VARIABLES)

    t_only = sorted(set(tv) - set(bv))
    b_only = sorted(set(bv) - set(tv))

    grades = {"A+": 0, "A": 0, "B": 0, "C": 0, "D": 0}
    n_noted = 0
    variable_grades = {}

    for var in matched:
        grade, detail = grade_variable(var, tv[var], bv[var], cohort=cohort_name)
        base_grade = grade.rstrip("*")
        if base_grade in grades:
            grades[base_grade] += 1
        if grade.endswith("*"):
            n_noted += 1
        variable_grades[var] = {"grade": grade, **detail}

    total_graded = grades["A+"] + grades["A"] + grades["B"] + grades["C"] + grades["D"]
    pct_ab = ((grades["A+"] + grades["A"] + grades["B"]) / total_graded * 100) if total_graded > 0 else 0

    return {
        "cohort": cohort_name,
        "topmed_n": t.get("total_participants", 0),
        "bdc_n": b.get("total_participants", 0),
        "matched_vars": len(matched),
        "topmed_only": len(t_only),
        "bdc_only": len(b_only),
        "grades": grades,
        "n_noted": n_noted,
        "pct_ab": pct_ab,
        "variable_grades": variable_grades,
        "topmed_file": str(topmed_path.name),
        "bdc_file": str(bdc_path.name),
    }


# ─────────────────────────────────────────────────────────────────────────────
# FORMATTED OUTPUT
# ─────────────────────────────────────────────────────────────────────────────

def format_cohort_scorecard(result: dict) -> str:
    """Format a single cohort scorecard as text."""
    lines = []
    g = result["grades"]
    lines.append(f"{'='*70}")
    lines.append(f"  {result['cohort']} — Match Quality Scorecard")
    lines.append(f"{'='*70}")
    lines.append(f"  TOPMed N: {result['topmed_n']:>10,}    BDC N: {result['bdc_n']:>10,}")
    lines.append(f"  Matched: {result['matched_vars']}    TOPMed-only: {result['topmed_only']}    BDC-only: {result['bdc_only']}")
    lines.append(f"  Grades:  A+={g['A+']}  A={g['A']}  B={g['B']}  C={g['C']}  D={g['D']}")
    if result.get('n_noted'):
        lines.append(f"  (* = {result['n_noted']} variable(s) with known methodological notes)")
    lines.append(f"  A+B rate: {result['pct_ab']:.0f}%")
    lines.append("")
    lines.append(f"  {'Variable':<35} {'Type':<5} {'Grade':<6}")
    lines.append(f"  {'-'*50}")

    for var, detail in sorted(result["variable_grades"].items()):
        lines.append(f"  {var:<35} {'cont' if 't_mean' in detail else 'cat':<5} {detail['grade']:<6}")

    lines.append("")
    return "\n".join(lines)


def format_cross_cohort_summary(results: list[dict], timestamp: str) -> str:
    """Format cross-cohort summary table."""
    lines = []
    lines.append(f"{'='*90}")
    lines.append(f"  DCCCompareBatch — Cross-Cohort Scorecard Summary")
    lines.append(f"  Generated: {timestamp}")
    lines.append(f"{'='*90}")
    lines.append("")

    # Header
    lines.append(f"  {'Cohort':<12} {'TOPMed N':>10} {'BDC N':>10} {'Match':>5} {'A+':>4} {'A':>4} {'B':>4} {'C':>4} {'D':>4} {'*':>4} {'A+B%':>6} {'Grade':>6}")
    lines.append(f"  {'-'*80}")

    # Sort by cohort name
    for r in sorted(results, key=lambda x: x["cohort"]):
        g = r["grades"]
        # Overall grade based on A+B percentage
        if r["pct_ab"] >= 80:
            overall = "GOOD"
        elif r["pct_ab"] >= 60:
            overall = "FAIR"
        elif r["pct_ab"] >= 40:
            overall = "POOR"
        else:
            overall = "CRIT"

        lines.append(
            f"  {r['cohort']:<12} {r['topmed_n']:>10,} {r['bdc_n']:>10,} "
            f"{r['matched_vars']:>5} {g['A+']:>4} {g['A']:>4} {g['B']:>4} {g['C']:>4} {g['D']:>4} {r.get('n_noted',0):>4} "
            f"{r['pct_ab']:>5.0f}% {overall:>6}"
        )

    lines.append(f"  {'-'*80}")

    # Totals
    total_a = sum(r["grades"]["A"] for r in results)
    total_b = sum(r["grades"]["B"] for r in results)
    total_c = sum(r["grades"]["C"] for r in results)
    total_d = sum(r["grades"]["D"] for r in results)
    total_m = sum(r["grades"].get("M", 0) for r in results)
    total_q = sum(r["grades"]["?"] for r in results)
    total_graded = total_a + total_b + total_c + total_d
    total_pct = ((total_a + total_b) / total_graded * 100) if total_graded > 0 else 0

    lines.append(
        f"  {'TOTAL':<12} {'':>10} {'':>10} "
        f"{'':>5} {total_a:>4} {total_b:>4} {total_c:>4} {total_d:>4} {total_m:>4} {total_q:>4} "
        f"{total_pct:>5.0f}%"
    )
    lines.append("")

    # Legend
    lines.append("  Grade thresholds:")
    lines.append("    Continuous: A=normDelta<0.02, B<0.05, C<0.1, D>=0.1  (+ missing% diff)")
    lines.append("    Categorical: A=maxPctDiff<1pp, B<3pp, C<10pp, D>=10pp (+ missing% diff)")
    lines.append("    Overall: GOOD=80%+ A+B, FAIR=60%+, POOR=40%+, CRIT=<40%")
    lines.append("")

    # D-grade hot list (variables graded D across cohorts)
    lines.append(f"  {'='*70}")
    lines.append(f"  D-Grade Hot List (variables with D in any cohort)")
    lines.append(f"  {'='*70}")
    lines.append("")

    # Collect all D-grade variables per cohort
    d_vars: dict[str, list[str]] = {}
    for r in results:
        for var, detail in r["variable_grades"].items():
            if detail["grade"] == "D":
                d_vars.setdefault(var, []).append(r["cohort"])

    if d_vars:
        lines.append(f"  {'Variable':<35} {'D Count':>7}  Cohorts")
        lines.append(f"  {'-'*70}")
        for var in sorted(d_vars, key=lambda v: -len(d_vars[v])):
            cohorts_str = ", ".join(sorted(d_vars[var]))
            lines.append(f"  {var:<35} {len(d_vars[var]):>7}  {cohorts_str}")
    else:
        lines.append("  (none)")

    lines.append("")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="DCCCompareBatch: Cross-cohort match quality scorecards"
    )
    parser.add_argument(
        "--bdc-dir", type=Path, default=DEFAULT_BDC_DIR,
        help="Directory containing BDC summary JSONs",
    )
    parser.add_argument(
        "--topmed-dir", type=Path, default=DEFAULT_TOPMED_DIR,
        help="Directory containing TOPMed reference JSONs",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
        help="Directory for output scorecards",
    )
    parser.add_argument(
        "--cohorts", nargs="*", default=None,
        help="Limit to specific cohorts (e.g., ARIC CHS FHS)",
    )
    parser.add_argument(
        "--all-vars", action="store_true", default=False,
        help="Score all matched variables instead of the 28-variable core set",
    )
    args = parser.parse_args()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # Discover BDC JSONs
    bdc_files = discover_bdc_jsons(args.bdc_dir)
    if not bdc_files:
        print(f"ERROR: No BDC summary JSONs found in {args.bdc_dir}", file=sys.stderr)
        sys.exit(1)

    # Filter to requested cohorts
    if args.cohorts:
        requested = set()
        for c in args.cohorts:
            key = COHORT_ALIASES.get(c.lower(), c.upper())
            requested.add(key)
        bdc_files = {k: v for k, v in bdc_files.items() if k in requested}

    print(f"DCCCompareBatch — {len(bdc_files)} cohort(s) discovered")
    for cohort, path in sorted(bdc_files.items()):
        print(f"  {cohort}: {path.name}")
    print()

    # Process each cohort
    results = []
    for cohort_key in sorted(bdc_files):
        bdc_path = bdc_files[cohort_key]
        topmed_path = find_topmed_json(args.topmed_dir, cohort_key)

        if topmed_path is None:
            print(f"  SKIP {cohort_key}: no TOPMed reference JSON found")
            continue

        print(f"  Scoring {cohort_key}...", end=" ", flush=True)
        result = run_cohort_scorecard(topmed_path, bdc_path, all_vars=args.all_vars)
        results.append(result)
        g = result["grades"]
        print(f"A={g['A']} B={g['B']} C={g['C']} D={g['D']} M={g.get('M',0)}  ({result['pct_ab']:.0f}% A+B)")

    if not results:
        print("\nERROR: No cohorts could be scored.", file=sys.stderr)
        sys.exit(1)

    # Write outputs
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Per-cohort scorecards
    for r in results:
        cohort_file = args.output_dir / f"{r['cohort']}_scorecard_{timestamp}.txt"
        with open(cohort_file, "w", encoding="utf-8") as f:
            f.write(format_cohort_scorecard(r))

    # Cross-cohort summary
    summary_file = args.output_dir / f"cross_cohort_summary_{timestamp}.txt"
    summary_text = format_cross_cohort_summary(results, timestamp)
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(summary_text)

    # Also print summary to stdout
    print()
    print(summary_text)
    print(f"Scorecards written to: {args.output_dir}")

    # JSON export for programmatic consumption
    json_file = args.output_dir / f"cross_cohort_summary_{timestamp}.json"
    json_export = {
        "timestamp": timestamp,
        "cohorts": {
            r["cohort"]: {
                "topmed_n": r["topmed_n"],
                "bdc_n": r["bdc_n"],
                "matched_vars": r["matched_vars"],
                "topmed_only": r["topmed_only"],
                "bdc_only": r["bdc_only"],
                "grades": r["grades"],
                "pct_ab": r["pct_ab"],
                "topmed_file": r["topmed_file"],
                "bdc_file": r["bdc_file"],
                "variable_grades": r["variable_grades"],
            }
            for r in results
        },
    }
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(json_export, f, indent=2)


if __name__ == "__main__":
    main()
