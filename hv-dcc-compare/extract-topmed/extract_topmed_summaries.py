"""
extract_topmed_summaries.py — Cross-cohort extraction from TOPMed DCC harmonized EAV files
======================================================================================
Reads one or more TOPMed DCC harmonized EAV flat files, extracts data for ALL
9 shared BDC cohorts (ARIC, CARDIA, CHS, COPDGene, FHS, HCHS/SOL, JHS, MESA, WHI),
normalizes value encodings, and writes **per-cohort aggregate-only JSON summaries**.

This is the cross-cohort generalization of `whi_compare/extract_topmed_whi.py`.

OUTPUT FORMAT (per cohort: topmed_<cohort>_summary.json):
    JSON with:
      metadata          — source, input files, generation timestamp
      cohort            — cohort name and metadata
      total_participants — integer
      datasets_loaded   — list of dataset keys successfully processed
      variables         — per-variable aggregate stats:
          categorical → {distribution: {label: {n, pct}}, n_missing, ...}
          continuous  → {n_valid, n_missing, mean, sd, median, q1, q3, min, max, ...}
      dq_flags          — data quality observations

    NO participant IDs, raw source values, or individual rows are written to JSON,
    stdout, or logs. Safe to export from enclave.

USAGE:
    # Simplest: point at the directory containing the tar.gz bundles and let
    # the script discover everything (base files + upload_2020-05-21 updates).
    python extract_topmed_summaries.py \\
        --base-dir   /path/to/TOPMed_DCC_harmonization/ \\
        --output-dir /path/to/output/

    # Same, but restrict to specific cohorts
    python extract_topmed_summaries.py \\
        --base-dir   /path/to/TOPMed_DCC_harmonization/ \\
        --output-dir /path/to/output/ \\
        --cohorts ARIC FHS WHI

    # With an explicit upload directory (if it has a non-default name)
    python extract_topmed_summaries.py \\
        --base-dir   /path/to/TOPMed_DCC_harmonization/ \\
        --upload-dir /path/to/TOPMed_DCC_harmonization/upload_2020-05-21/ \\
        --output-dir /path/to/output/

    # Override a single file (all others still auto-discovered from --base-dir)
    python extract_topmed_summaries.py \\
        --base-dir           /path/to/TOPMed_DCC_harmonization/ \\
        --demographics-file  /other/path/demographic_eav.txt \\
        --output-dir         /path/to/output/

    # Manual: supply each EAV file path explicitly (no --base-dir needed)
    python extract_topmed_summaries.py \\
        --demographics-file      /path/to/demographic_eav.txt \\
        --baseline-covariates-file /path/to/baseline_common_covariates_eav.txt \\
        --blood-pressure-file    /path/to/blood_pressure_eav.txt \\
        --lipids-file            /path/to/lipids_eav.txt \\
        --blood-cell-count-file  /path/to/blood_cell_count_eav.txt \\
        --inflammation-file      /path/to/inflammation_eav.txt \\
        --atherosclerosis-file   /path/to/atherosclerosis_eav.txt \\
        --vte-file               /path/to/vte_eav.txt \\
        --atherosclerosis-events-prior-file /path/to/athero_events_prior_eav.txt \\
        --sleep-file             /path/to/sleep_eav.txt \\
        --output-dir             /path/to/output/ \\
        --cohorts ARIC FHS WHI

    # First run -- use --verbose to see all studies and variables in each file
    python extract_topmed_summaries.py \\
        --base-dir /path/to/TOPMed_DCC_harmonization/ \\
        --output-dir /path/to/output/ \\
        --verbose

PREREQUISITES:
    - Data files must be extracted from the tar.gz bundles first:
        tar xzf topmed_dcc_harmonized_demographic_v4_*.tar.gz
    - Expected file format: tab-separated EAV with columns:
        SUBJECT_ID, unique_subject_key, topmed_study, dcc_harmonization_id, variable, value
    - All cohorts are combined in each file; the script filters by topmed_study column.
"""

from __future__ import annotations

import argparse
import json
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add the hv-dcc-compare root to the path so config.py is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    COHORTS,
    DATASETS,
    get_variable_spec,
)

