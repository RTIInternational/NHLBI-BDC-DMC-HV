"""YAML-driven crosswalk building for the compare pipeline.

Loads dbGaP cache (PHV→name, PHV→PHT, PHV→type maps) and parses HV transform
YAMLs to map harmonized concepts back to source variables. Pools per-PHT
source summaries when multiple tables contribute to a single longitudinal
harmonized variable, and emits a list of "matches" — each is a dict
describing one source-harmonized pair with all the context the check
functions need (resolved source summary, conversion factor, value mappings,
etc.).

Public API:
- load_phv_name_map / load_phv_to_pht_map / load_phv_type_map /
  load_phv_value_codes_map — read dbGaP cache.
- determine_comparison_type — pick expected type given dbGaP > YAML > observed.
- authoritative_source_type_for_match — dbGaP-type consensus for pooled PHVs.
- build_yaml_crosswalk — YAML-driven crosswalk parsing entry point.
- build_variable_crosswalk — top-level orchestrator (YAML-driven with
  multi-PHT aggregation).
- build_expected_summary — derive expected harmonized summary from YAML
  value_mappings.
- _normalize_harmonized_vars — fix dm-bip serialization quirks (used by main).
- _expected_harmonized_n — compute expected harmonized n_valid for concept
  routing (used by C2).
- Helpers used by checks: _distribution_count_map,
  _codes_are_numeric_or_sentinel, _normalize_code, _is_null_sentinel_code.

A number of the private helpers here (with leading underscore) are imported
by check modules. That's a known sharp edge — they should eventually move
to a shared util module or become public API. For now they stay underscored
and we let checks import them by name.
"""

from __future__ import annotations

import ast
import math
import re
import sys
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import yaml

from hv_dataqc.compare._common import CrosswalkBuildError
from hv_dataqc.hv_dataqc_common import (
    canonical_phv_id,
    load_phv_name_map as _shared_load_phv_name_map,
    normalize_category_key,
)

_canonical_phv_id = canonical_phv_id


# ---------------------------------------------------------------------------
# Source-extract lookup helpers
# ---------------------------------------------------------------------------

def _build_variables_by_name(
    variables_by_pht: dict[str, dict],
) -> dict[str, dict[str, dict]]:
    """Index the source extract by column name then PHT.

    Returns ``{col_name: {pht: summary}}``. This is the canonical view used
    when the crosswalk needs to look up a source column's stats by its bare
    name and disambiguate across PHTs (multi-PHT longitudinal cohorts).

    Distinct from ``variables_by_pht`` (the extractor's emission), which is
    keyed PHT-first. Both views share the same underlying summary objects.
    """
    by_name: dict[str, dict[str, dict]] = {}
    for pht, pht_vars in variables_by_pht.items():
        for col, summary in pht_vars.items():
            by_name.setdefault(col, {})[pht] = summary
    return by_name


def _pick_single_pht_summary(
    variables_by_name: dict[str, dict[str, dict]],
    col: str,
) -> dict | None:
    """Pick one PHT's summary for a column when caller can't disambiguate.

    Current behavior: return the first PHT's summary (Python dict insertion
    order, matching the extractor's emission order). This preserves the
    legacy "first-PHT-wins" semantics from when the source extractor emitted
    a flat ``variables`` dict with the same rule.

    Step 5 of the Phase B refactor will replace this with a per-variable
    FAIL CheckResult that lists all contributing PHTs so reviewers can fix
    the YAML/cache rather than silently accepting one PHT's stats.
    """
    pht_map = variables_by_name.get(col)
    if not pht_map:
        return None
    # First inserted PHT wins.
    first_pht = next(iter(pht_map))
    return pht_map[first_pht]


# ---------------------------------------------------------------------------
# PHV name map (from dbGaP data dict XML)
# ---------------------------------------------------------------------------

def load_phv_name_map(cache_dir: Path) -> dict[str, str]:
    """Load PHV-accession → variable-name map from dbGaP data-dict XML files.

    Reads ``*.data_dict.xml`` under ``<cache_dir>/pheno_variable_summaries/``.
    Returns empty dict if path not found (graceful degradation).
    """
    return _shared_load_phv_name_map(
        cache_dir,
        info=lambda msg: print(f"  {msg}"),
        warning=lambda msg: print(f"  WARNING: {msg}"),
    )


def load_phv_to_pht_map(cache_dir: Path) -> dict[str, str]:
    """Build PHV-accession -> PHT-accession map from dbGaP data-dict XML files.

    Each ``*.data_dict.xml`` filename encodes the PHT accession (e.g.
    ``phs000179.v7.pht002239.v8...data_dict.xml`` -> ``pht002239``).
    Every ``<variable id="phvXXXXXX">`` element inside maps to that PHT.

    Returns ``{phv_id: pht_id}`` (e.g. ``{"phv00169419": "pht002239"}``).
    Returns empty dict when cache is unavailable.
    """
    phv_to_pht: dict[str, str] = {}
    pheno_dir = cache_dir / "pheno_variable_summaries"
    if not pheno_dir.exists():
        return phv_to_pht

    _pht_file_re = re.compile(r"\bpht(\d{6,7})\b", re.IGNORECASE)

    for dd_file in sorted(pheno_dir.glob("*.data_dict.xml")):
        m = _pht_file_re.search(dd_file.name)
        if not m:
            continue
        pht_id = f"pht{m.group(1)}"
        try:
            tree = ET.parse(dd_file)
            for var in tree.getroot().findall(".//variable"):
                phv_id = _canonical_phv_id(var.get("id", ""))
                if phv_id.startswith("phv"):
                    phv_to_pht[phv_id] = pht_id
        except ET.ParseError as exc:
            print(f"  WARNING: Could not parse PHV->PHT XML {dd_file.name}: {exc}")

    print(f"  PHV->PHT map: {len(phv_to_pht)} entries across "
          f"{len(set(phv_to_pht.values()))} PHTs")
    return phv_to_pht


# dbGaP <type> text values that map unambiguously to continuous / categorical.
# Anything not in these sets is left as None (keep heuristic result).
# Covers both simple vocabulary (CHS, MESA, …) and compound vocabulary (ARIC, FHS, …).
_DBGAP_CONTINUOUS_TYPES: frozenset[str] = frozenset({
    # simple vocabulary
    "integer", "decimal", "float", "num",
    # compound vocabulary (ARIC / FHS style)
    "continuous integer", "continuous decimal", "continuous",
    "numeric", "integer decimal",
})
_DBGAP_CATEGORICAL_TYPES: frozenset[str] = frozenset({
    # simple vocabulary
    "encoded", "string", "char", "character",
    # compound vocabulary (ARIC / FHS style)
    "enumerated integer", "encoded value", "text",
})
# Keyword fallback: if the raw type string contains any of these words it maps
# unambiguously to continuous/categorical — covers multi-word variants and
# compound strings like "string, encoded value" or "encoded values" without
# requiring exhaustive enumeration.  Typos ("sting", "strin") intentionally
# left unrecognized so we don't over-infer from garbled data.
_DBGAP_CONTINUOUS_KEYWORDS: frozenset[str] = frozenset(
    {"continuous", "numeric", "decimal", "float"}
)
_DBGAP_CATEGORICAL_KEYWORDS: frozenset[str] = frozenset(
    {"encoded", "string", "text", "character", "char"}
)


