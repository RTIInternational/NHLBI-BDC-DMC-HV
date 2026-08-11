#!/usr/bin/env python
"""Every cell that ever changed in the published Table S4, grouped by cause.

The point of this script is to make "why did this number change?" answerable
without rerunning the old pipeline.  The old pipeline read three live Google
Sheets that have since moved, so a rerun would exercise the code path but could
not reproduce the historical numbers anyway.  What *is* reproducible is the pair
(sheet export, committed pipeline CSV) at each point in time -- and those pin
every change to either a code commit or an input-sheet edit.

Causes assigned here:

  code <commit>   a pipeline code commit lands between the two sheet versions
                  and is the only thing that could have moved the number
  input sheet     no code commit in the window; the curator-maintained Google
                  Sheets the pipeline read must have changed
  hand edit       the sheet changed while no pipeline CSV did -- someone typed
                  in the spreadsheet

Usage:
    ./.venv/bin/python transform_assessment/s4_count_investigation/change_ledger.py
    ... --detail            # list every changed cell, not just counts
    ... --csv ledger.csv    # write the full ledger for spreadsheet review
"""
from __future__ import annotations

import argparse
import csv as csvmod
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s4_sheets import fmt, load_csv, load_xlsx  # noqa: E402

HERE = Path(__file__).resolve().parent
XLSX_DIR = HERE / "xlsx"
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

# Old-pipeline code revisions, with whether each one could move numbers.
# "no" entries are still listed so the ledger can show that a window containing
# a commit is nonetheless explained by something else.
CODE_COMMITS = [
    ("16cd942e", "2025-08-27", True, "initial implementation"),
    ("ce27257c", "2025-08-27", True,
     "'Fixed N values': parse n directly, and count cohorts with no valid-phvs "
     "list instead of skipping them (origin of the ARIC/CARDIA/JHS unfiltered counts)"),
    ("903f6d41", "2025-08-28", True, "'Got it working with the two other sheets': COPDGene + FHS added"),
    ("c72e781c", "2025-12-09", True, "filter out rows whose Transform Comment is 'out of scope'"),
    ("0a438db2", "2026-06-25", False, "--debug-variable dump + regex raw-string fix; no counting change"),
]

# Committed outputs of the old pipeline, path as of that commit.
CSV_COMMITS = [
    ("ce27257c", "2025-08-27", "transform_assessment/preharmonized_qaqc_report.csv"),
    ("903f6d41", "2025-08-28", "transform_assessment/preharmonized_qaqc_report.csv"),
    ("1e6a34db", "2025-12-11", "transform_assessment/preharmonized_qaqc_report.csv"),
    ("31bd764a", "2026-06-09", "transform_assessment/preharmonized_qaqc_report.csv"),
]


def git_show(commit: str, path: str, dest: Path) -> Path | None:
    if dest.exists():
        return dest
    blob = subprocess.run(["git", "show", f"{commit}:{path}"], capture_output=True, text=True)
    if blob.returncode:
        return None
    dest.write_text(blob.stdout)
    return dest


def load_sheets() -> dict[str, tuple]:
    out = {}
    for p in sorted(XLSX_DIR.glob("*.xlsx")):
        m = DATE_RE.search(p.name)
        if m:
            labels, rows, cohorts = load_xlsx(p, drop_totals=True)
            out[m.group(1)] = (rows, cohorts)
    return out


def load_csvs(tmp: Path) -> dict[str, dict]:
    out = {}
    for commit, date, path in CSV_COMMITS:
        f = git_show(commit, path, tmp / f"ledger_{commit}.csv")
        if f:
            _, rows = load_csv(f)
            out[date] = (commit, rows)
    return out


def csv_distances(rows: dict, cohorts: list, csvs: dict) -> dict[str, tuple[str, int, int]]:
    """Distance from this sheet state to every committed pipeline CSV.

    Returns {csv_date: (commit, differing_cells, shared_labels)}.  Comparing the
    sheet against the CSVs directly is what distinguishes "someone pasted a new
    pipeline run" from "someone typed in the spreadsheet"; a window-based guess
    gets this backwards, because a repaste can land months after the CSV was
    committed and a hand edit can happen in the same window as one.

    Distances are only comparable *between CSVs for one sheet*, not across
    sheets: each pair shares a different label set, so the denominators differ.
    """
    out = {}
    for date, (commit, crows) in csvs.items():
        common = [l for l in crows if l in rows]
        if not common:
            continue
        d = sum(1 for l in common for co in cohorts if crows[l].get(co) != rows[l].get(co))
        out[date] = (commit, d, len(common))
    return out


def best_csv_match(rows: dict, cohorts: list, csvs: dict) -> tuple[str, str, int]:
    """The single closest CSV: (csv_date, commit, differing_cells)."""
    dists = csv_distances(rows, cohorts, csvs)
    if not dists:
        return (None, None, 10**9)
    date = min(dists, key=lambda d: dists[d][1])
    commit, diffs, _ = dists[date]
    return (date, commit, diffs)