# Track which files have already been profiled (one-time diagnostic per file)
_profiled_files: set[str] = set()


# ─────────────────────────────────────────────────────────────────────────────
# BASE-DIR AUTO-DISCOVERY
# ─────────────────────────────────────────────────────────────────────────────

# Maps filename substrings → DATASETS keys.  ORDER MATTERS: the more specific
# "atherosclerosis_events_*" patterns must come before bare "atherosclerosis".
_DATASET_FILENAME_PATTERNS: list[tuple[str, str]] = [
    ("atherosclerosis_events_incident", "atherosclerosis_events_incident"),
    ("atherosclerosis_events_prior",    "atherosclerosis_events_prior"),
    ("atherosclerosis",                 "atherosclerosis"),
    ("baseline_common_covariates",      "baseline_covariates"),
    ("blood_cell_count",                "blood_cell_count"),
    ("blood_pressure",                  "blood_pressure"),
    ("demographic",                     "demographics"),
    ("lipids",                          "lipids"),
    ("vte",                             "vte"),
    ("inflammation",                    "inflammation"),
    ("sleep",                           "sleep"),
]


def _classify_tgz(filename: str) -> str | None:
    """Return the DATASETS key that matches this tar.gz filename, or None."""
    lower = filename.lower()
    for pattern, key in _DATASET_FILENAME_PATTERNS:
        if pattern in lower:
            return key
    return None


def discover_tgz_files(
    base_dir: Path,
    upload_dir: Path | None = None,
) -> dict[str, Path]:
    """
    Scan base_dir (and optional upload_dir) for TOPMed DCC *.tar.gz files and
    map each to a DATASETS key.  upload_dir files take precedence over base_dir
    for the same key (they carry higher version numbers and supersede the base).

    If upload_dir is None, checks for a 'upload_2020-05-21' subdirectory of
    base_dir automatically.

    Returns: {dataset_key: Path_to_tar_gz}
    """
    found: dict[str, Path] = {}

    for tgz in sorted(base_dir.glob("*.tar.gz")):
        key = _classify_tgz(tgz.name)
        if key:
            found[key] = tgz

    if upload_dir is None:
        candidate = base_dir / "upload_2020-05-21"
        if candidate.is_dir():
            upload_dir = candidate

    if upload_dir is not None and upload_dir.is_dir():
        for tgz in sorted(upload_dir.glob("*.tar.gz")):
            key = _classify_tgz(tgz.name)
            if key:
                found[key] = tgz  # overrides base dir for same key

    return found


def extract_eav_from_tgz(tgz_path: Path, extract_root: Path) -> Path | None:
    """
    Extract a TOPMed DCC tar.gz and return the path to the *_eav.txt file
    inside it.  Extraction is skipped when the EAV file is already present.

    The extracted files land in:  extract_root / <archive-stem> /
    Returns None if no *_eav.txt is found after extraction.
    """
    stem = tgz_path.name
    if stem.endswith(".tar.gz"):
        stem = stem[:-7]
    dest = extract_root / stem

    # Re-use existing extraction if the EAV file is already there
    if dest.is_dir():
        existing = list(dest.rglob("*_eav.txt"))
        if existing:
            return existing[0]

    print(f"    Extracting: {tgz_path.name} ...", file=sys.stderr)
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tgz_path, "r:gz") as tf:
        dest_resolved = dest.resolve()
        for member in tf.getmembers():
            if member.issym() or member.islnk():
                raise ValueError(f"Unsafe tar link member rejected: {member.name!r}")
            member_path = (dest / member.name).resolve()
            if not str(member_path).startswith(str(dest_resolved)):
                raise ValueError(f"Unsafe tar member path rejected: {member.name!r}")
        tf.extractall(dest)

    eav_files = list(dest.rglob("*_eav.txt"))
    if not eav_files:
        print(
            f"    WARNING: No *_eav.txt found inside {tgz_path.name}",
            file=sys.stderr,
        )
        return None
    return eav_files[0]


# ─────────────────────────────────────────────────────────────────────────────
# EAV FILE LOADING
# ─────────────────────────────────────────────────────────────────────────────

