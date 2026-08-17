"""Distribution checks: C4 (mean), C5 (mean after conversion), C6 (SD), C7 (categorical).

C4 and C6 compare continuous-variable mean and SD with relative-tolerance
thresholds. C5 applies a unit conversion factor before comparing means
(e.g., inches → cm). C7 compares categorical distributions after value
mappings are applied.
"""

from __future__ import annotations

from typing import Any

from hv_dataqc.compare._common import CheckResult, fmt_cmp_stat as _cmp_stat, fmt_n as _n
from hv_dataqc.hv_dataqc_common import normalize_category_key


def check_c4_mean_preservation(
    src_var: dict, harmonized_var: dict, var_name: str,
    pass_rel: float = 0.001, warn_rel: float = 0.01,
) -> CheckResult:
    """C4: Continuous mean comparison (no unit conversion)."""
    if src_var.get("_comparison_confidence") == "unsupported":
        return CheckResult(
            "C4", var_name, "SKIP",
            "Expected mean requires row-level joint counts; aggregate comparison not attempted",
            {"comparison_confidence": "unsupported",
             "comparison_limitations": src_var.get("_comparison_limitations") or []},
        )
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
                           _cmp_stat("Mean preserved", src_mean, harmonized_mean, rel_diff))
    if rel_diff <= warn_rel:
        return CheckResult("C4", var_name, "WARN",
                           _cmp_stat("Mean shifted", src_mean, harmonized_mean, rel_diff),
                           {"source_mean": src_mean, "harmonized_mean": harmonized_mean})
    # --- Unit-conversion detection ---
    # If the observed ratio matches a well-known unit conversion factor (±2%),
    # demote to WARN and annotate rather than FAIL.  The comparison cannot be
    # done accurately without knowing the expected factor; a C5 entry with an
    # explicit conversion_factor will give a definitive verdict.
    _KNOWN_FACTORS = [
        (0.001, "×0.001"), (0.01, "×0.01"), (0.1, "×0.1"),
        (10.0, "×10"), (100.0, "×100"), (1000.0, "×1000"),
        (0.453592, "lbs→kg"), (2.20462, "kg→lbs"),
        (2.54, "in→cm"), (0.393701, "cm→in"),
        (0.02586, "mg/dL→mmol/L cholesterol"), (38.67, "mmol/L→mg/dL cholesterol"),
        (0.0555, "mg/dL→mmol/L glucose"), (18.018, "mmol/L→mg/dL glucose"),
        (0.01129, "mg/dL→mmol/L triglycerides"), (88.57, "mmol/L→mg/dL triglycerides"),
        (6.0, "μIU→pmol/L insulin (approx)"), (0.1667, "pmol/L→μIU insulin (approx)"),
    ]
    _FACTOR_TOL = 0.02  # ±2 % tolerance
    ratio = harmonized_mean / src_mean
    for factor, label in _KNOWN_FACTORS:
        if abs(ratio - factor) / factor <= _FACTOR_TOL:
            return CheckResult(
                "C4", var_name, "WARN",
                f"Mean mismatch likely due to unit conversion ({label}, ratio={ratio:.4f}): "
                f"{_n(src_mean)} -> {_n(harmonized_mean)} (d={rel_diff:.4f}) — add conversion_factor to C5 for precise check",
                {"source_mean": src_mean, "harmonized_mean": harmonized_mean,
                 "observed_ratio": ratio, "suspected_conversion": label},
            )
    return CheckResult("C4", var_name, "FAIL",
                       f"Mean mismatch: {_n(src_mean)} -> {_n(harmonized_mean)} (d={rel_diff:.4f}, ratio={ratio:.4f})",
                       {"source_mean": src_mean, "harmonized_mean": harmonized_mean,
                        "observed_ratio": ratio})


