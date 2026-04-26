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


# ─────────────────────────────────────────────────────────────────────────────
# REPORT FORMATTING
# ─────────────────────────────────────────────────────────────────────────────

def section(title: str, width: int = 76) -> None:
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def subsection(title: str) -> None:
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

    # Missing row
    tM = (t_stats or {}).get("n_missing", 0)
    tMP = (t_stats or {}).get("pct_missing", 0.0)
    bM = (b_stats or {}).get("n_missing", 0)
    bMP = (b_stats or {}).get("pct_missing", 0.0)
    delta_m = bM - tM
    delta_m_str = f"{delta_m:+,}" if delta_m != 0 else "0"
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

    print(f"\n    {bdc_label} ({var_name})")
    unit = t.get("unit") or b.get("unit") or ""
    if unit:
        print(f"    Unit: {unit}")
    if b_visit:
        print(f"    BDC visit: {b_visit}")

    print(f"    {'Statistic':<25} {'TOPMed':>15} {'BDC':>15} {'Delta':>12}")
    print("    " + "-" * 70)

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
    print(f"  {'Variable':<40} {'TOPMed':^8} {'BDC':^8} {'Match':^8}")
    print("  " + "-" * 65)
    n_matched = 0
    n_topmed_only = 0
    n_bdc_only = 0
    for var in sorted(all_vars):
        in_t = "✓" if var in t_vars else "—"
        in_b = "✓" if var in b_vars else "—"
        match = "✓" if var in t_vars and var in b_vars else "—"
        label = (t_vars.get(var) or b_vars.get(var, {})).get("bdc_label", var)
        print(f"  {label:<40} {in_t:^8} {in_b:^8} {match:^8}")
        if var in t_vars and var in b_vars:
            n_matched += 1
        elif var in t_vars:
            n_topmed_only += 1
        else:
            n_bdc_only += 1

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

    # ── DQ Flags ──
    section("DATA QUALITY FLAGS")
    for label, data in [("TOPMed", topmed), ("BDC", bdc)]:
        flags = data.get("dq_flags", [])
        print(f"\n  {label}:")
        if flags:
            for f in flags:
                print(f"    • {f}")
        else:
            print("    No flags.")

    # ── Summary ──
    section("SUMMARY")
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

    If quiet=True, the full report is written to file only (not echoed to
    console).  Useful in batch mode to avoid flooding the terminal.
    """
    print("=" * 60)
    print("  TOPMed DCC vs. BDC DMC Comparison Report")
    print("=" * 60)
    print()

    topmed = load_json(str(topmed_path), "TOPMed")
    bdc = load_json(str(bdc_path), "BDC")

    if output_path:
        buf = io.StringIO()
        _stdout = sys.stdout
        sys.stdout = buf

    try:
        result = run_comparison(topmed, bdc)
    finally:
        if output_path:
            sys.stdout = _stdout
            report_text = buf.getvalue()
            if not quiet:
                try:
                    print(report_text)
                except UnicodeEncodeError:
                    # Windows cp1252 can't render some Unicode chars — skip echo
                    pass
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text(report_text, encoding="utf-8")
            print(f"\n  Report saved to: {output_path}", file=sys.stderr)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# CROSS-COHORT SUMMARY REPORT
# ─────────────────────────────────────────────────────────────────────────────

def generate_cross_cohort_summary(
    cohort_results: dict[str, dict],
    output_path: Path | None = None,
) -> None:
    """Generate a cross-cohort summary report from per-cohort comparison results."""

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
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report_text, encoding="utf-8")
        print(f"\n  Cross-cohort summary saved to: {output_path}", file=sys.stderr)


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
