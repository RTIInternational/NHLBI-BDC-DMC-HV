#!/usr/bin/env python3
"""HV-Lint Phase 1: YAML Structural & Formatting Checks.

Validates transformation YAML files for structural correctness.
No schema, no linkml imports, no dbGaP data required -- PyYAML only.

Checks:
    1.1  Expression syntax validation (balanced braces, non-empty)
    1.2  Duplicate block detection (same class + pht + visit + concept)
    1.3  Inline comment detection (trailing # on active code lines)
    1.4  Unquoted brace unit detection ({xxx}/yyy pattern not surrounded by quotes)
    1.5  Unquoted expr value starting with { (YAML will misparse as flow mapping)
    1.7  Semantic duplicate DrugExposure blocks (same source PHV, different vocab codes)
    1.9  Common typo detection (known misspellings in slot names and values)
    1.10 Space-in-key detection (illegal spaces in YAML key names)

Usage:
    python hv-lint/phase-1/validate_yaml_structure.py
    python hv-lint/phase-1/validate_yaml_structure.py --cohort ARIC
    python hv-lint/phase-1/validate_yaml_structure.py --fail-on critical
    python hv-lint/phase-1/validate_yaml_structure.py --file path/to/file.yaml
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _paths import find_transform_dir  # noqa: E402
from _derivations import iter_nested_class_derivs  # noqa: E402

TRANSFORM_DIR = find_transform_dir()



COHORTS = [
    "ARIC", "CARDIA", "CHS", "COPDGene",
    "FHS", "HCHS", "JHS", "MESA", "SPIROMICS", "WHI",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Precompiled regex
_EMPTY_VAR_REF_RE = re.compile(r"\{\{\s*\}\}")

# Inline comment detection: active YAML line with trailing # comment.
# Matches lines where a YAML key-value pair is followed by a # comment.
# Excludes:
#   - Standalone comment lines (entire line starts with #)
#   - Lines where # is inside a quoted string
#   - Lines that are blank
# This is a heuristic -- it catches the common patterns but may miss edge
# cases involving complex quoting. Known safe for HV YAML files.
_INLINE_COMMENT_RE = re.compile(
    r"""
    ^                          # start of line
    (\s*)                      # leading whitespace
    (?!\#)                     # NOT a standalone comment line
    (.+?)                      # active YAML content (non-greedy)
    \s+                        # whitespace before comment
    \#\s                       # hash + space = inline comment
    (.+)                       # comment text
    $                          # end of line
    """,
    re.VERBOSE,
)

# Check 1.4: Unquoted UCUM unit value containing {xxx}/yyy pattern.
# Matches: value: {#}/wk  or  value: {servings}/wk  (not wrapped in quotes).
# The leading { causes YAML to treat the value as a flow mapping, silently
# misparsing it -- so this must run before yaml.safe_load.
_UNQUOTED_BRACE_UNIT_RE = re.compile(r"^\s+\w[\w_-]*:\s+\{[^}\s]+\}/\S")

# Check 1.5: Unquoted expr value starting with {.
# Matches: expr: {phv00112960} + ...  (no quote wrapping the value).
# Quoted forms like expr: "{phv...}" or expr: '{phv...}' are safe.
_UNQUOTED_EXPR_RE = re.compile(r"^\s+expr:\s+\{")

# Check 1.9: Common typo dictionary.
# Maps known misspellings -> correct spelling. Checked against raw file text.
# Sourced from HV-Audit Dimension 4 checks (4b, 4f) -- migrated to Lint for
# deterministic CI detection.
KNOWN_TYPOS: dict[str, str] = {
    "expsoure_provenance": "exposure_provenance",
    "expsoure": "exposure",
    "vetricular": "ventricular",
    "diagnoisis": "diagnosis",
    "observaton": "observation",
    "measurment": "measurement",
    "particpant": "participant",
    "assocated": "associated",
}

# Check 1.10: Space-in-key detection.
# Matches YAML keys with internal spaces (e.g., "populated from:" instead of
# "populated_from:"). These silently create wrong keys that the pipeline ignores.
_SPACE_IN_KEY_RE = re.compile(r"^\s+(populated from|slot derivations|class derivations|value mappings|object derivations|unit conversion|source unit)\s*:", re.IGNORECASE)

# Files to skip entirely (known issues).
# Cleared 2026-03-15: starting fresh to re-confirm known issues.
KNOWN_ISSUES: dict[str, str] = {}

# Severity ranking for --fail-on filtering
SEVERITY_RANK = {"CRITICAL": 5, "ERROR": 4, "HIGH": 3, "WARNING": 2, "INFO": 1}

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    file: str
    block: int          # -1 for line-level checks (1.3)
    check: str          # e.g., "1.1"
    severity: str       # CRITICAL, ERROR, HIGH, WARNING, INFO
    message: str
    line: int = 0       # source line number (0 = unknown)

    def terminal_line(self) -> str:
        sev = self.severity[:5].ljust(5)
        loc = f"line {self.line:>4}" if self.line else f"block {self.block:>3}"
        return f"  {sev}  {loc}  [{self.check}] {self.message}"

    def gh_annotation(self) -> str:
        level = {
            "CRITICAL": "error", "ERROR": "error", "HIGH": "warning",
            "WARNING": "warning", "INFO": "notice",
        }.get(self.severity, "notice")
        file_esc = (self.file.replace("%", "%25").replace("\r", "%0D")
                    .replace("\n", "%0A").replace(":", "%3A").replace(",", "%2C"))
        msg_esc = self.message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        loc = f"block {self.block}" if not self.line else f"line {self.line}"
        return f"::{level} file={file_esc}::HV-Lint [{self.check}] {msg_esc} ({loc})"


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
# Check 1.1: Expression syntax validation
# ---------------------------------------------------------------------------

def check_expression_syntax(
    expr: str, class_name: str, slot_name: str,
    block_idx: int, rel_path: str
) -> list[Finding]:
    """Check 1.1: Basic expression syntax validation.

    - Balanced Jinja block delimiters: {%  ==  %}
    - Balanced Jinja variable delimiters: {{  ==  }}
    - Non-empty expression
    - No empty variable references ({{ }})
    """
    findings = []

    if expr.count("{%") != expr.count("%}"):
        findings.append(Finding(
            rel_path, block_idx, "1.1", "ERROR",
            f"Unbalanced {{% %}} in expr on {class_name}.{slot_name}"
        ))
    if expr.count("{{") != expr.count("}}"):
        findings.append(Finding(
            rel_path, block_idx, "1.1", "ERROR",
            f"Unbalanced {{{{ }}}} in expr on {class_name}.{slot_name}"
        ))

    if not expr.strip():
        findings.append(Finding(
            rel_path, block_idx, "1.1", "ERROR",
            f"Empty expr on {class_name}.{slot_name}"
        ))

    if _EMPTY_VAR_REF_RE.search(expr):
        findings.append(Finding(
            rel_path, block_idx, "1.1", "WARNING",
            f"Empty variable reference '{{{{ }}}}' in expr on {class_name}.{slot_name}"
        ))

    return findings


def walk_expressions(block: dict, block_idx: int, rel_path: str) -> list[Finding]:
    """Walk all class_derivations and slot_derivations to find expr fields."""
    findings: list[Finding] = []
    class_derivs = block.get("class_derivations")
    if not isinstance(class_derivs, dict):
        return findings

    def _recurse(class_derivs: dict, prefix: str = "") -> None:
        for class_name, class_def in class_derivs.items():
            if not isinstance(class_def, dict):
                continue
            slot_derivs = class_def.get("slot_derivations")
            if not isinstance(slot_derivs, dict):
                continue
            for slot_name, slot_def in slot_derivs.items():
                if not isinstance(slot_def, dict):
                    continue
                expr = slot_def.get("expr")
                if isinstance(expr, str):
                    findings.extend(check_expression_syntax(
                        expr, f"{prefix}{class_name}", slot_name,
                        block_idx, rel_path
                    ))
                # Recurse into nested class derivations (list-based or legacy
                # object_derivations)
                for nested_name, nested_spec in iter_nested_class_derivs(slot_def):
                    if isinstance(nested_spec, dict):
                        _recurse(
                            {nested_name: nested_spec},
                            f"{prefix}{class_name}.{slot_name}."
                        )

    _recurse(class_derivs)
    return findings


# ---------------------------------------------------------------------------
# Check 1.2: Duplicate block detection
# ---------------------------------------------------------------------------

def get_block_identity(block: dict) -> list[tuple]:
    """Extract distinguishing identity for each class in a block.

    Identity tuple: (class, pht, visit, concept, distinguishing_phv)
    See assumption A8 in HV-Lint-Reference.md for the full identity schema.
    """
    if not isinstance(block, dict):
        return []
    identities = []
    class_derivs = block.get("class_derivations")
    if not isinstance(class_derivs, dict):
        return identities

    def _d(val) -> dict:
        return val if isinstance(val, dict) else {}

    def _s(val, maxlen: int = 0) -> str:
        t = val if isinstance(val, str) else str(val) if val is not None else ""
        return t[:maxlen] if maxlen else t

    for cls_name, cls_def in class_derivs.items():
        if not isinstance(cls_def, dict):
            continue
        pht = cls_def.get("populated_from", "")
        slots = cls_def.get("slot_derivations")
        slots = slots if isinstance(slots, dict) else {}

        av = _d(slots.get("associated_visit"))
        visit = (_s(av.get("value", ""))
                 or _s(av.get("populated_from", ""))
                 or _s(av.get("expr", "")))

        concept = ""
        distinguishing_phv = ""

        if cls_name == "Condition":
            cc = _d(slots.get("condition_concept"))
            concept = (_s(cc.get("value", ""))
                       or _s(cc.get("populated_from", ""))
                       or _s(cc.get("expr", "")))
            cs = _d(slots.get("condition_status"))
            cs_phv = (_s(cs.get("populated_from", ""))
                      or _s(cs.get("expr", "")))
            # Include value_mappings to distinguish blocks with same PHV
            # but different coded interpretations (e.g., PRESENT vs
            # HISTORICAL, or partial vs full mappings)
            vm = cs.get("value_mappings")
            vm_sig = ("|".join(f"{k}:{v}" for k, v in sorted(vm.items()))
                      if isinstance(vm, dict) else "")
            # Include condition_provenance to distinguish clinical vs
            # self-reported diagnoses from the same source variable
            cp = _s(_d(slots.get("condition_provenance")).get("value", ""))
            distinguishing_phv = f"{cs_phv}|{cp}|{vm_sig}"
        elif cls_name == "ResearchStudy":
            nm = _d(slots.get("name"))
            concept = (_s(nm.get("value", ""))
                       or _s(nm.get("expr", "")))
        elif cls_name == "MeasurementObservationSet":
            mt = _d(slots.get("method_type"))
            concept = (_s(mt.get("value", ""))
                       or _s(mt.get("expr", "")))
            # Extract nested observation PHV (direct nesting pattern)
            obs = _d(slots.get("observations"))
            for nested_cls, nested_def in obs.items():
                nd = _d(nested_def)
                ns = _d(nd.get("slot_derivations"))
                vd = _d(ns.get("value_decimal") or ns.get("value_integer"))
                phv = (_s(vd.get("populated_from", ""))
                       or _s(vd.get("expr", "")))
                if phv:
                    distinguishing_phv = phv
                    break
        elif cls_name in ("MeasurementObservation", "Observation", "SdohObservation"):
            ot = _d(slots.get("observation_type"))
            concept = (_s(ot.get("value", ""))
                       or _s(ot.get("expr", ""))
                       or _s(ot.get("populated_from", "")))
            # Include method_type in identity -- blocks with different
            # method_type values (e.g., fasting protocol variations)
            # are NOT duplicates
            mt = _d(slots.get("method_type"))
            mt_sig = (_s(mt.get("value", ""))
                      or _s(mt.get("expr", ""))
                      or _s(mt.get("populated_from", "")))
            for qty_name, qty in iter_nested_class_derivs(slots.get("value_quantity")):
                if qty_name != "Quantity":
                    continue
                qty_slots = _d(_d(qty).get("slot_derivations"))
                # Bug fix: also check value_concept, not just
                # value_decimal/value_integer -- blocks mapping
                # different PHVs via value_concept are NOT duplicates
                vd = _d(qty_slots.get("value_decimal")
                        or qty_slots.get("value_integer")
                        or qty_slots.get("value_concept"))
                distinguishing_phv = (_s(vd.get("populated_from", ""))
                                      or _s(vd.get("expr", "")))
                break
            # Fallback: value_enum (direct slot, not nested in Quantity)
            if not distinguishing_phv:
                ve = _d(slots.get("value_enum"))
                distinguishing_phv = (_s(ve.get("populated_from", ""))
                                      or _s(ve.get("expr", "")))
            # Append method_type signature to distinguisher
            if mt_sig:
                distinguishing_phv = f"{distinguishing_phv}|mt:{mt_sig}"
        elif cls_name == "DrugExposure":
            dc = _d(slots.get("drug_concept"))
            concept = _s(dc.get("value", "")) or _s(dc.get("expr", ""))
        elif cls_name == "Procedure":
            pc = _d(slots.get("procedure_concept"))
            concept = (_s(pc.get("value", ""))
                       or _s(pc.get("expr", ""))
                       or _s(pc.get("populated_from", "")))
        elif cls_name == "Person":
            # Distinguish Person blocks by nested cause_of_death concept
            # (e.g., ARIC cause_of_death.yaml has ~11 blocks per table,
            # each mapping a different ICD-10 code + order)
            # Bug fix: collect ALL derivations, not just the first -- Person
            # blocks may have multiple cause_of_death derivations with distinct
            # cause concepts
            cod_parts = []
            for cod_name, cod_cls in iter_nested_class_derivs(slots.get("cause_of_death")):
                if cod_name != "CauseOfDeath":
                    continue
                cod_slots = _d(_d(cod_cls).get("slot_derivations"))
                cause = _d(cod_slots.get("cause") or cod_slots.get("cause_of_death_concept"))
                part = (_s(cause.get("value", ""))
                        or _s(cause.get("expr", ""))
                        or _s(cause.get("populated_from", "")))
                if part:
                    cod_parts.append(part)
            distinguishing_phv = "|".join(cod_parts)
        elif cls_name == "Visit":
            # Bug fix: check id.value, id.expr, AND name -- FHS Visit
            # blocks have no id slot; they use name.expr with different
            # "EXAM N" suffixes and different age PHVs
            id_deriv = _d(slots.get("id"))
            name_deriv = _d(slots.get("name"))
            concept = (_s(id_deriv.get("value", ""))
                       or _s(id_deriv.get("expr", ""))
                       or _s(name_deriv.get("value", ""))
                       or _s(name_deriv.get("expr", "")))
            # Also use age_at_visit_start as distinguisher (different
            # exams reference different age PHVs)
            avs = _d(slots.get("age_at_visit_start"))
            distinguishing_phv = (_s(avs.get("populated_from", ""))
                                  or _s(avs.get("expr", "")))
        elif cls_name == "Demography":
            # Include actual slot values (not just slot names) to
            # distinguish blocks with identical keys but different
            # PHV assignments or expressions
            slot_vals = []
            for sn, sv in sorted(slots.items()):
                sd = _d(sv)
                pf = sd.get("populated_from", "")
                ex = sd.get("expr", "")
                val = sd.get("value", "")
                slot_vals.append(f"{sn}:{pf or ex or val}")
            distinguishing_phv = "|".join(slot_vals)

        identities.append(
            (cls_name, _s(pht), _s(visit), _s(concept), _s(distinguishing_phv))
        )
    return identities


def check_duplicates(blocks: list[dict], rel_path: str) -> list[Finding]:
    """Check 1.2: Detect duplicate blocks within a single file."""
    findings: list[Finding] = []
    seen: dict[tuple[str, str, str, str, str], int] = {}

    for idx, block in enumerate(blocks):
        for identity in get_block_identity(block):
            if identity in seen:
                first_idx = seen[identity]
                cls, pht, visit, concept, dist = identity
                # Truncate only for display -- full strings used for comparison
                v_disp = visit[:80] + "..." if len(visit) > 80 else visit
                c_disp = concept[:80] + "..." if len(concept) > 80 else concept
                # Content-equality safety guard: only flag as ERROR
                # if blocks are byte-identical.  Identity-only
                # collisions (same tuple, different content) are
                # WARNINGS -- the identity function may be incomplete.
                import yaml as _yaml
                b1 = _yaml.dump(blocks[first_idx], sort_keys=True)
                b2 = _yaml.dump(block, sort_keys=True)
                if b1 == b2:
                    severity = "ERROR"
                    suffix = ""
                else:
                    severity = "WARNING"
                    suffix = (" -- identity collision but content DIFFERS; "
                              "review manually before removing")
                findings.append(Finding(
                    rel_path, idx, "1.2", severity,
                    f"Duplicate block: {cls} with pht={pht} "
                    f"visit='{v_disp}' concept='{c_disp}' "
                    f"(first seen in block {first_idx}){suffix}"
                ))
            else:
                seen[identity] = idx
    return findings


# ---------------------------------------------------------------------------
# Check 1.7: Semantic duplicate DrugExposure blocks
# ---------------------------------------------------------------------------

def check_drug_exposure_duplicates(blocks: list[dict], rel_path: str) -> list[Finding]:
    """Check 1.7: Detect DrugExposure blocks with the same source PHV but different vocab codes.

    A common error pattern is mapping the same source variable (e.g., a
    yes/no medication question) to two DrugExposure blocks -- one with an
    ATC code and one with a VANDF code -- when only one vocabulary mapping
    is needed. This produces duplicate drug entries per participant.
    """
    findings: list[Finding] = []

    # Collect (block_idx, source_phv, concept_value) for all DrugExposure blocks
    drug_blocks: list[tuple[int, str, str]] = []

    for idx, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue
        class_derivs = block.get("class_derivations")
        if not isinstance(class_derivs, dict):
            continue

        for cls_name, cls_def in class_derivs.items():
            if cls_name != "DrugExposure":
                continue
            if not isinstance(cls_def, dict):
                continue
            slots = cls_def.get("slot_derivations")
            if not isinstance(slots, dict):
                continue

            # Extract source PHV from drug_concept
            dc = slots.get("drug_concept", {})
            if not isinstance(dc, dict):
                dc = {}
            dc_expr = dc.get("expr", "") or ""
            dc_value = dc.get("value", "") or ""
            dc_pf = dc.get("populated_from", "") or ""
            concept = dc_value or dc_expr

            # Extract the source PHV(s) from case() or value_mappings
            source_phv = dc_pf
            if not source_phv and dc_expr:
                # Extract PHV references from case() expressions
                phvs = sorted(set(re.findall(r'phv\d+', dc_expr)))
                source_phv = "|".join(phvs) if phvs else ""

            # Also check value_mappings source
            vm = dc.get("value_mappings")
            if isinstance(vm, dict) and not source_phv:
                # value_mappings keys are source values, not PHVs
                # The populated_from or expr is the source
                pass

            if source_phv:
                drug_blocks.append((idx, source_phv, concept))

    # Group by source_phv and flag groups with >1 distinct concept
    from collections import defaultdict
    by_source: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for idx, src, concept in drug_blocks:
        by_source[src].append((idx, concept))

    for src, entries in by_source.items():
        if len(entries) < 2:
            continue
        concepts = set(c for _, c in entries)
        if len(concepts) < 2:
            continue
        # Multiple blocks, same source, different concepts -- likely duplicates
        block_ids = ", ".join(str(i) for i, _ in entries)
        concept_strs = ", ".join(sorted(concepts))
        findings.append(Finding(
            rel_path, entries[0][0], "1.7", "WARNING",
            f"DrugExposure blocks {block_ids} share source "
            f"'{src}' but map to different concepts: {concept_strs} -- "
            f"possible semantic duplicate (same medication, multiple vocabs)"
        ))

    return findings


# ---------------------------------------------------------------------------
# Check 1.3: Inline comment detection
# ---------------------------------------------------------------------------

def check_inline_comments(file_path: Path, rel_path: str) -> list[Finding]:
    """Check 1.3: Detect trailing inline comments on active YAML lines.

    Inline comments (e.g., `value: PRESENT # REVIEW`) are distinct from
    standalone comment lines (entire line starting with #).
    """
    findings: list[Finding] = []
    try:
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return findings

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        # Skip blank lines and standalone comment lines
        if not stripped or stripped.startswith("#"):
            continue
        # Skip lines that are list items starting with "- #" (commented list items)
        if stripped.startswith("- #"):
            continue

        m = _INLINE_COMMENT_RE.match(line)
        if m:
            content = m.group(2).rstrip()
            comment = m.group(3).strip()
            # Avoid false positives: # inside quoted strings
            # Simple heuristic: if the content before # has unbalanced quotes,
            # the # is likely inside a string, not a comment.
            single_q = content.count("'")
            double_q = content.count('"')
            if single_q % 2 != 0 or double_q % 2 != 0:
                continue
            findings.append(Finding(
                rel_path, -1, "1.3", "ERROR",
                f"Inline comment: '{comment[:60]}' on active line",
                line=i,
            ))

    return findings


# ---------------------------------------------------------------------------
# Check 1.4 & 1.5: Raw-text pre-parse checks
# ---------------------------------------------------------------------------

def check_unquoted_brace_units(file_path: Path, rel_path: str) -> list[Finding]:
    """Check 1.4 & 1.5: Detect unquoted values that YAML misparsing as flow mappings.

    Check 1.4 -- unit values like `{#}/wk` or `{servings}/wk` not wrapped in quotes.
    Check 1.5 -- expr values that start with `{` not wrapped in quotes, e.g.:
                 `expr: {phv00112960} + {phv00112961} + {phv00112962}`

    Both cases: the leading `{` causes YAML to attempt flow-mapping parsing.
    This either produces a silent wrong value or a hard YAMLError. Must run
    before yaml.safe_load -- the parsed tree is already corrupt by then.

    Source: commits 4361f51 and 20888f4 (Check 1.4), commit 4361f51 (Check 1.5)
    on RTIInternational/NHLBI-BDC-DMC-HV feature/414-measobs-curation-fixes.
    """
    findings: list[Finding] = []
    try:
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return findings

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Check 1.4: any key whose value is {xxx}/yyy (unquoted)
        if _UNQUOTED_BRACE_UNIT_RE.match(line):
            findings.append(Finding(
                rel_path, -1, "1.4", "ERROR",
                f"Unquoted brace unit value -- YAML will misparse as flow mapping: "
                f"{stripped[:80]}",
                line=i,
            ))

        # Check 1.5: expr value starts with { (unquoted)
        if _UNQUOTED_EXPR_RE.match(line):
            findings.append(Finding(
                rel_path, -1, "1.5", "CRITICAL",
                f"Unquoted expr value starting with '{{' -- YAML will misparse as "
                f"flow mapping: {stripped[:80]}",
                line=i,
            ))

    return findings


# ---------------------------------------------------------------------------
# Check 1.9: Common typo detection
# ---------------------------------------------------------------------------

def check_common_typos(file_path: Path, rel_path: str) -> list[Finding]:
    """Check 1.9: Detect known misspellings in YAML file text.

    Scans the raw file text for entries in KNOWN_TYPOS dictionary.
    Reports each unique typo once per file with line numbers.
    """
    findings: list[Finding] = []
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings

    text_lower = text.lower()
    for typo, correct in KNOWN_TYPOS.items():
        if typo.lower() in text_lower:
            # Find the first line containing the typo for reporting
            for i, line in enumerate(text.splitlines(), start=1):
                if typo.lower() in line.lower():
                    findings.append(Finding(
                        rel_path, -1, "1.9", "ERROR",
                        f"Typo '{typo}' detected (should be '{correct}')",
                        line=i,
                    ))
                    break  # One finding per typo per file
    return findings


# ---------------------------------------------------------------------------
# Check 1.10: Space-in-key detection
# ---------------------------------------------------------------------------

def check_space_in_key(file_path: Path, rel_path: str) -> list[Finding]:
    """Check 1.10: Detect YAML keys with illegal internal spaces.

    Keys like 'populated from:' (instead of 'populated_from:') are silently
    accepted by YAML parsers but create wrong keys that the pipeline ignores,
    causing silent data loss.
    """
    findings: list[Finding] = []
    try:
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return findings

    for i, line in enumerate(lines, start=1):
        m = _SPACE_IN_KEY_RE.match(line)
        if m:
            bad_key = m.group(1)
            correct_key = bad_key.replace(" ", "_")
            findings.append(Finding(
                rel_path, -1, "1.10", "CRITICAL",
                f"Space in key '{bad_key}:' (should be '{correct_key}:')",
                line=i,
            ))
    return findings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="HV-Lint Phase 1: YAML structural & formatting checks"
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
    args = parse_args()
    in_ci = os.environ.get("GITHUB_ACTIONS") == "true"

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
    skipped = []

    for file_path in yaml_files:
        rel_path = file_path.as_posix()

        # Skip known issues
        if any(rel_path.endswith(k) or k in rel_path for k in KNOWN_ISSUES):
            skip_key = next((k for k in KNOWN_ISSUES if k in rel_path), rel_path)
            skipped.append((rel_path, KNOWN_ISSUES.get(skip_key, "known issue")))
            continue

        # -- Check 1.3: Inline comments (line-level, before YAML parse) --
        all_findings.extend(check_inline_comments(file_path, rel_path))

        # -- Check 1.4: Unquoted brace units (raw text, before YAML parse) --
        all_findings.extend(check_unquoted_brace_units(file_path, rel_path))

        # -- Check 1.9: Common typos (raw text, before YAML parse) --
        all_findings.extend(check_common_typos(file_path, rel_path))

        # -- Check 1.10: Space-in-key (raw text, before YAML parse) --
        all_findings.extend(check_space_in_key(file_path, rel_path))

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

            # 1.1: Expression syntax
            all_findings.extend(walk_expressions(block, idx, rel_path))

        # 1.2: Duplicate blocks within file
        all_findings.extend(check_duplicates(blocks, rel_path))

        # 1.7: Semantic duplicate DrugExposure blocks
        all_findings.extend(check_drug_exposure_duplicates(blocks, rel_path))

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
    print("HV-Lint Phase 1: YAML Structural & Formatting Results")
    print(f"{'='*70}")
    print(f"Files checked:  {files_checked}")
    print(f"Blocks checked: {blocks_checked}")
    if skipped:
        print(f"Files skipped:  {len(skipped)} (known issues)")

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
            # Shorten Windows absolute paths too
            if "priority_variables_transform" in short:
                short = short[short.index("priority_variables_transform") + len("priority_variables_transform/"):]
            print(f"\n{short}:")
            for f in sorted(findings_by_file[fpath],
                            key=lambda x: (x.line or x.block * 1000, x.check)):
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
    lines.append("## HV-Lint Phase 1: YAML Structural & Formatting Results\n")
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
                           f.file, f.line or f.block * 1000, f.check)
        )
        shown = sorted_findings[:limit]
        lines.append(f"### Findings (showing {len(shown)} of {len(findings)})\n")
        lines.append("| Severity | File | Location | Check | Message |")
        lines.append("|----------|------|----------|-------|---------|")
        for f in shown:
            short = f.file.replace("priority_variables_transform/", "")
            loc = f"line {f.line}" if f.line else f"block {f.block}"
            msg = (f.message.replace("\r", " ").replace("\n", " ")
                   .replace("|", "\\|"))
            lines.append(f"| {f.severity} | {short} | {loc} | {f.check} | {msg} |")
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
