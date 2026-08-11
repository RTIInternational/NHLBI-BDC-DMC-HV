#!/usr/bin/env python
"""Verify that the published Table S4 is the CSV committed on 2025-12-11.

Finding this closed the central question of the investigation.  The published
sheet is not a moving target and not a corrupted paste: it is exactly the output
of the superseded pipeline as committed in `1e6a34db` ("uploading generated csv
from 2025-12-11"), pasted into the Google Sheet and never regenerated.  All 1332
compared cells match, with the same 148 labels in the same order.

That CSV is checked in beside this script as `published_source_20251211.csv`, so
the comparison runs without going through git.  To re-extract it from history:

    git show 1e6a34db:transform_assessment/preharmonized_qaqc_report.csv

Consequence: diagnose the current generator against this CSV, not against the
spreadsheet.  A difference here is a real difference between two pipelines, with
no spreadsheet handling in between to explain it away.

Usage:
    ./.venv/bin/python transform_assessment/s4_count_investigation/verify_published_source.py
    ... --csv other.csv --xlsx other.xlsx
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s4_sheets import load_csv, load_xlsx  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_CSV = HERE / "published_source_20251211.csv"
DEFAULT_XLSX = HERE / "xslx" / "s4-gsheet-2025-12-23-just-added-totals.xlsx"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    args = ap.parse_args()

    corder, C = load_csv(args.csv)
    xorder, X, cohorts = load_xlsx(args.xlsx, drop_totals=True)

    print(f"csv:  {args.csv.name}  ({len(corder)} rows)")
    print(f"xlsx: {args.xlsx.name}  ({len(xorder)} rows)\n")

    only_csv = [l for l in corder if l not in X]
    only_x = [l for l in xorder if l not in C]
    same_order = [l for l in corder if l in X] == [l for l in xorder if l in C]
    print(f"labels only in csv:  {only_csv or 'none'}")
    print(f"labels only in xlsx: {only_x or 'none'}")
    print(f"shared labels in the same order: {same_order}\n")

    common = [l for l in corder if l in X]
    diffs = [(l, co, C[l].get(co), X[l].get(co))
             for l in common for co in cohorts if C[l].get(co) != X[l].get(co)]
    total = len(common) * len(cohorts)
    print(f"cells differing: {len(diffs)}/{total}")
    for label, cohort, a, b in diffs[:25]:
        print(f"   {label[:36]:<38} {cohort:<9} csv={a}  xlsx={b}")
    if len(diffs) > 25:
        print(f"   ... and {len(diffs) - 25} more")

    if not diffs and not only_csv and not only_x and same_order:
        print("\nEXACT MATCH: the published sheet is this CSV.")


if __name__ == "__main__":
    main()
