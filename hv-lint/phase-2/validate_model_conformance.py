#!/usr/bin/env python3
"""HV-Lint Phase 2: BDC-HM Model Conformance Checks.

Validates transformation YAML files against the linkml-map transformer model
and the BDCHM LinkML schema.

Checks:
    2.1  LinkML-Map key validation (unknown keys at any nesting level)
    2.2  BDCHM slot name validation (per-class)
    2.3  BDCHM class name validation
    2.4  Required/recommended slot enforcement (schema-driven)
         ext: Advisory age_at_observation on MeasurementObservation
    2.5  Object derivation structure validation
    2.5b Nested class range validation (class must match slot's schema range)
    2.6  CURIE format validation
         ext: Known-bad OMOP identifiers (380035630 ethnicity typo)
    2.7  Enum / value set membership validation
         ext: Cross-file enum consistency (e.g., SELF vs ONESELF)
    2.10 Unconditional age_at_condition_start on binary Condition blocks
    2.11 Condition missing ABSENT in condition_status value_mappings

Usage:
    python hv-lint/phase-2/validate_model_conformance.py
    python hv-lint/phase-2/validate_model_conformance.py --bdchm-ref v1.2.0 --cohort ARIC
    python hv-lint/phase-2/validate_model_conformance.py --bdchm-schema path/to/bdchm.yaml

Extracted from hv-lint/validate_yaml_quality.py (HV branch feature/392-hv-lint).
Phase 1 checks (expression syntax, duplicate detection) are in phase-1/.
Phase 3 checks (PHV/PHT accession format, dbGaP cross-ref) are in validate_dbgap_crossref.py.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _paths import find_transform_dir  # noqa: E402

TRANSFORM_DIR = find_transform_dir()

COHORTS = [
    "ARIC", "CARDIA", "CHS", "COPDGene",
    "FHS", "HCHS", "JHS", "MESA", "SPIROMICS", "WHI",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BDCHM_URL_TEMPLATE = (
    "https://raw.githubusercontent.com/RTIInternational/"
    "NHLBI-BDC-DMC-HM/{ref}/src/bdchm/schema/bdchm.yaml"
)

# Valid keys for each linkml-map model level.
# Derived from linkml_map.datamodel.transformer_model v0.3.9.
# See HV-Lint-Reference.md Assumption A2 for rationale.
#
# Captured from NHLBI-BDC-DMC-HV/.venv (Python 3.12, linkml-map 0.3.9) by
# reading transformer_model.py directly -- the import path crashes on Python 3.14
# due to ucumvert/pint initializing at module level (KeyError: 'millimeter_Hg').
# When the import fails, _derive_valid_keys() returns these frozen constants
# and prints a warning.  CI (Python 3.12) always uses the live import.
#
# HV-specific extensions ('value', 'object_derivations') are added
# manually -- see Assumption A3.
def _derive_valid_keys():
    """Derive valid key sets from the installed linkml-map model.

    Tries a live import first (accurate, Python 3.12 / CI).  Falls back to
    frozen constants captured from linkml-map v0.3.9 when the import fails
    (e.g., Python 3.14 pint/ucumvert incompatibility -- Assumption A2).
    """
    # --- frozen fallback (linkml-map v0.3.9, extracted 2026-03-15) -----------
    _TS_FROZEN = frozenset({
        "class_derivations", "comments", "description", "enum_derivations",
        "id", "implements", "prefixes", "slot_derivations", "source_schema",
        "target_schema", "title",
    })
    _CD_FROZEN = frozenset({
        "comments", "copy_directives", "description",
        "expression_to_expression_mappings", "expression_to_value_mappings",
        "implements", "is_a", "joins", "mirror_source", "mixins", "name",
        "overrides", "populated_from", "slot_derivations", "sources",
        "target_definition", "value_mappings",
    })
    _SD_FROZEN = frozenset({
        "aggregation_operation", "cast_collection_as", "comments",
        "copy_directives", "derived_from", "description", "dictionary_key",
        "expression_to_expression_mappings", "expression_to_value_mappings",
        "expr", "hide", "implements", "inverse_of", "is_a", "mirror_source",
        "mixins", "name", "overrides", "populated_from", "range", "sources",
        "stringification", "target_definition", "type_designator",
        "unit_conversion", "value_mappings",
        # HV extensions (not in base linkml-map model -- Assumption A3):
        "value",               # Static value assignment
        "class_derivations",   # Nested object structure, list-based (e.g., Quantity)
        "object_derivations",  # Legacy nested object structure (deprecated)
    })
    # -------------------------------------------------------------------------

    try:
        from linkml_map.datamodel.transformer_model import (
            TransformationSpecification, ClassDerivation, SlotDerivation,
        )
        ts_keys = frozenset(TransformationSpecification.model_fields.keys())
        cd_keys = frozenset(ClassDerivation.model_fields.keys())
        sd_keys = frozenset(SlotDerivation.model_fields.keys()) | {
            "value",
            "class_derivations",
            "object_derivations",
        }
        return ts_keys, cd_keys, sd_keys
    except Exception:
        print(
            "WARNING: linkml_map import failed (likely Python 3.14 + ucumvert "
            "incompatibility). Using frozen key sets from linkml-map v0.3.9. "
            "Check results may be slightly stale if the model has changed.",
            file=sys.stderr,
        )
        return _TS_FROZEN, _CD_FROZEN, _SD_FROZEN


# Populated lazily in main() so --help works without linkml_map installed.
VALID_TRANSFORMATION_SPEC_KEYS: frozenset = frozenset()
VALID_CLASS_DERIVATION_KEYS: frozenset = frozenset()
VALID_SLOT_DERIVATION_KEYS: frozenset = frozenset()

# CURIE prefix -> (compiled regex for identifier part, human description)
CURIE_RULES: dict[str, tuple[re.Pattern, str]] = {
    "OMOP":  (re.compile(r"^\d{4,9}$"), "numeric, 4-9 digits"),
    "OBA":   (re.compile(r"^(\d{7}|VT\d{7})$"), "7 digits, or VT followed by 7 digits"),
    "MONDO": (re.compile(r"^\d{7}$"),   "exactly 7 digits"),
    "HP":    (re.compile(r"^\d{7}$"),   "exactly 7 digits"),
    "NCIT":  (re.compile(r"^C\d+$"),    "C followed by digits"),
    "LOINC": (re.compile(r"^\d+-\d$"),  "digits-dash-digit"),
    "RxCUI": (re.compile(r"^\d{3,8}$"), "numeric, 3-8 digits"),
}

# Precompiled regexes for CURIE extraction
_CURIE_PREFIX_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_]*:')
_CURIE_IN_EXPR_RE = re.compile(r"['\"]([A-Za-z][A-Za-z0-9_]*:\S+?)['\"]")

# Severity ranking for --fail-on filtering
SEVERITY_RANK = {"CRITICAL": 5, "ERROR": 4, "HIGH": 3, "WARNING": 2, "INFO": 1}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    file: str
    block: int
    check: str       # e.g., "2.1"
    severity: str    # CRITICAL, ERROR, HIGH, WARNING, INFO
    message: str

    def terminal_line(self) -> str:
        sev = self.severity[:5].ljust(5)
        return f"  {sev}  block {self.block:>3}  [{self.check}] {self.message}"

    def gh_annotation(self) -> str:
        level = {
            "CRITICAL": "error", "ERROR": "error", "HIGH": "warning",
            "WARNING": "warning", "INFO": "notice",
        }.get(self.severity, "notice")
        file_esc = (self.file.replace("%", "%25").replace("\r", "%0D")
                    .replace("\n", "%0A").replace(":", "%3A").replace(",", "%2C"))
        msg_esc = self.message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        return f"::{level} file={file_esc}::HV-Lint [{self.check}] {msg_esc} (block {self.block})"


@dataclass
class ValidationContext:
    valid_classes: set[str] = field(default_factory=set)
    class_slots: dict[str, set[str]] = field(default_factory=dict)
    required_slots: dict[str, set[str]] = field(default_factory=dict)
    recommended_slots: dict[str, set[str]] = field(default_factory=dict)
    # Check 2.5b: slot range -> expected nested class (including ancestors)
    slot_ranges: dict[str, dict[str, str]] = field(default_factory=dict)  # {class: {slot: range_class}}
    class_ancestors: dict[str, set[str]] = field(default_factory=dict)  # {class: {self, parent, ...}}
    # Check 2.7: {class: {slot: frozenset(valid_enum_values)}} -- only static enums
    slot_enum_values: dict[str, dict[str, frozenset[str]]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Schema loading
# ---------------------------------------------------------------------------

def load_bdchm_schema(bdchm_ref: str, bdchm_schema: str | None) -> ValidationContext:
    """Load BDCHM schema and extract validation context."""
    from linkml_runtime.utils.schemaview import SchemaView

    if bdchm_schema:
        print(f"Loading BDCHM schema from local file: {bdchm_schema}")
        sv = SchemaView(bdchm_schema)
    else:
        url = BDCHM_URL_TEMPLATE.format(ref=bdchm_ref)
        print(f"Loading BDCHM schema from: {url}")
        sv = SchemaView(url)

    ctx = ValidationContext()
    ctx.valid_classes = set(sv.all_classes().keys())

    for cls_name in ctx.valid_classes:
        slots = sv.class_induced_slots(cls_name)
        ctx.class_slots[cls_name] = {s.name for s in slots}
        ctx.required_slots[cls_name] = {s.name for s in slots if s.required}
        ctx.recommended_slots[cls_name] = {s.name for s in slots if s.recommended}
        # Check 2.5b: collect slot ranges that point to classes
        ctx.slot_ranges[cls_name] = {
            s.name: s.range for s in slots
            if s.range in ctx.valid_classes
        }
        # Class ancestry (self + all ancestors) for subclass checking
        ctx.class_ancestors[cls_name] = set(sv.class_ancestors(cls_name)) | {cls_name}

    # Check 2.7: resolve enum permissible values for static enums
    all_enums = sv.all_enums()
    enum_pvs: dict[str, frozenset[str] | None] = {}  # None = dynamic (skip)

    def _resolve_enum_pvs(enum_name: str) -> frozenset[str] | None:
        """Recursively resolve an enum's permissible values.

        Returns None if the enum (or any ancestor) has reachable_from
        (dynamic, cannot be validated locally).  Includes both PV key
        names and their ``meaning`` CURIEs (if present) so that YAML
        files using either form are accepted.
        """
        if enum_name in enum_pvs:
            return enum_pvs[enum_name]
        edef = all_enums.get(enum_name)
        if edef is None:
            enum_pvs[enum_name] = None
            return None
        # Dynamic enums cannot be validated locally
        if getattr(edef, "reachable_from", None):
            enum_pvs[enum_name] = None
            return None
        values: set[str] = set()
        if edef.permissible_values:
            values.update(edef.permissible_values.keys())
            # Also accept the meaning CURIE as a valid value
            for pv in edef.permissible_values.values():
                if getattr(pv, "meaning", None):
                    values.add(pv.meaning)
        # include is a list of AnonymousEnumExpression objects
        if edef.include:
            for inc_expr in edef.include:
                inc_pvs = getattr(inc_expr, "permissible_values", None)
                if isinstance(inc_pvs, dict):
                    values.update(inc_pvs.keys())
                    for pv in inc_pvs.values():
                        if getattr(pv, "meaning", None):
                            values.add(pv.meaning)
        if edef.inherits:
            for parent_name in edef.inherits:
                parent_pvs = _resolve_enum_pvs(parent_name)
                if parent_pvs is None:
                    # Parent is dynamic -> this enum is effectively dynamic
                    enum_pvs[enum_name] = None
                    return None
                values.update(parent_pvs)
        result = frozenset(values) if values else None
        enum_pvs[enum_name] = result
        return result

    enum_names = set(all_enums.keys())
    for enum_name in enum_names:
        _resolve_enum_pvs(enum_name)

    # Map class.slot -> valid enum values (only for static enums with values)
    for cls_name in ctx.valid_classes:
        slots = sv.class_induced_slots(cls_name)
        for s in slots:
            if s.range in enum_names:
                pvs = enum_pvs.get(s.range)
                if pvs is not None:
                    if cls_name not in ctx.slot_enum_values:
                        ctx.slot_enum_values[cls_name] = {}
                    ctx.slot_enum_values[cls_name][s.name] = pvs

    enum_count = sum(1 for v in enum_pvs.values() if v is not None)
    print(f"  Loaded {len(ctx.valid_classes)} classes, {enum_count} validatable enums")
    return ctx


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def find_yaml_files(base_dir: Path, cohort: str) -> list[Path]:
    """Find all *-ingest/*.yaml files, optionally filtered by cohort."""
    files = sorted(
        f for f in base_dir.rglob("*.yaml")
        if any("-ingest" in part for part in f.parts)
        and not f.name.endswith(".swp")
    )
    if cohort.lower() != "all":
        pattern = f"{cohort}-ingest".lower()
        files = [f for f in files if any(part.lower() == pattern for part in f.parts)]
    return files
# ---------------------------------------------------------------------------

def check_top_level_keys(block: dict, block_idx: int, rel_path: str) -> list[Finding]:
    """Validate top-level TransformationSpecification keys."""
    findings = []
    for key in block:
        if key not in VALID_TRANSFORMATION_SPEC_KEYS:
            findings.append(Finding(
                rel_path, block_idx, "2.1", "CRITICAL",
                f"Unknown TransformationSpecification key '{key}'"
            ))
    return findings


def check_class_derivation_keys(
    class_def: dict, class_name: str, block_idx: int,
    rel_path: str, path_prefix: str
) -> list[Finding]:
    """Validate ClassDerivation-level keys."""
    findings = []
    for key in class_def:
        if key not in VALID_CLASS_DERIVATION_KEYS:
            findings.append(Finding(
                rel_path, block_idx, "2.1", "CRITICAL",
                f"Unknown ClassDerivation key '{key}' on {path_prefix}{class_name}"
            ))
    return findings


def check_slot_derivation_keys(
    slot_def: dict, slot_name: str, class_name: str,
    block_idx: int, rel_path: str, path_prefix: str
) -> list[Finding]:
    """Validate SlotDerivation-level keys."""
    findings = []
    for key in slot_def:
        if key not in VALID_SLOT_DERIVATION_KEYS:
            findings.append(Finding(
                rel_path, block_idx, "2.1", "CRITICAL",
                f"Unknown SlotDerivation key '{key}' on "
                f"{path_prefix}{class_name}.{slot_name}"
            ))
    return findings


# ---------------------------------------------------------------------------
# Check 2.6: CURIE format validation
# ---------------------------------------------------------------------------

def check_curie_value(
    value: str, class_name: str, slot_name: str,
    block_idx: int, rel_path: str
) -> list[Finding]:
    """Check 2.6: Validate CURIE format for a static value."""
    findings = []
    if ":" not in value:
        return findings

    # Skip URLs
    if value.startswith("http"):
        return findings

    # Only validate strings that look like CURIEs: PREFIX:identifier
    if not _CURIE_PREFIX_RE.match(value):
        return findings

    parts = value.split(":", 1)
    prefix, identifier = parts[0].strip(), parts[1].strip()

    # Check for leading whitespace after the colon (e.g. "OMOP: 1234")
    if parts[1] != parts[1].lstrip():
        findings.append(Finding(
            rel_path, block_idx, "2.6", "HIGH",
            f"CURIE has space after colon: '{value}' on {class_name}.{slot_name}"
        ))
        return findings  # Don't double-report format issues

    if value != value.strip() or " " in identifier:
        findings.append(Finding(
            rel_path, block_idx, "2.6", "HIGH",
            f"CURIE has extra whitespace: '{value}' on {class_name}.{slot_name}"
        ))

    if prefix in CURIE_RULES:
        pat, desc = CURIE_RULES[prefix]
        if not pat.match(identifier):
            findings.append(Finding(
                rel_path, block_idx, "2.6", "HIGH",
                f"Invalid {prefix} identifier '{identifier}' "
                f"(expected {desc}): '{value}' on {class_name}.{slot_name}"
            ))

    # Known-bad OMOP identifiers (common copy-paste errors)
    if prefix == "OMOP" and identifier == "380035630":
        findings.append(Finding(
            rel_path, block_idx, "2.6", "HIGH",
            f"Known OMOP typo: 380035630 has extra digit "
            f"(should be 38003563 Hispanic or 38003564 Not Hispanic): "
            f"'{value}' on {class_name}.{slot_name}"
        ))

    return findings


def check_curies_in_expr(
    expr: str, class_name: str, slot_name: str,
    block_idx: int, rel_path: str
) -> list[Finding]:
    """Check 2.6: Extract and validate CURIEs embedded in expressions."""
    findings = []
    for match in _CURIE_IN_EXPR_RE.finditer(expr):
        curie = match.group(1)
        findings.extend(check_curie_value(
            curie, class_name, slot_name, block_idx, rel_path
        ))
    return findings


# ---------------------------------------------------------------------------
# Check 2.7: Enum / Value Set Membership
# ---------------------------------------------------------------------------

# Regex for extracting result strings from case() expressions
_CASE_RESULT_DQ_RE = re.compile(r',\s*"([^"]+)"\s*\)')
_CASE_RESULT_SQ_RE = re.compile(r",\s*'([^']+)'\s*\)")


def check_enum_membership(
    slot_def: dict, class_name: str, slot_name: str,
    valid_pvs: frozenset[str], block_idx: int, rel_path: str,
    path_prefix: str
) -> list[Finding]:
    """Check 2.7: Validate that assigned values are valid enum members.

    Checks three assignment forms:
      1. value: "STATIC_VALUE"
      2. value_mappings: {source_code: "TARGET_VALUE", ...}
      3. expr: "case((..., 'VALUE1'), (..., 'VALUE2'))"
    """
    findings: list[Finding] = []
    fqname = f"{path_prefix}{class_name}.{slot_name}"

    # 1. Static value
    value = slot_def.get("value")
    if isinstance(value, str) and value:
        if value not in valid_pvs:
            findings.append(Finding(
                rel_path, block_idx, "2.7", "ERROR",
                f"Value '{value}' is not a valid member of the enum for "
                f"{fqname} (valid: {_format_pvs(valid_pvs)})"
            ))

    # 2. value_mappings targets
    vm = slot_def.get("value_mappings")
    if isinstance(vm, dict):
        for source_key, target_val in vm.items():
            if not isinstance(target_val, str):
                continue
            if target_val not in valid_pvs:
                findings.append(Finding(
                    rel_path, block_idx, "2.7", "ERROR",
                    f"value_mappings target '{target_val}' "
                    f"(from source '{source_key}') is not a valid member of "
                    f"the enum for {fqname} "
                    f"(valid: {_format_pvs(valid_pvs)})"
                ))

    # 3. Case expression result values
    expr = slot_def.get("expr")
    if isinstance(expr, str) and "case(" in expr:
        case_results = (
            _CASE_RESULT_DQ_RE.findall(expr)
            + _CASE_RESULT_SQ_RE.findall(expr)
        )
        for result_val in case_results:
            # Skip None/null placeholders
            if result_val.lower() in ("none", "null", ""):
                continue
            if result_val not in valid_pvs:
                findings.append(Finding(
                    rel_path, block_idx, "2.7", "WARNING",
                    f"case() result '{result_val}' may not be a valid member "
                    f"of the enum for {fqname} "
                    f"(valid: {_format_pvs(valid_pvs)})"
                ))

    return findings


def _format_pvs(pvs: frozenset[str], max_show: int = 8) -> str:
    """Format permissible values for display, truncating if too many."""
    sorted_pvs = sorted(pvs)
    if len(sorted_pvs) <= max_show:
        return ", ".join(sorted_pvs)
    return ", ".join(sorted_pvs[:max_show]) + f", ... ({len(pvs)} total)"


# ---------------------------------------------------------------------------
# Checks 2.2, 2.3, 2.4, 2.5, 2.6, 2.7 -- recursive class_derivations walk
# ---------------------------------------------------------------------------

def validate_class_derivations(
    class_derivs: dict, block_idx: int, rel_path: str,
    ctx: ValidationContext, path_prefix: str = ""
) -> list[Finding]:
    """Recursively validate class_derivations at any nesting level.

    Covers checks 2.1 (keys), 2.2 (slot names), 2.3 (class names),
    2.4 (required/recommended), 2.5 (object_derivation structure),
    2.6 (CURIEs).

    NOTE: PHV/PHT accession format (Phase 3, check 3.1) and expression
    syntax (Phase 1, check 1.1) are NOT performed here.
    """
    findings: list[Finding] = []

    if not isinstance(class_derivs, dict):
        return findings

    for class_name, class_def in class_derivs.items():
        # -- Check 2.3: BDCHM class name --
        if class_name not in ctx.valid_classes:
            findings.append(Finding(
                rel_path, block_idx, "2.3", "ERROR",
                f"Unknown BDCHM class '{path_prefix}{class_name}'"
            ))

        if not isinstance(class_def, dict):
            continue

        # -- Check 2.1: ClassDerivation keys --
        findings.extend(check_class_derivation_keys(
            class_def, class_name, block_idx, rel_path, path_prefix
        ))

        # -- Slot derivations --
        slot_derivs = class_def.get("slot_derivations")
        if not isinstance(slot_derivs, dict):
            if slot_derivs is not None:
                # Key exists but wrong type -- structural error
                findings.append(Finding(
                    rel_path, block_idx, "2.4", "ERROR",
                    f"{path_prefix}{class_name} slot_derivations is "
                    f"{type(slot_derivs).__name__}, expected mapping"
                ))
            elif class_name in ctx.class_slots:
                # Check 2.4: Missing slot_derivations entirely
                findings.append(Finding(
                    rel_path, block_idx, "2.4", "WARNING",
                    f"{path_prefix}{class_name} has no slot_derivations"
                ))
            # Still check required/recommended slots (all will be missing)
            slot_derivs = {}

        present_slots = set(slot_derivs.keys())

        for slot_name, slot_def in slot_derivs.items():
            # -- Check 2.2: BDCHM slot name --
            if class_name in ctx.class_slots:
                if slot_name not in ctx.class_slots[class_name]:
                    findings.append(Finding(
                        rel_path, block_idx, "2.2", "ERROR",
                        f"Slot '{slot_name}' is not valid for "
                        f"{path_prefix}{class_name}"
                    ))

            if not isinstance(slot_def, dict):
                continue

            # -- Check 2.1: SlotDerivation keys --
            findings.extend(check_slot_derivation_keys(
                slot_def, slot_name, class_name,
                block_idx, rel_path, path_prefix
            ))

            # -- Check 2.6: CURIE format on value --
            value = slot_def.get("value")
            if isinstance(value, str):
                findings.extend(check_curie_value(
                    value, class_name, slot_name, block_idx, rel_path
                ))

            # -- Check 2.6: CURIEs in expr --
            expr = slot_def.get("expr")
            if isinstance(expr, str):
                findings.extend(check_curies_in_expr(
                    expr, class_name, slot_name, block_idx, rel_path
                ))

            # -- Check 2.7: Enum / value set membership --
            valid_pvs = ctx.slot_enum_values.get(
                class_name, {}
            ).get(slot_name)
            if valid_pvs is not None:
                findings.extend(check_enum_membership(
                    slot_def, class_name, slot_name,
                    valid_pvs, block_idx, rel_path, path_prefix
                ))

            # -- Check 2.5: object_derivation structure --
            obj_derivs = slot_def.get("object_derivations")
            if obj_derivs is not None:
                if not isinstance(obj_derivs, list):
                    findings.append(Finding(
                        rel_path, block_idx, "2.5", "ERROR",
                        f"object_derivations must be a list on "
                        f"{path_prefix}{class_name}.{slot_name}"
                    ))
                else:
                    for od_idx, od in enumerate(obj_derivs):
                        if not isinstance(od, dict):
                            findings.append(Finding(
                                rel_path, block_idx, "2.5", "ERROR",
                                f"object_derivation item {od_idx} is not a dict "
                                f"on {path_prefix}{class_name}.{slot_name}"
                            ))
                            continue
                        if "class_derivations" not in od:
                            findings.append(Finding(
                                rel_path, block_idx, "2.5", "ERROR",
                                f"object_derivation item {od_idx} missing "
                                f"'class_derivations' on "
                                f"{path_prefix}{class_name}.{slot_name}"
                            ))
                            continue
                        # -- Check 2.5b: nested class matches slot range --
                        expected_range = ctx.slot_ranges.get(
                            class_name, {}
                        ).get(slot_name)
                        if expected_range:
                            nested_cd = od["class_derivations"]
                            if isinstance(nested_cd, dict):
                                for nested_cls in nested_cd:
                                    # Accept the exact range or any subclass
                                    ancestors = ctx.class_ancestors.get(
                                        nested_cls, set()
                                    )
                                    if expected_range not in ancestors:
                                        findings.append(Finding(
                                            rel_path, block_idx, "2.5b",
                                            "ERROR",
                                            f"Nested class '{nested_cls}' in "
                                            f"{path_prefix}{class_name}."
                                            f"{slot_name} does not match "
                                            f"expected range '{expected_range}'"
                                        ))

                        # Recurse into nested class_derivations
                        nested_path = f"{path_prefix}{class_name}.{slot_name}."
                        findings.extend(validate_class_derivations(
                            od["class_derivations"], block_idx, rel_path,
                            ctx, nested_path
                        ))

            # -- Check 2.5: nested class_derivations structure (list-based) --
            slot_cds = slot_def.get("class_derivations")
            if slot_cds is not None:
                if not isinstance(slot_cds, list):
                    findings.append(Finding(
                        rel_path, block_idx, "2.5", "ERROR",
                        f"class_derivations must be a list on "
                        f"{path_prefix}{class_name}.{slot_name}"
                    ))
                else:
                    nested_path = f"{path_prefix}{class_name}.{slot_name}."
                    for cd_idx, cd in enumerate(slot_cds):
                        if not isinstance(cd, dict):
                            findings.append(Finding(
                                rel_path, block_idx, "2.5", "ERROR",
                                f"class_derivation item {cd_idx} is not a dict "
                                f"on {path_prefix}{class_name}.{slot_name}"
                            ))
                            continue
                        if "name" in cd:
                            nested_cls, nested_spec = cd.get("name"), cd
                        elif len(cd) == 1:
                            # dict-keyed form: `- ClassName: {...}`; a null body
                            # (`- X:`) parses as {X: None}, which would silently
                            # skip recursion below -- coerce to keep parity with
                            # the `- name: X` form
                            nested_cls, nested_spec = next(iter(cd.items()))
                            if not isinstance(nested_spec, dict):
                                nested_spec = {}
                        else:
                            nested_cls, nested_spec = None, cd
                        # -- Check 2.5b: nested class matches slot range --
                        expected_range = ctx.slot_ranges.get(
                            class_name, {}
                        ).get(slot_name)
                        if expected_range and nested_cls:
                            ancestors = ctx.class_ancestors.get(nested_cls, set())
                            if expected_range not in ancestors:
                                findings.append(Finding(
                                    rel_path, block_idx, "2.5b", "ERROR",
                                    f"Nested class '{nested_cls}' in "
                                    f"{path_prefix}{class_name}.{slot_name} does "
                                    f"not match expected range '{expected_range}'"
                                ))
                        # Recurse per entry -- a slot may hold several
                        # derivations of the same class (e.g. multiple
                        # MeasurementObservation under 'observations'), which a
                        # name-keyed dict would collapse.
                        if nested_cls:
                            findings.extend(validate_class_derivations(
                                {nested_cls: nested_spec}, block_idx, rel_path,
                                ctx, nested_path
                            ))

        # -- Check 2.4: Required/recommended slots --
        if class_name in ctx.required_slots:
            for req_slot in ctx.required_slots[class_name]:
                # 'id' is typically auto-generated, skip it
                if req_slot == "id":
                    continue
                if req_slot not in present_slots:
                    findings.append(Finding(
                        rel_path, block_idx, "2.4", "ERROR",
                        f"{path_prefix}{class_name} missing required slot "
                        f"'{req_slot}'"
                    ))
        if class_name in ctx.recommended_slots:
            for rec_slot in ctx.recommended_slots[class_name]:
                if rec_slot not in present_slots:
                    findings.append(Finding(
                        rel_path, block_idx, "2.4", "INFO",
                        f"{path_prefix}{class_name} missing recommended slot "
                        f"'{rec_slot}'"
                    ))

        # -- Check 2.4 ext: Advisory age_at_observation on MeasurementObservation --
        # age_at_observation is optional (not required or recommended in
        # bdchm schema) but its absence is a completeness gap worth noting.
        if (class_name == "MeasurementObservation"
                and not path_prefix
                and "age_at_observation" not in present_slots):
            findings.append(Finding(
                rel_path, block_idx, "2.4", "INFO",
                f"{path_prefix}{class_name} missing age_at_observation "
                f"(optional but recommended for completeness)"
            ))

        # -- Check 2.10: Unconditional age_at_condition_start on binary Condition --
        if class_name == "Condition" and not path_prefix:
            age_slot = slot_derivs.get("age_at_condition_start") if slot_derivs else None
            cs_slot = slot_derivs.get("condition_status") if slot_derivs else None
            if isinstance(age_slot, dict) and isinstance(cs_slot, dict):
                cs_vm = cs_slot.get("value_mappings")
                has_absent = False
                if isinstance(cs_vm, dict):
                    has_absent = any(
                        v in ("ABSENT", "Condition.ABSENT")
                        for v in cs_vm.values()
                    )
                if has_absent:
                    # Block maps both PRESENT and ABSENT -- age should be guarded
                    age_expr = age_slot.get("expr", "")
                    age_pf = age_slot.get("populated_from", "")
                    age_source = age_expr or age_pf
                    if age_source and "case(" not in str(age_source):
                        findings.append(Finding(
                            rel_path, block_idx, "2.10", "WARNING",
                            f"{path_prefix}Condition.age_at_condition_start "
                            f"is unconditional but condition_status maps "
                            f"ABSENT rows -- age should use case() to return "
                            f"None for ABSENT"
                        ))

        # -- Check 2.11: Condition missing ABSENT in condition_status --
        if class_name == "Condition" and not path_prefix:
            cs_slot = slot_derivs.get("condition_status") if slot_derivs else None
            if isinstance(cs_slot, dict):
                cs_vm = cs_slot.get("value_mappings")
                if isinstance(cs_vm, dict) and cs_vm:
                    mapped_targets = set(cs_vm.values())
                    has_present = any(
                        v in ("PRESENT", "Condition.PRESENT",
                              "HISTORICAL", "Condition.HISTORICAL")
                        for v in mapped_targets
                    )
                    has_absent = any(
                        v in ("ABSENT", "Condition.ABSENT")
                        for v in mapped_targets
                    )
                    if has_present and not has_absent:
                        findings.append(Finding(
                            rel_path, block_idx, "2.11", "WARNING",
                            f"{path_prefix}Condition.condition_status maps "
                            f"PRESENT/HISTORICAL but has no ABSENT mapping -- "
                            f"verify that ABSENT rows are handled (possibly "
                            f"in a separate block)"
                        ))

    return findings


# ---------------------------------------------------------------------------
# Check 2.7 extension: Cross-file enum consistency
# ---------------------------------------------------------------------------

# Slots where cross-file consistency matters (different values across files
# indicate an error -- the cohort should use one value everywhere).
_CONSISTENCY_SLOTS = {"relationship_to_participant"}


def _track_enum_values(
    class_derivs: dict, rel_path: str,
    tracker: dict[str, dict[str, set[str]]]
) -> None:
    """Collect static enum values per slot across files for consistency checks."""
    if not isinstance(class_derivs, dict):
        return
    for cls_name, cls_def in class_derivs.items():
        if not isinstance(cls_def, dict):
            continue
        slots = cls_def.get("slot_derivations")
        if not isinstance(slots, dict):
            continue
        for slot_name in _CONSISTENCY_SLOTS:
            slot_def = slots.get(slot_name)
            if not isinstance(slot_def, dict):
                continue
            value = slot_def.get("value")
            if isinstance(value, str) and value:
                if slot_name not in tracker:
                    tracker[slot_name] = {}
                tracker[slot_name].setdefault(rel_path, set()).add(value)


def check_cross_file_enum_consistency(
    tracker: dict[str, dict[str, set[str]]]
) -> list[Finding]:
    """Check 2.7 ext: Flag slots where different enum values are used across files.

    For example, relationship_to_participant should consistently use either
    "SELF" or "ONESELF" across all files in a cohort -- not a mix.
    """
    findings: list[Finding] = []
    for slot_name, file_values in tracker.items():
        all_values: set[str] = set()
        for vals in file_values.values():
            all_values.update(vals)
        if len(all_values) > 1:
            val_summary = ", ".join(
                f"'{v}' in {sum(1 for fv in file_values.values() if v in fv)} file(s)"
                for v in sorted(all_values)
            )
            findings.append(Finding(
                "(cross-file)", 0, "2.7", "WARNING",
                f"Inconsistent '{slot_name}' values across files: {val_summary}"
            ))
    return findings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="HV-Lint Phase 2: BDC-HM model conformance checks"
    )
    p.add_argument(
        "--bdchm-ref", default="main",
        help="Git ref (branch/tag/SHA) for BDCHM schema (default: main)"
    )
    p.add_argument(
        "--bdchm-schema", default=None,
        help="Local path to bdchm.yaml (overrides --bdchm-ref)"
    )
    p.add_argument(
        "--cohort", default="all",
        help="Cohort to validate (e.g., ARIC, CHS) or 'all' (default: all)"
    )
    p.add_argument(
        "--file", default=None,
        help="Validate a single file instead of scanning directories"
    )
    p.add_argument(
        "--fail-on", default="error",
        choices=["critical", "error", "high", "warning", "info"],
        help="Minimum severity to cause non-zero exit (default: error)"
    )
    p.add_argument(
        "--summary-file", default=None,
        help="Write a Markdown summary table to this file"
    )
    p.add_argument(
        "--summary-limit", type=int, default=50,
        help="Max findings to include in the Markdown summary (default: 50)"
    )
    return p.parse_args()


def main() -> int:
    global VALID_TRANSFORMATION_SPEC_KEYS, VALID_CLASS_DERIVATION_KEYS, VALID_SLOT_DERIVATION_KEYS
    args = parse_args()
    in_ci = os.environ.get("GITHUB_ACTIONS") == "true"

    # Derive valid linkml-map keys (deferred so --help works without linkml_map).
    # _derive_valid_keys() handles its own fallback -- it never raises.
    VALID_TRANSFORMATION_SPEC_KEYS, VALID_CLASS_DERIVATION_KEYS, VALID_SLOT_DERIVATION_KEYS = _derive_valid_keys()

    # Load BDCHM schema
    try:
        ctx = load_bdchm_schema(args.bdchm_ref, args.bdchm_schema)
    except Exception as e:
        print(f"ERROR: Failed to load BDCHM schema: {e}", file=sys.stderr)
        return 1

    # Discover YAML files
    if args.file:
        yaml_files = [Path(args.file)]
        if not yaml_files[0].exists():
            print(f"File not found: {args.file}", file=sys.stderr)
            return 1
    else:
        base_dir = TRANSFORM_DIR
        if not base_dir.exists():
            print(f"HV repo transform directory not found: {base_dir}", file=sys.stderr)
            return 1
        yaml_files = find_yaml_files(base_dir, args.cohort)

    if not yaml_files:
        print("No YAML files found to validate")
        return 1
    print(f"Found {len(yaml_files)} YAML files to validate")

    # Run checks
    all_findings: list[Finding] = []
    files_checked = 0
    blocks_checked = 0
    # Cross-file tracking for 2.7 consistency checks
    enum_value_tracker: dict[str, dict[str, set[str]]] = {}  # {slot_name: {file: {values}}}

    for file_path in yaml_files:
        rel_path = file_path.as_posix()

        # Load YAML
        try:
            with file_path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except (OSError, yaml.YAMLError) as e:
            all_findings.append(Finding(
                rel_path, 0, "2.0", "ERROR", f"Failed to parse YAML: {e}"
            ))
            continue

        if data is None:
            all_findings.append(Finding(
                rel_path, 0, "2.0", "WARNING", "Empty file"
            ))
            continue

        blocks = data if isinstance(data, list) else [data]
        files_checked += 1

        # Per-block checks
        for idx, block in enumerate(blocks):
            blocks_checked += 1
            if not isinstance(block, dict):
                all_findings.append(Finding(
                    rel_path, idx, "2.0", "ERROR", "Block is not a YAML mapping"
                ))
                continue

            # 2.1: Top-level TransformationSpecification keys
            all_findings.extend(check_top_level_keys(block, idx, rel_path))

            # 2.2-2.6: Class derivation walk (slot names, class names,
            # required/recommended, object derivation, CURIEs)
            class_derivs = block.get("class_derivations")
            if isinstance(class_derivs, dict):
                all_findings.extend(validate_class_derivations(
                    class_derivs, idx, rel_path, ctx
                ))
                # Track enum slot values for cross-file consistency (2.7 ext)
                _track_enum_values(class_derivs, rel_path, enum_value_tracker)

    # Cross-file consistency checks (2.7 extension)
    all_findings.extend(check_cross_file_enum_consistency(enum_value_tracker))

    # -----------------------------------------------------------------------
    # Report
    # -----------------------------------------------------------------------
    fail_rank = SEVERITY_RANK[args.fail_on.upper()]

    counts: dict[str, int] = {}
    for f in all_findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1

    findings_by_file: dict[str, list[Finding]] = {}
    for f in all_findings:
        findings_by_file.setdefault(f.file, []).append(f)

    print(f"\n{'='*70}")
    print("HV-Lint Phase 2: BDC-HM Model Conformance Results")
    print(f"{'='*70}")
    print(f"Files checked:  {files_checked}")
    print(f"Blocks checked: {blocks_checked}")

    parts = []
    for sev in ("CRITICAL", "ERROR", "HIGH", "WARNING", "INFO"):
        if counts.get(sev, 0) > 0:
            parts.append(f"{counts[sev]} {sev}")
    if parts:
        print(f"Findings:       {', '.join(parts)}")
    else:
        print("Findings:       None -- all checks passed!")

    if findings_by_file:
        print(f"\n{'-'*70}")
        for fpath in sorted(findings_by_file):
            short = fpath.replace("priority_variables_transform/", "")
            if "priority_variables_transform" in short:
                short = short[short.index("priority_variables_transform") + len("priority_variables_transform/"):]
            print(f"\n{short}:")
            for f in sorted(findings_by_file[fpath],
                            key=lambda x: (x.block, x.check)):
                print(f.terminal_line())
                if in_ci:
                    print(f.gh_annotation())

    # Write Markdown summary
    if args.summary_file:
        _write_summary(args.summary_file, files_checked, blocks_checked,
                       counts, all_findings, args.summary_limit)

    # Determine exit code
    blocking = [
        f for f in all_findings
        if SEVERITY_RANK.get(f.severity, 0) >= fail_rank
    ]
    if blocking:
        print(f"\n{'='*70}")
        print(f"FAILED: {len(blocking)} findings at or above '{args.fail_on}' severity")
        return 1
    else:
        if all_findings:
            print(f"\n{'='*70}")
            print(f"PASSED (with {len(all_findings)} advisory findings below fail threshold)")
        return 0


def _write_summary(path: str, files: int, blocks: int,
                   counts: dict[str, int], findings: list[Finding],
                   limit: int) -> None:
    """Write a Markdown summary table for GITHUB_STEP_SUMMARY."""
    lines: list[str] = []
    lines.append("## HV-Lint Phase 2: BDC-HM Model Conformance Results\n")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Files checked | {files} |")
    lines.append(f"| Blocks checked | {blocks} |")
    for sev in ("CRITICAL", "ERROR", "HIGH", "WARNING", "INFO"):
        if counts.get(sev, 0) > 0:
            lines.append(f"| {sev} | {counts[sev]} |")
    lines.append("")
    if findings:
        sorted_findings = sorted(
            findings,
            key=lambda f: (-SEVERITY_RANK.get(f.severity, 0),
                           f.file, f.block, f.check)
        )
        shown = sorted_findings[:limit]
        lines.append(f"### Findings (showing {len(shown)} of {len(findings)})\n")
        lines.append("| Severity | File | Block | Check | Message |")
        lines.append("|----------|------|-------|-------|---------|")
        for f in shown:
            short = f.file.replace("priority_variables_transform/", "")
            msg = (f.message.replace("\r", " ").replace("\n", " ")
                   .replace("|", "\\|"))
            lines.append(f"| {f.severity} | {short} | {f.block} | {f.check} | {msg} |")
        if len(findings) > limit:
            lines.append(
                f"\n> **{len(findings) - limit} additional findings omitted.** "
                f"Re-run with a higher `summary_limit` or check the raw log."
            )
    else:
        lines.append("All checks passed!\n")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
