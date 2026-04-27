"""
compare_bdc_topmed.py — Cross-cohort comparison of BDC vs TOPMed DCC summaries
================================================================================
Reads per-cohort aggregate JSON summaries from extract_topmed_summaries.py and
extract_harmonized_summaries.py, then produces a structured side-by-side comparison report.

Both input JSONs use the same variable naming scheme (TOPMed DCC variable
names as keys), making alignment automatic.

OUTPUT: Text report (stdout and/or file) with per-variable comparison tables.

USAGE:
    # Single cohort comparison (original mode)
    python compare_bdc_topmed.py \\
        --topmed-json  /path/to/topmed_whi_summary.json \\
        --bdc-json     /path/to/bdc_whi_summary.json \\
        [--output      /path/to/WHI_comparison_report.txt]

    # Batch mode: auto-discover and compare all cohorts
    python compare_bdc_topmed.py \\
        --batch \\
        --bdc-dir      /path/to/BDC_Output/ \\
        --topmed-dir   /path/to/TOPMed_Output/ \\
        [--output-dir  /path/to/comparison_output/]

    # Batch with default paths (run from TOPMed_DCC_Compare directory)
    python compare_bdc_topmed.py --batch
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ─────────────────────────────────────────────────────────────────────────────
# REPORT FORMAT CONTROL
# Internal switch used while rendering TXT and Markdown reports.
# ─────────────────────────────────────────────────────────────────────────────

_REPORT_FMT: str = "txt"  # "txt" | "md"


def _md_cell(value: object) -> str:
    """Escape a value for use in a Markdown table cell."""
    text = str(value)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


# ─────────────────────────────────────────────────────────────────────────────
# REPORT FORMATTING
# ─────────────────────────────────────────────────────────────────────────────

def section(title: str, width: int = 76) -> None:
    if _REPORT_FMT == "md":
        print(f"\n---\n\n## {title}")
    else:
        print()
        print("=" * width)
        print(f"  {title}")
        print("=" * width)


def subsection(title: str) -> None:
    if _REPORT_FMT == "md":
        print(f"\n### {title}")
    else:
        print(f"\n  ── {title} ──")


def print_categorical_comparison(
    var_name: str,
    t_stats: dict | None,
    b_stats: dict | None,
    bdc_label: str,
) -> None:
    """Print side-by-side categorical frequency table."""
    t_dist = (t_stats or {}).get("distribution", {})
    b_dist = (b_stats or {}).get("distribution", {})
    all_cats = list(dict.fromkeys(list(t_dist.keys()) + list(b_dist.keys())))

    t_total = (t_stats or {}).get("n_total", 0)
    b_total = (b_stats or {}).get("n_total", 0)

    tM = (t_stats or {}).get("n_missing", 0)
    tMP = (t_stats or {}).get("pct_missing", 0.0)
    bM = (b_stats or {}).get("n_missing", 0)
    bMP = (b_stats or {}).get("pct_missing", 0.0)
    delta_m = bM - tM
    delta_m_str = f"{delta_m:+,}" if delta_m != 0 else "0"

    if _REPORT_FMT == "md":
        print(f"\n#### {_md_cell(bdc_label)} (`{_md_cell(var_name)}`)\n")
        print("| Category | TOPMed N | TOPMed % | BDC N | BDC % | Delta |")
        print("|:---|---:|---:|---:|---:|---:|")
        for cat in all_cats:
            tN = t_dist.get(cat, {}).get("n", 0)
            tP = t_dist.get(cat, {}).get("pct", 0.0)
            bN = b_dist.get(cat, {}).get("n", 0)
            bP = b_dist.get(cat, {}).get("pct", 0.0)
            delta = bN - tN
            delta_str = f"{delta:+,}" if delta != 0 else "0"
            print(f"| {_md_cell(cat)} | {tN:,} | {tP:.1f}% | {bN:,} | {bP:.1f}% | {delta_str} |")
        print(f"| *Missing / Null* | {tM:,} | {tMP:.1f}% | {bM:,} | {bMP:.1f}% | {delta_m_str} |")
        return

    print(f"\n    {bdc_label} ({var_name})")
    print(f"    {'Category':<40} {'TOPMed N':>10} {'%':>7}  {'BDC N':>10} {'%':>7}  {'Delta':>8}")
    print("    " + "-" * 85)

    for cat in all_cats:
        tN = t_dist.get(cat, {}).get("n", 0)
        tP = t_dist.get(cat, {}).get("pct", 0.0)
        bN = b_dist.get(cat, {}).get("n", 0)
        bP = b_dist.get(cat, {}).get("pct", 0.0)
        delta = bN - tN
        delta_str = f"{delta:+,}" if delta != 0 else "0"
        print(f"    {cat:<40} {tN:>10,} {tP:>6.1f}%  {bN:>10,} {bP:>6.1f}%  {delta_str:>8}")

    print(f"    {'Missing / Null':<40} {tM:>10,} {tMP:>6.1f}%  {bM:>10,} {bMP:>6.1f}%  {delta_m_str:>8}")


def print_continuous_comparison(
    var_name: str,
    t_stats: dict | None,
    b_stats: dict | None,
    bdc_label: str,
) -> None:
    """Print side-by-side continuous variable statistics."""
    t = t_stats or {}
    b = b_stats or {}

    t_visit = t.get("visit_label", "baseline")
    b_visit = b.get("visit_label", "")

    unit = t.get("unit") or b.get("unit") or ""

    stat_keys = [
        ("N (valid)", "n_valid", True),
        ("N (missing)", "n_missing", True),
        ("% missing", "pct_missing", False),
        ("Mean", "mean", False),
        ("SD", "sd", False),
        ("Median", "median", False),
        ("Q1", "q1", False),
        ("Q3", "q3", False),
        ("Min", "min", False),
        ("Max", "max", False),
        ("N implausible", "n_implausible", True),
    ]

    if _REPORT_FMT == "md":
        print(f"\n#### {_md_cell(bdc_label)} (`{_md_cell(var_name)}`)")
        if unit:
            print(f"\n*Unit: {_md_cell(unit)}*")
        if b_visit:
            print(f"*BDC visit: {_md_cell(b_visit)}*")
        print("\n| Statistic | TOPMed | BDC | Delta |")
        print("|:---|---:|---:|---:|")
        for display, key, is_int in stat_keys:
            tv = t.get(key)
            bv = b.get(key)
            tv_str = (f"{tv:,}" if is_int else f"{tv:.4f}") if tv is not None else "—"
            bv_str = (f"{bv:,}" if is_int else f"{bv:.4f}") if bv is not None else "—"
            if tv is not None and bv is not None:
                delta = bv - tv
                delta_str = f"{delta:+,}" if is_int else f"{delta:+.4f}"
            else:
                delta_str = "—"
            print(f"| {display} | {tv_str} | {bv_str} | {delta_str} |")
        return

    print(f"\n    {bdc_label} ({var_name})")
    if unit:
        print(f"    Unit: {unit}")
    if b_visit:
        print(f"    BDC visit: {b_visit}")

    print(f"    {'Statistic':<25} {'TOPMed':>15} {'BDC':>15} {'Delta':>12}")
    print("    " + "-" * 70)

    for display, key, is_int in stat_keys:
        tv = t.get(key)
        bv = b.get(key)
        if is_int:
            tv_str = f"{tv:,}" if tv is not None else "—"
            bv_str = f"{bv:,}" if bv is not None else "—"
        else:
            tv_str = f"{tv:.4f}" if tv is not None else "—"
            bv_str = f"{bv:.4f}" if bv is not None else "—"

        if tv is not None and bv is not None:
            delta = bv - tv
            if is_int:
                delta_str = f"{delta:+,}"
            else:
                delta_str = f"{delta:+.4f}"
        else:
            delta_str = "—"

        print(f"    {display:<25} {tv_str:>15} {bv_str:>15} {delta_str:>12}")


# ─────────────────────────────────────────────────────────────────────────────
# TIER ASSIGNMENT HELPERS
# Thresholds match match_quality_table.py for cross-tool consistency.
# ─────────────────────────────────────────────────────────────────────────────

def _assign_value_tier_continuous(norm_delta: float) -> str:
    """Tier based on |delta| / TOPMed SD (T1=near-exact ... T5=substantial)."""
    if norm_delta < 0.005:
        return "T1"
    elif norm_delta < 0.02:
        return "T2"
    elif norm_delta < 0.05:
        return "T3"
    elif norm_delta < 0.1:
        return "T4"
    else:
        return "T5"


def _assign_value_tier_categorical(max_pct_diff: float) -> str:
    """Tier based on max category pct-point difference."""
    if max_pct_diff < 0.5:
        return "T1"
    elif max_pct_diff < 1.0:
        return "T2"
    elif max_pct_diff < 3.0:
        return "T3"
    elif max_pct_diff < 10.0:
        return "T4"
    else:
        return "T5"


def _assign_miss_tier(miss_diff_pp: float) -> str:
    """Tier based on abs missingness pct-point difference."""
    if miss_diff_pp < 1.0:
        return "M1"
    elif miss_diff_pp < 3.0:
        return "M2"
    elif miss_diff_pp < 8.0:
        return "M3"
    elif miss_diff_pp < 20.0:
        return "M4"
    else:
        return "M5"


# ─────────────────────────────────────────────────────────────────────────────
# MAIN COMPARISON
# ─────────────────────────────────────────────────────────────────────────────

def load_json(path: str, label: str) -> dict:
    """Load and validate a summary JSON file."""
    print(f"  Loading {label}: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"  ERROR: File not found: {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"  ERROR: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    n = data.get("total_participants", 0)
    source = data.get("metadata", {}).get("source", "unknown")
    cohort = data.get("cohort", {}).get("name", data.get("metadata", {}).get("cohort", "unknown"))
    print(f"    {source} / {cohort}: {n:,} participants, "
          f"{len(data.get('variables', {}))} variables")
    return data


def run_comparison(topmed: dict, bdc: dict) -> dict:
    """Produce full comparison report from two aggregate JSONs.

    Returns a structured summary dict with key metrics for cross-cohort rollup.
    """

    t_vars = topmed.get("variables", {})
    b_vars = bdc.get("variables", {})
    all_vars = list(dict.fromkeys(list(t_vars.keys()) + list(b_vars.keys())))

    t_cohort = topmed.get("cohort", {}).get("name", "?")
    b_cohort = bdc.get("cohort", {}).get("name", "?")

    # ── Header ──
    section(f"{t_cohort} HARMONIZATION COMPARISON: TOPMed DCC vs. BDC DMC")
    if _REPORT_FMT == "md":
        print(f"- **Cohort:** {_md_cell(topmed.get('cohort', {}).get('full_name', t_cohort))}")
        print(f"- **TOPMed participants:** {topmed.get('total_participants', 0):,}")
        print(f"- **BDC participants:** {bdc.get('total_participants', 0):,}")
        print(f"- **TOPMed variables:** {len(t_vars)}")
        print(f"- **BDC variables:** {len(b_vars)}")
        print(f"- **Matched variables:** {len(set(t_vars) & set(b_vars))}")
    else:
        print(f"  Cohort: {topmed.get('cohort', {}).get('full_name', t_cohort)}")
        print(f"  TOPMed participants: {topmed.get('total_participants', 0):,}")
        print(f"  BDC participants:    {bdc.get('total_participants', 0):,}")
        print(f"  TOPMed variables:    {len(t_vars)}")
        print(f"  BDC variables:       {len(b_vars)}")
        print(f"  Matched variables:   {len(set(t_vars) & set(b_vars))}")

    # ── Participant count check ──
    n_t = topmed.get("total_participants", 0)
    n_b = bdc.get("total_participants", 0)
    if n_t > 0 and n_b > 0:
        delta = n_b - n_t
        pct = delta / n_t * 100
        print(f"\n  Participant delta: {delta:+,} ({pct:+.1f}%)")
        if abs(pct) > 5:
            print("  ⚠ >5% difference in participant counts — investigate consent group coverage.")

    # ── Coverage matrix ──
    section("VARIABLE COVERAGE MATRIX")
    n_matched = 0
    n_topmed_only = 0
    n_bdc_only = 0
    _cov_rows: list[tuple[str, bool, bool]] = []
    for var in sorted(all_vars):
        in_t = var in t_vars
        in_b = var in b_vars
        label = (t_vars.get(var) or b_vars.get(var, {})).get("bdc_label", var)
        _cov_rows.append((label, in_t, in_b))
        if in_t and in_b:
            n_matched += 1
        elif in_t:
            n_topmed_only += 1
        else:
            n_bdc_only += 1

    if _REPORT_FMT == "md":
        print("| Variable | TOPMed | BDC | Match |")
        print("|:---|:---:|:---:|:---:|")
        for label, in_t, in_b in _cov_rows:
            t_s = "Y" if in_t else "—"
            b_s = "Y" if in_b else "—"
            m_s = "Y" if in_t and in_b else "—"
            print(f"| {_md_cell(label)} | {t_s} | {b_s} | {m_s} |")
        print(f"\nMatched: **{n_matched}** | TOPMed only: {n_topmed_only} | BDC only: {n_bdc_only}")
    else:
        print(f"  {'Variable':<40} {'TOPMed':^8} {'BDC':^8} {'Match':^8}")
        print("  " + "-" * 65)
        for label, in_t, in_b in _cov_rows:
            t_s = "✓" if in_t else "—"
            b_s = "✓" if in_b else "—"
            m_s = "✓" if in_t and in_b else "—"
            print(f"  {label:<40} {t_s:^8} {b_s:^8} {m_s:^8}")
        print(f"\n  Matched: {n_matched}  |  TOPMed only: {n_topmed_only}  |  BDC only: {n_bdc_only}")

    # ── BDC-only variable inventory (discovered variables not in TOPMed) ──
    bdc_only_vars = sorted(set(b_vars) - set(t_vars))
    if bdc_only_vars:
        section("BDC-ONLY VARIABLES (not in TOPMed DCC)")
        # Group by dataset
        bdc_only_by_ds: dict[str, list[str]] = {}
        for var in bdc_only_vars:
            ds = b_vars[var].get("dataset", "other")
            bdc_only_by_ds.setdefault(ds, []).append(var)
        for ds in sorted(bdc_only_by_ds.keys()):
            print(f"\n  {ds} ({len(bdc_only_by_ds[ds])} variables):")
            for var in sorted(bdc_only_by_ds[ds]):
                stat = b_vars[var]
                label = stat.get("bdc_label", var)
                vtype = stat.get("type", "?")
                n_valid = stat.get("n_valid", 0)
                if vtype == "continuous":
                    mean = stat.get("mean")
                    sd = stat.get("sd")
                    mean_str = f"mean={mean:.2f}" if mean is not None else "mean=—"
                    sd_str = f"sd={sd:.2f}" if sd is not None else "sd=—"
                    print(f"    {label:<50} {vtype:<12} n={n_valid:>8,}  {mean_str} {sd_str}")
                else:
                    dist = stat.get("distribution", {})
                    top_cats = ", ".join(
                        f"{k}:{v['n']}" for k, v in sorted(
                            dist.items(), key=lambda x: -x[1].get('n', 0)
                        )[:3]
                    )
                    print(f"    {label:<50} {vtype:<12} n={n_valid:>8,}  [{top_cats}]")

    # ── Per-variable comparisons (matched only) ──
    matched_vars = sorted(set(t_vars) & set(b_vars))

    # Group by dataset
    datasets_order = [
        "demographics", "baseline_covariates", "blood_pressure", "lipids",
        "blood_cell_count", "inflammation", "atherosclerosis",
        "atherosclerosis_events_prior", "atherosclerosis_events_incident",
        "vte", "sleep", "measurements", "conditions", "procedures",
        "observations", "drugs",
        # BDC discovery datasets (from extract_harmonized_summaries.py --all mode)
        "bdc_measurement", "bdc_condition", "bdc_procedure",
        "bdc_observation", "bdc_drug_exposure",
    ]
    var_by_dataset: dict[str, list[str]] = {}
    for var in matched_vars:
        ds = (t_vars.get(var) or b_vars.get(var, {})).get("dataset", "other")
        var_by_dataset.setdefault(ds, []).append(var)

    tier_rows: list[dict] = []  # collected during per-variable loops for scorecard

    for ds in datasets_order:
        if ds not in var_by_dataset:
            continue
        section(f"COMPARISON: {ds.upper().replace('_', ' ')}")

        for var in sorted(var_by_dataset[ds]):
            t_stat = t_vars.get(var, {})
            b_stat = b_vars.get(var, {})
            label = (t_stat or b_stat).get("bdc_label", var)
            var_type = (t_stat or b_stat).get("type", "categorical")

            if var_type == "categorical":
                print_categorical_comparison(var, t_stat, b_stat, label)
            else:
                print_continuous_comparison(var, t_stat, b_stat, label)

            # Collect tier data for scorecard
            t_pm = t_stat.get("pct_missing", 0) or 0
            b_pm = b_stat.get("pct_missing", 0) or 0
            miss_tier = _assign_miss_tier(abs(b_pm - t_pm))
            if var_type == "categorical":
                t_dist = t_stat.get("distribution", {})
                b_dist = b_stat.get("distribution", {})
                all_cats = set(list(t_dist.keys()) + list(b_dist.keys()))
                max_pct_diff = max(
                    (abs(t_dist.get(c, {}).get("pct", 0) - b_dist.get(c, {}).get("pct", 0))
                     for c in all_cats),
                    default=0.0,
                )
                val_tier = _assign_value_tier_categorical(max_pct_diff)
                val_delta_str = f"max+-{max_pct_diff:.1f}pp"
            else:
                t_mean = t_stat.get("mean")
                b_mean = b_stat.get("mean")
                t_sd = t_stat.get("sd") or 1
                if t_mean is not None and b_mean is not None and t_sd > 0:
                    norm_delta = abs(b_mean - t_mean) / t_sd
                    val_tier = _assign_value_tier_continuous(norm_delta)
                    val_delta_str = f"{norm_delta:.4f} SD"
                else:
                    val_tier = "?"
                    val_delta_str = "—"
            tier_rows.append({
                "dataset": ds,
                "var": var,
                "label": label,
                "type": var_type[:4],
                "t_n": t_stat.get("n_valid", t_stat.get("n_total", 0)),
                "b_n": b_stat.get("n_valid", b_stat.get("n_total", 0)),
                "val_delta_str": val_delta_str,
                "t_pm": t_pm,
                "b_pm": b_pm,
                "val_tier": val_tier,
                "miss_tier": miss_tier,
            })

    # Handle any remaining datasets
    remaining = set(var_by_dataset.keys()) - set(datasets_order)
    for ds in sorted(remaining):
        section(f"COMPARISON: {ds.upper()}")
        for var in sorted(var_by_dataset[ds]):
            t_stat = t_vars.get(var, {})
            b_stat = b_vars.get(var, {})
            label = (t_stat or b_stat).get("bdc_label", var)
            var_type = (t_stat or b_stat).get("type", "categorical")
            if var_type == "categorical":
                print_categorical_comparison(var, t_stat, b_stat, label)
            else:
                print_continuous_comparison(var, t_stat, b_stat, label)

            # Collect tier data for scorecard
            t_pm = t_stat.get("pct_missing", 0) or 0
            b_pm = b_stat.get("pct_missing", 0) or 0
            miss_tier = _assign_miss_tier(abs(b_pm - t_pm))
            if var_type == "categorical":
                t_dist = t_stat.get("distribution", {})
                b_dist = b_stat.get("distribution", {})
                all_cats = set(list(t_dist.keys()) + list(b_dist.keys()))
                max_pct_diff = max(
                    (abs(t_dist.get(c, {}).get("pct", 0) - b_dist.get(c, {}).get("pct", 0))
                     for c in all_cats),
                    default=0.0,
                )
                val_tier = _assign_value_tier_categorical(max_pct_diff)
                val_delta_str = f"max+-{max_pct_diff:.1f}pp"
            else:
                t_mean = t_stat.get("mean")
                b_mean = b_stat.get("mean")
                t_sd = t_stat.get("sd") or 1
                if t_mean is not None and b_mean is not None and t_sd > 0:
                    norm_delta = abs(b_mean - t_mean) / t_sd
                    val_tier = _assign_value_tier_continuous(norm_delta)
                    val_delta_str = f"{norm_delta:.4f} SD"
                else:
                    val_tier = "?"
                    val_delta_str = "—"
            tier_rows.append({
                "dataset": ds,
                "var": var,
                "label": label,
                "type": var_type[:4],
                "t_n": t_stat.get("n_valid", t_stat.get("n_total", 0)),
                "b_n": b_stat.get("n_valid", b_stat.get("n_total", 0)),
                "val_delta_str": val_delta_str,
                "t_pm": t_pm,
                "b_pm": b_pm,
                "val_tier": val_tier,
                "miss_tier": miss_tier,
            })

    # ── Match Quality Scorecard ──
    section("MATCH QUALITY SCORECARD")
    val_tier_counts: dict[str, int] = {"T1": 0, "T2": 0, "T3": 0, "T4": 0, "T5": 0}
    miss_tier_counts: dict[str, int] = {"M1": 0, "M2": 0, "M3": 0, "M4": 0, "M5": 0}
    for row in tier_rows:
        val_tier_counts[row["val_tier"]] = val_tier_counts.get(row["val_tier"], 0) + 1
        if row["miss_tier"] in miss_tier_counts:
            miss_tier_counts[row["miss_tier"]] += 1
    t1, t2, t3, t4, t5 = (
        val_tier_counts["T1"], val_tier_counts["T2"], val_tier_counts["T3"],
        val_tier_counts["T4"], val_tier_counts["T5"],
    )
    m1, m2, m3, m4, m5 = (
        miss_tier_counts["M1"], miss_tier_counts["M2"], miss_tier_counts["M3"],
        miss_tier_counts["M4"], miss_tier_counts["M5"],
    )
    attention = [r for r in tier_rows if r["val_tier"] in ("T4", "T5")]

    if _REPORT_FMT == "md":
        print("| Variable | Type | T_N | B_N | Val Delta | T M% | B M% | Val | Miss |")
        print("|:---|:---:|---:|---:|---:|---:|---:|:---:|:---:|")
        current_ds = None
        for row in tier_rows:
            if row["dataset"] != current_ds:
                current_ds = row["dataset"]
                print(f"| ***{current_ds}*** | | | | | | | | |")
            print(
                f"| {_md_cell(row['label'])} | {_md_cell(row['type'])} | {row['t_n']:,} | {row['b_n']:,}"
                f" | {_md_cell(row['val_delta_str'])} | {row['t_pm']:.1f}% | {row['b_pm']:.1f}%"
                f" | **{row['val_tier']}** | {row['miss_tier']} |"
            )
        print()
        print(f"**Value tiers:** T1={t1} T2={t2} T3={t3} T4={t4} T5={t5}  "
              f"| **Miss tiers:** M1={m1} M2={m2} M3={m3} M4={m4} M5={m5}")
        print()
        print("> T1=near-exact | T2=high similarity | T3=moderate diff | T4=notable diff | T5=substantial diff  ")
        print("> M1=<1pp | M2=<3pp | M3=<8pp | M4=<20pp | M5>=20pp")
        if attention:
            print()
            print("**Attention items (T4/T5):**")
            for row in attention:
                print(f"- **[{row['val_tier']}]** {_md_cell(row['label'])} (`{_md_cell(row['var'])}`) -- {_md_cell(row['val_delta_str'])}  miss: {row['miss_tier']}")
    else:
        print(f"  {'Variable':<38} {'Type':<5} {'T_N':>8} {'B_N':>8} {'Val_Delta':>12}  {'T_M%':>5} {'B_M%':>5}  {'Val':>3}  {'Miss':>4}")
        print("  " + "-" * 100)
        current_ds = None
        for row in tier_rows:
            if row["dataset"] != current_ds:
                current_ds = row["dataset"]
                print(f"\n  -- {current_ds} --")
            print(
                f"  {row['label']:<38} {row['type']:<5} {row['t_n']:>8,} {row['b_n']:>8,}"
                f" {row['val_delta_str']:>12}  {row['t_pm']:>4.1f}%  {row['b_pm']:>4.1f}%"
                f"  {row['val_tier']:>3}  {row['miss_tier']:>4}"
            )
        print()
        print(f"  Value tier summary:  T1={t1}  T2={t2}  T3={t3}  T4={t4}  T5={t5}")
        print(f"  Miss. tier summary:  M1={m1}  M2={m2}  M3={m3}  M4={m4}  M5={m5}")
        print("  T1=near-exact  T2=high similarity  T3=moderate diff  T4=notable diff  T5=substantial diff")
        print("  M1=<1pp  M2=<3pp  M3=<8pp  M4=<20pp  M5>=20pp")
        if attention:
            print()
            print("  Attention items (T4/T5 value tier):")
            for row in attention:
                print(f"    [{row['val_tier']}] {row['label']} ({row['var']}) -- {row['val_delta_str']}  miss: {row['miss_tier']}")

    # ── DQ Flags ──
    section("DATA QUALITY FLAGS")
    for label, data in [("TOPMed", topmed), ("BDC", bdc)]:
        flags = data.get("dq_flags", [])
        if _REPORT_FMT == "md":
            print(f"\n**{label}:**")
            if flags:
                for f in flags:
                    print(f"- {f}")
            else:
                print("*No flags.*")
        else:
            print(f"\n  {label}:")
            if flags:
                for f in flags:
                    print(f"    • {f}")
            else:
                print("    No flags.")

    # ── Summary ──
    section("SUMMARY")
    if _REPORT_FMT == "md":
        print(f"- **Cohort:** {t_cohort}")
        print(f"- **Variables compared:** {n_matched}")
        print(f"- **TOPMed N:** {n_t:,} | **BDC N:** {n_b:,}")
        print("\n---\n\n*End of report*")
    else:
        print(f"  Cohort: {t_cohort}")
        print(f"  Variables compared: {n_matched}")
        print(f"  TOPMed N: {n_t:,}  |  BDC N: {n_b:,}")
        print()
        print("=" * 76)
        print("  END OF COMPARISON REPORT")
        print("=" * 76)

    # ── Build structured summary for cross-cohort rollup ────────────────────
    per_var_summary: dict[str, dict] = {}
    for var in matched_vars:
        t_stat = t_vars.get(var, {})
        b_stat = b_vars.get(var, {})
        vtype = (t_stat or b_stat).get("type", "categorical")
        label = (t_stat or b_stat).get("bdc_label", var)
        entry: dict = {"label": label, "type": vtype}
        if vtype == "continuous":
            t_mean = t_stat.get("mean")
            b_mean = b_stat.get("mean")
            entry["topmed_n"] = t_stat.get("n_valid", 0)
            entry["bdc_n"] = b_stat.get("n_valid", 0)
            entry["topmed_mean"] = t_mean
            entry["bdc_mean"] = b_mean
            if t_mean is not None and b_mean is not None:
                entry["mean_delta"] = b_mean - t_mean
                entry["mean_pct_delta"] = (
                    ((b_mean - t_mean) / t_mean * 100) if t_mean != 0 else None
                )
        else:
            entry["topmed_n"] = t_stat.get("n_total", 0)
            entry["bdc_n"] = b_stat.get("n_total", 0)
        per_var_summary[var] = entry

    return {
        "cohort": t_cohort,
        "full_name": topmed.get("cohort", {}).get("full_name", ""),
        "topmed_n": n_t,
        "bdc_n": n_b,
        "participant_delta": n_b - n_t if n_t and n_b else None,
        "participant_delta_pct": ((n_b - n_t) / n_t * 100) if n_t else None,
        "n_topmed_vars": len(t_vars),
        "n_bdc_vars": len(b_vars),
        "n_matched": n_matched,
        "n_topmed_only": n_topmed_only,
        "n_bdc_only": n_bdc_only,
        "n_dq_flags_topmed": len(topmed.get("dq_flags", [])),
        "n_dq_flags_bdc": len(bdc.get("dq_flags", [])),
        "variables": per_var_summary,
    }


# ─────────────────────────────────────────────────────────────────────────────
# BATCH AUTO-DISCOVERY
# ─────────────────────────────────────────────────────────────────────────────

# Cohort name normalization: BDC extract uses "HCHS" but TOPMed file uses
# "hchs_sol".  This map handles known mismatches.
_COHORT_NORMALIZE: dict[str, str] = {
    "HCHS": "HCHS_SOL",
    "HCHS_SOL": "HCHS_SOL",
}


def _find_latest_bdc_json(bdc_dir: Path, cohort_key: str) -> Path | None:
    """Find the newest bdc_{cohort}_summary_*.json in bdc_dir."""
    pattern = f"bdc_{cohort_key.lower()}_summary_*.json"
    candidates = sorted(bdc_dir.glob(pattern))
    return candidates[-1] if candidates else None


def _find_topmed_json(topmed_dir: Path, cohort_key: str) -> Path | None:
    """Find topmed_{cohort}_summary.json in topmed_dir."""
    # Try exact match first
    p = topmed_dir / f"topmed_{cohort_key.lower()}_summary.json"
    if p.is_file():
        return p
    # Try normalized name (e.g., HCHS → hchs_sol)
    norm = _COHORT_NORMALIZE.get(cohort_key.upper(), cohort_key).lower()
    p2 = topmed_dir / f"topmed_{norm}_summary.json"
    return p2 if p2.is_file() else None


def discover_json_pairs(
    bdc_dir: Path,
    topmed_dir: Path,
) -> list[tuple[str, Path, Path]]:
    """Auto-discover matching (cohort, bdc_json, topmed_json) triples.

    Scans bdc_dir for bdc_*_summary_*.json files, extracts cohort names,
    finds the latest BDC JSON per cohort, and matches to the TOPMed JSON.
    Returns only cohorts with both files present.
    """
    # Discover all BDC cohort keys from filenames
    bdc_pat = re.compile(r"^bdc_([a-z0-9_]+?)_summary_\d+_\d+\.json$", re.IGNORECASE)
    cohort_keys: set[str] = set()
    for f in bdc_dir.iterdir():
        m = bdc_pat.match(f.name)
        if m:
            cohort_keys.add(m.group(1).upper())

    pairs: list[tuple[str, Path, Path]] = []
    for key in sorted(cohort_keys):
        bdc_json = _find_latest_bdc_json(bdc_dir, key)
        topmed_json = _find_topmed_json(topmed_dir, key)
        if bdc_json and topmed_json:
            display_name = _COHORT_NORMALIZE.get(key, key)
            pairs.append((display_name, bdc_json, topmed_json))
        else:
            missing = []
            if not bdc_json:
                missing.append("BDC")
            if not topmed_json:
                missing.append("TOPMed")
            print(f"  [SKIP] {key}: missing {' + '.join(missing)} JSON", file=sys.stderr)

    return pairs


# ─────────────────────────────────────────────────────────────────────────────
# SINGLE-COHORT COMPARE (unchanged logic, extracted for reuse)
# ─────────────────────────────────────────────────────────────────────────────

def compare_one_cohort(
    topmed_path: str | Path,
    bdc_path: str | Path,
    output_path: str | Path | None = None,
    quiet: bool = False,
) -> dict:
    """Run comparison for a single cohort pair. Returns structured summary.

    Always produces both a .txt and .md report when output_path is given.
    The output_path extension is ignored — both files are derived from the stem.
    Console output (unless quiet=True) shows the plain-text report.
    """
    global _REPORT_FMT

    topmed = load_json(str(topmed_path), "TOPMed")
    bdc = load_json(str(bdc_path), "BDC")

    def _capture(fmt: str) -> tuple[str, dict]:
        global _REPORT_FMT
        _REPORT_FMT = fmt
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            res = run_comparison(topmed, bdc)
        finally:
            sys.stdout = old
            _REPORT_FMT = "txt"
        return buf.getvalue(), res

    txt_text, result = _capture("txt")
    md_text = ""
    if output_path:
        md_text, _ = _capture("md")

    if not quiet:
        try:
            print(txt_text)
        except UnicodeEncodeError:
            # Windows cp1252 can't render some Unicode chars — skip echo
            pass

    if output_path:
        base = Path(output_path).with_suffix("")
        txt_path = base.with_suffix(".txt")
        md_path = base.with_suffix(".md")
        txt_path.parent.mkdir(parents=True, exist_ok=True)
        txt_path.write_text(txt_text, encoding="utf-8")
        md_path.write_text(md_text, encoding="utf-8")
        print(f"  Reports saved: {txt_path.name}  +  {md_path.name}", file=sys.stderr)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# CROSS-COHORT SUMMARY REPORT
# ─────────────────────────────────────────────────────────────────────────────

def generate_cross_cohort_summary(
    cohort_results: dict[str, dict],
    output_path: Path | None = None,
) -> None:
    """Generate cross-cohort summary reports from per-cohort comparison results."""

    buf = io.StringIO()
    _stdout = sys.stdout
    sys.stdout = buf

    try:
        _write_cross_cohort_summary(cohort_results)
    finally:
        sys.stdout = _stdout

    report_text = buf.getvalue()
    print(report_text)

    if output_path:
        base = output_path.with_suffix("")
        txt_path = base.with_suffix(".txt")
        md_path = base.with_suffix(".md")
        txt_path.parent.mkdir(parents=True, exist_ok=True)
        txt_path.write_text(report_text, encoding="utf-8")
        md_path.write_text(
            "# Cross-Cohort Harmonization Comparison Summary\n\n"
            "```text\n"
            f"{report_text}"
            "```\n",
            encoding="utf-8",
        )
        print(f"\n  Cross-cohort summaries saved: {txt_path.name}  +  {md_path.name}", file=sys.stderr)


def _write_cross_cohort_summary(cohort_results: dict[str, dict]) -> None:
    """Internal: write the cross-cohort summary text."""
    n_cohorts = len(cohort_results)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    print("=" * 80)
    print("  CROSS-COHORT HARMONIZATION COMPARISON SUMMARY")
    print(f"  TOPMed DCC vs. BDC DMC — {n_cohorts} Cohorts")
    print(f"  Generated: {ts}")
    print("=" * 80)

    # ── 1. Participant Count Overview ────────────────────────────────────────
    print("\n" + "─" * 80)
    print("  1. PARTICIPANT COUNTS")
    print("─" * 80)
    print(f"\n  {'Cohort':<15} {'TOPMed N':>12} {'BDC N':>12} {'Delta':>10} {'% Delta':>10}")
    print("  " + "-" * 60)

    total_topmed = 0
    total_bdc = 0
    for cohort in sorted(cohort_results):
        r = cohort_results[cohort]
        tn = r.get("topmed_n", 0)
        bn = r.get("bdc_n", 0)
        total_topmed += tn
        total_bdc += bn
        delta = r.get("participant_delta", 0) or 0
        pct = r.get("participant_delta_pct")
        pct_str = f"{pct:+.1f}%" if pct is not None else "—"
        print(f"  {cohort:<15} {tn:>12,} {bn:>12,} {delta:>+10,} {pct_str:>10}")

    total_delta = total_bdc - total_topmed
    total_pct = (total_delta / total_topmed * 100) if total_topmed else 0
    print("  " + "-" * 60)
    print(f"  {'TOTAL':<15} {total_topmed:>12,} {total_bdc:>12,} {total_delta:>+10,} {total_pct:>+.1f}%")

    # ── 2. Variable Coverage Matrix ─────────────────────────────────────────
    print("\n" + "─" * 80)
    print("  2. VARIABLE COVERAGE BY COHORT")
    print("─" * 80)
    print(f"\n  {'Cohort':<15} {'TOPMed':>8} {'BDC':>8} {'Matched':>9} {'T-only':>8} {'B-only':>8} {'Match%':>8}")
    print("  " + "-" * 65)

    for cohort in sorted(cohort_results):
        r = cohort_results[cohort]
        nt = r.get("n_topmed_vars", 0)
        nb = r.get("n_bdc_vars", 0)
        nm = r.get("n_matched", 0)
        nto = r.get("n_topmed_only", 0)
        nbo = r.get("n_bdc_only", 0)
        pct = (nm / nt * 100) if nt else 0
        print(f"  {cohort:<15} {nt:>8} {nb:>8} {nm:>9} {nto:>8} {nbo:>8} {pct:>7.0f}%")

    # ── 3. Per-Variable Cross-Cohort Comparison ─────────────────────────────
    # Collect all variable keys across cohorts
    all_vars: dict[str, dict] = {}
    for cohort, r in sorted(cohort_results.items()):
        for var, vstat in r.get("variables", {}).items():
            if var not in all_vars:
                all_vars[var] = {"label": vstat.get("label", var), "type": vstat.get("type", "?"), "cohorts": {}}
            all_vars[var]["cohorts"][cohort] = vstat

    # 3a. Continuous variables
    continuous_vars = {k: v for k, v in all_vars.items() if v["type"] == "continuous"}
    if continuous_vars:
        print("\n" + "─" * 80)
        print("  3. CONTINUOUS VARIABLE MEANS: BDC vs TOPMed (per cohort)")
        print("─" * 80)

        for var in sorted(continuous_vars, key=lambda v: continuous_vars[v]["label"]):
            vi = continuous_vars[var]
            print(f"\n  {vi['label']} ({var})")
            print(f"    {'Cohort':<15} {'TOPMed Mean':>14} {'BDC Mean':>14} {'Delta':>12} {'% Delta':>10}")
            print("    " + "-" * 68)
            for cohort in sorted(vi["cohorts"]):
                cs = vi["cohorts"][cohort]
                tm = cs.get("topmed_mean")
                bm = cs.get("bdc_mean")
                md = cs.get("mean_delta")
                mp = cs.get("mean_pct_delta")
                tm_s = f"{tm:.4f}" if tm is not None else "—"
                bm_s = f"{bm:.4f}" if bm is not None else "—"
                md_s = f"{md:+.4f}" if md is not None else "—"
                mp_s = f"{mp:+.1f}%" if mp is not None else "—"
                print(f"    {cohort:<15} {tm_s:>14} {bm_s:>14} {md_s:>12} {mp_s:>10}")

    # 3b. Categorical variables
    categorical_vars = {k: v for k, v in all_vars.items() if v["type"] == "categorical"}
    if categorical_vars:
        print("\n" + "─" * 80)
        print("  4. CATEGORICAL VARIABLE N-COUNTS: BDC vs TOPMed (per cohort)")
        print("─" * 80)

        for var in sorted(categorical_vars, key=lambda v: categorical_vars[v]["label"]):
            vi = categorical_vars[var]
            print(f"\n  {vi['label']} ({var})")
            print(f"    {'Cohort':<15} {'TOPMed N':>12} {'BDC N':>12} {'Delta':>10}")
            print("    " + "-" * 52)
            for cohort in sorted(vi["cohorts"]):
                cs = vi["cohorts"][cohort]
                tn = cs.get("topmed_n", 0)
                bn = cs.get("bdc_n", 0)
                delta = bn - tn
                print(f"    {cohort:<15} {tn:>12,} {bn:>12,} {delta:>+10,}")

    # ── 4. DQ Flag Summary ──────────────────────────────────────────────────
    print("\n" + "─" * 80)
    print("  5. DATA QUALITY FLAGS SUMMARY")
    print("─" * 80)
    print(f"\n  {'Cohort':<15} {'TOPMed DQ':>12} {'BDC DQ':>12}")
    print("  " + "-" * 40)
    for cohort in sorted(cohort_results):
        r = cohort_results[cohort]
        print(f"  {cohort:<15} {r.get('n_dq_flags_topmed', 0):>12} {r.get('n_dq_flags_bdc', 0):>12}")

    # ── 5. Cohorts with large discrepancies ─────────────────────────────────
    print("\n" + "─" * 80)
    print("  6. ATTENTION ITEMS (> 5% participant delta or large mean shifts)")
    print("─" * 80)
    flagged = False
    for cohort in sorted(cohort_results):
        r = cohort_results[cohort]
        issues: list[str] = []
        pct = r.get("participant_delta_pct")
        if pct is not None and abs(pct) > 5:
            issues.append(f"Participant count delta {pct:+.1f}%")
        for var, vs in r.get("variables", {}).items():
            mp = vs.get("mean_pct_delta")
            if mp is not None and abs(mp) > 10:
                issues.append(f"{vs.get('label', var)}: mean delta {mp:+.1f}%")
        if issues:
            flagged = True
            print(f"\n  {cohort}:")
            for issue in issues:
                print(f"    [!] {issue}")
    if not flagged:
        print("\n  None — all cohorts within tolerance.")

    print("\n" + "=" * 80)
    print("  END OF CROSS-COHORT SUMMARY")
    print("=" * 80)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare BDC vs TOPMed DCC aggregate summary statistics.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Single-cohort mode
    parser.add_argument(
        "--topmed-json",
        default=None,
        metavar="FILE",
        help="TOPMed DCC aggregate JSON (from extract_topmed_summaries.py). Single-cohort mode.",
    )
    parser.add_argument(
        "--bdc-json",
        default=None,
        metavar="FILE",
        help="BDC DMC aggregate JSON (from extract_harmonized_summaries.py). Single-cohort mode.",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="FILE",
        help="Write report to file (also prints to stdout). Single-cohort mode.",
    )

    # Batch mode
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Batch mode: auto-discover and compare all cohorts with matching BDC + TOPMed JSONs.",
    )
    parser.add_argument(
        "--bdc-dir",
        default=None,
        metavar="DIR",
        help="Directory containing BDC summary JSONs. Default: ./BDC_Output/",
    )
    parser.add_argument(
        "--topmed-dir",
        default=None,
        metavar="DIR",
        help="Directory containing TOPMed summary JSONs. Default: ./TOPMed_Output/",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        metavar="DIR",
        help="Directory for per-cohort and cross-cohort reports. Default: current directory.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.batch:
        # ── Batch mode ──────────────────────────────────────────────────────
        bdc_dir = Path(args.bdc_dir) if args.bdc_dir else Path("BDC_Output")
        topmed_dir = Path(args.topmed_dir) if args.topmed_dir else Path("TOPMed_Output")
        output_dir = Path(args.output_dir) if args.output_dir else Path(".")

        if not bdc_dir.is_dir():
            print(f"ERROR: BDC directory not found: {bdc_dir.resolve()}", file=sys.stderr)
            sys.exit(1)
        if not topmed_dir.is_dir():
            print(f"ERROR: TOPMed directory not found: {topmed_dir.resolve()}", file=sys.stderr)
            sys.exit(1)

        pairs = discover_json_pairs(bdc_dir, topmed_dir)
        if not pairs:
            print("ERROR: No matching BDC + TOPMed JSON pairs found.", file=sys.stderr)
            sys.exit(1)

        print(f"\n  Found {len(pairs)} cohort pair(s) to compare:")
        for cohort, bdc_path, topmed_path in pairs:
            print(f"    {cohort}: {bdc_path.name}  <->  {topmed_path.name}")
        print()

        run_ts = datetime.now().strftime("%Y%m%d")
        output_dir.mkdir(parents=True, exist_ok=True)

        cohort_results: dict[str, dict] = {}
        for cohort, bdc_path, topmed_path in pairs:
            report_path = output_dir / f"{cohort}_comparison_{run_ts}.txt"
            try:
                result = compare_one_cohort(topmed_path, bdc_path, report_path, quiet=True)
                cohort_results[cohort] = result
            except Exception as exc:
                print(f"\n  ERROR comparing {cohort}: {exc}", file=sys.stderr)

        # Generate cross-cohort summary
        if cohort_results:
            summary_path = output_dir / f"Cross_Cohort_Summary_{run_ts}.txt"
            generate_cross_cohort_summary(cohort_results, summary_path)

            # Also write structured JSON for downstream tooling
            json_path = output_dir / f"cross_cohort_summary_{run_ts}.json"
            json_data = {
                "metadata": {
                    "generated": datetime.now(timezone.utc).isoformat(),
                    "script": "compare_bdc_topmed.py --batch",
                    "n_cohorts": len(cohort_results),
                },
                "cohorts": cohort_results,
            }
            json_path.write_text(
                json.dumps(json_data, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            print(f"\n  Structured JSON: {json_path}", file=sys.stderr)

        # Final batch summary
        print(f"\n  Batch complete: {len(cohort_results)}/{len(pairs)} cohorts compared.")
        if len(cohort_results) < len(pairs):
            failed = set(c for c, _, _ in pairs) - set(cohort_results)
            print(f"  Failed: {', '.join(sorted(failed))}", file=sys.stderr)
            sys.exit(1)

    elif args.topmed_json and args.bdc_json:
        # ── Single-cohort mode (original behavior) ──────────────────────────
        compare_one_cohort(args.topmed_json, args.bdc_json, args.output)

    else:
        print("ERROR: Provide either --batch or both --topmed-json and --bdc-json.",
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
