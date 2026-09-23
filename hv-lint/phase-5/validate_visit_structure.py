#!/usr/bin/env python3
"""HV-Lint Phase 5: Visit Structure Validation.

Cross-file validation of visit.yaml against all measurement and condition
transform files within each cohort. Builds a per-cohort visit registry
from visit.yaml and validates referential integrity, uniqueness, age
formula structure, multi-visit coverage, and orphan detection.

Checks:
  5.1  Visit ID Uniqueness -- no duplicate visit IDs within a cohort
  5.2  Visit ID Referential Integrity -- associated_visit references resolve
  5.3  Visit <-> PHT Consistency -- visit block PHTs exist in the dbGaP PHV index
  5.4  Age Formula Structural Check -- age expressions reference valid PHVs
  5.6  Orphan Visit References -- visit IDs defined but never referenced
  5.8  Collection Interval Mismatch -- data PHV coll_interval vs visit case
  5.9  Visit uuid5 Format Compliance -- visit IDs must use uuid5 expressions
  5.10 Visit uuid5 Namespace -- uuid5 must use canonical bdchm namespace URL

Checks 5.5 (Multi-Visit Table Coverage) and 5.7 (Visit PHT/Label Alignment) were REMOVED on
2026-09-10. Both rested entirely on a visit cache produced by regex-matching dbGaP variable
names and table descriptions (`update_data.py` step 5: six name patterns such as `^VISIT$`,
`VTYP$`, `^visitnum$`, plus a description pattern). That is an inference, not a published visit
list, so validating a transform spec against it is one heuristic agreeing with another -- and a
PASS from it reads as verification. Neither could gate anyway: their severities topped out at
WARNING, and over the 11-cohort fleet they produced 1,982 INFO + 15 WARNING + 0 ERROR.

The signal is still useful as a LEAD -- it is how WHI's 37 `*VTYP` columns across 40 multi-visit
tables were spotted -- so the extraction now lives as an instrument in the AI-harmonization repo,
where a guess is allowed to be a guess. `data/visit-cache/` is not an authoritative alternative:
it holds the same generated regex results in a different shape.

Data source:
  --cache-dir     Directory holding the release-keyed .json.gz indexes -- the PHV index for
                  checks 5.3 and 5.4, the detail index for 5.8. Effectively REQUIRED: without
                  it those checks cannot run, and a check that cannot run is reported as an
                  ERROR against the cohort rather than skipped.

Usage:
    python validate_visit_structure.py --cohort FHS --cache-dir hv-lint/dbgap-cache
    python validate_visit_structure.py --cohort all --cache-dir hv-lint/dbgap-cache
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _paths import find_transform_dir  # noqa: E402
import _cohorts  # noqa: E402
from _derivations import iter_nested_class_derivs  # noqa: E402

import yaml




# -- Severity -----------------------------------------------------------------

SEVERITY_RANK = {"CRITICAL": 5, "ERROR": 4, "HIGH": 3, "WARNING": 2, "INFO": 1}

# -- Cohort mapping -----------------------------------------------------------


# -- Regex patterns -----------------------------------------------------------

# Matches the result string in a case tuple: , "RESULT") or , 'RESULT')
# YAML single-quoted strings use '' for literal ', producing single-quoted
# strings in the parsed Python value.  We need both quote flavours.
CASE_RESULT_DQ_RE = re.compile(r',\s*"([^"]+)"\s*\)')
CASE_RESULT_SQ_RE = re.compile(r",\s*'([^']+)'\s*\)")

# Matches string concatenated after closing paren: ) + "SUFFIX" or ) + 'SUFFIX'
SUFFIX_AFTER_PAREN_DQ_RE = re.compile(r'\)\s*\+\s*"([^"]*)"')
SUFFIX_AFTER_PAREN_SQ_RE = re.compile(r"\)\s*\+\s*'([^']*)'")

# Matches a case() branch whose result is a whole uuid5() call, with the visit label in the
# seed: , uuid5("<ns>", str({phv}) + ":LABEL")
#
# Without this the branch result is not a bare quoted string, nothing matches above, and the
# function falls through to the "no case()" path below -- which returns every quoted string in
# the expression, including the DISCRIMINATOR CODES being compared against. A pht then appears
# to carry twice the labels it has, which reads as a cross-file inconsistency that is not there.
# COPDGene's shipped specs use this form in 48 associated_visit blocks, so the fallback
# mis-parses production output, not only generated output.
CASE_RESULT_UUID5_RE = re.compile(r""",\s*uuid5\(.*?\+\s*['"]:?([^'"]+)['"]\s*\)""")

# Matches any quoted string (double or single)
QUOTED_DQ_RE = re.compile(r'"([^"]+)"')
QUOTED_SQ_RE = re.compile(r"'([^']+)'")

# Matches PHV accessions (with or without braces)
PHV_RE = re.compile(r'(phv\d{8})')

# Matches PHT accessions
PHT_RE = re.compile(r'^pht\d{6}$')

# Detects case() usage in expressions
CASE_USAGE_RE = re.compile(r'\bcase\s*\(')


def _strip_label_artifacts(label: str) -> str:
    """Strip separator artifacts from extracted visit labels.

    FHS Pattern-A embeds the colon separator inside the string:
        str({phv}) + ":FHS OFFSPRING EXAM 1"
    This produces labels like ":FHS OFFSPRING EXAM 1".
    Strip the leading colon (it's a uuid5 seed separator, not part of the label).
    """
    return label.lstrip(":")


# -- Data structures ----------------------------------------------------------

@dataclass
class Finding:
    file: str
    block: int
    check: str
    severity: str
    message: str

    @staticmethod
    def _esc_prop(text: str) -> str:
        return (text.replace("%", "%25").replace("\r", "%0D")
                .replace("\n", "%0A").replace(":", "%3A").replace(",", "%2C"))

    @staticmethod
    def _esc_msg(text: str) -> str:
        return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")

    def gh_annotation(self) -> str:
        level = {
            "CRITICAL": "error", "ERROR": "error",
            "WARNING": "warning", "HIGH": "warning", "INFO": "notice",
        }.get(self.severity, "notice")
        file_prop = self._esc_prop(self.file)
        msg = self._esc_msg(self.message)
        block_str = f" (block {self.block})" if self.block >= 0 else ""
        return f"::{level} file={file_prop}::HV-Lint [{self.check}] {msg}{block_str}"

    def terminal_line(self) -> str:
        sev = self.severity[:5].ljust(5)
        block_str = f"block {self.block:>3}" if self.block >= 0 else "  cohort "
        return f"  {sev}  {block_str}  [{self.check}] {self.message}"


@dataclass
class VisitBlock:
    """A single Visit class_derivation block from visit.yaml."""
    block_index: int
    visit_id: str | None          # from value:, or None if dynamic
    visit_labels: set[str]        # human-readable labels
    pht: str | None               # populated_from
    id_is_dynamic: bool           # True if uses uuid5/complex expr
    id_expr: str | None           # raw id expression (for 5.7 discriminator check)
    age_start_expr: str | None
    age_end_expr: str | None
    age_phvs: set[str]            # PHVs referenced in age expressions
    all_phvs: set[str]            # PHVs referenced in ANY expression in this block
    has_participant: bool


@dataclass
class VisitRegistry:
    """All Visit blocks from a cohort's visit.yaml."""
    cohort: str
    file_path: str                # relative path
    blocks: list[VisitBlock]
    static_ids: set[str]          # All value-based visit IDs
    all_labels: set[str]          # Union of all labels across all blocks
    uses_dynamic_ids: bool        # True if any block uses uuid5


@dataclass
class VisitReference:
    """A reference to a visit from a measurement/condition file."""
    file: str
    block_index: int
    class_name: str
    visit_id: str | None
    visit_labels: set[str]
    is_dynamic: bool


@dataclass
class TransformBlock:
    """Info about a class_derivation block."""
    file: str
    block_index: int
    class_name: str
    pht: str | None


# -- Visit label extraction ---------------------------------------------------

def extract_visit_labels_from_expr(expr: str) -> tuple[set[str], bool]:
    """Extract human-readable visit labels from an id or associated_visit expression.

    Handles:
      - Simple case(): case((..., "LABEL1"), (..., "LABEL2"))
      - Case + suffix: case((..., "PREFIX1"), ...) + " SUFFIX"
      - UUID5 wrapping: uuid5("URL", ... + case(...) + " SUFFIX")
      - FHS Pattern A: str({phv}) + ":LABEL" -- colon prefix on label
      - Single-quoted values: YAML '' escaping -> Python ' in parsed exprs

    Returns (set_of_labels, is_dynamic).
    """
    is_dynamic = "uuid5" in expr
    expr_str = str(expr)

    # Extract case() result strings (both quote flavours)
    case_results = (
        CASE_RESULT_DQ_RE.findall(expr_str)
        + CASE_RESULT_SQ_RE.findall(expr_str)
        + CASE_RESULT_UUID5_RE.findall(expr_str)
    )

    if case_results:
        # Look for suffix concatenated after case(): ) + "SUFFIX"
        suffixes = (
            SUFFIX_AFTER_PAREN_DQ_RE.findall(expr_str)
            + SUFFIX_AFTER_PAREN_SQ_RE.findall(expr_str)
        )
        visit_suffix = ""
        for s in suffixes:
            stripped = s.strip()
            if (stripped
                    and not stripped.startswith("http")
                    and stripped != ":"
                    # `.lstrip(':')`: a suffix keeps its leading colon where a captured
                    # label does not, so comparing raw lets a label be appended to itself.
                    and s.lstrip(":") not in case_results
                    and any(c.isalpha() for c in stripped)):
                visit_suffix = s
                break
        labels = {
            _strip_label_artifacts(cr + visit_suffix)
            for cr in case_results
        }
        return labels, is_dynamic

    # No case() -- extract quoted strings as candidate labels
    all_quoted = (
        QUOTED_DQ_RE.findall(expr_str)
        + QUOTED_SQ_RE.findall(expr_str)
    )
    non_url = {
        _strip_label_artifacts(s)
        for s in all_quoted
        if not s.startswith("http")
        and len(s) > 1
        and any(c.isalpha() for c in s)
        and s.lstrip(":") != ""
    }
    # Filter out bare separator artifacts that are only ":"
    non_url.discard("")
    return non_url, is_dynamic


def extract_phvs_from_expr(expr: str) -> set[str]:
    """Extract all PHV accessions from an expression."""
    return set(PHV_RE.findall(str(expr)))


# -- YAML parsing -------------------------------------------------------------

def find_yaml_files(base_dir: Path, cohort: str) -> list[Path]:
    """Find all transform YAML files, optionally filtered by cohort."""
    files = sorted(
        f for f in base_dir.rglob("*.yaml")
        if any("-ingest" in part for part in f.parts)
        and not f.name.endswith(".swp")
    )
    if cohort.lower() != "all":
        target_dir = f"{cohort}-ingest".lower()
        # Use exact directory name match, not substring, to avoid
        # "CHS-ingest" matching "HCHS-ingest".
        files = [
            f for f in files
            if any(part.lower() == target_dir for part in f.parts)
        ]
    return files


def detect_cohort(file_path: Path) -> str:
    """Extract cohort name from directory path."""
    for part in file_path.parts:
        if part.endswith("-ingest"):
            return part.replace("-ingest", "")
    return "UNKNOWN"


def parse_yaml_safe(file_path: Path) -> list[dict] | None:
    """Parse a YAML file and return its block list, or None on error."""
    try:
        with file_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError):
        return None
    if data is None:
        return None
    return data if isinstance(data, list) else [data]


