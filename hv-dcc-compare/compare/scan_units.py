#!/usr/bin/env python3
"""
scan_units.py -- find continuous variables whose values do not fit their unit

The declared unit for every variable comes from config.py and is asserted, not
read from the data. Both sides of a comparison are labelled from that same
config, so a unit disagreement between the datasets is invisible by
construction: the report prints one merged unit and a large mean delta with no
indication why.

This scan looks for the two signatures a wrong unit leaves behind.

  SCALE OUTLIER   One cohort's mean is an order of magnitude away from the
                  other cohorts' for the same variable. This is how FHS white
                  blood cell count was found: 62.6 against 5.6-6.5 everywhere
                  else, which turned out to be a source variable recorded on a
                  10x scale under a 10*3/uL label (issue #814). Cross-cohort
                  agreement is the strongest available evidence because the
                  same variable should mean the same thing in every cohort.

  IMPLAUSIBLE     A high proportion of values outside the plausible range
                  configured for the variable. A wrong unit pushes most of a
                  distribution out of range at once, so a high percentage is
                  more suggestive of a unit problem than of outliers.

  UNIT MISMATCH   Where the extract recorded an observed unit alongside the
                  declared one, the two disagree. Only available for summaries
                  produced after observed-unit capture was added.

Read-only. It reports suspicion, not conclusions: a genuine population
difference can look like a scale outlier, and a cohort with one variable in
different units is a harmonization question, not something a scan should
decide.

Usage:
    python compare/scan_units.py --bdc-dir runs/<ts>/bdc
    python compare/scan_units.py --bdc-dir runs/<ts>/bdc --ratio 3
    python compare/scan_units.py --bdc-dir runs/<ts>/bdc --verbose
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# A cohort mean this many times away from the cross-cohort median is treated as
# a scale outlier. 5 sits below a factor-of-10 error and above the largest
# genuine between-cohort differences seen in practice.
DEFAULT_RATIO = 5.0

# Percentage of values outside the configured plausible range above which a
# unit problem is more likely than ordinary outliers.
DEFAULT_IMPLAUSIBLE_PCT = 20.0

# A variable needs means from at least this many cohorts before a cross-cohort
# comparison means anything.
MIN_COHORTS_FOR_RATIO = 3


def load_summaries(directory: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in sorted(directory.glob("bdc_*_summary_*.json")):
        if "all_cohorts" in path.name:
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  WARNING: skipping {path.name}: {exc}", file=sys.stderr)
            continue
        cohort = doc.get("metadata", {}).get("cohort") or path.stem
        out[cohort.upper()] = doc.get("variables", {})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Find continuous variables whose values do not fit their declared unit."
    )
    ap.add_argument("--bdc-dir", required=True, type=Path,
                    help="Directory of bdc_*_summary_*.json.")
    ap.add_argument("--ratio", type=float, default=DEFAULT_RATIO,
                    help=f"Fold-difference from the cross-cohort median mean that "
                         f"counts as a scale outlier (default {DEFAULT_RATIO}).")
    ap.add_argument("--implausible-pct", type=float, default=DEFAULT_IMPLAUSIBLE_PCT,
                    help=f"%% implausible above which to report (default "
                         f"{DEFAULT_IMPLAUSIBLE_PCT}).")
    ap.add_argument("--verbose", action="store_true",
                    help="Show every cohort's mean for each flagged variable.")
    args = ap.parse_args()

    if not args.bdc_dir.is_dir():
        print(f"ERROR: --bdc-dir not found: {args.bdc_dir}", file=sys.stderr)
        return 1
    bdc = load_summaries(args.bdc_dir)
    if not bdc:
        print(f"ERROR: no bdc_*_summary_*.json in {args.bdc_dir}", file=sys.stderr)
        return 1

    # variable -> cohort -> stats
    by_var: dict[str, dict[str, dict]] = defaultdict(dict)
    for cohort, variables in bdc.items():
        for var, stats in variables.items():
            if isinstance(stats, dict) and stats.get("type") == "continuous":
                by_var[var][cohort] = stats

    print("=" * 78)
    print("  Continuous variables whose values do not fit their declared unit")
    print("=" * 78)
    print(f"  cohorts            : {len(bdc)}")
    print(f"  continuous variables: {sum(len(v) for v in by_var.values())} "
          f"instances across {len(by_var)} distinct variables")
    print(f"  scale outlier at   : {args.ratio}x from the cross-cohort median mean")
    print(f"  implausible floor  : {args.implausible_pct:.0f}%")
    print()

    scale_rows: list[tuple] = []
    implausible_rows: list[tuple] = []
    mismatch_rows: list[tuple] = []
    observed_seen = False

    for var, per_cohort in sorted(by_var.items()):
        means = {c: s.get("mean") for c, s in per_cohort.items()
                 if isinstance(s.get("mean"), (int, float)) and s.get("mean")}
        median_mean = (statistics.median(means.values())
                       if len(means) >= MIN_COHORTS_FOR_RATIO else None)

        for cohort, stats in sorted(per_cohort.items()):
            unit = stats.get("unit") or "(none)"
            mean = stats.get("mean")
            n_valid = stats.get("n_valid") or 0
            n_imp = stats.get("n_implausible") or 0

            # Scale outlier against the other cohorts.
            if median_mean and isinstance(mean, (int, float)) and mean:
                fold = max(abs(mean), abs(median_mean)) / min(abs(mean), abs(median_mean))
                if fold >= args.ratio:
                    scale_rows.append((fold, var, cohort, mean, median_mean, unit,
                                       sorted(means.items())))

            # Implausible proportion.
            if n_valid and n_imp:
                pct = n_imp / n_valid * 100
                if pct >= args.implausible_pct:
                    implausible_rows.append((pct, var, cohort, n_imp, n_valid, unit, mean))

            # Observed vs declared unit, when the extract recorded it.
            observed = stats.get("unit_observed")
            if observed:
                observed_seen = True
                if str(observed).strip() and str(observed).strip() != str(unit).strip():
                    mismatch_rows.append((var, cohort, unit, observed))

    def section(title: str, note: str, rows: list, render) -> None:
        print("-" * 78)
        print(f"  {title}  ({len(rows)})")
        print(f"  {note}")
        print("-" * 78)
        if not rows:
            print("    none")
        else:
            for r in rows:
                render(r)
        print()

    def render_scale(r) -> None:
        fold, var, cohort, mean, med, unit, means = r
        print(f"    {cohort:9} {var:30} mean={mean:<12.4g} "
              f"other cohorts median={med:<10.4g} {fold:5.1f}x   unit={unit}")
        if args.verbose:
            others = "  ".join(f"{c}={m:.4g}" for c, m in means)
            print(f"      all cohorts: {others}")

    def render_imp(r) -> None:
        pct, var, cohort, n_imp, n_valid, unit, mean = r
        print(f"    {cohort:9} {var:30} {pct:5.1f}% implausible "
              f"({n_imp:,}/{n_valid:,})  mean={mean}  unit={unit}")

    def render_mismatch(r) -> None:
        var, cohort, declared, observed = r
        print(f"    {cohort:9} {var:30} declared={declared!r} observed={observed!r}")

    section("SCALE OUTLIER", "One cohort's mean is far from the others for the same variable.",
            sorted(scale_rows, reverse=True), render_scale)
    section("IMPLAUSIBLE PROPORTION", "Most of the distribution falls outside the configured range.",
            sorted(implausible_rows, reverse=True), render_imp)
    section("DECLARED vs OBSERVED UNIT",
            "The extract's own unit column disagrees with config."
            if observed_seen else
            "No summary recorded an observed unit -- re-extract to enable this check.",
            mismatch_rows, render_mismatch)

    flagged = {(r[1], r[2]) for r in scale_rows} | {(r[1], r[2]) for r in implausible_rows} \
              | {(r[0], r[1]) for r in mismatch_rows}
    print("=" * 78)
    print(f"  {len(flagged)} cohort-variable instance(s) flagged across "
          f"{len({f[0] for f in flagged})} variable(s).")
    print("  Nothing was changed. Two cautions before acting:")
    print("   - a scale outlier can be a real population difference;")
    print("   - the flagged cohort is not necessarily the WRONG one. Vegetable")
    print("     servings flags JHS at 2.5/day, which is plausible, against 15-25/day")
    print("     elsewhere, which is not. The majority can be the error.")
    print("  Confirm against the dbGaP data dictionary for each source variable.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
