"""
compare_source_output.py — HV-DataQC Component 3

Compare aggregate summaries from extract_source_summaries.py (raw dbGaP source)
and extract_output_summaries.py (dm-bip harmonized output). Runs checks C1–C10
and produces a Markdown + JSON report.

No hardcoded paths. All paths are explicit CLI arguments.

CHECKS:
  C1  N Preservation        — total participant / row counts
  C2  N Loss Detection       — per-variable valid-N comparison
  C3  Missing Value Accounting — missing-rate source vs. output
  C4  Mean Preservation      — continuous mean within tolerance
  C5  Mean After Conversion  — mean with unit-conversion factor
  C6  SD Preservation        — standard deviation within tolerance
  C7  Categorical Distribution — distribution match (with value_mappings)
  C8  Visit N Distribution   — per-visit row counts
  C9  Clinical Range         — output values within clinical_ranges.yaml bounds
  C10 Cross-Variable Consistency — SBP > DBP, FEV1 < FVC, etc.
  C11 Variable Type Consistency  — source/output agree on continuous vs. categorical

USAGE:
  python compare_source_output.py \\
      --source  spiromics_source_20250101T120000.json \\
      --output  spiromics_output_20250101T120000.json \\
      --cohort  SPIROMICS \\
      --yaml-dir /path/to/HV-repo/priority_variables_transform/SPIROMICS-ingest/ \\
      --cache-dir /path/to/data/dbgap-cache/spiromics/

  # --yaml-dir and --cache-dir are optional; without them the variable crosswalk
  # cannot be built and only C1 / C8 / C10 run.
  # --clinical-ranges defaults to compare/config/clinical_ranges.yaml.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import yaml

# Default clinical ranges config (relative to this script)
_CONFIG_DIR = Path(__file__).resolve().parent / "config"


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


# ---------------------------------------------------------------------------
# PHV name map (from dbGaP data dict XML)
# ---------------------------------------------------------------------------

def load_phv_name_map(cache_dir: Path) -> dict[str, str]:
    """Load PHV-accession → variable-name map from dbGaP data-dict XML files.

    Reads ``*.data_dict.xml`` under ``<cache_dir>/pheno_variable_summaries/``.
    Returns empty dict if path not found (graceful degradation).
    """
    phv_names: dict[str, str] = {}
    pheno_dir = cache_dir / "pheno_variable_summaries"
    if not pheno_dir.exists():
        print(f"  NOTE: cache pheno_variable_summaries/ not found at {pheno_dir} — PHV names unavailable")
        return phv_names

    files = list(pheno_dir.glob("*.data_dict.xml"))
    print(f"  Loading PHV names from {len(files)} data_dict.xml files...")
    for dd_file in files:
        try:
            tree = ET.parse(dd_file)
            for var in tree.getroot().findall(".//variable"):
                raw_id = var.get("id", "")
                phv_id = raw_id.split(".")[0]   # strip version suffix
                name = (var.findtext("name") or "").strip()
                if phv_id and name:
                    phv_names[phv_id] = name
        except ET.ParseError:
            pass

    print(f"  PHV name map: {len(phv_names)} entries")
    return phv_names


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
                raw_id = var.get("id", "")
                phv_id = raw_id.split(".")[0]   # strip version suffix
                if phv_id.startswith("phv"):
                    phv_to_pht[phv_id] = pht_id
        except ET.ParseError:
            pass

    print(f"  PHV->PHT map: {len(phv_to_pht)} entries across "
          f"{len(set(phv_to_pht.values()))} PHTs")
    return phv_to_pht


# ---------------------------------------------------------------------------
# YAML crosswalk construction
# ---------------------------------------------------------------------------

def _extract_value_mappings(slot_body: dict) -> dict | None:
    """Extract value_mappings dict from a slot body, or None."""
    vm = slot_body.get("value_mappings")
    if not vm or not isinstance(vm, dict):
        return None
    return {str(k): str(v) for k, v in vm.items()}


def _extract_crosswalk_from_class_derivations(
    class_derivations: dict,
    yaml_filename: str,
    phv_names: dict[str, str],
    crosswalk: list[dict],
) -> None:
    """Recursively extract crosswalk entries from a class_derivations block."""
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
        slots = class_body.get("slot_derivations", {})
        if not isinstance(slots, dict):
            continue

        # Find the concept code for this derivation
        concept_code: str | None = None
        concept_slot_name = CONCEPT_SLOTS.get(entity_class)
        if concept_slot_name and concept_slot_name in slots:
            slot = slots[concept_slot_name]
            if isinstance(slot, dict):
                val = slot.get("value")
                if val and isinstance(val, str):
                    concept_code = val.strip()
                else:
                    expr = slot.get("expr", "")
                    pf = slot.get("populated_from", "")
                    if expr and not pf:
                        concept_code = expr.strip("'\" ")
                    elif pf and not str(pf).startswith("phv"):
                        concept_code = str(pf).strip()

        # --- Demography: each slot maps a separate PHV → demog_<slot> ---
        if entity_class == "Demography":
            for slot_name, slot_body in slots.items():
                if not isinstance(slot_body, dict):
                    continue
                pf = str(slot_body.get("populated_from", ""))
                if not pf.startswith("phv"):
                    continue
                src_name = phv_names.get(pf, "")
                if not src_name:
                    continue
                crosswalk.append(
                    {
                        "source_key": src_name,
                        "output_key": f"demog_{slot_name}",
                        "match_method": "yaml",
                        "yaml_file": yaml_filename,
                        "phv_id": pf,
                        "concept_code": None,
                        "entity_class": entity_class,
                        "value_map": _extract_value_mappings(slot_body),
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
                                inner_cd, yaml_filename, phv_names, crosswalk
                            )
            continue

        # --- Standard path: gather PHVs and concept code ---
        primary_phvs: list[dict] = []
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
                    }
                )
            # PHVs referenced inside case() expressions
            expr = slot_body.get("expr", "")
            if isinstance(expr, str):
                for phv in re.findall(r"(phv\d+)", expr):
                    primary_phvs.append(
                        {
                            "phv": phv,
                            "slot": slot_name,
                            "is_value_slot": slot_name == value_slot_name,
                            "value_map": _extract_value_mappings(slot_body),
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
                                primary_phvs.append(
                                    {
                                        "phv": inner_pf,
                                        "slot": f"{slot_name}.{inner_slot}",
                                        "is_value_slot": inner_slot in (
                                            "value_decimal", "value_integer", "value_coded"
                                        ),
                                        "value_map": _extract_value_mappings(inner_slot_body),
                                    }
                                )
                            inner_expr = inner_slot_body.get("expr", "")
                            if isinstance(inner_expr, str):
                                for phv in re.findall(r"(phv\d+)", inner_expr):
                                    primary_phvs.append(
                                        {
                                            "phv": phv,
                                            "slot": f"{slot_name}.{inner_slot}",
                                            "is_value_slot": inner_slot in (
                                                "value_decimal", "value_integer"
                                            ),
                                            "value_map": None,
                                        }
                                    )

        if not primary_phvs or not concept_code:
            continue

        # method_type creates a compound output key (e.g. MO spirometry legs)
        method_type_val: str | None = None
        if entity_class == "MeasurementObservation" and "method_type" in slots:
            mt = slots["method_type"]
            if isinstance(mt, dict):
                method_type_val = (
                    mt.get("value")
                    or (mt.get("expr", "").strip("'\" ") or None)
                )

        prefix = ENTITY_PREFIX.get(entity_class, f"{entity_class.lower()}_")
        # Use bare concept code as key — the output extractor groups MeasurementObservation
        # rows by observation_type only (no method_type suffix), so the crosswalk key must
        # match that form.  method_type_val is retained as metadata only.
        output_key = f"{prefix}{concept_code}"

        value_phvs = [p for p in primary_phvs if p["is_value_slot"]]
        primary = value_phvs[0] if value_phvs else primary_phvs[0]

        src_name = phv_names.get(primary["phv"], "")
        if not src_name:
            continue

        crosswalk.append(
            {
                "source_key": src_name,
                "output_key": output_key,
                "match_method": "yaml",
                "yaml_file": yaml_filename,
                "phv_id": primary["phv"],
                "concept_code": concept_code,
                "entity_class": entity_class,
                "value_map": primary["value_map"],
                "method_type": method_type_val,
            }
        )


def build_yaml_crosswalk(
    yaml_dir: Path,
    phv_names: dict[str, str],
) -> list[dict]:
    """Parse all YAML transform files in *yaml_dir* and return crosswalk entries.

    Each entry maps a source variable name (resolved via *phv_names*) to an
    output entity key (``measurement_<code>``, ``condition_<code>``, etc.).
    """
    crosswalk: list[dict] = []

    for yaml_file in sorted(yaml_dir.glob("*.yaml")):
        if yaml_file.name.startswith("."):
            continue
        try:
            with yaml_file.open("r", encoding="utf-8") as fh:
                docs = list(yaml.safe_load_all(fh))
        except yaml.YAMLError:
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
# Output variable key normalization
# ---------------------------------------------------------------------------

_TUPLE_OBS_RE = re.compile(r"^\(\s*['\"]?([^'\"()]+?)['\"]?\s*,?\s*\)$")
# Matches full output keys whose observation_type was serialized as a Python
# singleton tuple: e.g.  measurement_('OMOP:4152194',)
_TUPLE_KEY_RE = re.compile(r"^([a-z_]+)\('([^']+)',?\)$")


def _norm_obs_type(s: str) -> str:
    """Strip Python singleton-tuple notation from an observation_type string.

    dm-bip occasionally serializes observation_type as a Python tuple repr
    (e.g. ``('OMOP:4152194',)``) rather than a plain string.  This returns
    the inner value, leaving already-clean strings unchanged.
    """
    m = _TUPLE_OBS_RE.match(s.strip())
    return m.group(1) if m else s


def _normalize_output_vars(raw: dict) -> dict:
    """Normalize output variable keys and metadata produced by dm-bip.

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
        else:
            new_key = key
        if isinstance(val, dict):
            obs = val.get("observation_type", "")
            if isinstance(obs, str) and "(" in obs:
                val = dict(val)
                val["observation_type"] = _norm_obs_type(obs)
        result[new_key] = val
    return result


