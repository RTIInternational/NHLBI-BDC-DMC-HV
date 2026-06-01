"""Expected post-transform summary builders for source-side aggregate comparison.

These functions translate a YAML transform entry's semantics (value_mappings,
case() expressions, scalar conversion, concept routing) into an expected
harmonized distribution or continuous summary that C2/C3/C4/C6/C7 can
compare against the actual harmonized extractor output.
"""

from __future__ import annotations

import math
import re
from typing import Any

from hv_dataqc.compare.helpers import (
    _canonical_phv_id,
    _distribution_count_map,
    _NULL_SENTINEL_CODES,
    _is_null_sentinel_code,
    _normalize_code,
)
from hv_dataqc.hv_dataqc_common import normalize_category_key


# ---------------------------------------------------------------------------
# Case-expression parsing
# ---------------------------------------------------------------------------

_CASE_BRANCH_RE = re.compile(
    r"\((?P<condition>[^,]+),\s*"
    r"(?P<value>None|True|False|'[^']*'|\"[^\"]*\"|[A-Za-z0-9_:.-]+)\)"
)
_PHV_EQ_RE = re.compile(
    r"\{(?P<phv>phv\d+)\}\s*==\s*"
    r"(?P<value>'[^']*'|\"[^\"]*\"|-?\d+(?:\.\d+)?|[A-Za-z0-9_:.-]+)",
    re.IGNORECASE,
)
# Matches {phv} in (val1, val2, ...) set-membership tests in case() conditions
_PHV_IN_RE = re.compile(
    r"\{(?P<phv>phv\d+)\}\s+in\s+\((?P<values>[^)]+)\)",
    re.IGNORECASE,
)


def _strip_expr_literal(value: str) -> str:
    """Return a case() branch literal without surrounding quotes."""
    text = str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1]
    return text


def _case_branches(expr: str) -> list[tuple[str, str]]:
    """Extract simple ``case((condition, value), ...)`` branches.

    The compare engine only needs aggregate metadata, so this intentionally
    supports the common YAML subset used for categorical routing: comma-free
    boolean conditions and scalar string/number outputs.  Unsupported branches
    are ignored by callers rather than guessed.
    """
    if not isinstance(expr, str) or "case" not in expr:
        return []
    branches: list[tuple[str, str]] = []
    for match in _CASE_BRANCH_RE.finditer(expr):
        branches.append(
            (
                match.group("condition").strip().strip("() "),
                _strip_expr_literal(match.group("value")),
            )
        )
    return branches


def _distribution_count_for_code(summary: dict | None, code: str) -> int | None:
    """Return the aggregate count for *code* in a source summary distribution."""
    if not summary:
        return None
    dist = summary.get("distribution") or summary.get("values")
    if not isinstance(dist, dict):
        return None
    target = normalize_category_key(_normalize_code(code))
    for raw_code, info in dist.items():
        if normalize_category_key(_normalize_code(raw_code)) != target:
            continue
        if isinstance(info, dict):
            return int(info.get("n", info.get("count", 0)) or 0)
        try:
            return int(info)
        except (TypeError, ValueError):
            return None
    return None


def _unsupported_joint_summary(src_summary: dict | None, basis: str, limitation: str) -> dict:
    """Return a source-shaped summary that tells checks to skip exact verdicts."""
    summary = dict(src_summary or {})
    summary.setdefault("type", (src_summary or {}).get("type", "categorical"))
    summary.setdefault("n_total", int((src_summary or {}).get("n_total", 0) or 0))
    summary.setdefault("n_valid", int((src_summary or {}).get("n_valid", 0) or 0))
    summary.setdefault("n_missing", int((src_summary or {}).get("n_missing", 0) or 0))
    summary["_comparison_basis"] = basis
    summary["_comparison_confidence"] = "unsupported"
    summary["_comparison_limitations"] = [limitation]
    return summary


