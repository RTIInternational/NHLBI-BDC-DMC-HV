"""
compare_source_harmonized.py — HV-DataQC Component 3

Compare aggregate summaries from extract_source_summaries.py (raw dbGaP source)
and extract_harmonized_summaries.py (dm-bip harmonized output). Runs checks C1–C11
and produces a Markdown + JSON report.

No hardcoded paths. All paths are explicit CLI arguments.

CHECKS:
  C1  N Preservation        — total participant / row counts
  C2  N Loss Detection       — per-variable valid-N comparison
  C3  Missing Value Accounting — missing-rate source vs. harmonized
  C4  Mean Preservation      — continuous mean within tolerance
  C5  Mean After Conversion  — mean with unit-conversion factor
  C6  SD Preservation        — standard deviation within tolerance
  C7  Categorical Distribution — distribution match (with value_mappings)
  C8  Visit N Distribution   — per-visit row counts; for table-based cohorts synthesizes
                               source counts from total_rows_by_pht + visit.yaml
  C9  Clinical Range         — harmonized values within clinical_ranges.yaml bounds
  C10 Cross-Variable Consistency — SBP > DBP, FEV1 < FVC, etc.
  C11 Variable Type Consistency  — source/harmonized agree on continuous vs. categorical

USAGE:
  python compare_source_harmonized.py \\
      --source  spiromics_source_20250101T120000.json \\
      --harmonized  spiromics_harmonized_20250101T120000.json \\
      --cohort  SPIROMICS \\
      --yaml-dir /path/to/HV-repo/priority_variables_transform/SPIROMICS-ingest/ \\
      --cache-dir /path/to/data/dbgap-cache/spiromics/

  # --yaml-dir and --cache-dir are optional; without them the variable crosswalk
  # cannot be built and only C1 / C8 / C10 run.
  # --clinical-ranges defaults to compare/config/clinical_ranges.yaml.
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import yaml

_HV_DATAQC_ROOT = Path(__file__).resolve().parents[1]
if str(_HV_DATAQC_ROOT) not in sys.path:
    sys.path.insert(0, str(_HV_DATAQC_ROOT))

from hv_dataqc_common import (  # noqa: E402
    canonical_phv_id,
    json_safe,
    load_phv_name_map as _shared_load_phv_name_map,
    normalize_category_key,
    write_json_atomic,
)

# Default clinical ranges config (relative to this script)
_CONFIG_DIR = Path(__file__).resolve().parent / "config"
_THRESHOLDS_PATH = _CONFIG_DIR / "thresholds.yaml"

_canonical_phv_id = canonical_phv_id
_json_safe = json_safe


def _write_json_atomic(path: Path, data: Any) -> None:
    """Write strict JSON via temp file then atomic replace."""
    write_json_atomic(path, data, ensure_ascii=False, default=str)


def _write_text_atomic(path: Path, text: str) -> None:
    """Write text via temp file then atomic replace.

    Creates parent directories as needed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as fh:
            fh.write(text)
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _md_escape(value: Any) -> str:
    """Escape values embedded in Markdown prose/tables."""
    text = str(value).replace("\r", " ").replace("\n", " ")
    return (
        text.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("`", "\\`")
        .replace("*", "\\*")
        .replace("_", "\\_")
    )


def validate_clinical_ranges_config(clinical_ranges: dict) -> list[str]:
    """Return non-fatal validation warnings for clinical_ranges.yaml."""
    warnings: list[str] = []
    required_bounds = ("plausible_lo", "plausible_hi", "red_flag_lo", "red_flag_hi")
    range_names = {k for k in clinical_ranges if not str(k).startswith("_")}

    for name in sorted(range_names):
        rng = clinical_ranges.get(name)
        if not isinstance(rng, dict):
            warnings.append(f"{name}: range definition is not a mapping")
            continue
        missing = [k for k in required_bounds if k not in rng]
        if missing:
            warnings.append(f"{name}: missing bound(s): {', '.join(missing)}")
            continue
        try:
            plaus_lo = float(rng["plausible_lo"])
            plaus_hi = float(rng["plausible_hi"])
            red_lo = float(rng["red_flag_lo"])
            red_hi = float(rng["red_flag_hi"])
        except (TypeError, ValueError):
            warnings.append(f"{name}: one or more bounds are not numeric")
            continue
        if plaus_lo > plaus_hi:
            warnings.append(f"{name}: plausible_lo > plausible_hi")
        if red_lo > plaus_lo:
            warnings.append(f"{name}: red_flag_lo > plausible_lo")
        if red_hi < plaus_hi:
            warnings.append(f"{name}: red_flag_hi < plausible_hi")

    rules = clinical_ranges.get("_cross_variable_rules", {})
    if rules and not isinstance(rules, dict):
        warnings.append("_cross_variable_rules: expected a mapping")
    elif isinstance(rules, dict):
        for rule_name, rule in sorted(rules.items()):
            if not isinstance(rule, dict):
                warnings.append(f"_cross_variable_rules.{rule_name}: expected a mapping")
                continue
            for var_name in rule.get("variables", []) or []:
                if var_name not in range_names:
                    warnings.append(
                        f"_cross_variable_rules.{rule_name}: unknown variable reference {var_name!r}"
                    )

    return warnings


def load_thresholds(path: Path | None = None) -> dict:
    """Load statistical comparison thresholds from YAML, falling back to built-in defaults.

    Built-in defaults match COPDGene-calibrated values.  Any subset of keys
    can be overridden by supplying a custom YAML path via ``--thresholds``.
    """
    effective_path = path or _THRESHOLDS_PATH
    if effective_path.exists():
        try:
            with effective_path.open("r", encoding="utf-8") as fh:
                cfg = yaml.safe_load(fh) or {}
            print(f"Loaded thresholds from {effective_path.name}")
            return cfg
        except yaml.YAMLError as exc:
            print(f"WARNING: Malformed thresholds YAML {effective_path.name}: {exc} -- using built-in defaults",
                  file=sys.stderr)
            return {}
    if path is not None:
        print(f"WARNING: Thresholds file not found: {effective_path} -- using built-in defaults")
    return {}


# ---------------------------------------------------------------------------
# Check result
# ---------------------------------------------------------------------------

class CheckResult:
    """One check result for one variable."""

    def __init__(
        self,
        check_id: str,
        variable: str,
        status: str,          # PASS | WARN | FAIL | SKIP | INFO
        message: str,
        detail: dict | None = None,
    ) -> None:
        self.check_id = check_id
        self.variable = variable
        self.status = status
        self.message = message
        self.detail = detail or {}

    def to_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "variable": self.variable,
            "status": self.status,
            "message": self.message,
            "detail": self.detail,
        }


class CrosswalkBuildError(RuntimeError):
    """Raised when a YAML-driven variable crosswalk cannot be built safely."""


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
    source_vars: dict,
    harmonized_vars: dict,
    yaml_dir: Path | None = None,
    cache_dir: Path | None = None,
    source_doc: dict | None = None,
    diagnostics_out: dict | None = None,
) -> list[dict]:
    """Build source <-> harmonized variable crosswalk.

    Strategy (in priority order):
    1. YAML-driven: PHV -> concept code -> entity key.  When multiple YAML
       blocks (typically one per visit / source PHT) emit the SAME
       harmonized key, all per-PHT source summaries are pooled into one
       combined summary so the C2/C3/C4/C6/C7 comparisons see the same
       longitudinal pool the harmonized extractor produces.
    2. PHV ID match: source key starts with "phv", check harmonized metadata.
    3. Name match: source ``name`` == harmonized ``bdc_label``.

    When *source_doc* contains ``variables_by_pht`` and *cache_dir* provides a
    PHV->PHT map, each YAML-matched entry gains a ``_resolved_src`` field with
    pooled stats drawn from every contributing PHT.  ``_source_phts`` lists
    the PHTs that contributed and ``_per_pht_src`` retains the individual
    per-PHT summaries for audit / diagnostic reporting.

    If *diagnostics_out* is supplied, it is populated with details of YAML
    entries the parser produced that could not be matched (missing source
    column or missing harmonized key) — keyed by harmonized_key for use by
    the unmatched-harmonized FAIL reporter.
    """
    matches: list[dict] = []
    matched_src: set[str] = set()
    matched_harmonized: set[str] = set()

    # --- Strategy 1: YAML-driven (with multi-PHT aggregation) ---
    if yaml_dir and yaml_dir.exists():
        phv_names: dict[str, str] = {}
        phv_to_pht: dict[str, str] = {}
        if cache_dir and cache_dir.exists():
            phv_names = load_phv_name_map(cache_dir)
            phv_to_pht = load_phv_to_pht_map(cache_dir)

        # Hard-fail when the cache directory was supplied but produced no
        # PHV->name mappings.  This catches typo'd paths, wrong-cohort caches,
        # and caches that exist but lack pheno_variable_summaries/*.data_dict.xml.
        if cache_dir and cache_dir.exists() and not phv_names:
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
            elif src_key in source_vars:
                resolved_src_key = src_key
            else:
                for sk in source_vars:
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
            source_flat_keys_used: list[str] = []
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
                    # Fall back to the flat source_vars dict (first-PHT-wins).
                    resolved_summary = source_vars.get(src_key)

                if resolved_summary is not None:
                    entry["_source_summary"] = dict(resolved_summary)
                    if phv_id:
                        summaries_by_phv[_canonical_phv_id(phv_id)] = dict(resolved_summary)
                    per_pht_summaries.append(dict(resolved_summary))
                    if resolved_pht and resolved_pht not in source_phts:
                        source_phts.append(resolved_pht)
                    if src_key not in source_keys_used:
                        source_keys_used.append(src_key)
                    if src_key in source_vars and src_key not in source_flat_keys_used:
                        source_flat_keys_used.append(src_key)
                    if resolved_pht:
                        namespaced_key = f"{resolved_pht}.{src_key.lower()}"
                        if (
                            namespaced_key in source_vars
                            and namespaced_key not in source_flat_keys_used
                        ):
                            source_flat_keys_used.append(namespaced_key)

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
                        expr_summary = source_vars.get(expr_src_key)
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
            merged["_source_flat_keys"] = source_flat_keys_used
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

    # --- Strategy 2: PHV ID match ---
    # Build a PHV -> harmonized-key index once, instead of scanning every
    # harmonized key for every source PHV.  This preserves the old substring
    # behavior but makes the fallback O(n + m) rather than O(n*m).
    phv_harmonized_index: dict[str, list[str]] = {}
    for harmonized_key, out_info in harmonized_vars.items():
        haystacks = [harmonized_key]
        if isinstance(out_info, dict):
            for value in out_info.values():
                if isinstance(value, str):
                    haystacks.append(value)
        for haystack in haystacks:
            for phv_id in re.findall(r"phv\d+", haystack, flags=re.IGNORECASE):
                phv_harmonized_index.setdefault(_canonical_phv_id(phv_id), []).append(harmonized_key)

    for src_key, src_info in source_vars.items():
        if "error" in src_info or src_key in matched_src:
            continue
        if not src_key.startswith("phv"):
            continue
        for harmonized_key in phv_harmonized_index.get(_canonical_phv_id(src_key), []):
            if harmonized_key in matched_harmonized:
                continue
            matches.append(
                {"source_key": src_key, "harmonized_key": harmonized_key, "match_method": "phv_id"}
            )
            matched_src.add(src_key)
            matched_harmonized.add(harmonized_key)
            break

    # --- Strategy 3: Name match ---
    for src_key, src_info in source_vars.items():
        if "error" in src_info or src_key in matched_src:
            continue
        src_name = src_info.get("name", "").upper()
        if not src_name:
            continue
        for harmonized_key, out_info in harmonized_vars.items():
            if harmonized_key in matched_harmonized:
                continue
            out_label = out_info.get("bdc_label", "").upper()
            if out_label and src_name == out_label:
                matches.append(
                    {"source_key": src_key, "harmonized_key": harmonized_key, "match_method": "name"}
                )
                matched_src.add(src_key)
                matched_harmonized.add(harmonized_key)
                break

    return matches


