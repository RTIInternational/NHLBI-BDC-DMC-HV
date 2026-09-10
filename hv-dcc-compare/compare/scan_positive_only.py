#!/usr/bin/env python3
"""
scan_positive_only.py -- find categorical variables emitting only the
affirmative case

Several BDC transforms emit a category only when the answer is "yes" and leave
the negative arm null, so participants who do NOT have the condition become
missing rather than negative:

    WHI coronary angioplasty   reference 1,467 prior / 139,657 no
                               BDC       1,467 prior /       0 no   (-> null)

The affirmative arm is harmonized correctly -- WHI's positive count matches the
reference exactly -- but a dataset that cannot separate "no prior angioplasty"
from "we don't know" breaks every denominator, prevalence and unexposed-group
comparison built on it. That is a defect on its own terms, independent of any
comparison against TOPMed.

Read-only. It classifies and counts; it changes nothing and fixes nothing,
because whether a source form can justify emitting an explicit negative is a
per-table curation judgement (a checklist supports it, free text usually does
not).

FINDINGS

  CONFIRMED  BDC emits one category, the reference emits two or more, and the
             categories BDC lacks account for its extra missing. Strongest
             evidence: the data exists on the reference side.

  PARTIAL    BDC emits several categories but is missing one the reference has.
             Same defect, narrower.

  SUSPECTED  BDC emits one category with high missingness and there is no
             reference counterpart to check against. These are the ones no
             comparison report can surface -- the reason for scanning rather
             than reading the D-grade list.

  (A single category with LOW missingness is not reported: a genuinely uniform
  population, e.g. an all-Hispanic cohort's ethnicity, looks like that and is
  correct.)

Usage:
    python compare/scan_positive_only.py --bdc-dir runs/<ts>/bdc
    python compare/scan_positive_only.py --bdc-dir runs/<ts>/bdc \\
        --topmed-dir /data/topmed-dcc-summaries        # enables CONFIRMED/PARTIAL
    python compare/scan_positive_only.py --bdc-dir runs/<ts>/bdc --verbose
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Missingness above which a single-category variable is suspicious. Below it,
# a lone category is far more likely to be a uniform population than a dropped
# negative arm.
DEFAULT_MISSING_THRESHOLD = 25.0

# Category names that read as an explicit negative. Used only to say whether a
# variable that DOES emit two categories is already doing the right thing.
NEGATIVE_HINTS = {
    "no", "no prior history", "not current smoker", "never smoked",
    "not exposed", "unaffected", "absent", "not hispanic or latino",
    "control", "negative", "none",
}


def load_summaries(directory: Path, pattern: str) -> dict[str, dict]:
    """cohort -> variables dict, from summary JSONs in a directory."""
    out: dict[str, dict] = {}
    for path in sorted(directory.glob(pattern)):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  WARNING: skipping {path.name}: {exc}", file=sys.stderr)
            continue
        cohort = (doc.get("metadata", {}).get("cohort")
                  or doc.get("cohort", {}).get("name")
                  or path.stem)
        if "all_cohorts" in path.name:
            continue
        out[cohort.upper()] = doc.get("variables", {})
    return out


def categories(stats: dict) -> list[str]:
    dist = stats.get("distribution") or {}
    # The pooled small-cell bucket is not a real category.
    return [k for k in dist if not k.startswith("Other (n<")]


def is_binaryish(stats: dict) -> bool:
    return stats.get("type") == "categorical"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Find BDC categorical variables that emit only the affirmative case."
    )
    ap.add_argument("--bdc-dir", required=True, type=Path,
                    help="Directory of bdc_*_summary_*.json.")
    ap.add_argument("--topmed-dir", type=Path, default=None,
                    help="Directory of topmed_*_summary.json. Enables CONFIRMED/PARTIAL.")
    ap.add_argument("--missing-threshold", type=float, default=DEFAULT_MISSING_THRESHOLD,
                    help=f"%%-missing above which a lone category is suspicious "
                         f"(default {DEFAULT_MISSING_THRESHOLD}).")
    ap.add_argument("--verbose", action="store_true",
                    help="Show every affected variable, not just a per-cohort roll-up.")
    args = ap.parse_args()

    if not args.bdc_dir.is_dir():
        print(f"ERROR: --bdc-dir not found: {args.bdc_dir}", file=sys.stderr)
        return 1

    bdc = load_summaries(args.bdc_dir, "bdc_*_summary_*.json")
    if not bdc:
        print(f"ERROR: no bdc_*_summary_*.json in {args.bdc_dir}", file=sys.stderr)
        return 1
    topmed = (load_summaries(args.topmed_dir, "topmed_*_summary.json")
              if args.topmed_dir and args.topmed_dir.is_dir() else {})

    print("=" * 78)
    print("  Categorical variables emitting only the affirmative case")
    print("=" * 78)
    print(f"  cohorts        : {len(bdc)}")
    print(f"  reference side : {'available (' + str(len(topmed)) + ' cohorts)' if topmed else 'NOT supplied -- CONFIRMED/PARTIAL disabled'}")
    print(f"  missing floor  : {args.missing_threshold:.0f}%")
    print()

    confirmed: list[tuple] = []
    partial: list[tuple] = []
    suspected: list[tuple] = []

    for cohort, variables in sorted(bdc.items()):
        tvars = topmed.get(cohort, {})
        for var, stats in sorted(variables.items()):
            if not is_binaryish(stats):
                continue
            cats = categories(stats)
            pct_missing = float(stats.get("pct_missing") or 0.0)
            label = stats.get("bdc_label", var)
            tstats = tvars.get(var)
            tcats = categories(tstats) if tstats else []

            if tcats and len(cats) < len(tcats):
                missing_cats = [c for c in tcats if c not in cats]
                row = (cohort, var, label, cats, missing_cats, pct_missing)
                (confirmed if len(cats) <= 1 else partial).append(row)
            elif not tstats and len(cats) == 1 and pct_missing >= args.missing_threshold:
                suspected.append((cohort, var, label, cats, [], pct_missing))

    def emit(title: str, rows: list[tuple], note: str) -> None:
        print("-" * 78)
        print(f"  {title}  ({len(rows)})")
        print(f"  {note}")
        print("-" * 78)
        if not rows:
            print("    none")
            print()
            return
        by_var: dict[str, list[str]] = defaultdict(list)
        for cohort, var, *_ in rows:
            by_var[var].append(cohort)
        for var, cohorts in sorted(by_var.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            print(f"    {var:34} {len(cohorts)} cohort(s): {', '.join(sorted(cohorts))}")
        if args.verbose:
            print()
            for cohort, var, label, cats, missing_cats, pct in sorted(rows):
                print(f"    {cohort:9} {label} ({var})")
                print(f"      emits   : {cats or '(nothing)'}   missing {pct:.1f}%")
                if missing_cats:
                    print(f"      lacks   : {missing_cats}")
        print()

    emit("CONFIRMED", confirmed,
         "BDC emits one category; the reference emits more. The data exists.")
    emit("PARTIAL", partial,
         "BDC emits several categories but lacks one the reference has.")
    emit("SUSPECTED", suspected,
         "One category, high missingness, no reference counterpart to check.")

    total = len(confirmed) + len(partial) + len(suspected)
    affected_vars = {r[1] for r in confirmed + partial + suspected}
    affected_cohorts = {r[0] for r in confirmed + partial + suspected}
    print("=" * 78)
    print(f"  {total} cohort-variable instance(s); "
          f"{len(affected_vars)} distinct variable(s); "
          f"{len(affected_cohorts)} of {len(bdc)} cohorts affected.")
    if not topmed:
        print("  Pass --topmed-dir to separate CONFIRMED from SUSPECTED.")
    print("  Nothing was changed. Whether a source form can justify an explicit")
    print("  negative is a per-table curation decision.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
