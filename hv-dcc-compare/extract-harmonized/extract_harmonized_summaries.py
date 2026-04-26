"""
extract_harmonized_summaries.py — Cross-cohort extraction from BDC dm-bip harmonized TSV output
(Part of hv-dcc-compare. Config maps live in config.py at repo root.)
====================================================================================
Reads BDC dm-bip TSV output files for any cohort, concatenates across consent groups,
normalizes OMOP/OBA concept IDs to common display labels, and writes a
**per-cohort aggregate-only JSON summary** (no individual-level data).

Processes ALL entity types: Demography, MeasurementObservation, Condition,
DrugExposure, Procedure, Observation.

Matches the output format of extract_topmed_summaries.py so that comparison scripts
can consume both JSON summaries side-by-side.

OUTPUT FORMAT (bdc_<cohort>_summary.json):
    JSON with:
      metadata           — source, input dirs, generation timestamp
      cohort             — cohort name and metadata
      total_participants — integer (from Demography deduplicated)
      datasets_loaded    — list of entity types successfully processed
      variables          — per-variable aggregate stats:
          categorical → {distribution: {label: {n, pct}}, n_missing, ...}
          continuous  → {n_valid, n_missing, mean, sd, median, q1, q3, min, max, ...}
      dq_flags           — data quality observations

    NO participant IDs or individual rows are written. Safe to export from enclave.

USAGE:
    # Simplest: auto-discover all consent groups from current directory
    python extract_harmonized_summaries.py --cohort HCHS

    # Auto-discover from a specific base directory
    python extract_harmonized_summaries.py --cohort WHI --base-dir /enclave/output/

    # Process multiple named cohorts in one run
    python extract_harmonized_summaries.py --cohorts ARIC CHS FHS WHI --base-dir /enclave/output/

    # Process ALL cohorts found under base-dir (no --cohort/--cohorts needed)
    python extract_harmonized_summaries.py --base-dir /enclave/output/

    # Explicit mapped-data dirs (overrides auto-discovery, single cohort only)
    python extract_harmonized_summaries.py \\
        --mapped-data-dirs \\
            ./DMC_parent-WHI_HMB-IRB_-phs000200-v12-p3-c1_WHI_Processed_20260322_141514/parent-WHI_HMB-IRB_-phs000200-v12-p3-c1_BDCHM/mapped-data \\
            ./DMC_parent-WHI_HMB-IRB-NPU_-phs000200-v12-p3-c2_WHI_Processed_20260322_173030/parent-WHI_HMB-IRB-NPU_-phs000200-v12-p3-c2_BDCHM/mapped-data \\
        --cohort WHI \\
        --output-dir ./comparison_output/
"""

from __future__ import annotations

import argparse
import glob
import io
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT CAPTURE
# ─────────────────────────────────────────────────────────────────────────────