def build_variable_crosswalk(
    source_vars: dict,
    output_vars: dict,
    yaml_dir: Path | None = None,
    cache_dir: Path | None = None,
    source_doc: dict | None = None,
) -> list[dict]:
    """Build source <-> output variable crosswalk.

    Strategy (in priority order):
    1. YAML-driven: PHV -> concept code -> entity key.
    2. PHV ID match: source key starts with "phv", check output metadata.
    3. Name match: source ``name`` == output ``bdc_label``.

    When *source_doc* contains ``variables_by_pht`` and *cache_dir* provides a
    PHV->PHT map, each YAML-matched entry gains a ``_resolved_src`` field with
    stats drawn from the correct PHT table.  This eliminates false C2/C3
    failures caused by the same variable appearing in multiple PHT files.
    """
    matches: list[dict] = []
    matched_src: set[str] = set()
    matched_out: set[str] = set()

    # --- Strategy 1: YAML-driven ---
    if yaml_dir and yaml_dir.exists():
        phv_names: dict[str, str] = {}
        phv_to_pht: dict[str, str] = {}
        if cache_dir and cache_dir.exists():
            phv_names = load_phv_name_map(cache_dir)
            phv_to_pht = load_phv_to_pht_map(cache_dir)

        variables_by_pht: dict[str, dict] = (
            source_doc.get("variables_by_pht", {}) if source_doc else {}
        )

        yaml_cw = build_yaml_crosswalk(yaml_dir, phv_names)
        print(f"  YAML crosswalk: {len(yaml_cw)} entries from {yaml_dir.name}")

        for entry in yaml_cw:
            src_key = entry["source_key"]
            out_key = entry["output_key"]

            # Case-insensitive fallback for source key
            if src_key not in source_vars:
                for sk in source_vars:
                    if sk.upper() == src_key.upper():
                        src_key = sk
                        entry["source_key"] = sk
                        break
                else:
                    continue

            # Case-insensitive fallback for output key
            if out_key not in output_vars:
                for ok in output_vars:
                    if ok.upper() == out_key.upper():
                        out_key = ok
                        entry["output_key"] = ok
                        break
                else:
                    continue

            if src_key in matched_src:
                continue
            if out_key in matched_out:
                # Multi-source MOS: another source column already claimed this key
                continue

            # Resolve per-PHT source stats to avoid multi-table inflation.
            phv_id = entry.get("phv_id", "")
            if phv_id and variables_by_pht:
                pht_id = phv_to_pht.get(phv_id)
                if pht_id and pht_id in variables_by_pht:
                    pht_vars = variables_by_pht[pht_id]
                    # Try exact match first, then case-insensitive.
                    resolved = pht_vars.get(src_key)
                    if resolved is None:
                        for k, v in pht_vars.items():
                            if k.upper() == src_key.upper():
                                resolved = v
                                break
                    if resolved is not None:
                        entry["_resolved_src"] = resolved
                        entry["_resolved_pht"] = pht_id

            matches.append(entry)
            matched_src.add(src_key)
            matched_out.add(out_key)

    # --- Strategy 2: PHV ID match ---
    for src_key, src_info in source_vars.items():
        if "error" in src_info or src_key in matched_src:
            continue
        if not src_key.startswith("phv"):
            continue
        for out_key, out_info in output_vars.items():
            if out_key in matched_out:
                continue
            if src_key in out_key or src_key in str(out_info):
                matches.append(
                    {"source_key": src_key, "output_key": out_key, "match_method": "phv_id"}
                )
                matched_src.add(src_key)
                matched_out.add(out_key)
                break

    # --- Strategy 3: Name match ---
    for src_key, src_info in source_vars.items():
        if "error" in src_info or src_key in matched_src:
            continue
        src_name = src_info.get("name", "").upper()
        if not src_name:
            continue
        for out_key, out_info in output_vars.items():
            if out_key in matched_out:
                continue
            out_label = out_info.get("bdc_label", "").upper()
            if out_label and src_name == out_label:
                matches.append(
                    {"source_key": src_key, "output_key": out_key, "match_method": "name"}
                )
                matched_src.add(src_key)
                matched_out.add(out_key)
                break

    return matches


