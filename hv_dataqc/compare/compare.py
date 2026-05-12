"""
hv_dataqc.compare — Source vs. Harmonized comparison orchestrator.

Compare aggregate summaries from extract_source_summaries.py (raw dbGaP source)
and extract_harmonized_summaries.py (dm-bip harmonized output). Runs checks C1–C12
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
  C12 Value Mapping Coverage     — YAML value_mappings cover dbGaP coded values

USAGE:
  python -m hv_dataqc.compare \\
      --source  spiromics_source_20250101T120000.json \\
      --harmonized  spiromics_harmonized_20250101T120000.json \\
      --cohort  SPIROMICS \\
      --yaml-dir /path/to/HV-repo/priority_variables_transform/SPIROMICS-ingest/ \\
      --cache-dir /path/to/data/dbgap-cache/spiromics/

  # --clinical-ranges defaults to compare/config/clinical_ranges.yaml.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from hv_dataqc.hv_dataqc_common import json_safe
from hv_dataqc.compare._common import (
    AmbiguousColumnError,
    CheckResult,
    CrosswalkBuildError,
)
from hv_dataqc.compare.crosswalk import (  # noqa: F401  (many symbols re-exported for tests)
    # Used internally by checks and main():
    _build_variables_by_name,
    _codes_are_numeric_or_sentinel,
    _distribution_count_map,
    _is_null_sentinel_code,
    _normalize_code,
    _normalize_harmonized_vars,
    _pick_single_pht_summary,
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
from hv_dataqc.compare.checks.clinical_ranges import check_c9_clinical_range
from hv_dataqc.compare.checks.cross_variable import (
    check_c10_cross_variable,
    check_c12_value_mapping_coverage,
)
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

# Backwards-compatible alias for tests that import _json_safe by name.
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


def _current_git_commit() -> str | None:
    """Return the short git commit hash for the repo containing this file,
    or None if git isn't available or the lookup fails."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent,
            timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _ambiguous_columns_fail(
    match: dict,
    ambiguous: list[dict],
    variables_by_name: dict[str, dict[str, dict]],
) -> CheckResult:
    """Build a FAIL CheckResult describing one or more ambiguous column lookups.

    A column is ambiguous when it appears in multiple source PHTs and the
    YAML/cache route couldn't pin it to one. The FAIL message and detail
    give the operator enough information to decide whether the YAML/cache
    needs fixing, or whether the column should be aggregated across PHTs
    (the deferred option B in the Phase B plan).
    """
    harmonized_key = match.get("harmonized_key", "?")
    parts: list[str] = []
    detail: dict = {
        "harmonized_key": harmonized_key,
        "yaml_file": match.get("yaml_file"),
        "ambiguous_columns": [],
    }
    for amb in ambiguous:
        col = amb["col"]
        phts = amb["phts"]
        role = amb.get("role", "source")
        phv = amb.get("phv_id") or "?"
        # Capture per-PHT stat summary (n_valid, mean, sd) so a reviewer can
        # see whether the PHTs disagree materially or just need pooling.
        pht_map = variables_by_name.get(col, {})
        per_pht_stats = {
            pht: {
                k: v for k, v in (pht_map.get(pht) or {}).items()
                if k in ("n_valid", "n_total", "mean", "sd", "n_distinct", "_pht")
            }
            for pht in phts
        }
        detail["ambiguous_columns"].append({
            "col": col,
            "role": role,
            "phv_id": phv,
            "phts": phts,
            "per_pht_stats": per_pht_stats,
        })
        parts.append(
            f"column {col!r} ({role}; phv={phv}) appears in {len(phts)} PHTs: "
            f"{', '.join(phts)}"
        )
    msg = (
        "Ambiguous source-column lookup; could not pick a single PHT. "
        + " | ".join(parts)
        + ". Fix the YAML to disambiguate the PHV→PHT mapping, "
        "or add PHT aggregation if these summaries should be pooled."
    )
    return CheckResult("CROSSWALK", harmonized_key, "FAIL", msg, detail)