# ---------------------------------------------------------------------------
# Report formatting helpers — used by check functions
# ---------------------------------------------------------------------------

def _n(val: int | float) -> str:
    """Format a number with commas for integers, leave floats as-is."""
    if isinstance(val, int):
        return f"{val:,}"
    if isinstance(val, float) and val == int(val) and abs(val) >= 1000:
        return f"{int(val):,}"
    return str(val)


def _cmp(src, dst, unit: str = "") -> str:
    """Format a comparison. If src == dst, show once; otherwise 'src -> dst'."""
    s, d = _n(src), _n(dst)
    u = unit
    if s == d:
        return f"{s}{u}"
    return f"{s}{u} -> {d}{u}"


def _cmp_stat(label: str, src, dst, rel_diff: float) -> str:
    """Format 'Label: value (d=X)' or 'Label: src -> dst (d=X)'.

    Omits the delta when values are identical.
    """
    s, d = _n(src), _n(dst)
    if s == d:
        return f"{label}: {s}"
    return f"{label}: {s} -> {d} (d={rel_diff:.4f})"


# ---------------------------------------------------------------------------
# Check implementations
# ---------------------------------------------------------------------------

def check_c1_n_preservation(
    source: dict, harmonized: dict, fail_pct: float = 1.0,
    mapped_phts: set | None = None,
) -> list[CheckResult]:
    """C1: Total participant count comparison.

    If the source summary includes ``participants_by_pht`` and ``mapped_phts``
    is provided (PHTs actually referenced by YAML), the message shows both:
      - max across mapped PHTs (the YAML-scoped universe ceiling)
      - all-PHT union (total_participants, the pass/fail denominator)

    If ``mapped_phts`` is not provided, falls back to showing the global max
    single PHT for diagnostics.  The pass/fail denominator always remains
    ``total_participants``.
    """
    src_n = source.get("total_participants", 0)
    harmonized_n = harmonized.get("total_participants", 0)

    if src_n == 0:
        return [CheckResult("C1", "_total", "SKIP", "No source participant count")]
    if harmonized_n == 0:
        return [CheckResult("C1", "_total", "FAIL", "No harmonized participants found")]

    detail_base: dict = {"source_n": src_n, "harmonized_n": harmonized_n}
    pht_note = ""
    participants_by_pht: dict[str, int] = source.get("participants_by_pht", {})
    if participants_by_pht:
        max_pht_n = max(participants_by_pht.values())
        max_pht_key = max(participants_by_pht, key=participants_by_pht.get)
        detail_base.update({
            "max_single_pht": max_pht_key,
            "max_single_pht_n": max_pht_n,
        })
        if mapped_phts:
            mapped_counts = {
                pht: n for pht, n in participants_by_pht.items()
                if pht in mapped_phts
            }
            if mapped_counts:
                mapped_max_n = max(mapped_counts.values())
                mapped_max_key = max(mapped_counts, key=mapped_counts.get)
                pht_note = (
                    f" [mapped-PHT max: {mapped_max_key}={mapped_max_n};"
                    f" all-PHT union={src_n}]"
                )
                detail_base.update({
                    "mapped_pht_max": mapped_max_key,
                    "mapped_pht_max_n": mapped_max_n,
                })
            else:
                pht_note = f" [cross-PHT union={src_n}]"
        else:
            pht_note = (
                f" [max single-PHT: {max_pht_key}={max_pht_n};"
                f" cross-PHT union={src_n}]"
            )

    if harmonized_n == src_n:
        return [CheckResult("C1", "_total", "PASS",
                             f"Participant count matches: {_n(src_n)}{pht_note}",
                             detail_base)]

    if harmonized_n < src_n:
        loss_pct = round((src_n - harmonized_n) / src_n * 100, 1)
        status = "FAIL" if loss_pct > fail_pct else "WARN"
        detail = {**detail_base, "loss_pct": loss_pct}
        return [CheckResult("C1", "_total", status,
                             f"Participant loss: {_n(src_n)} -> {_n(harmonized_n)}"
                             f" ({loss_pct}%){pht_note}",
                             detail)]

    return [CheckResult("C1", "_total", "WARN",
                         f"Harmonized has MORE participants than source:"
                         f" {_n(src_n)} -> {_n(harmonized_n)}{pht_note}",
                         detail_base)]


def check_c2_n_loss(
    src_var: dict, harmonized_var: dict, var_name: str,
    pass_pct: float = 0.5, warn_pct: float = 2.0,
    gain_warn_pct: float | None = None, gain_fail_pct: float | None = None,
    expected_n: int | None = None,
) -> CheckResult:
    """C2: Per-variable valid-N comparison.

    When *expected_n* is provided (typically by ``_expected_harmonized_n``
    for value_mappings-routed concept slots), it is used as the denominator
    in place of the raw source ``n_valid``.  This makes the check correctly
    handle one-source-to-many-concepts routing where the full source row
    count is not the right comparison target for a single harmonized concept.
    """
    src_n_raw = src_var.get("n_valid", 0)
    src_n = expected_n if expected_n is not None else src_n_raw
    harmonized_n = harmonized_var.get("n_valid", 0)
    confidence = src_var.get("_comparison_confidence")
    limitations = src_var.get("_comparison_limitations") or []

    detail_base = {
        "source_n": src_n,
        "harmonized_n": harmonized_n,
    }
    if confidence:
        detail_base["comparison_confidence"] = confidence
    if limitations:
        detail_base["comparison_limitations"] = limitations
    if expected_n is not None:
        detail_base["source_n_raw"] = src_n_raw
        detail_base["expected_n_for_concept"] = expected_n

    if src_n == 0:
        return CheckResult("C2", var_name, "SKIP", "No valid source values", detail_base)
    if confidence == "unsupported":
        return CheckResult(
            "C2", var_name, "SKIP",
            "Expected N requires row-level joint counts; aggregate comparison not attempted",
            detail_base,
        )
    if harmonized_n == src_n:
        return CheckResult("C2", var_name, "PASS", f"N preserved: {_n(src_n)}", detail_base)

    loss_pct = round((src_n - harmonized_n) / src_n * 100, 1) if src_n > 0 else 0
    detail_base["loss_pct"] = loss_pct
    if abs(loss_pct) <= pass_pct:
        return CheckResult("C2", var_name, "PASS",
                           f"N within {pass_pct}%: {_n(src_n)} -> {_n(harmonized_n)}",
                           detail_base)
    if confidence == "partial":
        return CheckResult(
            "C2", var_name, "WARN",
            f"Partial expected N differs from harmonized: {_n(src_n)} -> {_n(harmonized_n)} ({abs(loss_pct)}%); row-level data needed for exact verdict",
            detail_base,
        )
    if 0 < loss_pct <= warn_pct:
        return CheckResult("C2", var_name, "WARN",
                           f"Moderate N loss: {_n(src_n)} -> {_n(harmonized_n)} ({loss_pct}%)",
                           detail_base)
    if loss_pct > warn_pct:
        return CheckResult("C2", var_name, "FAIL",
                           f"Significant N loss: {_n(src_n)} -> {_n(harmonized_n)} ({loss_pct}%)",
                           detail_base)
    gain_pct = round(-loss_pct, 1)
    gain_warn = warn_pct if gain_warn_pct is None else gain_warn_pct
    gain_fail = gain_warn if gain_fail_pct is None else gain_fail_pct
    detail_base["gain_pct"] = gain_pct
    status = "FAIL" if gain_pct > gain_fail else "WARN"
    severity = "Large" if status == "FAIL" else "Moderate"
    return CheckResult("C2", var_name, status,
                       f"{severity} N gain: {_n(src_n)} -> {_n(harmonized_n)} ({gain_pct}%)",
                       detail_base)


def check_c3_missing_accounting(
    src_var: dict, harmonized_var: dict, var_name: str,
    pass_pp: float = 0.5, warn_pp: float = 3.0,
    n_valid_pass_pct: float = 0.5, n_valid_warn_pct: float = 3.0,
) -> CheckResult:
    """C3: Missing value rate comparison.

    When denominators differ by >20% (common when source is concatenated raw
    TSVs), falls back to n_valid comparison to avoid false positives.
    """
    src_total = src_var.get("n_total", 0)
    harmonized_total = harmonized_var.get("n_total", 0)
    src_valid = src_var.get("n_valid", 0)
    harmonized_valid = harmonized_var.get("n_valid", 0)
    confidence = src_var.get("_comparison_confidence")
    limitations = src_var.get("_comparison_limitations") or []

    if confidence == "unsupported":
        return CheckResult(
            "C3", var_name, "SKIP",
            "Expected missingness requires row-level joint counts; aggregate comparison not attempted",
            {"comparison_confidence": confidence, "comparison_limitations": limitations},
        )

    if src_total > 0 and harmonized_total > 0:
        denom_ratio = min(src_total, harmonized_total) / max(src_total, harmonized_total)
        if denom_ratio < 0.8:
            if src_valid == 0:
                return CheckResult("C3", var_name, "SKIP",
                                   "No valid source values (denominator mismatch)")
            if harmonized_valid == src_valid:
                return CheckResult("C3", var_name, "PASS",
                                   f"n_valid preserved: {_n(src_valid)}")
            diff_pct = abs(harmonized_valid - src_valid) / src_valid * 100
            if confidence == "partial":
                return CheckResult(
                    "C3", var_name, "WARN",
                    f"Partial expected n_valid differs from harmonized: {_n(src_valid)} -> {_n(harmonized_valid)} ({diff_pct:.1f}%); row-level data needed for exact verdict",
                    {"source_n_valid": src_valid, "harmonized_n_valid": harmonized_valid,
                     "comparison_confidence": confidence, "comparison_limitations": limitations},
                )
            if diff_pct <= n_valid_pass_pct:
                return CheckResult("C3", var_name, "PASS",
                                   f"n_valid within {n_valid_pass_pct}%: {_n(src_valid)} -> {_n(harmonized_valid)}")
            if diff_pct <= n_valid_warn_pct:
                return CheckResult("C3", var_name, "WARN",
                                   f"n_valid shifted: {_n(src_valid)} -> {_n(harmonized_valid)} ({diff_pct:.1f}%)")
            return CheckResult("C3", var_name, "FAIL",
                               f"n_valid mismatch: {_n(src_valid)} -> {_n(harmonized_valid)} ({diff_pct:.1f}%)",
                               {"source_n_valid": src_valid, "harmonized_n_valid": harmonized_valid})

    src_pct = src_var.get("pct_missing", 0)
    harmonized_pct = harmonized_var.get("pct_missing", 0)
    diff = abs(harmonized_pct - src_pct)

    if diff <= pass_pp:
        return CheckResult("C3", var_name, "PASS",
                           f"Missing rate: {_cmp(src_pct, harmonized_pct, '%')}")
    if diff <= warn_pp:
        return CheckResult("C3", var_name, "WARN",
                           f"Missing rate changed: {src_pct}% -> {harmonized_pct}% (d={diff:.1f}%)")
    return CheckResult("C3", var_name, "FAIL",
                       f"Large missing rate change: {src_pct}% -> {harmonized_pct}% (d={diff:.1f}%)",
                       {"source_pct": src_pct, "harmonized_pct": harmonized_pct})


