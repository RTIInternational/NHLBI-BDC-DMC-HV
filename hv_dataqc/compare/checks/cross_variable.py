"""Cross-variable checks: C10 (consistency rules) and C12 (value mapping coverage).

C10 validates cross-variable rules from `_cross_variable_rules` in
clinical_ranges.yaml (e.g., SBP > DBP, FEV1 < FVC). It currently supports
simple 2-variable directional comparisons of means; formula-based rules
(e.g., BMI consistency) are not yet implemented.

C12 verifies that YAML value_mappings cover all dbGaP coded values for
the source PHV — a YAML completeness check that runs independently of
before/after preservation.
"""

from __future__ import annotations

import re

from hv_dataqc.compare._common import CheckResult
from hv_dataqc.compare.crosswalk import (
    _canonical_phv_id,
    _distribution_count_map,
    _is_null_sentinel_code,
    _normalize_code,
)
from hv_dataqc.hv_dataqc_common import normalize_category_key


def check_c12_value_mapping_coverage(match: dict, phv_value_codes: dict[str, set[str]]) -> list[CheckResult]:
    """C12: Verify YAML value_mappings cover dbGaP/observed source codes."""
    results: list[CheckResult] = []
    yaml_entries = match.get("_yaml_entries") or [match]
    source_summaries_by_phv = match.get("_source_summaries_by_phv") or {}
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
            observed_summary = source_summaries_by_phv.get(phv_id) or entry.get("source_summary")
            observed_counts = _distribution_count_map(observed_summary)
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
