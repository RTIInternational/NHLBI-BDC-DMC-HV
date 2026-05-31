"""Clinical range checks: C9.

Checks whether harmonized min/max values fall within clinically plausible
ranges defined in `clinical_ranges.yaml`. Catches sentinel values (e.g., 0,
999) that should have been mapped to missing, and unit-conversion errors
that produce impossible values.
"""

from __future__ import annotations

import re

from hv_dataqc.compare._common import CheckResult


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


def _match_clinical_range(
    var_name: str, observation_type: str, clinical_ranges: dict,
) -> tuple[str | None, dict | None, str, str | None]:
    """Return the best clinical range match and the basis used to match it."""
    matched_name: str | None = None
    matched_range: dict | None = None
    matched_method = "none"
    matched_code: str | None = None
    best_len = 0

    for range_name, rng in clinical_ranges.items():
        if range_name.startswith("_"):
            continue
        if var_name.upper() in [n.upper() for n in rng.get("common_phv_names", [])]:
            return range_name, rng, "common_phv_name", None
        codes = rng.get("oba_codes", []) + rng.get("omop_codes", [])
        if observation_type and observation_type in codes:
            return range_name, rng, "concept_code", observation_type
        # Word-boundary substring fallback: treat underscores as separators to prevent
        # e.g. range_name="wbc" matching var_name="wbc_pct_basophils".
        _wb_pattern = (r'(?<![A-Za-z0-9_])' + re.escape(range_name.upper())
                       + r'(?![A-Za-z0-9_])')
        if re.search(_wb_pattern, var_name.upper()) and len(range_name) > best_len:
            matched_name = range_name
            matched_range = rng
            matched_method = "substring"
            matched_code = None
            best_len = len(range_name)

    return matched_name, matched_range, matched_method, matched_code


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
        return CheckResult("C9", var_name, "SKIP", "Not continuous", {
            "range_name": None,
            "match_method": "not_applicable",
        })

    # Match range definition: exact name > code match > substring
    obs_type = harmonized_var.get("observation_type", "")
    range_name, matched, match_method, matched_code = _match_clinical_range(
        var_name, obs_type, clinical_ranges
    )
    detail = {
        "range_name": range_name,
        "match_method": match_method,
    }
    if matched_code:
        detail["matched_code"] = matched_code
    if obs_type:
        detail["observation_type"] = obs_type

    if not matched:
        return CheckResult("C9", var_name, "SKIP", "No clinical range defined", detail)

    out_min = harmonized_var.get("min")
    out_max = harmonized_var.get("max")
    detail.update({"min": out_min, "max": out_max})
    if out_min is None or out_max is None:
        return CheckResult("C9", var_name, "SKIP", "No min/max in harmonized", detail)

    out_issues = _range_violations(out_min, out_max, matched)

    if not out_issues:
        plaus_lo = matched.get("plausible_lo")
        plaus_hi = matched.get("plausible_hi")
        return CheckResult("C9", var_name, "PASS",
                           f"Range OK: [{out_min}, {out_max}] within [{plaus_lo}, {plaus_hi}]",
                           detail)

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
                       detail)