def load_phv_type_map(cache_dir: Path) -> dict[str, str]:
    """Build PHV-accession -> inferred-type map from dbGaP data-dict XML files.

    For each ``<variable>`` element the ``<type>`` child text is mapped to
    either ``"continuous"`` or ``"categorical"`` using the dbGaP vocabulary.
    Covers both the simple vocabulary (CHS/MESA/WHI: ``integer``, ``decimal``,
    ``encoded``, …) and the compound vocabulary (ARIC/FHS: ``continuous integer``,
    ``continuous decimal``, ``enumerated integer``, ``encoded value``, ``numeric``,
    ``text``, …).

    PHVs whose dbGaP ``<type>`` is absent or unrecognized are omitted; the
    heuristic in the source extractor applies for them.

    Returns ``{phv_id: "continuous" | "categorical"}``.
    Returns empty dict when cache is unavailable.
    """
    phv_type: dict[str, str] = {}
    pheno_dir = cache_dir / "pheno_variable_summaries"
    if not pheno_dir.exists():
        return phv_type

    for dd_file in sorted(pheno_dir.glob("*.data_dict.xml")):
        try:
            tree = ET.parse(dd_file)
            for var in tree.getroot().findall(".//variable"):
                phv_id = _canonical_phv_id(var.get("id", ""))
                if not phv_id.startswith("phv"):
                    continue
                type_el = var.find("type")
                if type_el is None or not type_el.text:
                    continue
                raw = type_el.text.strip().lower()
                if raw in _DBGAP_CONTINUOUS_TYPES:
                    phv_type[phv_id] = "continuous"
                elif raw in _DBGAP_CATEGORICAL_TYPES:
                    phv_type[phv_id] = "categorical"
                elif any(kw in raw for kw in _DBGAP_CONTINUOUS_KEYWORDS):
                    phv_type[phv_id] = "continuous"
                elif any(kw in raw for kw in _DBGAP_CATEGORICAL_KEYWORDS):
                    phv_type[phv_id] = "categorical"
                # else: unrecognized type — omit, keep source-extractor heuristic
        except ET.ParseError as exc:
            print(f"  WARNING: Could not parse PHV-type XML {dd_file.name}: {exc}")

    print(f"  PHV-type map: {len(phv_type)} entries "
          f"({sum(1 for v in phv_type.values() if v == 'continuous')} continuous, "
          f"{sum(1 for v in phv_type.values() if v == 'categorical')} categorical)")
    return phv_type


def authoritative_source_type_for_match(match: dict, phv_type_map: dict[str, str]) -> str | None:
    """Return dbGaP source type for a crosswalk match when all PHVs agree.

    Pooled YAML matches can aggregate several source PHVs.  A single
    ``match["phv_id"]`` may be only the first contributor, so use all resolved
    source PHVs where available and override the observed source summary only
    when the dbGaP types are unanimous.
    """
    phv_ids = list(
        dict.fromkeys(
            (match.get("_source_phvs") or [])
            + (match.get("_phv_ids") or [])
            + ([match.get("phv_id")] if match.get("phv_id") else [])
        )
    )
    types = {
        phv_type_map.get(_canonical_phv_id(phv_id))
        for phv_id in phv_ids
        if phv_type_map.get(_canonical_phv_id(phv_id))
    }
    if len(types) == 1:
        return next(iter(types))
    return None


def _yaml_intent_type_for_match(match: dict) -> str | None:
    """Infer comparison type from YAML semantics when dbGaP type is unavailable."""
    entries = match.get("_yaml_entries") or [match]

    if any(entry.get("is_static") for entry in entries):
        return "categorical"
    if any(entry.get("value_map") or entry.get("concept_value_map") for entry in entries):
        return "categorical"

    entity_classes = {entry.get("entity_class") for entry in entries if entry.get("entity_class")}
    if entity_classes and entity_classes <= {"Condition", "Demography", "DrugExposure", "Procedure"}:
        return "categorical"

    if any(entry.get("conversion_factor") for entry in entries):
        return "continuous"
    if entity_classes and entity_classes <= {"MeasurementObservation", "MeasurementObservationSet"}:
        return "continuous"

    return None


def determine_comparison_type(
    match: dict,
    src_var: dict,
    phv_type_map: dict[str, str],
) -> dict[str, Any]:
    """Determine the source-driven type expected for a source/harmonized match.

    The harmonized extractor's observed type is deliberately excluded from this
    decision; it is what C11 validates against the expected source/YAML type.
    """
    dbgap_type = authoritative_source_type_for_match(match, phv_type_map)
    yaml_type = _yaml_intent_type_for_match(match)
    observed_source_type = src_var.get("type")

    if dbgap_type:
        expected_type = dbgap_type
        basis = "dbgap_phv_type_consensus"
    elif yaml_type:
        expected_type = yaml_type
        basis = "yaml_transform_intent"
    elif observed_source_type in {"continuous", "categorical"}:
        expected_type = observed_source_type
        basis = "source_extract_observed_type"
    else:
        expected_type = None
        basis = "unknown"

    detail: dict[str, Any] = {
        "expected_type": expected_type,
        "basis": basis,
        "dbgap_type": dbgap_type,
        "yaml_intent_type": yaml_type,
        "observed_source_type": observed_source_type,
    }
    if dbgap_type and yaml_type and dbgap_type != yaml_type:
        detail["type_evidence_conflict"] = True
    return detail


def load_phv_value_codes_map(cache_dir: Path) -> dict[str, set[str]]:
    """Build PHV-accession -> coded value set from dbGaP data-dict XML files."""
    phv_codes: dict[str, set[str]] = {}
    pheno_dir = cache_dir / "pheno_variable_summaries"
    if not pheno_dir.exists():
        return phv_codes

    for dd_file in sorted(pheno_dir.glob("*.data_dict.xml")):
        try:
            tree = ET.parse(dd_file)
            for var in tree.getroot().findall(".//variable"):
                phv_id = _canonical_phv_id(var.get("id", ""))
                if not phv_id.startswith("phv"):
                    continue
                codes = {
                    normalize_category_key(_normalize_code(value.get("code", "")))
                    for value in var.findall("value")
                    if value.get("code") is not None
                }
                if codes:
                    phv_codes[phv_id] = codes
        except ET.ParseError as exc:
            print(f"  WARNING: Could not parse PHV codes XML {dd_file.name}: {exc}")

    print(f"  PHV coded-value map: {len(phv_codes)} entries")
    return phv_codes


# ---------------------------------------------------------------------------
# YAML crosswalk construction
# ---------------------------------------------------------------------------

# Mapping from crosswalk entity prefix (e.g. "condition_") to the
# "discovered:" namespace used by newer BDC extractor builds
# (e.g. "discovered:condition:").  Older extractor builds used the bare
# "condition_X" format; newer ones prefix with "discovered:".  The compare
# tool tries both forms when resolving a harmonized key.
_CROSSWALK_TO_DISCOVERED: dict[str, str] = {
    "condition_": "discovered:condition:",
    "measurement_": "discovered:measurement:",
    "observation_": "discovered:observation:",
    "drug_": "discovered:drug:",
    "procedure_": "discovered:procedure:",
}


