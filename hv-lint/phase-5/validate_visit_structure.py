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
  5.11 Participant / visit seed -- the variable that seeds a participant or visit id must be
       the table's participant ID, the same one for both, and in the block's own table
  5.12 Id expression coverage -- an id / associated_visit / associated_participant expression
       the shared enumerator cannot parse was not checked by 1.8, 5.1, 5.2 or 5.11: WARNING.
       (5.2 also reports a fallback label with no Visit block that observed codes reach.)

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
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _paths import find_transform_dir  # noqa: E402
import _cohorts  # noqa: E402
import _known_issues  # noqa: E402
import _visit_ids  # noqa: E402
from _derivations import iter_nested_class_derivs  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "phase-3"))
import check_status_semantic as _css  # noqa: E402  (the one reader of the value-count index)

import yaml




# -- Severity -----------------------------------------------------------------

SEVERITY_RANK = {"CRITICAL": 5, "ERROR": 4, "HIGH": 3, "WARNING": 2, "INFO": 1}

# -- Cohort mapping -----------------------------------------------------------


# -- Regex patterns -----------------------------------------------------------

# Matches PHV accessions (with or without braces)
PHV_RE = re.compile(r'(phv\d{8})')

# Matches PHT accessions
PHT_RE = re.compile(r'^pht\d{6}$')

# Detects case() usage in expressions
CASE_USAGE_RE = re.compile(r'\bcase\s*\(')


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
    identity: str = ""            # known-issue block identity (_known_issues.file_identities)


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
    """The visit labels an id or associated_visit expression can emit, and whether it is dynamic.

    Delegates to the shared enumerator (``_visit_ids``), the parser 1.8 and 5.11 also use: case()
    arms are enumerated, comparison operands are never labels, a nested case() inside a uuid5
    seed composes with the text around it (FHS visit.yaml's ``case(...) + ' EXAM 7'``), and a
    ``(True, ...)`` fallback arm is dropped. An expression the enumerator cannot model yields no
    labels.

    Returns (set_of_labels, is_dynamic), where is_dynamic means the id is a uuid5.
    """
    is_dynamic = "uuid5" in str(expr)
    try:
        return _visit_ids.labels(_visit_ids.enumerate_ids(str(expr))), is_dynamic
    except _visit_ids.Unparsed:
        return set(), is_dynamic


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


def yaml_parse_error(file_path: Path) -> str | None:
    """The first line of the reason ``file_path`` cannot be read as YAML, or None if it can."""
    try:
        with file_path.open(encoding="utf-8") as f:
            yaml.safe_load(f)
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
        return str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
    return None


def parse_yaml_safe(file_path: Path) -> list[dict] | None:
    """Parse a YAML file and return its block list, or None on error."""
    try:
        with file_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
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
    identities = _known_issues.file_identities(blocks_data)

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
            identity=identities[idx],
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


def repr_age(expr: str) -> str:
    """An age expression quoted for a finding message: the known-issue fingerprint masks
    unquoted numbers, and a multiplier (`* 365` vs `* 12`) is the part that must not be masked.

    The quote must not occur inside the expression, or it ends the quoted run early and the
    numbers after it are masked (CARDIA YEAR 20: `... == 'M' else float(...) * 365`). An
    expression holding a single quote is wrapped in double quotes, with any double quote inside
    it shown as a single quote."""
    if expr == "no age":
        return expr
    if "'" not in expr:
        return f"'{expr}'"
    return '"' + expr.replace('"', "'") + '"'

