#!/usr/bin/env python3
"""HV-Lint Phase 1: Schema-driven structural quality checks for HV YAML files.

Validates transformation YAML files against the linkml-map transformer model
and the BDCHM LinkML schema. No dbGaP metadata required.

Usage:
    python hv-lint/validate_yaml_quality.py
    python hv-lint/validate_yaml_quality.py --bdchm-ref v1.2.0 --cohort ARIC
    python hv-lint/validate_yaml_quality.py --bdchm-schema path/to/bdchm.yaml

Checks implemented:
    1.1  LinkML-Map key validation (unknown keys at any nesting level)
    1.2  BDCHM slot name validation (per-class)
    1.3  BDCHM class name validation
    1.4  Required/recommended slot enforcement (schema-driven)
    1.5  Object derivation structure validation
    1.6  CURIE format validation
    1.7  PHV/PHT accession format validation
    1.9  Expression syntax validation (balanced braces, non-empty)
    1.10 Duplicate block detection (same class + pht + concept)
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
# Constants
# ---------------------------------------------------------------------------

BDCHM_URL_TEMPLATE = (
    "https://raw.githubusercontent.com/RTIInternational/"
    "NHLBI-BDC-DMC-HM/{ref}/src/bdchm/schema/bdchm.yaml"
)

# Valid keys for each linkml-map model level, derived at runtime
# from the installed linkml_map.datamodel.transformer_model Pydantic classes.
# HV-specific extensions (not in the base model) are added explicitly.
def _derive_valid_keys():
    from linkml_map.datamodel.transformer_model import (
        TransformationSpecification, ClassDerivation, SlotDerivation,
    )
    ts_keys = frozenset(TransformationSpecification.model_fields.keys())
    cd_keys = frozenset(ClassDerivation.model_fields.keys())
    sd_keys = frozenset(SlotDerivation.model_fields.keys()) | {
        # Extensions used in HV YAML files (not in base linkml-map model):
        "value",               # Static value assignment
        "object_derivations",  # Nested object structure (e.g., Quantity)
    }
    return ts_keys, cd_keys, sd_keys


# Populated lazily in main() so --help works without linkml_map installed.
VALID_TRANSFORMATION_SPEC_KEYS: frozenset = frozenset()
VALID_CLASS_DERIVATION_KEYS: frozenset = frozenset()
VALID_SLOT_DERIVATION_KEYS: frozenset = frozenset()

# CURIE prefix → (compiled regex for identifier part, human description)
CURIE_RULES: dict[str, tuple[re.Pattern, str]] = {
    "OMOP":  (re.compile(r"^\d{5,9}$"), "numeric, 5-9 digits"),
    "OBA":   (re.compile(r"^\d{7}$"),   "exactly 7 digits"),
    "MONDO": (re.compile(r"^\d{7}$"),   "exactly 7 digits"),
    "HP":    (re.compile(r"^\d{7}$"),   "exactly 7 digits"),
    "NCIT":  (re.compile(r"^C\d+$"),    "C followed by digits"),
    "LOINC": (re.compile(r"^\d+-\d$"),  "digits-dash-digit"),
    "RxCUI": (re.compile(r"^\d+$"),     "numeric only"),
}

# Precompiled regexes used in CURIE / expression checks
_CURIE_PREFIX_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_]*:')
_CURIE_IN_EXPR_RE = re.compile(r"['\"]([A-Za-z][A-Za-z0-9_]*:\S+?)['\"]")
_EMPTY_VAR_REF_RE = re.compile(r"\{\{\s*\}\}")
_PHT_FORMAT_RE = re.compile(r"^pht\d{6}$")
_PHV_FORMAT_RE = re.compile(r"^phv\d{8}$")

# Files to skip entirely (same pattern as validate_ingest_yamls.py).
KNOWN_ISSUES: dict[str, str] = {
    "priority_variables_transform/FHS-ingest/il18.yaml":
        "empty file (entirely commented out)",
    "priority_variables_transform/FHS-ingest/pr_qrs_qt.yaml":
        "MeasurementObservationSet nesting not in linkml-map schema",
    "priority_variables_transform/FHS-ingest/_manifest-fhs.yaml":
        "version tracking manifest, not a transformation spec",
}

# Severity ranking for --fail-on filtering
SEVERITY_RANK = {"CRITICAL": 5, "ERROR": 4, "HIGH": 3, "WARNING": 2, "INFO": 1}

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    file: str
    block: int
    check: str       # e.g., "1.2"
    severity: str    # CRITICAL, ERROR, WARNING, INFO
    message: str

    @staticmethod
    def _esc_prop(text: str) -> str:
        """Escape a workflow-command *property* value (file=, line=, …)."""
        return (text.replace("%", "%25").replace("\r", "%0D")
                .replace("\n", "%0A").replace(":", "%3A").replace(",", "%2C"))

    @staticmethod
    def _esc_msg(text: str) -> str:
        """Escape a workflow-command *message* (colons/commas stay readable)."""
        return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")

    def gh_annotation(self) -> str:
        level = {
            "CRITICAL": "error", "ERROR": "error", "HIGH": "warning",
            "WARNING": "warning", "INFO": "notice",
        }.get(self.severity, "notice")
        return f"::{level} file={self._esc_prop(self.file)}::HV-Lint [{self.check}] {self._esc_msg(self.message)} (block {self.block})"

    def terminal_line(self) -> str:
        sev = self.severity[:5].ljust(5)
        return f"  {sev}  block {self.block:>3}  [{self.check}] {self.message}"


@dataclass
class ValidationContext:
    valid_classes: set[str] = field(default_factory=set)
    class_slots: dict[str, set[str]] = field(default_factory=dict)
    required_slots: dict[str, set[str]] = field(default_factory=dict)
    recommended_slots: dict[str, set[str]] = field(default_factory=dict)

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

    print(f"  Loaded {len(ctx.valid_classes)} classes")
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
        files = [f for f in files if pattern in str(f).lower()]
    return files


# ---------------------------------------------------------------------------
# Check 1.1: LinkML-Map key validation
# ---------------------------------------------------------------------------

def check_top_level_keys(block: dict, block_idx: int, rel_path: str) -> list[Finding]:
    """Validate top-level TransformationSpecification keys."""
    findings = []
    for key in block:
        if key not in VALID_TRANSFORMATION_SPEC_KEYS:
            findings.append(Finding(
                rel_path, block_idx, "1.1", "CRITICAL",
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
                rel_path, block_idx, "1.1", "CRITICAL",
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
                rel_path, block_idx, "1.1", "CRITICAL",
                f"Unknown SlotDerivation key '{key}' on "
                f"{path_prefix}{class_name}.{slot_name}"
            ))
    return findings

# ---------------------------------------------------------------------------
# Checks 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.9 — recursive class_derivations
# ---------------------------------------------------------------------------

def check_curie_value(
    value: str, class_name: str, slot_name: str,
    block_idx: int, rel_path: str
) -> list[Finding]:
    """Check 1.6: Validate CURIE format for a static value."""
    findings = []
    if ":" not in value:
        return findings

    # Skip URLs
    if value.startswith("http"):
        return findings

    # Only validate strings that look like CURIEs: PREFIX:identifier
    # Allow space after colon so the whitespace check below can catch it.
    if not _CURIE_PREFIX_RE.match(value):
        return findings

    parts = value.split(":", 1)
    prefix, identifier = parts[0].strip(), parts[1].strip()

    # Check for leading whitespace after the colon (e.g. "OMOP: 1234")
    if parts[1] != parts[1].lstrip():
        findings.append(Finding(
            rel_path, block_idx, "1.6", "HIGH",
            f"CURIE has space after colon: '{value}' on {class_name}.{slot_name}"
        ))
        return findings  # Don't double-report format issues

    if value != value.strip() or " " in identifier:
        findings.append(Finding(
            rel_path, block_idx, "1.6", "HIGH",
            f"CURIE has extra whitespace: '{value}' on {class_name}.{slot_name}"
        ))

    if prefix in CURIE_RULES:
        pat, desc = CURIE_RULES[prefix]
        if not pat.match(identifier):
            findings.append(Finding(
                rel_path, block_idx, "1.6", "HIGH",
                f"Invalid {prefix} identifier '{identifier}' "
                f"(expected {desc}): '{value}' on {class_name}.{slot_name}"
            ))
    return findings


def check_curies_in_expr(
    expr: str, class_name: str, slot_name: str,
    block_idx: int, rel_path: str
) -> list[Finding]:
    """Check 1.6: Extract and validate CURIEs embedded in expressions."""
    findings = []
    # Match quoted CURIE-like values in expressions: 'PREFIX:ID' or "PREFIX:ID"
    for match in _CURIE_IN_EXPR_RE.finditer(expr):
        curie = match.group(1)
        findings.extend(check_curie_value(
            curie, class_name, slot_name, block_idx, rel_path
        ))
    return findings


def check_expression_syntax(
    expr: str, class_name: str, slot_name: str,
    block_idx: int, rel_path: str
) -> list[Finding]:
    """Check 1.9: Basic expression syntax validation."""
    findings = []

    # Balanced Jinja braces
    if expr.count("{%") != expr.count("%}"):
        findings.append(Finding(
            rel_path, block_idx, "1.9", "ERROR",
            f"Unbalanced {{% %}} in expr on {class_name}.{slot_name}"
        ))
    if expr.count("{{") != expr.count("}}"):
        findings.append(Finding(
            rel_path, block_idx, "1.9", "ERROR",
            f"Unbalanced {{{{ }}}} in expr on {class_name}.{slot_name}"
        ))

    # Empty expression
    if not expr.strip():
        findings.append(Finding(
            rel_path, block_idx, "1.9", "ERROR",
            f"Empty expr on {class_name}.{slot_name}"
        ))

    # Empty variable references: {{ }}
    if _EMPTY_VAR_REF_RE.search(expr):
        findings.append(Finding(
            rel_path, block_idx, "1.9", "WARNING",
            f"Empty variable reference '{{{{ }}}}' in expr on {class_name}.{slot_name}"
        ))

    return findings


def validate_class_derivations(
    class_derivs: dict, block_idx: int, rel_path: str,
    ctx: ValidationContext, path_prefix: str = ""
) -> list[Finding]:
    """Recursively validate class_derivations at any nesting level.

    Covers checks 1.1 (keys), 1.2 (slot names), 1.3 (class names),
    1.4 (required/recommended), 1.5 (object_derivation structure),
    1.6 (CURIEs), 1.7 (accession format), 1.9 (expression syntax).
    """
    findings: list[Finding] = []

    if not isinstance(class_derivs, dict):
        return findings

    for class_name, class_def in class_derivs.items():
        # -- Check 1.3: BDCHM class name --
        if class_name not in ctx.valid_classes:
            findings.append(Finding(
                rel_path, block_idx, "1.3", "ERROR",
                f"Unknown BDCHM class '{path_prefix}{class_name}'"
            ))

        if not isinstance(class_def, dict):
            continue

        # -- Check 1.1: ClassDerivation keys --
        findings.extend(check_class_derivation_keys(
            class_def, class_name, block_idx, rel_path, path_prefix
        ))

        # -- Check 1.7: PHT accession format --
        pht = class_def.get("populated_from")
        if pht is not None and not isinstance(pht, str):
            findings.append(Finding(
                rel_path, block_idx, "1.7", "ERROR",
                f"populated_from on {path_prefix}{class_name} is not a string "
                f"(got {type(pht).__name__})"
            ))
        elif isinstance(pht, str) and pht.startswith("pht"):
            if not _PHT_FORMAT_RE.match(pht):
                findings.append(Finding(
                    rel_path, block_idx, "1.7", "ERROR",
                    f"Invalid PHT format '{pht}' on {path_prefix}{class_name} "
                    f"(expected pht + 6 digits)"
                ))

        # -- Slot derivations --
        slot_derivs = class_def.get("slot_derivations")
        if not isinstance(slot_derivs, dict):
            # Check 1.4: Missing slot_derivations entirely
            if class_name in ctx.class_slots:
                findings.append(Finding(
                    rel_path, block_idx, "1.4", "WARNING",
                    f"{path_prefix}{class_name} has no slot_derivations"
                ))
            # Still check required/recommended slots (all will be missing)
            slot_derivs = {}

        present_slots = set(slot_derivs.keys())

        for slot_name, slot_def in slot_derivs.items():
            # -- Check 1.2: BDCHM slot name --
            if class_name in ctx.class_slots:
                if slot_name not in ctx.class_slots[class_name]:
                    findings.append(Finding(
                        rel_path, block_idx, "1.2", "ERROR",
                        f"Slot '{slot_name}' is not valid for "
                        f"{path_prefix}{class_name}"
                    ))

            if not isinstance(slot_def, dict):
                continue

            # -- Check 1.1: SlotDerivation keys --
            findings.extend(check_slot_derivation_keys(
                slot_def, slot_name, class_name,
                block_idx, rel_path, path_prefix
            ))

            # -- Check 1.6: CURIE format on value --
            value = slot_def.get("value")
            if isinstance(value, str):
                findings.extend(check_curie_value(
                    value, class_name, slot_name, block_idx, rel_path
                ))

            # -- Check 1.6: CURIEs in expr --
            expr = slot_def.get("expr")
            if isinstance(expr, str):
                findings.extend(check_curies_in_expr(
                    expr, class_name, slot_name, block_idx, rel_path
                ))
                # -- Check 1.9: Expression syntax --
                findings.extend(check_expression_syntax(
                    expr, class_name, slot_name, block_idx, rel_path
                ))

            # -- Check 1.7: PHV accession format on populated_from --
            pf = slot_def.get("populated_from")
            if pf is not None and not isinstance(pf, str):
                findings.append(Finding(
                    rel_path, block_idx, "1.7", "ERROR",
                    f"populated_from on {path_prefix}{class_name}.{slot_name} "
                    f"is not a string (got {type(pf).__name__})"
                ))
            elif isinstance(pf, str) and pf.startswith("phv"):
                if not _PHV_FORMAT_RE.match(pf):
                    findings.append(Finding(
                        rel_path, block_idx, "1.7", "ERROR",
                        f"Invalid PHV format '{pf}' on "
                        f"{path_prefix}{class_name}.{slot_name} "
                        f"(expected phv + 8 digits)"
                    ))

            # -- Check 1.5: object_derivation structure --
            obj_derivs = slot_def.get("object_derivations")
            if obj_derivs is not None:
                if not isinstance(obj_derivs, list):
                    findings.append(Finding(
                        rel_path, block_idx, "1.5", "ERROR",
                        f"object_derivations must be a list on "
                        f"{path_prefix}{class_name}.{slot_name}"
                    ))
                else:
                    for od_idx, od in enumerate(obj_derivs):
                        if not isinstance(od, dict):
                            findings.append(Finding(
                                rel_path, block_idx, "1.5", "ERROR",
                                f"object_derivation item {od_idx} is not a dict "
                                f"on {path_prefix}{class_name}.{slot_name}"
                            ))
                            continue
                        if "class_derivations" not in od:
                            findings.append(Finding(
                                rel_path, block_idx, "1.5", "ERROR",
                                f"object_derivation item {od_idx} missing "
                                f"'class_derivations' on "
                                f"{path_prefix}{class_name}.{slot_name}"
                            ))
                            continue
                        # Validate keys in the object_derivation item
                        # (Only check for class_derivations — OD items don't
                        #  have a formal key set in the linkml-map model.)
                        # Recurse
                        nested_path = f"{path_prefix}{class_name}.{slot_name}."
                        findings.extend(validate_class_derivations(
                            od["class_derivations"], block_idx, rel_path,
                            ctx, nested_path
                        ))

        # -- Check 1.4: Required/recommended slots --
        if class_name in ctx.required_slots:
            for req_slot in ctx.required_slots[class_name]:
                # 'id' is typically auto-generated, skip it
                if req_slot == "id":
                    continue
                if req_slot not in present_slots:
                    findings.append(Finding(
                        rel_path, block_idx, "1.4", "ERROR",
                        f"{path_prefix}{class_name} missing required slot "
                        f"'{req_slot}'"
                    ))
        if class_name in ctx.recommended_slots:
            for rec_slot in ctx.recommended_slots[class_name]:
                if rec_slot not in present_slots:
                    findings.append(Finding(
                        rel_path, block_idx, "1.4", "INFO",
                        f"{path_prefix}{class_name} missing recommended slot "
                        f"'{rec_slot}'"
                    ))

    return findings

# ---------------------------------------------------------------------------
# Check 1.10: Duplicate block detection
# ---------------------------------------------------------------------------

def get_block_identity(block: dict) -> list[tuple]:
    """Extract distinguishing identity for each class in a block.

    Identity tuple: (class, pht, visit, concept, distinguishing_phv)
    where distinguishing_phv captures the data-bearing variable that makes
    blocks with the same class/pht/visit/concept actually distinct.
    """
    if not isinstance(block, dict):
        return []
    identities = []
    class_derivs = block.get("class_derivations")
    if not isinstance(class_derivs, dict):
        return identities

    def _d(val) -> dict:
        """Return val if it's a dict, else empty dict (guard non-dict truthy values)."""
        return val if isinstance(val, dict) else {}

    def _s(val, maxlen: int = 0) -> str:
        """Coerce val to str, optionally truncate (guard non-string YAML values)."""
        t = val if isinstance(val, str) else str(val) if val else ""
        return t[:maxlen] if maxlen else t

    for cls_name, cls_def in class_derivs.items():
        if not isinstance(cls_def, dict):
            continue
        pht = cls_def.get("populated_from", "")
        slots = cls_def.get("slot_derivations")
        slots = slots if isinstance(slots, dict) else {}

        av = _d(slots.get("associated_visit"))
        visit = _s(av.get("value", "")) or _s(av.get("populated_from", "")) or _s(av.get("expr", ""), 60)

        concept = ""
        distinguishing_phv = ""

        if cls_name == "Condition":
            cc = _d(slots.get("condition_concept"))
            concept = _s(cc.get("value", "")) or _s(cc.get("populated_from", "")) or _s(cc.get("expr", ""), 60)
            cs = _d(slots.get("condition_status"))
            distinguishing_phv = _s(cs.get("populated_from", "")) or _s(cs.get("expr", ""), 60)
        elif cls_name in ("MeasurementObservation", "Observation", "SdohObservation"):
            concept = _d(slots.get("observation_type")).get("value", "")
            # Use the value_quantity PHV as distinguishing
            vq = _d(slots.get("value_quantity"))
            for od in (vq.get("object_derivations") or []):
                if isinstance(od, dict):
                    qty = _d(_d(od.get("class_derivations")).get("Quantity"))
                    qty_slots = _d(qty.get("slot_derivations"))
                    vd = _d(qty_slots.get("value_decimal") or qty_slots.get("value_integer"))
                    distinguishing_phv = _s(vd.get("populated_from", "")) or _s(vd.get("expr", ""), 60)
                    break
        elif cls_name == "DrugExposure":
            dc = _d(slots.get("drug_concept"))
            concept = _s(dc.get("value", "")) or _s(dc.get("expr", ""), 80)
        elif cls_name == "Visit":
            concept = _s(_d(slots.get("id")).get("expr", ""), 80)
        elif cls_name == "Demography":
            # All slots together distinguish Demography blocks
            distinguishing_phv = str(sorted(slots.keys()))

        identities.append((cls_name, str(pht), visit, concept, distinguishing_phv))
    return identities