def _to_discovered_key(harmonized_key: str) -> str | None:
    """Convert a bare crosswalk key to its discovered: equivalent, or None.

    ``condition_MONDO:0004981`` -> ``discovered:condition:MONDO:0004981``
    ``demog_annotated_sex``     -> None (demography uses different naming)
    """
    for old_prefix, new_prefix in _CROSSWALK_TO_DISCOVERED.items():
        if harmonized_key.startswith(old_prefix):
            return new_prefix + harmonized_key[len(old_prefix):]
    return None


def _extract_value_mappings(slot_body: dict) -> dict | None:
    """Extract value_mappings dict from a slot body, or None."""
    vm = slot_body.get("value_mappings")
    if not vm or not isinstance(vm, dict):
        return None
    return {str(k): str(v) for k, v in vm.items()}


_CASE_BRANCH_RE = re.compile(
    r"\((?P<condition>[^,]+),\s*"
    r"(?P<value>None|True|False|'[^']*'|\"[^\"]*\"|[A-Za-z0-9_:.-]+)\)"
)
_PHV_EQ_RE = re.compile(
    r"\{(?P<phv>phv\d+)\}\s*==\s*"
    r"(?P<value>'[^']*'|\"[^\"]*\"|-?\d+(?:\.\d+)?|[A-Za-z0-9_:.-]+)",
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


def _expected_summary_from_case_value_exprs(
    entries: list[dict], summaries_by_phv: dict[str, dict]
) -> dict | None:
    """Build expected harmonized categorical distribution from YAML case() values.

    Some transforms intentionally split one harmonized variable across multiple
    YAML blocks to avoid null propagation or to combine multiple source PHVs.
    When those blocks use simple ``case()`` value expressions, aggregate source
    distributions can provide the correct comparison basis without adding any
    metadata to the YAML.  For multi-PHV conditions, prefer the last equality
    test with a usable distribution; this captures common gated patterns such
    as ``TBEA1 == 1 and TBEA3 == 3`` where TBEA1 selects the skip pattern and
    TBEA3 supplies the emitted category.
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
                eq_tests = list(_PHV_EQ_RE.finditer(condition))
                if not eq_tests:
                    return None
                counted = False
                for eq in reversed(eq_tests):
                    phv = _canonical_phv_id(eq.group("phv"))
                    code = _strip_expr_literal(eq.group("value"))
                    count = _distribution_count_for_code(summaries_by_phv.get(phv), code)
                    if count is None:
                        continue
                    expected_counts[output_key] = expected_counts.get(output_key, 0) + count
                    contributing_phvs.add(phv)
                    counted = True
                    break
                if not counted:
                    return None

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
        "_comparison_phvs": sorted(contributing_phvs),
    }


_COMMON_UNIT_FACTORS: dict[tuple[str, str], float] = {
    ("[lb_av]", "kg"): 0.453592,
    ("lb", "kg"): 0.453592,
    ("lbs", "kg"): 0.453592,
    ("kg", "[lb_av]"): 2.20462,
    ("kg", "lb"): 2.20462,
    ("kg", "lbs"): 2.20462,
    ("in", "cm"): 2.54,
    ("[in_i]", "cm"): 2.54,
    ("cm", "in"): 0.393701,
    ("mg/dL", "mmol/L glucose"): 0.0555,
    ("mg/dL", "mmol/L cholesterol"): 0.02586,
    ("mg/dL", "mmol/L triglycerides"): 0.01129,
}


def _unit_conversion_factor(unit_conversion: dict | None) -> float | None:
    """Return a known scalar factor for a YAML ``unit_conversion`` block."""
    if not isinstance(unit_conversion, dict):
        return None
    source_unit = str(unit_conversion.get("source_unit", "")).strip()
    target_unit = str(unit_conversion.get("target_unit", "")).strip()
    if not source_unit or not target_unit:
        return None
    direct = _COMMON_UNIT_FACTORS.get((source_unit, target_unit))
    if direct is not None:
        return direct
    # A few transforms use only the target dimensionality.  Keep these exact
    # mappings conservative to avoid inventing conversion semantics.
    if source_unit == "mg/dL" and target_unit == "mmol/L":
        return None
    return None


def _distribution_count_map(summary: dict | None) -> dict[str, int]:
    """Return normalized category -> count for a categorical summary."""
    dist = (summary or {}).get("distribution") or (summary or {}).get("values") or {}
    if not isinstance(dist, dict):
        return {}
    counts: dict[str, int] = {}
    for raw_code, info in dist.items():
        key = normalize_category_key(_normalize_code(raw_code))
        if isinstance(info, dict):
            count = int(info.get("n", info.get("count", 0)) or 0)
        else:
            try:
                count = int(info)
            except (TypeError, ValueError):
                count = 0
        counts[key] = counts.get(key, 0) + count
    return counts


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

_NULL_SENTINEL_CODES: set[str] = {
    "",
    ".",
    "*",
    "**",
    "***",
    "****",
    "*****",
    "******",
    "*******",
    "********",
    "*********",
    "NA",
    "N/A",
    "NULL",
    "NONE",
    "MISSING",
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


def _is_null_sentinel_code(code: Any) -> bool:
    """Return True for common dbGaP/SAS/suppression sentinels, not semantic categories."""
    normalized = normalize_category_key(_normalize_code(code)).upper()
    if normalized in _NULL_SENTINEL_CODES:
        return True
    return bool(re.fullmatch(r"\*{2,}", normalized))


def _codes_are_numeric_or_sentinel(codes: set[str]) -> bool:
    """Whether all observed categorical keys are parseable numeric values or null sentinels."""
    meaningful = [code for code in codes if not _is_null_sentinel_code(code)]
    if not meaningful:
        return False
    for code in meaningful:
        try:
            float(str(code))
        except (TypeError, ValueError):
            return False
    return True


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


def _expected_summary_from_case_entry(entry: dict, src_summary: dict, summaries_by_phv: dict[str, dict]) -> dict | None:
    """Build expected summary for a single value-slot case expression."""
    counts: dict[str, int] = {}
    explicit_count = 0
    saw_branch = False
    table_total = int(src_summary.get("n_total", 0) or src_summary.get("n_valid", 0) or 0)

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
            eq_tests = list(_PHV_EQ_RE.finditer(condition))
            if not eq_tests:
                return None
            counted = False
            for eq in reversed(eq_tests):
                phv = _canonical_phv_id(eq.group("phv"))
                code = _strip_expr_literal(eq.group("value"))
                count = _distribution_count_for_code(summaries_by_phv.get(phv), code)
                if count is None:
                    continue
                counts[output_key] = counts.get(output_key, 0) + count
                explicit_count += count
                counted = True
                break
            if not counted:
                return None
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


def _expected_summary_for_entry(entry: dict, summaries_by_phv: dict[str, dict]) -> dict | None:
    """Build the best available expected post-transform summary for one YAML block."""
    src_summary = entry.get("_source_summary") or summaries_by_phv.get(_canonical_phv_id(entry.get("phv_id", "")))
    if not src_summary:
        return None

    # Most specific first: value-slot case expressions, then concept routing,
    # then value mappings, then scalar/unit conversion, then direct copy.
    case_summary = _expected_summary_from_case_entry(entry, src_summary, summaries_by_phv)
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


def build_expected_summary(entries: list[dict], summaries_by_phv: dict[str, dict]) -> dict | None:
    """Build expected harmonized aggregate summary from YAML transform semantics."""
    expected_parts: list[dict] = []
    limitations: list[str] = []
    bases: set[str] = set()
    confidences: set[str] = set()

    for entry in entries:
        part = _expected_summary_for_entry(entry, summaries_by_phv)
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
    confidence = "exact" if confidences <= {"exact"} and not limitations else "partial"
    expected["_comparison_basis"] = basis
    expected["_comparison_confidence"] = confidence
    expected["_comparison_limitations"] = limitations
    expected = _normalize_status_distribution(expected, entries)
    return expected


# Matches a quoted CURIE-like string inside case() expressions or bare values:
# e.g.  'OMOP:4041720'  "MONDO:0013792"  OBA:2045443  HP:0002140
_CURIE_QUOTED_RE = re.compile(r"['\"]([A-Z][A-Z0-9]+:[A-Za-z0-9.:_-]+)['\"]")
# Matches a bare (unquoted) CURIE value as-is (for value_mappings dict values):
_CURIE_BARE_RE = re.compile(r"^[A-Z][A-Z0-9]+:[A-Za-z0-9.:_-]+$")


def _concept_codes_from_expr(expr: str) -> list[str]:
    """Extract all unique CURIE-like concept codes quoted inside a case() or similar expression.

    Returns a deduplicated list preserving order of first occurrence.
    Returns an empty list if the expression contains no recognizable CURIEs,
    in which case the caller should fall back to treating *expr* as a literal.
    """
    codes = _CURIE_QUOTED_RE.findall(expr)
    # Deduplicate while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for c in codes:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _concept_codes_from_value_mappings(slot_body: dict) -> list[str]:
    """Extract unique CURIE-like concept codes from a slot's value_mappings values.

    Used when a concept slot (observation_type, condition_concept, …) is driven
    by a source-coded column via ``value_mappings``, e.g.::

        condition_concept:
          populated_from: phv00106406
          value_mappings:
            '1': MONDO:0005015
            '2': MONDO:0006920

    Returns deduplicated codes in order of first occurrence.
    """
    vm = slot_body.get("value_mappings")
    if not vm or not isinstance(vm, dict):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for v in vm.values():
        sv = str(v).strip()
        if _CURIE_BARE_RE.match(sv) and sv not in seen:
            seen.add(sv)
            out.append(sv)
    return out


# Matches simple scalar arithmetic on a single PHV placeholder:
#   '{phv00105771} * 7'   -> factor 7.0
#   '{phv00098799} * 365' -> factor 365.0
#   '{phv00012345} / 1000'-> factor 0.001  (stored as reciprocal)
# Compound exprs (multiple PHVs, additions, etc.) are intentionally NOT matched.
_SCALAR_MULT_RE = re.compile(
    r"""
    (?:                              # PHV * scalar
        \{phv\d+\}\s*([*/])\s*(\d+(?:\.\d+)?)
    )
    |
    (?:                              # scalar * PHV
        (\d+(?:\.\d+)?)\s*([*/])\s*\{phv\d+\}
    )
    """,
    re.VERBOSE,
)


def _extract_conversion_factor(expr: str) -> float | None:
    """Extract a scalar conversion factor from a simple PHV arithmetic expression.

    Detects patterns where a single PHV is multiplied or divided by a literal
    scalar, e.g.::

        ``{phv00105771} * 7``      → 7.0
        ``{phv00098799} * 365``    → 365.0
        ``{phv00012345} / 1000``   → 0.001  (reciprocal stored as factor)

    Returns None for compound expressions involving multiple PHVs, additions,
    or any pattern that cannot be expressed as a single scalar factor.
    """
    # Require exactly one PHV — compound exprs don't produce a single factor
    if len(re.findall(r"phv\d+", expr)) != 1:
        return None
    m = _SCALAR_MULT_RE.search(expr)
    if not m:
        return None
    # Group layout: (op1, scalar1) for PHV*scalar, (scalar2, op2) for scalar*PHV
    if m.group(1) and m.group(2):          # PHV op scalar
        op, scalar_str = m.group(1), m.group(2)
    elif m.group(3) and m.group(4):        # scalar op PHV
        op, scalar_str = m.group(4), m.group(3)
    else:
        return None
    scalar = float(scalar_str)
    if scalar == 0:
        return None
    return (1.0 / scalar) if op == "/" else scalar


def _extract_crosswalk_from_class_derivations(
    class_derivations: dict,
    yaml_filename: str,
    phv_names: dict[str, str],
    crosswalk: list[dict],
    inside_mos: bool = False,
) -> None:
    """Recursively extract crosswalk entries from a class_derivations block.

    When *inside_mos* is True, the caller is iterating nested
    MeasurementObservation blocks inside a MeasurementObservationSet's
    ``observations`` list.  In that case method_type — when present on the
    inner block — is appended to the harmonized_key as ``|<method_type>``,
    mirroring how ``process_measurement_observation_sets()`` in the harmonized
    extractor groups MOS rows.  Standalone MeasurementObservation files keep
    bare ``measurement_<concept>`` keys because the standalone extractor path
    does not include method_type in its grouping.
    """
    ENTITY_PREFIX = {
        "Condition": "condition_",
        "MeasurementObservation": "measurement_",
        "MeasurementObservationSet": "measurement_",
        "Observation": "observation_",
        "DrugExposure": "drug_",
        "Procedure": "procedure_",
        "Demography": "demog_",
    }
    CONCEPT_SLOTS = {
        "Condition": "condition_concept",
        "MeasurementObservation": "observation_type",
        "MeasurementObservationSet": "observation_type",
        "Observation": "observation_type",
        "DrugExposure": "drug_concept",
        "Procedure": "procedure_type",
    }
    VALUE_SLOTS = {
        "Condition": "condition_status",
        "MeasurementObservation": "value_quantity",
        "Observation": "value_enum",
        "DrugExposure": "drug_status",
        "Procedure": "procedure_status",
    }

    for class_name, class_body in class_derivations.items():
        if not isinstance(class_body, dict):
            continue

        entity_class = class_name
        if entity_class not in ENTITY_PREFIX:
            print(
                f"  WARNING: Unknown entity class {entity_class!r} in {yaml_filename}; "
                f"using fallback prefix {entity_class.lower()}_. Add this class to "
                "ENTITY_PREFIX/CONCEPT_SLOTS/VALUE_SLOTS if it should be crosswalked.",
                file=sys.stderr,
            )
        slots = class_body.get("slot_derivations", {})
        if not isinstance(slots, dict):
            continue

        # Find the concept code(s) for this derivation.
        # A slot may yield MULTIPLE concept codes when:
        #   - observation_type / condition_concept uses a case() expression with
        #     different CURIEs in each branch (e.g. hdl.yaml, stroke.yaml)
        #   - condition_concept uses value_mappings whose values are CURIEs
        #     (e.g. diabetes.yaml pht001490 block)
        # We emit one crosswalk entry per unique code so every possible
        # harmonized key gets a source-side match.
        concept_codes: list[str] = []
        # When the concept slot (e.g. condition_concept) routes one source
        # column to MULTIPLE concept CURIEs via value_mappings, we capture the
        # raw {source_code: CURIE} dict here.  Threaded onto each emitted
        # crosswalk entry as ``concept_value_map`` so C2 can compute the
        # expected harmonized N as the sum of source rows whose code routes to
        # *this* concept (instead of the full source n_valid).
        concept_value_map: dict | None = None
        concept_phv: str | None = None
        concept_slot_name = CONCEPT_SLOTS.get(entity_class)
        if concept_slot_name and concept_slot_name in slots:
            slot = slots[concept_slot_name]
            if isinstance(slot, dict):
                val = slot.get("value")
                if val and isinstance(val, str):
                    concept_codes = [val.strip()]
                else:
                    expr = slot.get("expr", "")
                    pf = slot.get("populated_from", "")
                    if str(pf).startswith("phv"):
                        concept_phv = _canonical_phv_id(str(pf))
                    if expr and not pf:
                        # Try to extract CURIEs from a case() or compound expr.
                        codes = _concept_codes_from_expr(expr)
                        if codes:
                            concept_codes = codes
                        else:
                            # Treat as a literal (e.g. a plain string value)
                            concept_codes = [expr.strip("'\" ")]
                    elif pf and not str(pf).startswith("phv"):
                        concept_codes = [str(pf).strip()]
                    # Fallback: value_mappings values on the concept slot
                    # (e.g. condition_concept: populated_from: phv…  value_mappings: …)
                    if not concept_codes:
                        vm_codes = _concept_codes_from_value_mappings(slot)
                        if vm_codes:
                            concept_codes = vm_codes
                            vm_raw = slot.get("value_mappings")
                            if isinstance(vm_raw, dict):
                                concept_value_map = {
                                    str(k): str(v).strip()
                                    for k, v in vm_raw.items()
                                }

        # --- Demography: each slot maps a separate PHV → demog_<slot> ---
        if entity_class == "Demography":
            for slot_name, slot_body in slots.items():
                if not isinstance(slot_body, dict):
                    continue
                pf = str(slot_body.get("populated_from", ""))
                if pf.startswith("phv"):
                    src_name = phv_names.get(pf, "")
                    if not src_name:
                        continue
                    crosswalk.append(
                        {
                            "source_key": src_name,
                            "harmonized_key": f"demog_{slot_name}",
                            "match_method": "yaml",
                            "yaml_file": yaml_filename,
                            "phv_id": pf,
                            "concept_code": None,
                            "entity_class": entity_class,
                            "value_map": _extract_value_mappings(slot_body),
                            "is_static": False,
                        }
                    )
                    continue

                static_value = slot_body.get("value")
                static_expr = slot_body.get("expr")
                if static_value is not None or static_expr is not None:
                    crosswalk.append(
                        {
                            "source_key": "__static__",
                            "harmonized_key": f"demog_{slot_name}",
                            "match_method": "yaml+static",
                            "yaml_file": yaml_filename,
                            "phv_id": "",
                            "concept_code": None,
                            "entity_class": entity_class,
                            "value_map": None,
                            "is_static": True,
                            "static_value": static_value if static_value is not None else static_expr,
                            "static_pht": class_body.get("populated_from"),
                        }
                    )
            continue

        # --- MeasurementObservationSet: recurse into inner MO blocks ---
        if entity_class == "MeasurementObservationSet":
            obs_slot = slots.get("observations", {})
            if isinstance(obs_slot, dict):
                for od in obs_slot.get("object_derivations", []):
                    if isinstance(od, dict):
                        inner_cd = od.get("class_derivations")
                        if inner_cd and isinstance(inner_cd, dict):
                            _extract_crosswalk_from_class_derivations(
                                inner_cd,
                                yaml_filename,
                                phv_names,
                                crosswalk,
                                inside_mos=True,
                            )
            continue

        # --- Standard path: gather PHVs and concept code ---
        primary_phvs: list[dict] = []
        value_exprs: list[str] = []
        value_slot_name = VALUE_SLOTS.get(entity_class, "")

        for slot_name, slot_body in slots.items():
            if not isinstance(slot_body, dict):
                continue
            pf = str(slot_body.get("populated_from", ""))
            if pf.startswith("phv"):
                primary_phvs.append(
                    {
                        "phv": pf,
                        "slot": slot_name,
                        "is_value_slot": (
                            slot_name == value_slot_name
                            or slot_name in ("value_decimal", "value_integer", "value_coded")
                            or slot_name.startswith("value")
                        ),
                        "value_map": _extract_value_mappings(slot_body),
                        "conversion_factor": None,
                    }
                )
            # PHVs referenced inside case() expressions
            expr = slot_body.get("expr", "")
            if isinstance(expr, str):
                is_value_expr = (
                    slot_name == value_slot_name
                    or slot_name in ("value_decimal", "value_integer", "value_coded")
                    or slot_name.startswith("value")
                )
                if is_value_expr:
                    value_exprs.append(expr)
                cf = (
                    _extract_conversion_factor(expr)
                    if slot_name in ("value_decimal", "value_integer")
                    else None
                )
                for phv in re.findall(r"(phv\d+)", expr):
                    primary_phvs.append(
                        {
                            "phv": phv,
                            "slot": slot_name,
                            "is_value_slot": is_value_expr,
                            "value_map": _extract_value_mappings(slot_body),
                            "conversion_factor": cf,
                            "expr": expr,
                        }
                    )

            # PHVs nested inside object_derivations (e.g. Quantity)
            obj_d = slot_body.get("object_derivations")
            if isinstance(obj_d, list):
                for od in obj_d:
                    if not isinstance(od, dict):
                        continue
                    inner_cd = od.get("class_derivations")
                    if not inner_cd or not isinstance(inner_cd, dict):
                        continue
                    for inner_class, inner_body in inner_cd.items():
                        if not isinstance(inner_body, dict):
                            continue
                        for inner_slot, inner_slot_body in (
                            inner_body.get("slot_derivations", {}).items()
                        ):
                            if not isinstance(inner_slot_body, dict):
                                continue
                            inner_pf = str(inner_slot_body.get("populated_from", ""))
                            if inner_pf.startswith("phv"):
                                inner_cf_from_block = _unit_conversion_factor(
                                    inner_slot_body.get("unit_conversion")
                                )
                                primary_phvs.append(
                                    {
                                        "phv": inner_pf,
                                        "slot": f"{slot_name}.{inner_slot}",
                                        "is_value_slot": inner_slot in (
                                            "value_decimal", "value_integer",
                                            "value_coded", "value_concept",
                                        ),
                                        "value_map": _extract_value_mappings(inner_slot_body),
                                        "conversion_factor": inner_cf_from_block,
                                    }
                                )
                            inner_expr = inner_slot_body.get("expr", "")
                            if isinstance(inner_expr, str):
                                is_inner_value_expr = inner_slot in (
                                    "value_decimal", "value_integer", "value_coded", "value_concept"
                                )
                                if is_inner_value_expr:
                                    value_exprs.append(inner_expr)
                                inner_cf = (
                                    _extract_conversion_factor(inner_expr)
                                    if inner_slot in ("value_decimal", "value_integer")
                                    else None
                                )
                                for phv in re.findall(r"(phv\d+)", inner_expr):
                                    primary_phvs.append(
                                        {
                                            "phv": phv,
                                            "slot": f"{slot_name}.{inner_slot}",
                                            "is_value_slot": is_inner_value_expr,
                                            "value_map": None,
                                            "conversion_factor": inner_cf,
                                            "expr": inner_expr,
                                        }
                                    )

        if not primary_phvs or not concept_codes:
            continue

        # method_type creates a compound harmonized key only for MO blocks
        # nested inside a MeasurementObservationSet — the MOS path in the
        # harmonized extractor groups by (observation_type, method_type) and
        # emits keys like ``measurement_OMOP:XXX|<method_type>``.  Standalone
        # MeasurementObservation files (bdy_hgt, bmi, hrt_rt, ...) are grouped
        # by observation_type alone and keep bare keys.
        method_type_val: str | None = None
        if entity_class == "MeasurementObservation" and "method_type" in slots:
            mt = slots["method_type"]
            if isinstance(mt, dict):
                method_type_val = (
                    mt.get("value")
                    or (mt.get("expr", "").strip("'\" ") or None)
                )

        prefix = ENTITY_PREFIX.get(entity_class, f"{entity_class.lower()}_")

        value_phvs = [p for p in primary_phvs if p["is_value_slot"]]
        primary = value_phvs[0] if value_phvs else primary_phvs[0]

        src_name = phv_names.get(primary["phv"], "")
        if not src_name:
            continue

        # Emit one crosswalk entry per unique concept code.  Case() exprs and
        # value_mappings-driven concept slots may produce multiple codes (e.g.
        # hdl.yaml: OMOP:4041720 & OBA:VT0000184, stroke.yaml: HP:0002140 &
        # MONDO:0013792, diabetes.yaml pht001490: MONDO:0005015 & MONDO:0006920).
        for concept_code in concept_codes:
            if inside_mos and method_type_val:
                harmonized_key = f"{prefix}{concept_code}|{method_type_val}"
            else:
                harmonized_key = f"{prefix}{concept_code}"

            crosswalk.append(
                {
                    "source_key": src_name,
                    "harmonized_key": harmonized_key,
                    "match_method": "yaml",
                    "yaml_file": yaml_filename,
                    "phv_id": primary["phv"],
                    "concept_code": concept_code,
                    "concept_phv": concept_phv,
                    "entity_class": entity_class,
                    "value_map": primary["value_map"],
                    "concept_value_map": concept_value_map,
                    "method_type": method_type_val,
                    "conversion_factor": primary.get("conversion_factor"),
                    "source_phvs": sorted(
                        {
                            _canonical_phv_id(p["phv"])
                            for p in primary_phvs
                            if p.get("phv")
                        }
                    ),
                    "value_exprs": value_exprs,
                }
            )


def build_yaml_crosswalk(
    yaml_dir: Path,
    phv_names: dict[str, str],
) -> list[dict]:
    """Parse all YAML transform files in *yaml_dir* and return crosswalk entries.

    Each entry maps a source variable name (resolved via *phv_names*) to an
    harmonized entity key (``measurement_<code>``, ``condition_<code>``, etc.).
    """
    crosswalk: list[dict] = []

    for yaml_file in sorted(yaml_dir.glob("*.yaml")):
        if yaml_file.name.startswith("."):
            continue
        try:
            with yaml_file.open("r", encoding="utf-8") as fh:
                docs = list(yaml.safe_load_all(fh))
        except yaml.YAMLError as exc:
            print(f"  WARNING: Could not parse YAML {yaml_file.name}: {exc}")
            continue

        for doc in docs:
            if not isinstance(doc, list):
                continue
            for block in doc:
                if not isinstance(block, dict):
                    continue
                cd = block.get("class_derivations")
                if cd and isinstance(cd, dict):
                    _extract_crosswalk_from_class_derivations(
                        cd, yaml_file.name, phv_names, crosswalk
                    )

    return crosswalk


# ---------------------------------------------------------------------------
# Harmonized variable key normalization
# ---------------------------------------------------------------------------

_TUPLE_OBS_RE = re.compile(r"^\(\s*['\"]?([^'\"()]+?)['\"]?\s*,?\s*\)$")
# Matches full harmonized keys whose observation_type was serialized as a Python
# singleton tuple: e.g.  measurement_('OMOP:4152194',)
_TUPLE_KEY_RE = re.compile(r"^([a-z_]+)\('([^']+)',?\)$")


def _norm_obs_type(s: str) -> str:
    """Strip Python singleton-tuple notation from an observation_type string.

    dm-bip occasionally serializes observation_type as a Python tuple repr
    (e.g. ``('OMOP:4152194',)``) rather than a plain string.  This returns
    the inner value, leaving already-clean strings unchanged.
    """
    try:
        parsed = ast.literal_eval(s.strip())
        if isinstance(parsed, (list, tuple)) and len(parsed) == 1:
            return str(parsed[0])
    except (ValueError, SyntaxError):
        pass
    m = _TUPLE_OBS_RE.match(s.strip())
    return m.group(1) if m else s


def _normalize_harmonized_vars(raw: dict) -> dict:
    """Normalize harmonized variable keys and metadata produced by dm-bip.

    Fixes two serialization quirks:
    - Dict key contains prefixed tuple notation:
      ``measurement_('OMOP:4152194',)``  ->  ``measurement_OMOP:4152194``
    - The ``observation_type`` metadata field inside the variable dict
      also carries the tuple string and must be cleaned so that C10
      cross-variable lookups (which match on observation_type) work.
    """
    result: dict = {}
    for key, val in raw.items():
        if "(" in key:
            m = _TUPLE_KEY_RE.match(key)
            new_key = (m.group(1) + m.group(2)) if m else key
        elif key.endswith("]") and "_[" in key:
            prefix, raw_obs = key.split("_", 1)
            new_key = f"{prefix}_{_norm_obs_type(raw_obs)}"
        else:
            new_key = key
        if isinstance(val, dict):
            obs = val.get("observation_type", "")
            if isinstance(obs, str) and "(" in obs:
                val = dict(val)
                val["observation_type"] = _norm_obs_type(obs)
        result[new_key] = val
    return result


# ---------------------------------------------------------------------------
# Multi-PHT source aggregation
# ---------------------------------------------------------------------------

def _normalize_code(c) -> str:
    """Normalise a coded value for cross-source matching.

    Distribution keys from the source extractor often arrive as float-typed
    strings (e.g. ``'1.0'``) because pandas read the column as numeric, while
    YAML value_mappings keys are typically integer strings (``'1'``).  This
    function trims trailing ``.0`` from integer-valued floats and strips
    surrounding whitespace so the two representations compare equal.
    """
    s = str(c).strip()
    # Drop trailing .0 for integer-valued floats: '1.0' -> '1', '12.0' -> '12'
    if s.endswith(".0") and s[:-2].lstrip("-").isdigit():
        return s[:-2]
    return s


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


def build_variable_crosswalk(
    variables_by_name: dict[str, dict[str, dict]],
    harmonized_vars: dict,
    yaml_dir: Path,
    cache_dir: Path,
    source_doc: dict | None = None,
    diagnostics_out: dict | None = None,
) -> list[dict]:
    """Build source <-> harmonized variable crosswalk via YAML transforms.

    PHV -> concept code -> entity key.  When multiple YAML blocks (typically
    one per visit / source PHT) emit the SAME harmonized key, all per-PHT
    source summaries are pooled into one combined summary so the
    C2/C3/C4/C6/C7 comparisons see the same longitudinal pool the harmonized
    extractor produces.

    When *source_doc* contains ``variables_by_pht``, each YAML-matched entry
    gains a ``_resolved_src`` field with pooled stats drawn from every
    contributing PHT.  ``_source_phts`` lists the PHTs that contributed and
    ``_per_pht_src`` retains the individual per-PHT summaries for audit /
    diagnostic reporting.

    If *diagnostics_out* is supplied, it is populated with details of YAML
    entries the parser produced that could not be matched (missing source
    column or missing harmonized key) — keyed by harmonized_key for use by
    the unmatched-harmonized FAIL reporter.
    """
    matches: list[dict] = []
    matched_src: set[str] = set()
    matched_harmonized: set[str] = set()

    phv_names = load_phv_name_map(cache_dir)
    phv_to_pht = load_phv_to_pht_map(cache_dir)

    # Hard-fail when the cache directory produced no PHV->name mappings.
    # This catches typo'd paths, wrong-cohort caches, and caches that exist
    # but lack pheno_variable_summaries/*.data_dict.xml.
    if not phv_names:
        raise CrosswalkBuildError(
            f"ERROR: --cache-dir produced 0 PHV-to-name mappings: {cache_dir}. "
            f"Expected layout: {cache_dir}/pheno_variable_summaries/*.data_dict.xml. "
            "Aborting because the YAML crosswalk would be empty."
        )

    variables_by_pht: dict[str, dict] = (
        source_doc.get("variables_by_pht", {}) if source_doc else {}
    )

    yaml_cw = build_yaml_crosswalk(yaml_dir, phv_names)
    if not yaml_cw:
        raise CrosswalkBuildError(
            f"ERROR: YAML crosswalk produced 0 entries from {yaml_dir.name}. "
            "This usually means the PHV->name map is empty or every YAML "
            "block references PHVs absent from the cache. Check --cache-dir "
            "matches the cohort and contains pheno_variable_summaries/*.data_dict.xml."
        )
    print(f"  YAML crosswalk: {len(yaml_cw)} entries from {yaml_dir.name}")

    # Group YAML entries by harmonized_key, normalising source/harmonized
    # keys against the actual extract dicts.  Track which entries failed to
    # resolve so we can surface diagnostics for the matching FAIL.
    grouped: dict[str, list[dict]] = {}
    unresolved: dict[str, list[dict]] = {}

    for entry in yaml_cw:
        src_key = entry["source_key"]
        harmonized_key = entry["harmonized_key"]

        # Case-insensitive fallback for source key
        resolved_src_key: str | None = None
        if entry.get("is_static"):
            resolved_src_key = "__static__"
        elif src_key in variables_by_name:
            resolved_src_key = src_key
        else:
            for sk in variables_by_name:
                if sk.upper() == src_key.upper():
                    resolved_src_key = sk
                    break

        # Case-insensitive fallback for harmonized key
        resolved_harmonized_key: str | None = None
        if harmonized_key in harmonized_vars:
            resolved_harmonized_key = harmonized_key
        else:
            for ok in harmonized_vars:
                if ok.upper() == harmonized_key.upper():
                    resolved_harmonized_key = ok
                    break

        # Fallback 1: newer BDC extractors prefix YAML-mapped concept keys
        # with "discovered:" (e.g. "discovered:condition:MONDO:0004981")
        # while the crosswalk generates bare keys ("condition_MONDO:...").
        # Try the discovered: form when the bare form wasn't found.
        if resolved_harmonized_key is None:
            disc_key = _to_discovered_key(harmonized_key)
            if disc_key is not None:
                if disc_key in harmonized_vars:
                    resolved_harmonized_key = disc_key
                else:
                    for ok in harmonized_vars:
                        if ok.upper() == disc_key.upper():
                            resolved_harmonized_key = ok
                            break

        # Fallback 2: Demography slots are emitted by the BDC extractor as
        # "<slot_name>_<visit_N>" (e.g. "annotated_sex_1").  Try stripping
        # the "demog_" prefix and matching against "<slot>_1" then bare
        # "<slot>".
        if resolved_harmonized_key is None and harmonized_key.startswith("demog_"):
            slot_bare = harmonized_key[len("demog_"):]
            for candidate in (f"{slot_bare}_1", slot_bare):
                if candidate in harmonized_vars:
                    resolved_harmonized_key = candidate
                    break
                for ok in harmonized_vars:
                    if ok.upper() == candidate.upper():
                        resolved_harmonized_key = ok
                        break
                if resolved_harmonized_key is not None:
                    break

        # Fallback 3: MeasurementObservation blocks nested inside a
        # MeasurementObservationSet generate a crosswalk key with a
        # ``|<method_type>`` suffix (e.g.
        # ``measurement_OMOP:4241837|Pre-bronchodilator, spirometry``).
        # Some cohort harmonized extractors group by observation_type alone
        # and emit bare keys without the method_type component (e.g.
        # COPDGene spirometry.yaml and blood_pressure.yaml).  Fall back to
        # the bare key when the suffixed form is absent from harmonized_vars.
        if (
            resolved_harmonized_key is None
            and entry.get("entity_class") == "MeasurementObservation"
            and entry.get("method_type")
            and "|" in harmonized_key
        ):
            bare_key = harmonized_key.split("|", 1)[0]
            if bare_key in harmonized_vars:
                resolved_harmonized_key = bare_key
            else:
                for ok in harmonized_vars:
                    if ok.upper() == bare_key.upper():
                        resolved_harmonized_key = ok
                        break

        if resolved_harmonized_key is None or resolved_src_key is None:
            # Stash diagnostic — at minimum we still know the YAML claims
            # there is a harmonized key here, even if resolution failed.
            stash_key = resolved_harmonized_key or harmonized_key
            unresolved.setdefault(stash_key, []).append(
                {
                    "yaml_file": entry.get("yaml_file"),
                    "phv_id": entry.get("phv_id"),
                    "concept_code": entry.get("concept_code"),
                    "entity_class": entry.get("entity_class"),
                    "source_key_in_yaml": entry.get("source_key"),
                    "missing_source_column": resolved_src_key is None,
                    "missing_harmonized_key": resolved_harmonized_key is None,
                }
            )
            continue

        # Use a shallow copy so the original yaml_cw entries are not mutated;
        # callers that reuse yaml_cw (e.g. tests) see the original PHV/source keys.
        grouped.setdefault(resolved_harmonized_key, []).append(
            {**entry, "source_key": resolved_src_key, "harmonized_key": resolved_harmonized_key}
        )

    for harmonized_key, entries in grouped.items():
        if harmonized_key in matched_harmonized:
            continue

        # Resolve per-PHT source stats for every contributing entry.
        per_pht_summaries: list[dict] = []
        source_phts: list[str] = []
        source_keys_used: list[str] = []
        phv_ids: list[str] = []
        summaries_by_phv: dict[str, dict] = {}

        for entry in entries:
            src_key = entry["source_key"]
            phv_id = entry.get("phv_id", "")
            if phv_id:
                phv_ids.append(phv_id)

            if entry.get("is_static"):
                static_pht = entry.get("static_pht")
                rows_by_pht = (source_doc or {}).get("total_rows_by_pht", {})
                total = int(rows_by_pht.get(static_pht, 0) or 0)
                if not total:
                    total = int((source_doc or {}).get("total_participants", 0) or 0)
                static_value = normalize_category_key(entry.get("static_value"))
                static_summary = _categorical_summary_from_counts(
                    {static_value: total},
                    basis="static_yaml_value",
                    confidence="exact",
                    raw={"n_total": total},
                ) or {}
                entry["_source_summary"] = static_summary
                per_pht_summaries.append(static_summary)
                if static_pht and static_pht not in source_phts:
                    source_phts.append(static_pht)
                continue

            resolved_summary: dict | None = None
            resolved_pht: str | None = None
            if phv_id and variables_by_pht:
                pht_id = phv_to_pht.get(phv_id)
                if pht_id and pht_id in variables_by_pht:
                    pht_vars = variables_by_pht[pht_id]
                    resolved_summary = pht_vars.get(src_key)
                    if resolved_summary is None:
                        for k, v in pht_vars.items():
                            if k.upper() == src_key.upper():
                                resolved_summary = v
                                break
                    if resolved_summary is not None:
                        resolved_pht = pht_id

            if resolved_summary is None:
                # No PHV→PHT route worked. Fall back to "first PHT wins"
                # by column name. Step 5 will replace this with a per-variable
                # FAIL when the column appears in multiple PHTs.
                resolved_summary = _pick_single_pht_summary(
                    variables_by_name, src_key
                )

            if resolved_summary is not None:
                entry["_source_summary"] = dict(resolved_summary)
                if phv_id:
                    summaries_by_phv[_canonical_phv_id(phv_id)] = dict(resolved_summary)
                per_pht_summaries.append(dict(resolved_summary))
                if resolved_pht and resolved_pht not in source_phts:
                    source_phts.append(resolved_pht)
                if src_key not in source_keys_used:
                    source_keys_used.append(src_key)

            # Also resolve every PHV referenced in value expressions.  This
            # lets the compare derive an expected categorical distribution
            # for split case() blocks without changing the transform YAML.
            for expr_phv in entry.get("source_phvs") or []:
                expr_phv = _canonical_phv_id(expr_phv)
                if not expr_phv or expr_phv in summaries_by_phv:
                    continue
                expr_src_key = phv_names.get(expr_phv, "")
                if not expr_src_key:
                    continue
                expr_summary: dict | None = None
                expr_pht = phv_to_pht.get(expr_phv)
                if expr_pht and expr_pht in variables_by_pht:
                    pht_vars = variables_by_pht[expr_pht]
                    expr_summary = pht_vars.get(expr_src_key)
                    if expr_summary is None:
                        for k, v in pht_vars.items():
                            if k.upper() == expr_src_key.upper():
                                expr_summary = v
                                break
                if expr_summary is None:
                    expr_summary = _pick_single_pht_summary(
                        variables_by_name, expr_src_key
                    )
                if expr_summary is not None:
                    summaries_by_phv[expr_phv] = dict(expr_summary)

        if not per_pht_summaries:
            # Couldn't resolve a single contributing summary.
            unresolved.setdefault(harmonized_key, []).extend(
                [
                    {
                        "yaml_file": e.get("yaml_file"),
                        "phv_id": e.get("phv_id"),
                        "concept_code": e.get("concept_code"),
                        "entity_class": e.get("entity_class"),
                        "source_key_in_yaml": e.get("source_key"),
                        "missing_source_column": True,
                        "missing_harmonized_key": False,
                    }
                    for e in entries
                ]
            )
            continue

        # Build the merged crosswalk match using the first entry as a
        # template (preserves yaml_file, phv_id of the first contributor,
        # concept_code, entity_class, value_map, method_type) and overlay
        # the pooled fields.
        merged = dict(entries[0])
        expected_src = build_expected_summary(entries, summaries_by_phv)
        merged["_resolved_src"] = expected_src or _aggregate_source_summaries(per_pht_summaries)
        unsupported_joint = any(
            e.get("concept_value_map")
            and _canonical_phv_id(e.get("concept_phv", ""))
            and _canonical_phv_id(e.get("phv_id", ""))
            and _canonical_phv_id(e.get("concept_phv", "")) != _canonical_phv_id(e.get("phv_id", ""))
            for e in entries
        )
        if unsupported_joint and not expected_src:
            merged["_resolved_src"]["_comparison_basis"] = "source_pooled_raw"
            merged["_resolved_src"]["_comparison_confidence"] = "unsupported"
            merged["_resolved_src"]["_comparison_limitations"] = [
                "Concept routing and value mapping use different PHVs; aggregate summaries cannot compute joint counts"
            ]
        merged["_per_pht_src"] = per_pht_summaries
        merged["_source_phts"] = source_phts
        merged["_source_keys"] = source_keys_used
        merged["_phv_ids"] = list(dict.fromkeys(phv_ids))
        merged["_yaml_entries"] = [
            {
                "yaml_file": e.get("yaml_file"),
                "phv_id": e.get("phv_id"),
                "concept_phv": e.get("concept_phv"),
                "concept_code": e.get("concept_code"),
                "entity_class": e.get("entity_class"),
                "harmonized_key": e.get("harmonized_key"),
                "value_map": e.get("value_map"),
                "concept_value_map": e.get("concept_value_map"),
                "value_exprs": e.get("value_exprs"),
                "source_summary": e.get("_source_summary"),
            }
            for e in entries
        ]
        if summaries_by_phv:
            merged["_source_phvs"] = sorted(summaries_by_phv)
        if expected_src:
            merged["_comparison_basis"] = expected_src.get("_comparison_basis")
            merged["_comparison_confidence"] = expected_src.get("_comparison_confidence")
            merged["_comparison_limitations"] = expected_src.get("_comparison_limitations")
        # Preserve concept_value_map from ANY contributing entry that
        # has one.  Different visit blocks for the same harmonized_key
        # may use a static ``value:`` (no cvm) while one block uses
        # ``value_mappings`` (cvm present); we must not lose the cvm
        # by defaulting to entries[0].
        if not merged.get("concept_value_map"):
            for e in entries:
                cvm = e.get("concept_value_map")
                if cvm:
                    merged["concept_value_map"] = cvm
                    break
        if source_phts:
            # Keep _resolved_pht populated for backward-compat in the
            # console crosswalk listing; show comma-joined list when many.
            merged["_resolved_pht"] = ",".join(source_phts)
        merged["match_method"] = (
            "yaml+pooled" if len(per_pht_summaries) > 1 else "yaml"
        )

        matches.append(merged)
        matched_harmonized.add(harmonized_key)
        for sk in source_keys_used:
            matched_src.add(sk)

    if diagnostics_out is not None:
        diagnostics_out["unresolved_yaml_entries"] = unresolved
        # Record every harmonized key the YAML parser proposed (resolved or
        # not).  The unmatched-FAIL reporter can use this to distinguish
        # "YAML claims this exists but couldn't link source" from "YAML
        # never proposed this key at all".
        diagnostics_out["yaml_proposed_harmonized_keys"] = sorted(
            set(grouped.keys()) | set(unresolved.keys())
        )

    return matches