# ---------------------------------------------------------------------------
# Check implementations
# ---------------------------------------------------------------------------

def check_c1_n_preservation(source: dict, output: dict) -> list[CheckResult]:
    """C1: Total participant count comparison."""
    src_n = source.get("total_participants", 0)
    out_n = output.get("total_participants", 0)

    if src_n == 0:
        return [CheckResult("C1", "_total", "SKIP", "No source participant count")]
    if out_n == 0:
        return [CheckResult("C1", "_total", "FAIL", "No output participants found")]
    if out_n == src_n:
        return [CheckResult("C1", "_total", "PASS", f"Participant count matches: {src_n}")]

    if out_n < src_n:
        loss_pct = round((src_n - out_n) / src_n * 100, 1)
        status = "FAIL" if loss_pct > 5 else "WARN"
        return [CheckResult("C1", "_total", status,
                             f"Participant loss: {src_n} -> {out_n} ({loss_pct}%)",
                             {"source_n": src_n, "output_n": out_n, "loss_pct": loss_pct})]

    return [CheckResult("C1", "_total", "WARN",
                         f"Output has MORE participants than source: {src_n} -> {out_n}",
                         {"source_n": src_n, "output_n": out_n})]


def check_c2_n_loss(src_var: dict, out_var: dict, var_name: str) -> CheckResult:
    """C2: Per-variable valid-N comparison."""
    src_n = src_var.get("n_valid", 0)
    out_n = out_var.get("n_valid", 0)

    if src_n == 0:
        return CheckResult("C2", var_name, "SKIP", "No valid source values")
    if out_n == src_n:
        return CheckResult("C2", var_name, "PASS", f"N preserved: {src_n}")

    loss_pct = round((src_n - out_n) / src_n * 100, 1) if src_n > 0 else 0
    if abs(loss_pct) <= 1:
        return CheckResult("C2", var_name, "PASS",
                           f"N within 1%: {src_n} -> {out_n}",
                           {"source_n": src_n, "output_n": out_n, "loss_pct": loss_pct})
    if 0 < loss_pct <= 5:
        return CheckResult("C2", var_name, "WARN",
                           f"Moderate N loss: {src_n} -> {out_n} ({loss_pct}%)",
                           {"source_n": src_n, "output_n": out_n, "loss_pct": loss_pct})
    if loss_pct > 5:
        return CheckResult("C2", var_name, "FAIL",
                           f"Significant N loss: {src_n} -> {out_n} ({loss_pct}%)",
                           {"source_n": src_n, "output_n": out_n, "loss_pct": loss_pct})
    return CheckResult("C2", var_name, "WARN",
                       f"N gain: {src_n} -> {out_n}",
                       {"source_n": src_n, "output_n": out_n})


