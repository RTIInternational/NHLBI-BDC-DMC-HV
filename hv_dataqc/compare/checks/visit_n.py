"""Visit N distribution: C8.

Per-visit row count preservation. For table-based cohorts where source files
have no visit column, source visit counts are synthesized from
total_rows_by_pht + visit.yaml mappings.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from hv_dataqc.compare._common import CheckResult, fmt_n as _n
from hv_dataqc.compare.expected_summary import (
    _case_branches,
    _PHV_EQ_RE,
    _strip_expr_literal,
)


def _synthesize_source_visit_counts(
    source: dict, yaml_dir: Path,
) -> tuple[dict[str, int], list[str], list[dict]]:
    """Build a {visit_label: participant_count} dict for table-based cohorts.

    Table-based cohorts (CHS, ARIC, CARDIA, FHS, etc.) encode visit structure
    through PHT identity rather than a dedicated visit column within each TSV.
    For these cohorts the source extractor cannot auto-detect a visit column, so
    ``rows_per_visit`` stays empty.

    This function derives visit counts from two pieces that are always present:
      - ``total_rows_by_pht`` in the source summary (one row per participant)
      - ``visit.yaml`` in the YAML directory (maps each populated_from PHT to a
        canonical visit ``name`` label)

    If multiple YAML blocks share the same PHT (e.g. pht001451 appears for both
    "CHS BASELINE 2" self-report and ECG blocks), only the *Visit* class
    derivation is used to avoid double-counting.  If the same PHT maps to
    multiple distinct visit labels, aggregate metadata cannot determine the
    split safely, so the PHT is reported as unsupported instead of being
    duplicated across labels.

    Returns a tuple of:
      - synthesized {visit_label: count} (PHTs mapped in visit.yaml only)
            - uncovered_phts: list of PHT IDs present in source but absent from visit.yaml
            - unsupported_phts: list of multi-label PHTs that could not be synthesized
    """
    visit_yaml = yaml_dir / "visit.yaml"
    if not visit_yaml.exists():
        return {}, [], []

    rows_by_pht: dict[str, int] = source.get("total_rows_by_pht", {})
    if not rows_by_pht:
        return {}, [], []

    # Parse visit.yaml: each YAML document is a single-element list whose only
    # item is {"class_derivations": {"Visit": {populated_from, slot_derivations}}}
    pht_to_labels: dict[str, list[str]] = {}
    try:
        docs = list(yaml.safe_load_all(visit_yaml.read_text(encoding="utf-8")))
    except yaml.YAMLError:
        return {}, [], []

    for doc in docs:
        if not isinstance(doc, list):
            continue
        for block in doc:
            if not isinstance(block, dict):
                continue
            cd = block.get("class_derivations", {})
            visit_def = cd.get("Visit")
            if not visit_def:
                continue
            pht = visit_def.get("populated_from", "")
            if not pht:
                continue
            slot_defs = visit_def.get("slot_derivations", {}) or {}
            name_slot = slot_defs.get("name", {}) or {}
            label = name_slot.get("value", "")
            if not label:
                continue
            pht_to_labels.setdefault(pht, [])
            if label not in pht_to_labels[pht]:
                pht_to_labels[pht].append(label)

    synthesized: dict[str, int] = {}
    uncovered: list[str] = []
    unsupported: list[dict] = []
    for pht, n in rows_by_pht.items():
        labels = pht_to_labels.get(pht)
        if not labels:
            # PHT present in source but absent from visit.yaml — not being harmonized (by design)
            uncovered.append(pht)
        elif len(labels) > 1:
            unsupported.append({"pht": pht, "labels": sorted(labels), "rows": int(n)})
        else:
            for label in labels:
                synthesized[label] = synthesized.get(label, 0) + n

    return synthesized, uncovered, unsupported


def _build_visit_label_crosswalk(yaml_dir: Path) -> dict[str, str]:
    """Build a {raw_visit_label: canonical_label} crosswalk from visit.yaml name: expr:.

    Column-based cohorts (e.g. SPIROMICS, COPDGene) store a visit discriminator
    column in their source TSV.  The source extractor reads the raw coded values
    (e.g. ``'VISIT_1'``, ``'P1'``, ``0``) directly into ``rows_per_visit``,
    while the harmonized output uses the canonical labels produced by the
    ``case()`` expression in ``visit.yaml`` (e.g. ``'SPIROMICS Visit 1'``,
    ``'COPDGene P1'``, ``'FHS ORIGINAL'``).

    This function parses every ``name: expr: case(...)`` expression in
    ``visit.yaml`` and returns a mapping of raw value → canonical label so
    C8 can re-key source visit counts before comparing.

    Handles both string comparisons (``{phv} == 'VISIT_1'``) and integer
    comparisons (``{phv} == 0``).  Integer raw values are stored as their
    string representations to match JSON/dict key conventions.
    """
    visit_yaml = yaml_dir / "visit.yaml"
    if not visit_yaml.exists():
        return {}
    try:
        docs = list(yaml.safe_load_all(visit_yaml.read_text(encoding="utf-8")))
    except yaml.YAMLError:
        return {}

    crosswalk: dict[str, str] = {}
    for doc in docs:
        if not isinstance(doc, list):
            continue
        for block in doc:
            if not isinstance(block, dict):
                continue
            cd = block.get("class_derivations", {})
            visit_def = cd.get("Visit")
            if not visit_def:
                continue
            slot_defs = visit_def.get("slot_derivations", {}) or {}
            name_slot = slot_defs.get("name", {}) or {}
            expr = name_slot.get("expr", "")
            if not expr or "case" not in expr:
                continue
            for condition, canonical in _case_branches(expr):
                m = _PHV_EQ_RE.search(condition)
                if m:
                    raw_val = _strip_expr_literal(m.group("value"))
                    if raw_val not in crosswalk:
                        crosswalk[raw_val] = canonical
    return crosswalk


def check_c8_visit_distribution(
    source: dict, harmonized: dict,
    warn_lo_ratio: float = 0.95, warn_hi_ratio: float = 1.05,
    yaml_dir: Path | None = None,
    consent_group_file_status: dict | None = None,
) -> list[CheckResult]:
    """C8: Visit-stratified row count comparison.

    For column-based cohorts (SPIROMICS, COPDGene) the source extractor
    auto-detects a visit column and populates ``rows_per_visit`` directly.
    For table-based cohorts (CHS, ARIC, CARDIA, FHS) ``rows_per_visit`` is
    empty; when *yaml_dir* is provided this function synthesizes source visit
    counts from ``total_rows_by_pht`` + ``visit.yaml``.

    When source and harmonized use incompatible visit label namespaces (zero
    overlap), falls back to total-count comparison.

    Args:
        source: Source summary dict.
        harmonized: Harmonized summary dict.
        warn_lo_ratio: Lower bound of acceptable harmonized/source ratio (warn).
        warn_hi_ratio: Upper bound of acceptable harmonized/source ratio (warn).
        yaml_dir: HV YAML transform directory; enables table-based synthesis.
        consent_group_file_status: Per-consent-group entity file status from
            the harmonized JSON (``consent_group_file_status`` field).  When
            provided, empty Visit.tsv groups are noted in FAIL result details.
    """
    # Build a short Visit-specific note from consent_group_file_status if present.
    visit_cg_note: str | None = None
    visit_cg_detail: dict | None = None
    if consent_group_file_status and isinstance(consent_group_file_status, dict):
        loaded_groups: list[tuple[str, int]] = []
        failed_groups: list[str] = []
        for cg_label, entity_map in consent_group_file_status.items():
            st = entity_map.get("Visit", {})
            if st.get("status") == "loaded":
                loaded_groups.append((cg_label, int(st.get("rows", 0))))
            elif st.get("status") in ("empty", "missing"):
                failed_groups.append(cg_label)
        if failed_groups and loaded_groups:
            loaded_str = "; ".join(f"{lbl} ({_n(rows)} rows)" for lbl, rows in sorted(loaded_groups))
            visit_cg_note = (
                f"Visit.tsv empty/missing for {len(failed_groups)} consent group(s) "
                f"({', '.join(sorted(failed_groups))}); loaded in: {loaded_str}. "
                f"See C0 for details."
            )
            visit_cg_detail = {
                "visit_tsv_loaded_groups": {lbl: rows for lbl, rows in loaded_groups},
                "visit_tsv_failed_groups": sorted(failed_groups),
                "c0_reference": "See C0 Entity File Coverage check for root cause.",
            }
    results: list[CheckResult] = []
    src_visits = source.get("rows_per_visit", {})
    harmonized_visits = harmonized.get("rows_per_visit", {})

    # For table-based cohorts: synthesize source visit counts from PHT rows + visit.yaml
    synthesized = False
    uncovered_phts: list[str] = []
    unsupported_phts: list[dict] = []
    if not src_visits and yaml_dir:
        src_visits, uncovered_phts, unsupported_phts = _synthesize_source_visit_counts(source, yaml_dir)
        if src_visits:
            synthesized = True

    unsupported_results: list[CheckResult] = []
    if unsupported_phts:
        unsupported_results.append(CheckResult(
            "C8", "_unsupported_multi_label_phts", "WARN",
            f"{len(unsupported_phts)} source table(s) map to multiple visit labels; aggregate visit counts cannot be synthesized safely",
            {"comparison_confidence": "unsupported", "multi_label_phts": unsupported_phts},
        ))

    if not src_visits and not harmonized_visits:
        return unsupported_results or [CheckResult("C8", "_visits", "SKIP", "No visit data in either summary")]
    if not src_visits:
        return unsupported_results or [CheckResult("C8", "_visits", "SKIP", "No source visit data")]

    src_label = "synthesized from total_rows_by_pht + visit.yaml" if synthesized else "source"

    src_keys = set(src_visits) - {"_MISSING"}
    harmonized_keys = set(harmonized_visits) - {"_MISSING"}

    # For column-based cohorts (SPIROMICS, COPDGene, …): when source rows_per_visit
    # was populated directly from the TSV visit column, the raw coded values
    # (e.g. 'VISIT_1', 'P1', 0) will not match the canonical labels in harmonized
    # (e.g. 'SPIROMICS Visit 1', 'COPDGene P1', 'FHS ORIGINAL').  Attempt to
    # resolve this by translating source keys via the case() expression in
    # visit.yaml before falling back to total-count comparison.
    if src_keys and harmonized_keys and not (src_keys & harmonized_keys) and yaml_dir and not synthesized:
        crosswalk = _build_visit_label_crosswalk(yaml_dir)
        if crosswalk:
            rekeyed: dict[str, int] = {}
            for lbl, n in src_visits.items():
                canonical = crosswalk.get(lbl, lbl)
                rekeyed[canonical] = rekeyed.get(canonical, 0) + int(n)
            rekeyed_keys = set(rekeyed) - {"_MISSING"}
            if rekeyed_keys & harmonized_keys:
                src_visits = rekeyed
                src_keys = rekeyed_keys
                src_label = "source (visit labels translated via visit.yaml case() crosswalk)"

    # Namespace mismatch fallback
    if src_keys and harmonized_keys and not (src_keys & harmonized_keys):
        src_total = sum(n for k, n in src_visits.items() if k != "_MISSING")
        harmonized_total = sum(n for k, n in harmonized_visits.items() if k != "_MISSING")
        detail = {
            "note": "Source and harmonized use different visit label namespaces; "
                    "aggregate visit correctness cannot be evaluated safely",
            "source_labels": sorted(src_keys),
            "harmonized_labels": sorted(harmonized_keys),
            "source_total": src_total,
            "harmonized_total": harmonized_total,
        }
        if synthesized:
            detail["synthesis_note"] = (
                "Source visit counts derived from total_rows_by_pht + visit.yaml. "
                "A FAIL may indicate a visit.yaml label mismatch rather than a pipeline issue."
            )
        if harmonized_total == src_total:
            detail["comparison_confidence"] = "unsupported"
            return unsupported_results + [CheckResult("C8", "visit_TOTAL", "WARN",
                                f"Visit labels use incompatible namespaces; totals match N={_n(src_total)} but row-level visit semantics are needed for an exact verdict",
                                detail)]
        detail["comparison_confidence"] = "unsupported"
        return unsupported_results + [CheckResult(
            "C8", "visit_TOTAL", "WARN",
            f"Visit labels use incompatible namespaces; totals differ {_n(src_total)} -> {_n(harmonized_total)} and row-level visit semantics are needed for an exact verdict",
            detail,
        )]

    synthesis_note = (
        "Source visit counts derived from total_rows_by_pht + visit.yaml. "
        "A FAIL may indicate a visit.yaml label mismatch rather than a pipeline issue."
        if synthesized else None
    )

    # Normal label-keyed comparison
    for visit, src_n in sorted(src_visits.items()):
        harmonized_n = harmonized_visits.get(visit, 0)
        detail: dict = {}
        if synthesis_note:
            detail["synthesis_note"] = synthesis_note
        if visit_cg_detail:
            detail.update(visit_cg_detail)
        if harmonized_n == src_n:
            results.append(CheckResult("C8", f"visit_{visit}", "PASS",
                                       f"Visit {visit}: N={_n(src_n)} ({src_label})",
                                       detail or None))
        elif harmonized_n == 0:
            msg = f"Visit {visit}: missing in harmonized (source N={_n(src_n)}, {src_label})"
            if visit_cg_note:
                msg += f" — {visit_cg_note}"
            results.append(CheckResult("C8", f"visit_{visit}", "FAIL", msg, detail or None))
        else:
            ratio = harmonized_n / src_n if src_n > 0 else 0
            status = "WARN" if warn_lo_ratio <= ratio <= warn_hi_ratio else "FAIL"
            detail.update({"source_n": src_n, "harmonized_n": harmonized_n, "ratio": ratio})
            results.append(CheckResult("C8", f"visit_{visit}", status,
                                       f"Visit {visit}: {_n(src_n)} -> {_n(harmonized_n)} ({src_label})",
                                       detail))

    for visit in sorted(set(harmonized_visits) - set(src_visits)):
        results.append(CheckResult("C8", f"visit_{visit}", "INFO",
                                   f"Visit {visit}: only in harmonized (N={_n(harmonized_visits[visit])})"))

    # Uncovered PHTs: in source data but not in visit.yaml — not being harmonized, by design
    if uncovered_phts:
        rows_by_pht = source.get("total_rows_by_pht", {})
        total_uncovered_rows = sum(rows_by_pht.get(p, 0) for p in uncovered_phts)
        results.append(CheckResult(
            "C8", "_uncovered_phts", "INFO",
            f"{len(uncovered_phts)} source table(s) not in visit.yaml (not being harmonized): "
            f"{', '.join(sorted(uncovered_phts))} — {total_uncovered_rows:,} rows not covered",
            {"uncovered_phts": sorted(uncovered_phts), "total_rows": total_uncovered_rows},
        ))

    return unsupported_results + results
