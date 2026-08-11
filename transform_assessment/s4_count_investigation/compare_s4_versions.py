#!/usr/bin/env python
"""Compare Table S4 across dated exports of the Google Sheet.

Why this exists: the published S4 changed several times, and the changes do not
line up with changes to the transform specs.  Establishing *when* counts moved,
and whether label->count row alignment held across versions, is the entry point
to the count investigation.  ``compare_s4_to_published.py`` compares one
generated run against one published sheet; this compares published versions to
each other.

Sheet parsing, and the normalizations it depends on, live in ``s4_sheets``.

Usage:
    ./.venv/bin/python transform_assessment/s4_count_investigation/compare_s4_versions.py
    ... --dir path/to/xslx --row "Alcohol Consumption"
    ... --labels          # row-alignment check only
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s4_sheets import fmt, load_xlsx  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_DIR = HERE / "xslx"
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def version_key(path: Path) -> str:
    """Sort/label key: the date embedded in the filename, else the stem."""
    m = DATE_RE.search(path.name)
    return m.group(1) if m else path.stem


def load(path: Path) -> tuple[list[str], dict[str, dict[str, tuple]]]:
    """Labels in sheet order plus {label: {cohort: (phv, n)}}.

    Labels come back as a list as well as a dict so callers can check row *order*
    and duplication, not just membership.
    """
    labels, rows, _ = load_xlsx(path)
    return labels, rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="directory of .xlsx exports")
    ap.add_argument("--row", action="append", default=[], help="trace one label across versions (repeatable)")
    ap.add_argument("--labels", action="store_true", help="row-alignment check only")
    ap.add_argument("--max-detail", type=int, default=25,
                    help="list individual changed cells when a transition has at most this many")
    args = ap.parse_args()

    paths = sorted(args.dir.glob("*.xlsx"), key=version_key)
    if not paths:
        ap.error(f"no .xlsx files in {args.dir}")
    data = {version_key(p): load(p) for p in paths}
    versions = list(data)

    print("versions:", ", ".join(versions), end="\n\n")

    # Row alignment: duplicated labels within a version, and order changes
    # between versions.  A duplicate row is the signature of a bad paste --
    # counts were pasted positionally at cell B5 before xlsx generation existed,
    # so nothing joins a count to its label.
    print("== row alignment ==")
    for v in versions:
        labels, _ = data[v]
        dupes = {x for x in labels if labels.count(x) > 1}
        print(f"  {v}: {len(labels)} rows, {len(set(labels))} distinct" + (f"  DUPLICATED: {sorted(dupes)}" if dupes else ""))
    for a, b in zip(versions, versions[1:]):
        la, lb = data[a][0], data[b][0]
        # Compare the shared labels as *sequences*, after dropping duplicates.
        # A repeated row shifts every later position by one without reordering
        # anything, and comparing raw positions reports that as a reordering --
        # which is how the 2026-06-25 duplicate was first misread.
        sa = list(dict.fromkeys(x for x in la if x in set(lb)))
        sb = list(dict.fromkeys(x for x in lb if x in set(la)))
        note = "shared labels in the same order" if sa == sb else (
            f"{sum(x != y for x, y in zip(sa, sb))} shared labels in a different relative order")
        print(f"  {a} -> {b}: {note}")
    print()

    if args.labels:
        return

    # Cell-level drift between consecutive versions.
    print("== cell changes between consecutive versions ==")
    for a, b in zip(versions, versions[1:]):
        _, A = data[a]
        _, B = data[b]
        common = set(A) & set(B)
        cohorts = (
            set().union(*[set(v) for v in A.values()]) & set().union(*[set(v) for v in B.values()])
        ) - {"TOTALS"}
        diffs = [(lab, co) for lab in common for co in cohorts if A[lab].get(co) != B[lab].get(co)]
        print(
            f"  {a} -> {b}: labels {len(A)}->{len(B)} (common {len(common)}), "
            f"cells differing {len(diffs)}/{len(common) * len(cohorts)}"
        )
        # When a transition is small, the individual cells are the finding --
        # print them rather than making the reader write another script.
        if diffs and len(diffs) <= args.max_detail:
            for lab, co in diffs:
                print(f"      {lab[:38]:<40} {co:<9} {fmt(A[lab][co]):>14} -> {fmt(B[lab][co])}")
        for tag, extra in ((a, set(A) - set(B)), (b, set(B) - set(A))):
            if extra:
                print(f"      labels only in {tag}: {sorted(extra)}")
    print()

    for target in args.row:
        print(f"== {target} ==")
        for v in versions:
            _, rows = data[v]
            row = rows.get(target)
            if row is None:
                near = [k for k in rows if target.lower()[:12] in k.lower()]
                print(f"  {v}: absent" + (f" (near: {near[:3]})" if near else ""))
                continue
            cells = "  ".join(f"{co}:{fmt(c)}" for co, c in row.items() if c[0] not in (None, ""))
            print(f"  {v}: {cells}")
        print()


if __name__ == "__main__":
    main()