def _extract_phv_conditions(condition: str) -> dict[str, list[str]]:
    """Extract per-PHV value lists from a case() branch condition string.

    Handles both ``{phv} == value`` equality comparisons and
    ``{phv} in (v1, v2, ...)`` set-membership patterns.

    Returns ``{canonical_phv_id: [value, ...]}`` where multiple values arise
    from ``in (...)`` lists.  A single ``==`` test contributes one value.
    PHVs referenced only by inequality (``!=``) or comparison operators
    (``<``, ``>``) are intentionally excluded — they constrain the population
    but the compare engine cannot compute the residual count from marginals.

    Parameters
    ----------
    condition:
        A single case() branch condition string, e.g.
        ``"{phv00001} == 1 and {phv00002} in (2, 3)"``.

    Returns
    -------
    dict
        ``{phv_id: [val, ...]}`` for each PHV with deterministic value tests.
    """
    phv_vals: dict[str, list[str]] = {}
    for m in _PHV_EQ_RE.finditer(condition):
        phv = _canonical_phv_id(m.group("phv"))
        val = _strip_expr_literal(m.group("value"))
        phv_vals.setdefault(phv, []).append(val)
    for m in _PHV_IN_RE.finditer(condition):
        phv = _canonical_phv_id(m.group("phv"))
        vals = [_strip_expr_literal(v.strip()) for v in m.group("values").split(",")]
        phv_vals.setdefault(phv, []).extend(vals)
    return phv_vals


def _count_from_joint_dist(
    joint_dists_by_pht: dict[str, dict],
    pht: str,
    phv_a: str,
    vals_a: list[str],
    phv_b: str,
    vals_b: list[str],
) -> int | None:
    """Look up and sum joint counts for a two-PHV condition from a pre-computed crosstab.

    The joint distribution is keyed by canonical sorted PHV pair
    (``"phv_smaller+phv_larger"``), with the smaller PHV's values as the outer
    dict keys and the larger PHV's values as inner keys.  This function handles
    the orientation transparently — the caller does not need to know which PHV
    is "outer".

    Parameters
    ----------
    joint_dists_by_pht:
        ``{pht: {pair_key: {outer_val: {inner_val: count}}}}`` from the source
        extract JSON's ``joint_distributions_by_pht`` field.
    pht:
        PHT accession for the source table (e.g. ``"pht001234"``).
    phv_a, phv_b:
        Canonical PHV accession IDs for the two PHVs in the condition.
    vals_a, vals_b:
        Value strings to match for *phv_a* and *phv_b* respectively.

    Returns
    -------
    int or None
        Summed count of rows satisfying the joint condition, or ``None`` if
        the crosstab for this pair/PHT is not available in *joint_dists_by_pht*.
    """
    sorted_pair = sorted([phv_a, phv_b])
    pair_key = "+".join(sorted_pair)
    joint_dist = joint_dists_by_pht.get(pht, {}).get(pair_key)
    if joint_dist is None:
        return None

    # Determine which vals are "outer" (sorted_pair[0]) vs "inner" (sorted_pair[1])
    if phv_a == sorted_pair[0]:
        outer_vals, inner_vals = vals_a, vals_b
    else:
        outer_vals, inner_vals = vals_b, vals_a

    # Normalize target values using the same normalization as the distribution lookup
    norm_outer = {normalize_category_key(_normalize_code(v)) for v in outer_vals}
    norm_inner = {normalize_category_key(_normalize_code(v)) for v in inner_vals}

    count = 0
    for outer_key, inner_dict in joint_dist.items():
        if normalize_category_key(_normalize_code(outer_key)) not in norm_outer:
            continue
        for inner_key, n in inner_dict.items():
            if normalize_category_key(_normalize_code(inner_key)) in norm_inner:
                count += int(n)
    return count