def check_duplicates(
    blocks: list[dict], rel_path: str
) -> list[Finding]:
    """Check 1.10: Detect duplicate blocks within a single file."""
    findings: list[Finding] = []
    seen: dict[tuple[str, str, str, str, str], int] = {}

    for idx, block in enumerate(blocks):
        for identity in get_block_identity(block):
            if identity in seen:
                cls, pht, visit, concept, _ = identity
                findings.append(Finding(
                    rel_path, idx, "1.10", "ERROR",
                    f"Duplicate block: {cls} with pht={pht} "
                    f"visit='{visit}' concept='{concept}' "
                    f"(first seen in block {seen[identity]})"
                ))
            else:
                seen[identity] = idx
    return findings

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="HV-Lint Phase 1: Schema-driven structural quality checks"
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
        "--fail-on", default="error",
        choices=["critical", "error", "high", "warning", "info"],
        help="Minimum severity to cause non-zero exit (default: error)"
    )
    p.add_argument(
        "--summary-file", default=None,
        help="Write a Markdown summary table to this file (for GITHUB_STEP_SUMMARY)"
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

    # Derive valid linkml-map keys (deferred so --help works without linkml_map)
    try:
        VALID_TRANSFORMATION_SPEC_KEYS, VALID_CLASS_DERIVATION_KEYS, VALID_SLOT_DERIVATION_KEYS = _derive_valid_keys()
    except (ImportError, AttributeError) as e:
        print(f"ERROR: linkml_map is not installed or incompatible: {e}", file=sys.stderr)
        print("Install/upgrade with: pip install linkml-map", file=sys.stderr)
        return 1

    # Load BDCHM schema
    try:
        ctx = load_bdchm_schema(args.bdchm_ref, args.bdchm_schema)
    except Exception as e:
        print(f"ERROR: Failed to load BDCHM schema: {e}", file=sys.stderr)
        return 1

    # Discover YAML files
    base_dir = Path("priority_variables_transform")
    yaml_files = find_yaml_files(base_dir, args.cohort)
    if not yaml_files:
        print(f"No YAML files found under {base_dir}")
        return 1
    print(f"Found {len(yaml_files)} YAML files to validate")

    # Run checks
    all_findings: list[Finding] = []
    files_checked = 0
    blocks_checked = 0
    skipped = []

    for file_path in yaml_files:
        rel_path = file_path.as_posix()

        # Skip known issues
        if rel_path in KNOWN_ISSUES:
            skipped.append((rel_path, KNOWN_ISSUES[rel_path]))
            continue

        # Load YAML
        try:
            with file_path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except (OSError, yaml.YAMLError) as e:
            all_findings.append(Finding(
                rel_path, 0, "1.0", "ERROR", f"Failed to parse YAML: {e}"
            ))
            continue

        if data is None:
            all_findings.append(Finding(
                rel_path, 0, "1.0", "WARNING", "Empty file"
            ))
            continue

        blocks = data if isinstance(data, list) else [data]
        files_checked += 1

        # Per-block checks
        for idx, block in enumerate(blocks):
            blocks_checked += 1
            if not isinstance(block, dict):
                all_findings.append(Finding(
                    rel_path, idx, "1.0", "ERROR", "Block is not a YAML mapping"
                ))
                continue

            # 1.1: Top-level keys
            all_findings.extend(check_top_level_keys(block, idx, rel_path))

            # 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.9: class_derivations
            class_derivs = block.get("class_derivations")
            if isinstance(class_derivs, dict):
                all_findings.extend(
                    validate_class_derivations(class_derivs, idx, rel_path, ctx)
                )

        # 1.10: Duplicate blocks within file
        all_findings.extend(check_duplicates(blocks, rel_path))

    # -----------------------------------------------------------------------
    # Report
    # -----------------------------------------------------------------------
    fail_rank = SEVERITY_RANK[args.fail_on.upper()]

    # Tally by severity
    counts: dict[str, int] = {"CRITICAL": 0, "ERROR": 0, "WARNING": 0, "HIGH": 0, "INFO": 0}
    for f in all_findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1

    # Group by file for terminal display
    findings_by_file: dict[str, list[Finding]] = {}
    for f in all_findings:
        findings_by_file.setdefault(f.file, []).append(f)

    print(f"\n{'='*70}")
    print("HV-Lint Phase 1 Results")
    print(f"{'='*70}")
    print(f"Files checked:  {files_checked}")
    print(f"Blocks checked: {blocks_checked}")
    if skipped:
        print(f"Files skipped:  {len(skipped)} (known issues)")

    # Summary line
    parts = []
    for sev in ("CRITICAL", "ERROR", "HIGH", "WARNING", "INFO"):
        if counts.get(sev, 0) > 0:
            parts.append(f"{counts[sev]} {sev}")
    if parts:
        print(f"Findings:       {', '.join(parts)}")
    else:
        print(f"Findings:       None — all checks passed!")

    # Detail output
    if findings_by_file:
        print(f"\n{'-'*70}")
        for fpath in sorted(findings_by_file):
            short = fpath.replace("priority_variables_transform/", "")
            print(f"\n{short}:")
            for f in sorted(findings_by_file[fpath], key=lambda x: (x.block, x.check)):
                print(f.terminal_line())
                if in_ci:
                    print(f.gh_annotation())

    # Write Markdown summary
    if args.summary_file:
        _write_summary(args.summary_file, "Phase 1", files_checked, blocks_checked,
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


def _write_summary(path: str, phase: str, files: int, blocks: int,
                   counts: dict[str, int], findings: list[Finding],
                   limit: int) -> None:
    """Write a Markdown summary table for GITHUB_STEP_SUMMARY."""
    lines: list[str] = []
    lines.append(f"## HV-Lint {phase} Results\n")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Files checked | {files} |")
    lines.append(f"| Blocks checked | {blocks} |")
    for sev in ("CRITICAL", "ERROR", "HIGH", "WARNING", "INFO"):
        if counts.get(sev, 0) > 0:
            lines.append(f"| {sev} | {counts[sev]} |")
    lines.append("")
    if findings:
        sorted_findings = sorted(findings, key=lambda f: SEVERITY_RANK.get(f.severity, 0), reverse=True)
        shown = sorted_findings[:limit]
        lines.append(f"### Findings (showing {len(shown)} of {len(findings)})\n")
        lines.append("| Severity | File | Block | Check | Message |")
        lines.append("|----------|------|-------|-------|---------|")
        for f in shown:
            short = f.file.replace("priority_variables_transform/", "")
            msg = f.message.replace("\r", " ").replace("\n", " ").replace("|", "\\|")
            lines.append(f"| {f.severity} | {short} | {f.block} | {f.check} | {msg} |")
        if len(findings) > limit:
            lines.append(f"\n> **{len(findings) - limit} additional findings omitted.** "
                         f"Re-run with a higher `summary_limit` or check the raw log.")
    else:
        lines.append("All checks passed!\n")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