# -- Visit registry construction ----------------------------------------------

def build_visit_registry(visit_file: Path, hv_root: Path) -> VisitRegistry | None:
    """Parse a visit.yaml and build a VisitRegistry."""
    cohort = detect_cohort(visit_file)
    rel_path = visit_file.relative_to(hv_root).as_posix()

    blocks_data = parse_yaml_safe(visit_file)
    if not blocks_data:
        return None

    visit_blocks: list[VisitBlock] = []
    static_ids: set[str] = set()
    all_labels: set[str] = set()
    uses_dynamic = False

    for idx, block in enumerate(blocks_data):
        if not isinstance(block, dict):
            continue
        class_derivs = block.get("class_derivations", {})
        if "Visit" not in class_derivs:
            continue

        visit_cd = class_derivs["Visit"]
        if not isinstance(visit_cd, dict):
            continue
        pht = visit_cd.get("populated_from")
        slot_derivs = visit_cd.get("slot_derivations", {})

        # -- Extract visit ID --
        id_slot = slot_derivs.get("id", {})
        visit_id = None
        visit_labels_set: set[str] = set()
        id_is_dynamic = False
        id_expr: str | None = None

        if isinstance(id_slot, dict):
            if "value" in id_slot:
                visit_id = str(id_slot["value"])
                visit_labels_set = {visit_id}
                static_ids.add(visit_id)
            elif "expr" in id_slot:
                id_expr = str(id_slot["expr"])
                labels, is_dyn = extract_visit_labels_from_expr(id_expr)
                visit_labels_set = labels
                id_is_dynamic = is_dyn
                if is_dyn:
                    uses_dynamic = True

        all_labels.update(visit_labels_set)

        # -- Extract age expressions and PHVs --
        age_start = slot_derivs.get("age_at_visit_start", {})
        age_end = slot_derivs.get("age_at_visit_end", {})

        age_start_expr = (
            str(age_start.get("expr")) if isinstance(age_start, dict) and "expr" in age_start else None
        )
        age_end_expr = (
            str(age_end.get("expr")) if isinstance(age_end, dict) and "expr" in age_end else None
        )

        age_phvs: set[str] = set()
        if age_start_expr:
            age_phvs.update(extract_phvs_from_expr(age_start_expr))
        if age_end_expr:
            age_phvs.update(extract_phvs_from_expr(age_end_expr))
        # Also check populated_from for age slots
        for age_slot in (age_start, age_end):
            if isinstance(age_slot, dict) and "populated_from" in age_slot:
                pfrom = str(age_slot["populated_from"])
                phvs = PHV_RE.findall(pfrom)
                age_phvs.update(phvs)

        # -- Check for associated_participant --
        participant_slot = slot_derivs.get("associated_participant", {})
        has_participant = bool(
            isinstance(participant_slot, dict)
            and (participant_slot.get("populated_from") or participant_slot.get("expr"))
        )

        # -- Collect ALL PHVs from all expressions in this block --
        all_block_phvs: set[str] = set(age_phvs)
        for sd_name, sd_val in slot_derivs.items():
            if not isinstance(sd_val, dict):
                continue
            for key in ("expr", "populated_from"):
                raw = sd_val.get(key)
                if isinstance(raw, str):
                    all_block_phvs.update(PHV_RE.findall(raw))

        visit_blocks.append(VisitBlock(
            block_index=idx,
            visit_id=visit_id,
            visit_labels=visit_labels_set,
            pht=pht,
            id_is_dynamic=id_is_dynamic,
            id_expr=id_expr,
            age_start_expr=age_start_expr,
            age_end_expr=age_end_expr,
            age_phvs=age_phvs,
            all_phvs=all_block_phvs,
            has_participant=has_participant,
        ))

    if not visit_blocks:
        return None

    return VisitRegistry(
        cohort=cohort,
        file_path=rel_path,
        blocks=visit_blocks,
        static_ids=static_ids,
        all_labels=all_labels,
        uses_dynamic_ids=uses_dynamic,
    )


