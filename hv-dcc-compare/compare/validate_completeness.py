"""
validate_completeness.py — Definitive validation of participant count gaps
======================================================================================
Runs on per-participant data from BOTH TOPMed DCC and BDC extracts and produces an
anonymized **phenotype completeness profile** for each system:

  - How many participants have 0 non-null phenotype variables?
  - How many have 1, 2, ..., N variables?
  - What is the distribution of per-participant completeness?

This validates the hypothesis that TOPMed's 12,895 count includes ~375-400
enrollment-only subjects with no measured phenotype data, while BDC's 11,831
count reflects only participants with actual exam records.

OUTPUT: JSON + console report (aggregate only — NO participant IDs or raw
participant-level values written).

USAGE:
    # TOPMed side (from enclave with EAV files):
    python validate_participant_completeness.py topmed \\
        --demographics-file /path/to/demographic_eav.txt \\
        --baseline-covariates-file /path/to/baseline_covariates_eav.txt \\
        --inflammation-file /path/to/inflammation_eav.txt \\
        --sleep-file /path/to/sleep_eav.txt \\
        --cohort HCHS_SOL \\
        --output-dir ./validation_output/

    # BDC side (from enclave with dm-bip output):
    python validate_participant_completeness.py bdc \\
        --cohort HCHS \\
        --base-dir /path/to/bdc/output/ \\
        --output-dir ./validation_output/

    # Compare two previously-generated validation JSONs:
    python validate_participant_completeness.py compare \\
        --topmed-json ./validation_output/topmed_HCHS_SOL_completeness.json \\
        --bdc-json ./validation_output/bdc_HCHS_completeness.json

WHAT THIS PROVES:
    If TOPMed shows ~375-400 participants with 0-1 non-null phenotype variables
    (only race/ethnicity populated, which are study-level 100%-complete codes),
    this confirms they are enrollment-only subjects inflating the participant count.
    BDC should show near-zero such participants, confirming it counts only
    participants with actual exam data.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add the hv-dcc-compare root to path so config.py is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import COHORTS, DATASETS, get_variable_spec

# Variables that are "trivially complete" (study-level coding, not measured):
# These are 100% complete for all subjects regardless of exam participation.
TRIVIALLY_COMPLETE_VARS = {"race_us_1", "hispanic_or_latino_1"}

# Core phenotype variables that require actual exam participation:
EXAM_VARIABLES = [
    "annotated_sex_1",      # demographics — usually from consent form
    "height_baseline_1",    # anthropometrics — requires exam
    "weight_baseline_1",    # anthropometrics — requires exam
    "bmi_baseline_1",       # derived from height + weight
    "bp_systolic_1",        # vitals — requires exam
    "bp_diastolic_1",       # vitals — requires exam
    "hdl_1",                # lipids — requires blood draw
    "total_cholesterol_1",  # lipids — requires blood draw
    "triglycerides_1",      # lipids — requires blood draw
    "crp_1",                # inflammation — requires blood draw
    "sleep_duration_1",     # questionnaire
]


# ─────────────────────────────────────────────────────────────────────────────
# TOPMed EAV Loading
# ─────────────────────────────────────────────────────────────────────────────

def load_topmed_wide(file_args: dict, cohort: str, verbose: bool = False) -> pd.DataFrame:
    """
    Load all TOPMed EAV files for a cohort, merge into wide format.
    Returns DataFrame with SUBJECT_ID index and one column per variable.
    """
    merged = None
    for ds_key, ds_info in DATASETS.items():
        arg_name = ds_key + "_file"
        filepath = file_args.get(arg_name)
        if filepath is None:
            continue

        try:
            df = pd.read_csv(filepath, sep="\t", low_memory=False)
        except FileNotFoundError:
            print(f"  WARNING: File not found: {filepath}", file=sys.stderr)
            continue

        required = {"SUBJECT_ID", "topmed_study", "variable", "value"}
        if not required.issubset(df.columns):
            continue

        var_names = list(ds_info["variables"].keys())
        filtered = df[
            (df["topmed_study"] == cohort) & (df["variable"].isin(var_names))
        ].copy()

        if filtered.empty:
            continue

        wide = filtered.pivot_table(
            index="SUBJECT_ID", columns="variable", values="value", aggfunc="first"
        )
        wide.reset_index(inplace=True)
        wide.columns.name = None
        wide["SUBJECT_ID"] = wide["SUBJECT_ID"].astype(str)

        if merged is None:
            merged = wide
        else:
            merged = merged.merge(wide, on="SUBJECT_ID", how="outer")

        if verbose:
            n_vars = len([c for c in wide.columns if c != "SUBJECT_ID"])
            print(f"  Loaded {ds_key}: {len(wide):,} subjects, {n_vars} variables")

    if merged is None:
        return pd.DataFrame()

    return merged


# ─────────────────────────────────────────────────────────────────────────────
# BDC TSV Loading
# ─────────────────────────────────────────────────────────────────────────────

def discover_bdc_dirs(base_dir: str, cohort: str) -> list[str]:
    """Auto-discover BDC mapped-data directories for a cohort.

    Uses case-insensitive matching on the cohort name so that mixed-case
    folder names (e.g. COPDGene) are found on case-sensitive file systems.
    Also tries known aliases (e.g. HCHS for HCHS_SOL).
    """
    import re
    # Build alias map from centralized COHORT_FOLDER_TO_CANONICAL (invert it)
    from config import COHORT_FOLDER_TO_CANONICAL
    _CANONICAL_ALIASES: dict[str, list[str]] = {}
    for alias, canon in COHORT_FOLDER_TO_CANONICAL.items():
        _CANONICAL_ALIASES.setdefault(canon, []).append(alias)

    base = Path(base_dir)
    pat = re.compile(
        rf"^DMC_.*_{re.escape(cohort)}_Processed_\d+", re.IGNORECASE
    )
    dirs = []
    try:
        for proc_dir in sorted(base.iterdir()):
            if proc_dir.is_dir() and pat.match(proc_dir.name):
                for mapped in proc_dir.rglob("mapped-data"):
                    if mapped.is_dir():
                        dirs.append(str(mapped))
    except OSError:
        pass
    # Fallback: try aliases if no match on canonical name
    if not dirs:
        for alias in _CANONICAL_ALIASES.get(cohort.upper(), []):
            alias_pat = re.compile(
                rf"^DMC_.*_{re.escape(alias)}_Processed_\d+", re.IGNORECASE
            )
            try:
                for proc_dir in sorted(base.iterdir()):
                    if proc_dir.is_dir() and alias_pat.match(proc_dir.name):
                        for mapped in proc_dir.rglob("mapped-data"):
                            if mapped.is_dir():
                                dirs.append(str(mapped))
            except OSError:
                pass
            if dirs:
                break
    return dirs


def load_bdc_wide(dirs: list[str], verbose: bool = False) -> pd.DataFrame:
    """
    Load BDC dm-bip TSV output into wide format (one row per participant).
    Combines Demography + MeasurementObservation into a single wide frame.
    """
    # --- Demography ---
    demo_frames = []
    for d in dirs:
        for f in Path(d).glob("*Demography*.tsv"):
            demo_frames.append(pd.read_csv(f, sep="\t", low_memory=False))

    if not demo_frames:
        print("  WARNING: No Demography files found.", file=sys.stderr)
        return pd.DataFrame()

    demo = pd.concat(demo_frames, ignore_index=True)
    id_col = "associated_participant"
    if id_col not in demo.columns:
        print(f"  WARNING: '{id_col}' column missing.", file=sys.stderr)
        return pd.DataFrame()

    demo = demo.drop_duplicates(subset=[id_col], keep="first")
    participant_ids = set(demo[id_col].dropna().unique())

    # Build wide row per participant from Demography columns
    result = pd.DataFrame({"SUBJECT_ID": list(participant_ids)})

    # Map sex
    if "sex" in demo.columns:
        sex_map = demo.set_index(id_col)["sex"].to_dict()
        result["annotated_sex_1"] = result["SUBJECT_ID"].map(sex_map)

    # Race → always "Other" for HCHS (study-level coding)
    if "race" in demo.columns:
        race_map = demo.set_index(id_col)["race"].to_dict()
        result["race_us_1"] = result["SUBJECT_ID"].map(race_map)

    # Ethnicity → always "Hispanic or Latino" for HCHS
    if "ethnicity" in demo.columns:
        eth_map = demo.set_index(id_col)["ethnicity"].to_dict()
        result["hispanic_or_latino_1"] = result["SUBJECT_ID"].map(eth_map)

    # --- MeasurementObservation ---
    meas_frames = []
    for d in dirs:
        for f in Path(d).glob("*MeasurementObservation*.tsv"):
            meas_frames.append(pd.read_csv(f, sep="\t", low_memory=False))

    if meas_frames:
        meas = pd.concat(meas_frames, ignore_index=True)
        if "observation_type" in meas.columns and id_col in meas.columns:
            # Import BDC_MEASUREMENT_MAP for code -> variable name mapping
            from config import BDC_MEASUREMENT_MAP

            for code, spec in BDC_MEASUREMENT_MAP.items():
                topmed_var = spec["topmed_var"]
                aliases = spec.get("aliases", [])
                if isinstance(aliases, str):
                    aliases = [aliases]
                observation_types = [code, *aliases]
                code_rows = meas[meas["observation_type"].isin(observation_types)]
                if code_rows.empty:
                    continue
                # Take first value per participant — try known column names
                val_col = None
                for candidate in ["value_quantity__value_decimal", "value_decimal",
                                  "value_as_number", "value_enum", "value_string"]:
                    if candidate in code_rows.columns:
                        val_col = candidate
                        break
                if val_col is None:
                    if verbose:
                        print(f"    WARNING: no value column found for {code}, "
                              f"columns: {list(code_rows.columns)}")
                    continue
                val_map = code_rows.drop_duplicates(
                    subset=[id_col], keep="first"
                ).set_index(id_col)[val_col].to_dict()
                result[topmed_var] = result["SUBJECT_ID"].map(val_map)

        if verbose:
            print(f"  Loaded MeasurementObservation: {len(meas):,} rows")

    if verbose:
        print(f"  Total participants: {len(result):,}")
        print(f"  Variables: {[c for c in result.columns if c != 'SUBJECT_ID']}")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Completeness Analysis (shared by both modes)
# ─────────────────────────────────────────────────────────────────────────────

def compute_completeness(
    wide: pd.DataFrame,
    source_name: str,
    cohort: str,
) -> dict:
    """
    Compute per-participant phenotype completeness profile.

    For each participant, count how many EXAM variables (not trivially-complete
    ones like race/ethnicity) have non-null values. Return an anonymized
    histogram + summary statistics.
    """
    if wide.empty:
        return {"error": "No data loaded"}

    n_total = len(wide)

    # Identify which exam variables are actually present in the data
    available_exam_vars = [v for v in EXAM_VARIABLES if v in wide.columns]
    all_vars = [c for c in wide.columns if c != "SUBJECT_ID"]
    trivially_present = [v for v in TRIVIALLY_COMPLETE_VARS if v in wide.columns]

    print(f"\n  {'='*60}")
    print(f"  PHENOTYPE COMPLETENESS PROFILE: {source_name} — {cohort}")
    print(f"  {'='*60}")
    print(f"  Total participants: {n_total:,}")
    print(f"  All variables in data: {len(all_vars)}")
    print(f"  Exam variables present: {len(available_exam_vars)}")
    print(f"  Trivially-complete vars: {len(trivially_present)}")

    # --- Per-variable completeness ---
    print(f"\n  Per-variable completeness:")
    var_completeness = {}
    for var in sorted(all_vars):
        n_valid = int(wide[var].notna().sum())
        n_miss = n_total - n_valid
        pct = round(n_valid / n_total * 100, 1) if n_total > 0 else 0
        trivial_tag = " [trivially complete]" if var in TRIVIALLY_COMPLETE_VARS else ""
        exam_tag = " [exam]" if var in available_exam_vars else ""
        print(f"    {var:<30} {n_valid:>7,} / {n_total:,}  ({pct:>5.1f}%){trivial_tag}{exam_tag}")
        var_completeness[var] = {
            "n_valid": n_valid,
            "n_missing": n_miss,
            "pct_valid": pct,
            "is_exam_variable": var in available_exam_vars,
            "is_trivially_complete": var in TRIVIALLY_COMPLETE_VARS,
        }

    # --- Per-participant exam completeness histogram ---
    if available_exam_vars:
        exam_subset = wide[available_exam_vars]
        per_participant_count = exam_subset.notna().sum(axis=1)
    else:
        per_participant_count = pd.Series([0] * n_total)

    histogram = Counter(int(v) for v in per_participant_count)
    max_possible = len(available_exam_vars)

    print(f"\n  Per-participant exam variable completeness (max={max_possible}):")
    print(f"  {'Vars Non-Null':<20} {'# Participants':<18} {'% of Total':<12} {'Cumulative %':<12}")
    print(f"  {'─'*62}")

    cumulative = 0
    sorted_bins = sorted(histogram.keys())
    for n_vars in sorted_bins:
        count = histogram[n_vars]
        cumulative += count
        pct = round(count / n_total * 100, 2)
        cum_pct = round(cumulative / n_total * 100, 2)
        marker = " ← ZERO EXAM DATA" if n_vars == 0 else ""
        print(f"  {n_vars:<20} {count:>14,}  {pct:>10.2f}%  {cum_pct:>10.2f}%{marker}")

    # --- Key metrics ---
    n_zero_exam = histogram.get(0, 0)
    n_low = sum(histogram.get(k, 0) for k in range(0, 3))  # 0-2 vars
    n_high = sum(histogram.get(k, 0) for k in range(max_possible - 2, max_possible + 1))

    print(f"\n  KEY METRICS:")
    print(f"    Participants with ZERO exam data:  {n_zero_exam:,} ({n_zero_exam/n_total*100:.1f}%)")
    print(f"    Participants with 0-2 exam vars:   {n_low:,} ({n_low/n_total*100:.1f}%)")
    print(f"    Participants with near-complete:    {n_high:,} ({n_high/n_total*100:.1f}%)")
    print(f"    Median exam vars per participant:   {per_participant_count.median():.0f}")
    print(f"    Mean exam vars per participant:     {per_participant_count.mean():.1f}")

    result = {
        "metadata": {
            "source": source_name,
            "cohort": cohort,
            "generated": datetime.now(timezone.utc).isoformat(),
            "script": "validate_completeness.py",
            "note": "Anonymized phenotype completeness profile — no participant IDs or raw participant-level values.",
        },
        "total_participants": n_total,
        "exam_variables_available": available_exam_vars,
        "trivially_complete_variables": trivially_present,
        "n_exam_variables": len(available_exam_vars),
        "per_variable_completeness": var_completeness,
        "per_participant_histogram": {str(k): v for k, v in sorted(histogram.items())},
        "key_metrics": {
            "n_zero_exam_data": n_zero_exam,
            "pct_zero_exam_data": round(n_zero_exam / n_total * 100, 2) if n_total else 0,
            "n_low_completeness_0_to_2": n_low,
            "n_near_complete": n_high,
            "median_exam_vars": float(per_participant_count.median()),
            "mean_exam_vars": round(float(per_participant_count.mean()), 2),
        },
    }
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Compare mode — works with pre-generated JSONs (no raw data needed)
# ─────────────────────────────────────────────────────────────────────────────

def compare_profiles(topmed_path: str, bdc_path: str) -> None:
    """
    Load two completeness profiles and produce a side-by-side comparison.
    This mode works entirely from the aggregate JSONs.
    """
    with open(topmed_path) as f:
        topmed = json.load(f)
    with open(bdc_path) as f:
        bdc = json.load(f)

    t_total = topmed["total_participants"]
    b_total = bdc["total_participants"]
    t_hist = {int(k): v for k, v in topmed["per_participant_histogram"].items()}
    b_hist = {int(k): v for k, v in bdc["per_participant_histogram"].items()}
    t_metrics = topmed["key_metrics"]
    b_metrics = bdc["key_metrics"]

    print(f"\n{'='*70}")
    print(f"  PARTICIPANT COMPLETENESS COMPARISON")
    print(f"  TOPMed: {topmed['metadata']['cohort']} ({t_total:,} participants)")
    print(f"  BDC:    {bdc['metadata']['cohort']} ({b_total:,} participants)")
    print(f"{'='*70}")

    # Side-by-side histogram
    all_bins = sorted(set(list(t_hist.keys()) + list(b_hist.keys())))
    max_vars = max(all_bins) if all_bins else 0

    print(f"\n  {'Exam Vars':<12} {'TOPMed N':<12} {'TOPMed %':<10} {'BDC N':<12} {'BDC %':<10} {'Δ N':<10}")
    print(f"  {'─'*66}")

    for n_vars in all_bins:
        t_n = t_hist.get(n_vars, 0)
        b_n = b_hist.get(n_vars, 0)
        t_pct = t_n / t_total * 100 if t_total else 0
        b_pct = b_n / b_total * 100 if b_total else 0
        delta = b_n - t_n
        marker = " ← ZERO" if n_vars == 0 else ""
        print(f"  {n_vars:<12} {t_n:>10,}  {t_pct:>8.2f}%  {b_n:>10,}  {b_pct:>8.2f}%  {delta:>+8,}{marker}")

    # Key comparison
    t_zero = t_metrics["n_zero_exam_data"]
    b_zero = b_metrics["n_zero_exam_data"]

    print(f"\n  VERDICT:")
    print(f"  {'─'*66}")
    print(f"  TOPMed participants with ZERO exam data: {t_zero:,} ({t_metrics['pct_zero_exam_data']:.1f}%)")
    print(f"  BDC participants with ZERO exam data:    {b_zero:,} ({b_metrics['pct_zero_exam_data']:.1f}%)")
    print(f"  Difference (enrollment-only inflation):   {t_zero - b_zero:,}")
    print()

    if t_zero > 100:
        effective_topmed = t_total - t_zero
        print(f"  HYPOTHESIS CONFIRMED: TOPMed count includes {t_zero:,} enrollment-only subjects.")
        print(f"  Effective data-bearing participants:")
        print(f"    TOPMed: {effective_topmed:,} (after removing zero-exam subjects)")
        print(f"    BDC:    {b_total:,}")
        print(f"    Adjusted gap: {effective_topmed - b_total:,} (version-driven consent restructuring)")
    else:
        print(f"  HYPOTHESIS NOT CONFIRMED: TOPMed has only {t_zero:,} zero-exam subjects.")
        print(f"  The participant gap requires a different explanation.")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate participant count gaps via phenotype completeness profiles"
    )
    sub = parser.add_subparsers(dest="mode", help="Extraction mode")

    # -- topmed mode --
    tp = sub.add_parser("topmed", help="Extract from TOPMed DCC EAV files")
    tp.add_argument("--demographics-file", required=True)
    tp.add_argument("--baseline-covariates-file")
    tp.add_argument("--blood-pressure-file")
    tp.add_argument("--lipids-file")
    tp.add_argument("--blood-cell-count-file")
    tp.add_argument("--inflammation-file")
    tp.add_argument("--sleep-file")
    tp.add_argument("--cohort", required=True, help="TOPMed study name (e.g. HCHS_SOL)")
    tp.add_argument("--output-dir", default=".")
    tp.add_argument("--verbose", action="store_true")

    # -- bdc mode --
    bp = sub.add_parser("bdc", help="Extract from BDC dm-bip TSV output")
    bp.add_argument("--cohort", required=True, help="Cohort label (e.g. HCHS)")
    bp.add_argument("--base-dir", default=".")
    bp.add_argument("--mapped-data-dirs", nargs="*")
    bp.add_argument("--output-dir", default=".")
    bp.add_argument("--verbose", action="store_true")

    # -- compare mode --
    cp = sub.add_parser("compare", help="Compare two completeness JSONs")
    cp.add_argument("--topmed-json", required=True)
    cp.add_argument("--bdc-json", required=True)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.mode == "topmed":
        file_args = {
            "demographics_file": args.demographics_file,
            "baseline_covariates_file": getattr(args, "baseline_covariates_file", None),
            "blood_pressure_file": getattr(args, "blood_pressure_file", None),
            "lipids_file": getattr(args, "lipids_file", None),
            "blood_cell_count_file": getattr(args, "blood_cell_count_file", None),
            "inflammation_file": getattr(args, "inflammation_file", None),
            "sleep_file": getattr(args, "sleep_file", None),
        }
        wide = load_topmed_wide(file_args, args.cohort, verbose=args.verbose)
        result = compute_completeness(wide, "TOPMed DCC", args.cohort)

        out_path = Path(args.output_dir) / f"topmed_{args.cohort}_completeness.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\n  Saved: {out_path}")

    elif args.mode == "bdc":
        if args.mapped_data_dirs:
            dirs = args.mapped_data_dirs
        else:
            dirs = discover_bdc_dirs(args.base_dir, args.cohort)
        if not dirs:
            print(f"ERROR: No mapped-data directories found for {args.cohort}", file=sys.stderr)
            sys.exit(1)

        wide = load_bdc_wide(dirs, verbose=args.verbose)
        result = compute_completeness(wide, "BDC DMC", args.cohort)

        out_path = Path(args.output_dir) / f"bdc_{args.cohort}_completeness.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\n  Saved: {out_path}")

    elif args.mode == "compare":
        compare_profiles(args.topmed_json, args.bdc_json)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