def _expected_summary_from_case_value_exprs(
    entries: list[dict],
    summaries_by_phv: dict[str, dict],
    joint_dists_by_pht: dict[str, dict] | None = None,
) -> dict | None:
    """Build expected harmonized categorical distribution from YAML case() values.

    Some transforms intentionally split one harmonized variable across multiple
    YAML blocks to avoid null propagation or to combine multiple source PHVs.
    When those blocks use simple single-PHV ``case()`` value expressions,
    aggregate source distributions can provide the correct comparison basis
    without adding any metadata to the YAML.  Multi-PHV branch conditions
    require joint counts, which are pre-computed crosstabs if *joint_dists_by_pht*
    is provided; otherwise they yield an unsupported summary.
    """
    expected_counts: dict[str, int] = {}
    contributing_phvs: set[str] = set()

    for entry in entries:
        for expr in entry.get("value_exprs") or []:
            for condition, output in _case_branches(expr):
                output_key = normalize_category_key(output)
                if output_key in {"", "None"}:
                    continue
                if condition == "True":
                    # A non-null else/default branch requires row-level or
                    # complement counts.  A partial distribution would make C2
                    # look like a loss, so leave this comparison on the normal
                    # pooled-source path.
                    return None

                # Extract all PHV references including == and in() patterns
                phv_conds = _extract_phv_conditions(condition)
                distinct_phvs = sorted(phv_conds.keys())

                if len(distinct_phvs) == 0:
                    return None

                elif len(distinct_phvs) == 1:
                    # Single PHV — use marginal distribution (existing behaviour)
                    phv = distinct_phvs[0]
                    vals = phv_conds[phv]
                    # For a single == test, try values in reverse order (matches
                    # original behaviour for compound conditions on one PHV)
                    counted = False
                    for val in reversed(vals):
                        count = _distribution_count_for_code(summaries_by_phv.get(phv), val)
                        if count is None:
                            continue
                        expected_counts[output_key] = expected_counts.get(output_key, 0) + count
                        contributing_phvs.add(phv)
                        counted = True
                        break
                    if not counted:
                        return None

                elif len(distinct_phvs) == 2 and joint_dists_by_pht is not None:
                    # Two-PHV condition — attempt joint distribution lookup
                    phv_a, phv_b = distinct_phvs[0], distinct_phvs[1]
                    # Get PHT from either PHV's source summary
                    pht = (
                        (summaries_by_phv.get(phv_a) or {}).get("_pht")
                        or (summaries_by_phv.get(phv_b) or {}).get("_pht")
                        or ""
                    )
                    count = _count_from_joint_dist(
                        joint_dists_by_pht, pht,
                        phv_a, phv_conds[phv_a],
                        phv_b, phv_conds[phv_b],
                    ) if pht else None
                    if count is None:
                        return _unsupported_joint_summary(
                            None,
                            "yaml_case_value_expr",
                            "case() branch references multiple PHVs; aggregate summaries cannot compute joint counts",
                        )
                    expected_counts[output_key] = expected_counts.get(output_key, 0) + count
                    contributing_phvs.update([phv_a, phv_b])

                else:
                    return _unsupported_joint_summary(
                        None,
                        "yaml_case_value_expr",
                        "case() branch references multiple PHVs; aggregate summaries cannot compute joint counts",
                    )

    total = sum(expected_counts.values())
    if total <= 0:
        return None

    distribution = {
        category: {"n": count, "pct": round(count / total * 100, 2)}
        for category, count in sorted(expected_counts.items())
    }
    return {
        "type": "categorical",
        "n_total": total,
        "n_valid": total,
        "n_missing": 0,
        "pct_missing": 0.0,
        "distribution": distribution,
        "_comparison_basis": "yaml_case_value_expr",
        "_comparison_confidence": "exact",
        "_comparison_phvs": sorted(contributing_phvs),
    }


# ---------------------------------------------------------------------------
# Status-alias normalization
# ---------------------------------------------------------------------------

_STATUS_CATEGORY_ALIASES: dict[str, str] = {
    "NO": "ABSENT",
    "N": "ABSENT",
    "FALSE": "ABSENT",
    "F": "ABSENT",
    "YES": "PRESENT",
    "Y": "PRESENT",
    "TRUE": "PRESENT",
    "T": "PRESENT",
    "U": "UNKNOWN",
    "UNK": "UNKNOWN",
    "UNKNOWN": "UNKNOWN",
}


def _status_alias_map(entries: list[dict]) -> dict[str, str]:
    """Return canonical status aliases implied by the YAML entries."""
    aliases = dict(_STATUS_CATEGORY_ALIASES)
    for entry in entries:
        value_map = entry.get("value_map")
        if not isinstance(value_map, dict):
            continue
        for raw_code, mapped_value in value_map.items():
            mapped = normalize_category_key(mapped_value).upper()
            if mapped in {"PRESENT", "ABSENT", "UNKNOWN", "HISTORICAL"}:
                aliases[normalize_category_key(_normalize_code(raw_code)).upper()] = mapped
    return aliases


def _is_status_transform_entry(entry: dict) -> bool:
    """Whether an entry is expected to emit status-like categorical values."""
    if entry.get("entity_class") == "Condition":
        return True
    value_map = entry.get("value_map")
    if isinstance(value_map, dict):
        mapped_values = {normalize_category_key(v).upper() for v in value_map.values()}
        if mapped_values & {"PRESENT", "ABSENT", "UNKNOWN", "HISTORICAL"}:
            return True
    for expr in entry.get("value_exprs") or []:
        for _, output in _case_branches(expr):
            if normalize_category_key(output).upper() in {"PRESENT", "ABSENT", "UNKNOWN", "HISTORICAL"}:
                return True
    return False


