# extract_source — Raw dbGaP TSV Summarizer

Extracts aggregate statistics from raw dbGaP phenotype TSV files and exports
an aggregate-only JSON artifact. Run this **inside the data enclave**.

---

## What It Does

- Walks consent-group directories under a source root (or use explicit paths)
- Summarizes **every non-system column** — no YAML dependency at all
- Auto-detects categorical vs. continuous based on dtype and n_distinct
- Optionally stratifies row counts by a visit column
- Optionally resolves PHV IDs to variable names from the local dbGaP cache
- Counts the participant union internally and exports only the aggregate count
- Writes strict JSON atomically; non-finite numeric summaries are exported as `null`
- Writes a stable, YAML-version-independent JSON artifact

The source JSON only needs to be re-run when the dbGaP study version changes
or a new pht table is added. It does NOT need to be re-run when HV YAMLs change.

---

## Usage

```bash
# Minimal — auto-discovers consent-group dirs under ./<COHORT>
python extract_source_summaries.py --cohort COPDGene

# With explicit source root (must contain <cohort>_..._c<N>/ dirs)
python extract_source_summaries.py \
    --cohort SPIROMICS \
    --source-root /enclave/raw/spiromics/ \
    --output-dir ./dataqc-runs/

# Filter to one PHT file across all consent groups
python extract_source_summaries.py \
    --cohort SPIROMICS \
    --source-root /enclave/raw/spiromics/ \
    --pht-filter pht006243

# With PHV name resolution from local dbGaP cache
python extract_source_summaries.py \
    --cohort SPIROMICS \
    --source-root /enclave/raw/spiromics/ \
    --cache-dir /enclave/dbgap-cache/spiromics/ \
    --output-dir ./dataqc-runs/
```

### All Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--cohort NAME` | Yes | Cohort name (used in output filename) |
| `--source-root DIR` | No | Root dir containing consent-group subdirs (`<cohort>_..._c<N>`). Defaults to `./<COHORT>` if omitted. |
| `--source-dirs DIR ...` | No | Explicit list of consent-group directories (mutually exclusive with `--source-root`). |
| `--visit-col COL` | No | Column holding visit label for stratified row counts. |
| `--participant-col COL` | No | Column holding participant ID for N-unique counting. |
| `--pht-filter PHT` | No | Only load files whose names contain this string (e.g. `pht002239`). Substring match. |
| `--phv-list PHV ...` | No | Only summarize these specific columns (override all-columns behavior). |
| `--n-distinct-threshold N` | No | Max distinct values to treat numeric column as categorical (default: 20). |
| `--cache-dir DIR` | No | dbGaP cache dir; resolves PHV IDs to human-readable names. |
| `--output-dir DIR` | No | Output directory. Defaults to `<source-root>/dataqc-runs/`. |
| `--output FILE` | No | Override output JSON filename |
| `--verbose` | No | Enable debug logging |

---

## Output Layout

Output is written into a timestamped subdirectory with a `latest_source` symlink:

```
<output-dir>/
  source_20260504_120000/
    copdgene_source_20260504_120000.json
    copdgene_source_extract_20260504_120000.log
  latest_source -> source_20260504_120000
```

Re-running creates a new dated directory and updates the symlink.

---

## Output JSON Format

```json
{
  "metadata": {
    "source": "raw_dbgap",
    "cohort": "SPIROMICS",
    "extracted_at": "20250101T120000",
    "n_source_dirs": 2,
    "source_dirs": ["spiromics_phs001119_c1", "spiromics_phs001119_c2"]
  },
  "total_rows": 11892,
  "rows_per_visit": {"VISIT_1": 2973, "VISIT_2": 2919, ...},
  "variables": {
    "ht_cm": {
      "type": "continuous",
      "n_valid": 2973, "n_missing": 0,
      "mean": 170.4, "sd": 9.1,
      "min": 142.0, "max": 198.5,
      "_pht": "pht006243",
      "_col_original": "HT_CM",
      "name": "Standing Height"
    },
    "race1": {
      "type": "categorical",
      "n_valid": 2973, "n_missing": 0,
      "n_distinct": 5,
      "distribution": {
        "1": {"n": 1800, "pct": 60.5},
        "2": {"n": 600, "pct": 20.2},
        ...
      }
    }
  }
}
```

---

## System Columns Skipped

The following column patterns are always skipped (never summarized):

- `dbGaP_Subject_ID`, `SUBJECT_ID`, `Subject_ID` and variants
- `CONSENT`, `SAMPLE_ID`, `TOPMED_FLAG`
- Any column starting with `_`

---

## Requirements

```
pandas >= 1.3
```

No YAML dependency. No dependency on any other hv_dataqc script.