# ---------------------------------------------------------------------------
# Check implementations
# ---------------------------------------------------------------------------


















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
        description="Compare source vs. harmonized summaries (C1-C12 checks).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--source", required=True, metavar="JSON",
                   help="Source summary JSON from extract_source_summaries.py")
    p.add_argument("--harmonized", required=True, metavar="JSON",
                   help="Harmonized summary JSON from extract_harmonized_summaries.py")
    p.add_argument("--cohort", required=True, metavar="NAME",
                   help="Cohort name (e.g. SPIROMICS, CARDIA)")

    p.add_argument("--yaml-dir", metavar="DIR", required=True,
                   help="HV YAML transform directory for the cohort "
                        "(e.g. .../priority_variables_transform/SPIROMICS-ingest/).")
    p.add_argument("--cache-dir", metavar="DIR", required=True,
                   help="dbGaP cache directory for the cohort, used to resolve PHV->name "
                        "(e.g. data/dbgap-cache/spiromics/). Must contain "
                        "pheno_variable_summaries/*.data_dict.xml.")

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
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    cohort = args.cohort.upper()

    # Validate inputs
    for path_arg, label in [(args.source, "--source"), (args.harmonized, "--harmonized")]:
        if not Path(path_arg).exists():
            print(f"ERROR: {label} file not found: {path_arg}", file=sys.stderr)
            sys.exit(1)

    # Resolve required paths
    yaml_dir = Path(args.yaml_dir)
    cache_dir = Path(args.cache_dir)
    if not yaml_dir.exists():
        print(f"ERROR: --yaml-dir not found: {yaml_dir}", file=sys.stderr)
        sys.exit(2)
    if not cache_dir.exists():
        print(f"ERROR: --cache-dir not found: {cache_dir}", file=sys.stderr)
        sys.exit(2)

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

    variables_by_pht = source.get("variables_by_pht", {})
    variables_by_name = _build_variables_by_name(variables_by_pht)
    harmonized_vars = _normalize_harmonized_vars(harmonized.get("variables", {}))
    source_meta = source.get("metadata", {})
    harmonized_meta = harmonized.get("metadata", {})

    print(f"\nSource: {len(variables_by_name)} variables across "
          f"{len(variables_by_pht)} PHTs, "
          f"{source.get('total_participants', '?')} participants")
    print(f"Harmonized: {len(harmonized_vars)} variables, "
          f"{harmonized.get('total_participants', '?')} participants")

    # Build crosswalk
    print("\nBuilding variable crosswalk...")
    yaml_diagnostics: dict = {}
    try:
        crosswalk = build_variable_crosswalk(
            variables_by_name, harmonized_vars,
            yaml_dir=yaml_dir,
            cache_dir=cache_dir,
            source_doc=source,
            diagnostics_out=yaml_diagnostics,
        )
    except CrosswalkBuildError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
    method_counts: dict[str, int] = {}
    for m in crosswalk:
        method_counts[m.get("match_method", "?")] = method_counts.get(m.get("match_method", "?"), 0) + 1
    method_summary = ", ".join(f"{n} {k}" for k, n in sorted(method_counts.items()))
    print(f"Matched {len(crosswalk)} variable pairs ({method_summary})")
    for m in crosswalk:
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
        print(f"  {m['source_key']:<30} -> {m['harmonized_key']:<40}{extra}")

    # Load dbGaP authoritative type map for source-type override (fixes heuristic
    # misclassification of true-integer count variables as categorical when
    # n_distinct ≤ 20, e.g. fruitf25 "how many fruits per day" range 0-20).
    phv_type_map: dict[str, str] = load_phv_type_map(cache_dir)
    phv_value_codes: dict[str, set[str]] = load_phv_value_codes_map(cache_dir)

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

        # If the crosswalk recorded an ambiguous column lookup (column appears
        # in multiple PHTs and the YAML/cache couldn't pick one), surface a
        # FAIL with diagnostic detail and skip the rest of the checks for this
        # match — the source summary would be unreliable.
        ambiguous = match.get("_ambiguous_columns") or []
        if ambiguous:
            all_results.append(_ambiguous_columns_fail(
                match, ambiguous, variables_by_name
            ))
            continue

        # Use pooled per-PHT stats from the match when present; fall back
        # to picking the only PHT's summary by column name. If the column
        # is itself ambiguous, AmbiguousColumnError → caught above (the
        # crosswalk already recorded it on the match).
        try:
            src_var = match.get("_resolved_src") or _pick_single_pht_summary(
                variables_by_name, src_key
            ) or {}
        except AmbiguousColumnError as exc:
            all_results.append(_ambiguous_columns_fail(
                match,
                [{"col": exc.col, "phts": sorted(exc.pht_map),
                  "role": "source", "phv_id": match.get("phv_id")}],
                variables_by_name,
            ))
            continue
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
        else:
            matched_src.add(m["source_key"])
    matched_harmonized = {m["harmonized_key"] for m in crosswalk}
    _unmatched_src_keys = [
        col for col in variables_by_name if col not in matched_src
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
            "git_commit": _current_git_commit(),
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