# ---------------------------------------------------------------------------
# Categorical summary builders
# ---------------------------------------------------------------------------

def _categorical_summary_from_counts(
    counts: dict[str, int], *, basis: str, confidence: str = "exact", raw: dict | None = None,
    limitations: list[str] | None = None,
) -> dict | None:
    """Build a categorical aggregate summary from category counts."""
    total = sum(counts.values())
    if total <= 0:
        return None
    n_total = int((raw or {}).get("n_total", total) or total)
    distribution = {
        category: {"n": count, "pct": round(count / total * 100, 2)}
        for category, count in sorted(counts.items())
    }
    return {
        "type": "categorical",
        "n_total": n_total,
        "n_valid": total,
        "n_missing": max(n_total - total, 0),
        "pct_missing": round(max(n_total - total, 0) / n_total * 100, 2) if n_total else 0.0,
        "distribution": distribution,
        "_comparison_basis": basis,
        "_comparison_confidence": confidence,
        "_comparison_limitations": limitations or [],
    }


def _normalize_status_distribution(summary: dict, entries: list[dict]) -> dict:
    """Merge raw Y/N/T/0/1 status codes into PRESENT/ABSENT/UNKNOWN when appropriate."""
    if summary.get("type") != "categorical" or not any(_is_status_transform_entry(e) for e in entries):
        return summary
    dist = summary.get("distribution")
    if not isinstance(dist, dict) or not dist:
        return summary

    aliases = _status_alias_map(entries)
    merged_counts: dict[str, int] = {}
    changed = False
    for category, stats in dist.items():
        mapped = aliases.get(normalize_category_key(_normalize_code(category)).upper())
        output_category = mapped or normalize_category_key(category)
        if mapped and mapped != normalize_category_key(category):
            changed = True
        count = int((stats or {}).get("n", 0) or 0) if isinstance(stats, dict) else 0
        merged_counts[output_category] = merged_counts.get(output_category, 0) + count
    if not changed:
        return summary
    normalized = _categorical_summary_from_counts(
        merged_counts,
        basis=summary.get("_comparison_basis", "yaml_status_aliases"),
        confidence=summary.get("_comparison_confidence", "exact"),
        raw={**summary, "n_total": summary.get("n_total", sum(merged_counts.values()))},
        limitations=summary.get("_comparison_limitations") or [],
    ) or summary
    normalized["_comparison_status_aliases_applied"] = True
    return normalized


