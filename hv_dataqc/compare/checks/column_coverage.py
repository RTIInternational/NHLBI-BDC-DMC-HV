"""Entity column coverage: C15.

Checks that each entity TSV produced consistent column schemas across all
consent groups, and that every slot defined in the cohort's YAML transform
files is present as a column in the loaded entity TSV.

Reads ``consent_group_file_status`` from the harmonized JSON, populated by
``extract_harmonized_summaries.py``.  When the field is absent or contains no
``columns`` data (older JSON artifacts), the check skips gracefully.

Two sub-checks are performed:

1. **Cross-consent-group consistency** (FAIL): If an entity is loaded in two
   or more consent groups, all groups must have identical column sets.  A
   mismatch indicates a structural pipeline inconsistency -- one consent group
   run may have dropped or added columns relative to another.

2. **YAML-driven column presence** (FAIL): When *yaml_dir* is provided, each
   loaded entity is checked against the union of all ``slot_derivations`` keys
   defined for that entity across all cohort YAML files.  Two slot types are
   intentionally excluded from this check:

   * ``id`` is only included when the YAML explicitly derives it (e.g. via
     ``uuid5()`` in ``visit.yaml``).  For all other entities the pipeline does
     not emit ``id`` as a TSV column — it is the row key handled internally.
   * Composite object slots (those whose value contains ``class_derivations``
     or ``object_derivations``, e.g. ``value_quantity``) are flattened into
     sub-columns in TSV output and never appear as a single column.

   A slot that appears in the YAML spec but is absent from the TSV indicates
   that the pipeline silently dropped a mapped field -- all C1/C2/C7 stats
   for that slot will be wrong without any other error signal.

   Sub-check 2 is SKIPPED when *yaml_dir* is not provided.
"""

from __future__ import annotations

from pathlib import Path

import yaml as _yaml

from hv_dataqc.compare._common import CheckResult


def build_expected_columns_from_yaml(yaml_dir: Path) -> dict[str, set[str]]:
    """Return per-entity expected columns derived from cohort YAML transform files.

    Scans every ``*.yaml`` file in *yaml_dir*, collects the keys of each
    ``slot_derivations`` block grouped by ``class_derivations`` entity name.
    Composite object slots (those with nested ``class_derivations`` or
    ``object_derivations``) are excluded because they are flattened into
    sub-columns in TSV output and never appear as a single column.  ``id``
    is only included when the YAML explicitly derives it — it is NOT added
    unconditionally, since the pipeline only emits it for entities whose YAML
    defines an explicit ``id`` derivation (e.g. ``visit.yaml``).

    Args:
        yaml_dir: Directory containing the cohort's ``*-ingest`` YAML files
            (e.g. ``priority_variables_transform/CARDIA-ingest/``).

    Returns:
        Mapping of entity class name to the set of column names expected in
        the output TSV.  Empty dict if no parseable YAML files are found.
    """
    expected: dict[str, set[str]] = {}

    for yaml_file in sorted(yaml_dir.glob("*.yaml")):
        try:
            with open(yaml_file, encoding="utf-8") as fh:
                content = _yaml.safe_load(fh)
        except Exception:  # malformed YAML or IO error — skip silently
            continue

        if not isinstance(content, list):
            continue

        for item in content:
            if not isinstance(item, dict):
                continue
            class_derivations = item.get("class_derivations")
            if not isinstance(class_derivations, dict):
                continue
            for class_name, class_def in class_derivations.items():
                if not isinstance(class_def, dict):
                    continue
                slot_derivations = class_def.get("slot_derivations")
                if not isinstance(slot_derivations, dict):
                    continue
                slots = expected.setdefault(class_name, set())
                for slot_name, slot_def in slot_derivations.items():
                    # Skip composite object slots — they have nested
                    # class_derivations or object_derivations and get
                    # flattened in TSV output, never appearing as a
                    # single column (e.g. value_quantity -> Quantity).
                    if isinstance(slot_def, dict) and (
                        "class_derivations" in slot_def
                        or "object_derivations" in slot_def
                    ):
                        continue
                    slots.add(slot_name)

    return expected