def check_c3_missing_accounting(
    src_var: dict, out_var: dict, var_name: str
) -> CheckResult:
    """C3: Missing value rate comparison.

    When denominators differ by >20% (common when source is concatenated raw
    TSVs), falls back to n_valid comparison to avoid false positives.
    """
    src_total = src_var.get("n_total", 0)
    out_total = out_var.get("n_total", 0)
    src_valid = src_var.get("n_valid", 0)
    out_valid = out_var.get("n_valid", 0)

    if src_total > 0 and out_total > 0:
        denom_ratio = min(src_total, out_total) / max(src_total, out_total)
        if denom_ratio < 0.8:
            if src_valid == 0:
                return CheckResult("C3", var_name, "SKIP",
                                   "No valid source values (denominator mismatch)")
            if out_valid == src_valid:
                return CheckResult("C3", var_name, "PASS",
                                   f"n_valid preserved: {src_valid}")
            diff_pct = abs(out_valid - src_valid) / src_valid * 100
            if diff_pct <= 1:
                return CheckResult("C3", var_name, "PASS",
                                   f"n_valid within 1%: {src_valid} -> {out_valid}")
            if diff_pct <= 5:
                return CheckResult("C3", var_name, "WARN",
                                   f"n_valid shifted: {src_valid} -> {out_valid} ({diff_pct:.1f}%)")
            return CheckResult("C3", var_name, "FAIL",
                               f"n_valid mismatch: {src_valid} -> {out_valid} ({diff_pct:.1f}%)",
                               {"source_n_valid": src_valid, "output_n_valid": out_valid})

    src_pct = src_var.get("pct_missing", 0)
    out_pct = out_var.get("pct_missing", 0)
    diff = abs(out_pct - src_pct)

    if diff <= 1.0:
        return CheckResult("C3", var_name, "PASS",
                           f"Missing rate stable: {src_pct}% -> {out_pct}%")
    if diff <= 5.0:
        return CheckResult("C3", var_name, "WARN",
                           f"Missing rate changed: {src_pct}% -> {out_pct}% (d={diff:.1f}%)")
    return CheckResult("C3", var_name, "FAIL",
                       f"Large missing rate change: {src_pct}% -> {out_pct}% (d={diff:.1f}%)",
                       {"source_pct": src_pct, "output_pct": out_pct})


def check_c4_mean_preservation(
    src_var: dict, out_var: dict, var_name: str, tolerance: float = 0.01
) -> CheckResult:
    """C4: Continuous mean comparison (no unit conversion)."""
    if src_var.get("type") != "continuous" or out_var.get("type") != "continuous":
        return CheckResult("C4", var_name, "SKIP", "Not both continuous")

    src_mean = src_var.get("mean")
    out_mean = out_var.get("mean")
    if src_mean is None or out_mean is None:
        return CheckResult("C4", var_name, "SKIP", "Missing mean value")

    if src_mean == 0:
        if out_mean == 0:
            return CheckResult("C4", var_name, "PASS", "Both means are 0")
        return CheckResult("C4", var_name, "WARN", f"Source mean=0, output mean={out_mean}")

    rel_diff = abs(out_mean - src_mean) / abs(src_mean)
    if rel_diff <= tolerance:
        return CheckResult("C4", var_name, "PASS",
                           f"Mean preserved: {src_mean} -> {out_mean} (d={rel_diff:.4f})")
    if rel_diff <= tolerance * 5:
        return CheckResult("C4", var_name, "WARN",
                           f"Mean shifted: {src_mean} -> {out_mean} (d={rel_diff:.4f})",
                           {"source_mean": src_mean, "output_mean": out_mean})
    return CheckResult("C4", var_name, "FAIL",
                       f"Mean mismatch: {src_mean} -> {out_mean} (d={rel_diff:.4f})",
                       {"source_mean": src_mean, "output_mean": out_mean})