def check_c4_mean_preservation(
    src_var: dict, harmonized_var: dict, var_name: str,
    pass_rel: float = 0.001, warn_rel: float = 0.01,
) -> CheckResult:
    """C4: Continuous mean comparison (no unit conversion)."""
    if src_var.get("type") != "continuous" or harmonized_var.get("type") != "continuous":
        return CheckResult("C4", var_name, "SKIP", "Not both continuous")

    src_mean = src_var.get("mean")
    harmonized_mean = harmonized_var.get("mean")
    if src_mean is None or harmonized_mean is None:
        return CheckResult("C4", var_name, "SKIP", "Missing mean value")

    if src_mean == 0:
        if harmonized_mean == 0:
            return CheckResult("C4", var_name, "PASS", "Both means are 0")
        return CheckResult("C4", var_name, "WARN", f"Source mean=0, harmonized mean={harmonized_mean}")

    rel_diff = abs(harmonized_mean - src_mean) / abs(src_mean)
    if rel_diff <= pass_rel:
        return CheckResult("C4", var_name, "PASS",
                           _cmp_stat("Mean preserved", src_mean, harmonized_mean, rel_diff))
    if rel_diff <= warn_rel:
        return CheckResult("C4", var_name, "WARN",
                           _cmp_stat("Mean shifted", src_mean, harmonized_mean, rel_diff),
                           {"source_mean": src_mean, "harmonized_mean": harmonized_mean})
    # --- Unit-conversion detection ---
    # If the observed ratio matches a well-known unit conversion factor (±2%),
    # demote to WARN and annotate rather than FAIL.  The comparison cannot be
    # done accurately without knowing the expected factor; a C5 entry with an
    # explicit conversion_factor will give a definitive verdict.
    _KNOWN_FACTORS = [
        (0.001, "×0.001"), (0.01, "×0.01"), (0.1, "×0.1"),
        (10.0, "×10"), (100.0, "×100"), (1000.0, "×1000"),
        (0.453592, "lbs→kg"), (2.20462, "kg→lbs"),
        (2.54, "in→cm"), (0.393701, "cm→in"),
        (0.02586, "mg/dL→mmol/L cholesterol"), (38.67, "mmol/L→mg/dL cholesterol"),
        (0.0555, "mg/dL→mmol/L glucose"), (18.018, "mmol/L→mg/dL glucose"),
        (0.01129, "mg/dL→mmol/L triglycerides"), (88.57, "mmol/L→mg/dL triglycerides"),
        (6.0, "μIU→pmol/L insulin (approx)"), (0.1667, "pmol/L→μIU insulin (approx)"),
    ]
    _FACTOR_TOL = 0.02  # ±2 % tolerance
    ratio = harmonized_mean / src_mean
    for factor, label in _KNOWN_FACTORS:
        if abs(ratio - factor) / factor <= _FACTOR_TOL:
            return CheckResult(
                "C4", var_name, "WARN",
                f"Mean mismatch likely due to unit conversion ({label}, ratio={ratio:.4f}): "
                f"{_n(src_mean)} -> {_n(harmonized_mean)} (d={rel_diff:.4f}) — add conversion_factor to C5 for precise check",
                {"source_mean": src_mean, "harmonized_mean": harmonized_mean,
                 "observed_ratio": ratio, "suspected_conversion": label},
            )
    return CheckResult("C4", var_name, "FAIL",
                       f"Mean mismatch: {_n(src_mean)} -> {_n(harmonized_mean)} (d={rel_diff:.4f}, ratio={ratio:.4f})",
                       {"source_mean": src_mean, "harmonized_mean": harmonized_mean,
                        "observed_ratio": ratio})


def check_c5_mean_after_conversion(
    src_var: dict, harmonized_var: dict, var_name: str,
    conversion_factor: float | None = None, pass_rel: float = 0.001,
) -> CheckResult:
    """C5: Mean comparison with a known unit conversion factor."""
    if conversion_factor is None:
        return CheckResult("C5", var_name, "SKIP", "No conversion factor specified")
    if src_var.get("type") != "continuous" or harmonized_var.get("type") != "continuous":
        return CheckResult("C5", var_name, "SKIP", "Not both continuous")

    src_mean = src_var.get("mean")
    harmonized_mean = harmonized_var.get("mean")
    if src_mean is None or harmonized_mean is None:
        return CheckResult("C5", var_name, "SKIP", "Missing mean value")

    expected = src_mean * conversion_factor
    if expected == 0:
        return CheckResult("C5", var_name, "SKIP", "Expected mean after conversion is 0")

    rel_diff = abs(harmonized_mean - expected) / abs(expected)
    if rel_diff <= pass_rel:
        return CheckResult("C5", var_name, "PASS",
                           f"Mean after x{conversion_factor}: "
                           f"{src_mean} -> {expected:.4f} (harmonized={harmonized_mean}, d={rel_diff:.4f})")
    return CheckResult("C5", var_name, "FAIL",
                       f"Mean mismatch after x{conversion_factor}: "
                       f"expected {expected:.4f}, got {harmonized_mean} (d={rel_diff:.4f})",
                       {"expected": expected, "actual": harmonized_mean, "factor": conversion_factor})


def should_run_c5_conversion_check(match: dict, c5_thresholds: dict) -> bool:
    """Return True only when C5 has an explicit conversion factor to validate.

    C5 is intentionally active-only: without a declared scalar conversion
    factor, emitting one SKIP per variable makes the report look like a real
    unit-conversion check ran when it did not.
    """
    return (match.get("conversion_factor") or c5_thresholds.get("conversion_factor")) is not None


def check_c11_type_consistency(src_var: dict, harmonized_var: dict, var_name: str) -> CheckResult:
    """C11: Variable type consistency between source and harmonized.

    Flags when source and harmonized disagree on whether a variable is continuous
    or categorical.  A mismatch usually means the pipeline recoded a continuous
    value into buckets (or treated categorical codes as numbers), which is a
    data-quality concern.
    """
    src_type = src_var.get("type")
    harmonized_type = harmonized_var.get("type")

    if not src_type or not harmonized_type:
        return CheckResult("C11", var_name, "SKIP", "Type information missing")
    if src_type == harmonized_type:
        return CheckResult("C11", var_name, "PASS", f"Type consistent: {src_type}")

    if src_type == "categorical" and harmonized_type == "continuous":
        observed_codes = set(_distribution_count_map(src_var))
        if _codes_are_numeric_or_sentinel(observed_codes):
            return CheckResult(
                "C11", var_name, "INFO",
                "Source is encoded/categorical but observed values are numeric; treating as numeric-coded source metadata, not a harmonization type error",
                {
                    "source_type": src_type,
                    "harmonized_type": harmonized_type,
                    "observed_codes_numeric_or_sentinel": True,
                },
            )

    return CheckResult(
        "C11", var_name, "WARN",
        f"Type mismatch: source={src_type}, harmonized={harmonized_type}",
        {"source_type": src_type, "harmonized_type": harmonized_type},
    )


def check_c6_sd_preservation(
    src_var: dict, harmonized_var: dict, var_name: str,
    pass_rel: float = 0.002, warn_rel: float = 0.01,
) -> CheckResult:
    """C6: Standard deviation comparison."""
    if src_var.get("type") != "continuous" or harmonized_var.get("type") != "continuous":
        return CheckResult("C6", var_name, "SKIP", "Not both continuous")

    src_sd = src_var.get("sd")
    harmonized_sd = harmonized_var.get("sd")
    if src_sd is None or harmonized_sd is None:
        return CheckResult("C6", var_name, "SKIP", "Missing SD value")

    if src_sd == 0:
        if harmonized_sd == 0:
            return CheckResult("C6", var_name, "PASS", "Both SDs are 0")
        return CheckResult("C6", var_name, "WARN", f"Source SD=0, harmonized SD={harmonized_sd}")

    rel_diff = abs(harmonized_sd - src_sd) / abs(src_sd)
    if rel_diff <= pass_rel:
        return CheckResult("C6", var_name, "PASS",
                           _cmp_stat("SD preserved", src_sd, harmonized_sd, rel_diff))
    if rel_diff <= warn_rel:
        return CheckResult("C6", var_name, "WARN",
                           _cmp_stat("SD shifted", src_sd, harmonized_sd, rel_diff))
    return CheckResult("C6", var_name, "FAIL",
                       f"SD mismatch: {_n(src_sd)} -> {_n(harmonized_sd)} (d={rel_diff:.4f})",
                       {"source_sd": src_sd, "harmonized_sd": harmonized_sd})