def _looks_like_unresolved_expr(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return "case(" in text or "{phv" in text or text.startswith("uuid5(")


def _expected_summary_from_value_map(entry: dict, src_summary: dict) -> dict | None:
    """Build exact expected categorical output for value_mappings on a value slot."""
    value_map = entry.get("value_map")
    if not isinstance(value_map, dict) or not value_map:
        return None
    src_counts = _distribution_count_map(src_summary)
    if not src_counts:
        return None
    normalized_map = {
        normalize_category_key(_normalize_code(code)): normalize_category_key(value)
        for code, value in value_map.items()
    }
    expected_counts: dict[str, int] = {}
    for code, count in src_counts.items():
        mapped = normalized_map.get(code)
        if mapped is None:
            continue
        expected_counts[mapped] = expected_counts.get(mapped, 0) + count
    return _categorical_summary_from_counts(
        expected_counts,
        basis="yaml_value_mappings",
        confidence="exact",
        raw=src_summary,
    )


def _expected_summary_from_concept_value_map(entry: dict, src_summary: dict) -> dict | None:
    """Build exact expected summary for concept-slot value_mappings when PHVs align."""
    concept_value_map = entry.get("concept_value_map")
    concept_code = entry.get("concept_code")
    if not isinstance(concept_value_map, dict) or not concept_code:
        return None
    concept_phv = _canonical_phv_id(entry.get("concept_phv", ""))
    primary_phv = _canonical_phv_id(entry.get("phv_id", ""))
    if concept_phv and primary_phv and concept_phv != primary_phv:
        return None
    src_counts = _distribution_count_map(src_summary)
    if not src_counts:
        return None
    value_map = entry.get("value_map") if isinstance(entry.get("value_map"), dict) else {}
    expected_counts: dict[str, int] = {}
    for code, target in concept_value_map.items():
        if str(target).strip() != str(concept_code).strip():
            continue
        normalized_code = normalize_category_key(_normalize_code(code))
        count = src_counts.get(normalized_code, 0)
        if count <= 0:
            continue
        output = normalize_category_key(value_map.get(str(code), concept_code))
        expected_counts[output] = expected_counts.get(output, 0) + count
    return _categorical_summary_from_counts(
        expected_counts,
        basis="yaml_concept_value_mappings",
        confidence="exact",
        raw=src_summary,
    )


def _expected_summary_from_case_entry(
    entry: dict,
    src_summary: dict,
    summaries_by_phv: dict[str, dict],
    joint_dists_by_pht: dict[str, dict] | None = None,
) -> dict | None:
    """Build expected summary for a single value-slot case expression."""
    counts: dict[str, int] = {}
    explicit_count = 0
    saw_branch = False
    table_total = int(src_summary.get("n_total", 0) or src_summary.get("n_valid", 0) or 0)
    pht = str(src_summary.get("_pht", "") or "")

    for expr in entry.get("value_exprs") or []:
        for condition, output in _case_branches(expr):
            output_key = normalize_category_key(output)
            if output_key in {"", "None"}:
                continue
            saw_branch = True
            if condition == "True":
                if table_total <= 0:
                    return None
                default_count = max(table_total - explicit_count, 0)
                counts[output_key] = counts.get(output_key, 0) + default_count
                continue

            # Extract all PHV references including == and in() patterns
            phv_conds = _extract_phv_conditions(condition)
            distinct_phvs = sorted(phv_conds.keys())

            if len(distinct_phvs) == 0:
                return None

            elif len(distinct_phvs) == 1:
                # Single PHV — use marginal distribution (existing behaviour)
                phv = distinct_phvs[0]
                vals = phv_conds[phv]
                counted = False
                for val in reversed(vals):
                    count = _distribution_count_for_code(summaries_by_phv.get(phv), val)
                    if count is None:
                        continue
                    counts[output_key] = counts.get(output_key, 0) + count
                    explicit_count += count
                    counted = True
                    break
                if not counted:
                    return None

            elif len(distinct_phvs) == 2 and joint_dists_by_pht is not None and pht:
                # Two-PHV condition — attempt joint distribution lookup
                phv_a, phv_b = distinct_phvs[0], distinct_phvs[1]
                count = _count_from_joint_dist(
                    joint_dists_by_pht, pht,
                    phv_a, phv_conds[phv_a],
                    phv_b, phv_conds[phv_b],
                )
                if count is None:
                    return _unsupported_joint_summary(
                        src_summary,
                        "yaml_case_value_expr",
                        "case() branch references multiple PHVs; aggregate summaries cannot compute joint counts",
                    )
                counts[output_key] = counts.get(output_key, 0) + count
                explicit_count += count

            else:
                return _unsupported_joint_summary(
                    src_summary,
                    "yaml_case_value_expr",
                    "case() branch references multiple PHVs; aggregate summaries cannot compute joint counts",
                )

    if not saw_branch:
        return None
    return _categorical_summary_from_counts(
        counts,
        basis="yaml_case_value_expr",
        confidence="exact",
        raw={**src_summary, "n_total": table_total},
    )


def _apply_conversion_factor_to_summary(src_summary: dict, factor: float | None) -> dict:
    """Return a continuous summary in expected harmonized units."""
    if not factor or src_summary.get("type") != "continuous":
        return src_summary
    converted = dict(src_summary)
    for key in ("mean", "min", "max"):
        if converted.get(key) is not None:
            converted[key] = round(float(converted[key]) * factor, 6)
    if converted.get("sd") is not None:
        converted["sd"] = round(abs(float(converted["sd"]) * factor), 6)
    converted["_comparison_basis"] = "yaml_scalar_conversion"
    converted["_comparison_confidence"] = "exact"
    return converted


def _expected_summary_for_entry(
    entry: dict,
    summaries_by_phv: dict[str, dict],
    joint_dists_by_pht: dict[str, dict] | None = None,
) -> dict | None:
    """Build the best available expected post-transform summary for one YAML block."""
    src_summary = entry.get("_source_summary") or summaries_by_phv.get(_canonical_phv_id(entry.get("phv_id", "")))
    if not src_summary:
        return None

    if entry.get("concept_exprs") and len(entry.get("concept_codes") or []) > 1:
        return _unsupported_joint_summary(
            src_summary,
            "yaml_concept_case_expr",
            "concept-slot case() routes one value PHV to multiple concepts; aggregate summaries cannot compute branch-specific counts or moments",
        )

    # Most specific first: value-slot case expressions, then concept routing,
    # then value mappings, then scalar/unit conversion, then direct copy.
    case_summary = _expected_summary_from_case_entry(
        entry, src_summary, summaries_by_phv, joint_dists_by_pht
    )
    if case_summary:
        return case_summary

    concept_summary = _expected_summary_from_concept_value_map(entry, src_summary)
    if concept_summary:
        return concept_summary
    if entry.get("concept_value_map"):
        concept_phv = _canonical_phv_id(entry.get("concept_phv", ""))
        primary_phv = _canonical_phv_id(entry.get("phv_id", ""))
        if concept_phv and primary_phv and concept_phv != primary_phv:
            return None

    value_summary = _expected_summary_from_value_map(entry, src_summary)
    if value_summary:
        return value_summary

    converted = _apply_conversion_factor_to_summary(src_summary, entry.get("conversion_factor"))
    if converted is src_summary:
        copied = dict(src_summary)
        copied.setdefault("_comparison_basis", "source_direct")
        copied.setdefault("_comparison_confidence", "exact")
        return copied
    return converted


def build_expected_summary(
    entries: list[dict],
    summaries_by_phv: dict[str, dict],
    joint_dists_by_pht: dict[str, dict] | None = None,
) -> dict | None:
    """Build expected harmonized aggregate summary from YAML transform semantics."""
    expected_parts: list[dict] = []
    limitations: list[str] = []
    bases: set[str] = set()
    confidences: set[str] = set()

    for entry in entries:
        part = _expected_summary_for_entry(entry, summaries_by_phv, joint_dists_by_pht)
        if part:
            expected_parts.append(part)
            bases.add(part.get("_comparison_basis", "source_direct"))
            confidences.add(part.get("_comparison_confidence", "exact"))
            limitations.extend(part.get("_comparison_limitations") or [])
        else:
            limitations.append(
                f"Unsupported transform in {entry.get('yaml_file', '?')} for {entry.get('phv_id', '?')}"
            )

    if not expected_parts:
        return None
    expected = _aggregate_source_summaries(expected_parts)
    basis = "+".join(sorted(bases)) if bases else "source_direct"
    if "unsupported" in confidences:
        confidence = "unsupported"
    else:
        confidence = "exact" if confidences <= {"exact"} and not limitations else "partial"
    expected["_comparison_basis"] = basis
    expected["_comparison_confidence"] = confidence
    expected["_comparison_limitations"] = limitations
    expected = _normalize_status_distribution(expected, entries)
    return expected


# ---------------------------------------------------------------------------
# Per-PHT pooling
# ---------------------------------------------------------------------------

def _aggregate_source_summaries(per_pht: list[dict]) -> dict:
    """Combine per-PHT source variable summaries into a single pooled summary.

    A YAML transform commonly maps a single harmonized variable (e.g.
    ``measurement_OBA:2045381`` for hematocrit) to source columns drawn from
    several dbGaP tables (one per visit / hospital form / etc.).  The
    harmonized extractor concatenates all rows across visits into a single
    long-format frame, so its ``n_valid`` reflects the full pool.  To
    compare apples to apples, the source side must also be pooled.

    Inputs are summary dicts produced by ``compute_variable_summary`` in
    ``extract_source_summaries.py``.  This helper:

      * Sums ``n_valid``, ``n_total``, ``n_missing`` across all PHTs.
      * Recomputes ``pct_missing`` against the pooled denominator.
      * For continuous variables, computes the n_valid-weighted mean and the
        pooled SD using the standard parallel-sample formula:
            SD_pooled = sqrt( ( sum_i (n_i - 1) * SD_i^2
                                + sum_i n_i * (mean_i - mean_pool)^2 ) / (N - 1) )
        and reports the min of mins, max of maxes.
      * For categorical variables, sums per-value counts and recomputes
        per-value ``pct`` against the pooled n_valid.
      * Preserves ``name``, ``type``, and ``_col_original`` from the first
        non-empty contributor.

    Returns an empty dict if *per_pht* is empty.
    """
    if not per_pht:
        return {}
    if len(per_pht) == 1:
        return dict(per_pht[0])

    # Pooled counts
    n_valid = sum(int(p.get("n_valid", 0) or 0) for p in per_pht)
    n_total = sum(int(p.get("n_total", 0) or 0) for p in per_pht)
    n_missing = sum(int(p.get("n_missing", 0) or 0) for p in per_pht)

    # Take the most common type; fall back to the first non-empty
    types = [p.get("type") for p in per_pht if p.get("type")]
    pooled_type: str | None = None
    if types:
        # All same → use it; otherwise prefer the type from the largest contributor
        if len(set(types)) == 1:
            pooled_type = types[0]
        else:
            largest = max(per_pht, key=lambda p: int(p.get("n_valid", 0) or 0))
            pooled_type = largest.get("type")

    pooled: dict = {
        "type": pooled_type,
        "n_total": n_total,
        "n_valid": n_valid,
        "n_missing": n_missing,
        "pct_missing": (
            round(n_missing / n_total * 100, 2) if n_total > 0 else 0.0
        ),
    }

    # Carry through the first available human-readable name / original column
    for key in ("name", "_col_original"):
        for p in per_pht:
            v = p.get(key)
            if v:
                pooled[key] = v
                break

    if pooled_type == "continuous":
        # n_valid-weighted mean over PHTs that report a mean
        mean_contribs = [
            (int(p.get("n_valid", 0) or 0), p.get("mean"))
            for p in per_pht
            if p.get("mean") is not None and int(p.get("n_valid", 0) or 0) > 0
        ]
        if mean_contribs:
            n_w = sum(n for n, _ in mean_contribs)
            mean_pool = (
                sum(n * float(m) for n, m in mean_contribs) / n_w
                if n_w > 0 else None
            )
            pooled["mean"] = round(mean_pool, 6) if mean_pool is not None else None
        else:
            pooled["mean"] = None

        # Pooled SD via parallel-samples formula.  Contributors with n=1 have
        # no within-group SD, but still contribute to between-group variance.
        sd_contribs = [
            (int(p.get("n_valid", 0) or 0), p.get("mean"), p.get("sd"))
            for p in per_pht
            if p.get("mean") is not None and int(p.get("n_valid", 0) or 0) > 0
        ]
        if sd_contribs and pooled.get("mean") is not None:
            mean_pool_val = pooled["mean"]
            n_total_for_sd = sum(n for n, _, _ in sd_contribs)
            if n_total_for_sd > 1:
                within = sum(
                    (n - 1) * float(sd) ** 2
                    for n, _, sd in sd_contribs
                    if sd is not None and n > 1
                )
                between = sum(
                    n * (float(m) - mean_pool_val) ** 2
                    for n, m, _ in sd_contribs
                )
                pooled_var = (within + between) / (n_total_for_sd - 1)
                pooled["sd"] = (
                    round(math.sqrt(pooled_var), 6) if pooled_var >= 0 else None
                )
            else:
                pooled["sd"] = None
        else:
            pooled["sd"] = None

        # Min-of-mins, max-of-maxes
        mins = [p.get("min") for p in per_pht if p.get("min") is not None]
        maxs = [p.get("max") for p in per_pht if p.get("max") is not None]
        if mins:
            pooled["min"] = min(float(x) for x in mins)
        if maxs:
            pooled["max"] = max(float(x) for x in maxs)

    elif pooled_type == "categorical":
        # Sum per-value counts across PHTs, then recompute pct.  The source
        # extractor emits distribution: {code: {n, pct}}; accept legacy
        # values/count defensively, but write the canonical distribution schema
        # consumed by check_c7_categorical_distribution().
        merged_distribution: dict[str, dict] = {}
        for p in per_pht:
            dist = p.get("distribution") or p.get("values") or {}
            if not isinstance(dist, dict):
                continue
            for code, info in dist.items():
                if not isinstance(info, dict):
                    continue
                cnt = int(info.get("n", info.get("count", 0)) or 0)
                slot = merged_distribution.setdefault(code, {"n": 0})
                slot["n"] += cnt
        for code, slot in merged_distribution.items():
            slot["pct"] = (
                round(slot["n"] / n_valid * 100, 2) if n_valid > 0 else 0.0
            )
        pooled["distribution"] = merged_distribution

    return pooled