def check_c5_mean_after_conversion(
    src_var: dict, out_var: dict, var_name: str,
    conversion_factor: float | None = None, tolerance: float = 0.01,
) -> CheckResult:
    """C5: Mean comparison with a known unit conversion factor."""
    if conversion_factor is None:
        return CheckResult("C5", var_name, "SKIP", "No conversion factor specified")
    if src_var.get("type") != "continuous" or out_var.get("type") != "continuous":
        return CheckResult("C5", var_name, "SKIP", "Not both continuous")

    src_mean = src_var.get("mean")
    out_mean = out_var.get("mean")
    if src_mean is None or out_mean is None:
        return CheckResult("C5", var_name, "SKIP", "Missing mean value")

    expected = src_mean * conversion_factor
    if expected == 0:
        return CheckResult("C5", var_name, "SKIP", "Expected mean after conversion is 0")

    rel_diff = abs(out_mean - expected) / abs(expected)
    if rel_diff <= tolerance:
        return CheckResult("C5", var_name, "PASS",
                           f"Mean after x{conversion_factor}: "
                           f"{src_mean} -> {expected:.4f} (output={out_mean}, d={rel_diff:.4f})")
    return CheckResult("C5", var_name, "FAIL",
                       f"Mean mismatch after x{conversion_factor}: "
                       f"expected {expected:.4f}, got {out_mean} (d={rel_diff:.4f})",
                       {"expected": expected, "actual": out_mean, "factor": conversion_factor})


def check_c11_type_consistency(src_var: dict, out_var: dict, var_name: str) -> CheckResult:
    """C11: Variable type consistency between source and output.

    Flags when source and output disagree on whether a variable is continuous
    or categorical.  A mismatch usually means the pipeline recoded a continuous
    value into buckets (or treated categorical codes as numbers), which is a
    data-quality concern.
    """
    src_type = src_var.get("type")
    out_type = out_var.get("type")

    if not src_type or not out_type:
        return CheckResult("C11", var_name, "SKIP", "Type information missing")
    if src_type == out_type:
        return CheckResult("C11", var_name, "PASS", f"Type consistent: {src_type}")

    return CheckResult(
        "C11", var_name, "WARN",
        f"Type mismatch: source={src_type}, output={out_type}",
        {"source_type": src_type, "output_type": out_type},
    )


def check_c6_sd_preservation(
    src_var: dict, out_var: dict, var_name: str, tolerance: float = 0.02,
) -> CheckResult:
    """C6: Standard deviation comparison."""
    if src_var.get("type") != "continuous" or out_var.get("type") != "continuous":
        return CheckResult("C6", var_name, "SKIP", "Not both continuous")

    src_sd = src_var.get("sd")
    out_sd = out_var.get("sd")
    if src_sd is None or out_sd is None:
        return CheckResult("C6", var_name, "SKIP", "Missing SD value")

    if src_sd == 0:
        if out_sd == 0:
            return CheckResult("C6", var_name, "PASS", "Both SDs are 0")
        return CheckResult("C6", var_name, "WARN", f"Source SD=0, output SD={out_sd}")

    rel_diff = abs(out_sd - src_sd) / abs(src_sd)
    if rel_diff <= tolerance:
        return CheckResult("C6", var_name, "PASS",
                           f"SD preserved: {src_sd} -> {out_sd} (d={rel_diff:.4f})")
    if rel_diff <= tolerance * 5:
        return CheckResult("C6", var_name, "WARN",
                           f"SD shifted: {src_sd} -> {out_sd} (d={rel_diff:.4f})")
    return CheckResult("C6", var_name, "FAIL",
                       f"SD mismatch: {src_sd} -> {out_sd} (d={rel_diff:.4f})",
                       {"source_sd": src_sd, "output_sd": out_sd})


def check_c7_categorical_distribution(
    src_var: dict, out_var: dict, var_name: str,
    tolerance_pct: float = 2.0,
    value_map: dict | None = None,
) -> CheckResult:
    """C7: Categorical distribution comparison.

    *value_map* translates source category keys (raw dbGaP codes) to output
    category keys (e.g. OMOP concept codes) before comparison.
    """
    if src_var.get("type") != "categorical" or out_var.get("type") != "categorical":
        return CheckResult("C7", var_name, "SKIP", "Not both categorical")

    src_dist = src_var.get("distribution", {})
    out_dist = out_var.get("distribution", {})
    if not src_dist:
        return CheckResult("C7", var_name, "SKIP", "No source distribution")

    # Translate using value_map
    if value_map:
        translated: dict[str, Any] = {}
        for cat, stats in src_dist.items():
            mapped = value_map.get(cat)
            if not mapped:
                try:
                    mapped = value_map.get(str(int(float(cat))))
                except (ValueError, OverflowError):
                    pass
            translated[mapped if mapped else cat] = stats
        src_dist = translated

    # Normalize output keys — pipeline may serialize lists as "['OMOP:8527']"
    normalized_out: dict[str, Any] = {}
    for ok, stats in out_dist.items():
        key = ok.strip()
        if key.startswith("[") and key.endswith("]"):
            key = key[1:-1].strip().strip("'\"")
        normalized_out[key] = stats
    out_dist = normalized_out

    src_keys = set(src_dist)
    out_keys = set(out_dist)
    missing = sorted(src_keys - out_keys)
    extra = sorted(out_keys - src_keys)

    mismatches: list[dict] = []
    for cat in src_keys & out_keys:
        src_pct = src_dist[cat].get("pct", 0)
        out_pct = out_dist[cat].get("pct", 0)
        diff = abs(out_pct - src_pct)
        if diff > tolerance_pct:
            mismatches.append({"category": cat, "source_pct": src_pct,
                               "output_pct": out_pct, "diff": diff})

    detail: dict = {}
    if missing:
        detail["missing_categories"] = missing
    if extra:
        detail["extra_categories"] = extra
    if mismatches:
        detail["mismatches"] = mismatches

    if not detail:
        return CheckResult("C7", var_name, "PASS",
                           f"Distribution matches ({len(src_dist)} categories)")
    if not mismatches and not missing:
        return CheckResult("C7", var_name, "INFO",
                           f"Extra output categories: {extra}", detail)
    if missing:
        return CheckResult("C7", var_name, "FAIL",
                           f"Missing categories in output: {missing}", detail)
    return CheckResult("C7", var_name, "WARN",
                       f"{len(mismatches)} categories with >+/-{tolerance_pct}% shift", detail)