def check_5_1_uniqueness(registry: VisitRegistry) -> list[Finding]:
    """5.1: one Visit id per (participant, label).

    Two blocks of one table emitting the same label is an ERROR: the table yields two Visit
    records with one id. Blocks of DIFFERENT tables emitting one label is a multi-table visit by
    design (ARIC's exam tables, CHS annual and phone contacts), reported as a WARNING that names
    the tables and their age expressions, because the duplicate Visit rows can disagree on age.
    Fallback labels are not compared: a (True, ...) arm is not a visit the table holds. Where
    observed codes do reach one that no Visit block defines, 5.2 reports it (check_5_12_id_coverage).
    """
    findings: list[Finding] = []

    if registry.uses_dynamic_ids:
        by_label: dict[str, list[VisitBlock]] = {}
        for vb in registry.blocks:
            for label in sorted(vb.visit_labels):
                by_label.setdefault(label, []).append(vb)
        for label, vbs in sorted(by_label.items()):
            if len(vbs) < 2:
                continue
            # Each table's anchor is its block with the smallest known-issue identity, not its
            # first in file order (as 1.2 anchors a duplicate group): the same-table ERROR is
            # reported on every other block of the table, and the anchor carries any
            # multi-table WARNING, so reordering visit.yaml re-keys neither, even when the two
            # blocks emit different label sets and so have different identities.
            by_pht: dict = {}
            for vb in vbs:
                by_pht.setdefault(vb.pht, []).append(vb)
            first_of: dict = {}
            for pht, members in by_pht.items():
                anchor = min(members, key=lambda v: v.identity)
                first_of[pht] = anchor
                for vb in members:
                    if vb is anchor:
                        continue
                    findings.append(Finding(
                        file=registry.file_path, block=vb.block_index, check="5.1",
                        severity="ERROR",
                        message=(f"Duplicate visit label '{label}' -- also in block "
                                 f"{anchor.block_index}, from the same table {pht}"),
                    ))
            # Sorted by table, not file order: reordering Visit blocks must not move the WARNING
            # to another block or reorder the message, which would re-key its baseline row.
            tables = sorted(first_of.values(), key=lambda v: str(v.pht))
            if len(tables) > 1:
                ages = sorted({vb2.age_start_expr or "no age" for vb2 in tables})
                for vb in tables[1:]:
                    findings.append(Finding(
                        file=registry.file_path, block=vb.block_index, check="5.1",
                        severity="WARNING",
                        message=(f"Visit id '{label}' emitted by {len(tables)} tables "
                                 f"({', '.join(str(x.pht) for x in tables)}); first in block "
                                 f"{tables[0].block_index}; age expressions: "
                                 f"{'; '.join(repr_age(a) for a in ages)}"),
                    ))
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


_ID_SLOTS = ("id", "associated_visit", "associated_participant")


def _id_exprs(block: dict):
    """``(class name, slot, expr)`` for every id-like slot at any depth of a block."""
    def walk(cls_name, cls_def):
        slots = cls_def.get("slot_derivations")
        if not isinstance(slots, dict):
            return
        for slot in _ID_SLOTS:
            sd = slots.get(slot)
            if isinstance(sd, dict) and sd.get("expr") not in (None, ""):
                yield cls_name, slot, str(sd["expr"])
        for sd in slots.values():
            if isinstance(sd, dict):
                for ncls, ndef in iter_nested_class_derivs(sd):
                    if isinstance(ndef, dict):
                        yield from walk(ncls, ndef)

    cds = block.get("class_derivations") if isinstance(block, dict) else None
    if isinstance(cds, dict):
        for cls_name, cls_def in cds.items():
            if isinstance(cls_def, dict):
                yield from walk(cls_name, cls_def)


def _fmt_codes(phv: str, codes: dict[str, int]) -> str:
    return f"{phv} " + ", ".join(f"'{c}' ({n:,} rows)" for c, n in sorted(codes.items()))