# -- Transform file scanning -------------------------------------------------

def scan_transform_file(
    yaml_file: Path, hv_root: Path,
) -> tuple[list[VisitReference], list[TransformBlock]]:
    """Extract visit references and block info from a single YAML file.

    Returns (visit_refs, transform_blocks).
    """
    rel_path = yaml_file.relative_to(hv_root).as_posix()
    blocks_data = parse_yaml_safe(yaml_file)
    if not blocks_data:
        return [], []

    visit_refs: list[VisitReference] = []
    transform_blocks: list[TransformBlock] = []

    for idx, block in enumerate(blocks_data):
        if not isinstance(block, dict):
            continue
        class_derivs = block.get("class_derivations", {})

        for class_name, class_def in class_derivs.items():
            if class_name == "Visit":
                continue
            if not isinstance(class_def, dict):
                continue

            pht = class_def.get("populated_from")
            slot_derivs = class_def.get("slot_derivations", {})
            visit_slot = slot_derivs.get("associated_visit", {})

            if isinstance(visit_slot, dict) and (
                "value" in visit_slot or "expr" in visit_slot
            ):
                visit_id = None
                visit_labels_set: set[str] = set()
                is_dynamic = False

                if "value" in visit_slot:
                    visit_id = str(visit_slot["value"])
                    visit_labels_set = {visit_id}
                elif "expr" in visit_slot:
                    expr_str = str(visit_slot["expr"])
                    labels, is_dyn = extract_visit_labels_from_expr(expr_str)
                    visit_labels_set = labels
                    is_dynamic = is_dyn

                if visit_labels_set or visit_id:
                    visit_refs.append(VisitReference(
                        file=rel_path,
                        block_index=idx,
                        class_name=class_name,
                        visit_id=visit_id,
                        visit_labels=visit_labels_set,
                        is_dynamic=is_dynamic,
                    ))

            transform_blocks.append(TransformBlock(
                file=rel_path,
                block_index=idx,
                class_name=class_name,
                pht=pht,
            ))

            # Also scan nested object_derivations for visit references
            _scan_nested_visit_refs(
                class_def, idx, class_name, rel_path, visit_refs
            )

    return visit_refs, transform_blocks


