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

from hv_dataqc.hv_dataqc_common import (
    canonical_phv_id,
    json_safe,
    load_phv_name_map as _shared_load_phv_name_map,
    normalize_category_key,
)
from hv_dataqc.compare._common import (
    CheckResult,
    CrosswalkBuildError,
    fmt_cmp as _cmp,
    fmt_cmp_stat as _cmp_stat,
    fmt_n as _n,
)
from hv_dataqc.compare.crosswalk import (  # noqa: F401  (many symbols re-exported for tests)
    # Used internally by checks and main():
    _codes_are_numeric_or_sentinel,
    _distribution_count_map,
    _is_null_sentinel_code,
    _normalize_code,
    _normalize_harmonized_vars,
    build_variable_crosswalk,
    determine_comparison_type,
    load_phv_type_map,
    load_phv_value_codes_map,
    # Re-exported for tests/external consumers (will be removed once
    # tests import directly from hv_dataqc.compare.crosswalk):
    _aggregate_source_summaries,
    _case_branches,
    _concept_codes_from_expr,
    _concept_codes_from_value_mappings,
    _expected_harmonized_n,
    _expected_summary_from_case_value_exprs,
    _expected_summary_from_concept_value_map,
    _expected_summary_from_value_map,
    _extract_crosswalk_from_class_derivations,
    _to_discovered_key,
    _unit_conversion_factor,
    authoritative_source_type_for_match,
    build_expected_summary,
)
from hv_dataqc.compare.checks.distributions import (
    check_c4_mean_preservation,
    check_c5_mean_after_conversion,
    check_c6_sd_preservation,
    check_c7_categorical_distribution,
    should_run_c5_conversion_check,
)
from hv_dataqc.compare.checks.missing_values import check_c3_missing_accounting
from hv_dataqc.compare.checks.n_preservation import (
    check_c1_n_preservation,
    check_c2_n_loss,
)
from hv_dataqc.compare.checks.visit_n import check_c8_visit_distribution
from hv_dataqc.compare.checks.type_consistency import check_c11_type_consistency
from hv_dataqc.compare.render import generate_markdown_report
from hv_dataqc.compare.report_io import (
    THRESHOLDS_PATH,
    load_thresholds,
    write_json_atomic_strict,
    write_text_atomic,
)

# Default clinical ranges config (relative to this script)
_CONFIG_DIR = Path(__file__).resolve().parent / "config"

_canonical_phv_id = canonical_phv_id
_json_safe = json_safe


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



# ---------------------------------------------------------------------------
# Check implementations
# ---------------------------------------------------------------------------








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
                   help=f"Statistical thresholds YAML (default: {THRESHOLDS_PATH})")
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
    thresholds_path = Path(args.thresholds) if args.thresholds else THRESHOLDS_PATH
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

        # Determine the expected comparison type from source/dbGaP/YAML intent.
        # The harmonized observed type is validated against this via C11.
        comparison_type_detail = determine_comparison_type(match, src_var, phv_type_map)
        comparison_type = comparison_type_detail.get("expected_type")
        if comparison_type and src_var.get("type") != comparison_type:
            src_var = {
                **src_var,
                "type": comparison_type,
                "_comparison_type_detail": comparison_type_detail,
            }

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
        harmonized_type = harmonized_var.get("type")
        if comparison_type == "continuous" and harmonized_type == "continuous":
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
        elif comparison_type == "categorical" and harmonized_type == "categorical":
            all_results.append(check_c7_categorical_distribution(
                src_var, harmonized_var, var_label,
                pass_pct=c7_t.get("pass_pct", 0.5), value_map=value_map,
            ))
        all_results.append(check_c9_clinical_range(harmonized_var, var_label, clinical_ranges, src_var=src_var))
        all_results.append(check_c11_type_consistency(
            src_var,
            harmonized_var,
            var_label,
            expected_type=comparison_type,
            type_basis=comparison_type_detail.get("basis"),
        ))
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
    write_text_atomic(report_path, md)
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
    write_json_atomic_strict(json_path, json_report)
    print(f"JSON report     : {json_path}")

    n_fail = counts.get("FAIL", 0)
    if n_fail > 0:
        print(f"\n{n_fail} FAIL(s) detected -- review report")
        sys.exit(1)
    else:
        print("\nAll checks passed or skipped")


if __name__ == "__main__":
    main()
