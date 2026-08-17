"""YAML transform spec validation: C16.

Checks structural requirements on cohort YAML transform files that cannot
be caught from harmonized output alone.

C16  id/identity Slot Pattern  -- Person and Participant blocks must have an
     explicit ``id`` slot derivation (uuid5-based) and ``identity`` must be
     the raw source string, not the uuid5 expression.

This check reads YAML files directly from *yaml_dir* and does not require
harmonized or source summary data.  It is a pre-flight spec check that runs
as part of the hv-dataqc compare pipeline.

Background
----------
The bdchm model requires every entity to have a stable URI-based ``id``.
The canonical pattern (established in MESA, then applied to ARIC, FHS, CHS):

    id:
        expr: 'uuid5("https://w3id.org/bdchm/Person", str({dbGaP_Subject_ID}))'
    identity:
        expr: 'str({dbGaP_Subject_ID})'

The legacy pattern (uuid5 in ``identity``, no ``id``) silently produces
output where the ``id`` column is absent or auto-generated inconsistently.
This was caught manually across CHS, ARIC, FHS, and JHS in 2026-07 after
pipeline migration to linkml-map 0.5.3rc3.
"""

from __future__ import annotations

from pathlib import Path
from typing import Generator

import yaml as _yaml

from hv_dataqc.compare._common import CheckResult

# Classes that must have an explicit 'id' slot derivation at top level
_ID_REQUIRED_CLASSES = {"Person", "Participant"}


def _iter_top_level_blocks(yaml_dir: Path) -> Generator[tuple[str, str, dict], None, None]:
    """Yield (filename, class_name, class_def) for all top-level class_derivation blocks."""
    for yaml_file in sorted(yaml_dir.glob("*.yaml")):
        try:
            with open(yaml_file, encoding="utf-8") as fh:
                content = _yaml.safe_load(fh)
        except Exception:
            continue

        if not isinstance(content, list):
            continue

        for item in content:
            if not isinstance(item, dict):
                continue
            class_derivs = item.get("class_derivations")
            if not isinstance(class_derivs, dict):
                continue
            for class_name, class_def in class_derivs.items():
                if isinstance(class_def, dict):
                    yield yaml_file.name, class_name, class_def


def check_c16_id_slot(yaml_dir: Path | str | None) -> list[CheckResult]:
    """C16: Verify Person and Participant have explicit ``id`` slot derivations.

    Checks that:
    1. ``id`` is present in slot_derivations for every Person/Participant block.
    2. ``identity`` does NOT contain a uuid5() expression (old anti-pattern).

    Args:
        yaml_dir: Path to the cohort's YAML ingest directory
            (e.g. ``priority_variables_transform/ARIC-ingest/``).
            Returns a single SKIP result if None or not a directory.

    Returns:
        List of CheckResult objects.
    """
    if yaml_dir is None:
        return [CheckResult("C16", "_spec_validation", "SKIP", "C16: yaml_dir not provided -- skipping id/identity check")]

    yaml_path = Path(yaml_dir)
    if not yaml_path.is_dir():
        return [CheckResult("C16", "_spec_validation", "SKIP", f"C16: yaml_dir not found: {yaml_dir}")]

    results: list[CheckResult] = []
    found_any = False

    for fname, class_name, class_def in _iter_top_level_blocks(yaml_path):
        if class_name not in _ID_REQUIRED_CLASSES:
            continue

        found_any = True
        slot_derivs = class_def.get("slot_derivations") or {}

        # Check 1: 'id' slot must be present
        if "id" not in slot_derivs:
            results.append(CheckResult(
                "C16",
                f"{class_name}_id_slot",
                "FAIL",
                f"C16 [{fname}] {class_name} missing required 'id' slot derivation. "
                f"Add: id: expr: 'uuid5(\"https://w3id.org/bdchm/{class_name}\", ...)'"
            ))

        # Check 2: 'identity' must not carry the uuid5 expression (old pattern)
        identity_sd = slot_derivs.get("identity")
        if isinstance(identity_sd, dict):
            identity_expr = identity_sd.get("expr", "")
            if isinstance(identity_expr, str) and "uuid5(" in identity_expr:
                results.append(CheckResult(
                    "C16",
                    f"{class_name}_identity_pattern",
                    "FAIL",
                    f"C16 [{fname}] {class_name}.identity uses uuid5() -- "
                    f"uuid5() belongs in 'id'; identity should be the raw source string "
                    f"(e.g., expr: 'str({{phv}})')"
                ))

    if not found_any:
        return [CheckResult("C16", "_spec_validation", "SKIP", "C16: no Person or Participant blocks found in yaml_dir")]

    if not results:
        results.append(CheckResult("C16", "_spec_validation", "PASS", "C16: all Person/Participant blocks have correct id/identity pattern"))

    return results