class Tee:
    """Write to multiple streams simultaneously (screen + log file)."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, data: str) -> int:
        for s in self.streams:
            s.write(data)
            s.flush()
        return len(data)

    def flush(self) -> None:
        for s in self.streams:
            s.flush()

    def fileno(self) -> int:
        # Return the fd of the first real file stream (needed by some libs)
        for s in self.streams:
            if hasattr(s, 'fileno'):
                try:
                    return s.fileno()
                except (io.UnsupportedOperation, AttributeError):
                    continue
        raise io.UnsupportedOperation("fileno")

# ─────────────────────────────────────────────────────────────────────────────
# Import shared config (with inline fallback for standalone enclave use)
# ---------------------------------------------------------------------------
# Import shared config from hv-dcc-compare root (config.py)
# ---------------------------------------------------------------------------
# Add the hv-dcc-compare root to path so config.py is importable whether
# this script is run from the repo root or from within extract-harmonized/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    COHORTS,
    COHORT_FOLDER_TO_CANONICAL,
    COHORT_CANONICAL_TO_ALIASES,
    normalize_cohort_name,
    resolve_baseline_visits,
    BASELINE_VISIT_PREFS,
    SMOKING_VISIT_OVERRIDE,
    CONDITION_PROCEDURE_VISIT_OVERRIDE,
    BDC_MEASUREMENT_MAP,
    BDC_CONDITION_MAP,
    BDC_PROCEDURE_MAP,
    OMOP_SEX_MAP,
    OMOP_RACE_MAP,
    OMOP_ETHNICITY_MAP,
    SMOKING_OBSERVATION_TYPE,
    OMOP_SMOKING_MAP,
)

def _ci_glob_processed_dirs(base: Path, cohort: str) -> list[Path]:
    """Find DMC_*_{cohort}_Processed_* directories with case-insensitive cohort matching.

    Linux glob is case-sensitive, so 'DMC_*_COPDGENE_Processed_*' won't match
    'DMC_copdgene_phs000179_v7_r1_c1_COPDGene_Processed_...'.  This helper
    scans top-level entries and matches the cohort portion case-insensitively.
    """
    import re
    # Match: DMC_<anything>_{cohort}_Processed_<timestamp>
    pat = re.compile(
        rf"^DMC_.*_{re.escape(cohort)}_Processed_\d+", re.IGNORECASE
    )
    results = []
    try:
        for entry in sorted(base.iterdir()):
            if entry.is_dir() and pat.match(entry.name):
                results.append(entry)
    except OSError:
        pass
    return results


def discover_all_cohorts(base_dir: str | Path) -> list[str]:
    """Auto-discover all cohort names from DMC_*_Processed_* directories under base_dir.

    Uses the known cohort list from config (if available) to probe
    for matching directories.  Also scans for any unrecognized cohort directories
    by extracting the segment before '_Processed_' in folder names.

    Returns a sorted, deduplicated list of uppercase cohort names
    (e.g., ['ARIC', 'CHS', 'FHS', 'WHI']).
    """
    import re
    base = Path(base_dir)
    found: set[str] = set()

    # Phase 1: Check all known cohorts from config
    known_cohorts = list(COHORTS.keys()) if _HAS_CONFIG else [
        "ARIC", "CARDIA", "CHS", "COPDGENE", "FHS", "HCHS_SOL", "JHS", "MESA", "SPIROMICS", "WHI",
    ]
    for cohort in known_cohorts:
        if _ci_glob_processed_dirs(base, cohort):
            found.add(cohort.upper())
        else:
            # Try folder-name aliases (e.g. HCHS_SOL → try HCHS)
            for alias in COHORT_CANONICAL_TO_ALIASES.get(cohort.upper(), []):
                if _ci_glob_processed_dirs(base, alias):
                    found.add(cohort.upper())  # store canonical name
                    break

    # Phase 2: Scan for any DMC_*_Processed_* dirs not covered by known cohorts
    proc_pat = re.compile(r"^DMC_.*_Processed_\d+", re.IGNORECASE)
    try:
        for entry in sorted(base.iterdir()):
            if not entry.is_dir() or not proc_pat.match(entry.name):
                continue
            # Already matched by a known cohort (or its alias)?
            already = False
            for c in found:
                dirs = _ci_glob_processed_dirs(base, c)
                if dirs and entry in dirs:
                    already = True
                    break
                # Also check aliases
                for alias in COHORT_CANONICAL_TO_ALIASES.get(c, []):
                    dirs = _ci_glob_processed_dirs(base, alias)
                    if dirs and entry in dirs:
                        already = True
                        break
                if already:
                    break
            if already:
                continue
            # Extract candidate: segment(s) before _Processed_ after [-_]c\d+_
            m = re.search(r"[-_]c\d+_([A-Za-z][A-Za-z0-9_]*)_Processed_", entry.name,
                          re.IGNORECASE)
            if m:
                raw_name = m.group(1).upper()
                # Normalize to canonical config name if alias exists
                canonical = COHORT_FOLDER_TO_CANONICAL.get(raw_name, raw_name)
                found.add(canonical)
    except OSError:
        pass

    return sorted(found)


def discover_mapped_data_dirs(base_dir: str | Path, cohort: str) -> list[str]:
    """Auto-discover mapped-data directories for a cohort under base_dir.

    Searches for the dm-bip output folder pattern:
        DMC_*_{COHORT}_Processed_*/*_BDCHM/mapped-data/

    Uses case-insensitive matching on the cohort name so that mixed-case
    folder names (e.g. COPDGene) are found on case-sensitive file systems.
    Also tries known aliases (e.g. HCHS for HCHS_SOL).

    Returns sorted list of discovered mapped-data directory paths.
    """
    base = Path(base_dir)
    hits: list[Path] = []

    # Find top-level DMC_*_{cohort}_Processed_* dirs (case-insensitive)
    proc_dirs = _ci_glob_processed_dirs(base, cohort)
    # Also try aliases if no match on canonical name
    if not proc_dirs:
        for alias in COHORT_CANONICAL_TO_ALIASES.get(cohort.upper(), []):
            proc_dirs = _ci_glob_processed_dirs(base, alias)
            if proc_dirs:
                break

    # Look for *_BDCHM/mapped-data inside each processed dir
    for proc_dir in proc_dirs:
        for bdchm in sorted(proc_dir.glob("*_BDCHM")):
            mapped = bdchm / "mapped-data"
            if mapped.is_dir():
                hits.append(mapped)

    # Fallback: maybe mapped-data is missing — files directly in _BDCHM
    if not hits:
        for proc_dir in proc_dirs:
            for bdchm in sorted(proc_dir.glob("*_BDCHM")):
                if bdchm.is_dir() and list(bdchm.glob("*.tsv")):
                    hits.append(bdchm)

    return [str(h) for h in sorted(hits)]


# ─────────────────────────────────────────────────────────────────────────────
# TSV LOADING UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

def load_tsv_files(directories: list[str], glob_pattern: str) -> pd.DataFrame:
    """Glob for TSV files across directories, load and concatenate."""
    files: list[str] = []
    for d in directories:
        found = sorted(glob.glob(str(Path(d) / glob_pattern)))
        files.extend(found)

    if not files:
        return pd.DataFrame()

    print(f"    Found {len(files)} file(s) matching '{glob_pattern}':")
    dfs = []
    for f in files:
        try:
            chunk = pd.read_csv(f, sep="\t", low_memory=False)
            consent_label = Path(f).parts[-4] if len(Path(f).parts) >= 4 else Path(f).parent.name
            chunk["_consent_group"] = consent_label
            dfs.append(chunk)
            print(f"      [{consent_label}] {Path(f).name}: {len(chunk):,} rows")
        except Exception as e:
            print(f"      ERROR loading {f}: {e}", file=sys.stderr)

    if not dfs:
        return pd.DataFrame()

    return pd.concat(dfs, ignore_index=True)


def _strip_list_wrapper(raw: str) -> str:
    """Strip Python list-literal wrapper from dm-bip output values.
    dm-bip often writes OMOP IDs as "['OMOP:8527']" instead of "OMOP:8527".
    """
    s = raw.strip()
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if inner.startswith("'") and inner.endswith("'") and inner.count("'") == 2:
            return inner[1:-1]
        if inner.startswith('"') and inner.endswith('"') and inner.count('"') == 2:
            return inner[1:-1]
    return s


def clean_concept(series: pd.Series) -> pd.Series:
    """Clean a concept ID column: strip list wrappers and whitespace."""
    return series.map(
        lambda x: _strip_list_wrapper(str(x).strip()) if pd.notna(x) else None
    )


# ─────────────────────────────────────────────────────────────────────────────
# AGGREGATE STATISTICS
# ─────────────────────────────────────────────────────────────────────────────

def categorical_stats(
    series: pd.Series,
    value_map: dict | None = None,
) -> dict:
    """Compute frequency table for a categorical variable."""
    if value_map:
        normalized = series.map(
            lambda x: value_map.get(str(x).strip(), f"UNMAPPED:{x}")
            if pd.notna(x) else None
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
            # pct_of_total: percentage of ALL rows (including missing), not just
            # respondents. Useful for population-based comparisons (M-4 fix).
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

    return {
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


# ─────────────────────────────────────────────────────────────────────────────
# ENTITY PROCESSORS
# ─────────────────────────────────────────────────────────────────────────────

def process_demography(
    dirs: list[str],
    cohort: str,
    variable_stats: dict,
    visit_mapping: dict[str, str] | None = None,
) -> tuple[set[str], int]:
    """
    Process Demography.tsv — extract Sex, Race, Ethnicity.
    Returns (set of participant IDs, total unique participant count).

    The returned participant set is restricted to those present at a BASELINE
    visit (per BASELINE_VISIT_CONFIG).  This ensures the denominator used by
    all downstream processors matches the TOPMed reference universe, which is
    baseline-only.  Cohorts where Demography.tsv has no associated_visit column
    (e.g. ARIC) or where BASELINE_VISIT_CONFIG has no entry fall back to the
    full all-phase coalesced set — no behaviour change for those cohorts.
    """
    print("\n  [Demography] Loading...")
    df = load_tsv_files(dirs, "*Demography*.tsv")
    if df.empty:
        print("    WARNING: No Demography files found.", file=sys.stderr)
        return set(), 0

    id_col = "associated_participant"
    if id_col not in df.columns:
        print(f"    WARNING: '{id_col}' column missing.", file=sys.stderr)
        return set(), 0

    # Report per-consent-group participant counts before dedup
    if "_consent_group" in df.columns:
        for cg, cg_df in df.groupby("_consent_group"):
            n_unique_cg = cg_df[id_col].nunique()
            n_rows_cg = len(cg_df)
            dup_tag = f" ({n_rows_cg - n_unique_cg:,} intra-file dups)" if n_rows_cg > n_unique_cg else ""
            print(f"    [{cg}] {n_rows_cg:,} rows, {n_unique_cg:,} unique participants{dup_tag}")

        # Consent groups are mutually exclusive by dbGaP design — a participant
        # belongs to exactly one consent group. If the same participant ID appears
        # in multiple consent groups, the extract data is corrupt.
        all_cg_ids = df.groupby("_consent_group")[id_col].apply(set)
        if len(all_cg_ids) > 1:
            seen: set = set()
            cross_consent_dups: set = set()
            for cg_ids in all_cg_ids:
                cross_consent_dups |= seen & cg_ids
                seen |= cg_ids
            if cross_consent_dups:
                n_dups = len(cross_consent_dups)
                sample = sorted(cross_consent_dups)[:5]
                print(f"    WARNING: {n_dups:,} participant(s) appear in multiple "
                      f"consent groups — deduplicating (keeping first occurrence).")
                print(f"      Sample IDs: {sample}")
                print(f"      Consent groups: {sorted(all_cg_ids.index.tolist())}")

    # DEFENSIVE: Coalesce duplicate rows per participant.
    # In practice, current YAMLs produce complete rows (all columns populated)
    # from each block, and consent groups are mutually exclusive, so this
    # groupby should be a no-op for most cohorts. It is retained as a safety
    # net in case future YAML changes introduce sparse multi-block rows.
    #
    # Save raw_df BEFORE coalesce so we can inspect per-row visit labels below.
    raw_df = df.copy()
    n_before = len(df)
    internal_cols = [c for c in df.columns if c.startswith("_")]
    data_cols = [c for c in df.columns if c != id_col and c not in internal_cols]
    df = df.groupby(id_col, sort=False).agg(
        {col: "first" for col in data_cols}
    ).reset_index()
    n_removed = n_before - len(df)
    if n_removed:
        print(f"    Coalesce: {n_before:,} → {len(df):,} rows ({n_removed:,} multi-source/cross-consent rows merged)")

    # ── Baseline participant filter ───────────────────────────────────────────
    # Restrict participant universe to those present at a baseline visit.
    # This prevents mid-study new enrollees (e.g. COPDGene Phase 2/3-only
    # participants) and ancillary-study-only participants (e.g. CHS SHHS1)
    # from inflating the denominator and creating phantom missing entries in
    # continuous variable comparisons against the TOPMed reference.
    #
    # Uses raw_df (pre-coalesce) so every row's visit label is visible.
    # Falls back to all-participants when:
    #   - associated_visit column is absent (e.g. ARIC)
    #   - BASELINE_VISIT_CONFIG has no entry for this cohort
    #   - No rows match the baseline label after UUID→name translation
    visit_col = "associated_visit"
    baseline_ids: set[str] | None = None

    if visit_col in raw_df.columns:
        if visit_mapping:
            raw_df["_visit_label"] = raw_df[visit_col].map(
                lambda x: visit_mapping.get(str(x).strip(), str(x).strip())
                if pd.notna(x) else None
            )
        else:
            raw_df["_visit_label"] = raw_df[visit_col].astype(str).where(
                raw_df[visit_col].notna(), other=None
            )
        label_col = "_visit_label"
        available_visits = set(raw_df[label_col].dropna().unique())
        matched = resolve_baseline_visits(cohort, available_visits)
        if matched:
            baseline_rows = raw_df[raw_df[label_col].isin(matched)]
            baseline_ids = set(baseline_rows[id_col].dropna().unique())
            print(f"    [baseline filter] Matched visits: {matched}")
            print(f"    [baseline filter] Baseline participants: {len(baseline_ids):,} "
                  f"(of {len(set(raw_df[id_col].dropna())):,} total across all visits)")
        else:
            print(f"    [baseline filter] No baseline visit match for {cohort} — "
                  f"using all-phase participant universe")
    else:
        print(f"    [baseline filter] No '{visit_col}' column in Demography.tsv — "
              f"using all-phase participant universe")

    # Apply baseline restriction to coalesced df
    if baseline_ids is not None:
        df = df[df[id_col].isin(baseline_ids)]

    participant_ids = set(df[id_col].dropna().unique())
    n_participants = len(participant_ids)
    print(f"    Unique participants (baseline universe): {n_participants:,}")

    # Sex
    if "sex" in df.columns:
        df["_sex_clean"] = clean_concept(df["sex"])
        stats = categorical_stats(df["_sex_clean"], OMOP_SEX_MAP)
        stats["bdc_label"] = "Sex"
        stats["topmed_variable"] = "annotated_sex_1"
        stats["dataset"] = "demographics"
        stats["n_total"] = n_participants  # base on unique participants
        stats["pct_missing"] = round(stats["n_missing"] / n_participants * 100, 1) if n_participants > 0 else 0.0
        variable_stats["annotated_sex_1"] = stats

    # Race
    if "race" in df.columns:
        df["_race_clean"] = clean_concept(df["race"])
        stats = categorical_stats(df["_race_clean"], OMOP_RACE_MAP)
        stats["bdc_label"] = "Race"
        stats["topmed_variable"] = "race_us_1"
        stats["dataset"] = "demographics"
        stats["n_total"] = n_participants
        stats["pct_missing"] = round(stats["n_missing"] / n_participants * 100, 1) if n_participants > 0 else 0.0
        variable_stats["race_us_1"] = stats

    # Ethnicity
    if "ethnicity" in df.columns:
        df["_eth_clean"] = clean_concept(df["ethnicity"])
        stats = categorical_stats(df["_eth_clean"], OMOP_ETHNICITY_MAP)
        stats["bdc_label"] = "Ethnicity"
        stats["topmed_variable"] = "hispanic_or_latino_1"
        stats["dataset"] = "demographics"
        stats["n_total"] = n_participants
        stats["pct_missing"] = round(stats["n_missing"] / n_participants * 100, 1) if n_participants > 0 else 0.0
        variable_stats["hispanic_or_latino_1"] = stats

    return participant_ids, n_participants


def load_visit_mapping(directories: list[str]) -> dict[str, str]:
    """Load Visit.tsv from pipeline output and build UUID → name mapping.

    The dm-bip pipeline outputs Visit.tsv with 'id' (UUID) and a label column.
    The label column name has varied across pipeline versions:
      - Older output: 'name'
      - Current output (v0.4+): 'visit_category'
    Both are tried in order so this works across pipeline versions.

    Some cohorts (e.g., FHS, JHS) use UUIDs in associated_visit columns while
    others (e.g., WHI) use human-readable names directly. This mapping allows
    the extraction script to resolve UUIDs to labels for visit selection.
    """
    df = load_tsv_files(directories, "*Visit*.tsv")
    if df.empty:
        return {}

    if "id" not in df.columns:
        print("    [visit mapping] WARNING: Visit.tsv has no 'id' column — cannot build UUID mapping")
        print(f"    [visit mapping] Columns found: {list(df.columns)}")
        return {}

    # Resolve whichever label column is most informative.
    # Priority order: 'label' and 'name' (descriptive) before 'visit_category'
    # (which is a standardized enum like "HEALTH_EXAMINATION" — same value for
    # all visits, useless for distinguishing cohort-specific visit names).
    # We pick the first candidate that has MORE THAN ONE unique non-null value
    # so we get a real descriptive mapping rather than a single enum value
    # repeated across all 26 (or N) visit rows.
    label_col = None
    for candidate in ("label", "name", "visit_category"):
        if candidate not in df.columns:
            continue
        n_unique = df[candidate].nunique(dropna=True)
        if n_unique > 1:
            label_col = candidate
            break
        # Only fall back to a single-value column if nothing better exists
        if label_col is None:
            label_col = candidate

    # Heuristic: treat id as "human-readable" (not a UUID) if none of the
    # sampled values match the UUID4/UUID5 pattern.
    id_sample = df["id"].dropna().head(20).astype(str)
    _uuid_pattern = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
    )
    ids_are_uuids = id_sample.str.match(_uuid_pattern).any()
    n_unique_ids = df["id"].nunique(dropna=True)

    if label_col is None:
        # No label column exists. If ids are human-readable visit names,
        # build an identity mapping so they pass through to baseline matching.
        if not ids_are_uuids and n_unique_ids > 0:
            print(f"    [visit mapping] No label column found — but id values are "
                  f"human-readable visit names ({n_unique_ids} unique). "
                  f"Using identity mapping.")
            print(f"    [visit mapping] Columns found: {list(df.columns)}")
            mapping = {}
            for vid in df["id"].dropna().unique():
                key = str(vid).strip()
                if key:
                    mapping[key] = key
        else:
            print("    [visit mapping] WARNING: Visit.tsv has no label column and "
                  "id values appear to be UUIDs — cannot build visit name mapping")
            print(f"    [visit mapping] Columns found: {list(df.columns)}")
            return {}
    elif not ids_are_uuids:
        n_unique_labels = df[label_col].nunique(dropna=True)
        if n_unique_ids > n_unique_labels:
            # id column is human-readable and more specific than label column —
            # use identity mapping so specific visit names are preserved.
            # This prevents destructive mapping like "CARDIA YEAR 0" →
            # "HEALTH_EXAMINATION".
            print(f"    [visit mapping] id values are human-readable visit names "
                  f"({n_unique_ids} unique) — using them directly (label_col='{label_col}' "
                  f"has only {n_unique_labels} unique values)")
            mapping = {}
            for vid in df["id"].dropna().unique():
                key = str(vid).strip()
                if key:
                    mapping[key] = key
        else:
            # ids are human-readable but not more specific than labels — use
            # the label column (normal path).
            mapping = {}
            for _, row in df[["id", label_col]].drop_duplicates().iterrows():
                vid = str(row["id"]).strip() if pd.notna(row["id"]) else None
                vname = str(row[label_col]).strip() if pd.notna(row[label_col]) else None
                if vid and vname:
                    mapping[vid] = vname
    else:
        # ids are UUIDs — map them to the label column (normal path).
        mapping = {}
        for _, row in df[["id", label_col]].drop_duplicates().iterrows():
            vid = str(row["id"]).strip() if pd.notna(row["id"]) else None
            vname = str(row[label_col]).strip() if pd.notna(row[label_col]) else None
            if vid and vname:
                mapping[vid] = vname

    if mapping:
        unique_names = sorted(set(mapping.values()))
        print(f"    Visit UUID → name mapping loaded ({len(mapping)} visits, label_col='{label_col}')")
        if len(unique_names) <= 10:
            print(f"    Visit labels: {unique_names}")
        else:
            print(f"    Visit labels (first 10 of {len(unique_names)}): {unique_names[:10]}")
    else:
        print(f"    [visit mapping] WARNING: Visit.tsv loaded but produced empty mapping (label_col='{label_col}')")
    return mapping


def _select_baseline_visit(
    df: pd.DataFrame,
    cohort: str,
    visit_col: str = "associated_visit",
    visit_mapping: dict[str, str] | None = None,
    override_visits: list[str] | None = None,
) -> tuple[pd.DataFrame, str]:
    """
    Filter measurement rows to the configured baseline visit(s).
    Returns (filtered_df, visit_label_used).

    Strategy:
    1. If visit values are UUIDs and a visit_mapping is available, translate
       UUIDs to human-readable names first.
    2. If override_visits is provided, use those visit labels directly instead
       of BASELINE_VISIT_CONFIG. Used for variables collected at a different
       visit than the cohort's primary baseline (e.g., ARIC MCH at Exam 3).
    3. Collect ALL preferred visits that exist (not just the first match) —
       this is essential for multi-generational cohorts like FHS where
       baseline data spans Original Exam 4 + Offspring Exam 1 + Gen3 Exam 1.
    4. Return only rows matching those preferred visits. If coverage is low,
       that is a real finding about YAML coverage gaps — not something to
       silently fix by pulling in non-baseline data.
    5. If no preferred visit matches at all, raise ValueError (config error).
    """
    if visit_col not in df.columns:
        return df, "unknown"

    # If UUIDs are present and we have a mapping, translate to names
    if visit_mapping:
        df = df.copy()
        df["_visit_label"] = df[visit_col].map(
            lambda x: visit_mapping.get(str(x).strip(), str(x).strip())
            if pd.notna(x) else None
        )
        label_col = "_visit_label"
    else:
        label_col = visit_col

    available = set(df[label_col].dropna().unique())

    if override_visits is not None:
        # Variable-specific visit override — bypass BASELINE_VISIT_CONFIG entirely.
        # Case-insensitive match against the override list.
        upper_to_original = {v.upper(): v for v in available}
        matched_prefs = [
            upper_to_original[ov.upper()]
            for ov in override_visits
            if ov.upper() in upper_to_original
        ]
        if not matched_prefs:
            raise ValueError(
                f"[_select_baseline_visit] override_visits {override_visits} matched "
                f"none of the available labels: {sorted(available)}"
            )
        filtered = df[df[label_col].isin(matched_prefs)]
        label_str = " + ".join(matched_prefs) if len(matched_prefs) > 1 else matched_prefs[0]
        return filtered, f"{label_str} [override]"

    # Collect ALL matching baseline visits (case-insensitive + pattern fallback)
    matched_prefs = resolve_baseline_visits(cohort, available)

    if matched_prefs:
        filtered = df[df[label_col].isin(matched_prefs)]
        if not filtered.empty:
            label = " + ".join(matched_prefs) if len(matched_prefs) > 1 else matched_prefs[0]
            return filtered, label

    if not matched_prefs:
        # No baseline visit matched at all — this is a configuration error, not a
        # coverage gap. All cohort visit.yamls must emit a 'name:' slot so Visit.tsv
        # has a descriptive label column matching BASELINE_VISIT_CONFIG.
        config = BASELINE_VISIT_CONFIG.get(cohort, {})
        raise ValueError(
            f"[_select_baseline_visit] No baseline visit matched for cohort '{cohort}'.\n"
            f"  Expected (exact):   {config.get('exact', [])}\n"
            f"  Expected (pattern): {config.get('pattern', 'none')}\n"
            f"  Available labels:   {sorted(available)}\n"
            f"  Fix: ensure the cohort's visit.yaml emits a 'name:' slot so Visit.tsv\n"
            f"  has a descriptive label column rather than visit_category enum values."
        )

    # matched_prefs was non-empty but filtered was empty — the preferred visit
    # labels exist in the data but produced zero rows after filtering (shouldn't
    # happen, but handle gracefully).
    label = " + ".join(matched_prefs) if len(matched_prefs) > 1 else matched_prefs[0]
    print(f"    [baseline] WARNING: Preferred visits {matched_prefs} matched but "
          f"produced 0 rows after filtering")
    return df.head(0), f"{label} (0 rows)"


def process_measurements(
    dirs: list[str],
    cohort: str,
    participant_ids: set[str],
    n_participants: int,
    variable_stats: dict,
    visit_mapping: dict[str, str] | None = None,
) -> tuple[list[str], set[str]]:
    """
    Process MeasurementObservation.tsv — extract all matched measurement variables.
    Returns (list of TOPMed variable names found, set of baseline participant IDs).
    """
    print("\n  [MeasurementObservation] Loading...")
    df = load_tsv_files(dirs, "*MeasurementObservation*.tsv")
    if df.empty:
        print("    No MeasurementObservation files found.")
        return [], set()

    # ── Diagnostic: show all columns for Set-related troubleshooting ─────
    all_cols = sorted(df.columns.tolist())
    obs_cols = [c for c in all_cols if "observation" in c.lower() or "value" in c.lower()]
    print(f"    [Columns] {len(all_cols)} total columns. Observation/value-related:")
    for c in obs_cols:
        non_null = int(df[c].notna().sum())
        print(f"      {c}: {non_null:,} non-null / {len(df):,} rows")

    # ── Normalize MeasurementObservationSet columns ──────────────────────
    # MeasurementObservationSet.tsv stores child observations in one of two
    # formats depending on dm-bip version:
    #
    # Format A (flattened columns):
    #   observations__observation_type, observations__value_quantity__value_decimal
    #   → Fill standard columns from prefixed ones.
    #
    # Format B (serialized blob):
    #   A single `observations` column containing JSON-like serialized data
    #   with child observation_type and value nested inside.
    #   → Parse, expand into rows, and merge back.
    #
    # Detection order: try Format A first (column name matching), then Format B.

    set_obs_col = None
    set_val_col = None
    for c in df.columns:
        cl = c.lower()
        if c != "observation_type" and "observation_type" in cl and set_obs_col is None:
            set_obs_col = c
        if c != "value_quantity__value_decimal" and "value_quantity" in cl and "value_decimal" in cl and set_val_col is None:
            set_val_col = c

    if set_obs_col:
        # ── Format A: flattened columns ──
        print(f"    [ObservationSet] Format A: detected child obs-type column '{set_obs_col}'")
        if "observation_type" not in df.columns:
            df["observation_type"] = df[set_obs_col]
        else:
            mask = df["observation_type"].isna() & df[set_obs_col].notna()
            df.loc[mask, "observation_type"] = df.loc[mask, set_obs_col]
        n_set_rows = int(df[set_obs_col].notna().sum())
        print(f"    [ObservationSet] Normalized {n_set_rows:,} child-observation rows")

        if set_val_col:
            std_val_col = "value_quantity__value_decimal"
            if std_val_col not in df.columns:
                df[std_val_col] = df[set_val_col]
            else:
                mask = df[std_val_col].isna() & df[set_val_col].notna()
                df.loc[mask, std_val_col] = df.loc[mask, set_val_col]

    elif "observations" in df.columns:
        # ── Format B: serialized `observations` column ──
        set_rows = df["observations"].notna()
        n_set = int(set_rows.sum())
        if n_set > 0:
            print(f"    [ObservationSet] Format B: found {n_set:,} rows with serialized "
                  f"'observations' column — parsing child observations...")

            # Sample to determine format
            sample_vals = df.loc[set_rows, "observations"].head(3).tolist()
            for i, sv in enumerate(sample_vals[:2]):
                preview = str(sv)[:200]
                print(f"      Sample {i+1}: {preview}...")

            import ast
            child_rows = []
            parse_errors = 0
            carry_cols = [c for c in df.columns if c != "observations"]

            for idx in df.index[set_rows]:
                raw = df.at[idx, "observations"]
                parent = {c: df.at[idx, c] for c in carry_cols}

                # Try parsing as Python literal (list of dicts) or JSON
                parsed = None
                try:
                    parsed = ast.literal_eval(str(raw))
                except (ValueError, SyntaxError):
                    try:
                        parsed = json.loads(str(raw))
                    except (json.JSONDecodeError, TypeError):
                        pass

                if parsed is None:
                    # Try as pipe-delimited or other simple format
                    parse_errors += 1
                    continue

                # Handle both single dict and list of dicts
                if isinstance(parsed, dict):
                    parsed = [parsed]

                if isinstance(parsed, list):
                    for child in parsed:
                        if not isinstance(child, dict):
                            continue
                        row = dict(parent)
                        # Extract observation_type from child
                        for key in ("observation_type", "type", "obs_type"):
                            if key in child:
                                row["observation_type"] = child[key]
                                break
                        # Extract value_decimal from nested value_quantity
                        vq = child.get("value_quantity", {})
                        if isinstance(vq, dict):
                            if "value_decimal" in vq:
                                row["value_quantity__value_decimal"] = vq["value_decimal"]
                            if "unit" in vq:
                                row["value_quantity__unit"] = vq["unit"]
                        # Direct value_decimal at child level
                        elif "value_decimal" in child:
                            row["value_quantity__value_decimal"] = child["value_decimal"]
                        child_rows.append(row)

            if child_rows:
                # Replace Set rows with expanded child rows
                df = df[~set_rows].copy()
                child_df = pd.DataFrame(child_rows)
                df = pd.concat([df, child_df], ignore_index=True)
                print(f"    [ObservationSet] Expanded {n_set:,} Set rows → "
                      f"{len(child_rows):,} child observation rows "
                      f"({parse_errors} parse errors)")
            elif parse_errors > 0:
                print(f"    [ObservationSet] WARNING: Could not parse {parse_errors:,} "
                      f"Set rows — BP will be missing. Check sample output above.")
            else:
                print(f"    [ObservationSet] WARNING: Parsed {n_set:,} Set rows but "
                      f"found 0 child observations — unexpected format.")
    else:
        print("    [ObservationSet] No Set columns detected (no child observations to normalize)")

    # Also normalize value_enum and value_string for categorical Set observations
    for suffix in ("value_enum", "value_string"):
        for c in df.columns:
            if c != suffix and c.endswith(suffix) and suffix in df.columns:
                mask = df[suffix].isna() & df[c].notna()
                if mask.any():
                    df.loc[mask, suffix] = df.loc[mask, c]
                    break

    if "observation_type" not in df.columns:
        print("    WARNING: 'observation_type' column missing.", file=sys.stderr)
        return [], set()

    # Clean observation_type
    df["_obs_type"] = clean_concept(df["observation_type"])

    # Build reverse lookup: alias code → primary label
    _alias_to_label: dict[str, str] = {}
    for _code, _spec in BDC_MEASUREMENT_MAP.items():
        for _a in _spec.get("aliases", []):
            _alias_to_label[_a] = _spec["bdc_label"]

    # Report all observation types found
    obs_types = df["_obs_type"].value_counts()
    print(f"    Observation types found ({len(obs_types)}):")
    for ot, cnt in obs_types.head(25).items():
        mapped = BDC_MEASUREMENT_MAP.get(ot, {}).get("bdc_label", "")
        if not mapped:
            mapped = _alias_to_label.get(ot, "")
        if mapped:
            marker = f" → {mapped}"
        else:
            marker = " (not in TOPMed comparison set)"
        print(f"      {ot}: {cnt:,} rows{marker}")
    if len(obs_types) > 25:
        print(f"      ... and {len(obs_types) - 25} more types")

    found_vars = []
    # Track participants who appear in ANY baseline measurement — used by
    # process_drugs as the denominator for medication binary variables.
    # Participants absent here never attended the baseline visit and should be
    # counted as missing (not "No") for medication status.
    baseline_meas_ids: set = set()
    value_col = "value_quantity__value_decimal"

    for bdc_code, spec in BDC_MEASUREMENT_MAP.items():
        # Collect rows matching the primary code AND any aliases
        codes_to_match = [bdc_code] + spec.get("aliases", [])
        subset = df[df["_obs_type"].isin(codes_to_match)]
        if subset.empty:
            continue

        topmed_var = spec["topmed_var"]
        found_vars.append(topmed_var)

        # If a preferred_method is configured, filter the subset BEFORE passing
        # to _select_baseline_visit().  This is important: the downstream dedup
        # (coalesce first non-null per participant) runs on whatever rows
        # _select_baseline_visit() returns, so applying the method filter AFTER
        # dedup would find no matching rows when the preferred method has a
        # preferred method has a higher (later) age than a non-preferred method.
        # Example: MESA bdy_wgt.yaml recalled weights (age=7300) would always beat
        # current measured weights (age~16000+) in the earliest-first dedup, making
        # the post-dedup preferred_method filter silently empty.
        # Per-cohort overrides take precedence over the global preferred_method.
        preferred = spec.get("preferred_method_override", {}).get(cohort,
                             spec.get("preferred_method"))
        if preferred and "method_type" in subset.columns:
            method_filtered = subset[subset["method_type"] == preferred]
            if not method_filtered.empty:
                print(f"      [method filter] {spec['bdc_label']}: "
                      f"{len(subset):,} → {len(method_filtered):,} rows "
                      f"(preferred: {preferred!r})")
                subset = method_filtered

        # Select baseline visit — skip this variable if no baseline rows exist.
        # A per-variable visit_override (e.g., ARIC MCH at Exams 3-5) bypasses
        # BASELINE_VISIT_CONFIG and uses the specified visits instead.
        visit_override = spec.get("visit_override", {}).get(cohort)
        try:
            baseline, visit_used = _select_baseline_visit(subset, cohort,
                                                           visit_mapping=visit_mapping,
                                                           override_visits=visit_override)
        except ValueError:
            print(f"    {spec['bdc_label']} ({bdc_code}): SKIPPED — no baseline visit data")
            continue

        # DEFENSIVE: Deduplicate to one value per participant.
        # In practice, each measurement block produces complete rows (value,
        # age, visit all populated), so this is equivalent to drop_duplicates.
        # Retained as a safety net in case future YAML changes introduce
        # overlapping blocks with sparse columns for the same participant.
        n_pre_dedup = len(baseline)
        if "associated_participant" in baseline.columns:
            id_col_meas = "associated_participant"
            internal_cols_meas = [c for c in baseline.columns if c.startswith("_")]
            data_cols_meas = [c for c in baseline.columns
                              if c != id_col_meas and c not in internal_cols_meas]
            baseline = (
                baseline
                .groupby(id_col_meas, sort=False)
                .agg({col: "first" for col in data_cols_meas})
                .reset_index()
            )
        print(f"    {spec['bdc_label']} ({bdc_code}): {len(baseline):,} participants "
              f"(from {n_pre_dedup:,} baseline rows) [visit: {visit_used}]")

        # Accumulate baseline participant IDs for medication denominator
        if "associated_participant" in baseline.columns:
            baseline_meas_ids.update(baseline["associated_participant"].dropna().unique())

        if value_col in baseline.columns:
            values = pd.to_numeric(baseline[value_col], errors="coerce")
            # Debug: if we have rows but all values are NaN, show raw samples
            if len(baseline) > 0 and values.notna().sum() == 0:
                raw_sample = baseline[value_col].head(5).tolist()
                print(f"    [debug] {spec['bdc_label']}: {len(baseline)} rows but 0 valid numeric values. "
                      f"Raw samples: {raw_sample}")
        else:
            values = pd.Series(dtype=float)

        # Compute stats directly from the baseline-filtered data.
        # Don't rely on participant ID intersection — IDs may differ
        # between Demography.tsv (dbGaP subject IDs) and MeasurementObservation.tsv
        # (dm-bip UUIDs or row-level references). Instead, count valid
        # measurements from the deduped baseline and use Demography's
        # n_participants as the denominator for missingness.
        stats = continuous_stats(
            values,
            unit=spec.get("unit"),
            plausible_lo=spec.get("plausible_lo"),
            plausible_hi=spec.get("plausible_hi"),
        )
        # Override n_total with Demography participant count for proper missingness
        stats["n_total"] = n_participants
        stats["n_missing"] = n_participants - stats["n_valid"]
        stats["pct_missing"] = round(
            stats["n_missing"] / n_participants * 100, 1
        ) if n_participants > 0 else 0.0
        stats["bdc_label"] = spec["bdc_label"]
        stats["topmed_variable"] = topmed_var
        stats["dataset"] = "baseline_covariates"
        stats["visit_label"] = visit_used
        stats["bdc_concept_code"] = bdc_code
        variable_stats[topmed_var] = stats

    # ── Discover ALL remaining observation types not in BDC_MEASUREMENT_MAP ──
    known_codes = set(BDC_MEASUREMENT_MAP.keys())
    # Also exclude alias codes — they're already aggregated into their primary
    for _spec in BDC_MEASUREMENT_MAP.values():
        known_codes.update(_spec.get("aliases", []))
    all_obs_types = set(df["_obs_type"].dropna().unique())
    discovered_codes = sorted(all_obs_types - known_codes)

    if discovered_codes:
        print(f"\n    [Discovery] Processing {len(discovered_codes)} additional observation types...")

        for disc_code in discovered_codes:
            subset = df[df["_obs_type"] == disc_code]
            if subset.empty:
                continue

            # Select baseline visit — skip gracefully if this discovered
            # observation type has no rows at baseline visits (e.g., only
            # collected at follow-up exams).  Not fatal for discovery.
            try:
                baseline, visit_used = _select_baseline_visit(
                    subset, cohort, visit_mapping=visit_mapping)
            except Exception as exc:
                print(f"      {disc_code}: skipped (no baseline data: {type(exc).__name__})")
                continue

            # Dedup per participant — coalesce (first non-null) for same reason
            # as the BDC_MEASUREMENT_MAP loop above.
            n_pre_dedup = len(baseline)
            if "associated_participant" in baseline.columns:
                id_col_disc = "associated_participant"
                internal_cols_disc = [c for c in baseline.columns if c.startswith("_")]
                data_cols_disc = [c for c in baseline.columns
                                  if c != id_col_disc and c not in internal_cols_disc]
                baseline = (
                    baseline
                    .groupby(id_col_disc, sort=False)
                    .agg({col: "first" for col in data_cols_disc})
                    .reset_index()
                )

            if baseline.empty:
                continue

            var_key = disc_code  # concept code as variable key

            # Accumulate baseline participant IDs for medication denominator
            if "associated_participant" in baseline.columns:
                baseline_meas_ids.update(baseline["associated_participant"].dropna().unique())

            # Try numeric first
            is_continuous = False
            numeric_vals = pd.Series(dtype=float)
            if value_col in baseline.columns:
                numeric_vals = pd.to_numeric(baseline[value_col], errors="coerce")
                n_numeric = int(numeric_vals.notna().sum())
                n_non_null = int(baseline[value_col].notna().sum())
                if n_non_null > 0 and n_numeric / n_non_null >= 0.5:
                    is_continuous = True

            if is_continuous:
                stats = continuous_stats(numeric_vals)
                stats["n_total"] = n_participants
                stats["n_missing"] = n_participants - stats["n_valid"]
                stats["pct_missing"] = round(
                    stats["n_missing"] / n_participants * 100, 1
                ) if n_participants > 0 else 0.0
            else:
                # Try categorical columns
                cat_series = pd.Series(dtype=object)
                for cat_col in ("value_enum", "value_string", value_col):
                    if cat_col in baseline.columns:
                        vals = baseline[cat_col].dropna()
                        if len(vals) > 0:
                            cat_series = vals
                            break
                stats = categorical_stats(cat_series)
                stats["n_total"] = n_participants
                stats["n_missing"] = n_participants - stats["n_valid"]
                stats["pct_missing"] = round(
                    stats["n_missing"] / n_participants * 100, 1
                ) if n_participants > 0 else 0.0

            stats["bdc_label"] = disc_code
            stats["topmed_variable"] = None
            stats["dataset"] = "bdc_measurement"
            stats["visit_label"] = visit_used
            stats["bdc_concept_code"] = disc_code
            discovered_key = f"discovered:measurement:{var_key}"
            variable_stats[discovered_key] = stats
            found_vars.append(discovered_key)

            type_tag = stats["type"]
            n_valid = stats["n_valid"]
            print(f"      {disc_code}: {len(baseline):,} participants "
                  f"({type_tag}, n_valid={n_valid:,}) [visit: {visit_used}]")

    return found_vars, baseline_meas_ids


def process_conditions(
    dirs: list[str],
    cohort: str,
    participant_ids: set[str],
    n_participants: int,
    variable_stats: dict,
    visit_mapping: dict[str, str] | None = None,
) -> list[str]:
    """
    Process Condition.tsv — extract matched condition variables.
    Returns list of TOPMed variable names found.

    BDC stores conditions as rows with condition_concept codes and a
    condition_status column (PRESENT, ABSENT, HISTORICAL).  Only rows
    with status PRESENT or HISTORICAL count as "affected".
    TOPMed stores them as binary (0/1) per participant.

    STRATEGY (2026-03-31 update):
    For "Prior History" comparison against TOPMed reference, we filter to
    BASELINE visits first, then apply "ever positive" within those visits.

    Why: Longitudinal cohorts (CHS, ARIC, FHS, WHI, etc.) have condition
    blocks at multiple follow-up visits capturing INCIDENT events (e.g.,
    "NEW MI" at Year 3, "INCIDENT ANGINA" in summary tables). The TOPMed
    reference captures only pre-enrollment prior history. Including
    post-baseline incident events inflates "Prior History" rates by 50-130%
    (confirmed: CHS angina +129%, MI +79%, coronary angioplasty +48%).

    The all-visits "ever positive" count is still logged for diagnostic
    purposes so we can compare baseline-only vs all-visits prevalence.

    Cohorts unaffected by this change (single visit only): COPDGene, HCHS.
    """
    print("\n  [Condition] Loading...")
    df = load_tsv_files(dirs, "*Condition*.tsv")
    if df.empty:
        print("    No Condition files found.")
        return []

    if "condition_concept" not in df.columns:
        print("    WARNING: 'condition_concept' column missing.", file=sys.stderr)
        return []

    n_total_rows = len(df)

    df["_cond_concept"] = clean_concept(df["condition_concept"])

    # Clean condition_status if present
    has_status = "condition_status" in df.columns
    if has_status:
        df["_cond_status"] = df["condition_status"].astype(str).str.strip().str.upper()
        # Normalize known typo: UKNOWN → UNKNOWN
        df["_cond_status"] = df["_cond_status"].replace("UKNOWN", "UNKNOWN")

    # Report condition concepts found (before baseline filter)
    cond_types = df["_cond_concept"].value_counts()
    print(f"    Condition concepts found ({len(cond_types)}) across {n_total_rows:,} total rows:")
    for ct, cnt in cond_types.head(20).items():
        mapped = BDC_CONDITION_MAP.get(ct, {}).get("bdc_label", "")
        marker = f" → {mapped}" if mapped else ""
        print(f"      {ct}: {cnt:,} rows{marker}")

    # ── Baseline visit filtering ─────────────────────────────────────────
    # For "Prior History" comparison, we need to restrict to baseline visits.
    # Load visit UUID->name mapping (if visits are stored as UUIDs) and
    # resolve human-readable visit labels for filtering.
    #
    # IMPORTANT: We create BOTH a baseline-filtered DF and keep the full DF.
    # - baseline_df: used for mapped conditions compared against TOPMed
    #   reference (which measures pre-enrollment prior history only)
    # - df (full): used for discovery of unmapped conditions (where
    #   all-visits prevalence is more informative)
    #
    # If baseline filtering yields no rows for a concept (e.g., the condition
    # was only asked at follow-up visits, or BASELINE_VISIT_CONFIG doesn't
    # match the visit labels), we fall back to all-visits to avoid losing
    # data entirely. This fallback is logged clearly so it can be diagnosed.
    visit_col = "associated_visit"
    has_visit = visit_col in df.columns

    if has_visit:
        # Resolve visit labels (handles UUID -> name translation)
        if visit_mapping:
            df["_visit_label"] = df[visit_col].map(
                lambda x: visit_mapping.get(str(x).strip(), str(x).strip())
                if pd.notna(x) else None
            )
        else:
            df["_visit_label"] = df[visit_col]

        # Show visit distribution before filtering (diagnostic)
        visit_dist = df["_visit_label"].value_counts()
        print(f"    Visit distribution across all condition rows ({len(visit_dist)} visits):")
        for vl, cnt in visit_dist.head(10).items():
            print(f"      {vl}: {cnt:,} rows")
        if len(visit_dist) > 10:
            print(f"      ... and {len(visit_dist) - 10} more visits")

        # Filter to baseline visits using BASELINE_VISIT_CONFIG
        available_visits = set(df["_visit_label"].dropna().unique())
        matched_baseline = resolve_baseline_visits(cohort, available_visits)

        if matched_baseline:
            baseline_df = df[df["_visit_label"].isin(matched_baseline)]
            baseline_label = " + ".join(matched_baseline)
            print(f"    [baseline filter] Matched baseline visits: {baseline_label}")
            print(f"    [baseline filter] {len(baseline_df):,} / {len(df):,} rows "
                  f"retained ({len(baseline_df)/len(df)*100:.1f}%)")
        else:
            # No baseline visit matched — warn and use all rows as fallback
            config = BASELINE_VISIT_CONFIG.get(cohort, {})
            print(f"    [baseline filter] WARNING: No baseline visit matched for conditions.")
            print(f"      Expected: {config.get('exact', [])}")
            print(f"      Available: {sorted(available_visits)}")
            print(f"      Falling back to all condition rows.")
            baseline_df = df
            baseline_label = "all rows (no baseline match)"
    else:
        # No visit column — can't filter; use all rows
        baseline_df = df
        baseline_label = "all rows (no visit column)"
        print(f"    [baseline filter] No '{visit_col}' column — using all rows")

    found_vars = []
    id_col = "associated_participant"

    # ── Group condition codes that map to the same TOPMed variable ────────
    # Multiple BDC codes can map to the same topmed_var (e.g., PAD has both
    # MONDO:0005386 and MONDO:0005294 -> pad_prior_1).  We must UNION the
    # affected participants, not overwrite.
    topmed_var_groups: dict[str, list[str]] = defaultdict(list)
    for bdc_code, spec in BDC_CONDITION_MAP.items():
        topmed_var_groups[spec["topmed_var"]].append(bdc_code)

    for topmed_var, bdc_codes in topmed_var_groups.items():
        spec = BDC_CONDITION_MAP[bdc_codes[0]]  # use first for labels
        all_affected_ids: set[str] = set()
        all_respondent_ids: set[str] = set()  # all IDs with ANY record (any status)
        all_visits_affected_ids: set[str] = set()  # diagnostic: all-visits count
        code_details: list[str] = []

        # Per-variable visit override: if this topmed_var has a cohort-specific
        # override in CONDITION_PROCEDURE_VISIT_OVERRIDE, re-filter from df
        # using those visits instead of the global baseline_df.
        var_override = CONDITION_PROCEDURE_VISIT_OVERRIDE.get(topmed_var, {}).get(cohort)
        if var_override and has_visit:
            var_baseline_df = df[df["_visit_label"].isin(var_override)]
            var_baseline_label = " + ".join(sorted(set(df["_visit_label"].dropna()) & set(var_override)))
            print(f"    [visit override] {spec['bdc_label']}: using {var_baseline_label} "
                  f"({len(var_baseline_df):,} / {len(df):,} rows)")
        else:
            var_baseline_df = baseline_df
            var_baseline_label = baseline_label

        for bdc_code in bdc_codes:
            cur_spec = BDC_CONDITION_MAP[bdc_code]

            # ── Step 1: All-visits count (diagnostic only) ───────────────
            # We still compute the all-visits "ever positive" count so we
            # can log the difference and diagnose whether the baseline filter
            # is working correctly.  This count is NOT used for the final
            # stats — it's purely informational.
            subset_all = df[df["_cond_concept"] == bdc_code]
            if has_status and not subset_all.empty:
                positive_all = subset_all[subset_all["_cond_status"].isin(
                    ["PRESENT", "HISTORICAL", "HISTORY"])]
            else:
                positive_all = subset_all
            if not positive_all.empty and id_col in positive_all.columns:
                all_visits_affected_ids |= set(positive_all[id_col].dropna().unique())

            # ── Step 2: Baseline-filtered count (used for comparison) ────
            # Filter to baseline visits first, THEN apply "ever positive"
            # within those visits.  This matches what the TOPMed reference
            # measures: pre-enrollment prior history only.
            subset = var_baseline_df[var_baseline_df["_cond_concept"] == bdc_code]

            if has_status and not subset.empty:
                positive_mask = subset["_cond_status"].isin(["PRESENT", "HISTORICAL", "HISTORY"])
                subset_positive = subset[positive_mask]
            else:
                subset_positive = subset

            n_total_concept = len(subset_all)  # all-visit row count for context
            n_baseline_rows = len(subset)
            n_positive = len(subset_positive)

            # ── Fallback: if baseline filter yields zero positive rows but
            # all-visits has positives, fall back to all-visits for this
            # concept.  This prevents losing data for conditions only asked
            # at non-baseline visits (e.g., a condition captured exclusively
            # in an AFU or event table with no baseline equivalent).
            if n_positive == 0 and len(positive_all) > 0:
                print(f"    {cur_spec['bdc_label']} ({bdc_code}): "
                      f"0 positive at baseline, {len(positive_all):,} across all visits "
                      f"-- FALLING BACK to all-visits")
                subset_positive = positive_all

            print(f"    {cur_spec['bdc_label']} ({bdc_code}): "
                  f"{n_total_concept:,} total rows, {n_baseline_rows:,} at baseline, "
                  f"{n_positive:,} positive [visit: {var_baseline_label}]")

            # Collect affected IDs from this code
            if not subset_positive.empty and id_col in subset_positive.columns:
                code_affected = set(subset_positive[id_col].dropna().unique())
            else:
                code_affected = set()

            n_code = len(code_affected & participant_ids) if participant_ids else len(code_affected)
            if n_code == 0 and code_affected:
                n_code = len(code_affected)
            code_details.append(f"{bdc_code}={n_code}")
            all_affected_ids |= code_affected

            # Collect ALL respondent IDs (any status) from the same scope
            # If fallback was triggered for this code, use all-visits; otherwise baseline
            if n_positive == 0 and len(positive_all) > 0:
                respondent_src = subset_all  # fallback scope
            else:
                respondent_src = subset  # baseline scope
            if not respondent_src.empty and id_col in respondent_src.columns:
                all_respondent_ids |= set(respondent_src[id_col].dropna().unique())

        n_affected = len(all_affected_ids & participant_ids) if participant_ids else len(all_affected_ids)
        if n_affected == 0 and all_affected_ids:
            n_affected = len(all_affected_ids)
        # Respondent-based denominator: only count participants with explicit
        # data (any status).  Do NOT impute "No" for absent records.
        n_respondent = len(all_respondent_ids & participant_ids) if participant_ids else len(all_respondent_ids)
        if n_respondent == 0 and all_respondent_ids:
            n_respondent = len(all_respondent_ids)
        n_unaffected = n_respondent - n_affected if n_respondent > 0 else 0
        n_unaffected = max(n_unaffected, 0)
        n_no_data = max(n_participants - n_respondent, 0) if n_participants > 0 else 0

        if n_no_data > 0 and n_participants > 0:
            print(f"    [missing] {spec['bdc_label']}: {n_respondent:,} with data, "
                  f"{n_no_data:,} no record ({n_no_data/n_participants*100:.1f}%)")

        # Build a binary categorical series (None entries = missing)
        labels = (
            ["Prior History"] * n_affected +
            ["No Prior History"] * n_unaffected +
            [None] * n_no_data
        )
        binary_series = pd.Series(labels)

        stats = categorical_stats(binary_series)
        stats["bdc_label"] = spec["bdc_label"]
        stats["topmed_variable"] = topmed_var
        stats["dataset"] = "atherosclerosis_events_prior"
        stats["bdc_concept_code"] = bdc_codes[0] if len(bdc_codes) == 1 else " | ".join(bdc_codes)
        stats["n_total"] = n_participants
        stats["visit_label"] = var_baseline_label  # record which visits were used
        variable_stats[topmed_var] = stats
        found_vars.append(topmed_var)

        # ── Diagnostic: compare baseline-only vs all-visits counts ───────
        # This log line is critical for debugging.  If the baseline count
        # looks too LOW compared to reference, check:
        #   (1) BASELINE_VISIT_CONFIG - do the exact/pattern rules match the TSV labels?
        #   (2) Does the cohort store baseline conditions in a visit with
        #       a non-baseline name? (e.g., WHI screening forms)
        #   (3) Did the fallback trigger? (baseline=0, used all-visits)
        # If the baseline count looks too HIGH, the baseline visits may
        # include summary/aggregate tables that span beyond enrollment.
        n_all_visits = len(all_visits_affected_ids & participant_ids) if participant_ids else len(all_visits_affected_ids)
        if n_all_visits == 0 and all_visits_affected_ids:
            n_all_visits = len(all_visits_affected_ids)
        delta = n_all_visits - n_affected
        if delta > 0 and n_participants > 0:
            print(f"    [diagnostic] {spec['bdc_label']}: baseline={n_affected:,} "
                  f"({n_affected/n_participants*100:.1f}%), "
                  f"all-visits={n_all_visits:,} "
                  f"({n_all_visits/n_participants*100:.1f}%), "
                  f"delta=+{delta:,} incident/follow-up cases excluded")

        if len(bdc_codes) > 1:
            detail_str = ", ".join(code_details)
            print(f"    {spec['bdc_label']} (merged: {detail_str}): "
                  f"{n_affected:,} affected / {n_participants:,} total "
                  f"({n_affected/n_participants*100:.1f}%)"
                  if n_participants > 0 else
                  f"    {spec['bdc_label']} (merged: {detail_str}): {n_affected:,} affected")
        else:
            print(f"    {spec['bdc_label']} ({bdc_codes[0]}): {n_affected:,} affected / "
                  f"{n_participants:,} total ({n_affected/n_participants*100:.1f}%)"
                  if n_participants > 0 else
                  f"    {spec['bdc_label']} ({bdc_codes[0]}): {n_affected:,} affected")

    # ── Discover ALL remaining condition concepts not in BDC_CONDITION_MAP ──
    # Use baseline_df (not df) so discovered conditions are also baseline-filtered,
    # consistent with the mapped conditions above (C-1 fix).
    known_cond_codes = set(BDC_CONDITION_MAP.keys())
    all_cond_types = set(baseline_df["_cond_concept"].dropna().unique())
    discovered_conds = sorted(all_cond_types - known_cond_codes)

    if discovered_conds:
        print(f"\n    [Discovery] Processing {len(discovered_conds)} additional condition concepts...")

        for disc_code in discovered_conds:
            subset = baseline_df[baseline_df["_cond_concept"] == disc_code]
            if subset.empty:
                continue

            # "Ever positive" strategy (same as mapped conditions above)
            if has_status:
                positive_mask = subset["_cond_status"].isin(
                    ["PRESENT", "HISTORICAL", "HISTORY"])
                subset_positive = subset[positive_mask]
            else:
                subset_positive = subset

            if id_col in subset_positive.columns:
                affected_ids = set(subset_positive[id_col].dropna().unique())
            else:
                affected_ids = set()

            # Respondent-based denominator (avoid closed-world imputation)
            if id_col in subset.columns:
                respondent_ids = set(subset[id_col].dropna().unique())
            else:
                respondent_ids = set()

            n_affected = len(affected_ids & participant_ids) if participant_ids else len(affected_ids)
            if n_affected == 0 and affected_ids:
                n_affected = len(affected_ids)
            n_respondent = len(respondent_ids & participant_ids) if participant_ids else len(respondent_ids)
            if n_respondent == 0 and respondent_ids:
                n_respondent = len(respondent_ids)
            n_unaffected = max(n_respondent - n_affected, 0)
            n_no_data = max(n_participants - n_respondent, 0)

            labels = ["Affected"] * n_affected + ["Unaffected"] * n_unaffected + [None] * n_no_data
            stats = categorical_stats(pd.Series(labels))
            stats["bdc_label"] = disc_code
            stats["topmed_variable"] = None
            stats["dataset"] = "bdc_condition"
            stats["bdc_concept_code"] = disc_code
            stats["n_total"] = n_participants
            stats["visit_label"] = baseline_label
            discovered_key = f"discovered:condition:{disc_code}"
            variable_stats[discovered_key] = stats
            found_vars.append(discovered_key)

            pct = n_affected / n_participants * 100 if n_participants > 0 else 0
            print(f"      {disc_code}: {n_affected:,} affected / "
                  f"{n_respondent:,} with data ({pct:.1f}%)")

    return found_vars


def process_procedures(
    dirs: list[str],
    cohort: str,
    participant_ids: set[str],
    n_participants: int,
    variable_stats: dict,
    visit_mapping: dict[str, str] | None = None,
) -> list[str]:
    """
    Process Procedure.tsv — extract matched procedure variables.
    Returns list of TOPMed variable names found.

    STRATEGY (2026-03-31 update):
    Same as process_conditions() — filter to baseline visits before counting
    "Prior History" for TOPMed comparison.  Post-baseline procedure events
    (e.g., "CHS YEAR 5 coronary angioplasty") are incident procedures, not
    pre-enrollment history.  All-visits count logged for diagnostics.
    See process_conditions() docstring for full rationale.
    """
    print("\n  [Procedure] Loading...")
    df = load_tsv_files(dirs, "*Procedure*.tsv")
    if df.empty:
        print("    No Procedure files found.")
        return []

    concept_col = None
    for col_name in ("procedure_concept", "procedure_type"):
        if col_name in df.columns:
            concept_col = col_name
            break

    if concept_col is None:
        print("    WARNING: No procedure concept column found.", file=sys.stderr)
        print(f"    Available columns: {list(df.columns)}", file=sys.stderr)
        return []

    n_total_rows = len(df)

    df["_proc_concept"] = clean_concept(df[concept_col])

    proc_types = df["_proc_concept"].value_counts()
    print(f"    Procedure concepts found ({len(proc_types)}) across {n_total_rows:,} total rows:")
    for pt, cnt in proc_types.head(20).items():
        mapped = BDC_PROCEDURE_MAP.get(pt, {}).get("bdc_label", "")
        marker = f" → {mapped}" if mapped else ""
        print(f"      {pt}: {cnt:,} rows{marker}")

    # Debug: check participant ID overlap
    id_col = "associated_participant"
    if id_col in df.columns and participant_ids:
        proc_pids = set(df[id_col].dropna().unique())
        overlap = len(proc_pids & participant_ids)
        print(f"    [debug] Procedure participant IDs: {len(proc_pids):,}, "
              f"overlap with Demography: {overlap:,}")
        if overlap == 0 and proc_pids and participant_ids:
            sample_proc = list(proc_pids)[:3]
            sample_demo = list(participant_ids)[:3]
            print(f"    [debug] Sample procedure IDs: {sample_proc}")
            print(f"    [debug] Sample demography IDs: {sample_demo}")

    found_vars = []

    # Clean procedure_status if present (filter ABSENT rows like Conditions)
    has_proc_status = "procedure_status" in df.columns
    if has_proc_status:
        df["_proc_status"] = df["procedure_status"].astype(str).str.strip().str.upper()
        proc_status_counts = df["_proc_status"].value_counts()
        print(f"    procedure_status distribution: {dict(proc_status_counts.head(10))}")
    else:
        print("    WARNING: 'procedure_status' column not found — all rows treated as affected.")

    # ── Baseline visit filtering (same pattern as process_conditions) ─────
    # See process_conditions() for detailed comments on the rationale.
    visit_col = "associated_visit"
    has_visit = visit_col in df.columns

    if has_visit:
        if visit_mapping:
            df["_visit_label"] = df[visit_col].map(
                lambda x: visit_mapping.get(str(x).strip(), str(x).strip())
                if pd.notna(x) else None
            )
        else:
            df["_visit_label"] = df[visit_col]

        visit_dist = df["_visit_label"].value_counts()
        print(f"    Visit distribution across all procedure rows ({len(visit_dist)} visits):")
        for vl, cnt in visit_dist.head(10).items():
            print(f"      {vl}: {cnt:,} rows")

        available_visits = set(df["_visit_label"].dropna().unique())
        matched_baseline = resolve_baseline_visits(cohort, available_visits)

        if matched_baseline:
            baseline_df = df[df["_visit_label"].isin(matched_baseline)]
            baseline_label = " + ".join(matched_baseline)
            print(f"    [baseline filter] Matched: {baseline_label} "
                  f"({len(baseline_df):,} / {len(df):,} rows)")
        else:
            config = BASELINE_VISIT_CONFIG.get(cohort, {})
            print(f"    [baseline filter] WARNING: No baseline visit matched for procedures.")
            print(f"      Expected: {config.get('exact', [])}")
            print(f"      Available: {sorted(available_visits)}")
            print(f"      Falling back to all procedure rows.")
            baseline_df = df
            baseline_label = "all rows (no baseline match)"
    else:
        baseline_df = df
        baseline_label = "all rows (no visit column)"

    # ── Group procedure codes that map to the same TOPMed variable ───────
    # Same pattern as process_conditions(): multiple BDC codes mapping to
    # the same topmed_var must UNION affected participants, not overwrite.
    topmed_var_groups: dict[str, list[str]] = defaultdict(list)
    for bdc_code, spec in BDC_PROCEDURE_MAP.items():
        topmed_var_groups[spec["topmed_var"]].append(bdc_code)

    for topmed_var, bdc_codes in topmed_var_groups.items():
        # L-6 guard: skip if conditions already wrote MEANINGFUL stats for this topmed_var.
        # (CABG and angioplasty appear in both BDC_CONDITION_MAP and BDC_PROCEDURE_MAP.)
        # If conditions wrote 0-affected (100% missing), let procedures overwrite —
        # the variable is likely mapped as Procedure in this cohort, not Condition.
        if topmed_var in variable_stats:
            existing = variable_stats[topmed_var]
            existing_n = existing.get("n_valid", existing.get("n_total", 0) - existing.get("n_missing", 0))
            if existing_n > 0:
                print(f"    [skip] {topmed_var} already set by conditions with "
                      f"{existing_n:,} responses — skipping procedure")
                continue
            else:
                print(f"    [override] {topmed_var} set by conditions with 0 data — "
                      f"overriding from Procedure.tsv")
        spec = BDC_PROCEDURE_MAP[bdc_codes[0]]  # use first for labels
        all_affected_ids: set[str] = set()
        all_respondent_ids: set[str] = set()
        all_visits_affected_ids: set[str] = set()

        # Per-variable visit override (same as process_conditions)
        var_override = CONDITION_PROCEDURE_VISIT_OVERRIDE.get(topmed_var, {}).get(cohort)
        if var_override and has_visit:
            var_baseline_df = df[df["_visit_label"].isin(var_override)]
            var_baseline_label = " + ".join(sorted(set(df["_visit_label"].dropna()) & set(var_override)))
            print(f"    [visit override] {spec['bdc_label']}: using {var_baseline_label} "
                  f"({len(var_baseline_df):,} / {len(df):,} rows)")
        else:
            var_baseline_df = baseline_df
            var_baseline_label = baseline_label

        for bdc_code in bdc_codes:
            cur_spec = BDC_PROCEDURE_MAP[bdc_code]

            # ── All-visits count (diagnostic) ────────────────────────────────
            subset_all = df[df["_proc_concept"] == bdc_code]
            if has_proc_status and not subset_all.empty:
                positive_all = subset_all[subset_all["_proc_status"].isin(
                    ["PRESENT", "HISTORICAL", "HISTORY"])]
            else:
                positive_all = subset_all
            if not positive_all.empty and id_col in positive_all.columns:
                all_visits_affected_ids |= set(positive_all[id_col].dropna().unique())

            # ── Baseline-filtered count (used for comparison) ────────────────
            subset = var_baseline_df[var_baseline_df["_proc_concept"] == bdc_code]

            if has_proc_status and not subset.empty:
                positive_mask = subset["_proc_status"].isin(["PRESENT", "HISTORICAL", "HISTORY"])
                subset_positive = subset[positive_mask]
            else:
                subset_positive = subset

            n_total_concept = len(subset_all)
            n_baseline_rows = len(subset)
            n_positive = len(subset_positive)

            # Fallback: if baseline yields nothing but all-visits has data
            if n_positive == 0 and len(positive_all) > 0:
                print(f"    {cur_spec['bdc_label']} ({bdc_code}): "
                      f"0 positive at baseline, {len(positive_all):,} across all visits "
                      f"-- FALLING BACK to all-visits")
                subset_positive = positive_all

            print(f"    {cur_spec['bdc_label']} ({bdc_code}): "
                  f"{n_total_concept:,} total rows, {n_baseline_rows:,} at baseline, "
                  f"{n_positive:,} positive [visit: {var_baseline_label}]")

            if not subset_positive.empty and id_col in subset_positive.columns:
                all_affected_ids |= set(subset_positive[id_col].dropna().unique())

            # Collect ALL respondent IDs (any status) from same scope
            if n_positive == 0 and len(positive_all) > 0:
                respondent_src = subset_all
            else:
                respondent_src = subset
            if not respondent_src.empty and id_col in respondent_src.columns:
                all_respondent_ids |= set(respondent_src[id_col].dropna().unique())

        # ── Compute stats from UNION of all codes in this group ──────────
        affected_ids = all_affected_ids
        respondent_ids = all_respondent_ids

        # Try participant ID intersection; fall back to direct count if IDs
        # are in different formats (e.g. UUIDs in Procedure vs subject IDs in Demography).
        overlap = affected_ids & participant_ids if participant_ids else set()
        overlap_rate = len(overlap) / len(affected_ids) if affected_ids else 1.0
        if overlap and overlap_rate >= 0.5:
            n_affected = len(overlap)
            n_respondent = len(respondent_ids & participant_ids) if participant_ids else len(respondent_ids)
        else:
            if overlap and overlap_rate < 0.5:
                print(f"    [debug] Low participant ID overlap ({overlap_rate:.0%} of "
                      f"procedure IDs match Demography) — using direct count from procedure data")
            n_affected = len(affected_ids)
            n_respondent = len(respondent_ids)
        if n_respondent == 0 and respondent_ids:
            n_respondent = len(respondent_ids)
        n_unaffected = n_respondent - n_affected if n_respondent > 0 else 0
        n_unaffected = max(n_unaffected, 0)
        n_no_data = max(n_participants - n_respondent, 0) if n_participants > 0 else 0

        if n_no_data > 0 and n_participants > 0:
            print(f"    [missing] {spec['bdc_label']}: {n_respondent:,} with data, "
                  f"{n_no_data:,} no record ({n_no_data/n_participants*100:.1f}%)")

        labels = (
            ["Prior History"] * n_affected +
            ["No Prior History"] * n_unaffected +
            [None] * n_no_data
        )
        binary_series = pd.Series(labels)

        bdc_code_str = ", ".join(bdc_codes)
        stats = categorical_stats(binary_series)
        stats["bdc_label"] = spec["bdc_label"]
        stats["topmed_variable"] = topmed_var
        stats["dataset"] = "atherosclerosis_events_prior"
        stats["bdc_concept_code"] = bdc_code_str
        stats["n_total"] = n_participants
        stats["visit_label"] = var_baseline_label
        variable_stats[topmed_var] = stats
        found_vars.append(topmed_var)

        # ── Diagnostic: baseline vs all-visits comparison ────────────────
        n_all_visits = len(all_visits_affected_ids & participant_ids) if participant_ids else len(all_visits_affected_ids)
        if n_all_visits == 0 and all_visits_affected_ids:
            n_all_visits = len(all_visits_affected_ids)
        delta = n_all_visits - n_affected
        if delta > 0 and n_participants > 0:
            print(f"    [diagnostic] {spec['bdc_label']}: baseline={n_affected:,} "
                  f"({n_affected/n_participants*100:.1f}%), "
                  f"all-visits={n_all_visits:,} "
                  f"({n_all_visits/n_participants*100:.1f}%), "
                  f"delta=+{delta:,} incident/follow-up cases excluded")

        if len(bdc_codes) > 1:
            print(f"    {spec['bdc_label']} (merged: {bdc_code_str}): {n_affected:,} affected / "
                  f"{n_participants:,} total ({n_affected/n_participants*100:.1f}%)"
                  if n_participants > 0 else
                  f"    {spec['bdc_label']} (merged: {bdc_code_str}): {n_affected:,} affected")
        else:
            print(f"    {spec['bdc_label']} ({bdc_codes[0]}): {n_affected:,} affected / "
                  f"{n_participants:,} total ({n_affected/n_participants*100:.1f}%)"
                  if n_participants > 0 else
                  f"    {spec['bdc_label']} ({bdc_codes[0]}): {n_affected:,} affected")

    # ── Discover ALL remaining procedure concepts not in BDC_PROCEDURE_MAP ──
    # Use baseline_df (not df) so discovered procedures are also baseline-filtered,
    # consistent with the mapped procedures above (C-2 fix).
    known_proc_codes = set(BDC_PROCEDURE_MAP.keys())
    all_proc_types = set(baseline_df["_proc_concept"].dropna().unique())
    discovered_procs = sorted(all_proc_types - known_proc_codes)

    if discovered_procs:
        print(f"\n    [Discovery] Processing {len(discovered_procs)} additional procedure concepts...")

        for disc_code in discovered_procs:
            subset = baseline_df[baseline_df["_proc_concept"] == disc_code]
            if subset.empty:
                continue

            # "Ever positive" strategy (same as mapped procedures above)
            if has_proc_status:
                positive_mask = subset["_proc_status"].isin(
                    ["PRESENT", "HISTORICAL", "HISTORY"])
                subset_positive = subset[positive_mask]
            else:
                subset_positive = subset

            if id_col in subset_positive.columns:
                affected_ids = set(subset_positive[id_col].dropna().unique())
            else:
                affected_ids = set()

            # Respondent-based denominator (avoid closed-world imputation)
            if id_col in subset.columns:
                respondent_ids = set(subset[id_col].dropna().unique())
            else:
                respondent_ids = set()

            overlap = affected_ids & participant_ids if participant_ids else set()
            overlap_rate = len(overlap) / len(affected_ids) if affected_ids else 1.0
            n_affected = len(overlap) if (overlap and overlap_rate >= 0.5) else len(affected_ids)
            if overlap and overlap_rate >= 0.5:
                n_respondent = len(respondent_ids & participant_ids) if participant_ids else len(respondent_ids)
            else:
                n_respondent = len(respondent_ids)
            if n_respondent == 0 and respondent_ids:
                n_respondent = len(respondent_ids)
            n_unaffected = max(n_respondent - n_affected, 0)
            n_no_data = max(n_participants - n_respondent, 0)

            labels = ["Affected"] * n_affected + ["Unaffected"] * n_unaffected + [None] * n_no_data
            stats = categorical_stats(pd.Series(labels))
            stats["bdc_label"] = disc_code
            stats["topmed_variable"] = None
            stats["dataset"] = "bdc_procedure"
            stats["bdc_concept_code"] = disc_code
            stats["n_total"] = n_participants
            stats["visit_label"] = baseline_label
            discovered_key = f"discovered:procedure:{disc_code}"
            variable_stats[discovered_key] = stats
            found_vars.append(discovered_key)

            pct = n_affected / n_participants * 100 if n_participants > 0 else 0
            print(f"      {disc_code}: {n_affected:,} affected / "
                  f"{n_respondent:,} with data ({pct:.1f}%)")

    return found_vars


def process_observations(
    dirs: list[str],
    cohort: str,
    participant_ids: set[str],
    n_participants: int,
    variable_stats: dict,
    visit_mapping: dict[str, str] | None = None,
) -> list[str]:
    """
    Process Observation.tsv — extract smoking status and other observations.
    Returns list of TOPMed variable names found.
    """
    print("\n  [Observation] Loading...")
    # Use exact filename to avoid matching MeasurementObservation.tsv
    df = load_tsv_files(dirs, "Observation.tsv")
    if df.empty:
        print("    No Observation files found.")
        return []

    if "observation_type" not in df.columns:
        print("    WARNING: 'observation_type' column missing.", file=sys.stderr)
        return []

    df["_obs_type"] = clean_concept(df["observation_type"])

    obs_types = df["_obs_type"].value_counts()
    print(f"    Observation types found ({len(obs_types)}):")
    for ot, cnt in obs_types.head(10).items():
        print(f"      {ot}: {cnt:,} rows")

    found_vars = []

    # ── Smoking status ──
    smoking_df = df[df["_obs_type"] == SMOKING_OBSERVATION_TYPE]
    if not smoking_df.empty:
        # Select baseline visit — use smoking-specific override if available,
        # otherwise fall back to BASELINE_VISIT_CONFIG.
        smoking_override = SMOKING_VISIT_OVERRIDE.get(cohort)
        try:
            baseline, visit_used = _select_baseline_visit(smoking_df, cohort,
                                                           visit_mapping=visit_mapping,
                                                           override_visits=smoking_override)
        except ValueError:
            print(f"    Smoking ({SMOKING_OBSERVATION_TYPE}): SKIPPED — no baseline visit data")
            baseline = smoking_df.head(0)  # empty DF so downstream code is safe
            visit_used = "none"

        # Get the value column — could be value_enum or value_string
        value_col = None
        for col in ("value_enum", "value_string", "value_quantity__value_decimal"):
            if col in baseline.columns:
                value_col = col
                break

        # Deduplicate per participant — prefer rows with non-null values
        # (multi-block YAML produces one NULL + one valued row per participant)
        # Use explicit clinical priority: Current > Former > Never > Unknown > null
        id_col = "associated_participant"
        if id_col in baseline.columns and value_col:
            _smoking_priority = {
                "OMOP:40766945": 0,  # Current smoker (highest priority)
                "OMOP:45883458": 1,  # Former smoker
                "OMOP:45883537": 2,  # Never smoked
                "OMOP:45885135": 3,  # Unknown
            }
            baseline["_sort_priority"] = (
                clean_concept(baseline[value_col])
                .map(_smoking_priority)
                .fillna(4)  # unmapped or null → lowest priority
            )
            baseline = baseline.sort_values(
                by="_sort_priority", na_position="last"
            ).drop_duplicates(subset=[id_col], keep="first")
            baseline = baseline.drop(columns=["_sort_priority"])

        if value_col:
            baseline["_smoking_label"] = clean_concept(baseline[value_col]).map(
                lambda x: OMOP_SMOKING_MAP.get(x, f"UNMAPPED:{x}") if pd.notna(x) else None
            )

            # Ever smoker: Current Smoker or Former Smoker → "Ever Smoked"
            ever_map = {
                "Current Smoker": "Ever Smoked",
                "Former Smoker": "Ever Smoked",
                "Never Smoked": "Never Smoked",
                "Unknown": None,
            }
            baseline["_ever_smoker"] = baseline["_smoking_label"].map(
                lambda x: ever_map.get(x) if pd.notna(x) else None
            )

            # Current smoker: Current Smoker → "Current Smoker", else "Not Current Smoker"
            current_map = {
                "Current Smoker": "Current Smoker",
                "Former Smoker": "Not Current Smoker",
                "Never Smoked": "Not Current Smoker",
                "Unknown": None,
            }
            baseline["_current_smoker"] = baseline["_smoking_label"].map(
                lambda x: current_map.get(x) if pd.notna(x) else None
            )

            # Compute stats directly from baseline-filtered data.
            # Don't reindex to Demography IDs — format may differ.
            ever_full = baseline["_ever_smoker"]
            current_full = baseline["_current_smoker"]

            # Ever smoker stats
            stats = categorical_stats(ever_full)
            stats["bdc_label"] = "Ever smoker"
            stats["topmed_variable"] = "ever_smoker_baseline_1"
            stats["dataset"] = "baseline_covariates"
            stats["visit_label"] = visit_used
            stats["n_total"] = n_participants
            stats["n_missing"] = n_participants - stats["n_valid"]
            stats["pct_missing"] = round(
                stats["n_missing"] / n_participants * 100, 1
            ) if n_participants > 0 else 0.0
            variable_stats["ever_smoker_baseline_1"] = stats
            found_vars.append("ever_smoker_baseline_1")

            # Current smoker stats
            stats2 = categorical_stats(current_full)
            stats2["bdc_label"] = "Current smoker"
            stats2["topmed_variable"] = "current_smoker_baseline_1"
            stats2["dataset"] = "baseline_covariates"
            stats2["visit_label"] = visit_used
            stats2["n_total"] = n_participants
            stats2["n_missing"] = n_participants - stats2["n_valid"]
            stats2["pct_missing"] = round(
                stats2["n_missing"] / n_participants * 100, 1
            ) if n_participants > 0 else 0.0
            variable_stats["current_smoker_baseline_1"] = stats2
            found_vars.append("current_smoker_baseline_1")

            n_smokers = int(baseline["_smoking_label"].notna().sum())
            smoking_dist = baseline["_smoking_label"].value_counts()
            print(f"    Smoking ({SMOKING_OBSERVATION_TYPE}): {n_smokers:,} records "
                  f"[visit: {visit_used}]")
            print(f"    [debug] Smoking label distribution: {dict(smoking_dist)}")

    # ── Discover ALL remaining observation types not handled above ──
    known_obs_types = {SMOKING_OBSERVATION_TYPE}
    all_obs_types = set(df["_obs_type"].dropna().unique())
    discovered_obs = sorted(all_obs_types - known_obs_types)

    if discovered_obs:
        print(f"\n    [Discovery] Processing {len(discovered_obs)} additional observation types...")

        for disc_code in discovered_obs:
            subset = df[df["_obs_type"] == disc_code]
            if subset.empty:
                continue

            # Select baseline visit — skip gracefully if this discovered
            # observation type has no rows at baseline visits.
            try:
                baseline, visit_used = _select_baseline_visit(
                    subset, cohort, visit_mapping=visit_mapping)
            except Exception as exc:
                print(f"      {disc_code}: skipped (no baseline data: {type(exc).__name__})")
                continue

            # Dedup per participant — coalesce (first non-null per column)
            id_col = "associated_participant"
            if id_col in baseline.columns:
                internal_cols = [c for c in baseline.columns if c.startswith("_")]
                data_cols = [c for c in baseline.columns
                             if c != id_col and c not in internal_cols]
                baseline = (
                    baseline
                    .groupby(id_col, sort=False)
                    .agg({col: "first" for col in data_cols})
                    .reset_index()
                )

            if baseline.empty:
                continue

            var_key = disc_code

            # Try to find the best value column
            value_col = None
            for col_name in ("value_quantity__value_decimal", "value_enum",
                             "value_string"):
                if col_name in baseline.columns and baseline[col_name].notna().any():
                    value_col = col_name
                    break

            is_continuous = False
            numeric_vals = pd.Series(dtype=float)
            if value_col == "value_quantity__value_decimal":
                numeric_vals = pd.to_numeric(baseline[value_col], errors="coerce")
                n_numeric = int(numeric_vals.notna().sum())
                n_non_null = int(baseline[value_col].notna().sum())
                if n_non_null > 0 and n_numeric / n_non_null >= 0.5:
                    is_continuous = True

            if is_continuous:
                stats = continuous_stats(numeric_vals)
                stats["n_total"] = n_participants
                stats["n_missing"] = n_participants - stats["n_valid"]
                stats["pct_missing"] = round(
                    stats["n_missing"] / n_participants * 100, 1
                ) if n_participants > 0 else 0.0
            elif value_col:
                cat_series = baseline[value_col].dropna()
                stats = categorical_stats(cat_series)
                stats["n_total"] = n_participants
                stats["n_missing"] = n_participants - stats["n_valid"]
                stats["pct_missing"] = round(
                    stats["n_missing"] / n_participants * 100, 1
                ) if n_participants > 0 else 0.0
            else:
                # No usable value column — report presence count only
                stats = {
                    "type": "categorical",
                    "n_total": n_participants,
                    "n_valid": len(baseline),
                    "n_missing": n_participants - len(baseline),
                    "pct_missing": round(
                        (n_participants - len(baseline)) / n_participants * 100, 1
                    ) if n_participants > 0 else 0.0,
                    "distribution": {"present": {"n": len(baseline),
                                                  "pct": round(len(baseline) / n_participants * 100, 1)
                                                  if n_participants > 0 else 0.0,
                                                  "pct_of_total": round(len(baseline) / n_participants * 100, 1)
                                                  if n_participants > 0 else 0.0}},
                }

            stats["bdc_label"] = disc_code
            stats["topmed_variable"] = None
            stats["dataset"] = "bdc_observation"
            stats["visit_label"] = visit_used
            stats["bdc_concept_code"] = disc_code
            discovered_key = f"discovered:observation:{var_key}"
            variable_stats[discovered_key] = stats
            found_vars.append(discovered_key)

            type_tag = stats["type"]
            n_valid = stats["n_valid"]
            print(f"      {disc_code}: {len(baseline):,} participants "
                  f"({type_tag}, n_valid={n_valid:,}) [visit: {visit_used}]")

    return found_vars


def process_drugs(
    dirs: list[str],
    cohort: str,
    participant_ids: set[str],
    n_participants: int,
    baseline_meas_ids: set,
    variable_stats: dict,
    visit_mapping: dict[str, str] | None = None,
) -> list[str]:
    """
    Process DrugExposure.tsv — report drug concept distribution.
    Currently informational since TOPMed DCC uses binary medication flags
    (antihypertensive_meds_1, lipid_lowering_medication_1) which aggregate
    multiple drug classes. We report individual BDC drug concepts.

    Filters to baseline visit only for fair comparison with TOPMed DCC
    (which only reports baseline values).

    baseline_meas_ids: participants present in ANY baseline measurement (from
    process_measurements). Used as the denominator for binary medication stats
    so participants who never attended the baseline visit are counted as
    missing rather than falsely coded "No".

    Returns list of variable names found.
    """
    print("\n  [DrugExposure] Loading...")
    df = load_tsv_files(dirs, "*DrugExposure*.tsv")
    if df.empty:
        print("    No DrugExposure files found.")
        return []

    concept_col = None
    for col_name in ("drug_concept", "drug_type"):
        if col_name in df.columns:
            concept_col = col_name
            break

    if concept_col is None:
        print("    WARNING: No drug concept column found.", file=sys.stderr)
        print(f"    Available columns: {list(df.columns)}", file=sys.stderr)
        return []

    df["_drug_concept"] = clean_concept(df[concept_col])
    drug_types = df["_drug_concept"].value_counts()
    print(f"    Drug concepts found ({len(drug_types)}):")

    # Antihypertensive drug ATC classes
    antihypertensive_atcs = {"ATC:C09A", "ATC:C09C", "ATC:C07A", "ATC:C03", "ATC:C02"}
    # Lipid-lowering drug ATC classes
    lipid_lowering_atcs = {"ATC:C10A", "ATC:C10B"}

    id_col = "associated_participant"
    found_vars = []

    for dt, cnt in drug_types.items():
        print(f"      {dt}: {cnt:,} rows")

    # ── Clean exposure_status (filter ABSENT rows, like Conditions) ──────
    has_exposure_status = "exposure_status" in df.columns
    if has_exposure_status:
        df["_exp_status"] = df["exposure_status"].astype(str).str.strip().str.upper()
        n_before = len(df)
        df = df[df["_exp_status"].isin(["PRESENT", "HISTORICAL", "HISTORY"])]
        n_dropped = n_before - len(df)
        if n_dropped > 0:
            print(f"    [exposure_status filter] {n_before:,} → {len(df):,} rows "
                  f"(dropped {n_dropped:,} ABSENT/other)")
        if df.empty:
            print("    No active drug exposures after status filter — skipping.")
            return []

    # ── Baseline visit filter ────────────────────────────────────────────
    # Filter drug rows to baseline visit only for fair comparison with
    # TOPMed DCC (which only reports baseline medication status).
    #
    # IMPORTANT: DrugExposure differs from MeasurementObservation — each
    # participant has MULTIPLE rows (one per drug class). Using the generic
    # _select_baseline_visit() would work for visit filtering, but the
    # downstream dedup logic in process_measurements (one row per participant)
    # would reduce each participant to exactly 1 drug row, destroying most
    # of the drug data.
    #
    # Strategy:
    #   A) If baseline visits can be identified by label (normal path for all
    #      cohorts with named visits), filter to those visits keeping ALL rows.
    #   B) If no visit label match (e.g. all visits = "HEALTH_EXAMINATION"),
    #      use age_at_observation to identify each participant's minimum age
    #      (= their Exam 1 / baseline), then keep ALL drug rows for those
    #      participants at that age. Falls back to keeping all rows if age
    #      is unavailable.
    n_pre_filter = len(df)

    # Translate visit UUIDs to labels if mapping is available
    visit_col = "associated_visit"
    if visit_col in df.columns and visit_mapping:
        df = df.copy()
        df["_visit_label"] = df[visit_col].map(
            lambda x: visit_mapping.get(str(x).strip(), str(x).strip())
            if pd.notna(x) else None
        )
        label_col = "_visit_label"
    else:
        label_col = visit_col if visit_col in df.columns else None

    visit_used = "all-visits (no filter)"
    if label_col and label_col in df.columns:
        available = set(df[label_col].dropna().unique())
        matched_prefs = resolve_baseline_visits(cohort, available)

        if matched_prefs:
            # Path A: named baseline visits found — keep ALL rows for those visits
            df = df[df[label_col].isin(matched_prefs)]
            visit_used = " + ".join(matched_prefs) if len(matched_prefs) > 1 else matched_prefs[0]
        else:
            config = BASELINE_VISIT_CONFIG.get(cohort, {})
            print(f"    [baseline filter] WARNING: No baseline visit matched for drugs.")
            print(f"      Expected: {config.get('exact', [])}")
            print(f"      Available: {sorted(available)}")
            print(f"      Falling back to all drug rows.")
            # Don't filter — use all rows
            visit_used = "all rows (no baseline match)"

    print(f"    Antihypertensive meds (aggregated): {n_pre_filter:,} -> {len(df):,} rows "
          f"after baseline filter [visit: {visit_used}]")

    # Aggregate antihypertensive medication (binary: any antihypertensive → Yes)
    # Denominator: participants present in any baseline measurement (baseline_meas_ids).
    # Participants NOT in baseline_meas_ids never attended the baseline visit and
    # are treated as missing rather than "No" (closed-world assumption avoided).
    if id_col in df.columns:
        # Effective denominator: participants at baseline with any measurement
        med_denom_ids = baseline_meas_ids if baseline_meas_ids else participant_ids
        n_med_denom = len(med_denom_ids)
        if n_med_denom == 0:
            n_med_denom = n_participants

        antihyp_df = df[df["_drug_concept"].isin(antihypertensive_atcs)]
        if not antihyp_df.empty:
            antihyp_ids = set(antihyp_df[id_col].dropna().unique())
            n_on_med = len(antihyp_ids & med_denom_ids) if med_denom_ids else len(antihyp_ids)
            n_off_med = n_med_denom - n_on_med
            n_missing_med = n_participants - n_med_denom

            labels = ["Yes"] * n_on_med + ["No"] * n_off_med
            stats = categorical_stats(pd.Series(labels))
            stats["bdc_label"] = "Hypertension treatment"
            stats["topmed_variable"] = "antihypertensive_meds_1"
            stats["dataset"] = "blood_pressure"
            stats["n_total"] = n_participants
            # Override missingness to reflect participants outside baseline
            stats["n_missing"] = n_missing_med
            stats["pct_missing"] = round(n_missing_med / n_participants * 100, 1) if n_participants > 0 else 0.0
            variable_stats["antihypertensive_meds_1"] = stats
            found_vars.append("antihypertensive_meds_1")

            print(f"    Antihypertensive meds (aggregated): {n_on_med:,} / "
                  f"{n_med_denom:,} baseline participants "
                  f"({n_on_med/n_med_denom*100:.1f}%); "
                  f"{n_missing_med:,} outside baseline → missing"
                  if n_med_denom > 0 else "")

        # Aggregate lipid-lowering medication
        lipid_df = df[df["_drug_concept"].isin(lipid_lowering_atcs)]
        if not lipid_df.empty:
            lipid_ids = set(lipid_df[id_col].dropna().unique())
            n_on_lipid = len(lipid_ids & med_denom_ids) if med_denom_ids else len(lipid_ids)
            n_off_lipid = n_med_denom - n_on_lipid
            n_missing_lipid = n_participants - n_med_denom

            labels = ["Yes"] * n_on_lipid + ["No"] * n_off_lipid
            stats = categorical_stats(pd.Series(labels))
            stats["bdc_label"] = "Lipid-lowering medication"
            stats["topmed_variable"] = "lipid_lowering_medication_1"
            stats["dataset"] = "lipids"
            stats["n_total"] = n_participants
            stats["n_missing"] = n_missing_lipid
            stats["pct_missing"] = round(n_missing_lipid / n_participants * 100, 1) if n_participants > 0 else 0.0
            variable_stats["lipid_lowering_medication_1"] = stats
            found_vars.append("lipid_lowering_medication_1")

            print(f"    Lipid-lowering meds (aggregated): {n_on_lipid:,} / "
                  f"{n_med_denom:,} baseline participants "
                  f"({n_on_lipid/n_med_denom*100:.1f}%); "
                  f"{n_missing_lipid:,} outside baseline → missing"
                  if n_med_denom > 0 else "")

    # ── Per-concept drug exposure stats (all individual drug concepts) ──
    # Use n_med_denom (baseline measurement participants) as denominator,
    # consistent with the aggregated antihypertensive/lipid stats above (M-6 fix).
    if id_col in df.columns:
        # n_med_denom and med_denom_ids are always defined above in this same
        # 'if id_col in df.columns' block — no guard needed (C-2 fix).
        _drug_denom = n_med_denom
        _drug_denom_ids = med_denom_ids

        aggregated_atcs = antihypertensive_atcs | lipid_lowering_atcs
        all_drug_types = set(df["_drug_concept"].dropna().unique())
        individual_drugs = sorted(all_drug_types - aggregated_atcs)

        if individual_drugs:
            print(f"\n    [Discovery] Processing {len(individual_drugs)} individual drug concepts...")

            for disc_code in individual_drugs:
                drug_subset = df[df["_drug_concept"] == disc_code]
                if drug_subset.empty:
                    continue

                drug_pids = set(drug_subset[id_col].dropna().unique())
                overlap = drug_pids & _drug_denom_ids if _drug_denom_ids else set()
                n_on = len(overlap) if overlap else len(drug_pids)
                n_off = max(_drug_denom - n_on, 0)
                n_missing_drug = max(n_participants - _drug_denom, 0)

                labels = ["Exposed"] * n_on + ["Not Exposed"] * n_off
                stats = categorical_stats(pd.Series(labels))
                stats["bdc_label"] = disc_code
                stats["topmed_variable"] = None
                stats["dataset"] = "bdc_drug_exposure"
                stats["bdc_concept_code"] = disc_code
                stats["n_total"] = n_participants
                stats["n_missing"] = n_missing_drug
                stats["pct_missing"] = round(n_missing_drug / n_participants * 100, 1) if n_participants > 0 else 0.0
                discovered_key = f"discovered:drug:{disc_code}"
                variable_stats[discovered_key] = stats
                found_vars.append(discovered_key)

                pct = n_on / _drug_denom * 100 if _drug_denom > 0 else 0
                print(f"      {disc_code}: {n_on:,} exposed / "
                      f"{_drug_denom:,} baseline ({pct:.1f}%)")

    return found_vars


# ─────────────────────────────────────────────────────────────────────────────
# DATA QUALITY CHECKS
# ─────────────────────────────────────────────────────────────────────────────

def run_dq_checks(
    cohort: str,
    variable_stats: dict,
    n_participants: int,
) -> list[str]:
    """Run data quality checks and return flag strings."""
    flags: list[str] = []

    if n_participants == 0:
        flags.append(f"CRITICAL: No participants found for {cohort}")
        return flags

    # Participant count for WHI
    if cohort == "WHI" and (n_participants < 130_000 or n_participants > 170_000):
        flags.append(
            f"WARNING: N={n_participants:,} outside expected WHI range (130,000–170,000)"
        )

    # Check for high missingness (> 50%)
    for var_name, stats in variable_stats.items():
        pct_missing = stats.get("pct_missing", 0.0)
        if pct_missing > 50:
            flags.append(
                f"WARNING: {stats.get('bdc_label', var_name)} has {pct_missing:.1f}% missing "
                f"({stats.get('n_missing', 0):,}/{stats.get('n_total', 0):,})"
            )

    # Check for implausible continuous values
    for var_name, stats in variable_stats.items():
        if stats.get("type") == "continuous":
            n_imp = stats.get("n_implausible", 0)
            if n_imp > 0:
                flags.append(
                    f"WARNING: {stats.get('bdc_label', var_name)} has {n_imp:,} "
                    f"implausible values"
                )

    # Check for UNMAPPED categorical values
    for var_name, stats in variable_stats.items():
        if stats.get("type") == "categorical":
            dist = stats.get("distribution", {})
            unmapped = [k for k in dist if k.startswith("UNMAPPED:")]
            if unmapped:
                flags.append(
                    f"WARNING: {stats.get('bdc_label', var_name)} has unmapped values: "
                    f"{unmapped}"
                )

    if not flags:
        flags.append(f"OK: No data quality issues detected for {cohort}")

    return flags


# ─────────────────────────────────────────────────────────────────────────────
# CONSOLE REPORT
# ─────────────────────────────────────────────────────────────────────────────

def print_cohort_summary(result: dict) -> None:
    """Print a human-readable summary of results."""
    cohort = result["cohort"]["name"]
    n = result["total_participants"]
    variables = result["variables"]

    print(f"\n  {'═' * 60}")
    print(f"  {cohort} BDC SUMMARY ({n:,} participants)")
    print(f"  {'═' * 60}")

    for var_name, stats in sorted(variables.items()):
        bdc_label = stats.get("bdc_label", var_name)
        if stats["type"] == "categorical":
            dist = stats.get("distribution", {})
            n_valid = stats["n_valid"]
            n_missing = stats["n_missing"]
            cats_str = ", ".join(
                f"{k}: {v['n']:,} ({v['pct']:.1f}%)"
                for k, v in sorted(dist.items())
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
            visit = stats.get("visit_label", "")
            visit_tag = f" [{visit}]" if visit else ""
            print(
                f"    {bdc_label:<35} n={n_valid:,}  miss={n_missing:,}  "
                f"mean={mean_str} ± {sd_str} {unit}{visit_tag}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract aggregate summary statistics from BDC dm-bip harmonized TSV output "
            "for comparison with TOPMed DCC summaries."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--mapped-data-dirs",
        nargs="+",
        metavar="DIR",
        default=None,
        help=(
            "One or more mapped-data directories from dm-bip output. "
            "Specify one per consent group (e.g., WHI_c1/mapped-data WHI_c2/mapped-data). "
            "If omitted, auto-discovered from --base-dir using the cohort name. "
            "Only valid with single-cohort mode (--cohort)."
        ),
    )
    parser.add_argument(
        "--cohort",
        required=False,
        default=None,
        metavar="NAME",
        help=(
            "Single cohort name (e.g., WHI, ARIC, FHS). "
            "Mutually exclusive with --cohorts."
        ),
    )
    parser.add_argument(
        "--cohorts",
        nargs="+",
        metavar="NAME",
        default=None,
        help=(
            "One or more cohort names to process (e.g., --cohorts ARIC CHS WHI). "
            "Mutually exclusive with --cohort."
        ),
    )
    parser.add_argument(
        "--base-dir",
        metavar="DIR",
        default=".",
        help=(
            "Root directory to search for DMC_*_<COHORT>_Processed_* folders. "
            "Defaults to current directory. When no cohort is specified, all "
            "cohorts found under this directory are processed."
        ),
    )
    parser.add_argument(
        "--output-dir",
        metavar="DIR",
        default=None,
        help=(
            "Directory for the output JSON summary file. "
            "Defaults to --base-dir if not specified."
        ),
    )
    parser.add_argument(
        "--log-file",
        metavar="FILE",
        default=None,
        help=(
            "Path for the log file capturing all console output. "
            "Defaults to <output-dir>/bdc_<cohort>_extract.log"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # ── Resolve cohort list ──────────────────────────────────────────────────
    if args.cohort and args.cohorts:
        print("ERROR: --cohort and --cohorts are mutually exclusive.", file=sys.stderr)
        sys.exit(1)

    if args.mapped_data_dirs and not args.cohort:
        print("ERROR: --mapped-data-dirs requires --cohort (single cohort mode).",
              file=sys.stderr)
        sys.exit(1)

    if args.cohort:
        cohort_list = [normalize_cohort_name(args.cohort)]
    elif args.cohorts:
        cohort_list = [normalize_cohort_name(c) for c in args.cohorts]
    else:
        # Default: auto-discover all cohorts from --base-dir
        cohort_list = discover_all_cohorts(args.base_dir)
        if not cohort_list:
            print(f"ERROR: No DMC_*_Processed_* directories found under "
                  f"'{Path(args.base_dir).resolve()}'.", file=sys.stderr)
            print("  Specify --cohort NAME, --cohorts NAME [NAME ...], or "
                  "check --base-dir.", file=sys.stderr)
            sys.exit(1)
        print(f"  Auto-discovered {len(cohort_list)} cohort(s): {', '.join(cohort_list)}")

    # ── Process each cohort ──────────────────────────────────────────────────
    results: dict[str, str] = {}  # cohort → output JSON path
    failures: list[str] = []

    for cohort in cohort_list:
        try:
            output_path = extract_one_cohort(
                cohort=cohort,
                base_dir=args.base_dir,
                mapped_data_dirs=args.mapped_data_dirs,
                output_dir=args.output_dir,
                log_file=args.log_file,
            )
            results[cohort] = output_path
        except SystemExit:
            failures.append(cohort)
        except Exception as exc:
            print(f"\n  ERROR processing {cohort}: {exc}", file=sys.stderr)
            failures.append(cohort)

    # ── Multi-cohort summary ─────────────────────────────────────────────────
    if len(cohort_list) > 1:
        print("\n" + "=" * 60)
        print("  BATCH EXTRACTION SUMMARY")
        print("=" * 60)
        print(f"  Cohorts requested: {len(cohort_list)}")
        print(f"  Succeeded: {len(results)}")
        if failures:
            print(f"  Failed: {len(failures)} — {', '.join(failures)}")
        for c, path in sorted(results.items()):
            print(f"    {c:12s} → {path}")
        print("=" * 60)

    if failures:
        sys.exit(1)


def extract_one_cohort(
    cohort: str,
    base_dir: str,
    mapped_data_dirs: list[str] | None,
    output_dir: str | None,
    log_file: str | None,
) -> str:
    """Run the full extraction pipeline for a single cohort. Returns output JSON path."""

    # ── Resolve mapped-data directories ──────────────────────────────────────
    if mapped_data_dirs:
        dirs = mapped_data_dirs
    else:
        dirs = discover_mapped_data_dirs(base_dir, cohort)
        if not dirs:
            print(f"ERROR: No mapped-data directories found for '{cohort}' "
                  f"under '{Path(base_dir).resolve()}'.", file=sys.stderr)
            print(f"  Looked for: DMC_*_{cohort}_Processed_*/*_BDCHM/mapped-data  (case-insensitive)",
                  file=sys.stderr)
            print(f"  Either specify --mapped-data-dirs explicitly, or check --base-dir.",
                  file=sys.stderr)
            raise SystemExit(1)

    # ── Timestamp for output filenames ────────────────────────────────────────
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── Set up log file capture (Tee: screen + file simultaneously) ──────────
    out_dir = Path(output_dir) if output_dir else Path(base_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = Path(log_file) if log_file else out_dir / f"bdc_{cohort.lower()}_extract_{run_ts}.log"
    log_fh = open(log_path, "w", encoding="utf-8")
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    sys.stdout = Tee(original_stdout, log_fh)
    sys.stderr = Tee(original_stderr, log_fh)

    try:

        print("=" * 60)
        print(f"  BDC DMC Summary Extraction: {cohort}")
        print("=" * 60)
        print(f"  Input directories ({len(dirs)}):")
        for d in dirs:
            print(f"    {d}")

        variable_stats: dict[str, dict] = {}
        datasets_loaded: list[str] = []
        vars_by_dataset: dict[str, list[str]] = {}

        # ── Load visit mapping ONCE for all processors (M-6 fix) ────────────────
        visit_mapping = load_visit_mapping(dirs)

        # ── Step 1: Demography (establishes participant universe) ────────────────
        participant_ids, n_participants = process_demography(dirs, cohort, variable_stats, visit_mapping=visit_mapping)
        if n_participants > 0:
            datasets_loaded.append("demographics")
            vars_by_dataset["demographics"] = [
                v for v in variable_stats if variable_stats[v].get("dataset") == "demographics"
            ]

        # ── Step 2: MeasurementObservation ──────────────────────────────────────
        # baseline_meas_ids = participants present at baseline in ANY measurement;
        # used as denominator for medication binary variables to avoid forcing
        # participants who never attended the baseline visit into the "No" bucket.
        meas_vars, baseline_meas_ids = process_measurements(dirs, cohort, participant_ids, n_participants, variable_stats, visit_mapping=visit_mapping)
        if meas_vars:
            datasets_loaded.append("measurements")
            vars_by_dataset["measurements"] = meas_vars

        # ── Step 3: Conditions ──────────────────────────────────────────────────
        cond_vars = process_conditions(dirs, cohort, participant_ids, n_participants, variable_stats, visit_mapping=visit_mapping)
        if cond_vars:
            datasets_loaded.append("conditions")
            vars_by_dataset["conditions"] = cond_vars

        # ── Step 4: Procedures ──────────────────────────────────────────────────
        proc_vars = process_procedures(dirs, cohort, participant_ids, n_participants, variable_stats, visit_mapping=visit_mapping)
        if proc_vars:
            datasets_loaded.append("procedures")
            vars_by_dataset["procedures"] = proc_vars

        # ── Step 5: Observations (Smoking) ──────────────────────────────────────
        obs_vars = process_observations(dirs, cohort, participant_ids, n_participants, variable_stats, visit_mapping=visit_mapping)
        if obs_vars:
            datasets_loaded.append("observations")
            vars_by_dataset["observations"] = obs_vars

        # ── Step 6: DrugExposure ────────────────────────────────────────────────
        drug_vars = process_drugs(dirs, cohort, participant_ids, n_participants, baseline_meas_ids, variable_stats, visit_mapping=visit_mapping)
        if drug_vars:
            datasets_loaded.append("drugs")
            vars_by_dataset["drugs"] = drug_vars

        # ── Step 7: DQ checks ──────────────────────────────────────────────────
        print("\n  [DQ] Running data quality checks...")
        dq_flags = run_dq_checks(cohort, variable_stats, n_participants)
        for flag in dq_flags:
            prefix = "    ⚠" if "WARNING" in flag else "    🚨" if "CRITICAL" in flag else "    ✓"
            print(f"{prefix} {flag}")

        # ── Step 8: Build output ────────────────────────────────────────────────
        cohort_meta = COHORTS.get(cohort, {}) if _HAS_CONFIG else {}

        result = {
            "metadata": {
                "source": "BDC DMC",
                "cohort": cohort,
                "generated": datetime.now(timezone.utc).isoformat(),
                "script": "extract_harmonized_summaries.py",
                "mapped_data_dirs": dirs,
                "note": "Aggregate statistics only — no individual-level data.",
            },
            "cohort": {
                "name": cohort,
                "full_name": cohort_meta.get("full_name", ""),
                "phs": cohort_meta.get("phs", ""),
                "bdc_version": cohort_meta.get("bdc_version", ""),
            },
            "total_participants": n_participants,
            "datasets_loaded": datasets_loaded,
            "variables_by_dataset": vars_by_dataset,
            "variables": variable_stats,
            "dq_flags": dq_flags,
        }

        # Print summary
        print_cohort_summary(result)

        # Write JSON
        output_path = out_dir / f"bdc_{cohort.lower()}_summary_{run_ts}.json"

        print(f"\n  Writing: {output_path}")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"  Contains: aggregate counts and statistics ONLY (no individual data).")

        total_vars = len(variable_stats)
        n_cat = sum(1 for v in variable_stats.values() if v["type"] == "categorical")
        n_con = sum(1 for v in variable_stats.values() if v["type"] == "continuous")
        print(f"\n  Total variables extracted: {total_vars} ({n_cat} categorical, {n_con} continuous)")

        print("\n" + "=" * 60)
        print(f"  BDC extraction complete for {cohort}.")
        print(f"  Output (JSON):    {output_path}")
        print(f"  Output (log):     {log_path}")
        print(f"  Next: run compare script with TOPMed and BDC JSONs side-by-side.")
        print("=" * 60)

    finally:
        # ── Restore stdout/stderr and close log file ────────────────────────
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        log_fh.close()

    return str(output_path)


if __name__ == "__main__":
    main()
