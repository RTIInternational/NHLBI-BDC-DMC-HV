"""
extract_source_summaries.py — HV-DataQC Component 1

Summarize raw dbGaP phenotype TSV files for a single cohort and export an
aggregate-only JSON artifact.

Design:
  - ZERO dependency on HV transform YAML files — summarizes EVERY non-system
    column in each pht directory. This makes the exported JSON a permanent,
    stable artifact tied to the dbGaP study version, not to the YAML state.
  - Run inside the data enclave where raw TSVs live.
  - Only aggregate statistics leave the enclave — no individual rows.

Usage examples:
  # Summarize all columns in all pht directories under a root
  python extract_source_summaries.py \\
      --cohort SPIROMICS \\
      --source-root /data/enclave/spiromics/pheno/ \\
      --output-dir ./dataqc-runs/

  # Restrict to specific pht sub-directories
  python extract_source_summaries.py \\
      --cohort CARDIA \\
      --source-dirs /data/pht003099 /data/pht003100 \\
      --output-dir ./dataqc-runs/

  # Additional optional flags
  --visit-col VISIT      # column holding visit label (default: auto-detect)
  --participant-col SUBJECT_ID
  --phv-list phv001 phv002   # restrict to these specific PHV columns only
  --cache-dir /data/dbgap-cache/spiromics/  # resolve PHV IDs to names
  --output spiromics_source_custom.json
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import pandas as pd
import yaml

from hv_dataqc.hv_dataqc_common import (
    canonical_phv_id,
    categorical_stats,
    continuous_stats,
    load_phv_name_map as _shared_load_phv_name_map,
    write_json_atomic,
)

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

_FMT = "%(asctime)s %(levelname)-8s %(message)s"
_DATEFMT = "%H:%M:%S"

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

# Console handler — added at module level so basic output is visible
_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(logging.Formatter(_FMT, datefmt=_DATEFMT))
log.addHandler(_console_handler)
# Prevent propagation to root logger (avoids duplicate output)
log.propagate = False

_file_handler: logging.FileHandler | None = None

_DEFAULT_THRESHOLDS_PATH = Path(__file__).resolve().parents[1] / "compare" / "config" / "thresholds.yaml"


def _canonical_phv_id(raw_id: str) -> str:
    """Return canonical PHV accession: lower-case, version suffix stripped."""
    return canonical_phv_id(raw_id)


def _write_json_atomic(path: Path, data: Any) -> None:
    """Write strict JSON via temp file then atomic replace."""
    write_json_atomic(path, data, ensure_ascii=True, default=str)


def load_source_extract_config(path: Path | None = None) -> dict[str, Any]:
    """Load source-extractor configuration from thresholds.yaml if available."""
    effective_path = path or _DEFAULT_THRESHOLDS_PATH
    if not effective_path.exists():
        return {}
    try:
        with effective_path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except yaml.YAMLError as exc:
        log.warning("Malformed thresholds config %s: %s", effective_path, exc)
        return {}


def _add_file_logging(log_path: Path) -> None:
    """Add a FileHandler to the module logger so log output is also written to *log_path*."""
    global _file_handler
    _file_handler = logging.FileHandler(log_path, encoding="utf-8")
    _file_handler.setFormatter(logging.Formatter(_FMT, datefmt=_DATEFMT))
    log.addHandler(_file_handler)


def _close_file_logging() -> None:
    """Flush and remove the FileHandler added by _add_file_logging."""
    global _file_handler
    if _file_handler is not None:
        _file_handler.flush()
        log.removeHandler(_file_handler)
        _file_handler.close()
        _file_handler = None


# ---------------------------------------------------------------------------
# System / metadata column detection
# ---------------------------------------------------------------------------

# These columns are never meaningful data variables
_SKIP_EXACT: frozenset[str] = frozenset(
    {
        "dbgap_subject_id",
        "subject_id",
        "topmed_subject_id",
        "sample_id",
        "sample.id",
        "consent",
        "consent_short_name",
        "_source_file",
        "_pht",
        "_phs",
    }
)


def is_system_column(col: str) -> bool:
    """Return True if this column should be skipped (IDs, metadata, internals)."""
    canon = col.strip().lower()
    if canon in _SKIP_EXACT:
        return True
    if canon.startswith("_"):
        return True
    # Patterns that flag ID / provenance columns
    if re.search(r"subject.?id|sample.?id|topmed_flag", canon):
        return True
    return False


# ---------------------------------------------------------------------------
# Type inference
# ---------------------------------------------------------------------------

_CATEGORICAL_DTYPE_KINDS = {"O", "b", "U", "S"}  # object, bool, unicode, bytes


def infer_variable_type(
    series: pd.Series,
    n_distinct_threshold: int = 20,
) -> str:
    """Infer whether a variable is 'categorical' or 'continuous'.

    Rules (in priority order):
      1. String / object dtype → categorical
      2. Boolean dtype → categorical
      3. n_distinct <= threshold → categorical
            4. Otherwise → continuous
    """
    if series.dtype.kind in _CATEGORICAL_DTYPE_KINDS:
        return "categorical"

    non_null = series.dropna()
    if len(non_null) == 0:
        return "continuous"  # can't tell; treat as numeric

    n_distinct = int(series.nunique(dropna=True))
    if n_distinct <= n_distinct_threshold:
        return "categorical"

    # NOTE: A previous block here re-checked `n_distinct <= n_distinct_threshold`
    # for integer-coded columns, which was unreachable dead code (the early
    # return above already covers it). Removed; if a tighter integer-code
    # threshold is wanted in the future, introduce a separate threshold
    # rather than reusing `n_distinct_threshold`.

    return "continuous"



# ---------------------------------------------------------------------------
# Source directory discovery
# ---------------------------------------------------------------------------

_CONSENT_GROUP_RE = re.compile(r"[-_]c\d+$", re.IGNORECASE)
_PHT_RE = re.compile(r"\bpht(\d{6,7})\b", re.IGNORECASE)


def _extract_pht_id(filename: str) -> str:
    """Extract PHT accession string from a filename (e.g. 'pht002239').

    Matches the ``phtNNNNNN`` pattern anywhere in the filename.  Falls back
    to ``"unknown"`` when no PHT accession can be found.
    """
    m = _PHT_RE.search(filename)
    return f"pht{m.group(1)}" if m else "unknown"


def discover_source_dirs(root: Path, cohort: str) -> list[Path]:
    """Walk *root* and return consent-group directories for this cohort.

    Expected BDC enclave layout (either naming convention)::

        <source_root>/
            <cohort_lower>_phs<accession>_c1/          <- short form
            <cohort_lower>_phs<accession>_c2/
            nih-nhlbi-topmed-parent-<cohort>-phs...-c1/ <- full BDC form
            dataqc-runs/   <- skipped

    Matches subdirectories whose names contain the cohort name
    (case-insensitive) and end with ``_c<N>`` or ``-c<N>``.
    """
    cohort_lower = cohort.lower()
    dirs: list[Path] = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        name = d.name.lower()
        if name == "dataqc-runs":
            continue
        # Match both short form (aric_phs..._c1) and full BDC enclave form
        # (nih-nhlbi-topmed-parent-aric-phs...-v8-r1-c1).
        if cohort_lower in name and _CONSENT_GROUP_RE.search(d.name):
            dirs.append(d)
    return dirs


def load_source_data(
    source_dirs: list[Path],
    pht_filter: str | None = None,
    participant_col: str | None = None,
) -> list[tuple[str, pd.DataFrame]]:
    """Load raw phenotype TSV files grouped by PHT accession.

    Files from multiple consent-group directories for the *same* PHT are
    concatenated together.  MULTI files (whose names contain ``"MULTI"``) are
    deduplicated on the participant-ID column to avoid counting the same
    subject once per consent group.

    Returns ``[(pht_id, DataFrame), ...]`` — one entry per distinct PHT,
    sorted by PHT accession.  The caller's
    ``for pht_label, df in loaded`` loop works unchanged.
    """
    _GLOB_PATTERNS = ("*.txt", "*.tsv", "*.txt.gz", "*.tsv.gz")

    # Collect frames and MULTI flags keyed by PHT accession.
    pht_frames: dict[str, list[pd.DataFrame]] = {}
    pht_is_multi: dict[str, bool] = {}

    for src_dir in source_dirs:
        dir_files: list[Path] = []
        for pattern in _GLOB_PATTERNS:
            dir_files.extend(sorted(src_dir.glob(pattern)))

        for f in sorted(set(dir_files)):
            if f.name.startswith(".") or "Sample" in f.name:
                continue
            if pht_filter and pht_filter not in f.name:
                continue

            pht_id = _extract_pht_id(f.name)
            is_multi = "MULTI" in f.name.upper()

            try:
                df = pd.read_csv(
                    f,
                    sep="\t",
                    comment="#",
                    na_values=["", "NA", ".", "NaN"],
                    low_memory=False,
                )
                df.columns = df.columns.astype(str).str.strip()
                df["_consent_group"] = src_dir.name
                log.info(
                    "  [%s] %s: %d rows (pht=%s%s)",
                    src_dir.name, f.name, len(df), pht_id,
                    ", MULTI" if is_multi else "",
                )
                pht_frames.setdefault(pht_id, []).append(df)
                if is_multi:
                    pht_is_multi[pht_id] = True
            except Exception as exc:
                log.warning("  Could not load %s: %s", f, exc)

    if not pht_frames:
        return []

    result: list[tuple[str, pd.DataFrame]] = []
    for pht_id in sorted(pht_frames):
        frames = pht_frames[pht_id]
        combined = pd.concat(frames, ignore_index=True)
        row_count_before = len(combined)

        if pht_is_multi.get(pht_id):
            # MULTI files list the same subjects in multiple consent groups.
            # Deduplicate to get exactly one row per participant.
            subj_col = participant_col
            if subj_col is None or subj_col not in combined.columns:
                for candidate in ("dbgap_subject_id", "topmed_subject_id", "subject_id"):
                    if candidate in combined.columns:
                        subj_col = candidate
                        break
            if subj_col and subj_col in combined.columns:
                combined = combined.drop_duplicates(subset=[subj_col], keep="first")
                log.info(
                    "  MULTI dedup %s: %d -> %d rows (on column '%s')",
                    pht_id, row_count_before, len(combined), subj_col,
                )
            else:
                log.warning(
                    "  MULTI file %s: no participant-ID column found for dedup "
                    "(pass --participant-col to specify one)",
                    pht_id,
                )

        log.info(
            "  PHT %s: %d rows from %d file(s)",
            pht_id, len(combined), len(frames),
        )
        result.append((pht_id, combined))

    log.info("  Loaded %d distinct PHT(s)", len(result))
    return result


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def compute_variable_summary(
    series: pd.Series,
    forced_type: str | None = None,
    n_distinct_threshold: int = 20,
) -> dict[str, Any]:
    """Compute summary statistics, auto-inferring type unless *forced_type* given."""
    var_type = forced_type or infer_variable_type(series, n_distinct_threshold)
    if var_type == "categorical":
        return categorical_stats(series)
    return continuous_stats(series)


# ---------------------------------------------------------------------------
# PHV name map (optional enhancement via dbGaP cache)
# ---------------------------------------------------------------------------

def load_phv_name_map(cache_dir: Path) -> dict[str, str]:
    """Load a PHV-accession → human-readable-name map from local dbGaP cache.

    Reads all ``*.data_dict.xml`` files under *cache_dir*/pheno_variable_summaries/.
    Returns empty dict if the path doesn't exist (graceful degradation).
    """
    return _shared_load_phv_name_map(
        cache_dir,
        info=lambda msg: log.info(msg),
        warning=lambda msg: log.warning(msg),
    )


_DBGAP_CONTINUOUS_TYPES: frozenset[str] = frozenset({
    "integer", "decimal", "float", "num",
    "continuous integer", "continuous decimal", "continuous",
    "numeric", "integer decimal",
})
_DBGAP_CATEGORICAL_TYPES: frozenset[str] = frozenset({
    "encoded", "string", "char", "character",
    "enumerated integer", "encoded value", "text",
})
_DBGAP_CONTINUOUS_KEYWORDS: frozenset[str] = frozenset(
    {"continuous", "numeric", "decimal", "float"}
)
_DBGAP_CATEGORICAL_KEYWORDS: frozenset[str] = frozenset(
    {"encoded", "string", "text", "character", "char"}
)


def _normalize_dbgap_type(raw: str) -> str | None:
    text = str(raw or "").strip().lower()
    if text in _DBGAP_CONTINUOUS_TYPES:
        return "continuous"
    if text in _DBGAP_CATEGORICAL_TYPES:
        return "categorical"
    if any(kw in text for kw in _DBGAP_CONTINUOUS_KEYWORDS):
        return "continuous"
    if any(kw in text for kw in _DBGAP_CATEGORICAL_KEYWORDS):
        return "categorical"
    return None


def load_source_type_map(cache_dir: Path) -> dict[str, str]:
    """Load source column/PHV -> dbGaP-derived continuous/categorical type.

    The source TSVs commonly use variable names as headers, while YAML and
    dbGaP metadata use PHV accessions.  Store both keys so extraction can force
    the correct aggregate shape before row-level values are reduced to JSON.
    """
    type_map: dict[str, str] = {}
    pheno_dir = cache_dir / "pheno_variable_summaries"
    if not pheno_dir.exists():
        log.info("cache pheno_variable_summaries/ not found at %s -- source types unavailable", pheno_dir)
        return type_map

    files = list(pheno_dir.glob("*.data_dict.xml"))
    log.info("Loading dbGaP source types from %d data_dict.xml files...", len(files))
    for dd_file in files:
        try:
            tree = ET.parse(dd_file)
            for var in tree.getroot().findall(".//variable"):
                inferred_type = _normalize_dbgap_type(var.findtext("type") or "")
                if not inferred_type:
                    continue
                phv_id = _canonical_phv_id(var.get("id", ""))
                name = (var.findtext("name") or "").strip().lower()
                if phv_id:
                    type_map[phv_id] = inferred_type
                if name:
                    type_map[name] = inferred_type
        except ET.ParseError as exc:
            log.warning("Could not parse PHV type XML %s: %s", dd_file.name, exc)

    log.info(
        "dbGaP source type map: %d keys (%d continuous, %d categorical)",
        len(type_map),
        sum(1 for v in type_map.values() if v == "continuous"),
        sum(1 for v in type_map.values() if v == "categorical"),
    )
    return type_map


# ---------------------------------------------------------------------------
# Visit-stratified row counts
# ---------------------------------------------------------------------------

def count_rows_per_visit(df: pd.DataFrame, visit_col: str | None) -> dict[str, int]:
    """Return {visit_label: row_count} dict if *visit_col* exists; else {}."""
    if not visit_col or visit_col not in df.columns:
        return {}
    counts = df[visit_col].value_counts(dropna=False).sort_index()
    return {str(k): int(v) for k, v in counts.items()}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Summarize raw dbGaP phenotype TSVs for one cohort. "
                    "Produces an aggregate-only JSON artifact for later comparison.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # --- required ---
    p.add_argument("--cohort", required=True, metavar="NAME",
                   help="Cohort name (e.g. SPIROMICS). Used in output file naming.")

    # --- source location: one of two forms ---
    src_group = p.add_mutually_exclusive_group(required=False)
    src_group.add_argument(
        "--source-root", metavar="DIR", default=None,
        help="Root directory containing consent-group subdirectories "
             "(named <cohort>_..._c<N>). Defaults to ./<COHORT> if omitted.")
    src_group.add_argument(
        "--source-dirs", metavar="DIR", nargs="+",
        help="Explicit list of consent-group directories to load (skip auto-discover).")

    # --- optional tuning ---
    p.add_argument("--visit-col", metavar="COL", default=None,
                   help="Column name holding visit label for stratified counts.")
    p.add_argument("--participant-col", metavar="COL", default=None,
                   help="Column holding participant ID for N-unique counting.")
    p.add_argument("--pht-filter", metavar="PHT", default=None,
                   help="Only load files whose names contain this PHT accession string "
                        "(e.g. pht002239). Substring match on filename.")
    p.add_argument("--phv-list", metavar="PHV", nargs="+",
                   help="If set, only summarize these specific columns (PHV accession IDs or column names).")
    p.add_argument("--n-distinct-threshold", type=int, default=None, metavar="N",
                   help="Max n_distinct to treat numeric variable as categorical "
                        "(default: source_extract.infer_type_distinct_threshold in thresholds.yaml, else 20).")
    p.add_argument("--thresholds", metavar="YAML",
                   help="Optional thresholds/config YAML. Defaults to compare/config/thresholds.yaml.")
    p.add_argument("--cache-dir", metavar="DIR",
                   help="Optional: path to dbGaP cache dir for a cohort, used to resolve PHV→name.")

    # --- output ---
    p.add_argument("--output-dir", metavar="DIR", default=None,
                   help="Directory to write output files. "
                        "Defaults to <source-root>/dataqc-runs/ (or ./<COHORT>/dataqc-runs/ "
                        "when source-root is defaulted from cohort name).")
    p.add_argument("--output", metavar="FILE",
                   help="Override JSON output filename.")
    p.add_argument("--verbose", action="store_true")

    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    if args.verbose:
        log.setLevel(logging.DEBUG)

    config = load_source_extract_config(Path(args.thresholds) if args.thresholds else None)
    source_cfg = config.get("source_extract", {}) if isinstance(config, dict) else {}
    n_distinct_threshold = (
        args.n_distinct_threshold
        if args.n_distinct_threshold is not None
        else int(source_cfg.get("infer_type_distinct_threshold", 20))
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    cohort_lower = args.cohort.lower()

    try:
        log.info("=== HV-DataQC Source Extractor ===")
        log.info("Cohort:    %s", args.cohort)
        log.info("Timestamp: %s", timestamp)
        log.info("Infer-type distinct threshold: %d", n_distinct_threshold)

        # ------------------------------------------------------------------
        # 1. Resolve source directories
        # ------------------------------------------------------------------
        if args.source_dirs:
            source_dirs = [Path(d) for d in args.source_dirs]
            resolved_root = source_dirs[0].parent  # for output-dir default
            log.info("Using %d explicit source directories", len(source_dirs))
        else:
            # Default source-root to ./<COHORT> when not specified
            root = Path(args.source_root) if args.source_root else Path(args.cohort)
            if not root.is_dir():
                log.error(
                    "Source root does not exist: %s  "
                    "(pass --source-root DIR or --source-dirs DIR [DIR ...])",
                    root,
                )
                sys.exit(1)
            source_dirs = discover_source_dirs(root, args.cohort)
            resolved_root = root
            log.info("Discovered %d consent-group directories under %s", len(source_dirs), root)

        if not source_dirs:
            log.error("No consent-group directories found — exiting.")
            sys.exit(1)

        # ------------------------------------------------------------------
        # 1b. Resolve output directory
        # ------------------------------------------------------------------
        output_dir = Path(args.output_dir) if args.output_dir else (resolved_root / "dataqc-runs")
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create a timestamped run subdirectory and a latest_source symlink
        run_dir = output_dir / f"source_{timestamp}"
        run_dir.mkdir(exist_ok=True)
        latest_link = output_dir / "latest_source"
        latest_link.unlink(missing_ok=True)
        latest_link.symlink_to(run_dir.name)
        log.info("Output dir: %s", run_dir)
        log.info("Symlink:    %s -> %s", latest_link, run_dir.name)

        log_path = run_dir / f"{cohort_lower}_source_extract_{timestamp}.log"
        # File logging only — no stdout redirection. The matching
        # `_close_file_logging()` call lives in the outer `finally` block.
        _add_file_logging(log_path)

        # ------------------------------------------------------------------
        # 2. Load all TSVs
        # ------------------------------------------------------------------
        loaded = load_source_data(source_dirs, args.pht_filter, args.participant_col)
        if not loaded:
            log.error("No data loaded — check --source-root / --source-dirs.")
            sys.exit(1)

        # ------------------------------------------------------------------
        # 3. Optional PHV name map
        # ------------------------------------------------------------------
        phv_name_map: dict[str, str] = {}
        source_type_map: dict[str, str] = {}
        if args.cache_dir:
            cache_path = Path(args.cache_dir)
            if cache_path.is_dir():
                phv_name_map = load_phv_name_map(cache_path)
            source_type_map = load_source_type_map(cache_path)

        # ------------------------------------------------------------------
        # 4. Optional column filter
        # ------------------------------------------------------------------
        phv_filter_set: set[str] = set()
        if args.phv_list:
            phv_filter_set = {c.strip().lower() for c in args.phv_list}
            log.info("Column filter active: %d columns", len(phv_filter_set))

        # ------------------------------------------------------------------
        # 5. Summarize variables across all pht frames
        # ------------------------------------------------------------------
        variables_by_pht: dict[str, dict] = {}   # {pht: {col_key: summary}}
        total_rows_all = 0
        total_rows_by_pht: dict[str, int] = {}
        total_participants: int | None = None
        participant_ids: set[str] = set()
        participants_by_pht: dict[str, int] = {}   # unique participant count per PHT
        rows_per_visit_combined: dict[str, int] = {}

        for pht_label, df in loaded:
            log.info("--- Processing %s (%d rows) ---", pht_label, len(df))
            total_rows_all += len(df)
            total_rows_by_pht[pht_label] = len(df)

            # Visit stratification
            visit_col = args.visit_col
            if visit_col is None:
                # Auto-detect common visit column names across cohorts:
                # - VISIT / EXAM / VISIT_LABEL — generic / SPIROMICS / CHS
                # - phase_study — COPDGene (P1, P2, P3)
                # - visitnum — COPDGene numeric visit number
                # - phase — generic phase column
                for candidate in (
                    "VISIT", "visit", "EXAM", "exam", "VISIT_LABEL",
                    "phase_study", "visitnum", "phase",
                ):
                    if candidate in df.columns:
                        visit_col = candidate
                        log.info("  Auto-detected visit column: %s", visit_col)
                        break

            rpv = count_rows_per_visit(df, visit_col)
            for k, v in rpv.items():
                rows_per_visit_combined[k] = rows_per_visit_combined.get(k, 0) + v

            # Participant N — use explicit --participant-col if given, otherwise
            # fall back to standard dbGaP system ID columns (case-insensitive).
            # These columns are filtered from variable stats but are valid for
            # counting unique participants.
            part_col = args.participant_col
            if part_col is None:
                cols_lower = {c.lower(): c for c in df.columns}
                for candidate in ("dbgap_subject_id", "topmed_subject_id", "subject_id"):
                    if candidate in cols_lower:
                        part_col = cols_lower[candidate]
                        log.info("  Auto-detected participant column: %s", part_col)
                        break
            if part_col and part_col in df.columns:
                n_unique_here = int(df[part_col].nunique(dropna=True))
                participant_ids.update(str(v) for v in df[part_col].dropna().unique())
                participants_by_pht[pht_label] = n_unique_here
                log.info("  Unique participants in %s: %d", pht_label, n_unique_here)
                if total_participants is None:
                    total_participants = n_unique_here
                else:
                    total_participants = max(total_participants, n_unique_here)

            # Iterate columns
            for col in df.columns:
                if is_system_column(col):
                    log.debug("  Skipping system column: %s", col)
                    continue

                col_key = col.strip().lower()

                # Apply optional filter
                if phv_filter_set and col_key not in phv_filter_set:
                    log.debug("  Filtered out: %s", col)
                    continue

                forced_type = source_type_map.get(col_key)
                summary = compute_variable_summary(
                    df[col],
                    forced_type=forced_type,
                    n_distinct_threshold=n_distinct_threshold,
                )
                if forced_type:
                    summary["_type_source"] = "dbGaP_data_dictionary"
                summary["_col_original"] = col
                summary["_pht"] = pht_label
                if col in phv_name_map:
                    summary["name"] = phv_name_map[col]
                elif col.lower() in phv_name_map:
                    summary["name"] = phv_name_map[col.lower()]

                variables_by_pht.setdefault(pht_label, {})[col_key] = summary
                log.debug("  Summarized: %s (%s, n_valid=%d)", col, summary["type"], summary.get("n_valid", 0))

            log.info("  PHT %s: %d variables", pht_label, len(variables_by_pht.get(pht_label, {})))

        if participant_ids:
            total_participants = len(participant_ids)
            log.info("Unique participants (cross-PHT union): %d", total_participants)
            if participants_by_pht:
                max_pht = max(participants_by_pht, key=participants_by_pht.get)
                log.info("  Largest single-PHT count: %s (%d)", max_pht, participants_by_pht[max_pht])

        # ------------------------------------------------------------------
        # 6. Build output document
        # ------------------------------------------------------------------
        output_doc: dict[str, Any] = {
            "metadata": {
                "source": "raw_dbgap",
                "cohort": args.cohort,
                "extracted_at": timestamp,
                "n_source_dirs": len(source_dirs),
                "source_dirs": [str(d) for d in source_dirs],
                "phts_loaded": [pht for pht, _ in loaded],
                "n_distinct_threshold": n_distinct_threshold,
            },
            "total_rows": total_rows_all,
            "total_rows_by_pht": total_rows_by_pht,
            "rows_per_visit": rows_per_visit_combined,
            "participants_by_pht": participants_by_pht,
            "variables_by_pht": variables_by_pht,
        }
        if total_participants is not None:
            output_doc["total_participants"] = total_participants

        # ------------------------------------------------------------------
        # 7. Write JSON
        # ------------------------------------------------------------------
        if args.output:
            out_path = run_dir / args.output
        else:
            out_path = run_dir / f"{cohort_lower}_source_{timestamp}.json"

        total_var_entries = sum(len(v) for v in variables_by_pht.values())
        log.info("Writing %d variable summaries to %s", total_var_entries, out_path)
        _write_json_atomic(out_path, output_doc)

        log.info("=== Done. Variables summarized: %d, Total rows: %d ===",
                 total_var_entries, total_rows_all)

    finally:
        _close_file_logging()


if __name__ == "__main__":
    main()
