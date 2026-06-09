"""Format pooled S5 rows for the Google Sheets paste-target and coverage report.

Two outputs:

- **paste TSV** — rows match ``TABLE_S5_LABELS`` order.  Pastes into cell B3
  of the Table S5 template.  Missing labels become blank rows so the row
  count stays fixed.
- **coverage TSV** — per-S5-label match status (matched / aliased / missing)
  plus n.  For debugging which labels need a new alias or upstream fix.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from hv_dataqc.extract_harmonized.table_s5.aggregate import PooledRow, pool_all
from hv_dataqc.extract_harmonized.table_s5.spec import (
    S5_LABEL_ALIASES,
    SHEET_COLUMNS,
    TABLE_S5_LABELS,
)


def _fmt_int(value: int | float | None) -> str:
    """Integer-format for n / nulls / participants columns."""
    if value is None:
        return ""
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return ""


def _fmt_float(value: float | None) -> str:
    """Decimal-format for mean / median / sd / min / max columns."""
    if value is None:
        return ""
    return str(value)


def _fmt_enums(enums: dict[str, int] | None) -> str:
    """Serialize an enum distribution as 'cat1: n1; cat2: n2; ...'.

    Sorts categories by count descending so the most common are first;
    ties broken alphabetically for stability across runs.
    """
    if not enums:
        return ""
    items = sorted(enums.items(), key=lambda kv: (-kv[1], kv[0]))
    return "; ".join(f"{cat}: {n}" for cat, n in items)


def _row_to_sheet_cells(row: PooledRow | None) -> list[str]:
    """Render a PooledRow as the SHEET_COLUMNS-ordered cells for the TSV."""
    if row is None:
        return [""] * len(SHEET_COLUMNS)
    return [
        _fmt_int(row.n),
        _fmt_int(row.nulls_missing),
        _fmt_float(row.mean),
        _fmt_float(row.median),
        _fmt_float(row.maximum),
        _fmt_float(row.minimum),
        _fmt_float(row.sd),
        _fmt_enums(row.enums),
        _fmt_int(row.participants),
    ]


def format_paste_tsv(pooled: dict[str, PooledRow]) -> tuple[str, list[dict]]:
    """Build the paste-ready TSV and a coverage list.

    Args:
        pooled: ``{bdc_label: PooledRow}`` from ``aggregate.pool_all``.

    Returns:
        Tuple of:
        - paste_tsv (str): one line per S5 row, columns separated by tabs.
          Missing labels are blank lines.  No header row (the template's
          line 1-4 already supply headers).
        - coverage (list[dict]): one dict per S5 label with keys
          ``s5_label``, ``lookup_label``, ``status``, ``n``,
          ``n_contributors``, ``contributing_codes``,
          ``contributing_cohorts``.
    """
    lines: list[str] = []
    coverage: list[dict] = []

    for s5_label in TABLE_S5_LABELS:
        lookup = S5_LABEL_ALIASES.get(s5_label, s5_label)
        row = pooled.get(lookup)
        if row is None:
            # Try the literal S5 label too, in case the alias was wrong or
            # both forms exist.
            row = pooled.get(s5_label) if lookup != s5_label else None

        if row is None:
            status = "missing"
            lines.append("\t".join([""] * len(SHEET_COLUMNS)))
            coverage.append({
                "s5_label": s5_label,
                "lookup_label": lookup,
                "status": status,
                "n": None,
                "n_contributors": 0,
                "contributing_codes": "",
                "contributing_cohorts": "",
            })
            continue

        status = "aliased" if lookup != s5_label else "matched"
        lines.append("\t".join(_row_to_sheet_cells(row)))
        coverage.append({
            "s5_label": s5_label,
            "lookup_label": lookup,
            "status": status,
            "n": row.n,
            "n_contributors": row.n_contributors,
            "contributing_codes": ", ".join(row.contributing_codes),
            "contributing_cohorts": ", ".join(row.contributing_cohorts),
        })

    return "\n".join(lines), coverage


def format_coverage_tsv(coverage: list[dict]) -> str:
    """Render the coverage list as a TSV with a header row."""
    if not coverage:
        return ""
    cols = list(coverage[0].keys())
    out = ["\t".join(cols)]
    for row in coverage:
        out.append("\t".join("" if row.get(c) is None else str(row.get(c)) for c in cols))
    return "\n".join(out)


def coverage_summary(coverage: list[dict]) -> str:
    """One-line summary of match status for stdout."""
    counts = {"matched": 0, "aliased": 0, "missing": 0}
    for row in coverage:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return (
        f"S5 coverage: {counts.get('matched', 0)} matched, "
        f"{counts.get('aliased', 0)} aliased, "
        f"{counts.get('missing', 0)} missing "
        f"(of {len(coverage)} S5 rows)."
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Build the Table S5 paste-ready TSV from per-cohort "
            "harmonized-extract JSON files.  Variables are grouped across "
            "cohorts by `bdc_label` (populated when the extractor was run "
            "with --label-map)."
        ),
    )
    p.add_argument(
        "json_paths", nargs="+", metavar="JSON",
        help="One or more harmonized_*.json files (one per cohort).",
    )
    p.add_argument(
        "--output-dir", metavar="DIR", default=".",
        help="Directory to write table_s5_paste_<ts>.tsv and "
             "s5_coverage_<ts>.tsv.  Defaults to cwd.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    cohort_jsons: dict[str, dict] = {}
    for json_path in args.json_paths:
        path = Path(json_path)
        with path.open(encoding="utf-8") as f:
            doc = json.load(f)
        cohort = (doc.get("metadata") or {}).get("cohort") or path.stem
        cohort_jsons[str(cohort)] = doc

    print(f"Loaded {len(cohort_jsons)} cohort JSON(s): {sorted(cohort_jsons)}")

    pooled = pool_all(cohort_jsons)
    print(f"Pooled into {len(pooled)} bdc_label rows.")

    paste_tsv, coverage = format_paste_tsv(pooled)
    coverage_tsv = format_coverage_tsv(coverage)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    paste_path = out_dir / f"table_s5_paste_{ts}.tsv"
    cov_path = out_dir / f"s5_coverage_{ts}.tsv"

    paste_path.write_text(paste_tsv, encoding="utf-8")
    cov_path.write_text(coverage_tsv, encoding="utf-8")

    print()
    print(coverage_summary(coverage))
    print(f"  Paste TSV    : {paste_path}")
    print(f"  Coverage TSV : {cov_path}")


if __name__ == "__main__":
    main()