def _scan_nested_visit_refs(
    class_def: dict,
    block_idx: int,
    parent_class: str,
    file: str,
    refs: list[VisitReference],
) -> None:
    """Extract visit references from object_derivations (nested classes)."""
    for slot_name, slot_def in class_def.get("slot_derivations", {}).items():
        if not isinstance(slot_def, dict):
            continue
        for nested_name, nested_def in iter_nested_class_derivs(slot_def):
            if not isinstance(nested_def, dict):
                continue
            nested_slots = nested_def.get("slot_derivations", {})
            visit_slot = nested_slots.get("associated_visit", {})
            if not isinstance(visit_slot, dict):
                continue
            if "value" in visit_slot or "expr" in visit_slot:
                visit_id = None
                visit_labels_set: set[str] = set()
                is_dynamic = False
                if "value" in visit_slot:
                    visit_id = str(visit_slot["value"])
                    visit_labels_set = {visit_id}
                elif "expr" in visit_slot:
                    labels, is_dyn = extract_visit_labels_from_expr(
                        str(visit_slot["expr"])
                    )
                    visit_labels_set = labels
                    is_dynamic = is_dyn
                refs.append(VisitReference(
                    file=file,
                    block_index=block_idx,
                    class_name=f"{parent_class}.{slot_name}.{nested_name}",
                    visit_id=visit_id,
                    visit_labels=visit_labels_set,
                    is_dynamic=is_dynamic,
                ))


# -- Checks -------------------------------------------------------------------

def check_5_1_uniqueness(registry: VisitRegistry) -> list[Finding]:
    """5.1: No duplicate visit IDs within a cohort's visit.yaml."""
    findings: list[Finding] = []

    if registry.uses_dynamic_ids:
        # For uuid5-based IDs, check label uniqueness instead
        seen_labels: dict[str, int] = {}
        for vb in registry.blocks:
            for label in sorted(vb.visit_labels):
                if label in seen_labels:
                    findings.append(Finding(
                        file=registry.file_path,
                        block=vb.block_index,
                        check="5.1",
                        severity="ERROR",
                        message=(
                            f"Duplicate visit label '{label}' -- "
                            f"also in block {seen_labels[label]}"
                        ),
                    ))
                else:
                    seen_labels[label] = vb.block_index
    else:
        # Static IDs -- check exact ID uniqueness
        seen_ids: dict[str, int] = {}
        for vb in registry.blocks:
            vid = vb.visit_id
            if vid is None:
                continue
            if vid in seen_ids:
                findings.append(Finding(
                    file=registry.file_path,
                    block=vb.block_index,
                    check="5.1",
                    severity="ERROR",
                    message=(
                        f"Duplicate visit ID '{vid}' -- "
                        f"also in block {seen_ids[vid]}"
                    ),
                ))
            else:
                seen_ids[vid] = vb.block_index

    return findings


def check_5_2_referential_integrity(
    registry: VisitRegistry,
    all_refs: list[VisitReference],
) -> list[Finding]:
    """5.2: Every associated_visit reference resolves to a visit.yaml entry."""
    findings: list[Finding] = []

    for ref in all_refs:
        if ref.visit_id and not ref.is_dynamic:
            # Static reference -- must match a static ID or known label
            if (ref.visit_id not in registry.static_ids
                    and ref.visit_id not in registry.all_labels):
                findings.append(Finding(
                    file=ref.file,
                    block=ref.block_index,
                    check="5.2",
                    severity="ERROR",
                    message=(
                        f"{ref.class_name}.associated_visit = '{ref.visit_id}' "
                        f"does not match any Visit ID in {registry.file_path}"
                    ),
                ))
        elif ref.visit_labels:
            # Dynamic or case-based reference -- check labels
            for label in sorted(ref.visit_labels):
                if label not in registry.all_labels:
                    is_fallback = any(
                        kw in label.upper()
                        for kw in ["UNKNOWN", "DEFAULT", "OTHER"]
                    )
                    findings.append(Finding(
                        file=ref.file,
                        block=ref.block_index,
                        check="5.2",
                        severity="INFO" if is_fallback else "WARNING",
                        message=(
                            f"{ref.class_name}.associated_visit label "
                            f"'{label}' not found in {registry.file_path}"
                            + (" (fallback/catch-all)" if is_fallback else "")
                        ),
                    ))

    return findings


def check_5_3_visit_pht_consistency(
    registry: VisitRegistry,
    phv_index: dict[str, str],
) -> list[Finding]:
    """5.3: Visit block PHTs are real tables in the dbGaP release being linted.

    Reads the PHT set from the authoritative ``{phv: pht}`` index -- the same source check 3.2
    uses -- rather than from the regex-derived visit cache. Two of the three assertions never
    needed a cache at all, and the third needs only the set of PHTs in the release, which is a
    fact rather than an inference.
    """
    findings: list[Finding] = []
    known_phts: set[str] = set(phv_index.values())

    for vb in registry.blocks:
        if not vb.pht:
            findings.append(Finding(
                file=registry.file_path,
                block=vb.block_index,
                check="5.3",
                severity="ERROR",
                message="Visit block has no populated_from PHT",
            ))
            continue

        if not PHT_RE.match(str(vb.pht)):
            findings.append(Finding(
                file=registry.file_path,
                block=vb.block_index,
                check="5.3",
                severity="ERROR",
                message=f"Visit block populated_from '{vb.pht}' is not a valid PHT accession",
            ))
            continue

        if vb.pht not in known_phts:
            label = vb.visit_id or next(iter(vb.visit_labels), f"block {vb.block_index}")
            findings.append(Finding(
                file=registry.file_path,
                block=vb.block_index,
                check="5.3",
                severity="ERROR",
                message=(
                    f"Visit '{label}' references PHT '{vb.pht}' "
                    f"which is not in the dbGaP PHV index for {registry.cohort} -- "
                    f"the table does not exist in the release being linted"
                ),
            ))

    return findings


