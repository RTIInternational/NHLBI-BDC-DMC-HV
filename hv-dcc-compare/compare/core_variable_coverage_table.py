"""
core_variable_coverage_table.py — Cross-cohort 19 Core Variable coverage matrix
=================================================================================
Generates a presence/absence table for the 19 Core Variables across all 9 cohorts,
showing both TOPMed DCC reference coverage and BDC YAML mapping coverage.

Usage:
    python compare/core_variable_coverage_table.py \
        --hv-repo /path/to/NHLBI-BDC-DMC-HV \
        --topmed-dir ./runs/topmed/

Output:
    Prints the coverage matrix to stdout.

The 19 Core Variables are the validated comparison scope defined in:
    QC/reports/BDC-vs-TOPMed-Comparison-Scope-2026-04-01.md

Legend:
    T = TOPMed DCC has this variable for the cohort (from per-cohort summary JSON)
    B = BDC has an active YAML mapping for this variable (from HV repo ingest dirs)
    Y Y = both present
    Y - = DCC only (BDC gap)
    - Y = BDC only (DCC not harmonized)
    - - = neither
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# 19 CORE VARIABLES — validated comparison scope (2026-04-01)
# Organized by clinical group.
# ---------------------------------------------------------------------------
CORE_VARS: list[tuple[str, list[str]]] = [
    ("Demographics", [
        "annotated_sex_1",
        "race_us_1",
        "hispanic_or_latino_1",
    ]),
    ("Anthropometrics", [
        "height_baseline_1",
        "weight_baseline_1",
        "bmi_baseline_1",
    ]),
    ("Blood Pressure", [
        "bp_systolic_1",
        "bp_diastolic_1",
        "antihypertensive_meds_1",
    ]),
    ("Smoking", [
        "current_smoker_baseline_1",
        "ever_smoker_baseline_1",
    ]),
    ("Lipids", [
        "total_cholesterol_1",
        "triglycerides_1",
    ]),
    ("CBC", [
        "platelet_ncnc_bld_1",
        "mch_entmass_rbc_1",
    ]),
    ("CVD History", [
        "mi_prior_1",
        "cabg_prior_1",
        "pad_prior_1",
        "angina_prior_1",
    ]),
]

# ---------------------------------------------------------------------------
# BDC YAML stem crosswalk — maps TOPMed variable name -> list of YAML file stems
# that cover it in the BDC HV repo. Any match = covered.
# ---------------------------------------------------------------------------
BDC_STEMS: dict[str, list[str]] = {
    "annotated_sex_1":             ["demography"],
    "race_us_1":                   ["demography"],
    "hispanic_or_latino_1":        ["demography"],
    "height_baseline_1":           ["bdy_hgt"],
    "weight_baseline_1":           ["bdy_wgt"],
    "bmi_baseline_1":              ["bmi"],
    "bp_systolic_1":               ["bp_systolic", "blood_pressure"],
    "bp_diastolic_1":              ["bp_diastolic", "blood_pressure"],
    "antihypertensive_meds_1":     ["hypert_trt", "antihypertensive_meds"],
    "current_smoker_baseline_1":   ["cig_smok"],
    "ever_smoker_baseline_1":      ["cig_smok"],
    "total_cholesterol_1":         ["tot_chol_bld"],
    "triglycerides_1":             ["triglyc_bld"],
    "platelet_ncnc_bld_1":         ["platelet_ct"],
    "mch_entmass_rbc_1":           ["mch"],
    "mi_prior_1":                  ["hist_my_inf", "hist_mi"],
    "cabg_prior_1":                ["hist_cor_bypg", "hist_coronary_bypass"],
    "pad_prior_1":                 ["pad"],
    "angina_prior_1":              ["angina"],
}

# ---------------------------------------------------------------------------
# Cohort configuration
# ---------------------------------------------------------------------------
COHORTS: list[str] = [
    "ARIC", "CARDIA", "CHS", "COPDGene", "FHS", "HCHS_SOL", "JHS", "MESA", "WHI"
]

COHORT_DISPLAY: dict[str, str] = {
    "ARIC":     "ARIC",
    "CARDIA":   "CARDIA",
    "CHS":      "CHS",
    "COPDGene": "COPDGene",
    "FHS":      "FHS",
    "HCHS_SOL": "HCHS-SOL",
    "JHS":      "JHS",
    "MESA":     "MESA",
    "WHI":      "WHI",
}

# Cohort name -> ingest folder name suffix (e.g. HCHS_SOL -> "HCHS-ingest")
COHORT_INGEST_DIR: dict[str, str] = {
    "ARIC":     "ARIC-ingest",
    "CARDIA":   "CARDIA-ingest",
    "CHS":      "CHS-ingest",
    "COPDGene": "COPDGene-ingest",
    "FHS":      "FHS-ingest",
    "HCHS_SOL": "HCHS-ingest",
    "JHS":      "JHS-ingest",
    "MESA":     "MESA-ingest",
    "WHI":      "WHI-ingest",
}

# TOPMed summary JSON file name pattern per cohort
COHORT_TOPMED_JSON: dict[str, str] = {
    "ARIC":     "topmed_aric_summary.json",
    "CARDIA":   "topmed_cardia_summary.json",
    "CHS":      "topmed_chs_summary.json",
    "COPDGene": "topmed_copdgene_summary.json",
    "FHS":      "topmed_fhs_summary.json",
    "HCHS_SOL": "topmed_hchs_sol_summary.json",
    "JHS":      "topmed_jhs_summary.json",
    "MESA":     "topmed_mesa_summary.json",
    "WHI":      "topmed_whi_summary.json",
}


def build_cohort_paths(hv_repo: Path, topmed_dir: Path) -> tuple[dict, dict]:
    """Build per-cohort HV ingest paths and TOPMed JSON paths from root dirs."""
    hv_paths = {
        cohort: hv_repo / "priority_variables_transform" / ingest_dir
        for cohort, ingest_dir in COHORT_INGEST_DIR.items()
    }
    topmed_paths = {
        cohort: topmed_dir / json_name
        for cohort, json_name in COHORT_TOPMED_JSON.items()
    }
    return hv_paths, topmed_paths


def load_topmed_variables(topmed_paths: dict[str, Path]) -> dict[str, set[str]]:
    """Load set of available TOPMed variables per cohort from summary JSONs."""
    result: dict[str, set[str]] = {}
    for cohort, path in topmed_paths.items():
        if not path.exists():
            print(f"  WARNING: TOPMed JSON not found for {cohort}: {path}")
            result[cohort] = set()
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        result[cohort] = set(data["variables"].keys())
    return result


def load_bdc_yaml_stems(hv_paths: dict[str, Path]) -> dict[str, set[str]]:
    """Load set of YAML file stems present in each cohort's HV ingest directory."""
    result: dict[str, set[str]] = {}
    for cohort, p in hv_paths.items():
        if p.exists():
            result[cohort] = {f.stem for f in p.glob("*.yaml")}
        else:
            print(f"  WARNING: HV ingest path not found for {cohort}: {p}")
            result[cohort] = set()
    return result


