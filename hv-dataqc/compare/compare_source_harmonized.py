"""
compare_source_harmonized.py — HV-DataQC Component 3

Compare aggregate summaries from extract_source_summaries.py (raw dbGaP source)
and extract_harmonized_summaries.py (dm-bip harmonized output). Runs checks C1–C10
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
  C8  Visit N Distribution   — per-visit row counts
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

# Default clinical ranges config (relative to this script)
_CONFIG_DIR = Path(__file__).resolve().parent / "config"
_THRESHOLDS_PATH = _CONFIG_DIR / "thresholds.yaml"


def _canonical_phv_id(raw_id: str) -> str:
    """Return canonical PHV accession: lower-case, version suffix stripped."""
    return str(raw_id or "").split(".")[0].lower()


def _json_safe(value: Any) -> Any:
    """Recursively convert non-finite floats to None before strict JSON writing."""
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _write_json_atomic(path: Path, data: Any) -> None:
    """Write strict JSON via temp file then atomic replace."""
    tmp_path = path.with_name(f"{path.name}.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(_json_safe(data), fh, indent=2, default=str, allow_nan=False)
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _write_text_atomic(path: Path, text: str) -> None:
    """Write text via temp file then atomic replace."""
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
        with effective_path.open("r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
        print(f"Loaded thresholds from {effective_path.name}")
        return cfg
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
                phv_id = _canonical_phv_id(var.get("id", ""))
                name = (var.findtext("name") or "").strip()
                if phv_id and name:
                    phv_names[phv_id] = name
        except ET.ParseError as exc:
            print(f"  WARNING: Could not parse PHV name XML {dd_file.name}: {exc}")

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
                phv_id = _canonical_phv_id(var.get("id", ""))
                if phv_id.startswith("phv"):
                    phv_to_pht[phv_id] = pht_id
        except ET.ParseError as exc:
            print(f"  WARNING: Could not parse PHV->PHT XML {dd_file.name}: {exc}")

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
                        "harmonized_key": f"demog_{slot_name}",
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

        # method_type creates a compound harmonized key (e.g. MO spirometry legs)
        method_type_val: str | None = None
        if entity_class == "MeasurementObservation" and "method_type" in slots:
            mt = slots["method_type"]
            if isinstance(mt, dict):
                method_type_val = (
                    mt.get("value")
                    or (mt.get("expr", "").strip("'\" ") or None)
                )

        prefix = ENTITY_PREFIX.get(entity_class, f"{entity_class.lower()}_")
        # Use bare concept code as key — the harmonized extractor groups MeasurementObservation
        # rows by observation_type only (no method_type suffix), so the crosswalk key must
        # match that form.  method_type_val is retained as metadata only.
        harmonized_key = f"{prefix}{concept_code}"

        value_phvs = [p for p in primary_phvs if p["is_value_slot"]]
        primary = value_phvs[0] if value_phvs else primary_phvs[0]

        src_name = phv_names.get(primary["phv"], "")
        if not src_name:
            continue

        crosswalk.append(
            {
                "source_key": src_name,
                "harmonized_key": harmonized_key,
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


def build_variable_crosswalk(
    source_vars: dict,
    harmonized_vars: dict,
    yaml_dir: Path | None = None,
    cache_dir: Path | None = None,
    source_doc: dict | None = None,
) -> list[dict]:
    """Build source <-> harmonized variable crosswalk.

    Strategy (in priority order):
    1. YAML-driven: PHV -> concept code -> entity key.
    2. PHV ID match: source key starts with "phv", check harmonized metadata.
    3. Name match: source ``name`` == harmonized ``bdc_label``.

    When *source_doc* contains ``variables_by_pht`` and *cache_dir* provides a
    PHV->PHT map, each YAML-matched entry gains a ``_resolved_src`` field with
    stats drawn from the correct PHT table.  This eliminates false C2/C3
    failures caused by the same variable appearing in multiple PHT files.
    """
    matches: list[dict] = []
    matched_src: set[str] = set()
    matched_harmonized: set[str] = set()

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
            harmonized_key = entry["harmonized_key"]

            # Case-insensitive fallback for source key
            if src_key not in source_vars:
                for sk in source_vars:
                    if sk.upper() == src_key.upper():
                        src_key = sk
                        entry["source_key"] = sk
                        break
                else:
                    continue

            # Case-insensitive fallback for harmonized key
            if harmonized_key not in harmonized_vars:
                for ok in harmonized_vars:
                    if ok.upper() == harmonized_key.upper():
                        harmonized_key = ok
                        entry["harmonized_key"] = ok
                        break
                else:
                    continue

            if src_key in matched_src:
                continue
            if harmonized_key in matched_harmonized:
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
            matched_harmonized.add(harmonized_key)

    # --- Strategy 2: PHV ID match ---
    for src_key, src_info in source_vars.items():
        if "error" in src_info or src_key in matched_src:
            continue
        if not src_key.startswith("phv"):
            continue
        for harmonized_key, out_info in harmonized_vars.items():
            if harmonized_key in matched_harmonized:
                continue
            if src_key in harmonized_key or src_key in str(out_info):
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
# Check implementations
# ---------------------------------------------------------------------------

def check_c1_n_preservation(
    source: dict, harmonized: dict, fail_pct: float = 1.0
) -> list[CheckResult]:
    """C1: Total participant count comparison."""
    src_n = source.get("total_participants", 0)
    harmonized_n = harmonized.get("total_participants", 0)

    if src_n == 0:
        return [CheckResult("C1", "_total", "SKIP", "No source participant count")]
    if harmonized_n == 0:
        return [CheckResult("C1", "_total", "FAIL", "No harmonized participants found")]
    if harmonized_n == src_n:
        return [CheckResult("C1", "_total", "PASS", f"Participant count matches: {src_n}")]

    if harmonized_n < src_n:
        loss_pct = round((src_n - harmonized_n) / src_n * 100, 1)
        status = "FAIL" if loss_pct > fail_pct else "WARN"
        return [CheckResult("C1", "_total", status,
                             f"Participant loss: {src_n} -> {harmonized_n} ({loss_pct}%)",
                             {"source_n": src_n, "harmonized_n": harmonized_n, "loss_pct": loss_pct})]

    return [CheckResult("C1", "_total", "WARN",
                         f"Harmonized has MORE participants than source: {src_n} -> {harmonized_n}",
                         {"source_n": src_n, "harmonized_n": harmonized_n})]


def check_c2_n_loss(
    src_var: dict, harmonized_var: dict, var_name: str,
    pass_pct: float = 0.5, warn_pct: float = 2.0,
) -> CheckResult:
    """C2: Per-variable valid-N comparison."""
    src_n = src_var.get("n_valid", 0)
    harmonized_n = harmonized_var.get("n_valid", 0)

    if src_n == 0:
        return CheckResult("C2", var_name, "SKIP", "No valid source values")
    if harmonized_n == src_n:
        return CheckResult("C2", var_name, "PASS", f"N preserved: {src_n}")

    loss_pct = round((src_n - harmonized_n) / src_n * 100, 1) if src_n > 0 else 0
    if abs(loss_pct) <= pass_pct:
        return CheckResult("C2", var_name, "PASS",
                           f"N within {pass_pct}%: {src_n} -> {harmonized_n}",
                           {"source_n": src_n, "harmonized_n": harmonized_n, "loss_pct": loss_pct})
    if 0 < loss_pct <= warn_pct:
        return CheckResult("C2", var_name, "WARN",
                           f"Moderate N loss: {src_n} -> {harmonized_n} ({loss_pct}%)",
                           {"source_n": src_n, "harmonized_n": harmonized_n, "loss_pct": loss_pct})
    if loss_pct > warn_pct:
        return CheckResult("C2", var_name, "FAIL",
                           f"Significant N loss: {src_n} -> {harmonized_n} ({loss_pct}%)",
                           {"source_n": src_n, "harmonized_n": harmonized_n, "loss_pct": loss_pct})
    return CheckResult("C2", var_name, "WARN",
                       f"N gain: {src_n} -> {harmonized_n}",
                       {"source_n": src_n, "harmonized_n": harmonized_n})


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

    if src_total > 0 and harmonized_total > 0:
        denom_ratio = min(src_total, harmonized_total) / max(src_total, harmonized_total)
        if denom_ratio < 0.8:
            if src_valid == 0:
                return CheckResult("C3", var_name, "SKIP",
                                   "No valid source values (denominator mismatch)")
            if harmonized_valid == src_valid:
                return CheckResult("C3", var_name, "PASS",
                                   f"n_valid preserved: {src_valid}")
            diff_pct = abs(harmonized_valid - src_valid) / src_valid * 100
            if diff_pct <= n_valid_pass_pct:
                return CheckResult("C3", var_name, "PASS",
                                   f"n_valid within {n_valid_pass_pct}%: {src_valid} -> {harmonized_valid}")
            if diff_pct <= n_valid_warn_pct:
                return CheckResult("C3", var_name, "WARN",
                                   f"n_valid shifted: {src_valid} -> {harmonized_valid} ({diff_pct:.1f}%)")
            return CheckResult("C3", var_name, "FAIL",
                               f"n_valid mismatch: {src_valid} -> {harmonized_valid} ({diff_pct:.1f}%)",
                               {"source_n_valid": src_valid, "harmonized_n_valid": harmonized_valid})

    src_pct = src_var.get("pct_missing", 0)
    harmonized_pct = harmonized_var.get("pct_missing", 0)
    diff = abs(harmonized_pct - src_pct)

    if diff <= pass_pp:
        return CheckResult("C3", var_name, "PASS",
                           f"Missing rate stable: {src_pct}% -> {harmonized_pct}%")
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
                           f"Mean preserved: {src_mean} -> {harmonized_mean} (d={rel_diff:.4f})")
    if rel_diff <= warn_rel:
        return CheckResult("C4", var_name, "WARN",
                           f"Mean shifted: {src_mean} -> {harmonized_mean} (d={rel_diff:.4f})",
                           {"source_mean": src_mean, "harmonized_mean": harmonized_mean})
    return CheckResult("C4", var_name, "FAIL",
                       f"Mean mismatch: {src_mean} -> {harmonized_mean} (d={rel_diff:.4f})",
                       {"source_mean": src_mean, "harmonized_mean": harmonized_mean})


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
                           f"SD preserved: {src_sd} -> {harmonized_sd} (d={rel_diff:.4f})")
    if rel_diff <= warn_rel:
        return CheckResult("C6", var_name, "WARN",
                           f"SD shifted: {src_sd} -> {harmonized_sd} (d={rel_diff:.4f})")
    return CheckResult("C6", var_name, "FAIL",
                       f"SD mismatch: {src_sd} -> {harmonized_sd} (d={rel_diff:.4f})",
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

    src_dist = src_var.get("distribution", {})
    harmonized_dist = harmonized_var.get("distribution", {})
    if not src_dist:
        return CheckResult("C7", var_name, "SKIP", "No source distribution")

    # Translate using value_map
    if value_map:
        translated: dict[str, Any] = {}
        translated_total = 0
        for cat, stats in src_dist.items():
            mapped = value_map.get(cat)
            if not mapped:
                try:
                    mapped = value_map.get(str(int(float(cat))))
                except (ValueError, OverflowError):
                    pass
            new_cat = mapped if mapped else cat
            existing = translated.setdefault(
                new_cat,
                {"n": 0, "pct": 0.0, "source_categories": []},
            )
            count = int(stats.get("n", 0) or 0)
            existing["n"] += count
            existing["source_categories"].append(cat)
            translated_total += count
        for stats in translated.values():
            stats["pct"] = round(stats["n"] / translated_total * 100, 2) if translated_total else 0.0
            if len(stats["source_categories"]) == 1:
                stats.pop("source_categories", None)
        src_dist = translated

    # Normalize harmonized keys — pipeline may serialize lists as "['OMOP:8527']"
    normalized_out: dict[str, Any] = {}
    for ok, stats in harmonized_dist.items():
        key = ok.strip()
        if key.startswith("[") and key.endswith("]"):
            key = key[1:-1].strip().strip("'\"")
        normalized_out[key] = stats
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
        return CheckResult("C7", var_name, "FAIL",
                           f"Missing categories in harmonized: {missing}", detail)
    return CheckResult("C7", var_name, "WARN",
                       f"{len(mismatches)} categories with >+/-{pass_pct}% shift", detail)


def check_c8_visit_distribution(
    source: dict, harmonized: dict,
    warn_lo_ratio: float = 0.95, warn_hi_ratio: float = 1.05,
) -> list[CheckResult]:
    """C8: Visit-stratified row count comparison.

    When source and harmonized use incompatible visit label namespaces (zero overlap),
    falls back to total-count comparison.
    """
    results: list[CheckResult] = []
    src_visits = source.get("rows_per_visit", {})
    harmonized_visits = harmonized.get("rows_per_visit", {})

    if not src_visits and not harmonized_visits:
        return [CheckResult("C8", "_visits", "SKIP", "No visit data in either summary")]
    if not src_visits:
        return [CheckResult("C8", "_visits", "SKIP", "No source visit data")]

    src_keys = set(src_visits) - {"_MISSING"}
    harmonized_keys = set(harmonized_visits) - {"_MISSING"}

    # Namespace mismatch fallback
    if src_keys and harmonized_keys and not (src_keys & harmonized_keys):
        src_total = sum(n for k, n in src_visits.items() if k != "_MISSING")
        harmonized_total = sum(n for k, n in harmonized_visits.items() if k != "_MISSING")
        detail = {
            "note": "Source and harmonized use different visit label namespaces; "
                    "comparing total counts only",
            "source_labels": sorted(src_keys),
            "harmonized_labels": sorted(harmonized_keys),
            "source_total": src_total,
            "harmonized_total": harmonized_total,
        }
        if harmonized_total == src_total:
            return [CheckResult("C8", "visit_TOTAL", "PASS",
                                f"Total visits match: N={src_total} (label namespace fallback)",
                                detail)]
        ratio = harmonized_total / src_total if src_total > 0 else 0
        status = "WARN" if warn_lo_ratio <= ratio <= warn_hi_ratio else "FAIL"
        return [CheckResult("C8", "visit_TOTAL", status,
                             f"Total visits: {src_total} -> {harmonized_total} (label namespace fallback)",
                             detail)]

    # Normal label-keyed comparison
    for visit, src_n in sorted(src_visits.items()):
        harmonized_n = harmonized_visits.get(visit, 0)
        if harmonized_n == src_n:
            results.append(CheckResult("C8", f"visit_{visit}", "PASS",
                                       f"Visit {visit}: N={src_n}"))
        elif harmonized_n == 0:
            results.append(CheckResult("C8", f"visit_{visit}", "FAIL",
                                       f"Visit {visit}: missing in harmonized (source N={src_n})"))
        else:
            ratio = harmonized_n / src_n if src_n > 0 else 0
            status = "WARN" if warn_lo_ratio <= ratio <= warn_hi_ratio else "FAIL"
            results.append(CheckResult("C8", f"visit_{visit}", status,
                                       f"Visit {visit}: {src_n} -> {harmonized_n}",
                                       {"source_n": src_n, "harmonized_n": harmonized_n, "ratio": ratio}))

    for visit in sorted(set(harmonized_visits) - set(src_visits)):
        results.append(CheckResult("C8", f"visit_{visit}", "INFO",
                                   f"Visit {visit}: only in harmonized (N={harmonized_visits[visit]})"))

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
    if src_var and src_var.get("type") == "continuous":
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

    has_red = any("red_flag" in i for i in issues)
    return CheckResult("C9", var_name, "FAIL" if has_red else "WARN",
                       "; ".join(issues),
                       {"min": out_min, "max": out_max})


# Detects simple 2-variable directional checks: "mean(X) > mean(Y)" or "mean(X) < mean(Y)".
# Rules using >=, <=, approximate equality, or multi-variable formulas do not match and are emitted as SKIP.
_C10_SIMPLE_RE = re.compile(r"mean\([^)]+\)\s*([<>])\s*mean\([^)]+\)")


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

        m = _C10_SIMPLE_RE.search(check_expr)
        if not m or len(variables) != 2:
            results.append(CheckResult(
                "C10", rule_id, "SKIP",
                f"Multi-variable or formula rule (not yet implemented): {description}"
            ))
            continue

        operator = m.group(1)  # "<" or ">"

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

        var_a = next((v for v in harmonized_vars.values()
                      if v.get("observation_type") in codes_a), None)
        var_b = next((v for v in harmonized_vars.values()
                      if v.get("observation_type") in codes_b), None)

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

        if operator == ">":
            passed = mean_a > mean_b
            display_operator = ">"
        else:  # "<"
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

    check_names = {
        "C1": "N Preservation", "C2": "N Loss Detection",
        "C3": "Missing Value Accounting", "C4": "Mean Preservation",
        "C5": "Mean After Conversion", "C6": "SD Preservation",
        "C7": "Categorical Distribution", "C8": "Visit N Distribution",
        "C9": "Clinical Range", "C10": "Cross-Variable Consistency",
        "C11": "Variable Type Consistency",
    }

    _sort_key = {"FAIL": 0, "WARN": 1, "PASS": 2, "INFO": 3, "SKIP": 4}

    def _render_c7_detail(r: CheckResult) -> list[str]:
        """Render C7 distribution table and mismatch detail as indented markdown."""
        sub: list[str] = []
        table = r.detail.get("distribution_table", [])
        if not table:
            return sub
        sub.append("")
        sub.append("  | Category | Src N | Src % | Harmonized N | Harmonized % | Δ% |")
        sub.append("  |----------|------:|------:|------:|------:|---:|")
        mismatch_cats = {m["category"] for m in r.detail.get("mismatches", [])}
        missing_cats = set(r.detail.get("missing_categories", []))
        extra_cats = set(r.detail.get("extra_categories", []))
        for row in table:
            cat = row["category"]
            cat_label = _md_escape(cat)
            src_n = row.get("source_n", "")
            src_pct = f"{row['source_pct']:.1f}" if row.get("source_pct") is not None else ""
            harmonized_n = row.get("harmonized_n", "")
            harmonized_pct = f"{row['harmonized_pct']:.1f}" if row.get("harmonized_pct") is not None else ""
            if row.get("source_pct") is not None and row.get("harmonized_pct") is not None:
                delta = f"{row['harmonized_pct'] - row['source_pct']:+.1f}"
            else:
                delta = ""
            flag = " ⚠" if cat in mismatch_cats else (
                   " ✗" if cat in missing_cats else (
                   " ＋" if cat in extra_cats else ""))
            sub.append(f"  | {cat_label}{flag} | {src_n} | {src_pct} | {harmonized_n} | {harmonized_pct} | {delta} |")
        return sub

    _check_notes = {
        "C9": (
            "> **Annotation key:** `[out+src]` = violation present in both source and harmonized "
            "(pre-existing in raw data, faithfully preserved); "
            "`[out only]` = harmonized exceeds bound but source did not "
            "(transformation may have introduced the issue); "
            "`[src only]` = source exceeds bound but harmonized does not "
            "(pipeline corrected or filtered the value)."
        ),
    }

    for check_id in ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "C10", "C11"]:
        check_results = [r for r in results if r.check_id == check_id]
        if not check_results:
            continue
        lines.append(f"## {check_id}: {check_names.get(check_id, check_id)}")
        lines.append("")
        if check_id in _check_notes:
            lines.append(_check_notes[check_id])
            lines.append("")
        for r in sorted(check_results, key=lambda x: _sort_key.get(x.status, 9)):
            icon = _STATUS_ICONS.get(r.status, r.status)
            lines.append(f"- {icon} **{_md_escape(r.variable)}**: {_md_escape(r.message)}")
            if check_id == "C7" and r.status in ("PASS", "WARN", "FAIL", "INFO"):
                lines.extend(_render_c7_detail(r))
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Compare source vs. harmonized summaries (C1-C10 checks).",
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
                        "Optional — PHV IDs are used as labels when not provided.")

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
        for warning in validate_clinical_ranges_config(clinical_ranges):
            print(f"WARNING: clinical ranges config: {warning}")
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
    crosswalk = build_variable_crosswalk(
        source_vars, harmonized_vars,
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
        print(f"  {m['source_key']:<30} -> {m['harmonized_key']:<40} [{method}]{extra}")

    # Run checks
    all_results: list[CheckResult] = []

    all_results.extend(check_c1_n_preservation(
        source, harmonized, fail_pct=c1_t.get("fail_pct", 1.0),
    ))

    for match in crosswalk:
        src_key = match["source_key"]
        harmonized_key = match["harmonized_key"]
        # Use per-PHT stats when available (eliminates multi-table inflation).
        src_var = match.get("_resolved_src") or source_vars.get(src_key, {})
        harmonized_var = harmonized_vars[harmonized_key]
        display_name = src_var.get("name", src_key)
        value_map = match.get("value_map")

        all_results.append(check_c2_n_loss(
            src_var, harmonized_var, display_name,
            pass_pct=c2_t.get("pass_pct", 0.5), warn_pct=c2_t.get("warn_pct", 2.0),
        ))
        all_results.append(check_c3_missing_accounting(
            src_var, harmonized_var, display_name,
            pass_pp=c3_t.get("pass_pp", 0.5), warn_pp=c3_t.get("warn_pp", 3.0),
            n_valid_pass_pct=c3_t.get("n_valid_pass_pct", 0.5),
            n_valid_warn_pct=c3_t.get("n_valid_warn_pct", 3.0),
        ))
        all_results.append(check_c4_mean_preservation(
            src_var, harmonized_var, display_name,
            pass_rel=c4_t.get("pass_rel", 0.001), warn_rel=c4_t.get("warn_rel", 0.01),
        ))
        all_results.append(check_c5_mean_after_conversion(
            src_var, harmonized_var, display_name,
            pass_rel=c5_t.get("pass_rel", 0.001),
        ))
        all_results.append(check_c6_sd_preservation(
            src_var, harmonized_var, display_name,
            pass_rel=c6_t.get("pass_rel", 0.002), warn_rel=c6_t.get("warn_rel", 0.01),
        ))
        all_results.append(check_c7_categorical_distribution(
            src_var, harmonized_var, display_name,
            pass_pct=c7_t.get("pass_pct", 0.5), value_map=value_map,
        ))
        all_results.append(check_c9_clinical_range(harmonized_var, display_name, clinical_ranges, src_var=src_var))
        all_results.append(check_c11_type_consistency(src_var, harmonized_var, display_name))

    all_results.extend(check_c8_visit_distribution(
        source, harmonized,
        warn_lo_ratio=c8_t.get("warn_lo_ratio", 0.95),
        warn_hi_ratio=c8_t.get("warn_hi_ratio", 1.05),
    ))
    all_results.extend(check_c10_cross_variable(harmonized_vars, clinical_ranges))

    # Flag unmatched variables
    matched_src = {m["source_key"] for m in crosswalk}
    matched_harmonized = {m["harmonized_key"] for m in crosswalk}
    for sk in source_vars:
        if sk not in matched_src and "error" not in source_vars[sk]:
            all_results.append(CheckResult(
                "C2", source_vars[sk].get("name", sk), "INFO", "Source variable not matched in harmonized"
            ))
    for ok in harmonized_vars:
        if ok not in matched_harmonized:
            all_results.append(CheckResult("C2", ok, "FAIL", "Harmonized variable not matched in source — no source PHV traceable"))

    # Summary
    counts: dict[str, int] = {}
    for r in all_results:
        counts[r.status] = counts.get(r.status, 0) + 1
    print(f"\n{'='*60}")
    print(f"Results: {counts}")

    # Write Markdown
    md = generate_markdown_report(all_results, cohort, source_meta, harmonized_meta)
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
        "crosswalk": crosswalk,
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