def check_5_4_age_formula(
    registry: VisitRegistry,
    phv_index: dict[str, str] | None,
) -> list[Finding]:
    """5.4: Age expressions reference valid PHVs and follow consistent patterns."""
    findings: list[Finding] = []

    for vb in registry.blocks:
        label = vb.visit_id or next(iter(vb.visit_labels), f"block {vb.block_index}")

        # Check that age slots exist
        if not vb.age_start_expr and not vb.age_end_expr:
            findings.append(Finding(
                file=registry.file_path,
                block=vb.block_index,
                check="5.4",
                severity="WARNING",
                message=f"Visit '{label}' has no age_at_visit_start or age_at_visit_end",
            ))
            continue

        # Validate PHVs in age expressions against index
        if phv_index is not None:
            for phv in sorted(vb.age_phvs):
                if phv not in phv_index:
                    findings.append(Finding(
                        file=registry.file_path,
                        block=vb.block_index,
                        check="5.4",
                        severity="ERROR",
                        message=(
                            f"Visit '{label}' age expression references "
                            f"unknown PHV '{phv}'"
                        ),
                    ))

        # Check for * 365 pattern (age in years -> days conversion)
        for expr_label, expr_val in [
            ("age_at_visit_start", vb.age_start_expr),
            ("age_at_visit_end", vb.age_end_expr),
        ]:
            if expr_val and "* 365" not in expr_val and "*365" not in expr_val:
                findings.append(Finding(
                    file=registry.file_path,
                    block=vb.block_index,
                    check="5.4",
                    severity="INFO",
                    message=(
                        f"Visit '{label}' {expr_label} does not contain "
                        f"'* 365' conversion -- verify units are in days"
                    ),
                ))

    return findings


def check_5_6_orphan_visits(
    registry: VisitRegistry,
    all_refs: list[VisitReference],
) -> list[Finding]:
    """5.6: Visit IDs/labels defined but never referenced by any transform file."""
    findings: list[Finding] = []

    # Collect all referenced labels/IDs
    referenced: set[str] = set()
    for ref in all_refs:
        if ref.visit_id:
            referenced.add(ref.visit_id)
        referenced.update(ref.visit_labels)

    for vb in registry.blocks:
        if vb.visit_id:
            # Static ID -- check if referenced
            if vb.visit_id not in referenced:
                findings.append(Finding(
                    file=registry.file_path,
                    block=vb.block_index,
                    check="5.6",
                    severity="INFO",
                    message=(
                        f"Visit '{vb.visit_id}' defined but never referenced "
                        f"by any transform file"
                    ),
                ))
        elif vb.visit_labels:
            # Dynamic -- check if ANY label is referenced
            unreferenced = vb.visit_labels - referenced
            if unreferenced and len(unreferenced) == len(vb.visit_labels):
                label_preview = sorted(vb.visit_labels)[0]
                findings.append(Finding(
                    file=registry.file_path,
                    block=vb.block_index,
                    check="5.6",
                    severity="INFO",
                    message=(
                        f"Visit block (labels include '{label_preview}') -- "
                        f"no labels referenced by any transform file"
                    ),
                ))

    return findings


# -- Collection interval parsing ----------------------------------------------

# Matches "Collected in: P1 P2 P3" or "Collected in: P2 P3" style values
_COLLECTED_IN_RE = re.compile(r"^Collected\s+in:\s*(.+)$", re.IGNORECASE)

# Sub-phase aliases: if a parent phase is in coll_interval, its sub-phases
# are considered covered.  COPDGene P3B is "Phase 3 Short-term 1-year
# follow-up" -- a sub-visit of P3 that dbGaP rolls into "Collected in: P3".
_PHASE_SUB_ALIASES: dict[str, str] = {
    "P3B": "P3",  # COPDGene Phase 3B -> Phase 3
}


def expand_ci_phases(ci_phases: set[str]) -> set[str]:
    """Expand collection-interval phases to include known sub-phase aliases.

    If ci_phases contains a parent phase (e.g., 'P3'), the corresponding
    sub-phase (e.g., 'P3B') is added to the returned set, because dbGaP
    annotates sub-visit data under the parent phase's collection interval.
    """
    expanded = set(ci_phases)
    # Reverse lookup: parent -> children
    for child, parent in _PHASE_SUB_ALIASES.items():
        if parent in ci_phases:
            expanded.add(child)
    return expanded


def parse_coll_interval_phases(coll_interval: str) -> set[str] | None:
    """Parse a structured coll_interval string into a set of phase tokens.

    Returns a set of phase tokens (e.g., {"P1", "P2", "P3"}) if the string
    follows the "Collected in: X Y Z" format.  Returns None if the format
    is unstructured (e.g., FHS date ranges) -- callers should skip validation.
    """
    if not coll_interval:
        return None
    m = _COLLECTED_IN_RE.match(coll_interval.strip())
    if not m:
        return None
    tokens = m.group(1).split()
    # Only return if we got at least one token
    return set(tokens) if tokens else None


def extract_visit_phase_token(visit_label: str) -> str | None:
    """Extract a phase token from a visit label like 'COPDGene P2' -> 'P2'.

    Heuristic: the last whitespace-separated token that looks like a
    phase identifier (starts with uppercase letter or digit). Returns
    None if no phase token is found.
    """
    parts = visit_label.strip().split()
    if len(parts) >= 2:
        return parts[-1]
    return None


def _extract_data_phvs_from_block(
    class_def: dict,
) -> tuple[set[str], set[str]]:
    """Extract data PHVs and visit-case PHVs from a class_derivation block.

    Returns (data_phvs, case_visit_phvs) where:
      - data_phvs: PHVs used for actual data (condition_status, value_decimal, etc.)
      - case_visit_phvs: PHVs used in the associated_visit case expression
    """
    slot_derivs = class_def.get("slot_derivations", {})
    data_phvs: set[str] = set()
    case_visit_phvs: set[str] = set()

    # Administrative slots whose PHVs are not "data" -- they are structural
    admin_slots = {
        "associated_visit", "associated_participant", "id",
        "associated_person", "associated_study",
    }

    for slot_name, slot_def in slot_derivs.items():
        if not isinstance(slot_def, dict):
            continue

        phvs_in_slot: set[str] = set()
        for key in ("expr", "populated_from"):
            raw = slot_def.get(key)
            if isinstance(raw, str):
                phvs_in_slot.update(PHV_RE.findall(raw))

        if slot_name in admin_slots:
            if slot_name == "associated_visit":
                case_visit_phvs.update(phvs_in_slot)
        else:
            data_phvs.update(phvs_in_slot)

    return data_phvs, case_visit_phvs


# Condition-class names that may produce false ABSENT on null
_CONDITION_CLASSES = {"Condition"}