def bdc_covered(var: str, cohort_stems: set[str]) -> bool:
    """Return True if any matching YAML stem exists for this variable."""
    return any(stem in cohort_stems for stem in BDC_STEMS.get(var, []))


def print_table(
    topmed: dict[str, set[str]],
    bdc: dict[str, set[str]],
) -> None:
    all_vars: list[str] = []

    col_w = 9
    line_w = 38 + 3 + (col_w + 3) * len(COHORTS)

    print()
    print("19 Core Variable Coverage Matrix")
    print("=" * line_w)
    print(
        "Variable".ljust(38)
        + " | "
        + " | ".join(COHORT_DISPLAY[c].center(col_w) for c in COHORTS)
    )
    print(
        " " * 38
        + " | "
        + " | ".join(("T  B").center(col_w) for _ in COHORTS)
    )
    print("-" * line_w)

    for group, vars_ in CORE_VARS:
        print(f"=== {group} ===")
        for v in vars_:
            all_vars.append(v)
            short = (
                v.replace("_baseline_1", "")
                 .replace("_ncnc_bld", "")
                 .replace("_1", "")
            )[:38]
            cells = []
            for c in COHORTS:
                t = "Y" if v in topmed[c] else "-"
                b = "Y" if bdc_covered(v, bdc[c]) else "-"
                cells.append(f"{t}  {b}")
            print(short.ljust(38) + " | " + " | ".join(cell.center(col_w) for cell in cells))

    print()
    print("T = TOPMed DCC has this variable for the cohort")
    print("B = BDC has a YAML mapping for this variable for the cohort")
    print()

    # Summary row
    print("=" * line_w)
    print("Cohort summary (of 19 core vars):")
    print(
        "Cohort".ljust(12)
        + "  TOPMed  BDC  Both-Missing"
    )
    for c in COHORTS:
        t_count = sum(1 for v in all_vars if v in topmed[c])
        b_count = sum(1 for v in all_vars if bdc_covered(v, bdc[c]))
        both_miss = sum(
            1 for v in all_vars
            if v not in topmed[c] and not bdc_covered(v, bdc[c])
        )
        print(
            COHORT_DISPLAY[c].ljust(12)
            + "  "
            + str(t_count).rjust(5)
            + "    "
            + str(b_count).rjust(3)
            + "   "
            + str(both_miss).rjust(5)
        )
    print()


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Cross-cohort 19 Core Variable coverage matrix."
    )
    parser.add_argument(
        "--hv-repo",
        required=True,
        help="Path to the root of the HV repo checkout "
             "(contains priority_variables_transform/).",
    )
    parser.add_argument(
        "--topmed-dir",
        default="topmed",
        help="Directory containing per-cohort topmed_*_summary.json files "
             "(default: ./topmed).",
    )
    args = parser.parse_args()

    hv_paths, topmed_paths = build_cohort_paths(
        Path(args.hv_repo), Path(args.topmed_dir)
    )

    print("Loading TOPMed DCC variable presence...")
    topmed = load_topmed_variables(topmed_paths)
    print("Loading BDC YAML presence...")
    bdc = load_bdc_yaml_stems(hv_paths)
    print_table(topmed, bdc)


if __name__ == "__main__":
    main()