def check_c8_visit_distribution(source: dict, output: dict) -> list[CheckResult]:
    """C8: Visit-stratified row count comparison.

    When source and output use incompatible visit label namespaces (zero overlap),
    falls back to total-count comparison.
    """
    results: list[CheckResult] = []
    src_visits = source.get("rows_per_visit", {})
    out_visits = output.get("rows_per_visit", {})

    if not src_visits and not out_visits:
        return [CheckResult("C8", "_visits", "SKIP", "No visit data in either summary")]
    if not src_visits:
        return [CheckResult("C8", "_visits", "SKIP", "No source visit data")]

    src_keys = set(src_visits) - {"_MISSING"}
    out_keys = set(out_visits) - {"_MISSING"}

    # Namespace mismatch fallback
    if src_keys and out_keys and not (src_keys & out_keys):
        src_total = sum(n for k, n in src_visits.items() if k != "_MISSING")
        out_total = sum(n for k, n in out_visits.items() if k != "_MISSING")
        detail = {
            "note": "Source and output use different visit label namespaces; "
                    "comparing total counts only",
            "source_labels": sorted(src_keys),
            "output_labels": sorted(out_keys),
            "source_total": src_total,
            "output_total": out_total,
        }
        if out_total == src_total:
            return [CheckResult("C8", "visit_TOTAL", "PASS",
                                f"Total visits match: N={src_total} (label namespace fallback)",
                                detail)]
        ratio = out_total / src_total if src_total > 0 else 0
        status = "WARN" if 0.9 <= ratio <= 1.1 else "FAIL"
        return [CheckResult("C8", "visit_TOTAL", status,
                             f"Total visits: {src_total} -> {out_total} (label namespace fallback)",
                             detail)]

    # Normal label-keyed comparison
    for visit, src_n in sorted(src_visits.items()):
        out_n = out_visits.get(visit, 0)
        if out_n == src_n:
            results.append(CheckResult("C8", f"visit_{visit}", "PASS",
                                       f"Visit {visit}: N={src_n}"))
        elif out_n == 0:
            results.append(CheckResult("C8", f"visit_{visit}", "FAIL",
                                       f"Visit {visit}: missing in output (source N={src_n})"))
        else:
            ratio = out_n / src_n if src_n > 0 else 0
            status = "WARN" if 0.9 <= ratio <= 1.1 else "FAIL"
            results.append(CheckResult("C8", f"visit_{visit}", status,
                                       f"Visit {visit}: {src_n} -> {out_n}",
                                       {"source_n": src_n, "output_n": out_n, "ratio": ratio}))

    for visit in sorted(set(out_visits) - set(src_visits)):
        results.append(CheckResult("C8", f"visit_{visit}", "INFO",
                                   f"Visit {visit}: only in output (N={out_visits[visit]})"))

    return results


def check_c9_clinical_range(
    out_var: dict, var_name: str, clinical_ranges: dict,
) -> CheckResult:
    """C9: Output values within defined clinical plausible range."""
    if out_var.get("type") != "continuous":
        return CheckResult("C9", var_name, "SKIP", "Not continuous")

    # Match range definition: exact name > code match > substring
    matched: dict | None = None
    best_len = 0
    obs_type = out_var.get("observation_type", "")
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
        if range_name.upper() in var_name.upper() and len(range_name) > best_len:
            matched = rng
            best_len = len(range_name)

    if not matched:
        return CheckResult("C9", var_name, "SKIP", "No clinical range defined")

    out_min = out_var.get("min")
    out_max = out_var.get("max")
    if out_min is None or out_max is None:
        return CheckResult("C9", var_name, "SKIP", "No min/max in output")

    issues: list[str] = []
    red_lo = matched.get("red_flag_lo")
    red_hi = matched.get("red_flag_hi")
    plaus_lo = matched.get("plausible_lo")
    plaus_hi = matched.get("plausible_hi")

    if red_lo is not None and out_min < red_lo:
        issues.append(f"min={out_min} below red_flag {red_lo}")
    elif plaus_lo is not None and out_min < plaus_lo:
        issues.append(f"min={out_min} below plausible {plaus_lo}")

    if red_hi is not None and out_max > red_hi:
        issues.append(f"max={out_max} above red_flag {red_hi}")
    elif plaus_hi is not None and out_max > plaus_hi:
        issues.append(f"max={out_max} above plausible {plaus_hi}")

    if not issues:
        return CheckResult("C9", var_name, "PASS",
                           f"Range OK: [{out_min}, {out_max}] within [{plaus_lo}, {plaus_hi}]")

    has_red = any("red_flag" in i for i in issues)
    return CheckResult("C9", var_name, "FAIL" if has_red else "WARN",
                       "; ".join(issues),
                       {"min": out_min, "max": out_max})