def check_c7_categorical_distribution(
    src_var: dict, harmonized_var: dict, var_name: str,
    pass_pct: float = 0.5,
    value_map: dict | None = None,
) -> CheckResult:
    """C7: Categorical distribution comparison.

    *value_map* translates source category keys (raw dbGaP codes) to harmonized
    category keys (e.g. OMOP concept codes) before comparison.
    """
    if src_var.get("type") != "categorical" or harmonized_var.get("type") != "categorical":
        return CheckResult("C7", var_name, "SKIP", "Not both categorical")
    confidence = src_var.get("_comparison_confidence")
    limitations = src_var.get("_comparison_limitations") or []
    if confidence == "unsupported":
        return CheckResult(
            "C7", var_name, "SKIP",
            "Expected distribution requires row-level joint counts; aggregate comparison not attempted",
            {"comparison_confidence": confidence, "comparison_limitations": limitations},
        )

    src_dist = src_var.get("distribution", {})
    harmonized_dist = harmonized_var.get("distribution", {})
    if not src_dist:
        return CheckResult("C7", var_name, "SKIP", "No source distribution")

    # Translate using value_map
    if value_map:
        translated: dict[str, Any] = {}
        translated_total = 0
        normalized_value_map = {normalize_category_key(k): v for k, v in value_map.items()}
        for cat, stats in src_dist.items():
            norm_cat = normalize_category_key(cat)
            mapped = normalized_value_map.get(norm_cat)
            if not mapped:
                try:
                    mapped = normalized_value_map.get(str(int(float(norm_cat))))
                except (ValueError, OverflowError):
                    pass
            new_cat = normalize_category_key(mapped if mapped else norm_cat)
            existing = translated.setdefault(
                new_cat,
                {"n": 0, "pct": 0.0, "source_categories": []},
            )
            count = int(stats.get("n", 0) or 0)
            existing["n"] += count
            existing["source_categories"].append(norm_cat)
            translated_total += count
        for stats in translated.values():
            stats["pct"] = round(stats["n"] / translated_total * 100, 2) if translated_total else 0.0
            if len(stats["source_categories"]) == 1:
                stats.pop("source_categories", None)
        src_dist = translated

    # Normalize harmonized keys — pipeline may serialize values as JSON arrays
    # or Python reprs such as "['OMOP:8527']" / "('OMOP:8527',)".
    normalized_out: dict[str, Any] = {}
    for ok, stats in harmonized_dist.items():
        normalized_out[normalize_category_key(ok)] = stats
    harmonized_dist = normalized_out

    src_keys = set(src_dist)
    harmonized_keys = set(harmonized_dist)
    missing = sorted(src_keys - harmonized_keys)
    extra = sorted(harmonized_keys - src_keys)

    mismatches: list[dict] = []
    for cat in src_keys & harmonized_keys:
        src_pct = src_dist[cat].get("pct", 0)
        harmonized_pct = harmonized_dist[cat].get("pct", 0)
        diff = abs(harmonized_pct - src_pct)
        if diff > pass_pct:
            mismatches.append({
                "category": cat,
                "source_n": src_dist[cat].get("n"),
                "source_pct": src_pct,
                "harmonized_n": harmonized_dist[cat].get("n"),
                "harmonized_pct": harmonized_pct,
                "diff": diff,
            })

    # Build full per-category distribution table for report rendering
    all_cats = sorted(src_keys | harmonized_keys)
    full_table: list[dict] = []
    for cat in all_cats:
        row: dict = {"category": cat}
        if cat in src_dist:
            row["source_n"] = src_dist[cat].get("n")
            row["source_pct"] = src_dist[cat].get("pct")
        if cat in harmonized_dist:
            row["harmonized_n"] = harmonized_dist[cat].get("n")
            row["harmonized_pct"] = harmonized_dist[cat].get("pct")
        full_table.append(row)

    detail: dict = {"distribution_table": full_table}
    if missing:
        detail["missing_categories"] = missing
    if extra:
        detail["extra_categories"] = extra
    if mismatches:
        detail["mismatches"] = mismatches

    if not missing and not extra and not mismatches:
        return CheckResult("C7", var_name, "PASS",
                           f"Distribution matches ({len(src_dist)} categories)", detail)
    if not mismatches and not missing:
        return CheckResult("C7", var_name, "INFO",
                           f"Extra harmonized categories: {extra}", detail)
    if missing:
        if confidence == "partial":
            detail["comparison_confidence"] = confidence
            detail["comparison_limitations"] = limitations
            return CheckResult("C7", var_name, "WARN",
                               f"Partial expected distribution missing categories in harmonized: {missing}", detail)
        return CheckResult("C7", var_name, "FAIL",
                           f"Missing categories in harmonized: {missing}", detail)
    if confidence == "partial":
        detail["comparison_confidence"] = confidence
        detail["comparison_limitations"] = limitations
        return CheckResult("C7", var_name, "WARN",
                           f"Partial expected distribution has {len(mismatches)} category shift(s); row-level data needed for exact verdict", detail)
    return CheckResult("C7", var_name, "WARN",
                       f"{len(mismatches)} categories with >+/-{pass_pct}% shift", detail)


def check_c12_value_mapping_coverage(match: dict, phv_value_codes: dict[str, set[str]]) -> list[CheckResult]:
    """C12: Verify YAML value_mappings cover dbGaP/observed source codes."""
    results: list[CheckResult] = []
    yaml_entries = match.get("_yaml_entries") or [match]
    for entry in yaml_entries:
        mapping_specs = []
        if isinstance(entry.get("value_map"), dict) and entry.get("phv_id"):
            mapping_specs.append(("value_mappings", entry.get("phv_id"), entry.get("value_map")))
        if isinstance(entry.get("concept_value_map"), dict):
            mapping_specs.append((
                "concept_value_mappings",
                entry.get("concept_phv") or entry.get("phv_id"),
                entry.get("concept_value_map"),
            ))

        for mapping_kind, raw_phv, value_map in mapping_specs:
            phv_id = _canonical_phv_id(raw_phv or "")
            if not phv_id:
                continue
            mapped_codes = {
                normalize_category_key(_normalize_code(code))
                for code in value_map
            }
            dbgap_codes = phv_value_codes.get(phv_id, set())
            observed_counts = _distribution_count_map(entry.get("source_summary"))
            observed_codes = {code for code, count in observed_counts.items() if count > 0}
            expected_codes = dbgap_codes | observed_codes
            if not expected_codes:
                results.append(CheckResult(
                    "C12", f"{phv_id} [{mapping_kind}]", "SKIP",
                    "No dbGaP or observed coded values available for mapping coverage check",
                ))
                continue

            missing_codes = sorted(expected_codes - mapped_codes)
            extra_codes = sorted(mapped_codes - expected_codes)
            detail = {
                "phv_id": phv_id,
                "mapping_kind": mapping_kind,
                "yaml_file": entry.get("yaml_file"),
                "dbgap_codes": sorted(dbgap_codes),
                "observed_codes": sorted(observed_codes),
                "mapped_codes": sorted(mapped_codes),
            }
            if missing_codes:
                detail["missing_codes"] = missing_codes
                sentinel_missing = [code for code in missing_codes if _is_null_sentinel_code(code)]
                semantic_missing = [code for code in missing_codes if code not in sentinel_missing]
                if sentinel_missing:
                    detail["missing_sentinel_codes"] = sentinel_missing
                if semantic_missing:
                    detail["missing_semantic_codes"] = semantic_missing
                observed_bits = [
                    f"{code} (n={observed_counts[code]})"
                    for code in missing_codes
                    if observed_counts.get(code, 0) > 0
                ]
                suffix = f"; observed: {', '.join(observed_bits)}" if observed_bits else ""
                if semantic_missing:
                    message = (
                        f"YAML mapping does not cover semantic source code(s): "
                        f"{', '.join(semantic_missing)}{suffix}"
                    )
                    status = "WARN"
                else:
                    message = (
                        f"YAML mapping does not explicitly handle null/sentinel code(s): "
                        f"{', '.join(sentinel_missing)}{suffix}"
                    )
                    status = "INFO"
                results.append(CheckResult(
                    "C12", f"{phv_id} [{mapping_kind}]", status,
                    message,
                    detail,
                ))
            elif extra_codes:
                detail["extra_codes"] = extra_codes
                results.append(CheckResult(
                    "C12", f"{phv_id} [{mapping_kind}]", "INFO",
                    f"YAML includes code(s) not present in dbGaP/observed values: {', '.join(extra_codes)}",
                    detail,
                ))
            else:
                results.append(CheckResult(
                    "C12", f"{phv_id} [{mapping_kind}]", "PASS",
                    f"Mapping covers {len(mapped_codes)} source code(s)",
                    detail,
                ))
    return results


