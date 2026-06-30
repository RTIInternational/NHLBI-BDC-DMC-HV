"""Entity File Coverage: C0.

Pre-flight check that detects when any entity TSV is completely empty (or
missing) for one consent group while the same entity produced rows in at
least one other consent group.  This signals a pipeline failure — not a
data-quality issue in the harmonized values — and should surface before all
other checks so reviewers see the root cause immediately.

Reads ``consent_group_file_status`` from the harmonized JSON, populated by
``extract_harmonized_summaries.py`` since issue #690.  When the field is
absent (older JSON artifacts), the check skips gracefully.
"""

from __future__ import annotations

from hv_dataqc.compare._common import CheckResult, fmt_n as _n


def check_c0_entity_file_coverage(harmonized: dict) -> list[CheckResult]:
    """C0: Per-consent-group entity file coverage.

    Emits FAIL when an entity TSV is empty or missing for one or more consent
    groups while it is loaded (non-empty) in at least one other consent group.
    Emits INFO when an entity is consistently missing across ALL consent groups
    (expected for optional entities like DrugExposure in many cohorts).

    Args:
        harmonized: Top-level harmonized summary dict from
            ``extract_harmonized_summaries.py``.

    Returns:
        List of CheckResult objects.  Empty if ``consent_group_file_status``
        is absent or contains no anomalies.
    """
    cg_status: dict[str, dict[str, dict]] = harmonized.get("consent_group_file_status", {})
    if not cg_status:
        return []

    # Collect all entity names seen across any consent group.
    all_entities: set[str] = set()
    for entity_map in cg_status.values():
        all_entities.update(entity_map.keys())

    results: list[CheckResult] = []

    for entity in sorted(all_entities):
        loaded: list[tuple[str, int]] = []    # [(label, rows), ...]
        empty: list[tuple[str, str]] = []     # [(label, error), ...]
        missing: list[str] = []               # [label, ...]

        for cg_label, entity_map in cg_status.items():
            st = entity_map.get(entity)
            if st is None:
                # Entity not recorded for this group — treat as missing
                missing.append(cg_label)
                continue
            status = st.get("status")
            if status == "loaded":
                loaded.append((cg_label, int(st.get("rows", 0))))
            elif status == "empty":
                empty.append((cg_label, st.get("error", "")))
            elif status == "missing":
                missing.append(cg_label)

        problem_groups = empty + [(lbl, "") for lbl in missing]
        if not problem_groups:
            continue  # all groups loaded — no issue

        if not loaded:
            # Entity absent in ALL consent groups — this is expected for optional
            # entities; report as INFO rather than FAIL.
            results.append(CheckResult(
                "C0", f"{entity}_file_coverage", "INFO",
                f"{entity}.tsv not found in any consent group ({len(missing)} group(s))",
                {
                    "entity": entity,
                    "missing_groups": sorted(missing),
                },
            ))
            continue

        # Some groups loaded, some didn't — that's the anomaly.
        loaded_summary = "; ".join(
            f"{lbl} ({_n(rows)} rows)" for lbl, rows in sorted(loaded)
        )
        failed_labels = sorted(lbl for lbl, _ in problem_groups)
        empty_labels = sorted(lbl for lbl, _ in empty)
        missing_labels = sorted(missing)

        parts: list[str] = []
        if empty_labels:
            parts.append(f"empty (0 bytes or parse failure): {', '.join(empty_labels)}")
        if missing_labels:
            parts.append(f"file not found: {', '.join(missing_labels)}")

        msg = (
            f"{entity}.tsv: {len(problem_groups)} of {len(cg_status)} consent group(s) "
            f"produced no output ({'; '.join(parts)}). "
            f"Loaded in: {loaded_summary}. "
            f"This likely indicates a pipeline failure for the affected group(s)."
        )

        detail: dict = {
            "entity": entity,
            "loaded_groups": {lbl: rows for lbl, rows in loaded},
            "failed_groups": failed_labels,
        }
        if empty:
            detail["empty_errors"] = {lbl: err for lbl, err in empty if err}

        results.append(CheckResult("C0", f"{entity}_file_coverage", "FAIL", msg, detail))

    if not results and cg_status:
        # All entities loaded in all consent groups — emit a single PASS summary.
        n_groups = len(cg_status)
        all_entities_list = sorted(all_entities)
        results.append(CheckResult(
            "C0", "entity_file_coverage", "PASS",
            f"All {len(all_entities_list)} entity type(s) loaded successfully in all "
            f"{n_groups} consent group(s).",
            {"entities": all_entities_list, "consent_groups": sorted(cg_status.keys())},
        ))

    return results