def check_5_8_collection_interval(
    yaml_files: list[Path],
    hv_root: Path,
    detail_index: dict[str, dict],
) -> list[Finding]:
    """5.8: PHV collection interval vs visit case label mismatch.

    For each transform file using a case() visit expression, extracts the
    visit phase tokens and compares them against each data PHV's
    ``coll_interval`` field from the detail index.

    If a data PHV is NOT collected at a phase that the case expression
    routes to, the pipeline will process rows for that phase with null
    data values -- producing NaN measurements or (worse) false ABSENT
    conditions.

    Severity:
        CRITICAL -- Condition class mismatch (null -> false ABSENT)
        ERROR    -- Measurement/Observation class mismatch (null -> NaN)
    """
    findings: list[Finding] = []

    for yaml_file in yaml_files:
        if yaml_file.name == "visit.yaml":
            continue

        blocks_data = parse_yaml_safe(yaml_file)
        if not blocks_data:
            continue

        rel_path = yaml_file.relative_to(hv_root).as_posix()

        for idx, block in enumerate(blocks_data):
            if not isinstance(block, dict):
                continue
            class_derivs = block.get("class_derivations", {})

            for class_name, class_def in class_derivs.items():
                if class_name == "Visit" or not isinstance(class_def, dict):
                    continue

                slot_derivs = class_def.get("slot_derivations", {})
                visit_slot = slot_derivs.get("associated_visit", {})
                if not isinstance(visit_slot, dict):
                    continue

                # Only check case()-based visit expressions
                visit_expr = visit_slot.get("expr")
                if not visit_expr or not CASE_USAGE_RE.search(str(visit_expr)):
                    continue

                # Extract visit labels from case expression
                visit_labels, _ = extract_visit_labels_from_expr(str(visit_expr))
                if not visit_labels:
                    continue

                # Extract phase tokens from labels (e.g., "COPDGene P2" -> "P2")
                label_to_phase: dict[str, str] = {}
                for label in visit_labels:
                    phase = extract_visit_phase_token(label)
                    if phase:
                        label_to_phase[label] = phase
                if not label_to_phase:
                    continue

                case_phases = set(label_to_phase.values())

                # Ignore the (True, None) fallback -- it suppresses, not routes
                # filter out None labels that came from extract
                visit_labels.discard("None")

                # Get data PHVs for this block
                data_phvs, _ = _extract_data_phvs_from_block(class_def)
                if not data_phvs:
                    continue

                is_condition = class_name in _CONDITION_CLASSES

                for phv in sorted(data_phvs):
                    detail = detail_index.get(phv)
                    if not detail:
                        continue

                    ci = detail.get("coll_interval", "")
                    ci_phases = parse_coll_interval_phases(ci)
                    if ci_phases is None:
                        # Unstructured or missing coll_interval -> skip
                        continue

                    # Expand ci_phases with known sub-phase aliases
                    # (e.g., P3 covers P3B in COPDGene)
                    ci_expanded = expand_ci_phases(ci_phases)

                    # Find phases in the case expression NOT covered
                    uncovered = case_phases - ci_expanded
                    if not uncovered:
                        continue

                    var_name = detail.get("name", phv)
                    covered_str = ", ".join(sorted(ci_phases))
                    uncovered_str = ", ".join(sorted(uncovered))

                    if is_condition:
                        severity = "CRITICAL"
                        impact = (
                            f"null condition_status at [{uncovered_str}] "
                            f"may default to ABSENT -> false negatives"
                        )
                    else:
                        severity = "ERROR"
                        impact = (
                            f"null data at [{uncovered_str}] "
                            f"-> NaN rows in output"
                        )

                    findings.append(Finding(
                        file=rel_path,
                        block=idx,
                        check="5.8",
                        severity=severity,
                        message=(
                            f"{class_name} visit case includes phases "
                            f"[{uncovered_str}] but {phv} ({var_name}) "
                            f"is only collected at [{covered_str}]. "
                            f"{impact}"
                        ),
                    ))

    return findings


# -- Check 5.9: Visit uuid5 Format Compliance ---------------------------------

_UUID5_RE = re.compile(r'\buuid5\s*\(')
_CANONICAL_NS = "https://w3id.org/bdchm/Visit"


def check_5_9_uuid5_format(
    registry: VisitRegistry,
    visit_refs: list[VisitReference],
) -> list[Finding]:
    """5.9: Visit IDs should use uuid5 expressions, not plain value: strings.

    Checks:
      a) visit.yaml: every Visit block id: should use expr: with uuid5
      b) Entity files: every associated_visit should use expr: with uuid5
    """
    findings: list[Finding] = []

    # 5.9a: visit.yaml blocks
    for vb in registry.blocks:
        if not vb.id_is_dynamic and vb.visit_id is not None:
            findings.append(Finding(
                file=registry.file_path,
                block=vb.block_index,
                check="5.9",
                severity="ERROR",
                message=(
                    f"Visit.id uses plain value: '{vb.visit_id}' -- "
                    f"should use expr: with uuid5() for deterministic, "
                    f"participant-scoped identifiers"
                ),
            ))

    # 5.9b: Entity file associated_visit references
    for ref in visit_refs:
        if not ref.is_dynamic and ref.visit_id is not None:
            findings.append(Finding(
                file=ref.file,
                block=ref.block_index,
                check="5.9",
                severity="ERROR",
                message=(
                    f"{ref.class_name}.associated_visit uses plain "
                    f"value: '{ref.visit_id}' -- should use expr: with "
                    f"uuid5() to match visit.yaml identifiers"
                ),
            ))

    return findings


# -- Check 5.10: Visit uuid5 Namespace Consistency ----------------------------