def _synthesize_source_visit_counts(
    source: dict, yaml_dir: Path,
) -> tuple[dict[str, int], list[str]]:
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
    multiple distinct visit labels (pooled tables are rare) the rows are split
    evenly with a note in the label.

    Returns a tuple of:
      - synthesized {visit_label: count} (PHTs mapped in visit.yaml only)
      - uncovered_phts: list of PHT IDs present in source but absent from visit.yaml
    """
    visit_yaml = yaml_dir / "visit.yaml"
    if not visit_yaml.exists():
        return {}, []

    rows_by_pht: dict[str, int] = source.get("total_rows_by_pht", {})
    if not rows_by_pht:
        return {}, []

    # Parse visit.yaml: each YAML document is a single-element list whose only
    # item is {"class_derivations": {"Visit": {populated_from, slot_derivations}}}
    pht_to_labels: dict[str, list[str]] = {}
    try:
        docs = list(yaml.safe_load_all(visit_yaml.read_text(encoding="utf-8")))
    except yaml.YAMLError:
        return {}, []

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
    for pht, n in rows_by_pht.items():
        labels = pht_to_labels.get(pht)
        if not labels:
            # PHT present in source but absent from visit.yaml — not being harmonized (by design)
            uncovered.append(pht)
        else:
            for label in labels:
                synthesized[label] = synthesized.get(label, 0) + n

    return synthesized, uncovered


def check_c8_visit_distribution(
    source: dict, harmonized: dict,
    warn_lo_ratio: float = 0.95, warn_hi_ratio: float = 1.05,
    yaml_dir: Path | None = None,
) -> list[CheckResult]:
    """C8: Visit-stratified row count comparison.

    For column-based cohorts (SPIROMICS, COPDGene) the source extractor
    auto-detects a visit column and populates ``rows_per_visit`` directly.
    For table-based cohorts (CHS, ARIC, CARDIA, FHS) ``rows_per_visit`` is
    empty; when *yaml_dir* is provided this function synthesizes source visit
    counts from ``total_rows_by_pht`` + ``visit.yaml``.

    When source and harmonized use incompatible visit label namespaces (zero
    overlap), falls back to total-count comparison.
    """
    results: list[CheckResult] = []
    src_visits = source.get("rows_per_visit", {})
    harmonized_visits = harmonized.get("rows_per_visit", {})

    # For table-based cohorts: synthesize source visit counts from PHT rows + visit.yaml
    synthesized = False
    uncovered_phts: list[str] = []
    if not src_visits and yaml_dir:
        src_visits, uncovered_phts = _synthesize_source_visit_counts(source, yaml_dir)
        if src_visits:
            synthesized = True

    if not src_visits and not harmonized_visits:
        return [CheckResult("C8", "_visits", "SKIP", "No visit data in either summary")]
    if not src_visits:
        return [CheckResult("C8", "_visits", "SKIP", "No source visit data")]

    src_label = "synthesized from total_rows_by_pht + visit.yaml" if synthesized else "source"

    src_keys = set(src_visits) - {"_MISSING"}
    harmonized_keys = set(harmonized_visits) - {"_MISSING"}

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
            return [CheckResult("C8", "visit_TOTAL", "PASS",
                                f"Total visits match: N={_n(src_total)} despite label namespace mismatch",
                                detail)]
        detail["comparison_confidence"] = "unsupported"
        return [CheckResult(
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
        if harmonized_n == src_n:
            results.append(CheckResult("C8", f"visit_{visit}", "PASS",
                                       f"Visit {visit}: N={_n(src_n)} ({src_label})",
                                       detail or None))
        elif harmonized_n == 0:
            results.append(CheckResult("C8", f"visit_{visit}", "FAIL",
                                       f"Visit {visit}: missing in harmonized (source N={_n(src_n)}, {src_label})",
                                       detail or None))
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

    return results


def _range_violations(val_min, val_max, matched: dict) -> list[str]:
    """Return list of range violation strings for a given min/max against a matched range def."""
    issues: list[str] = []
    red_lo = matched.get("red_flag_lo")
    red_hi = matched.get("red_flag_hi")
    plaus_lo = matched.get("plausible_lo")
    plaus_hi = matched.get("plausible_hi")
    if val_min is not None:
        if red_lo is not None and val_min < red_lo:
            issues.append(f"min={val_min} below red_flag {red_lo}")
        elif plaus_lo is not None and val_min < plaus_lo:
            issues.append(f"min={val_min} below plausible {plaus_lo}")
    if val_max is not None:
        if red_hi is not None and val_max > red_hi:
            issues.append(f"max={val_max} above red_flag {red_hi}")
        elif plaus_hi is not None and val_max > plaus_hi:
            issues.append(f"max={val_max} above plausible {plaus_hi}")
    return issues


def check_c9_clinical_range(
    harmonized_var: dict, var_name: str, clinical_ranges: dict,
    src_var: dict | None = None,
) -> CheckResult:
    """C9: Harmonized values within defined clinical plausible range.

    When src_var is provided, each violation message is annotated with:
            [out+src]  - both source and harmonized exceed the bound
            [out only] - only the harmonized exceeds the bound (transformation may have introduced issue)
            [src only] - only the source exceeds the bound (pre-existing in raw data)
    """
    if harmonized_var.get("type") != "continuous":
        return CheckResult("C9", var_name, "SKIP", "Not continuous")

    # Match range definition: exact name > code match > substring
    matched: dict | None = None
    best_len = 0
    obs_type = harmonized_var.get("observation_type", "")
    for range_name, rng in clinical_ranges.items():
        if range_name.startswith("_"):
            continue
        if var_name.upper() in [n.upper() for n in rng.get("common_phv_names", [])]:
            matched = rng
            break
        codes = rng.get("oba_codes", []) + rng.get("omop_codes", [])
        if obs_type and obs_type in codes:
            matched = rng
            break
        # Word-boundary substring fallback: treat underscores as separators to prevent
        # e.g. range_name="wbc" matching var_name="wbc_pct_basophils".
        _wb_pattern = (r'(?<![A-Za-z0-9_])' + re.escape(range_name.upper())
                       + r'(?![A-Za-z0-9_])')
        if re.search(_wb_pattern, var_name.upper()) and len(range_name) > best_len:
            matched = rng
            best_len = len(range_name)

    if not matched:
        return CheckResult("C9", var_name, "SKIP", "No clinical range defined")

    out_min = harmonized_var.get("min")
    out_max = harmonized_var.get("max")
    if out_min is None or out_max is None:
        return CheckResult("C9", var_name, "SKIP", "No min/max in harmonized")

    out_issues = _range_violations(out_min, out_max, matched)

    if not out_issues:
        plaus_lo = matched.get("plausible_lo")
        plaus_hi = matched.get("plausible_hi")
        return CheckResult("C9", var_name, "PASS",
                           f"Range OK: [{out_min}, {out_max}] within [{plaus_lo}, {plaus_hi}]")

    # Annotate each issue with source context when src_var is available
    if src_var and src_var.get("min") is not None and src_var.get("max") is not None:
        src_min = src_var.get("min")
        src_max = src_var.get("max")
        src_issues = _range_violations(src_min, src_max, matched)
        # Build annotated messages
        annotated: list[str] = []
        for issue in out_issues:
            # Determine if the same bound appears in src_issues
            in_src = any(
                ("below" in issue and "below" in s) or ("above" in issue and "above" in s)
                for s in src_issues
            )
            tag = "[out+src]" if in_src else "[out only]"
            annotated.append(f"{issue} {tag}")
        # Also report src-only violations so reviewer knows raw data pre-condition
        for s_issue in src_issues:
            in_out = any(
                ("below" in s_issue and "below" in o) or ("above" in s_issue and "above" in o)
                for o in out_issues
            )
            if not in_out:
                annotated.append(f"{s_issue} [src only]")
        issues = annotated
    else:
        issues = out_issues

    red_issues = [i for i in issues if "red_flag" in i]
    has_red = bool(red_issues)
    # Demote FAIL -> WARN when every red_flag violation is also present in the
    # source data ([out+src]): the raw data already contained the extreme value
    # so the harmonized output faithfully preserved it rather than introducing it.
    all_red_in_src = has_red and all("[out+src]" in i for i in red_issues)
    if has_red and not all_red_in_src:
        status = "FAIL"
    else:
        status = "WARN"
    return CheckResult("C9", var_name, status,
                       "; ".join(issues),
                       {"min": out_min, "max": out_max})


# Detects simple 2-variable directional checks: "mean(X) > mean(Y)",
# "mean(X) >= mean(Y)", "mean(X) < mean(Y)", or "mean(X) <= mean(Y)".
# These directional rules are interpreted as non-strict clinical expectations
# (>= / <=) because equal means at aggregate precision should not fail a
# population-level plausibility check when the config uses the strict forms.
_C10_SIMPLE_RE = re.compile(r"mean\([^)]+\)\s*(<=|>=|<|>)\s*mean\([^)]+\)")


def check_c10_cross_variable(
    harmonized_vars: dict, clinical_ranges: dict,
) -> list[CheckResult]:
    """C10: Cross-variable consistency driven by _cross_variable_rules in clinical_ranges.

    Rules with exactly 2 variables and a simple mean(X) > mean(Y) or mean(X) < mean(Y)
    check expression are executed automatically.  Complex rules (>=, approximate equality, multi-variable
    formulas) emit SKIP and are intended for future implementation.

    Concept codes are resolved from the per-range definitions in clinical_ranges -
    no concept IDs are hardcoded in this function.
    """
    results: list[CheckResult] = []
    rules = clinical_ranges.get("_cross_variable_rules", {})

    for rule_id, rule in rules.items():
        check_expr = rule.get("check", "")
        variables = rule.get("variables", [])
        severity = "FAIL" if rule.get("severity", "").upper() == "ERROR" else "WARN"
        description = rule.get("description", rule_id)

        if str(rule.get("type", "simple")).lower() == "complex":
            results.append(CheckResult(
                "C10", rule_id, "SKIP",
                f"Complex cross-variable rule declared in config; manual or future rule-engine review required: {description}"
            ))
            continue

        m = _C10_SIMPLE_RE.search(check_expr)
        if not m or len(variables) != 2:
            results.append(CheckResult(
                "C10", rule_id, "SKIP",
                f"Multi-variable or formula rule (not yet implemented): {description}"
            ))
            continue

        operator = m.group(1)  # "<", "<=", ">", or ">="

        # Resolve concept codes from config - no hardcoded IDs here (A2)
        range_a = clinical_ranges.get(variables[0])
        range_b = clinical_ranges.get(variables[1])
        if not range_a or not range_b:
            results.append(CheckResult(
                "C10", rule_id, "SKIP",
                f"Range definition not found for {variables[0]!r} or {variables[1]!r}"
            ))
            continue

        codes_a = set(range_a.get("omop_codes", []) + range_a.get("oba_codes", []))
        codes_b = set(range_b.get("omop_codes", []) + range_b.get("oba_codes", []))

        if not codes_a or not codes_b:
            results.append(CheckResult(
                "C10", rule_id, "SKIP",
                f"No concept codes defined for {variables[0]!r} or {variables[1]!r}"
            ))
            continue

        matches_a = [
            (key, v) for key, v in harmonized_vars.items()
            if v.get("observation_type") in codes_a
        ]
        matches_b = [
            (key, v) for key, v in harmonized_vars.items()
            if v.get("observation_type") in codes_b
        ]

        ambiguous: list[str] = []
        detail: dict = {}
        if len(matches_a) > 1:
            ambiguous.append(variables[0])
            detail[f"{variables[0]}_matches"] = [key for key, _ in matches_a]
        if len(matches_b) > 1:
            ambiguous.append(variables[1])
            detail[f"{variables[1]}_matches"] = [key for key, _ in matches_b]
        if ambiguous:
            results.append(CheckResult(
                "C10", rule_id, "WARN",
                "Ambiguous cross-variable rule: multiple harmonized variables match "
                f"{', '.join(ambiguous)}; rule not evaluated",
                detail,
            ))
            continue

        var_a = matches_a[0][1] if matches_a else None
        var_b = matches_b[0][1] if matches_b else None

        if not var_a or not var_b:
            missing = []
            if not var_a:
                missing.append(variables[0])
            if not var_b:
                missing.append(variables[1])
            results.append(CheckResult(
                "C10", rule_id, "SKIP",
                f"Rule not applicable; required harmonized variable(s) not found: {', '.join(missing)}"
            ))
            continue

        mean_a = var_a.get("mean")
        mean_b = var_b.get("mean")
        if mean_a is None or mean_b is None:
            results.append(CheckResult(
                "C10", rule_id, "SKIP",
                f"Mean missing for one or both variables in rule {rule_id!r}"
            ))
            continue

        label_a = variables[0].replace("_", " ")
        label_b = variables[1].replace("_", " ")

        if operator in (">", ">="):
            passed = mean_a >= mean_b
            display_operator = ">="
        else:  # "<" or "<="
            passed = mean_a <= mean_b
            display_operator = "<="

        if passed:
            results.append(CheckResult(
                "C10", rule_id, "PASS",
                f"{label_a} mean ({mean_a:.4g}) {display_operator} {label_b} mean ({mean_b:.4g})"
            ))
        else:
            results.append(CheckResult(
                "C10", rule_id, severity,
                f"{label_a} mean ({mean_a:.4g}) NOT {display_operator} {label_b} mean ({mean_b:.4g})"
                f" -- {description}"
            ))

    if not results:
        results.append(CheckResult("C10", "_cross", "SKIP",
                                   "No cross-variable pairs found in harmonized data"))

    return results


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

_STATUS_ICONS = {
    "PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]",
    "SKIP": "[SKIP]", "INFO": "[INFO]",
}


def generate_markdown_report(
    results: list[CheckResult],
    cohort: str,
    source_meta: dict,
    harmonized_meta: dict,
    crosswalk: list[dict] | None = None,
) -> str:
    """Generate a human-readable Markdown report."""
    lines = [
        f"# HV-DataQC Comparison Report: {cohort}",
        "",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Source:** {source_meta.get('source', '?')}",
        f"**Harmonized:** {harmonized_meta.get('source', '?')}",
        "",
    ]

    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1

    lines.append("## Summary")
    lines.append("")
    lines.append("| Status | Count |")
    lines.append("|--------|-------|")
    for status in ["PASS", "WARN", "FAIL", "SKIP", "INFO"]:
        if counts.get(status, 0) > 0:
            lines.append(f"| {_STATUS_ICONS[status]} {status} | {counts[status]} |")
    lines.append(f"| **Total** | **{sum(counts.values())}** |")
    lines.append("")

    # Multi-PHT pooled-source crosswalk audit section.  Lists every harmonized
    # variable whose source side was aggregated across multiple dbGaP tables
    # (typical for longitudinal measurements that appear once per visit).
    if crosswalk:
        pooled_entries = [m for m in crosswalk if len(m.get("_source_phts") or []) > 1]
        if pooled_entries:
            lines.append("## Pooled Source Crosswalk (multi-PHT aggregation)")
            lines.append("")
            lines.append(
                "Harmonized variables whose source side was pooled across multiple "
                "dbGaP tables.  The compare tool reports a single combined `n_valid`, "
                "weighted mean, pooled SD and merged value distribution against the "
                "harmonized longitudinal output."
            )
            lines.append("")
            lines.append(
                "| Harmonized key | Source column(s) | Contributing PHTs | Pooled n_valid |"
            )
            lines.append(
                "|----------------|------------------|-------------------|---------------:|"
            )
            for m in pooled_entries:
                hkey = _md_escape(m.get("harmonized_key", ""))
                src_keys = ", ".join(_md_escape(s) for s in (m.get("_source_keys") or []))
                phts = ", ".join(m.get("_source_phts") or [])
                pooled_n = (m.get("_resolved_src") or {}).get("n_valid", 0)
                lines.append(f"| {hkey} | {src_keys} | {phts} | {pooled_n:,} |")
            lines.append("")

    check_names = {
        "C1": "N Preservation", "C2": "N Loss Detection",
        "C3": "Missing Value Accounting", "C4": "Mean Preservation",
        "C5": "Mean After Conversion", "C6": "SD Preservation",
        "C7": "Categorical Distribution", "C8": "Visit N Distribution",
        "C9": "Clinical Range", "C10": "Cross-Variable Consistency",
        "C11": "Variable Type Consistency",
        "C12": "Value Mapping Coverage",
    }

    _sort_key = {"FAIL": 0, "WARN": 1, "PASS": 2, "INFO": 3, "SKIP": 4}

    def _render_c7_detail(r: CheckResult) -> list[str]:
        """Render C7 distribution table and mismatch detail as indented markdown."""
        sub: list[str] = []
        table = r.detail.get("distribution_table", [])
        if not table:
            return sub
        sub.append("")
        mismatch_cats = {m["category"] for m in r.detail.get("mismatches", [])}
        missing_cats = set(r.detail.get("missing_categories", []))
        extra_cats = set(r.detail.get("extra_categories", []))
        # Check if all rows are identical (src == harmonized) to simplify the table
        all_identical = all(
            row.get("source_n") == row.get("harmonized_n")
            and row.get("source_pct") == row.get("harmonized_pct")
            for row in table
        )
        if all_identical:
            sub.append("  | Category | N | % |")
            sub.append("  |----------|------:|------:|")
        else:
            sub.append("  | Category | Src N | Src % | Harmonized N | Harmonized % | Δ% |")
            sub.append("  |----------|------:|------:|------:|------:|---:|")
        for row in table:
            cat = row["category"]
            cat_label = _md_escape(cat)
            src_n = f"{row['source_n']:,}" if isinstance(row.get("source_n"), (int, float)) else str(row.get("source_n", ""))
            src_pct = f"{row['source_pct']:.1f}" if row.get("source_pct") is not None else ""
            flag = " ⚠" if cat in mismatch_cats else (
                   " ✗" if cat in missing_cats else (
                   " ＋" if cat in extra_cats else ""))
            if all_identical:
                sub.append(f"  | {cat_label}{flag} | {src_n} | {src_pct} |")
            else:
                harmonized_n = f"{row['harmonized_n']:,}" if isinstance(row.get("harmonized_n"), (int, float)) else str(row.get("harmonized_n", ""))
                harmonized_pct = f"{row['harmonized_pct']:.1f}" if row.get("harmonized_pct") is not None else ""
                if row.get("source_pct") is not None and row.get("harmonized_pct") is not None:
                    delta = f"{row['harmonized_pct'] - row['source_pct']:+.1f}"
                else:
                    delta = ""
                sub.append(f"  | {cat_label}{flag} | {src_n} | {src_pct} | {harmonized_n} | {harmonized_pct} | {delta} |")
        return sub

    _check_descriptions = {
        "C1": (
            "Checks whether the total number of unique participants is preserved "
            "from source to harmonized. A small loss may indicate that the pipeline's "
            "anchor table (e.g. Demographics_Baseline) excludes participants who appear "
            "in other source tables. Investigate with `find_participant_gap.py` on SB."
        ),
        "C2": (
            "Checks per-variable valid-N counts. PASS means the harmonized output has "
            "the same number of non-missing values as the source for that variable. "
            "FAIL means rows were silently lost or gained during transformation."
        ),
        "C3": (
            "Checks that missing-value rates are stable between source and harmonized. "
            "A shift suggests the pipeline is introducing or removing nulls."
        ),
        "C4": (
            "Checks that continuous variable means are preserved (no unit conversion). "
            "Deviations close to zero (d<0.001) are rounding artifacts. Larger deviations "
            "suggest data corruption or unintended filtering."
        ),
        "C5": (
            "Checks continuous means after a known unit conversion factor "
            "(e.g. inches to cm). Skipped when no conversion is expected."
        ),
        "C6": (
            "Checks that standard deviations are preserved. A shift in SD without a "
            "corresponding shift in mean suggests outlier filtering or truncation."
        ),
        "C7": (
            "Compares categorical value distributions after applying YAML value_mappings "
            "(e.g. source code 1/2 mapped to PRESENT/ABSENT). Categories are aggregated "
            "when multiple source values map to one harmonized category."
        ),
        "C8": (
            "Checks that per-visit row counts are preserved. For table-based cohorts "
            "where source files have no visit column, source visit counts are synthesized "
            "from total_rows_by_pht + visit.yaml mappings."
        ),
        "C9": (
            "Checks whether harmonized min/max values fall within clinically plausible "
            "ranges defined in `clinical_ranges.yaml`. This catches sentinel values "
            "(e.g. 0 or 999) that should have been mapped to missing, as well as unit "
            "conversion errors that produce impossible values.\n\n"
            "> **Annotations:** `[out+src]` = outlier exists in both source and harmonized "
            "(pre-existing in raw data, faithfully preserved — not a pipeline bug). "
            "`[out only]` = harmonized exceeds bound but source did not "
            "(the pipeline may have introduced the issue). "
            "`[src only]` = source exceeds bound but harmonized does not "
            "(pipeline corrected or filtered the value)."
        ),
        "C10": (
            "Checks cross-variable consistency rules (e.g. SBP > DBP, FEV1 < FVC). "
            "Rules are defined in `clinical_ranges.yaml`. Formula-based rules "
            "(e.g. BMI consistency) are not yet implemented."
        ),
        "C11": (
            "Checks that source and harmonized agree on variable type "
            "(continuous vs categorical). A mismatch suggests the YAML transform "
            "or the source type inference needs attention."
        ),
        "C12": (
            "Checks that YAML value_mappings cover dbGaP coded values and observed "
            "source categories. This is separate from before/after preservation: an "
            "unmapped code can be expected transform behavior while still being a "
            "YAML completeness issue."
        ),
    }

    def _render_unmatched_source(r: CheckResult) -> list[str]:
        """Render unmatched source variables as a collapsed block."""
        sub: list[str] = []
        keys = r.detail.get("source_keys", [])
        if not keys:
            return sub
        sub.append("")
        sub.append(f"<details><summary>{len(keys)} unmatched source variables</summary>")
        sub.append("")
        for sk in sorted(keys):
            sub.append(f"- `{sk}`")
        sub.append("")
        sub.append("</details>")
        return sub

    for check_id in ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "C10", "C11", "C12"]:
        check_results = [r for r in results if r.check_id == check_id]
        if not check_results:
            continue
        lines.append(f"## {check_id}: {check_names.get(check_id, check_id)}")
        lines.append("")
        if check_id in _check_descriptions:
            lines.append(_check_descriptions[check_id])
            lines.append("")

        # Separate results by status for collapsing
        fails = [r for r in check_results if r.status == "FAIL"]
        warns = [r for r in check_results if r.status == "WARN"]
        infos = [r for r in check_results if r.status == "INFO"]
        passes = [r for r in check_results if r.status == "PASS"]
        skips = [r for r in check_results if r.status == "SKIP"]

        # FAIL and WARN always shown expanded
        for r in fails + warns:
            icon = _STATUS_ICONS.get(r.status, r.status)
            lines.append(f"- {icon} **{_md_escape(r.variable)}**: {_md_escape(r.message)}")
            if check_id == "C7":
                lines.extend(_render_c7_detail(r))

        # INFO items
        for r in infos:
            icon = _STATUS_ICONS.get(r.status, r.status)
            lines.append(f"- {icon} **{_md_escape(r.variable)}**: {_md_escape(r.message)}")
            if r.detail.get("direction") == "source_unmatched_summary":
                lines.extend(_render_unmatched_source(r))

        # PASS collapsed if there are also FAIL/WARN/INFO items, or if > 5
        if passes:
            show_collapsed = len(passes) > 5 or fails or warns
            if show_collapsed:
                lines.append("")
                lines.append(f"<details><summary>{len(passes)} PASS results</summary>")
                lines.append("")
            for r in passes:
                icon = _STATUS_ICONS.get(r.status, r.status)
                lines.append(f"- {icon} **{_md_escape(r.variable)}**: {_md_escape(r.message)}")
                if check_id == "C7":
                    lines.extend(_render_c7_detail(r))
            if show_collapsed:
                lines.append("")
                lines.append("</details>")

        # SKIP always collapsed
        if skips:
            lines.append("")
            lines.append(f"<details><summary>{len(skips)} SKIP results</summary>")
            lines.append("")
            for r in skips:
                icon = _STATUS_ICONS.get(r.status, r.status)
                lines.append(f"- {icon} **{_md_escape(r.variable)}**: {_md_escape(r.message)}")
            lines.append("")
            lines.append("</details>")

        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Post-processing: dedup + consolidate check results
# ---------------------------------------------------------------------------

def _dedup_check_results(results: list[CheckResult]) -> list[CheckResult]:
    """Deduplicate and consolidate check results before reporting.

    Two passes:

    1. **Exact dedup** — when the same ``(check_id, variable, status, message)``
       tuple appears more than once (e.g. a source PHV is routed to both a
       pre- and post-bronchodilator harmonized concept and both fire the same
       C2/C3 finding), keep only the first occurrence.

    2. **C9 consolidation** — when different harmonized concepts both match the
       same source variable and fire C9 against *different* clinical range
       definitions, merge the per-range violations into one ``CheckResult``
       using the worst status and a joined message.  This prevents a variable
       like ``sbpa17`` from appearing twice as FAIL when it matches both a
       systolic and a diastolic range definition.
    """
    _STATUS_RANK = {"FAIL": 3, "WARN": 2, "INFO": 1, "PASS": 0, "SKIP": -1}

    # Pass 1: exact dedup by (check_id, variable, status, message)
    seen_exact: set[tuple] = set()
    deduped: list[CheckResult] = []
    for r in results:
        key = (r.check_id, r.variable, r.status, r.message)
        if key not in seen_exact:
            seen_exact.add(key)
            deduped.append(r)

    # Pass 2: C9 consolidation — merge multiple C9 results for the same variable
    # Collect C9 groups by variable, preserving insertion order
    c9_groups: dict[str, list[CheckResult]] = {}
    for r in deduped:
        if r.check_id == "C9":
            c9_groups.setdefault(r.variable, []).append(r)

    # Variables with only one C9 result need no work; build merged map for others
    c9_merged: dict[str, CheckResult] = {}
    for var, group in c9_groups.items():
        if len(group) == 1:
            c9_merged[var] = group[0]
            continue
        actionable = [r for r in group if r.status not in ("SKIP", "PASS")]
        if not actionable:
            # All SKIP/PASS — keep the first (PASS wins over SKIP)
            best = max(group, key=lambda r: _STATUS_RANK.get(r.status, -1))
            c9_merged[var] = best
            continue
        worst = max(actionable, key=lambda r: _STATUS_RANK.get(r.status, 0))
        # Deduplicate violation strings before joining (different range
        # definitions may fire the same "min=0 below red_flag X" string)
        seen_parts: set[str] = set()
        msg_parts: list[str] = []
        for r in actionable:
            for part in r.message.split("; "):
                if part and part not in seen_parts:
                    seen_parts.add(part)
                    msg_parts.append(part)
        merged_detail = dict(worst.detail) if worst.detail else {}
        c9_merged[var] = CheckResult(
            "C9", var, worst.status, "; ".join(msg_parts), merged_detail
        )

    # Rebuild final list: replace first C9 occurrence with merged result;
    # drop subsequent C9 occurrences for the same variable.
    final: list[CheckResult] = []
    c9_emitted: set[str] = set()
    for r in deduped:
        if r.check_id != "C9":
            final.append(r)
        elif r.variable not in c9_emitted:
            c9_emitted.add(r.variable)
            final.append(c9_merged[r.variable])
        # else: second/third C9 for same variable — already merged, drop

    return final


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Compare source vs. harmonized summaries (C1-C11 checks).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--source", required=True, metavar="JSON",
                   help="Source summary JSON from extract_source_summaries.py")
    p.add_argument("--harmonized", required=True, metavar="JSON",
                   help="Harmonized summary JSON from extract_harmonized_summaries.py")
    p.add_argument("--cohort", required=True, metavar="NAME",
                   help="Cohort name (e.g. SPIROMICS, CARDIA)")

    p.add_argument("--yaml-dir", metavar="DIR",
                   help="HV YAML transform directory for the cohort "
                        "(e.g. .../priority_variables_transform/SPIROMICS-ingest/). "
                        "Without this, only C1/C8/C10 run.")
    p.add_argument("--cache-dir", metavar="DIR",
                   help="dbGaP cache directory for the cohort, used to resolve PHV->name "
                        "(e.g. data/dbgap-cache/spiromics/). "
                        "REQUIRED when --yaml-dir is supplied (must contain "
                        "pheno_variable_summaries/*.data_dict.xml). Without it the "
                        "YAML-driven crosswalk cannot resolve PHV IDs to source column "
                        "names and would be empty.")

    p.add_argument("--clinical-ranges", metavar="YAML",
                   help=f"Clinical ranges YAML (default: {_CONFIG_DIR / 'clinical_ranges.yaml'})")
    p.add_argument("--thresholds", metavar="YAML",
                   help=f"Statistical thresholds YAML (default: {_THRESHOLDS_PATH})")
    p.add_argument("--report", metavar="FILE",
                   help="Markdown report output path "
                        "(default: <cohort>_comparison_report.md)")
    p.add_argument("--json-report", metavar="FILE",
                   help="JSON report output path "
                        "(default: <cohort>_comparison_results.json)")
    p.add_argument("--show-unmatched-source", action="store_true", default=False,
                   help="Include INFO rows for source variables not present in the harmonized "
                        "output (default: hidden; only a summary count is shown).")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    cohort = args.cohort.upper()

    # Validate inputs
    for path_arg, label in [(args.source, "--source"), (args.harmonized, "--harmonized")]:
        if not Path(path_arg).exists():
            print(f"ERROR: {label} file not found: {path_arg}", file=sys.stderr)
            sys.exit(1)

    # Resolve optional paths
    yaml_dir = Path(args.yaml_dir) if args.yaml_dir else None
    cache_dir = Path(args.cache_dir) if args.cache_dir else None

    if not yaml_dir:
        print("NOTE: --yaml-dir not provided. YAML-driven crosswalk disabled; C4/C5/C6/C7/C9 will SKIP.")
    elif not yaml_dir.exists():
        print(f"WARNING: --yaml-dir not found: {yaml_dir}")
        yaml_dir = None

    # --cache-dir is required when --yaml-dir is supplied: without the PHV->name
    # map produced from the cache, _extract_crosswalk_from_class_derivations()
    # silently skips every YAML entry (missing src_name) and the YAML-driven
    # crosswalk ends up empty, producing a useless report.
    if yaml_dir and not cache_dir:
        print(
            "ERROR: --cache-dir is required when --yaml-dir is supplied. "
            "Without it the PHV->name map cannot be built and the YAML "
            "crosswalk will be empty.",
            file=sys.stderr,
        )
        sys.exit(2)

    if cache_dir and not cache_dir.exists():
        if yaml_dir:
            print(
                f"ERROR: --cache-dir not found: {cache_dir}. "
                "Required when --yaml-dir is supplied.",
                file=sys.stderr,
            )
            sys.exit(2)
        print(f"WARNING: --cache-dir not found: {cache_dir}")
        cache_dir = None

    # Load clinical ranges
    cr_path = (
        Path(args.clinical_ranges)
        if args.clinical_ranges
        else _CONFIG_DIR / "clinical_ranges.yaml"
    )
    clinical_ranges: dict = {}
    if cr_path.exists():
        try:
            with cr_path.open("r", encoding="utf-8") as fh:
                clinical_ranges = yaml.safe_load(fh) or {}
            print(f"Loaded {len(clinical_ranges)} clinical range definitions from {cr_path.name}")
            for warning in validate_clinical_ranges_config(clinical_ranges):
                print(f"WARNING: clinical ranges config: {warning}")
        except yaml.YAMLError as exc:
            print(f"ERROR: Malformed clinical ranges YAML {cr_path.name}: {exc} -- C9/C10 will SKIP",
                  file=sys.stderr)
    else:
        print(f"NOTE: Clinical ranges file not found: {cr_path} -- C9/C10 will SKIP")

    # Load thresholds
    thresholds_path = Path(args.thresholds) if args.thresholds else _THRESHOLDS_PATH
    thresholds = load_thresholds(thresholds_path)
    c1_t = thresholds.get("c1", {})
    c2_t = thresholds.get("c2", {})
    c3_t = thresholds.get("c3", {})
    c4_t = thresholds.get("c4", {})
    c5_t = thresholds.get("c5", {})
    c6_t = thresholds.get("c6", {})
    c7_t = thresholds.get("c7", {})
    c8_t = thresholds.get("c8", {})

    # Load summaries
    print(f"\nLoading source summary : {args.source}")
    with open(args.source, "r", encoding="utf-8") as fh:
        source: dict = json.load(fh)

    print(f"Loading harmonized summary: {args.harmonized}")
    with open(args.harmonized, "r", encoding="utf-8") as fh:
        harmonized: dict = json.load(fh)

    source_vars = source.get("variables", {})
    harmonized_vars = _normalize_harmonized_vars(harmonized.get("variables", {}))
    source_meta = source.get("metadata", {})
    harmonized_meta = harmonized.get("metadata", {})

    print(f"\nSource: {len(source_vars)} variables, "
          f"{source.get('total_participants', '?')} participants")
    print(f"Harmonized: {len(harmonized_vars)} variables, "
          f"{harmonized.get('total_participants', '?')} participants")

    # Build crosswalk
    print("\nBuilding variable crosswalk...")
    yaml_diagnostics: dict = {}
    try:
        crosswalk = build_variable_crosswalk(
            source_vars, harmonized_vars,
            yaml_dir=yaml_dir,
            cache_dir=cache_dir,
            source_doc=source,
            diagnostics_out=yaml_diagnostics,
        )
    except CrosswalkBuildError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
    print(f"Matched {len(crosswalk)} variable pairs")
    for m in crosswalk:
        method = m.get("match_method", "?")
        yaml_f = m.get("yaml_file", "")
        phv = m.get("phv_id", "")
        resolved_pht = m.get("_resolved_pht", "")
        source_phts = m.get("_source_phts") or []
        per_pht = m.get("_per_pht_src") or []
        resolved = m.get("_resolved_src") or {}
        extra = f" [{yaml_f}]" if yaml_f else ""
        extra += f" ({phv})" if phv else ""
        if len(source_phts) > 1:
            phts_str = "+".join(source_phts)
            extra += (
                f" -> [{phts_str}] pooled n_valid="
                f"{resolved.get('n_valid', 0):,} "
                f"({len(per_pht)} PHTs)"
            )
        elif resolved_pht:
            extra += f" -> {resolved_pht}"
        print(f"  {m['source_key']:<30} -> {m['harmonized_key']:<40} [{method}]{extra}")

    # Load dbGaP authoritative type map for source-type override (fixes heuristic
    # misclassification of true-integer count variables as categorical when
    # n_distinct ≤ 20, e.g. fruitf25 "how many fruits per day" range 0-20).
    phv_type_map: dict[str, str] = (
        load_phv_type_map(cache_dir) if cache_dir and cache_dir.exists() else {}
    )
    phv_value_codes: dict[str, set[str]] = (
        load_phv_value_codes_map(cache_dir) if cache_dir and cache_dir.exists() else {}
    )

    # Run checks
    all_results: list[CheckResult] = []

    # Collect all PHTs referenced by any YAML mapping so C1 can show the
    # YAML-scoped participant ceiling alongside the all-PHT union.
    mapped_phts: set[str] = {
        pht
        for m in crosswalk
        for pht in (m.get("_source_phts") or [])
    }
    all_results.extend(check_c1_n_preservation(
        source, harmonized,
        fail_pct=c1_t.get("fail_pct", 1.0),
        mapped_phts=mapped_phts or None,
    ))

    for match in crosswalk:
        src_key = match["source_key"]
        harmonized_key = match["harmonized_key"]
        # Use per-PHT stats when available (eliminates multi-table inflation).
        src_var = match.get("_resolved_src") or source_vars.get(src_key, {})
        harmonized_var = harmonized_vars[harmonized_key]

        # Override source type with dbGaP authoritative type when available.
        # The source extractor's n_distinct ≤ 20 heuristic misclassifies true
        # integer/count variables (e.g. fruitf25 range 0-20) as categorical.
        # dbGaP <type>integer</type> with no coded value list is unambiguously
        # continuous; <type>encoded</type> is unambiguously categorical.
        _dbgap_type = phv_type_map.get(match.get("phv_id", ""))
        if _dbgap_type and src_var.get("type") != _dbgap_type:
            src_var = {**src_var, "type": _dbgap_type}

        display_name = src_var.get("name", src_key)
        expected_basis = src_var.get("_comparison_basis")
        value_map = None if expected_basis and expected_basis != "source_direct" else match.get("value_map")

        # Build an enriched label for C2-C9 that includes PHV + PHT refs so
        # reviewers can trace each finding back to the source data dictionary.
        # Format (single PHT):  ath07 [phv00099087 / pht001450]
        # Format (pooled):      alcoh [phv00100084 / pht001451+pht001452+…]
        _phv_ids = list(
            dict.fromkeys(
                (match.get("_source_phvs") or [])
                + (match.get("_phv_ids") or [match.get("phv_id", "")])
            )
        )
        _phv_ids = [p for p in _phv_ids if p]
        if len(_phv_ids) > 1:
            _phv = "+".join(_phv_ids[:3]) + ("…" if len(_phv_ids) > 3 else "")
        elif _phv_ids:
            _phv = _phv_ids[0]
        else:
            _phv = ""
        _phts: list[str] = match.get("_source_phts") or (
            [match["_resolved_pht"]] if match.get("_resolved_pht") else []
        )
        if _phts:
            _pht_str = "+".join(_phts[:3]) + ("…" if len(_phts) > 3 else "")
        else:
            _pht_str = ""
        if _phv and _pht_str:
            var_label = f"{display_name} [{_phv} / {_pht_str}]"
        elif _phv:
            var_label = f"{display_name} [{_phv}]"
        elif _pht_str:
            var_label = f"{display_name} [{_pht_str}]"
        else:
            var_label = display_name

        all_results.append(check_c2_n_loss(
            src_var, harmonized_var, var_label,
            pass_pct=c2_t.get("pass_pct", 0.5), warn_pct=c2_t.get("warn_pct", 2.0),
            gain_warn_pct=c2_t.get("gain_warn_pct"),
            gain_fail_pct=c2_t.get("gain_fail_pct"),
        ))
        all_results.append(check_c3_missing_accounting(
            src_var, harmonized_var, var_label,
            pass_pp=c3_t.get("pass_pp", 0.5), warn_pp=c3_t.get("warn_pp", 3.0),
            n_valid_pass_pct=c3_t.get("n_valid_pass_pct", 0.5),
            n_valid_warn_pct=c3_t.get("n_valid_warn_pct", 3.0),
        ))
        all_results.append(check_c4_mean_preservation(
            src_var, harmonized_var, var_label,
            pass_rel=c4_t.get("pass_rel", 0.001), warn_rel=c4_t.get("warn_rel", 0.01),
        ))
        if expected_basis != "yaml_scalar_conversion" and should_run_c5_conversion_check(match, c5_t):
            all_results.append(check_c5_mean_after_conversion(
                src_var, harmonized_var, var_label,
                conversion_factor=match.get("conversion_factor") or c5_t.get("conversion_factor"),
                pass_rel=c5_t.get("pass_rel", 0.001),
            ))
        all_results.append(check_c6_sd_preservation(
            src_var, harmonized_var, var_label,
            pass_rel=c6_t.get("pass_rel", 0.002), warn_rel=c6_t.get("warn_rel", 0.01),
        ))
        all_results.append(check_c7_categorical_distribution(
            src_var, harmonized_var, var_label,
            pass_pct=c7_t.get("pass_pct", 0.5), value_map=value_map,
        ))
        all_results.append(check_c9_clinical_range(harmonized_var, var_label, clinical_ranges, src_var=src_var))
        all_results.append(check_c11_type_consistency(src_var, harmonized_var, var_label))
        all_results.extend(check_c12_value_mapping_coverage(match, phv_value_codes))

    all_results.extend(check_c8_visit_distribution(
        source, harmonized,
        warn_lo_ratio=c8_t.get("warn_lo_ratio", 0.95),
        warn_hi_ratio=c8_t.get("warn_hi_ratio", 1.05),
        yaml_dir=yaml_dir,
    ))
    all_results.extend(check_c10_cross_variable(harmonized_vars, clinical_ranges))

    # Flag unmatched variables.  A pooled YAML match contributes ALL of its
    # contributing source columns to matched_src (not just the first), so
    # subsequent strategies and the INFO unmatched-source reporter behave
    # correctly when a harmonized key was satisfied by multiple PHTs.
    matched_src: set[str] = set()
    for m in crosswalk:
        if m.get("_source_keys"):
            matched_src.update(m["_source_keys"])
            matched_src.update(m.get("_source_flat_keys") or [])
        else:
            matched_src.add(m["source_key"])
    matched_harmonized = {m["harmonized_key"] for m in crosswalk}
    _unmatched_src_keys = [
        sk for sk in source_vars
        if sk not in matched_src and "error" not in source_vars[sk]
    ]
    if _unmatched_src_keys:
        count = len(_unmatched_src_keys)
        # Always include the full list of unmatched source variables in the
        # detail dict so the report can render them in a collapsed block.
        all_results.append(CheckResult(
            "C2", "_unmatched_source_vars", "INFO",
            f"{count} source variable(s) not matched in harmonized",
            {"direction": "source_unmatched_summary", "count": count,
             "source_keys": _unmatched_src_keys},
        ))

    unresolved_yaml = (yaml_diagnostics.get("unresolved_yaml_entries") or {})
    yaml_proposed = set(yaml_diagnostics.get("yaml_proposed_harmonized_keys") or [])
    for ok in harmonized_vars:
        if ok in matched_harmonized:
            continue
        diag_entries = unresolved_yaml.get(ok, [])
        detail: dict = {
            "direction": "harmonized_unmatched",
            "harmonized_key": ok,
            "yaml_proposed_harmonized_key": ok in yaml_proposed,
        }
        if diag_entries:
            yaml_files = sorted({e.get("yaml_file") for e in diag_entries if e.get("yaml_file")})
            phvs = sorted({e.get("phv_id") for e in diag_entries if e.get("phv_id")})
            concept_codes = sorted(
                {e.get("concept_code") for e in diag_entries if e.get("concept_code")}
            )
            entity_classes = sorted(
                {e.get("entity_class") for e in diag_entries if e.get("entity_class")}
            )
            missing_src = [
                e.get("source_key_in_yaml")
                for e in diag_entries
                if e.get("missing_source_column") and e.get("source_key_in_yaml")
            ]
            detail.update(
                {
                    "yaml_files": yaml_files,
                    "phv_ids_in_yaml": phvs,
                    "concept_codes": concept_codes,
                    "entity_classes": entity_classes,
                    "missing_source_columns": sorted(set(missing_src)),
                }
            )
            msg_parts = ["Harmonized variable not matched in source"]
            if missing_src:
                msg_parts.append(
                    f"YAML proposed PHV(s) {', '.join(phvs) or '?'} -> source column(s) "
                    f"{', '.join(sorted(set(missing_src)))} but they are absent from the source extract"
                )
            else:
                msg_parts.append(
                    f"YAML proposed PHV(s) {', '.join(phvs) or '?'} but no contributing PHT had stats"
                )
            message = " — ".join(msg_parts)
        else:
            message = (
                "Harmonized variable not matched in source — no YAML block proposed this concept"
            )
        all_results.append(CheckResult("C2", ok, "FAIL", message, detail))

    # Dedup: remove exact-duplicate findings (same source PHV routed to
    # multiple harmonized concepts) and consolidate per-variable C9 violations
    # that fired against different range definitions.
    all_results = _dedup_check_results(all_results)

    # Summary
    counts: dict[str, int] = {}
    for r in all_results:
        counts[r.status] = counts.get(r.status, 0) + 1
    print(f"\n{'='*60}")
    print(f"Results: {counts}")

    # Write Markdown
    md = generate_markdown_report(
        all_results, cohort, source_meta, harmonized_meta, crosswalk=crosswalk
    )
    report_path = Path(args.report or f"{cohort.lower()}_comparison_report.md")
    _write_text_atomic(report_path, md)
    print(f"\nMarkdown report : {report_path}")

    # Write JSON
    json_report = {
        "metadata": {
            "cohort": cohort,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_file": args.source,
            "harmonized_file": args.harmonized,
            "thresholds_file": str(thresholds_path),
        },
        "summary": counts,
        "crosswalk": [
            # Strip verbose per-PHT raw summaries from the JSON crosswalk to
            # keep file size manageable; the pooled _resolved_src and the list
            # of contributing PHTs (_source_phts / _source_keys) remain.
            {k: v for k, v in m.items() if k != "_per_pht_src"}
            for m in crosswalk
        ],
        "yaml_diagnostics": yaml_diagnostics,
        "results": [r.to_dict() for r in all_results],
    }
    json_path = Path(args.json_report or f"{cohort.lower()}_comparison_results.json")
    _write_json_atomic(json_path, json_report)
    print(f"JSON report     : {json_path}")

    n_fail = counts.get("FAIL", 0)
    if n_fail > 0:
        print(f"\n{n_fail} FAIL(s) detected -- review report")
        sys.exit(1)
    else:
        print("\nAll checks passed or skipped")


if __name__ == "__main__":
    main()
