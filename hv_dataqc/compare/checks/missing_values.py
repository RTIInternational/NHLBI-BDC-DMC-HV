"""Missing-value accounting: C3.

Compares per-variable missing-value rates between source and harmonized.
Falls back to n_valid comparison when source/harmonized denominators differ
by >20% (typical when source is concatenated raw TSVs).
"""

from __future__ import annotations

from hv_dataqc.compare._common import CheckResult, fmt_cmp as _cmp, fmt_n as _n


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
    confidence = src_var.get("_comparison_confidence")
    limitations = src_var.get("_comparison_limitations") or []

    if confidence == "unsupported":
        return CheckResult(
            "C3", var_name, "SKIP",
            "Expected missingness requires row-level joint counts; aggregate comparison not attempted",
            {"comparison_confidence": confidence, "comparison_limitations": limitations},
        )

    if src_total > 0 and harmonized_total > 0:
        denom_ratio = min(src_total, harmonized_total) / max(src_total, harmonized_total)
        if denom_ratio < 0.8:
            if src_valid == 0:
                return CheckResult("C3", var_name, "SKIP",
                                   "No valid source values (denominator mismatch)")
            if harmonized_valid == src_valid:
                return CheckResult("C3", var_name, "PASS",
                                   f"n_valid preserved: {_n(src_valid)}")
            diff_pct = abs(harmonized_valid - src_valid) / src_valid * 100
            if confidence == "partial":
                return CheckResult(
                    "C3", var_name, "WARN",
                    f"Partial expected n_valid differs from harmonized: {_n(src_valid)} -> {_n(harmonized_valid)} ({diff_pct:.1f}%); row-level data needed for exact verdict",
                    {"source_n_valid": src_valid, "harmonized_n_valid": harmonized_valid,
                     "comparison_confidence": confidence, "comparison_limitations": limitations},
                )
            if diff_pct <= n_valid_pass_pct:
                return CheckResult("C3", var_name, "PASS",
                                   f"n_valid within {n_valid_pass_pct}%: {_n(src_valid)} -> {_n(harmonized_valid)}")
            if diff_pct <= n_valid_warn_pct:
                return CheckResult("C3", var_name, "WARN",
                                   f"n_valid shifted: {_n(src_valid)} -> {_n(harmonized_valid)} ({diff_pct:.1f}%)")
            return CheckResult("C3", var_name, "FAIL",
                               f"n_valid mismatch: {_n(src_valid)} -> {_n(harmonized_valid)} ({diff_pct:.1f}%)",
                               {"source_n_valid": src_valid, "harmonized_n_valid": harmonized_valid})

    src_pct = src_var.get("pct_missing", 0)
    harmonized_pct = harmonized_var.get("pct_missing", 0)
    diff = abs(harmonized_pct - src_pct)

    if diff <= pass_pp:
        return CheckResult("C3", var_name, "PASS",
                           f"Missing rate: {_cmp(src_pct, harmonized_pct, '%')}")
    if diff <= warn_pp:
        return CheckResult("C3", var_name, "WARN",
                           f"Missing rate changed: {src_pct}% -> {harmonized_pct}% (d={diff:.1f}%)")
    return CheckResult("C3", var_name, "FAIL",
                       f"Large missing rate change: {src_pct}% -> {harmonized_pct}% (d={diff:.1f}%)",
                       {"source_pct": src_pct, "harmonized_pct": harmonized_pct})