def check_c10_cross_variable(
    output_vars: dict, clinical_ranges: dict,
) -> list[CheckResult]:
    """C10: Cross-variable consistency (SBP > DBP, FEV1 < FVC, etc.)."""
    results: list[CheckResult] = []
    rules = clinical_ranges.get("_cross_variable_rules", {})

    if "sbp_gt_dbp" in rules:
        sbp = next((v for v in output_vars.values() if v.get("observation_type") == "OMOP:4152194"), None)
        dbp = next((v for v in output_vars.values() if v.get("observation_type") == "OMOP:4154790"), None)
        if sbp and dbp:
            s, d = sbp.get("mean", 0), dbp.get("mean", 0)
            if s and d:
                if s > d:
                    results.append(CheckResult("C10", "sbp_gt_dbp", "PASS",
                                               f"SBP mean ({s}) > DBP mean ({d})"))
                else:
                    results.append(CheckResult("C10", "sbp_gt_dbp", "FAIL",
                                               f"SBP mean ({s}) <= DBP mean ({d}) -- possible swap"))

    if "fev1_lt_fvc" in rules:
        fev1 = next((v for v in output_vars.values() if v.get("observation_type") == "OMOP:4051332"), None)
        fvc  = next((v for v in output_vars.values() if v.get("observation_type") == "OMOP:4217326"), None)
        if fev1 and fvc:
            f1, fc = fev1.get("mean", 0), fvc.get("mean", 0)
            if f1 and fc:
                if f1 <= fc:
                    results.append(CheckResult("C10", "fev1_lt_fvc", "PASS",
                                               f"FEV1 mean ({f1}) <= FVC mean ({fc})"))
                else:
                    results.append(CheckResult("C10", "fev1_lt_fvc", "FAIL",
                                               f"FEV1 mean ({f1}) > FVC mean ({fc}) -- possible swap"))

    if not results:
        results.append(CheckResult("C10", "_cross", "SKIP",
                                   "No cross-variable pairs found in output"))

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
    output_meta: dict,
) -> str:
    """Generate a human-readable Markdown report."""
    lines = [
        f"# HV-DataQC Comparison Report: {cohort}",
        "",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Source:** {source_meta.get('source', '?')}",
        f"**Output:** {output_meta.get('source', '?')}",
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

    check_names = {
        "C1": "N Preservation", "C2": "N Loss Detection",
        "C3": "Missing Value Accounting", "C4": "Mean Preservation",
        "C5": "Mean After Conversion", "C6": "SD Preservation",
        "C7": "Categorical Distribution", "C8": "Visit N Distribution",
        "C9": "Clinical Range", "C10": "Cross-Variable Consistency",
        "C11": "Variable Type Consistency",
    }

    _sort_key = {"FAIL": 0, "WARN": 1, "PASS": 2, "INFO": 3, "SKIP": 4}
    for check_id in ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "C10", "C11"]:
        check_results = [r for r in results if r.check_id == check_id]
        if not check_results:
            continue
        lines.append(f"## {check_id}: {check_names.get(check_id, check_id)}")
        lines.append("")
        for r in sorted(check_results, key=lambda x: _sort_key.get(x.status, 9)):
            icon = _STATUS_ICONS.get(r.status, r.status)
            lines.append(f"- {icon} **{r.variable}**: {r.message}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Compare source vs. harmonized output summaries (C1-C10 checks).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--source", required=True, metavar="JSON",
                   help="Source summary JSON from extract_source_summaries.py")
    p.add_argument("--output", required=True, metavar="JSON",
                   help="Harmonized output summary JSON from extract_output_summaries.py")
    p.add_argument("--cohort", required=True, metavar="NAME",
                   help="Cohort name (e.g. SPIROMICS, CARDIA)")

    p.add_argument("--yaml-dir", metavar="DIR",
                   help="HV YAML transform directory for the cohort "
                        "(e.g. .../priority_variables_transform/SPIROMICS-ingest/). "
                        "Without this, only C1/C8/C10 run.")
    p.add_argument("--cache-dir", metavar="DIR",
                   help="dbGaP cache directory for the cohort, used to resolve PHV->name "
                        "(e.g. data/dbgap-cache/spiromics/). "
                        "Optional — PHV IDs are used as labels when not provided.")

    p.add_argument("--clinical-ranges", metavar="YAML",
                   help=f"Clinical ranges YAML (default: {_CONFIG_DIR / 'clinical_ranges.yaml'})")
    p.add_argument("--mean-tolerance", type=float, default=0.01,
                   help="Relative tolerance for mean comparison (default: 0.01 = 1%%)")
    p.add_argument("--report", metavar="FILE",
                   help="Markdown report output path "
                        "(default: <cohort>_comparison_report.md)")
    p.add_argument("--json-report", metavar="FILE",
                   help="JSON report output path "
                        "(default: <cohort>_comparison_results.json)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    cohort = args.cohort.upper()

    # Validate inputs
    for path_arg, label in [(args.source, "--source"), (args.output, "--output")]:
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

    if cache_dir and not cache_dir.exists():
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
        with cr_path.open("r", encoding="utf-8") as fh:
            clinical_ranges = yaml.safe_load(fh) or {}
        print(f"Loaded {len(clinical_ranges)} clinical range definitions from {cr_path.name}")
    else:
        print(f"NOTE: Clinical ranges file not found: {cr_path} — C9/C10 will SKIP")

    # Load summaries
    print(f"\nLoading source summary : {args.source}")
    with open(args.source, "r", encoding="utf-8") as fh:
        source: dict = json.load(fh)

    print(f"Loading output summary : {args.output}")
    with open(args.output, "r", encoding="utf-8") as fh:
        output: dict = json.load(fh)

    source_vars = source.get("variables", {})
    output_vars = _normalize_output_vars(output.get("variables", {}))
    source_meta = source.get("metadata", {})
    output_meta = output.get("metadata", {})

    print(f"\nSource: {len(source_vars)} variables, "
          f"{source.get('total_participants', '?')} participants")
    print(f"Output: {len(output_vars)} variables, "
          f"{output.get('total_participants', '?')} participants")

    # Build crosswalk
    print("\nBuilding variable crosswalk...")
    crosswalk = build_variable_crosswalk(
        source_vars, output_vars,
        yaml_dir=yaml_dir,
        cache_dir=cache_dir,
        source_doc=source,
    )
    print(f"Matched {len(crosswalk)} variable pairs")
    for m in crosswalk:
        method = m.get("match_method", "?")
        yaml_f = m.get("yaml_file", "")
        phv = m.get("phv_id", "")
        resolved_pht = m.get("_resolved_pht", "")
        extra = f" [{yaml_f}]" if yaml_f else ""
        extra += f" ({phv})" if phv else ""
        extra += f" -> {resolved_pht}" if resolved_pht else ""
        print(f"  {m['source_key']:<30} -> {m['output_key']:<40} [{method}]{extra}")

    # Run checks
    all_results: list[CheckResult] = []

    all_results.extend(check_c1_n_preservation(source, output))

    for match in crosswalk:
        src_key = match["source_key"]
        out_key = match["output_key"]
        # Use per-PHT stats when available (eliminates multi-table inflation).
        src_var = match.get("_resolved_src") or source_vars.get(src_key, {})
        out_var = output_vars[out_key]
        display_name = src_var.get("name", src_key)
        value_map = match.get("value_map")

        all_results.append(check_c2_n_loss(src_var, out_var, display_name))
        all_results.append(check_c3_missing_accounting(src_var, out_var, display_name))
        all_results.append(check_c4_mean_preservation(src_var, out_var, display_name, args.mean_tolerance))
        all_results.append(check_c5_mean_after_conversion(src_var, out_var, display_name))
        all_results.append(check_c6_sd_preservation(src_var, out_var, display_name))
        all_results.append(check_c7_categorical_distribution(src_var, out_var, display_name,
                                                               value_map=value_map))
        all_results.append(check_c9_clinical_range(out_var, display_name, clinical_ranges))
        all_results.append(check_c11_type_consistency(src_var, out_var, display_name))

    all_results.extend(check_c8_visit_distribution(source, output))
    all_results.extend(check_c10_cross_variable(output_vars, clinical_ranges))

    # Flag unmatched variables
    matched_src = {m["source_key"] for m in crosswalk}
    matched_out = {m["output_key"] for m in crosswalk}
    for sk in source_vars:
        if sk not in matched_src and "error" not in source_vars[sk]:
            all_results.append(CheckResult(
                "C2", source_vars[sk].get("name", sk), "INFO", "Source variable not matched in output"
            ))
    for ok in output_vars:
        if ok not in matched_out:
            all_results.append(CheckResult("C2", ok, "FAIL", "Output variable not matched in source — no source PHV traceable"))

    # Summary
    counts: dict[str, int] = {}
    for r in all_results:
        counts[r.status] = counts.get(r.status, 0) + 1
    print(f"\n{'='*60}")
    print(f"Results: {counts}")

    # Write Markdown
    md = generate_markdown_report(all_results, cohort, source_meta, output_meta)
    report_path = Path(args.report or f"{cohort.lower()}_comparison_report.md")
    with report_path.open("w", encoding="utf-8") as fh:
        fh.write(md)
    print(f"\nMarkdown report : {report_path}")

    # Write JSON
    json_report = {
        "metadata": {
            "cohort": cohort,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_file": args.source,
            "output_file": args.output,
            "mean_tolerance": args.mean_tolerance,
        },
        "summary": counts,
        "crosswalk": crosswalk,
        "results": [r.to_dict() for r in all_results],
    }
    json_path = Path(args.json_report or f"{cohort.lower()}_comparison_results.json")
    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(json_report, fh, indent=2, default=str)
    print(f"JSON report     : {json_path}")

    n_fail = counts.get("FAIL", 0)
    if n_fail > 0:
        print(f"\n{n_fail} FAIL(s) detected -- review report")
        sys.exit(1)
    else:
        print("\nAll checks passed or skipped")


if __name__ == "__main__":
    main()