def load_eav(
    filepath: str,
    variables: list[str],
    study_filter: str,
    verbose: bool = False,
) -> pd.DataFrame:
    """
    Load a TOPMed DCC EAV file, filter to the target study and variables,
    and pivot to one row per participant.

    Returns a wide DataFrame: SUBJECT_ID | var1 | var2 | ...
    """
    try:
        df = pd.read_csv(filepath, sep="\t", low_memory=False)
    except FileNotFoundError:
        print(f"    WARNING: File not found: {filepath}", file=sys.stderr)
        return pd.DataFrame()

    required = {"SUBJECT_ID", "topmed_study", "variable", "value"}
    missing = required - set(df.columns)
    if missing:
        print(f"    WARNING: Missing columns in {filepath}: {missing}", file=sys.stderr)
        return pd.DataFrame()

    # One-time diagnostic per file: show all studies and variables present
    if verbose and filepath not in _profiled_files:
        _profiled_files.add(filepath)
        print(f"\n    ── File profile: {Path(filepath).name} ──")
        print(f"    Rows: {len(df):,}  Columns: {list(df.columns)}")
        study_counts = df["topmed_study"].value_counts()
        print(f"    Studies in file ({len(study_counts)}):")
        for study, cnt in study_counts.items():
            marker = "  ← shared" if study in COHORTS else ""
            print(f"      {study}: {cnt:,} rows{marker}")
        var_counts = df["variable"].value_counts()
        print(f"    Variables in file ({len(var_counts)}):")
        for var, cnt in var_counts.items():
            print(f"      {var}: {cnt:,} rows")
        print()

    filtered = df[
        (df["topmed_study"] == study_filter) & (df["variable"].isin(variables))
    ].copy()

    if filtered.empty:
        return pd.DataFrame()

    # Detect duplicate (SUBJECT_ID, variable) pairs before pivoting
    dup_counts = filtered.groupby(["SUBJECT_ID", "variable"]).size()
    n_dups = int((dup_counts > 1).sum())
    if n_dups > 0:
        print(
            f"    WARNING: {n_dups:,} duplicate (subject, variable) pairs "
            f"for {study_filter} in {Path(filepath).name} — keeping first value only",
            file=sys.stderr,
        )

    wide = filtered.pivot_table(
        index="SUBJECT_ID", columns="variable", values="value", aggfunc="first"
    )
    wide.reset_index(inplace=True)
    wide.columns.name = None
    # Ensure SUBJECT_ID is always string to avoid int64/object merge conflicts
    wide["SUBJECT_ID"] = wide["SUBJECT_ID"].astype(str)
    return wide


def load_all_datasets(
    file_args: dict[str, str | None],
    study_filter: str,
    verbose: bool = False,
) -> tuple[pd.DataFrame | None, list[str], dict[str, list[str]]]:
    """
    Load data from all provided EAV files for a single cohort.

    Returns:
        - merged wide DataFrame (one row per participant) or None
        - list of dataset keys successfully loaded
        - dict of { dataset_key: [variables found] }
    """
    merged: pd.DataFrame | None = None
    loaded_datasets: list[str] = []
    vars_found: dict[str, list[str]] = {}

    for ds_key, ds_info in DATASETS.items():
        arg_name = ds_key + "_file"
        filepath = file_args.get(arg_name)
        if filepath is None:
            continue

        var_names = list(ds_info["variables"].keys())
        wide = load_eav(filepath, var_names, study_filter, verbose=verbose)
        if wide.empty:
            continue

        found_vars = [v for v in var_names if v in wide.columns]
        if not found_vars:
            continue

        loaded_datasets.append(ds_key)
        vars_found[ds_key] = found_vars

        if merged is None:
            merged = wide
        else:
            merged = merged.merge(wide, on="SUBJECT_ID", how="outer")

    return merged, loaded_datasets, vars_found


# ─────────────────────────────────────────────────────────────────────────────
# AGGREGATE STATISTICS COMPUTATION
# ─────────────────────────────────────────────────────────────────────────────

