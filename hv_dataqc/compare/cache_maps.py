"""dbGaP cache-loading helpers: PHV name, PHV→PHT, PHV type, and coded-value maps.

All functions here read locally cached ``*.data_dict.xml`` files under
``<cache_dir>/pheno_variable_summaries/`` and return plain dicts.  Nothing
here has side-effects beyond ``print()`` progress messages.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from hv_dataqc.compare.helpers import _canonical_phv_id, _normalize_code
from hv_dataqc.hv_dataqc_common import (
    load_phv_name_map as _shared_load_phv_name_map,
    normalize_category_key,
)


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
