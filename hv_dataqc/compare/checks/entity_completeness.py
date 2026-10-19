"""Entity File Coverage: C0.

Pre-flight check that detects when any entity TSV fails to produce valid rows
for one or more consent groups.  This signals a pipeline failure -- not a
data-quality issue in the harmonized values -- and should surface before all
other checks so reviewers see the root cause immediately.

Severity rule (three-way):
  - PASS: every consent group loaded the entity file with real rows.
  - INFO: the entity file was never produced in ANY consent group -- expected
    for optional entities the cohort simply doesn't populate (e.g.
    DrugExposure for a cohort that collects no medication data).
  - FAIL: anything else -- produced in one group but missing in another,
    zero rows anywhere (even uniformly across all groups), a genuine
    read/parse failure anywhere, or an unrecognized status literal. A file
    that IS produced but carries no rows means the transform ran and found
    nothing, which is a stronger signal than "never attempted" and is not
    given the benefit of the doubt.

Reads ``consent_group_file_status`` from the harmonized JSON, populated by
``extract_harmonized_summaries.py`` since issue #690.  When the field is
absent (older JSON artifacts), the check skips gracefully.
"""

from __future__ import annotations

from hv_dataqc.compare._common import CheckResult, fmt_n as _n


def check_c0_entity_file_coverage(harmonized: dict) -> list[CheckResult]:
    """C0: Per-consent-group entity file coverage.

    See module docstring for the PASS/INFO/FAIL severity rule.

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
        missing: list[str] = []               # [label, ...] file not found / not recorded
        real: list[tuple[str, int]] = []      # [(label, rows), ...] rows > 0
        problem: list[tuple[str, str]] = []   # [(label, reason), ...] produced but no valid rows

        for cg_label, entity_map in cg_status.items():
            st = entity_map.get(entity)
            if st is None:
                # Entity not recorded for this group — treat as missing
                missing.append(cg_label)
                continue
            status = st.get("status")
            if status == "missing":
                missing.append(cg_label)
            elif status == "loaded":
                rows = int(st.get("rows", 0))
                if rows > 0:
                    real.append((cg_label, rows))
                else:
                    # Parses fine (e.g. header-only TSV) but carries no data.
                    problem.append((cg_label, "0 rows (header-only file)"))
            elif status == "empty":
                problem.append((cg_label, st.get("error") or "empty file / parse failure"))
            else:
                # Unrecognized or absent status literal — we cannot confirm the
                # file loaded, so record it as a problem group rather than
                # letting it drop silently (which would let a broken run read
                # as PASS).
                problem.append((cg_label, f"unrecognized status {status!r}"))

        n_groups = len(cg_status)

        if not real and not problem:
            # Entity never produced in ANY consent group — expected for
            # optional entities; report as INFO rather than FAIL.
            results.append(CheckResult(
                "C0", f"{entity}_file_coverage", "INFO",
                f"{entity}.tsv not found in any consent group ({n_groups} group(s))",
                {"entity": entity, "missing_groups": sorted(missing)},
            ))
            continue

        if not problem and not missing:
            continue  # every group loaded with real rows — no issue

        # Anything else is the anomaly: inconsistent production across
        # groups, zero rows anywhere (even uniformly), a parse failure
        # anywhere, or an unrecognized status.
        real_summary = "; ".join(f"{lbl} ({_n(rows)} rows)" for lbl, rows in sorted(real))
        problem_labels = sorted(lbl for lbl, _ in problem)
        missing_labels = sorted(missing)

        parts: list[str] = []
        if problem:
            detail_bits = "; ".join(f"{lbl} ({reason})" for lbl, reason in sorted(problem))
            parts.append(f"produced no valid rows: {detail_bits}")
        if missing_labels:
            parts.append(f"file not found: {', '.join(missing_labels)}")

        loaded_clause = (
            f"Loaded with real rows in: {real_summary}. " if real
            else "No consent group produced any valid rows. "
        )

        n_problem_groups = len(problem) + len(missing)
        msg = (
            f"{entity}.tsv: {n_problem_groups} of {n_groups} consent group(s) "
            f"produced no valid rows ({'; '.join(parts)}). "
            f"{loaded_clause}"
            f"This likely indicates a pipeline failure for the affected group(s)."
        )

        detail: dict = {
            "entity": entity,
            "loaded_groups": {lbl: rows for lbl, rows in real},
            "failed_groups": sorted(problem_labels + missing_labels),
        }
        if problem:
            detail["problem_reasons"] = {lbl: reason for lbl, reason in problem}

        results.append(CheckResult("C0", f"{entity}_file_coverage", "FAIL", msg, detail))

    if not results and all_entities:
        # All entities loaded in all consent groups — emit a single PASS summary.
        n_groups = len(cg_status)
        all_entities_list = sorted(all_entities)
        results.append(CheckResult(
            "C0", "entity_file_coverage", "PASS",
            f"All {len(all_entities_list)} entity type(s) loaded successfully in all "
            f"{n_groups} consent group(s).",
            {"entities": all_entities_list, "consent_groups": sorted(cg_status.keys())},
        ))
    elif not results and not all_entities:
        # consent_group_file_status is present but records no entities in any
        # group — a total-absence signature we cannot interpret as success.
        # SKIP (not PASS) so an empty coverage map never reads as "all loaded".
        results.append(CheckResult(
            "C0", "entity_file_coverage", "SKIP",
            f"consent_group_file_status present for {len(cg_status)} consent group(s) "
            "but lists no entity files — coverage cannot be verified.",
            {"consent_groups": sorted(cg_status.keys())},
        ))

    return results