def check_5_12_id_coverage(
    yaml_files: list[Path], hv_root: Path, registry: VisitRegistry, counts_for,
) -> list[Finding]:
    """5.12, and 5.2 for fallback labels: what the label rules could not, or did not, check.

    * 5.12 WARNING: an id-like expression the enumerator cannot parse yields no labels and no
      seeds, so 1.8, 5.1, 5.2 and 5.11 skip it; a skip is reported, not silent.
    * 5.2 WARNING: an ``associated_visit`` fallback arm (``(True, 'FHS UNKNOWN VISIT')``) whose
      label no Visit block defines, when the table's observed codes reach it -- those rows link
      to a Visit that does not exist -- or when the reach cannot be evaluated. A fallback that
      no observed code reaches is not reported. ``counts_for(phv)`` gives ``{code: rows}``.
    """
    findings: list[Finding] = []
    for yf in yaml_files:
        rel = yf.relative_to(hv_root).as_posix()
        for idx, block in enumerate(parse_yaml_safe(yf) or []):
            for cls_name, slot, expr in _id_exprs(block):
                try:
                    values = _visit_ids.enumerate_ids(expr)
                except _visit_ids.Unparsed as exc:
                    findings.append(Finding(
                        file=rel, block=idx, check="5.12", severity="WARNING",
                        message=(f"{cls_name}.{slot} expression cannot be parsed ({exc}), so "
                                 f"1.8, 5.1, 5.2 and 5.11 did not check it")))
                    continue
                if slot != "associated_visit" or cls_name == "Visit":
                    continue
                missing = {v.label for v in values
                           if v.fallback and v.label and v.label not in registry.all_labels}
                if not missing:
                    continue
                try:
                    phv, reach = _visit_ids.fallback_reach(expr, counts_for)
                except _visit_ids.Unparsed as exc:
                    for label in sorted(missing):
                        findings.append(Finding(
                            file=rel, block=idx, check="5.2", severity="WARNING",
                            message=(f"{cls_name}.associated_visit fallback label '{label}' has "
                                     f"no Visit block, and whether observed codes reach it "
                                     f"cannot be evaluated ({exc})")))
                    continue
                for label in sorted(missing & set(reach)):
                    findings.append(Finding(
                        file=rel, block=idx, check="5.2", severity="WARNING",
                        message=(f"{cls_name}.associated_visit fallback label '{label}' has no "
                                 f"Visit block, and observed codes reach it: "
                                 f"{_fmt_codes(phv, reach[label])} -- those rows link to a "
                                 f"Visit that does not exist")))
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
            label = vb.visit_id or min(vb.visit_labels, default=f"block {vb.block_index}")
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
        label = vb.visit_id or min(vb.visit_labels, default=f"block {vb.block_index}")

        # Check that age slots exist
        if not vb.age_start_expr and not vb.age_end_expr:
            findings.append(Finding(
                file=registry.file_path,
                block=vb.block_index,
                check="5.4",
                severity="INFO",
                message=f"Visit '{label}' has no age_at_visit_start or age_at_visit_end "
                        f"(age is optional on Visit)",
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


#: dbGaP names of a participant-ID variable. A seed named anything else (FHS ``idtype``, the
#: cohort code 0/1/2/3/7/72) collapses every row of a block onto one fake participant per value.
PARTICIPANT_ID_NAMES = frozenset(n.casefold() for n in (
    "shareid", "SUBJECT_ID", "SUBJID", "Individual_ID", "sidno", "New_SUBJID", "GENEVA_ID",
    "dbGaP_Subject_ID",
))


def _seeds(slot_def) -> list[_visit_ids.Seed]:
    out: list[_visit_ids.Seed] = []
    for v in _visit_ids.slot_ids(slot_def):
        if v.namespace is not None or not v.label:
            out.extend(v.seeds)
    return list(dict.fromkeys(out))


def check_5_11_participant_seed(
    yaml_files: list[Path], hv_root: Path, detail_idx: dict[str, dict],
) -> list[Finding]:
    """5.11: the seed of every participant / visit id is the table's participant ID.

    For each Visit ``id``, ``associated_visit`` and ``associated_participant`` at any depth, the
    ``str({phv})`` seeds are read by the shared enumerator and checked BY NAME against the detail
    index:

      (a) a seed whose dbGaP name is not a participant ID (``idtype``, ``IDTYPE``, ...);
      (b) a visit seed set that differs from the participant seed set at the same level (the
          participant is inherited from the enclosing class when a nested one has none);
      (c) an unqualified seed in no enclosing table (the class's ``populated_from`` and those of
          the classes around it, as 3.5 reads reachability): a bare reference to another table
          is None in linkml-map, so participant and visit are emitted empty.

    Name-based on purpose: shareid and idtype are adjacent accessions in FHS tables but the
    distance varies by table, so a distance rule would be wrong. One ERROR per reason, so a
    second defect in a block that is already a known issue is a finding of its own.
    """
    findings: list[Finding] = []

    def name_of(seed: _visit_ids.Seed) -> tuple[str | None, str | None]:
        if not seed.phv.startswith("phv"):
            return seed.phv, None        # a bare column name such as {dbGaP_Subject_ID}
        rec = detail_idx.get(seed.phv)
        if not rec:
            return None, None
        return rec.get("name"), rec.get("pht")

    for yf in yaml_files:
        rel = yf.relative_to(hv_root).as_posix()
        blocks = parse_yaml_safe(yf) or []
        for idx, block in enumerate(blocks):
            if not isinstance(block, dict):
                continue
            cds = block.get("class_derivations")
            if not isinstance(cds, dict):
                continue
            reasons: list[str] = []

            def level(cls_name, cls_def, tables, inherited):
                slots = cls_def.get("slot_derivations")
                if not isinstance(slots, dict):
                    return
                visit = _seeds(slots.get("id") if cls_name == "Visit"
                               else slots.get("associated_visit"))
                own_part = _seeds(slots.get("associated_participant"))
                part = own_part or inherited
                for seed in visit + own_part:
                    name, pht = name_of(seed)
                    label = f"{{{seed.phv}}}" + (f" ({name}, {pht})" if pht else "")
                    if name is None:
                        continue
                    if name.casefold() not in PARTICIPANT_ID_NAMES:
                        reasons.append(f"seed {label} is not a participant ID")
                    if pht and not seed.table and tables and pht not in tables:
                        reasons.append(f"seed {label} is in another table than "
                                       f"{', '.join(tables)} and has no join, so it is None")
                if visit and part and {s.phv for s in visit} != {s.phv for s in part}:
                    reasons.append(
                        f"visit seed {sorted({s.phv for s in visit})} differs from participant "
                        f"seed {sorted({s.phv for s in part})}")
                for slot_def in slots.values():
                    if isinstance(slot_def, dict):
                        for ncls, ndef in iter_nested_class_derivs(slot_def):
                            if isinstance(ndef, dict):
                                npht = ndef.get("populated_from")
                                level(ncls, ndef, tables + ((npht,) if npht else ()), part)

            for cls_name, cls_def in cds.items():
                if isinstance(cls_def, dict):
                    top = cls_def.get("populated_from")
                    level(cls_name, cls_def, (top,) if top else (), [])
            for reason in dict.fromkeys(reasons):
                findings.append(Finding(
                    file=rel, block=idx, check="5.11", severity="ERROR",
                    message=f"participant / visit id seed: {reason}",
                ))
    return findings


# -- Index loading ------------------------------------------------------------

def load_phv_index(cache_dir: Path, cache_key: str) -> dict[str, str] | None:
    """The basic PHV->PHT index for a cohort, or ``None`` when absent.

    Raises ``_cohorts.CacheIntegrityError`` when its content is not what the manifest records.
    """
    if not (cache_dir / f"{cache_key}.json.gz").exists():
        return None
    return _cohorts.load_cache_artifact(cache_dir, cache_key)  # type: ignore[return-value]


def load_detail_index(cache_dir: Path, cache_key: str) -> dict[str, dict] | None:
    """The extended PHV detail index (with coll_interval) for a cohort, or ``None`` when absent.

    Raises ``_cohorts.CacheIntegrityError`` when its content is not what the manifest records.
    """
    if not (cache_dir / f"{cache_key}_detail.json.gz").exists():
        return None
    return _cohorts.load_cache_artifact(cache_dir, cache_key, "_detail")  # type: ignore[return-value]


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
        help="Directory with the release-keyed PHV and detail indexes (checks 5.3, 5.4, 5.8)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    # Stripped as `_cohorts.canonical_cohort` strips, so ` all` is `all` to Phases 3 and 5 alike.
    args.cohort = args.cohort.strip()
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
        # Canonicalised through the same `_cohorts` resolver the Phase 3 validators use, because
        # this validator is also run directly: `HCHS-SOL` must name `HCHS-ingest`, and
        # `copdgene` must name `COPDGene-ingest` on a case-sensitive filesystem.
        cohort_dirs = [_cohorts.canonical_cohort(args.cohort, base_dir)]
    named = args.cohort.lower() != "all"

    all_findings: list[Finding] = []
    # Any check that COULD NOT RUN fails the run on its own, independent of `--fail-on`.
    # Reporting it as an ERROR finding is not enough: findings are weighed against the
    # threshold, so `--fail-on critical` turned "this cohort was never checked" into a PASS --
    # the exact reading the comment below the cohort loop exists to forbid. 29a4c5dd made only
    # the release-mismatch path mandatory and left the three missing-input paths behind it.
    unrun_check = False
    cohorts_processed = 0
    cohorts_skipped: list[str] = []
    scanned_files: list[Path] = []

    for cohort in cohort_dirs:
        ingest_dir = base_dir / f"{cohort}-ingest"
        visit_file = ingest_dir / "visit.yaml"

        # A cohort NAMED on the command line with no ingest directory was never checked, so it
        # fails the run like any other unrun check; a WARNING skip here exits PASSED having read
        # nothing. `all` is derived from the directories, so it cannot reach this branch.
        if named and not ingest_dir.is_dir():
            all_findings.append(Finding(
                file=f"priority_variables_transform/{cohort}-ingest/",
                block=-1,
                check="5.0",
                severity="ERROR",
                message=(f"No ingest directory for cohort '{args.cohort}' (looked for "
                         f"priority_variables_transform/{cohort}-ingest/), so Phase 5 DID NOT "
                         f"RUN for it"),
            ))
            cohorts_skipped.append(cohort)
            unrun_check = True
            continue

        # An ingest directory without visit.yaml means none of 5.1-5.12 ran for that cohort, so
        # it is an unrun check whether the cohort was named or found under `all`: CI lints
        # `--cohort all`, and a deleted visit.yaml must fail it at any `--fail-on`.
        if not visit_file.exists():
            all_findings.append(Finding(
                file=f"priority_variables_transform/{cohort}-ingest/",
                block=-1,
                check="5.0",
                severity="ERROR",
                message=(f"No visit.yaml found for cohort {cohort}, so Phase 5 DID NOT "
                         f"RUN for it"),
            ))
            unrun_check = True
            cohorts_skipped.append(cohort)
            continue

        # Build visit registry
        registry = build_visit_registry(visit_file, hv_root)
        if registry is None:
            # None of 5.1-5.10 can run without a registry, so this is an unrun check at any
            # `--fail-on`, under `all` as well as for a named cohort.
            all_findings.append(Finding(
                file=visit_file.relative_to(hv_root).as_posix(),
                block=-1,
                check="5.0",
                severity="ERROR",
                message=(f"Could not parse visit.yaml or no Visit blocks for {cohort}, so "
                         f"Phase 5 DID NOT RUN for it"),
            ))
            cohorts_skipped.append(cohort)
            unrun_check = True
            continue

        # Scan all non-visit YAML files
        yaml_files = find_yaml_files(base_dir, cohort)
        scanned_files.extend(yaml_files)
        non_visit_files = [f for f in yaml_files if f.name != "visit.yaml"]

        # A spec Phase 5 cannot parse reads as empty to every check below, so its findings
        # vanish and a prune would remove their entries: it is an unrun check, at any --fail-on.
        for yf in non_visit_files:
            error = yaml_parse_error(yf)
            if error:
                all_findings.append(Finding(
                    file=yf.relative_to(hv_root).as_posix(), block=-1, check="5.0",
                    severity="ERROR",
                    message=(f"Could not parse {yf.name} ({error}), so Phase 5 DID NOT RUN on "
                             f"it"),
                ))
                unrun_check = True

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

        # 5.12 (and 5.2 for fallback labels): id expressions the label rules could not check.
        stats = (_css.load_stats_index(Path(args.cache_dir), cache_key)
                 if args.cache_dir else None) or {}
        all_findings.extend(check_5_12_id_coverage(
            yaml_files, hv_root, registry,
            lambda phv: stats[phv].counts if phv in stats else None))

        phv_index = None
        mismatch = None
        release_ok = True

        # A check that CANNOT run is reported as an ERROR against the cohort, not as a skip:
        # an unrun check that exits clean is indistinguishable from a passing one. Both the
        # "no directory was supplied" and "the file is not there" cases count.
        if not args.cache_dir:
            all_findings.append(Finding(
                f"priority_variables_transform/{cohort}-ingest", 0, "5.3/5.4", "ERROR",
                f"no --cache-dir supplied, so check 5.3 and the PHV-index half of 5.4 DID NOT "
                f"RUN for {cohort} (5.4's structural checks still ran)"))
            unrun_check = True
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
                    f"{_cohorts.declaration_file(cohort)}"))
            else:
                mismatch = _cohorts.study_mismatch(args.cache_dir, cache_key, declared)
                if mismatch:
                    all_findings.append(Finding(
                        f"priority_variables_transform/{cohort}-ingest", 0, "5.3/5.4/5.8",
                        "ERROR", f"declared release {declared}: {mismatch}"))

            # The release check is MANDATORY, so it cannot rest on a finding alone: findings
            # are weighed against `--fail-on`, and `--fail-on critical` would reduce a
            # cache/version mismatch to advisory. It also must not go on to CHECK against the
            # mismatched index -- that reports PHVs absent from the wrong release as mapping
            # errors, the exact confusion the check exists to remove. So the index is not
            # loaded, which leaves 5.3/5.4/5.8 unrun, and the run fails independently of the
            # severity threshold. Phase 3 does the same by returning 1.
            #
            # Deliberately NOT `continue`: 5.6, 5.9 and 5.10 read no cache, and a cohort with a
            # stale cache should still have its visit structure reported.
            release_ok = bool(declared) and not mismatch
            if not release_ok:
                unrun_check = True

        integrity_error = None
        if args.cache_dir and release_ok:
            try:
                phv_index = load_phv_index(Path(args.cache_dir), cache_key)
            except _cohorts.CacheIntegrityError as exc:
                phv_index, integrity_error = None, exc
                all_findings.append(Finding(
                    f"priority_variables_transform/{cohort}-ingest", 0, "5.3/5.4", "ERROR",
                    f"{exc} -- so check 5.3 and the PHV-index half of 5.4 DID NOT RUN"))
                unrun_check = True
            if not phv_index and integrity_error is None:
                all_findings.append(Finding(
                    f"priority_variables_transform/{cohort}-ingest", 0, "5.3/5.4", "ERROR",
                    f"no PHV index for {cohort} (looked for '{cache_key}.json.gz' in "
                    f"{args.cache_dir}), so check 5.3 and the PHV-index half of 5.4 DID NOT "
                    f"RUN (5.4's structural checks still ran)"))
                unrun_check = True

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
        if not release_ok:
            pass  # the release check above already reported it and failed the run
        elif not args.cache_dir:
            all_findings.append(Finding(
                f"priority_variables_transform/{cohort}-ingest", 0, "5.8", "ERROR",
                f"no --cache-dir supplied, so check 5.8 DID NOT RUN for {cohort}"))
            unrun_check = True
        else:
            try:
                detail_idx = load_detail_index(Path(args.cache_dir), cache_key)
            except _cohorts.CacheIntegrityError as exc:
                detail_idx, integrity_error = None, exc
                all_findings.append(Finding(
                    f"priority_variables_transform/{cohort}-ingest", 0, "5.8", "ERROR",
                    f"{exc} -- so check 5.8 DID NOT RUN"))
                unrun_check = True
            # An ABSENT detail index is an ERROR, by the same rule stated above the PHV index
            # guard: a missing file made 5.8 exit clean, which reads as a pass. Only a detail
            # index that is PRESENT and holds no intervals is a legitimate skip -- that is a
            # fact about the cohort, not a missing input.
            if integrity_error is not None and detail_idx is None:
                pass  # reported above; the run already fails
            elif detail_idx is None:
                all_findings.append(Finding(
                    f"priority_variables_transform/{cohort}-ingest", 0, "5.8/5.11", "ERROR",
                    f"no detail index for {cohort} (looked for '{cache_key}_detail.json.gz' "
                    f"in {args.cache_dir}), so checks 5.8 and 5.11 DID NOT RUN"))
                unrun_check = True
            else:
                # 5.11: participant / visit seeds, by dbGaP variable name
                all_findings.extend(
                    check_5_11_participant_seed(yaml_files, hv_root, detail_idx)
                )
                # Check if this cohort has any coll_interval data
                n_ci = sum(1 for v in detail_idx.values() if v.get("coll_interval"))
                if n_ci > 0:
                    all_findings.extend(
                        check_5_8_collection_interval(
                            yaml_files, hv_root, detail_idx
                        )
                    )
                else:
                    # A skip that prints nothing reads as "no mismatch": say it in the findings,
                    # so a 5.8 pass is not taken for coverage this cohort does not have.
                    all_findings.append(Finding(
                        f"priority_variables_transform/{cohort}-ingest", 0, "5.8", "WARNING",
                        f"5.8 did not run for {cohort}: its detail index has no coll_interval "
                        f"(collection interval) for any variable, so collection-interval "
                        f"mismatches are not checked here"))

        # 5.9: Visit uuid5 format compliance
        all_findings.extend(check_5_9_uuid5_format(registry, cohort_refs))

        # 5.10: Visit uuid5 namespace consistency
        all_findings.extend(
            check_5_10_uuid5_namespace(
                registry, cohort_refs, yaml_files, hv_root
            )
        )

        cohorts_processed += 1

    # Known issues, stale entries and the WARNING ratchet (hv-lint/_known_issues.py).
    all_findings.extend(_known_issues.finalize(
        all_findings,
        checks={"5.0", "5.1", "5.2", "5.3", "5.4", "5.6", "5.8", "5.9", "5.10", "5.11", "5.12"},
        scanned_files=scanned_files, make_finding=Finding))

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
    elif unrun_check:
        # Checked BEFORE the pass branch and independent of `--fail-on`: a threshold that can
        # downgrade the mandatory release check to advisory is not a mandatory check.
        # `--fail-on critical` did exactly that, and the run then reported PASSED having
        # skipped 5.3/5.4/5.8 for the cohort whose cache was the wrong release.
        print("\nFAILED: at least one check DID NOT RUN -- a named cohort has no ingest "
              "directory, a cohort has no visit.yaml, a visit.yaml could not be parsed or has "
              "no Visit blocks, another spec could not be parsed, the mandatory dbGaP release check did not pass, or a required cache "
              "input was missing (see the ERROR findings above). This is not weighed against "
              "--fail-on.")
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