def check_c15_column_coverage(
    harmonized: dict,
    *,
    yaml_dir: Path | None = None,
) -> list[CheckResult]:
    """C15: Entity TSV column schema consistency and YAML-driven column presence.

    Emits FAIL when:
    - An entity has different column sets across two or more consent groups
      (sub-check 1).
    - A slot defined in the cohort's YAML transform files is absent from the
      corresponding entity TSV (sub-check 2, only when *yaml_dir* provided).

    Emits SKIP when ``consent_group_file_status`` is absent or contains no
    ``columns`` data (re-run ``extract_harmonized_summaries.py`` to populate).
    Sub-check 2 is silently skipped when *yaml_dir* is ``None``.

    Emits PASS when all loaded entities pass both sub-checks.

    Args:
        harmonized: Top-level harmonized summary dict from
            ``extract_harmonized_summaries.py``.
        yaml_dir: Path to the cohort's ``*-ingest`` YAML directory
            (e.g. ``priority_variables_transform/CARDIA-ingest/``).
            When provided, sub-check 2 validates column presence against
            the union of all slot names defined for each entity across all
            YAML files in the directory.

    Returns:
        List of CheckResult objects.
    """
    cg_status: dict[str, dict[str, dict]] = harmonized.get(
        "consent_group_file_status", {}
    )
    if not cg_status:
        return [CheckResult(
            "C15", "_column_coverage", "SKIP",
            "consent_group_file_status not present in harmonized JSON -- "
            "re-run extract_harmonized_summaries.py to populate",
        )]

    # Collect column lists per entity across consent groups.
    # entity -> [(cg_label, columns_list), ...]
    entity_columns: dict[str, list[tuple[str, list[str]]]] = {}
    has_any_columns = False

    for cg_label, entity_map in cg_status.items():
        for entity, st in entity_map.items():
            if st.get("status") != "loaded":
                continue
            cols = st.get("columns")
            if cols is None:
                continue
            has_any_columns = True
            entity_columns.setdefault(entity, []).append((cg_label, sorted(cols)))

    if not has_any_columns:
        return [CheckResult(
            "C15", "_column_coverage", "SKIP",
            "No column data found in consent_group_file_status -- "
            "re-run extract_harmonized_summaries.py (columns field added "
            "in hv-dataqc issue #730)",
        )]

    # Build YAML-derived expected columns once (only when yaml_dir is supplied).
    yaml_expected: dict[str, set[str]] = (
        build_expected_columns_from_yaml(yaml_dir)
        if yaml_dir is not None
        else {}
    )

    results: list[CheckResult] = []
    all_ok = True

    for entity in sorted(entity_columns):
        entries = entity_columns[entity]  # [(cg_label, sorted_cols), ...]

        # ── Sub-check 1: cross-consent-group column consistency ──────────────
        if len(entries) > 1:
            ref_label, ref_cols = entries[0]
            ref_set = set(ref_cols)
            for cg_label, cols in entries[1:]:
                cg_set = set(cols)
                if cg_set != ref_set:
                    all_ok = False
                    missing_in_cg = sorted(ref_set - cg_set)
                    extra_in_cg = sorted(cg_set - ref_set)
                    results.append(CheckResult(
                        "C15",
                        f"{entity}_column_consistency",
                        "FAIL",
                        (
                            f"{entity}.tsv: column schema differs between consent groups "
                            f"'{ref_label}' and '{cg_label}' -- "
                            f"{len(missing_in_cg)} column(s) missing in {cg_label}, "
                            f"{len(extra_in_cg)} column(s) extra in {cg_label}"
                        ),
                        {
                            "entity": entity,
                            "reference_group": ref_label,
                            "differing_group": cg_label,
                            "missing_in_differing": missing_in_cg,
                            "extra_in_differing": extra_in_cg,
                        },
                    ))

        # ── Sub-check 2: YAML-driven column presence ─────────────────────────
        if yaml_expected:
            spec_cols = yaml_expected.get(entity)
            if spec_cols:
                # Union across consent groups: a column present in any group is
                # not missing.  Per-group gaps are caught by sub-check 1 above.
                all_seen = set().union(*(set(cols) for _, cols in entries))
                missing_yaml = sorted(spec_cols - all_seen)
                if missing_yaml:
                    all_ok = False
                    results.append(CheckResult(
                        "C15",
                        f"{entity}_required_columns",
                        "FAIL",
                        (
                            f"{entity}.tsv: {len(missing_yaml)} column(s) defined in "
                            f"YAML spec but absent from TSV: "
                            f"{', '.join(missing_yaml)}"
                        ),
                        {
                            "entity": entity,
                            "missing_yaml_columns": missing_yaml,
                            "present_columns": sorted(all_seen),
                        },
                    ))

    if all_ok:
        checked = sorted(entity_columns.keys())
        yaml_note = (
            f", YAML spec from {yaml_dir.name}" if yaml_dir is not None else ""
        )
        results.append(CheckResult(
            "C15", "_column_coverage", "PASS",
            (
                f"All {len(checked)} loaded entities have consistent column "
                f"schemas across consent groups and match YAML spec"
                f"{yaml_note} "
                f"({', '.join(checked)})"
            ),
        ))

    return results
