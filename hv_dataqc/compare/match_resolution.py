"""Match resolution helpers: Phase-3 comparison metadata and expected n_valid.

Functions here operate on already-assembled crosswalk match dicts and source
summary dicts.  They have no dependencies on YAML parsing or cache loading —
only on ``helpers.py``.
"""

from __future__ import annotations

from hv_dataqc.compare.helpers import _canonical_phv_id, _normalize_code


def _infer_match_mode(entries: list[dict], resolved_src: dict | None, per_pht_summaries: list[dict]) -> str:
    """Return the explicit comparison mode represented by merged YAML entries."""
    if (resolved_src or {}).get("_comparison_confidence") == "unsupported":
        return "unsupported_complex"
    if any(e.get("is_static") for e in entries):
        return "static_value"
    if any(e.get("concept_value_map") for e in entries):
        return "concept_routing"
    if any(e.get("value_map") for e in entries):
        return "value_mapping"
    if any(e.get("conversion_factor") for e in entries):
        return "scalar_conversion"
    if any("case(" in str(expr).lower() for e in entries for expr in (e.get("value_exprs") or [])):
        return "case_expr"
    if len(entries) > 1 or len(per_pht_summaries) > 1:
        return "pooled_blocks"
    return "direct"


def _source_phv_details_for_entries(
    entries: list[dict],
    phv_names: dict[str, str],
    phv_to_pht: dict[str, str],
) -> list[dict[str, str]]:
    """Build inspectable source-PHV metadata for merged YAML entries."""
    details: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for entry in entries:
        roles = entry.get("source_phv_roles") or []
        if not roles and entry.get("phv_id"):
            roles = [{"phv_id": entry.get("phv_id"), "role": "value", "slot": ""}]
        for role_entry in roles:
            phv_id = _canonical_phv_id(role_entry.get("phv_id", ""))
            if not phv_id:
                continue
            role = str(role_entry.get("role") or "context")
            slot = str(role_entry.get("slot") or "")
            yaml_file = str(entry.get("yaml_file") or "")
            detail_key = (phv_id, role, slot, yaml_file)
            if detail_key in seen:
                continue
            details.append(
                {
                    "phv_id": phv_id,
                    "pht_id": phv_to_pht.get(phv_id, ""),
                    "source_column": phv_names.get(phv_id, ""),
                    "role": role,
                    "slot": slot,
                    "yaml_file": yaml_file,
                }
            )
            seen.add(detail_key)
    return details


def _promote_comparison_metadata(match: dict) -> None:
    """Expose public comparison metadata fields while preserving private keys."""
    resolved_src = match.get("_resolved_src") or {}
    basis = resolved_src.get("_comparison_basis") or match.get("_comparison_basis")
    if not basis:
        basis = "source_pooled_raw" if len(match.get("_per_pht_src") or []) > 1 else "source_direct"
    confidence = (
        resolved_src.get("_comparison_confidence")
        or match.get("_comparison_confidence")
        or "exact"
    )
    limitations = (
        resolved_src.get("_comparison_limitations")
        or match.get("_comparison_limitations")
        or []
    )

    match["comparison_basis"] = basis
    match["comparison_confidence"] = confidence
    match["comparison_limitations"] = list(limitations)
    match["source_phts"] = list(match.get("_source_phts") or [])
    match["source_phvs"] = list(match.get("_source_phvs") or match.get("_phv_ids") or [])


def _expected_harmonized_n(match: dict, src_var: dict) -> int | None:
    """Compute expected harmonized n_valid for a crosswalk match.

    Generalises C2's denominator to handle one-source-to-many-concepts
    routing (e.g. ``condition_concept`` with value_mappings that route
    different source codes to different MONDO/HP CURIEs).

    Behaviour:

      * If the entry has no ``concept_value_map`` (continuous, 1:1 categorical,
        or any non-routing case): returns None — caller falls back to the
        pooled source ``n_valid``, preserving today's behaviour.
      * If the entry has a ``concept_value_map`` AND the source is categorical
        with a per-code distribution: returns the sum of source rows whose
        code maps to *this* match's ``concept_code``.  This is the row count
        we expect to see materialised under the harmonized concept, and
        therefore the correct denominator for source-to-harmonized
        alignment checks.
      * If we have ``concept_value_map`` but no usable distribution (e.g.
        type='unknown'): returns None — caller falls back to ``n_valid``.

    Cohort-agnostic; depends only on YAML-declared mappings + source
    distribution emitted by the source extractor.
    """
    cvm = match.get("concept_value_map")
    if not cvm or not isinstance(cvm, dict):
        return None
    target_code = match.get("concept_code")
    if not target_code:
        return None
    matching_codes = {
        _normalize_code(code) for code, target in cvm.items()
        if str(target).strip() == str(target_code).strip()
    }
    if not matching_codes:
        return 0
    dist = (src_var or {}).get("distribution") or (src_var or {}).get("values")
    if not isinstance(dist, dict) or not dist:
        return None
    expected = 0
    for code, info in dist.items():
        if _normalize_code(code) not in matching_codes:
            continue
        if isinstance(info, dict):
            expected += int(info.get("n", info.get("count", 0)) or 0)
        else:
            try:
                expected += int(info)
            except (TypeError, ValueError):
                pass
    return expected
