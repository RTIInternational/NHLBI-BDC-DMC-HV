"""Exact duplicate row detection: C14.

Checks that the harmonized output contains no exact duplicate rows within
each entity class. Duplicates indicate YAML design issues such as:
  - Multi-block transforms where two blocks cover overlapping source rows
    without a discriminating condition
  - A populated_from table whose scope is broader than intended, producing
    the same participant x visit x concept record from two different blocks
  - Missing deduplication logic in the pipeline

Reads ``duplicate_stats`` from the harmonized JSON, populated by
``extract_harmonized_summaries.py``. When the field is absent (older JSON
artifacts), the check skips gracefully.
"""

from __future__ import annotations

from hv_dataqc.compare._common import CheckResult


def check_c14_duplicate_rows(harmonized: dict) -> list[CheckResult]:
    """C14: Detect exact duplicate rows in harmonized entity output.

    Emits one WARN per entity class that has exact duplicate rows.
    Emits a single PASS when no entity has duplicates.
    Emits SKIP when duplicate_stats data is absent from the harmonized JSON
    (re-run extract_harmonized_summaries.py to populate it).

    A row is a duplicate if ALL non-id columns are identical to another row
    in the same entity TSV. This catches structural YAML issues without
    false-positiving intentional multi-provenance designs where rows differ
    in condition_provenance or associated_evidence.

    Args:
        harmonized: Top-level harmonized summary dict from
            ``extract_harmonized_summaries.py``.

    Returns:
        List of CheckResult objects.
    """
    dup_data: dict[str, dict] = harmonized.get("duplicate_stats", {})
    if not dup_data:
        return [CheckResult(
            "C14", "_duplicate_rows", "SKIP",
            "Duplicate stats not present in harmonized JSON -- "
            "re-run extract_harmonized_summaries.py to populate",
        )]

    results: list[CheckResult] = []
    all_ok = True

    for entity in sorted(dup_data):
        stats = dup_data[entity]
        n_dup = int(stats.get("n_duplicate_rows", 0))
        n_total = int(stats.get("n_total_rows", 0))
        n_groups = int(stats.get("n_duplicate_groups", 0))
        pct = float(stats.get("pct_duplicated", 0.0))

        if n_dup == 0:
            continue

        all_ok = False
        results.append(CheckResult(
            "C14",
            f"{entity}_duplicates",
            "WARN",
            f"{entity}: {n_dup} exact duplicate row(s) in {n_groups} duplicate group(s) "
            f"({pct:.1f}% of {n_total} total rows). "
            "Likely cause: multi-block YAML without discriminating condition, or "
            "populated_from table scope wider than intended.",
            {
                "entity": entity,
                "n_total_rows": n_total,
                "n_duplicate_rows": n_dup,
                "n_duplicate_groups": n_groups,
                "pct_duplicated": pct,
            },
        ))

    if all_ok:
        entities = sorted(dup_data.keys())
        results.append(CheckResult(
            "C14",
            "_duplicate_rows",
            "PASS",
            f"No exact duplicate rows found across {len(entities)} entity class(es): "
            f"{', '.join(entities)}",
            {"entities_checked": entities},
        ))

    return results