def categorical_stats(series: pd.Series, value_map: dict | None) -> dict:
    """Compute frequency table for a categorical variable."""
    # Normalize values through the value map
    if value_map:
        normalized = series.map(
            lambda x: value_map.get(str(x), "UNMAPPED") if pd.notna(x) else None
        )
    else:
        normalized = series.copy()

    n_total = int(len(normalized))
    n_missing = int(normalized.isna().sum())
    n_valid = n_total - n_missing

    counts = normalized.value_counts(dropna=True).sort_index()
    distribution = {}
    for val, cnt in counts.items():
        distribution[str(val)] = {
            "n": int(cnt),
            "pct": round(cnt / n_valid * 100, 1) if n_valid > 0 else 0.0,
            "pct_of_total": round(cnt / n_total * 100, 1) if n_total > 0 else 0.0,
        }

    return {
        "type": "categorical",
        "n_total": n_total,
        "n_valid": n_valid,
        "n_missing": n_missing,
        "pct_missing": round(n_missing / n_total * 100, 1) if n_total > 0 else 0.0,
        "distribution": distribution,
    }


def continuous_stats(
    series: pd.Series,
    unit: str | None = None,
    plausible_lo: float | None = None,
    plausible_hi: float | None = None,
) -> dict:
    """Compute descriptive statistics for a continuous variable."""
    numeric = pd.to_numeric(series, errors="coerce")
    n_total = int(len(numeric))
    s = numeric.dropna()
    n_valid = int(len(s))
    n_missing = n_total - n_valid

    n_implausible = 0
    if plausible_lo is not None and plausible_hi is not None and n_valid > 0:
        implausible = s[(s < plausible_lo) | (s > plausible_hi)]
        n_implausible = int(len(implausible))

    result = {
        "type": "continuous",
        "unit": unit,
        "n_total": n_total,
        "n_valid": n_valid,
        "n_missing": n_missing,
        "pct_missing": round(n_missing / n_total * 100, 1) if n_total > 0 else 0.0,
        "mean": round(float(s.mean()), 4) if n_valid > 0 else None,
        "sd": round(float(s.std()), 4) if n_valid > 1 else None,
        "median": round(float(s.median()), 4) if n_valid > 0 else None,
        "q1": round(float(s.quantile(0.25)), 4) if n_valid > 0 else None,
        "q3": round(float(s.quantile(0.75)), 4) if n_valid > 0 else None,
        "min": round(float(s.min()), 4) if n_valid > 0 else None,
        "max": round(float(s.max()), 4) if n_valid > 0 else None,
        "n_implausible": n_implausible,
    }
    return result


# ─────────────────────────────────────────────────────────────────────────────
# DATA QUALITY CHECKS
# ─────────────────────────────────────────────────────────────────────────────

def run_dq_checks(
    cohort_name: str,
    variable_stats: dict[str, dict],
    n_participants: int,
) -> list[str]:
    """Run data quality checks and return flag strings for JSON."""
    flags: list[str] = []

    # Check participant count
    if n_participants == 0:
        flags.append(f"CRITICAL: No participants found for {cohort_name}")
        return flags

    # Check for high missingness (> 50%)
    for var_name, stats in variable_stats.items():
        pct_missing = stats.get("pct_missing", 0.0)
        if pct_missing > 50:
            flags.append(
                f"WARNING: {var_name} has {pct_missing:.1f}% missing "
                f"({stats.get('n_missing', 0):,}/{stats.get('n_total', 0):,})"
            )

    # Check for implausible values in continuous variables
    for var_name, stats in variable_stats.items():
        if stats.get("type") == "continuous":
            n_imp = stats.get("n_implausible", 0)
            if n_imp > 0:
                flags.append(
                    f"WARNING: {var_name} has {n_imp:,} implausible values "
                    f"(outside plausible range)"
                )

    # Check for UNMAPPED categorical values
    for var_name, stats in variable_stats.items():
        if stats.get("type") == "categorical":
            dist = stats.get("distribution", {})
            unmapped = [k for k in dist if k == "UNMAPPED" or k.startswith("UNMAPPED:")]
            if unmapped:
                flags.append(
                    f"WARNING: {var_name} has unmapped values: {unmapped}"
                )

    if not flags:
        flags.append(f"OK: No data quality issues detected for {cohort_name}")

    return flags


