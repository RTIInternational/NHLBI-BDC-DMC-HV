"""
extract_harmonized_summaries.py — HV-DataQC Component 2

Summarize dm-bip harmonized output TSV files for one cohort and export an
aggregate-only JSON artifact compatible with hv_dataqc.compare.

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
import yaml

from hv_dataqc.hv_dataqc_common import (
    categorical_stats,
    continuous_stats,
    write_json_atomic,
)

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

DEMOGRAPHY_COLUMNS: list[tuple[str, str]] = [
    ("sex", "sex"),
    ("race", "race"),
    ("ethnicity", "ethnicity"),
]

_DEFAULT_EXTRACT_CONFIG = Path(__file__).resolve().parent / "config" / "harmonized_extract.yaml"


def load_harmonized_extract_config(path: Path | None = None) -> dict[str, Any]:
    """Load optional harmonized-extractor config for entity files and demography columns."""
    effective_path = path or _DEFAULT_EXTRACT_CONFIG
    if not effective_path.exists():
        return {}
    try:
        with effective_path.open("r", encoding="utf-8") as fh:
            config = yaml.safe_load(fh) or {}
        return config if isinstance(config, dict) else {}
    except yaml.YAMLError as exc:
        print(f"WARNING: Malformed harmonized extractor config {effective_path}: {exc}")
        return {}


def apply_harmonized_extract_config(config: dict[str, Any]) -> None:
    """Apply entity-file and demography-column overrides from config."""
    entity_files = config.get("entity_files")
    if isinstance(entity_files, dict):
        for entity, filename in entity_files.items():
            if entity and filename:
                ENTITY_FILES[str(entity)] = str(filename)

    demography_columns = config.get("demography_columns")
    if isinstance(demography_columns, dict):
        DEMOGRAPHY_COLUMNS[:] = [(str(col), str(label)) for col, label in demography_columns.items()]
    elif isinstance(demography_columns, list):
        parsed: list[tuple[str, str]] = []
        for item in demography_columns:
            if isinstance(item, dict) and item.get("column"):
                parsed.append((str(item["column"]), str(item.get("label", item["column"]))))
        if parsed:
            DEMOGRAPHY_COLUMNS[:] = parsed


def _write_json_atomic(path: Path, data: Any) -> None:
    """Write strict JSON via temp file then atomic replace."""
    write_json_atomic(path, data, ensure_ascii=False, default=str)


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

def load_entity(
    mapped_data_dirs: list[Path],
    entity: str,
    cg_status: dict[str, dict] | None = None,
) -> pd.DataFrame | None:
    """Load and concatenate a specific entity TSV from all mapped-data dirs.

    Args:
        mapped_data_dirs: List of mapped-data/ directories to search.
        entity: Entity name key from ENTITY_FILES (e.g. "Visit").
        cg_status: Optional dict populated in-place with per-consent-group file
            status for this entity.  Keys are consent-group labels (the
            ``DMC_…`` directory name two levels above each mapped-data dir).
            Values are status dicts with one of three shapes::

                {"status": "loaded", "rows": N}
                {"status": "empty",  "error": "<exception text>"}
                {"status": "missing"}
    """
    filename = ENTITY_FILES.get(entity)
    if not filename:
        return None

    frames: list[pd.DataFrame] = []
    found_files: list[tuple[str, int]] = []

    for d in mapped_data_dirs:
        label = d.parent.parent.name
        tsv = d / filename
        if not tsv.exists():
            if cg_status is not None:
                cg_status[label] = {"status": "missing"}
            continue
        try:
            df = pd.read_csv(tsv, sep="\t", low_memory=False)
            df.columns = df.columns.astype(str).str.strip()
            frames.append(df)
            found_files.append((label, len(df)))
            if cg_status is not None:
                cg_status[label] = {"status": "loaded", "rows": len(df)}
        except Exception as exc:
            print(f"      WARNING: Could not read {tsv}: {exc}")
            if cg_status is not None:
                cg_status[label] = {"status": "empty", "error": str(exc)}

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

# ---------------------------------------------------------------------------
# Entity processors
# ---------------------------------------------------------------------------

def process_demography(df: pd.DataFrame) -> dict[str, dict]:
    """Extract sex, race, ethnicity summaries from Demography entity."""
    variables: dict[str, dict] = {}
    for col, label in DEMOGRAPHY_COLUMNS:
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

    DECIMAL_COL         = "value_quantity__value_decimal"
    INTEGER_COL         = "value_quantity__value_integer"
    CODED_COL           = "value_quantity__value_coded"
    Q_VALUE_CONCEPT_COL = "value_quantity__value_concept"  # nested Quantity via object_derivations
    VALUE_CONCEPT_COL   = "value_concept"                  # flat (non-nested) fallback
    FLAT_CATEGORICAL_CANDIDATES = [
        VALUE_CONCEPT_COL,
        "value_enum",
        "value_coded",
        "value_as_string",
        "value_as_concept_name",
        "measurement_status",
        "observation_status",
    ]

    obs_cols = [
        c for c in df.columns
        if "value" in c.lower()
        or c in ("observation_type", "age_at_observation", "measurement_status", "observation_status")
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

        has_decimal         = DECIMAL_COL         in df.columns and group[DECIMAL_COL].notna().any()
        has_integer         = INTEGER_COL         in df.columns and group[INTEGER_COL].notna().any()
        has_coded           = CODED_COL           in df.columns and group[CODED_COL].notna().any()
        has_q_value_concept = Q_VALUE_CONCEPT_COL in df.columns and group[Q_VALUE_CONCEPT_COL].notna().any()

        flat_col: str | None = None
        for candidate in FLAT_CATEGORICAL_CANDIDATES:
            if candidate in group.columns and group[candidate].notna().any():
                flat_col = candidate
                break

        if has_decimal or has_integer:
            value_col = DECIMAL_COL if has_decimal else INTEGER_COL
            summary = continuous_stats(group[value_col])
        elif has_coded:
            summary = categorical_stats(group[CODED_COL])
        elif has_q_value_concept:
            summary = categorical_stats(group[Q_VALUE_CONCEPT_COL])
        elif flat_col:
            summary = categorical_stats(group[flat_col])
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
                elif has_q_value_concept:
                    by_visit_stats[vlabel] = categorical_stats(vgroup[Q_VALUE_CONCEPT_COL])
                elif flat_col:
                    by_visit_stats[vlabel] = categorical_stats(vgroup[flat_col])
            summary["by_visit"] = by_visit_stats

        variables[f"measurement_{key}"] = summary

    return variables


def process_conditions(
    df: pd.DataFrame,
    visit_id_to_label: dict[str, str],
    by_visit: bool = False,
    diagnostics_out: dict | None = None,
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

    if status_col is None:
        msg = (
            "Condition.tsv has no condition_status column; condition summaries "
            "count rows as valid but mark condition_status_missing_assumption=True"
        )
        print(f"    WARNING: {msg}")
        if diagnostics_out is not None:
            diagnostics_out["condition_status_missing"] = True
            diagnostics_out["condition_status_missing_rows"] = int(len(df))
            diagnostics_out["condition_status_missing_message"] = msg

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
                "condition_status_missing_assumption": True,
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
    produce different column names in the output TSV. Includes nested
    Quantity columns (value_quantity__*) emitted by dm-bip when the YAML
    uses an object_derivation for value_quantity (e.g., fam_income.yaml).
    """
    variables: dict[str, dict] = {}

    if "observation_type" not in df.columns:
        return variables

    # Nested Quantity columns produced by dm-bip when value_quantity is an
    # object derivation. Mirror the MeasurementObservation handler so that
    # Observation rows whose value lives inside Quantity are not misreported
    # as n_valid=0.
    DECIMAL_COL       = "value_quantity__value_decimal"
    INTEGER_COL       = "value_quantity__value_integer"
    CODED_COL         = "value_quantity__value_coded"
    Q_VALUE_CONCEPT   = "value_quantity__value_concept"

    # Flat (non-nested) candidate columns, in priority order.
    FLAT_CATEGORICAL_CANDIDATES = [
        "value_enum",
        "value_coded",
        "value_concept",
        "value_as_string",
        "value_as_concept_name",
    ]

    for obs_type, group in df.groupby("observation_type", dropna=False):
        key = str(obs_type) if pd.notna(obs_type) else "MISSING_OBS_TYPE"

        has_decimal       = DECIMAL_COL     in group.columns and group[DECIMAL_COL].notna().any()
        has_integer       = INTEGER_COL     in group.columns and group[INTEGER_COL].notna().any()
        has_q_coded       = CODED_COL       in group.columns and group[CODED_COL].notna().any()
        has_q_concept     = Q_VALUE_CONCEPT in group.columns and group[Q_VALUE_CONCEPT].notna().any()

        flat_col: str | None = None
        for candidate in FLAT_CATEGORICAL_CANDIDATES:
            if candidate in group.columns and group[candidate].notna().any():
                flat_col = candidate
                break

        if has_decimal or has_integer:
            value_col = DECIMAL_COL if has_decimal else INTEGER_COL
            summary = continuous_stats(group[value_col])
        elif has_q_coded:
            summary = categorical_stats(group[CODED_COL])
        elif has_q_concept:
            summary = categorical_stats(group[Q_VALUE_CONCEPT])
        elif flat_col:
            summary = categorical_stats(group[flat_col])
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

    DECIMAL_FIELD = "value_decimal"
    INTEGER_FIELD = "value_integer"
    CODED_FIELD = "value_coded"
    CONCEPT_FIELD = "value_concept"

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
            if not isinstance(vq, dict):
                vq = {}
            method = obs.get("method_type")
            rows.append(
                {
                    "observation_type": str(obs_type),
                    "method_type": str(method) if method else None,
                    DECIMAL_FIELD: vq.get(DECIMAL_FIELD),
                    INTEGER_FIELD: vq.get(INTEGER_FIELD),
                    CODED_FIELD: vq.get(CODED_FIELD),
                    CONCEPT_FIELD: vq.get(CONCEPT_FIELD),
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
            if isinstance(obs_type_val, tuple):
                obs_type_val = obs_type_val[0] if obs_type_val else None

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

        has_decimal = group[DECIMAL_FIELD].notna().any()
        has_integer = group[INTEGER_FIELD].notna().any()
        has_coded = group[CODED_FIELD].notna().any()
        has_concept = group[CONCEPT_FIELD].notna().any()

        if has_decimal or has_integer:
            value_field = DECIMAL_FIELD if has_decimal else INTEGER_FIELD
            summary = continuous_stats(group[value_field])
        elif has_coded:
            value_field = CODED_FIELD
            summary = categorical_stats(group[value_field])
        elif has_concept:
            value_field = CONCEPT_FIELD
            summary = categorical_stats(group[value_field])
        else:
            value_field = DECIMAL_FIELD
            summary = {
                "type": "unknown",
                "n_total": int(len(group)),
                "n_valid": 0,
                "n_missing": int(len(group)),
            }
        summary["entity"] = "MeasurementObservationSet"
        summary["observation_type"] = obs_type_str
        if method_str:
            summary["method_type"] = method_str

        if by_visit and "associated_visit" in group.columns:
            by_visit_stats: dict[str, dict] = {}
            for visit_val, vgroup in group.groupby("associated_visit", dropna=False):
                vlabel = str(visit_val) if pd.notna(visit_val) else "_MISSING_VISIT"
                if has_decimal or has_integer:
                    by_visit_stats[vlabel] = continuous_stats(vgroup[value_field])
                elif has_coded or has_concept:
                    by_visit_stats[vlabel] = categorical_stats(vgroup[value_field])
                else:
                    by_visit_stats[vlabel] = {
                        "type": "unknown",
                        "n_total": int(len(vgroup)),
                        "n_valid": 0,
                        "n_missing": int(len(vgroup)),
                    }
            summary["by_visit"] = by_visit_stats

        variables[harmonized_key] = summary

    return variables


def _distribution_count(info: Any) -> int:
    if isinstance(info, dict):
        return int(info.get("n", info.get("count", 0)) or 0)
    try:
        return int(info)
    except (TypeError, ValueError):
        return 0


def _merge_variable_summary(existing: dict, incoming: dict) -> dict:
    """Merge duplicate harmonized variable summaries instead of overwriting."""
    existing_type = existing.get("type")
    incoming_type = incoming.get("type")
    entities = sorted({str(v) for v in (existing.get("_merged_entities") or [existing.get("entity")]) + [incoming.get("entity")] if v})

    if existing_type == incoming_type == "continuous":
        n1 = int(existing.get("n_valid", 0) or 0)
        n2 = int(incoming.get("n_valid", 0) or 0)
        total_valid = n1 + n2
        n_total = int(existing.get("n_total", 0) or 0) + int(incoming.get("n_total", 0) or 0)
        n_missing = int(existing.get("n_missing", 0) or 0) + int(incoming.get("n_missing", 0) or 0)
        mean1 = existing.get("mean")
        mean2 = incoming.get("mean")
        merged = dict(existing)
        merged.update({"n_total": n_total, "n_valid": total_valid, "n_missing": n_missing})
        merged["pct_missing"] = round(n_missing / n_total * 100, 2) if n_total else 0.0
        if total_valid and mean1 is not None and mean2 is not None:
            pooled_mean = (n1 * float(mean1) + n2 * float(mean2)) / total_valid
            merged["mean"] = round(pooled_mean, 6)
            if total_valid > 1:
                within = 0.0
                if existing.get("sd") is not None and n1 > 1:
                    within += (n1 - 1) * float(existing["sd"]) ** 2
                if incoming.get("sd") is not None and n2 > 1:
                    within += (n2 - 1) * float(incoming["sd"]) ** 2
                between = 0.0
                if mean1 is not None:
                    between += n1 * (float(mean1) - pooled_mean) ** 2
                if mean2 is not None:
                    between += n2 * (float(mean2) - pooled_mean) ** 2
                merged["sd"] = round(math.sqrt((within + between) / (total_valid - 1)), 6)
        mins = [v for v in (existing.get("min"), incoming.get("min")) if v is not None]
        maxs = [v for v in (existing.get("max"), incoming.get("max")) if v is not None]
        if mins:
            merged["min"] = min(float(v) for v in mins)
        if maxs:
            merged["max"] = max(float(v) for v in maxs)
    elif existing_type == incoming_type == "categorical":
        merged = dict(existing)
        merged_dist: dict[str, dict] = {}
        for summary in (existing, incoming):
            dist = summary.get("distribution") or summary.get("values") or {}
            if not isinstance(dist, dict):
                continue
            for code, info in dist.items():
                slot = merged_dist.setdefault(str(code), {"n": 0})
                slot["n"] += _distribution_count(info)
        total_valid = sum(v["n"] for v in merged_dist.values())
        n_total = int(existing.get("n_total", 0) or 0) + int(incoming.get("n_total", 0) or 0)
        n_missing = int(existing.get("n_missing", 0) or 0) + int(incoming.get("n_missing", 0) or 0)
        for stats in merged_dist.values():
            stats["pct"] = round(stats["n"] / total_valid * 100, 2) if total_valid else 0.0
        merged.update({
            "distribution": merged_dist,
            "n_total": n_total,
            "n_valid": total_valid,
            "n_missing": n_missing,
            "pct_missing": round(n_missing / n_total * 100, 2) if n_total else 0.0,
        })
    else:
        merged = dict(existing)
        merged.update({
            "type": "mixed",
            "n_total": int(existing.get("n_total", 0) or 0) + int(incoming.get("n_total", 0) or 0),
            "n_valid": int(existing.get("n_valid", 0) or 0) + int(incoming.get("n_valid", 0) or 0),
            "_merge_warning": f"duplicate key had incompatible types: {existing_type} and {incoming_type}",
        })
    merged["_merged_harmonized_key_collision"] = True
    merged["_merged_entities"] = entities
    return merged


def merge_variable_summaries(
    variables: dict[str, dict],
    incoming: dict[str, dict],
    diagnostics_out: dict | None = None,
) -> None:
    """Merge a batch of variable summaries into *variables* without silent overwrites."""
    collisions: list[str] = []
    for key, summary in incoming.items():
        if key in variables:
            collisions.append(key)
            variables[key] = _merge_variable_summary(variables[key], summary)
        else:
            variables[key] = summary
    if collisions and diagnostics_out is not None:
        existing = diagnostics_out.setdefault("harmonized_variable_key_collisions", [])
        existing.extend(collisions)


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
    p.add_argument("--extract-config", metavar="YAML",
                   help=f"Harmonized extractor config YAML (default: {_DEFAULT_EXTRACT_CONFIG})")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    cohort = args.cohort.upper()
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    extract_config_path = Path(args.extract_config) if args.extract_config else _DEFAULT_EXTRACT_CONFIG
    extract_config = load_harmonized_extract_config(extract_config_path)
    apply_harmonized_extract_config(extract_config)

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

    # Create a timestamped run subdirectory and a latest_harmonized symlink
    run_dir = output_dir / f"harmonized_{run_ts}"
    run_dir.mkdir(exist_ok=True)
    latest_link = output_dir / "latest_harmonized"
    if latest_link.is_dir() and not latest_link.is_symlink():
        import shutil
        shutil.rmtree(latest_link)
    else:
        latest_link.unlink(missing_ok=True)
    latest_link.symlink_to(run_dir.name)
    print(f"Output dir: {run_dir}")
    print(f"Symlink:    {latest_link} -> {run_dir.name}")

    base_stem = f"{cohort.lower()}_harmonized_{run_ts}"
    # `--output` is treated as a filename only and is always placed inside
    # `run_dir`, mirroring the source extractor's behaviour. This prevents
    # `--output foo.json` from silently writing outside the run directory.
    output_path = (run_dir / Path(args.output).name) if args.output else run_dir / f"{base_stem}.json"
    log_path = run_dir / f"{base_stem}.log"

    tee = _Tee(log_path)
    try:
        _run_extract(
            args=args,
            cohort=cohort,
            run_ts=run_ts,
            mapped_dirs=mapped_dirs,
            output_path=output_path,
            log_path=log_path,
            extract_config=extract_config,
            extract_config_path=extract_config_path,
        )
    finally:
        # Ensure stdout is restored and the log file is closed even if an
        # exception or sys.exit() interrupts extraction.
        tee.close()


def _run_extract(
    *,
    args: argparse.Namespace,
    cohort: str,
    run_ts: str,
    mapped_dirs: list[Path],
    output_path: Path,
    log_path: Path,
    extract_config: dict | None,
    extract_config_path: Path,
) -> None:
    print("=" * 60)
    print(f"  HV-DataQC Harmonized Extractor: {cohort}")
    print("=" * 60)
    print(f"  Run timestamp : {run_ts}")
    print(f"  Output JSON   : {output_path}")
    print(f"  Log file      : {log_path}")
    print(f"  Extract config: {extract_config_path if extract_config else 'built-in defaults'}")
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
    # Per-consent-group file status: {cg_label: {entity_name: {status, rows?, error?}}}
    consent_group_file_status: dict[str, dict[str, dict]] = {}

    def _load(entity_name: str) -> pd.DataFrame | None:
        """Load an entity and record per-consent-group file status."""
        _cg: dict[str, dict] = {}
        df = load_entity(mapped_dirs, entity_name, cg_status=_cg)
        for lbl, st in _cg.items():
            consent_group_file_status.setdefault(lbl, {})[entity_name] = st
        return df

    # ------------------------------------------------------------------
    # 1. Visit — MUST be loaded first to build UUID→label map
    # ------------------------------------------------------------------
    print("  [Visit] Loading (required first for UUID resolution)...")
    visit_df = _load("Visit")
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
    dem_df = _load("Demography")
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
    meas_df = _load("MeasurementObservation")
    if meas_df is not None:
        datasets_loaded.append("MeasurementObservation")
        entity_counts["MeasurementObservation"] = len(meas_df)
        participant_count_candidates["MeasurementObservation"] = participant_count_from_entity(
            meas_df, ("associated_participant", "participant", "participant_id")
        )
        mo_vars = process_measurements(meas_df, visit_id_to_label, args.by_visit)
        merge_variable_summaries(variables, mo_vars, extraction_warnings)
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
    meas_set_df = _load("MeasurementObservationSet")
    if meas_set_df is not None:
        datasets_loaded.append("MeasurementObservationSet")
        entity_counts["MeasurementObservationSet"] = len(meas_set_df)
        participant_count_candidates["MeasurementObservationSet"] = participant_count_from_entity(
            meas_set_df, ("associated_participant", "participant", "participant_id")
        )
        mos_vars = process_measurement_observation_sets(
            meas_set_df, visit_id_to_label, args.by_visit, diagnostics_out=extraction_warnings
        )
        merge_variable_summaries(variables, mos_vars, extraction_warnings)
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
    cond_df = _load("Condition")
    if cond_df is not None:
        datasets_loaded.append("Condition")
        entity_counts["Condition"] = len(cond_df)
        participant_count_candidates["Condition"] = participant_count_from_entity(
            cond_df, ("associated_participant", "participant", "participant_id")
        )
        cond_vars = process_conditions(
            cond_df, visit_id_to_label, args.by_visit, diagnostics_out=extraction_warnings
        )
        variables.update(cond_vars)
        print(f"    Total: {len(cond_df):,} rows | {len(cond_vars)} condition concepts")
    else:
        print("    Not found")
    print()

    # ------------------------------------------------------------------
    # 6. Observation (smoking, etc.)
    # ------------------------------------------------------------------
    print("  [Observation] Loading...")
    obs_df = _load("Observation")
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
        ent_df = _load(entity)
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
            "extract_config": {
                "entity_files": ENTITY_FILES,
                "demography_columns": dict(DEMOGRAPHY_COLUMNS),
            },
        },
        "total_participants": n_participants,
        "total_rows": sum(entity_counts.values()),
        "datasets_loaded": datasets_loaded,
        "entity_counts": entity_counts,
        "rows_per_visit": rows_per_visit,
        "consent_group_file_status": consent_group_file_status,
        "variables": variables,
    }

    _write_json_atomic(output_path, output_doc)

    print()
    print("=" * 60)
    print("  Complete")
    print(f"    JSON  : {output_path}")
    print(f"    Log   : {log_path}")
    print(f"    {len(variables)} variables | {n_participants:,} participants")
    print(f"    Entities loaded: {', '.join(datasets_loaded)}")
    print("  AGGREGATE SUMMARIES ONLY -- safe to export from enclave")
    print("=" * 60)


if __name__ == "__main__":
    main()