def classify(prev_date: str, date: str, csvs: dict, sheets: dict) -> tuple[str, str]:
    """Why did the sheet change between these two dates?

    Decided by what the sheet *became*, not by what happened to sit in the same
    date window: if the new state matches a committed pipeline CSV, it is a
    paste of that run, and the cause is whatever produced that run (a code
    commit, or an input-sheet change if no code moved).  If it matches nothing,
    someone edited the spreadsheet.
    """
    rows, cohorts = sheets[date]
    prev_rows, _ = sheets[prev_date]
    now = best_csv_match(rows, cohorts, csvs)
    before = best_csv_match(prev_rows, cohorts, csvs)
    csv_date, _, diffs = now
    prev_csv_date, _, prev_diffs = before

    if csv_date != prev_csv_date:
        # The sheet is now closest to a *different* pipeline run: it was
        # repasted.  Whatever produced that newer run is the cause -- a code
        # commit landing between the two runs, or, if none did, a change in the
        # curator-maintained source sheets.
        moving = [(c, d, why) for c, d, moves, why in CODE_COMMITS
                  if moves and (prev_csv_date or "0000") < d <= csv_date]
        if moving:
            c, _, why = moving[-1]
            return f"code {c}", why
        return "input sheet", ("pasted a rerun with no code change since the previous run -- "
                               "the curator-maintained source sheets moved")
    # Same run as before, but the numbers moved: the spreadsheet was edited.
    if diffs > prev_diffs:
        return "hand edit", "sheet edited away from the pipeline output it had matched"
    if diffs < prev_diffs:
        return "hand edit", "sheet hand-corrected toward the pipeline output it was matching"
    return "hand edit", "no pipeline output matches this state; the spreadsheet was edited directly"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--detail", action="store_true", help="list every changed cell")
    ap.add_argument("--csv", type=Path, help="write the full ledger to this path")
    ap.add_argument("--tmp", type=Path, default=Path("/tmp/claude-504"))
    args = ap.parse_args()
    args.tmp.mkdir(parents=True, exist_ok=True)

    sheets = load_sheets()
    csvs = load_csvs(args.tmp)
    dates = sorted(sheets)

    ledger = []
    for prev, cur in zip(dates, dates[1:]):
        A, ca = sheets[prev]
        B, cb = sheets[cur]
        cohorts = sorted(set(ca) & set(cb))
        common = sorted(set(A) & set(B))
        cause, why = classify(prev, cur, csvs, sheets)
        for label in common:
            for co in cohorts:
                x, y = A[label].get(co), B[label].get(co)
                if x != y:
                    ledger.append({
                        "from": prev, "to": cur, "cause": cause, "why": why,
                        "variable": label, "cohort": co,
                        "before": fmt(x), "after": fmt(y),
                    })
        gone = sorted(set(A) - set(B))
        added = sorted(set(B) - set(A))
        for lab in gone:
            ledger.append({"from": prev, "to": cur, "cause": cause, "why": why,
                           "variable": lab, "cohort": "(row)", "before": "present", "after": "removed/renamed"})
        for lab in added:
            ledger.append({"from": prev, "to": cur, "cause": cause, "why": why,
                           "variable": lab, "cohort": "(row)", "before": "absent", "after": "added/renamed"})

    # Show the evidence the classification rests on before the classification.
    print("Which committed pipeline CSV does each sheet version match?\n")
    print(f"  {'sheet':<14}{'closest CSV':<26}{'differing cells':>16}")
    print("  " + "-" * 56)
    for d in dates:
        rows, cohorts = sheets[d]
        cdate, commit, diffs = best_csv_match(rows, cohorts, csvs)
        tag = f"{commit} ({cdate})" if commit else "-"
        mark = "  EXACT" if diffs == 0 else ""
        print(f"  {d:<14}{tag:<26}{diffs:>16}{mark}")
    print()

    print("Published Table S4 -- every change, grouped by cause\n")
    hdr = f"{'window':<26}{'cause':<20}{'cells':>7}  why"
    print(hdr)
    print("-" * 100)
    for prev, cur in zip(dates, dates[1:]):
        rows = [r for r in ledger if r["from"] == prev and r["to"] == cur]
        if not rows:
            print(f"{prev} -> {cur:<11}{'(no change)':<20}{0:>7}")
            continue
        cause, why = rows[0]["cause"], rows[0]["why"]
        cells = sum(1 for r in rows if r["cohort"] != "(row)")
        labels = sum(1 for r in rows if r["cohort"] == "(row)")
        note = why if len(why) < 60 else why[:57] + "..."
        print(f"{prev} -> {cur:<11}{cause:<20}{cells:>7}  {note}")
        if labels:
            print(f"{'':46}{labels:>7}  row labels added/removed/renamed")

    by_cause = {}
    for r in ledger:
        if r["cohort"] != "(row)":
            by_cause[r["cause"]] = by_cause.get(r["cause"], 0) + 1
    print("\n== totals by cause ==")
    for cause, n in sorted(by_cause.items(), key=lambda kv: -kv[1]):
        print(f"  {cause:<20} {n:>6} cells")

    if args.detail:
        print("\n== every changed cell ==")
        for r in ledger:
            if r["cohort"] == "(row)":
                continue
            print(f"  {r['from']}->{r['to']}  {r['cause']:<18} "
                  f"{r['variable'][:34]:<36} {r['cohort']:<9} {r['before']:>14} -> {r['after']}")

    if args.csv:
        with open(args.csv, "w", newline="") as fh:
            # csv.writer defaults to \r\n regardless of the file's newline mode.
            w = csvmod.DictWriter(fh, lineterminator="\n",
                                  fieldnames=["from", "to", "cause", "why", "variable", "cohort", "before", "after"])
            w.writeheader()
            w.writerows(ledger)
        print(f"\nwrote {len(ledger)} rows to {args.csv}")


if __name__ == "__main__":
    main()