# ─────────────────────────────────────────────────────────────────────────────
# PER-COHORT PROCESSING
# ─────────────────────────────────────────────────────────────────────────────

def process_cohort(
    cohort_name: str,
    file_args: dict[str, str | None],
    input_files_summary: dict[str, str],
    verbose: bool = False,
) -> dict | None:
    """
    Process a single cohort: load all datasets, compute aggregate stats.
    Returns a JSON-serializable dict, or None if no data found.
    """
    print(f"\n  {'─' * 60}")
    print(f"  Processing: {cohort_name}")
    print(f"  {'─' * 60}")

    cohort_meta = COHORTS.get(cohort_name, {})

    merged, loaded_datasets, vars_found = load_all_datasets(file_args, cohort_name, verbose=verbose)

    if merged is None or merged.empty:
        print(f"    No data found for {cohort_name} in any input file.")
        return None

    n_participants = len(merged)
    total_vars_found = sum(len(v) for v in vars_found.values())
    print(f"    Participants: {n_participants:,}")
    print(f"    Datasets loaded: {loaded_datasets}")
    print(f"    Variables found: {total_vars_found}")

    # Compute per-variable aggregate statistics
    variable_stats: dict[str, dict] = {}

    for ds_key in loaded_datasets:
        for var_name in vars_found.get(ds_key, []):
            if var_name not in merged.columns:
                continue

            spec = get_variable_spec(var_name)
            if spec is None:
                continue

            bdc_label = spec.get("bdc_label", var_name)
            var_type = spec.get("var_type", "continuous")

            if var_type == "categorical":
                stats = categorical_stats(
                    merged[var_name],
                    value_map=spec.get("value_map"),
                )
            else:
                stats = continuous_stats(
                    merged[var_name],
                    unit=spec.get("unit"),
                    plausible_lo=spec.get("plausible_lo"),
                    plausible_hi=spec.get("plausible_hi"),
                )

            stats["bdc_label"] = bdc_label
            stats["topmed_variable"] = var_name
            stats["dataset"] = ds_key
            variable_stats[var_name] = stats

    # Run DQ checks
    dq_flags = run_dq_checks(cohort_name, variable_stats, n_participants)

    # Print summary to console
    n_cat = sum(1 for v in variable_stats.values() if v["type"] == "categorical")
    n_con = sum(1 for v in variable_stats.values() if v["type"] == "continuous")
    print(f"    Stats computed: {n_cat} categorical, {n_con} continuous")
    for flag in dq_flags:
        prefix = "    ⚠" if flag.startswith("WARNING") else "    🚨" if flag.startswith("CRITICAL") else "    ✓"
        print(f"{prefix} {flag}")

    result = {
        "metadata": {
            "source": "TOPMed DCC",
            "cohort": cohort_name,
            "generated": datetime.now(timezone.utc).isoformat(),
            "script": "extract_topmed_summaries.py",
            "input_files": input_files_summary,
            "note": "Aggregate statistics only — no individual-level data.",
        },
        "cohort": {
            "name": cohort_name,
            "full_name": cohort_meta.get("full_name", ""),
            "phs": cohort_meta.get("phs", ""),
            "topmed_version": cohort_meta.get("topmed_version", ""),
            "bdc_version": cohort_meta.get("bdc_version", ""),
        },
        "total_participants": n_participants,
        "datasets_loaded": loaded_datasets,
        "variables_by_dataset": {k: v for k, v in vars_found.items()},
        "variables": variable_stats,
        "dq_flags": dq_flags,
    }
    return result


# ─────────────────────────────────────────────────────────────────────────────
# CONSOLE REPORT
# ─────────────────────────────────────────────────────────────────────────────