def check_5_10_uuid5_namespace(
    registry: VisitRegistry,
    visit_refs: list[VisitReference],
    yaml_files: list[Path],
    hv_root: Path,
) -> list[Finding]:
    """5.10: uuid5 expressions must use the canonical bdchm namespace URL.

    The standard namespace is 'https://w3id.org/bdchm/Visit'.
    Any uuid5 call using a different namespace will produce incompatible
    UUIDs that break visit-entity joins.
    """
    findings: list[Finding] = []

    # Check visit.yaml blocks
    for vb in registry.blocks:
        if vb.id_expr and "uuid5" in vb.id_expr:
            if _CANONICAL_NS not in vb.id_expr:
                findings.append(Finding(
                    file=registry.file_path,
                    block=vb.block_index,
                    check="5.10",
                    severity="CRITICAL",
                    message=(
                        f"Visit.id uuid5 uses non-canonical namespace -- "
                        f"must use '{_CANONICAL_NS}'. Mismatched namespaces "
                        f"produce incompatible UUIDs"
                    ),
                ))

    # Check entity files -- need to re-read for raw expr access
    for yf in yaml_files:
        if yf.name == "visit.yaml":
            continue
        rel_path = yf.relative_to(hv_root).as_posix()
        blocks_data = parse_yaml_safe(yf)
        if not blocks_data:
            continue

        for idx, block in enumerate(blocks_data):
            if not isinstance(block, dict):
                continue
            class_derivs = block.get("class_derivations", {})
            for cls_name, cls_def in class_derivs.items():
                if cls_name == "Visit" or not isinstance(cls_def, dict):
                    continue
                slot_derivs = cls_def.get("slot_derivations", {})
                visit_slot = slot_derivs.get("associated_visit", {})
                if not isinstance(visit_slot, dict):
                    continue
                expr = visit_slot.get("expr")
                if isinstance(expr, str) and "uuid5" in expr:
                    if _CANONICAL_NS not in expr:
                        findings.append(Finding(
                            file=rel_path,
                            block=idx,
                            check="5.10",
                            severity="CRITICAL",
                            message=(
                                f"{cls_name}.associated_visit uuid5 uses "
                                f"non-canonical namespace -- must use "
                                f"'{_CANONICAL_NS}'"
                            ),
                        ))

    return findings


# -- Index loading ------------------------------------------------------------

def load_phv_index(cache_dir: Path, cache_key: str) -> dict[str, str] | None:
    """Load the basic PHV->PHT index for a cohort."""
    gz_path = cache_dir / f"{cache_key}.json.gz"
    if not gz_path.exists():
        return None
    with gzip.open(gz_path, "rt", encoding="utf-8") as f:
        return json.load(f)


def load_detail_index(cache_dir: Path, cache_key: str) -> dict[str, dict] | None:
    """Load the extended PHV detail index (with coll_interval) for a cohort."""
    gz_path = cache_dir / f"{cache_key}_detail.json.gz"
    if not gz_path.exists():
        return None
    with gzip.open(gz_path, "rt", encoding="utf-8") as f:
        return json.load(f)


