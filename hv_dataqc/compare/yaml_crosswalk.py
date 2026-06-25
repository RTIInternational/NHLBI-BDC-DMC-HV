"""YAML transform file parsing: extract crosswalk entries and normalise harmonized keys.

Owns everything needed to turn a directory of HV ``.yaml`` files into a flat
list of ``{source_key, harmonized_key, ...}`` dicts.  Also owns the key-
normalisation helpers that fix dm-bip serialisation quirks in the harmonized
extract JSON (tuple-notation observation types, method_type suffixes, etc.).
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import yaml

from hv_dataqc.compare.helpers import _canonical_phv_id
from hv_dataqc.compare.expected_summary import _has_true_catchall, _true_arm_output_phvs


# ---------------------------------------------------------------------------
# YAML crosswalk construction helpers
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


# ---------------------------------------------------------------------------
# Unit conversion helpers
# ---------------------------------------------------------------------------

_COMMON_UNIT_FACTORS: dict[tuple[str, str], float] = {
    ("[lb_av]", "kg"): 0.453592,
    ("lb", "kg"): 0.453592,
    ("lbs", "kg"): 0.453592,
    ("kg", "[lb_av]"): 2.20462,
    ("kg", "lb"): 2.20462,
    ("kg", "lbs"): 2.20462,
    ("in", "cm"): 2.54,
    ("[in_i]", "cm"): 2.54,
    ("[in_us]", "cm"): 2.54,
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


# ---------------------------------------------------------------------------
# Concept CURIE extraction helpers
# ---------------------------------------------------------------------------

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
    # Structural classes that appear in YAML but have no source-variable
    # counterpart to crosswalk (e.g. Visit anchors measurements in time).
    # Skip them silently rather than emitting an "Unknown entity class" warning.
    STRUCTURAL_CLASSES = {"Visit"}

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

    def _is_value_slot_name(slot_name: str, value_slot_name: str) -> bool:
        return (
            slot_name == value_slot_name
            or slot_name in ("value_decimal", "value_integer", "value_coded", "value_concept")
            or slot_name.startswith("value")
        )

    def _phv_role_for_slot(
        slot_name: str,
        value_slot_name: str,
        concept_slot_name: str | None,
        is_value_slot: bool,
    ) -> str:
        if is_value_slot:
            return "value"
        if concept_slot_name and slot_name == concept_slot_name:
            return "concept"
        if slot_name == "associated_participant":
            return "participant_id"
        if slot_name == "associated_visit":
            return "visit"
        if slot_name == "age_at_observation" or slot_name.startswith("age_at"):
            return "age_at_observation"
        if "join" in slot_name:
            return "join_key"
        return "context"

    for class_name, class_body in class_derivations.items():
        if not isinstance(class_body, dict):
            continue

        entity_class = class_name
        if entity_class in STRUCTURAL_CLASSES:
            continue
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
        concept_exprs: list[str] = []
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
                            concept_exprs.append(expr)
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
            is_value_slot = _is_value_slot_name(slot_name, value_slot_name)
            if pf.startswith("phv"):
                primary_phvs.append(
                    {
                        "phv": pf,
                        "slot": slot_name,
                        "is_value_slot": is_value_slot,
                        "role": _phv_role_for_slot(
                            slot_name, value_slot_name, concept_slot_name, is_value_slot
                        ),
                        "value_map": _extract_value_mappings(slot_body),
                        "conversion_factor": None,
                    }
                )
            # PHVs referenced inside case() expressions
            expr = slot_body.get("expr", "")
            if isinstance(expr, str):
                is_value_expr = _is_value_slot_name(slot_name, value_slot_name)
                phv_role = _phv_role_for_slot(
                    slot_name, value_slot_name, concept_slot_name, is_value_expr
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
                            "role": phv_role,
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
                            is_inner_value_slot = _is_value_slot_name(inner_slot, "")
                            if inner_pf.startswith("phv"):
                                inner_uc = inner_slot_body.get("unit_conversion")
                                inner_cf_from_block = _unit_conversion_factor(inner_uc)
                                primary_phvs.append(
                                    {
                                        "phv": inner_pf,
                                        "slot": f"{slot_name}.{inner_slot}",
                                        "is_value_slot": is_inner_value_slot,
                                        "role": _phv_role_for_slot(
                                            inner_slot, "", None, is_inner_value_slot
                                        ),
                                        "value_map": _extract_value_mappings(inner_slot_body),
                                        "conversion_factor": inner_cf_from_block,
                                        "has_unit_conversion_def": isinstance(inner_uc, dict),
                                    }
                                )
                            inner_expr = inner_slot_body.get("expr", "")
                            if isinstance(inner_expr, str):
                                is_inner_value_expr = _is_value_slot_name(inner_slot, "")
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
                                            "role": _phv_role_for_slot(
                                                inner_slot, "", None, is_inner_value_expr
                                            ),
                                            "value_map": None,
                                            "conversion_factor": inner_cf,
                                            "expr": inner_expr,
                                        }
                                    )

        if not primary_phvs or not concept_codes:
            continue

        # method_type creates a compound harmonized key ``|<method_type>`` for
        # any MeasurementObservation block that has a method_type slot, whether
        # it is nested inside a MeasurementObservationSet or is a standalone MO.
        # The dm-bip harmonized extractor groups by (observation_type, method_type)
        # when method_type is present and emits keys like
        # ``measurement_OMOP:XXX|<method_type>``.  Standalone MO files without
        # a method_type slot (bdy_hgt, bmi, hrt_rt, ...) keep bare keys.
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
        if not value_phvs:
            # Condition blocks may have a coded concept PHV (e.g. PADDX or
            # STROKEDX via value_mappings) but a fixed condition_status value
            # such as 'PRESENT'.  The concept PHV is the driving variable in
            # that case — promote it to primary so the crosswalk builds
            # per-concept source entries (concept_phv == phv_id path in
            # build_expected_summary).  This resolves the "no YAML block
            # proposed this concept" false positive for such blocks (#670).
            concept_role_phvs = [p for p in primary_phvs if p.get("role") == "concept"]
            if concept_role_phvs:
                value_phvs = concept_role_phvs
            else:
                # No value PHV and no concept PHV — would use a structural PHV
                # (e.g. associated_participant / SUBJID) as the source key,
                # producing a misleading "subjid: N loss" C2 label.  Skip so
                # the unmatched-harmonized reporter surfaces the concept CURIE.
                continue
        primary = value_phvs[0]

        source_phv_roles: list[dict[str, str]] = []
        comparison_phvs: set[str] = set()
        seen_role_keys: set[tuple[str, str, str]] = set()
        for phv_ref in primary_phvs:
            phv_id = _canonical_phv_id(phv_ref.get("phv", ""))
            if not phv_id:
                continue
            role = str(phv_ref.get("role") or ("value" if phv_ref.get("is_value_slot") else "context"))
            slot = str(phv_ref.get("slot") or "")
            role_key = (phv_id, role, slot)
            if role_key not in seen_role_keys:
                source_phv_roles.append({"phv_id": phv_id, "role": role, "slot": slot})
                seen_role_keys.add(role_key)
            if role in {"value", "concept"}:
                comparison_phvs.add(phv_id)

        # Add any PHV referenced in the output of a (True, {phv}) fallback arm.
        # These PHVs drive most harmonized records but don't appear in conditions,
        # so they are absent from comparison_phvs without this step (issue #663).
        # set.update() deduplicates: Sub-type A patterns where the True-arm PHV
        # already appears in conditions are silently no-ops.
        for expr in value_exprs:
            comparison_phvs.update(_true_arm_output_phvs(expr))

        src_name = phv_names.get(primary["phv"], "")
        if not src_name:
            continue

        # Emit one crosswalk entry per unique concept code.  Case() exprs and
        # value_mappings-driven concept slots may produce multiple codes (e.g.
        # hdl.yaml: OMOP:4041720 & OBA:VT0000184, stroke.yaml: HP:0002140 &
        # MONDO:0013792, diabetes.yaml pht001490: MONDO:0005015 & MONDO:0006920).
        for concept_code in concept_codes:
            if method_type_val:
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
                    "concept_codes": concept_codes,
                    "concept_exprs": concept_exprs,
                    "concept_phv": concept_phv,
                    "entity_class": entity_class,
                    "value_map": primary["value_map"],
                    "concept_value_map": concept_value_map,
                    "method_type": method_type_val,
                    "conversion_factor": primary.get("conversion_factor"),
                    "has_unit_conversion": primary.get("has_unit_conversion_def", False),
                    "source_phvs": sorted(comparison_phvs),
                    "source_phv_roles": source_phv_roles,
                    "value_exprs": value_exprs,
                    "has_true_catchall": any(_has_true_catchall(e) for e in value_exprs),
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


def _normalize_method_type_part(s: str) -> str:
    """Normalize a method_type string for fuzzy matching.

    Strips commas, normalizes whitespace, and lowercases so that YAML values
    like ``pre-bronchodilator spirometry`` match harmonized keys like
    ``Pre-bronchodilator, spirometry``.
    """
    return re.sub(r"\s+", " ", s.replace(",", "").lower()).strip()


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