def print_cohort_summary(result: dict) -> None:
    """Print a human-readable summary of one cohort's results."""
    cohort = result["cohort"]["name"]
    n = result["total_participants"]
    variables = result["variables"]

    print(f"\n  ── {cohort} SUMMARY ({n:,} participants) ──")

    for var_name, stats in sorted(variables.items()):
        bdc_label = stats.get("bdc_label", var_name)
        if stats["type"] == "categorical":
            dist = stats.get("distribution", {})
            n_valid = stats["n_valid"]
            n_missing = stats["n_missing"]
            cats_str = ", ".join(
                f"{k}: {v['n']:,} ({v['pct']:.1f}%)" for k, v in sorted(dist.items())
            )
            print(f"    {bdc_label:<35} n={n_valid:,}  miss={n_missing:,}  [{cats_str}]")
        else:
            mean = stats.get("mean")
            sd = stats.get("sd")
            n_valid = stats["n_valid"]
            n_missing = stats["n_missing"]
            unit = stats.get("unit", "")
            mean_str = f"{mean:.2f}" if mean is not None else "—"
            sd_str = f"{sd:.2f}" if sd is not None else "—"
            print(
                f"    {bdc_label:<35} n={n_valid:,}  miss={n_missing:,}  "
                f"mean={mean_str} ± {sd_str} {unit}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract aggregate summary statistics from TOPMed DCC harmonized EAV files "
            "for all 9 shared BDC cohorts."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # ── Auto-discovery shortcut ─────────────────────────────────────────────
    parser.add_argument(
        "--base-dir",
        default=None,
        metavar="DIR",
        help=(
            "Root directory that contains the TOPMed DCC tar.gz bundles. "
            "The script scans this directory for all recognised dataset archives "
            "and also checks for a 'upload_2020-05-21' subdirectory, whose files "
            "take precedence over same-dataset files in the base directory. "
            "Archives are extracted automatically into <base-dir>/extracted/. "
            "Explicit --*-file arguments override auto-discovered paths."
        ),
    )
    parser.add_argument(
        "--upload-dir",
        default=None,
        metavar="DIR",
        help=(
            "Explicit path to the upload subdirectory that contains newer-version "
            "tar.gz files (overrides the default 'upload_2020-05-21' subdirectory "
            "of --base-dir).  Only used when --base-dir is also given."
        ),
    )

    # ── Per-dataset file overrides ───────────────────────────────────────────
    # Not required at parse time — validated in main() after auto-discovery.
    for ds_key, ds_info in DATASETS.items():
        arg_name = f"--{ds_key.replace('_', '-')}-file"
        parser.add_argument(
            arg_name,
            required=False,
            default=None,
            metavar="FILE",
            help=f"{ds_info['description']} EAV file. "
                 f"Variables: {', '.join(ds_info['variables'].keys())}",
        )

    parser.add_argument(
        "--output-dir",
        required=True,
        metavar="DIR",
        help="Directory for per-cohort JSON summary output files.",
    )
    parser.add_argument(
        "--cohorts",
        nargs="*",
        default=None,
        metavar="COHORT",
        help=(
            "Restrict to specific cohorts (e.g., --cohorts ARIC FHS WHI). "
            f"Default: all 9 ({', '.join(COHORTS.keys())})"
        ),
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Print file-level diagnostic: all studies and variables in each EAV file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args_dict = vars(args)

    # Determine which cohorts to process
    if args.cohorts:
        cohort_key_map = {key.casefold(): key for key in COHORTS}
        invalid = [c for c in args.cohorts if c.casefold() not in cohort_key_map]
        if invalid:
            print(f"ERROR: Unknown cohort(s): {invalid}", file=sys.stderr)
            print(f"Valid cohorts: {list(COHORTS.keys())}", file=sys.stderr)
            sys.exit(1)
        cohort_list = [cohort_key_map[c.casefold()] for c in args.cohorts]
    else:
        cohort_list = list(COHORTS.keys())

    # ── Auto-discovery from --base-dir ────────────────────────────────────────
    auto_discovered: dict[str, str] = {}  # dataset_key → eav txt path
    if args.base_dir:
        base_dir = Path(args.base_dir)
        if not base_dir.is_dir():
            print(f"ERROR: --base-dir does not exist: {base_dir}", file=sys.stderr)
            sys.exit(1)

        upload_dir: Path | None = Path(args.upload_dir) if args.upload_dir else None
        tgz_map = discover_tgz_files(base_dir, upload_dir)

        extract_root = base_dir / "extracted"
        n_found = 0
        print(f"  Auto-discovery from: {base_dir}")
        if not tgz_map:
            print("  WARNING: No recognised *.tar.gz archives found.", file=sys.stderr)
        for ds_key, tgz_path in sorted(tgz_map.items()):
            eav_path = extract_eav_from_tgz(tgz_path, extract_root)
            if eav_path:
                auto_discovered[ds_key] = str(eav_path)
                n_found += 1
                print(f"    {ds_key:<38} <- {tgz_path.name}")
            else:
                print(
                    f"    WARNING: Could not extract EAV from {tgz_path.name}",
                    file=sys.stderr,
                )
        print(f"  Auto-discovered {n_found} dataset(s).")

    # ── Build file_args: auto-discovered paths, then explicit CLI overrides ───
    file_args: dict[str, str | None] = {}
    input_files_summary: dict[str, str] = {}
    for ds_key in DATASETS:
        arg_key = ds_key + "_file"
        # Explicit CLI arg takes precedence over auto-discovery
        filepath = args_dict.get(ds_key.replace("-", "_") + "_file")
        if filepath is None:
            filepath = auto_discovered.get(ds_key)
        file_args[arg_key] = filepath
        if filepath:
            input_files_summary[ds_key] = filepath

    # Validate: demographics is required (it anchors participant counts)
    if not file_args.get("demographics_file"):
        print(
            "ERROR: demographics EAV file is required. "
            "Supply --demographics-file or use --base-dir pointing to a directory "
            "that contains topmed_dcc_harmonized_demographic_*.tar.gz.",
            file=sys.stderr,
        )
        sys.exit(1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    n_files = sum(1 for v in file_args.values() if v is not None)

    print("=" * 72)
    print("  CROSS-COHORT TOPMed DCC EXTRACTION")
    print("=" * 72)
    print(f"  Cohorts to process: {cohort_list}")
    print(f"  Input files: {n_files}")
    for ds_key, fp in input_files_summary.items():
        print(f"    {ds_key}: {fp}")
    print(f"  Output directory: {output_dir}")

    verbose = args.verbose

    # Process each cohort
    results: dict[str, dict] = {}
    for cohort_name in cohort_list:
        result = process_cohort(cohort_name, file_args, input_files_summary, verbose=verbose)
        if result is not None:
            results[cohort_name] = result

            # Write per-cohort JSON
            out_file = output_dir / f"topmed_{cohort_name.lower()}_summary.json"
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"    Written: {out_file}")

            print_cohort_summary(result)

    # Write combined cross-cohort summary
    if results:
        combined = {
            "metadata": {
                "source": "TOPMed DCC",
                "generated": datetime.now(timezone.utc).isoformat(),
                "script": "extract_topmed_summaries.py",
                "cohorts_processed": list(results.keys()),
                "input_files": input_files_summary,
                "note": "Aggregate statistics only — no individual-level data.",
            },
            "cohort_summaries": {},
        }
        for cohort_name, result in results.items():
            combined["cohort_summaries"][cohort_name] = {
                "total_participants": result["total_participants"],
                "datasets_loaded": result["datasets_loaded"],
                "n_variables": len(result["variables"]),
                "dq_flags": result["dq_flags"],
            }

        combined_file = output_dir / "topmed_all_cohorts_summary.json"
        with open(combined_file, "w", encoding="utf-8") as f:
            json.dump(combined, f, indent=2, ensure_ascii=False)
        print(f"\n  Combined summary: {combined_file}")

    # Final report
    print("\n" + "=" * 72)
    print("  EXTRACTION COMPLETE")
    print("=" * 72)
    print(f"  Cohorts processed: {len(results)} of {len(cohort_list)} requested")
    for cohort_name, result in results.items():
        n = result["total_participants"]
        nv = len(result["variables"])
        print(f"    {cohort_name:<12} {n:>8,} participants  {nv:>3} variables")
    not_found = [c for c in cohort_list if c not in results]
    if not_found:
        print(f"  Cohorts with no data: {not_found}")
    print(f"  Output files in: {output_dir}")
    print()


if __name__ == "__main__":
    main()