# -- Main ---------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="HV-Lint Phase 5: Visit Structure Validation"
    )
    p.add_argument(
        "--cohort", default="all",
        help="Cohort to validate (e.g., ARIC, CHS) or 'all' (default: all)",
    )
    p.add_argument(
        "--fail-on", default="error",
        choices=["critical", "error", "high", "warning", "info"],
        help="Minimum severity to cause non-zero exit (default: error)",
    )
    p.add_argument(
        "--cache-dir", default=None,
        help="Directory with per-cohort .json.gz PHV indexes (check 5.4)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    in_ci = os.environ.get("GITHUB_ACTIONS") == "true"

    base_dir = find_transform_dir()
    hv_root = base_dir.parent

    # Determine which cohorts to process
    if args.cohort.lower() == "all":
        cohort_dirs = sorted(set(
            detect_cohort(f)
            for f in base_dir.iterdir()
            if f.is_dir() and f.name.endswith("-ingest")
        ))
    else:
        cohort_dirs = [args.cohort]

    all_findings: list[Finding] = []
    cohorts_processed = 0
    cohorts_skipped: list[str] = []

    for cohort in cohort_dirs:
        ingest_dir = base_dir / f"{cohort}-ingest"
        visit_file = ingest_dir / "visit.yaml"

        if not visit_file.exists():
            all_findings.append(Finding(
                file=f"priority_variables_transform/{cohort}-ingest/",
                block=-1,
                check="5.0",
                severity="WARNING",
                message=f"No visit.yaml found for cohort {cohort}",
            ))
            cohorts_skipped.append(cohort)
            continue

        # Build visit registry
        registry = build_visit_registry(visit_file, hv_root)
        if registry is None:
            all_findings.append(Finding(
                file=visit_file.relative_to(hv_root).as_posix(),
                block=-1,
                check="5.0",
                severity="ERROR",
                message=f"Could not parse visit.yaml or no Visit blocks for {cohort}",
            ))
            cohorts_skipped.append(cohort)
            continue

        # Scan all non-visit YAML files
        yaml_files = find_yaml_files(base_dir, cohort)
        non_visit_files = [f for f in yaml_files if f.name != "visit.yaml"]

        cohort_refs: list[VisitReference] = []
        cohort_blocks: list[TransformBlock] = []
        for yf in non_visit_files:
            refs, blocks = scan_transform_file(yf, hv_root)
            cohort_refs.extend(refs)
            cohort_blocks.extend(blocks)

        # Print cohort header
        print(f"\n{'=' * 70}")
        print(f"Phase 5: {cohort}")
        print(f"  Visit blocks: {len(registry.blocks)}")
        print(f"  Visit labels: {len(registry.all_labels)}")
        print(f"  Dynamic IDs:  {'yes' if registry.uses_dynamic_ids else 'no'}")
        print(f"  Transform files: {len(non_visit_files)}")
        print(f"  Visit references: {len(cohort_refs)}")
        print(f"{'=' * 70}")

        # -- Run checks --

        # 5.1: Visit ID uniqueness
        all_findings.extend(check_5_1_uniqueness(registry))

        # 5.2: Referential integrity
        all_findings.extend(check_5_2_referential_integrity(registry, cohort_refs))

        cache_key = _cohorts.cache_key_for(cohort, args.cache_dir or "")
        phv_index = None

        # A check that CANNOT run is reported as an ERROR against the cohort, not as a skip:
        # an unrun check that exits clean is indistinguishable from a passing one. Both the
        # "no directory was supplied" and "the file is not there" cases count.
        if not args.cache_dir:
            all_findings.append(Finding(
                f"priority_variables_transform/{cohort}-ingest", 0, "5.3/5.4", "ERROR",
                f"no --cache-dir supplied, so checks 5.3 and 5.4 DID NOT RUN for {cohort}"))
        else:
            # The release is checked here for the reason Phase 3 checks it: `cache_key_for`
            # falls back to a legacy cohort-named key when the declared release file is absent,
            # and a cache built from a superseded release reports PHVs that exist only in the
            # newer one as absent -- indistinguishable from a real mapping error. Reported as a
            # Finding, not an exit code, because Phase 5 reports per cohort.
            declared = _cohorts.declared_study(cohort, cache_dir=args.cache_dir)
            if not declared:
                all_findings.append(Finding(
                    f"priority_variables_transform/{cohort}-ingest", 0, "5.3/5.4/5.8", "ERROR",
                    f"{cohort} declares no dbGaP release, so the cache cannot be checked -- add "
                    f"hv_dataqc/cache_fetcher/manifests/_manifest-{cohort.lower()}.yaml"))
            else:
                mismatch = _cohorts.study_mismatch(args.cache_dir, cache_key, declared)
                if mismatch:
                    all_findings.append(Finding(
                        f"priority_variables_transform/{cohort}-ingest", 0, "5.3/5.4/5.8",
                        "ERROR", f"declared release {declared}: {mismatch}"))

            phv_index = load_phv_index(Path(args.cache_dir), cache_key)
            if not phv_index:
                all_findings.append(Finding(
                    f"priority_variables_transform/{cohort}-ingest", 0, "5.3/5.4", "ERROR",
                    f"no PHV index for {cohort} (looked for '{cache_key}.json.gz' in "
                    f"{args.cache_dir}), so checks 5.3 and 5.4 DID NOT RUN"))

        # 5.3: Visit <-> PHT consistency, against the authoritative PHV index
        if phv_index:
            all_findings.extend(
                check_5_3_visit_pht_consistency(registry, phv_index)
            )

        # 5.4: Age formula structural check
        all_findings.extend(check_5_4_age_formula(registry, phv_index))

        # 5.5 REMOVED 2026-09-10 -- it rested on a regex-derived visit cache; see the module
        # docstring. The signal now lives as an instrument, not as a check.

        # 5.6: Orphan visit references
        all_findings.extend(check_5_6_orphan_visits(registry, cohort_refs))

        # 5.7 REMOVED 2026-09-10 -- same reason as 5.5.

        # 5.8: Collection interval vs visit case mismatch
        if not args.cache_dir:
            all_findings.append(Finding(
                f"priority_variables_transform/{cohort}-ingest", 0, "5.8", "ERROR",
                f"no --cache-dir supplied, so check 5.8 DID NOT RUN for {cohort}"))
        else:
            detail_idx = load_detail_index(Path(args.cache_dir), cache_key)
            # An ABSENT detail index is an ERROR, by the same rule stated above the PHV index
            # guard: a missing file made 5.8 exit clean, which reads as a pass. Only a detail
            # index that is PRESENT and holds no intervals is a legitimate skip -- that is a
            # fact about the cohort, not a missing input.
            if detail_idx is None:
                all_findings.append(Finding(
                    f"priority_variables_transform/{cohort}-ingest", 0, "5.8", "ERROR",
                    f"no detail index for {cohort} (looked for '{cache_key}_detail.json.gz' "
                    f"in {args.cache_dir}), so check 5.8 DID NOT RUN"))
            else:
                # Check if this cohort has any coll_interval data
                n_ci = sum(1 for v in detail_idx.values() if v.get("coll_interval"))
                if n_ci > 0:
                    all_findings.extend(
                        check_5_8_collection_interval(
                            yaml_files, hv_root, detail_idx
                        )
                    )
                else:
                    print(f"  INFO: No coll_interval data for {cohort} -- skipping 5.8")

        # 5.9: Visit uuid5 format compliance
        all_findings.extend(check_5_9_uuid5_format(registry, cohort_refs))

        # 5.10: Visit uuid5 namespace consistency
        all_findings.extend(
            check_5_10_uuid5_namespace(
                registry, cohort_refs, yaml_files, hv_root
            )
        )

        cohorts_processed += 1

    # -- Print findings grouped by file --
    findings_by_file: dict[str, list[Finding]] = {}
    for f in all_findings:
        findings_by_file.setdefault(f.file, []).append(f)

    for file_path in sorted(findings_by_file):
        print(f"\n{file_path}")
        for finding in sorted(
            findings_by_file[file_path],
            key=lambda f: (SEVERITY_RANK.get(f.severity, 0) * -1, f.block),
        ):
            print(finding.terminal_line())
            if in_ci:
                print(finding.gh_annotation())

    # -- Summary --
    by_severity: dict[str, int] = {}
    for f in all_findings:
        by_severity[f.severity] = by_severity.get(f.severity, 0) + 1

    print(f"\n{'=' * 70}")
    print(f"Phase 5 Summary: {cohorts_processed} cohort(s) processed, "
          f"{len(cohorts_skipped)} skipped")
    print(f"  Total findings: {len(all_findings)}")
    for sev in ["CRITICAL", "ERROR", "HIGH", "WARNING", "INFO"]:
        if sev in by_severity:
            print(f"    {sev}: {by_severity[sev]}")
    if cohorts_skipped:
        print(f"  Skipped: {', '.join(cohorts_skipped)}")

    # -- Exit code --
    fail_rank = SEVERITY_RANK[args.fail_on.upper()]
    blocking = [
        f for f in all_findings
        if SEVERITY_RANK.get(f.severity, 0) >= fail_rank
    ]
    if blocking:
        print(f"\nFAILED: {len(blocking)} findings at or above "
              f"'{args.fail_on}' severity")
        return 1
    else:
        if all_findings:
            print(f"\nPASSED (with {len(all_findings)} advisory findings "
                  f"below fail threshold)")
        else:
            print("\nPASSED (no findings)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
