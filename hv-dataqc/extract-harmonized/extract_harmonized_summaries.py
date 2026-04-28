"""
extract_harmonized_summaries.py — HV-DataQC Component 2

Summarize dm-bip harmonized output TSV files for one cohort and export an
aggregate-only JSON artifact compatible with compare_source_harmonized.py.

Design:
  - ZERO dependency on HV transform YAML files. Reads entity TSVs produced by
    dm-bip and groups by observation_type / condition_concept columns that are
    already embedded in the pipeline output.
  - UUID resolution: Visit.tsv is loaded FIRST. Associated-visit UUIDs in all
    entity TSVs are resolved to human-readable labels before building by-visit
    stats. This ensures C8 visit-distribution keys match the source extractor.
  - Run inside the data enclave. Only aggregate statistics leave the enclave.

Usage examples:
  # Auto-discover consent group dirs under a root
  python extract_harmonized_summaries.py \\
      --cohort SPIROMICS \\
      --harmonized-root /enclave/SPIROMICS-BDCHM

  # Specify explicit mapped-data directories
  python extract_harmonized_summaries.py \\
      --cohort SPIROMICS \\
      --mapped-data-dirs /enclave/SPIROMICS-BDCHM/.../mapped-data \\
                         /enclave/SPIROMICS-BDCHM/.../mapped-data

  # Include visit-stratified stats
  python extract_harmonized_summaries.py \\
      --cohort SPIROMICS \\
      --harmonized-root /enclave/SPIROMICS-BDCHM \\
      --by-visit

  # Write to a specific directory
  python extract_harmonized_summaries.py \\
      --cohort SPIROMICS \\
      --harmonized-root /enclave/SPIROMICS-BDCHM \\
      --output-dir /enclave/dataqc-runs/
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

import pandas as pd

# Entity TSV files produced by dm-bip
ENTITY_FILES = {
    "Demography": "Demography.tsv",
    "Person": "Person.tsv",
    "Participant": "Participant.tsv",
    "Visit": "Visit.tsv",
    "MeasurementObservation": "MeasurementObservation.tsv",
    "MeasurementObservationSet": "MeasurementObservationSet.tsv",
    "Condition": "Condition.tsv",
    "DrugExposure": "DrugExposure.tsv",
    "Procedure": "Procedure.tsv",
    "Observation": "Observation.tsv",
}


def _json_safe(value: Any) -> Any:
    """Recursively convert non-finite floats to None before strict JSON writing."""
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _write_json_atomic(path: Path, data: Any) -> None:
    """Write strict JSON via temp file then atomic replace."""
    tmp_path = path.with_name(f"{path.name}.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(_json_safe(data), fh, indent=2, default=str, allow_nan=False)
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


# ---------------------------------------------------------------------------
# Logging — tee to stdout and file simultaneously
# ---------------------------------------------------------------------------

class _Tee:
    """Write to both stdout and a log file simultaneously."""

    def __init__(self, log_path: Path) -> None:
        self._log = log_path.open("w", encoding="utf-8")
        self._stdout = sys.stdout
        sys.stdout = self

    def write(self, msg: str) -> None:
        self._stdout.write(msg)
        self._log.write(msg)

    def flush(self) -> None:
        self._stdout.flush()
        self._log.flush()

    def close(self) -> None:
        sys.stdout = self._stdout
        self._log.close()


# ---------------------------------------------------------------------------
# Directory auto-discovery
# ---------------------------------------------------------------------------

def discover_mapped_data_dirs(harmonized_root: Path, cohort: str) -> list[Path]:
    """Walk *harmonized_root* and return all mapped-data/ directories.

    Expected layout::

        <harmonized_root>/
            DMC_<cohort_lower>_<study>_c1_<COHORT>_Processed_<ts>/
                <cohort_lower>_<study>_c1_BDCHM/
                    mapped-data/        <- collected
                    validation-logs/
            DMC_<cohort_lower>_..._c2_.../
                ...

    Sorted by consent group suffix for deterministic order.
    """
    mapped_dirs: list[Path] = []
    # Build a filter token: "_COPDGene_Processed_" (case-insensitive match)
    cohort_token = f"_{cohort}_Processed_".lower()

    for run_dir in sorted(harmonized_root.iterdir()):
        if not run_dir.is_dir():
            continue
        if run_dir.name.lower().startswith("dataqc"):
            continue
        if not run_dir.name.upper().startswith("DMC_"):
            continue
        if cohort_token not in run_dir.name.lower():
            continue

        for bdchm_dir in sorted(run_dir.iterdir()):
            if not bdchm_dir.is_dir():
                continue
            if not bdchm_dir.name.endswith("_BDCHM"):
                continue
            mapped = bdchm_dir / "mapped-data"
            if mapped.exists():
                mapped_dirs.append(mapped)
                break

    return mapped_dirs


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_entity(mapped_data_dirs: list[Path], entity: str) -> pd.DataFrame | None:
    """Load and concatenate a specific entity TSV from all mapped-data dirs."""
    filename = ENTITY_FILES.get(entity)
    if not filename:
        return None

    frames: list[pd.DataFrame] = []
    found_files: list[tuple[str, int]] = []

    for d in mapped_data_dirs:
        tsv = d / filename
        if tsv.exists():
            try:
                df = pd.read_csv(tsv, sep="\t", low_memory=False)
                df.columns = df.columns.astype(str).str.strip()
                frames.append(df)
                label = d.parent.parent.name
                found_files.append((label, len(df)))
            except Exception as exc:
                print(f"      WARNING: Could not read {tsv}: {exc}")

    if not frames:
        return None

    print(f"    Found {len(found_files)} file(s) for '{filename}':")
    for label, n in found_files:
        print(f"      [{label}] {n:,} rows")

    return pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]


# ---------------------------------------------------------------------------
# UUID → visit label resolution
# ---------------------------------------------------------------------------

def build_visit_id_to_label(visit_df: pd.DataFrame) -> dict[str, str]:
    """Build a {uuid_or_id: human_label} dict from the Visit.tsv entity.

    Priority for the label column: name > visit_type > visit_category.
    Falls back to the id itself if neither is populated.
    """
    mapping: dict[str, str] = {}
    if "id" not in visit_df.columns:
        return mapping

    label_col = (
        "name" if "name" in visit_df.columns
        else "visit_type" if "visit_type" in visit_df.columns
        else "visit_category" if "visit_category" in visit_df.columns
        else None
    )
    if label_col is None:
        return mapping

    for _, row in visit_df.iterrows():
        vid = str(row["id"]) if pd.notna(row["id"]) else None
        vlabel = str(row[label_col]) if pd.notna(row[label_col]) else vid
        if vid:
            mapping[vid] = vlabel

    return mapping


def resolve_visit_series(
    series: pd.Series,
    visit_id_to_label: dict[str, str],
) -> pd.Series:
    """Replace UUID values with human-readable visit labels where a mapping exists.

    Values that are already human-readable labels (not in the map) are passed
    through unchanged, so the resolver is safe to apply unconditionally.
    """
    if not visit_id_to_label:
        return series

    return series.map(
        lambda v: visit_id_to_label.get(str(v), v) if pd.notna(v) else v
    )


def participant_count_from_entity(df: pd.DataFrame, preferred_cols: tuple[str, ...]) -> int:
    """Return unique participant count from the first available preferred column."""
    for col in preferred_cols:
        if col in df.columns:
            return int(df[col].nunique(dropna=True))
    return 0


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------

def categorical_stats(series: pd.Series) -> dict:
    n_total = int(len(series))
    n_missing = int(series.isna().sum())
    n_valid = n_total - n_missing
    counts = series.value_counts(dropna=True).sort_index()
    distribution: dict = {}
    for val, cnt in counts.items():
        distribution[str(val)] = {
            "n": int(cnt),
            "pct": round(int(cnt) / n_valid * 100, 2) if n_valid > 0 else 0.0,
        }
    return {
        "type": "categorical",
        "n_total": n_total,
        "n_valid": n_valid,
        "n_missing": n_missing,
        "pct_missing": round(n_missing / n_total * 100, 2) if n_total > 0 else 0.0,
        "n_distinct": int(series.nunique(dropna=True)),
        "distribution": distribution,
    }


def continuous_stats(series: pd.Series) -> dict:
    numeric = pd.to_numeric(series, errors="coerce")
    n_total = int(len(numeric))
    s = numeric.dropna()
    n_valid = int(len(s))
    n_missing = n_total - n_valid
    result: dict = {
        "type": "continuous",
        "n_total": n_total,
        "n_valid": n_valid,
        "n_missing": n_missing,
        "pct_missing": round(n_missing / n_total * 100, 2) if n_total > 0 else 0.0,
        "n_distinct": int(s.nunique()),
    }
    if n_valid > 0:
        result.update(
            {
                "mean": round(float(s.mean()), 4),
                "sd": round(float(s.std()), 4),
                "min": round(float(s.min()), 4),
                "q1": round(float(s.quantile(0.25)), 4),
                "median": round(float(s.quantile(0.50)), 4),
                "q3": round(float(s.quantile(0.75)), 4),
                "max": round(float(s.max()), 4),
                "p5": round(float(s.quantile(0.05)), 4),
                "p95": round(float(s.quantile(0.95)), 4),
            }
        )
    else:
        result.update(
            {k: None for k in ["mean", "sd", "min", "q1", "median", "q3", "max", "p5", "p95"]}
        )
    return result


# ---------------------------------------------------------------------------
# Entity processors
# ---------------------------------------------------------------------------

def process_demography(df: pd.DataFrame) -> dict[str, dict]:
    """Extract sex, race, ethnicity summaries from Demography entity."""
    variables: dict[str, dict] = {}
    for col, label in [("sex", "sex"), ("race", "race"), ("ethnicity", "ethnicity")]:
        if col in df.columns:
            summary = categorical_stats(df[col])
            summary["entity"] = "Demography"
            summary["bdc_label"] = label
            variables[f"demog_{col}"] = summary
    return variables


def process_measurements(
    df: pd.DataFrame,
    visit_id_to_label: dict[str, str],
    by_visit: bool = False,
) -> dict[str, dict]:
    """Extract per-observation_type summaries from MeasurementObservation.

    dm-bip flattens nested Quantity via double-underscore separator, so
    value_quantity.value_decimal becomes value_quantity__value_decimal.

    Args:
        df: MeasurementObservation DataFrame.
        visit_id_to_label: UUID-to-label map built from Visit.tsv. Resolves
            UUIDs in associated_visit before building by-visit stats.
        by_visit: If True, include per-visit breakdowns.
    """
    variables: dict[str, dict] = {}

    if "observation_type" not in df.columns:
        return variables

    DECIMAL_COL       = "value_quantity__value_decimal"
    INTEGER_COL       = "value_quantity__value_integer"
    CODED_COL         = "value_quantity__value_coded"
    VALUE_CONCEPT_COL = "value_concept"

    obs_cols = [
        c for c in df.columns
        if "value" in c.lower() or c in ("observation_type", "age_at_observation")
    ]
    print(f"    [Columns] {len(df.columns)} total. Observation/value-related:")
    for c in obs_cols:
        print(f"      {c}: {int(df[c].notna().sum()):,} non-null / {len(df):,} rows")

    # Resolve visit UUIDs once for the whole DataFrame
    if by_visit and "associated_visit" in df.columns:
        df = df.copy()
        df["associated_visit"] = resolve_visit_series(df["associated_visit"], visit_id_to_label)

    for obs_type, group in df.groupby("observation_type", dropna=False):
        key = str(obs_type) if pd.notna(obs_type) else "MISSING_OBS_TYPE"

        has_decimal       = DECIMAL_COL       in df.columns and group[DECIMAL_COL].notna().any()
        has_integer       = INTEGER_COL       in df.columns and group[INTEGER_COL].notna().any()
        has_coded         = CODED_COL         in df.columns and group[CODED_COL].notna().any()
        has_value_concept = VALUE_CONCEPT_COL in df.columns and group[VALUE_CONCEPT_COL].notna().any()

        if has_decimal or has_integer:
            value_col = DECIMAL_COL if has_decimal else INTEGER_COL
            summary = continuous_stats(group[value_col])
        elif has_coded:
            summary = categorical_stats(group[CODED_COL])
        elif has_value_concept:
            summary = categorical_stats(group[VALUE_CONCEPT_COL])
        else:
            summary = {
                "type": "unknown",
                "n_total": int(len(group)),
                "n_valid": 0,
                "n_missing": int(len(group)),
            }

        summary["entity"] = "MeasurementObservation"
        summary["observation_type"] = key

        if by_visit and "associated_visit" in df.columns:
            by_visit_stats: dict[str, dict] = {}
            for visit_val, vgroup in group.groupby("associated_visit", dropna=False):
                vlabel = str(visit_val) if pd.notna(visit_val) else "_MISSING_VISIT"
                if has_decimal or has_integer:
                    by_visit_stats[vlabel] = continuous_stats(vgroup[value_col])
                elif has_coded:
                    by_visit_stats[vlabel] = categorical_stats(vgroup[CODED_COL])
                elif has_value_concept:
                    by_visit_stats[vlabel] = categorical_stats(vgroup[VALUE_CONCEPT_COL])
            summary["by_visit"] = by_visit_stats

        variables[f"measurement_{key}"] = summary

    return variables


def process_conditions(
    df: pd.DataFrame,
    visit_id_to_label: dict[str, str],
    by_visit: bool = False,
) -> dict[str, dict]:
    """Extract per-condition_concept summaries from Condition entity.

    Args:
        df: Condition DataFrame.
        visit_id_to_label: UUID-to-label map from Visit.tsv.
        by_visit: If True, include per-visit breakdowns.
    """
    variables: dict[str, dict] = {}

    concept_col = "condition_concept" if "condition_concept" in df.columns else None
    status_col  = "condition_status"  if "condition_status"  in df.columns else None

    if not concept_col:
        return variables

    if by_visit and "associated_visit" in df.columns:
        df = df.copy()
        df["associated_visit"] = resolve_visit_series(df["associated_visit"], visit_id_to_label)

    for concept, group in df.groupby(concept_col, dropna=False):
        key = str(concept) if pd.notna(concept) else "MISSING_CONCEPT"

        if status_col:
            summary = categorical_stats(group[status_col])
        else:
            summary = {
                "type": "categorical",
                "n_total": int(len(group)),
                "n_valid": int(len(group)),
                "n_missing": 0,
                "pct_missing": 0.0,
            }

        summary["entity"] = "Condition"
        summary["condition_concept"] = key

        if by_visit and "associated_visit" in df.columns:
            by_visit_stats: dict[str, dict] = {}
            for visit_val, vgroup in group.groupby("associated_visit", dropna=False):
                vlabel = str(visit_val) if pd.notna(visit_val) else "_MISSING_VISIT"
                if status_col:
                    by_visit_stats[vlabel] = categorical_stats(vgroup[status_col])
            summary["by_visit"] = by_visit_stats

        variables[f"condition_{key}"] = summary

    return variables


def process_observations(df: pd.DataFrame) -> dict[str, dict]:
    """Extract per-observation_type summaries from Observation entity.

    Checks multiple candidate value column names — different YAML slot names
    produce different column names in the output TSV.
    """
    variables: dict[str, dict] = {}

    if "observation_type" not in df.columns:
        return variables

    for obs_type, group in df.groupby("observation_type", dropna=False):
        key = str(obs_type) if pd.notna(obs_type) else "MISSING_OBS_TYPE"

        value_col: str | None = None
        for candidate in ["value_enum", "value_coded", "value_as_string", "value_as_concept_name"]:
            if candidate in group.columns and group[candidate].notna().any():
                value_col = candidate
                break

        if value_col:
            summary = categorical_stats(group[value_col])
        else:
            summary = {"type": "categorical", "n_total": int(len(group)), "n_valid": 0}

        summary["entity"] = "Observation"
        summary["observation_type"] = key
        variables[f"observation_{key}"] = summary

    return variables


def process_measurement_observation_sets(
    df: pd.DataFrame,
    visit_id_to_label: dict[str, str],
    by_visit: bool = False,
    diagnostics_out: dict | None = None,
) -> dict[str, dict]:
    """Extract per-observation_type summaries from MeasurementObservationSet entity.

    dm-bip stores nested MeasurementObservation objects in the 'observations'
    column as a stringified list (JSON or Python repr). This function parses
    each row's list, explodes it, and computes per-observation_type stats.

    Args:
        df: MeasurementObservationSet DataFrame.
        visit_id_to_label: UUID-to-label map from Visit.tsv. Applied to the
            'associated_visit' column on the outer (set-level) DataFrame before
            propagating visit labels to exploded sub-observations.
        by_visit: If True, include per-visit breakdowns.
    """
    variables: dict[str, dict] = {}

    if "observations" not in df.columns:
        return variables

    # Resolve visit UUIDs on the outer DataFrame before exploding
    if "associated_visit" in df.columns:
        df = df.copy()
        df["associated_visit"] = resolve_visit_series(df["associated_visit"], visit_id_to_label)

    rows: list[dict] = []
    parse_errors = 0

    for idx, raw in enumerate(df["observations"]):
        if pd.isna(raw) or not str(raw).strip():
            continue

        obs_list = None
        raw_str = str(raw).strip()

        # Strategy 1: JSON with double quotes
        try:
            parsed = json.loads(raw_str)
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
            obs_list = parsed
        except (json.JSONDecodeError, ValueError):
            pass

        # Strategy 2: Python repr with single quotes
        if obs_list is None:
            try:
                obs_list = ast.literal_eval(raw_str)
            except (ValueError, SyntaxError):
                pass

        if obs_list is None:
            parse_errors += 1
            continue

        if isinstance(obs_list, dict):
            obs_list = [obs_list]

        if not isinstance(obs_list, list):
            parse_errors += 1
            continue

        visit_val = (
            df["associated_visit"].iloc[idx]
            if "associated_visit" in df.columns
            else None
        )

        for obs in obs_list:
            if not isinstance(obs, dict):
                continue
            obs_type = obs.get("observation_type")
            if not obs_type:
                continue
            # Normalize tuple-form observation_type — dm-bip occasionally stores
            # these as Python singleton tuples: ('OMOP:4152194',) -> OMOP:4152194
            if isinstance(obs_type, (list, tuple)):
                obs_type = obs_type[0] if obs_type else None
            elif isinstance(obs_type, str) and "(" in obs_type:
                _t = re.match(r"^\(\s*['\"]?([^'\"()]+?)['\"]?\s*,?\s*\)$", obs_type.strip())
                if _t:
                    obs_type = _t.group(1)
            if not obs_type:
                continue
            vq = obs.get("value_quantity", {})
            value = vq.get("value_decimal") if isinstance(vq, dict) else None
            method = obs.get("method_type")
            rows.append(
                {
                    "observation_type": str(obs_type),
                    "method_type": str(method) if method else None,
                    "value_decimal": value,
                    "associated_visit": visit_val,
                }
            )

    if parse_errors:
        print(f"    WARNING: MeasurementObservationSet — {parse_errors} rows could not be parsed")
    if diagnostics_out is not None:
        diagnostics_out["measurement_observation_set_parse_errors"] = parse_errors
        diagnostics_out["measurement_observation_set_rows_examined"] = int(len(df))

    if not rows:
        return variables

    exploded = pd.DataFrame(rows)
    has_method = exploded["method_type"].notna().any()
    group_cols = ["observation_type", "method_type"] if has_method else ["observation_type"]

    for group_key, group in exploded.groupby(group_cols, dropna=False):
        if has_method:
            obs_type_val, method_val = group_key
        else:
            obs_type_val = group_key
            method_val = None

        obs_type_str = str(obs_type_val) if pd.notna(obs_type_val) else "MISSING_OBS_TYPE"
        method_str = (
            str(method_val)
            if method_val and pd.notna(method_val) and str(method_val) not in ("None", "nan")
            else None
        )

        harmonized_key = (
            f"measurement_{obs_type_str}|{method_str}"
            if method_str
            else f"measurement_{obs_type_str}"
        )

        summary = continuous_stats(group["value_decimal"])
        summary["entity"] = "MeasurementObservationSet"
        summary["observation_type"] = obs_type_str
        if method_str:
            summary["method_type"] = method_str

        if by_visit and "associated_visit" in group.columns:
            by_visit_stats: dict[str, dict] = {}
            for visit_val, vgroup in group.groupby("associated_visit", dropna=False):
                vlabel = str(visit_val) if pd.notna(visit_val) else "_MISSING_VISIT"
                by_visit_stats[vlabel] = continuous_stats(vgroup["value_decimal"])
            summary["by_visit"] = by_visit_stats

        variables[harmonized_key] = summary

    return variables


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Summarize dm-bip harmonized output TSVs for one cohort.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--cohort", required=True, metavar="NAME",
                   help="Cohort name (e.g. SPIROMICS).")

    src_grp = p.add_mutually_exclusive_group()
    src_grp.add_argument("--harmonized-root", metavar="DIR", default=None,
                         help="Root dir containing DMC_* run directories (auto-discover). "
                              "Defaults to . (current directory) if omitted.")
    src_grp.add_argument("--mapped-data-dirs", nargs="+", metavar="DIR",
                         help="Explicit list of mapped-data/ directories.")

    p.add_argument("--by-visit", action="store_true",
                   help="Include per-visit breakdowns in variable summaries.")

    p.add_argument("--output-dir", metavar="DIR", default=None,
                   help="Output directory. Defaults to <harmonized-root>/dataqc-runs/.")
    p.add_argument("--output", metavar="FILE",
                   help="Override output JSON filename.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    cohort = args.cohort.upper()
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Resolve mapped-data directories
    if args.mapped_data_dirs:
        mapped_dirs = [Path(d) for d in args.mapped_data_dirs]
        resolved_root = mapped_dirs[0].parent  # best-effort for output-dir default
    else:
        # Default harmonized-root to current directory when not specified
        root = Path(args.harmonized_root) if args.harmonized_root else Path(".")
        if not root.exists():
            print(
                f"ERROR: harmonized root does not exist: {root}  "
                f"(pass --harmonized-root DIR or --mapped-data-dirs DIR [DIR ...])"
            )
            sys.exit(1)
        mapped_dirs = discover_mapped_data_dirs(root, cohort)
        if not mapped_dirs:
            print(f"ERROR: No mapped-data/ directories found under {root}")
            sys.exit(1)
        resolved_root = root

    # Default output-dir to <resolved_root>/dataqc-runs/
    output_dir = Path(args.output_dir) if args.output_dir else (resolved_root / "dataqc-runs")
    output_dir.mkdir(parents=True, exist_ok=True)

    base_stem = f"{cohort.lower()}_harmonized_{run_ts}"
    output_path = Path(args.output) if args.output else output_dir / f"{base_stem}.json"
    log_path = output_dir / f"{base_stem}.log"

    tee = _Tee(log_path)

    print("=" * 60)
    print(f"  HV-DataQC Harmonized Extractor: {cohort}")
    print("=" * 60)
    print(f"  Run timestamp : {run_ts}")
    print(f"  Output JSON   : {output_path}")
    print(f"  Log file      : {log_path}")
    print(f"  mapped-data dirs ({len(mapped_dirs)}):")
    for d in mapped_dirs:
        print(f"    {d}")
    for d in mapped_dirs:
        if not d.exists():
            print(f"  WARNING: directory not found: {d}")
    print()

    variables: dict[str, dict] = {}
    datasets_loaded: list[str] = []
    entity_counts: dict[str, int] = {}
    rows_per_visit: dict[str, int] = {}
    participant_count_candidates: dict[str, int] = {}
    extraction_warnings: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # 1. Visit — MUST be loaded first to build UUID→label map
    # ------------------------------------------------------------------
    print("  [Visit] Loading (required first for UUID resolution)...")
    visit_df = load_entity(mapped_dirs, "Visit")
    visit_id_to_label: dict[str, str] = {}

    if visit_df is not None:
        datasets_loaded.append("Visit")
        entity_counts["Visit"] = len(visit_df)
        visit_id_to_label = build_visit_id_to_label(visit_df)
        print(f"    Total: {len(visit_df):,} rows | UUID map: {len(visit_id_to_label)} entries")

        # Build rows_per_visit from Visit entity
        visit_cat_col = (
            "name" if "name" in visit_df.columns
            else "visit_type" if "visit_type" in visit_df.columns
            else "visit_category" if "visit_category" in visit_df.columns
            else None
        )
        if visit_cat_col:
            for vt, cnt in visit_df[visit_cat_col].value_counts(dropna=False).items():
                rows_per_visit[str(vt) if pd.notna(vt) else "_MISSING"] = int(cnt)
    else:
        print("    Not found — by-visit UUID resolution unavailable")
    print()

    # ------------------------------------------------------------------
    # 2. Demography
    # ------------------------------------------------------------------
    print("  [Demography] Loading...")
    dem_df = load_entity(mapped_dirs, "Demography")
    n_participants = 0
    if dem_df is not None:
        datasets_loaded.append("Demography")
        entity_counts["Demography"] = len(dem_df)
        variables.update(process_demography(dem_df))
        n_participants = (
            int(dem_df["associated_participant"].nunique())
            if "associated_participant" in dem_df.columns
            else len(dem_df)
        )
        participant_count_candidates["Demography"] = n_participants
        print(f"    Total: {len(dem_df):,} rows | {n_participants:,} unique participants")
    else:
        print("    Not found")
    print()

    # ------------------------------------------------------------------
    # 3. MeasurementObservation (standalone: bdy_hgt, bdy_wgt, bmi, hrt_rt)
    # ------------------------------------------------------------------
    print("  [MeasurementObservation] Loading...")
    meas_df = load_entity(mapped_dirs, "MeasurementObservation")
    if meas_df is not None:
        datasets_loaded.append("MeasurementObservation")
        entity_counts["MeasurementObservation"] = len(meas_df)
        participant_count_candidates["MeasurementObservation"] = participant_count_from_entity(
            meas_df, ("associated_participant", "participant", "participant_id")
        )
        mo_vars = process_measurements(meas_df, visit_id_to_label, args.by_visit)
        variables.update(mo_vars)
        n_types = (
            int(meas_df["observation_type"].nunique()) if "observation_type" in meas_df.columns else 0
        )
        print(f"    Observation types ({n_types}):")
        for key in sorted(mo_vars):
            v = mo_vars[key]
            print(f"      {v.get('observation_type', key)}: "
                  f"{v.get('n_total', 0):,} rows, n_valid={v.get('n_valid', 0):,}")
    else:
        print("    Not found")
    print()

    # ------------------------------------------------------------------
    # 4. MeasurementObservationSet (blood_pressure, spirometry_*)
    # ------------------------------------------------------------------
    print("  [MeasurementObservationSet] Loading...")
    meas_set_df = load_entity(mapped_dirs, "MeasurementObservationSet")
    if meas_set_df is not None:
        datasets_loaded.append("MeasurementObservationSet")
        entity_counts["MeasurementObservationSet"] = len(meas_set_df)
        participant_count_candidates["MeasurementObservationSet"] = participant_count_from_entity(
            meas_set_df, ("associated_participant", "participant", "participant_id")
        )
        mos_vars = process_measurement_observation_sets(
            meas_set_df, visit_id_to_label, args.by_visit, diagnostics_out=extraction_warnings
        )
        variables.update(mos_vars)
        print(f"    Total: {len(meas_set_df):,} rows | {len(mos_vars)} observation types extracted")
        for key in sorted(mos_vars):
            v = mos_vars[key]
            print(f"      {v.get('observation_type', key)}: "
                  f"n_valid={v.get('n_valid', 0):,}, mean={v.get('mean')}")
    else:
        print("    Not found")
    print()

    # ------------------------------------------------------------------
    # 5. Condition
    # ------------------------------------------------------------------
    print("  [Condition] Loading...")
    cond_df = load_entity(mapped_dirs, "Condition")
    if cond_df is not None:
        datasets_loaded.append("Condition")
        entity_counts["Condition"] = len(cond_df)
        participant_count_candidates["Condition"] = participant_count_from_entity(
            cond_df, ("associated_participant", "participant", "participant_id")
        )
        cond_vars = process_conditions(cond_df, visit_id_to_label, args.by_visit)
        variables.update(cond_vars)
        print(f"    Total: {len(cond_df):,} rows | {len(cond_vars)} condition concepts")
    else:
        print("    Not found")
    print()

    # ------------------------------------------------------------------
    # 6. Observation (smoking, etc.)
    # ------------------------------------------------------------------
    print("  [Observation] Loading...")
    obs_df = load_entity(mapped_dirs, "Observation")
    if obs_df is not None:
        datasets_loaded.append("Observation")
        entity_counts["Observation"] = len(obs_df)
        participant_count_candidates["Observation"] = participant_count_from_entity(
            obs_df, ("associated_participant", "participant", "participant_id")
        )
        obs_vars = process_observations(obs_df)
        variables.update(obs_vars)
        print(f"    Total: {len(obs_df):,} rows | {len(obs_vars)} observation types")
    else:
        print("    Not found")
    print()

    # ------------------------------------------------------------------
    # 7. Participant / Person (for entity count tracking only)
    # ------------------------------------------------------------------
    for entity in ["Participant", "Person"]:
        ent_df = load_entity(mapped_dirs, entity)
        if ent_df is not None:
            datasets_loaded.append(entity)
            entity_counts[entity] = len(ent_df)
            participant_count_candidates[entity] = participant_count_from_entity(
                ent_df, ("id", "associated_participant", "participant", "participant_id")
            ) or len(ent_df)

    if n_participants == 0:
        for source in ("Participant", "Person", "MeasurementObservation", "MeasurementObservationSet", "Condition", "Observation"):
            if participant_count_candidates.get(source):
                n_participants = participant_count_candidates[source]
                print(f"  Participant count fallback from {source}: {n_participants:,}")
                break

    # ------------------------------------------------------------------
    # 8. Write output JSON
    # ------------------------------------------------------------------
    output_doc: dict = {
        "metadata": {
            "source": "bdc_dmbip",
            "cohort": cohort,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "run_timestamp": run_ts,
            "mapped_data_dirs": [str(d) for d in mapped_dirs],
            "by_visit": args.by_visit,
            "uuid_map_size": len(visit_id_to_label),
            "participant_count_candidates": participant_count_candidates,
            "extraction_warnings": extraction_warnings,
        },
        "total_participants": n_participants,
        "total_rows": sum(entity_counts.values()),
        "datasets_loaded": datasets_loaded,
        "entity_counts": entity_counts,
        "rows_per_visit": rows_per_visit,
        "variables": variables,
    }

    _write_json_atomic(output_path, output_doc)

    print()
    print("=" * 60)
    print(f"  Complete")
    print(f"    JSON  : {output_path}")
    print(f"    Log   : {log_path}")
    print(f"    {len(variables)} variables | {n_participants:,} participants")
    print(f"    Entities loaded: {', '.join(datasets_loaded)}")
    print("  AGGREGATE SUMMARIES ONLY -- safe to export from enclave")
    print("=" * 60)

    tee.close()


if __name__ == "__main__":
    main()