def check_c5_mean_after_conversion(
    src_var: dict, harmonized_var: dict, var_name: str,
    conversion_factor: float | None = None, pass_rel: float = 0.001,
) -> CheckResult:
    """C5: Mean comparison with a known unit conversion factor."""
    if src_var.get("_comparison_confidence") == "unsupported":
        return CheckResult(
            "C5", var_name, "SKIP",
            "Expected converted mean requires row-level joint counts; aggregate comparison not attempted",
            {"comparison_confidence": "unsupported",
             "comparison_limitations": src_var.get("_comparison_limitations") or []},
        )
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


def should_run_c5_conversion_check(match: dict, c5_thresholds: dict) -> bool:
    """Return True only when C5 has an explicit conversion factor to validate.

    C5 is intentionally active-only: without a declared scalar conversion
    factor, emitting one SKIP per variable makes the report look like a real
    unit-conversion check ran when it did not.
    """
    return (match.get("conversion_factor") or c5_thresholds.get("conversion_factor")) is not None


def check_c6_sd_preservation(
    src_var: dict, harmonized_var: dict, var_name: str,
    pass_rel: float = 0.002, warn_rel: float = 0.01,
) -> CheckResult:
    """C6: Standard deviation comparison."""
    if src_var.get("_comparison_confidence") == "unsupported":
        return CheckResult(
            "C6", var_name, "SKIP",
            "Expected SD requires row-level joint counts; aggregate comparison not attempted",
            {"comparison_confidence": "unsupported",
             "comparison_limitations": src_var.get("_comparison_limitations") or []},
        )
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
                           _cmp_stat("SD preserved", src_sd, harmonized_sd, rel_diff))
    if rel_diff <= warn_rel:
        return CheckResult("C6", var_name, "WARN",
                           _cmp_stat("SD shifted", src_sd, harmonized_sd, rel_diff))
    return CheckResult("C6", var_name, "FAIL",
                       f"SD mismatch: {_n(src_sd)} -> {_n(harmonized_sd)} (d={rel_diff:.4f})",
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
    confidence = src_var.get("_comparison_confidence")
    limitations = src_var.get("_comparison_limitations") or []
    if confidence == "unsupported":
        return CheckResult(
            "C7", var_name, "SKIP",
            "Expected distribution requires row-level joint counts; aggregate comparison not attempted",
            {"comparison_confidence": confidence, "comparison_limitations": limitations},
        )

    src_dist = src_var.get("distribution", {})
    harmonized_dist = harmonized_var.get("distribution", {})
    if not src_dist:
        return CheckResult("C7", var_name, "SKIP", "No source distribution")

    # Translate using value_map
    if value_map:
        translated: dict[str, Any] = {}
        translated_total = 0
        normalized_value_map = {normalize_category_key(k): v for k, v in value_map.items()}
        for cat, stats in src_dist.items():
            norm_cat = normalize_category_key(cat)
            mapped = normalized_value_map.get(norm_cat)
            if not mapped:
                try:
                    mapped = normalized_value_map.get(str(int(float(norm_cat))))
                except (ValueError, OverflowError):
                    pass
            new_cat = normalize_category_key(mapped if mapped else norm_cat)
            existing = translated.setdefault(
                new_cat,
                {"n": 0, "pct": 0.0, "source_categories": []},
            )
            count = int(stats.get("n", 0) or 0)
            existing["n"] += count
            existing["source_categories"].append(norm_cat)
            translated_total += count
        for stats in translated.values():
            stats["pct"] = round(stats["n"] / translated_total * 100, 2) if translated_total else 0.0
            if len(stats["source_categories"]) == 1:
                stats.pop("source_categories", None)
        src_dist = translated
    else:
        # No value_map: still normalize source keys so dtype/formatting
        # differences (e.g. "1.0" vs "1") do not cause false category
        # mismatches. Mirrors the harmonized-key normalization below and the
        # value_map source normalization above. New source artifacts are
        # already normalized by categorical_stats; this also protects older
        # artifacts. Existing pct values are preserved (not recomputed, so the
        # sentinel-aware denominator downstream is unchanged); only keys that
        # genuinely collapse together have their n and pct summed.
        normalized_src: dict[str, Any] = {}
        for cat, stats in src_dist.items():
            norm_cat = normalize_category_key(cat)
            if norm_cat in normalized_src:
                existing = normalized_src[norm_cat]
                existing["n"] = int(existing.get("n", 0) or 0) + int(stats.get("n", 0) or 0)
                existing["pct"] = round(
                    float(existing.get("pct", 0) or 0) + float(stats.get("pct", 0) or 0), 2
                )
            else:
                normalized_src[norm_cat] = dict(stats)
        src_dist = normalized_src

    # Normalize harmonized keys — pipeline may serialize values as JSON arrays
    # or Python reprs such as "['OMOP:8527']" / "('OMOP:8527',)".
    normalized_out: dict[str, Any] = {}
    for ok, stats in harmonized_dist.items():
        norm_ok = normalize_category_key(ok)
        if norm_ok in normalized_out:
            # Two representations of the same category (e.g. "OMOP:8527" and
            # "['OMOP:8527']") collapse together — sum their n and pct rather
            # than letting the last writer win, which would silently discard
            # the earlier bucket's mass and could mask a real distribution
            # discrepancy as a match. Mirrors the source-side handling above.
            existing = normalized_out[norm_ok]
            existing["n"] = int(existing.get("n", 0) or 0) + int(stats.get("n", 0) or 0)
            existing["pct"] = round(
                float(existing.get("pct", 0) or 0) + float(stats.get("pct", 0) or 0), 2
            )
        else:
            normalized_out[norm_ok] = dict(stats)
    harmonized_dist = normalized_out

    src_keys = set(src_dist)
    harmonized_keys = set(harmonized_dist)
    missing = sorted(src_keys - harmonized_keys)
    extra = sorted(harmonized_keys - src_keys)

    # "None" in the expected distribution means source codes were explicitly
    # mapped to null (the drop sentinel) in the YAML value_mappings — those
    # rows produce no harmonised record by design.  Keep them visible in the
    # distribution table so reviewers can audit the drop, but do not treat
    # them as a missing category for FAIL/WARN purposes.
    none_drop_n = src_dist.get("None", {}).get("n", 0) if "None" in missing else 0
    missing_real = [m for m in missing if m != "None"]

    mismatches: list[dict] = []
    for cat in sorted(src_keys & harmonized_keys):
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
    if missing_real:
        detail["missing_categories"] = missing_real
    elif missing:  # only "None" entries — preserve for table display
        detail["missing_categories"] = missing
    if none_drop_n:
        detail["none_drop_n"] = none_drop_n
    if extra:
        detail["extra_categories"] = extra
    if mismatches:
        detail["mismatches"] = mismatches

    if not missing_real and not extra and not mismatches:
        if none_drop_n:
            return CheckResult("C7", var_name, "INFO",
                               f"Distribution matches; {none_drop_n} source rows "
                               f"explicitly excluded via None value_mapping (not in harmonized)",
                               detail)
        return CheckResult("C7", var_name, "PASS",
                           f"Distribution matches ({len(src_dist)} categories)", detail)
    if not mismatches and not missing_real:
        msgs = []
        if none_drop_n:
            msgs.append(f"{none_drop_n} rows excluded via None mapping")
        if extra:
            msgs.append(f"Extra harmonized categories: {extra}")
        return CheckResult("C7", var_name, "INFO", "; ".join(msgs), detail)
    if missing_real:
        if confidence == "partial":
            detail["comparison_confidence"] = confidence
            detail["comparison_limitations"] = limitations
            return CheckResult("C7", var_name, "WARN",
                               f"Partial expected distribution missing categories in harmonized: {missing_real}", detail)
        return CheckResult("C7", var_name, "FAIL",
                           f"Missing categories in harmonized: {missing_real}", detail)
    if confidence == "partial":
        detail["comparison_confidence"] = confidence
        detail["comparison_limitations"] = limitations
        return CheckResult("C7", var_name, "WARN",
                           f"Partial expected distribution has {len(mismatches)} category shift(s); row-level data needed for exact verdict", detail)
    return CheckResult("C7", var_name, "WARN",
                       f"{len(mismatches)} categories with >+/-{pass_pct}% shift", detail)
