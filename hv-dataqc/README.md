# HV-DataQC: Source vs. Harmonized Output Comparison Suite

Validates that the BDC dm-bip harmonized output faithfully preserves the
source dbGaP data — checking N preservation, distribution matching, clinical
ranges, visit structure, and cross-variable consistency.

---

## Components

| Folder | Script | Purpose | Runs where |
|--------|--------|---------|-----------|
| `extract-source/` | `extract_source_summaries.py` | Summarize raw dbGaP TSVs | **Inside enclave** |
| `extract-harmonized/` | `extract_harmonized_summaries.py` | Summarize dm-bip harmonized output | **Inside enclave** |
| `compare/` | `compare_source_harmonized.py` | Compare both summaries; run checks C1-C11 | Outside enclave |

---

## Design Principles

1. **Source extract is YAML-agnostic.** It summarizes every column in the raw
   TSV regardless of what the current HV YAMLs reference. This makes it a
   stable, reusable artifact — it never needs to be re-run when YAMLs change,
   only when the source study version changes or a new PHT table is added.

2. **Harmonized extract is also YAML-agnostic.** It reads entity TSVs produced
   by dm-bip and groups by `observation_type` / `condition_concept` columns —
   concept codes that are already baked into the pipeline output. Visit UUIDs
   are resolved to human-readable labels from `Visit.tsv` at extraction time.

3. **Comparison uses live YAMLs.** The crosswalk (source PHV → harmonized concept
   code) is built fresh from the current HV YAML checkout on every compare run.
   Re-run `compare_source_harmonized.py` as often as needed as YAMLs evolve — no
   re-entry to the enclave required.

---

## Workflow

```
ENCLAVE (run once per source study version)
  # source-root must contain <cohort>_..._c<N>/ consent-group dirs
  # defaults to ./<COHORT> if --source-root is omitted
  python extract-source/extract_source_summaries.py \
      --cohort SPIROMICS \
      --source-root /path/to/raw/spiromics/ \
      --output-dir ./dataqc-runs/
  → exports: spiromics_source_<timestamp>.json

ENCLAVE (run after each dm-bip pipeline execution)
  # harmonized-root must contain DMC_* run directories
  # defaults to . (current directory) if --harmonized-root is omitted
  python extract-harmonized/extract_harmonized_summaries.py \
      --cohort SPIROMICS \
      --harmonized-root /path/to/dmbip_output/ \
      --output-dir ./dataqc-runs/
  → exports: spiromics_harmonized_<timestamp>.json

OUTSIDE ENCLAVE (re-run freely as YAMLs evolve)
  python compare/compare_source_harmonized.py \
      --source  spiromics_source_<timestamp>.json \
      --harmonized  spiromics_harmonized_<timestamp>.json \
      --cohort  SPIROMICS \
      --yaml-dir /path/to/HV-repo/priority_variables_transform/SPIROMICS-ingest/ \
      --cache-dir /path/to/data/dbgap-cache/spiromics/
```

---

## Exported JSON Format (both extracts)

Both `extract_source_summaries.py` and `extract_harmonized_summaries.py` write
**aggregate-only** JSON — no individual participant rows.

```json
{
  "metadata": { "source": "raw_dbgap", "cohort": "SPIROMICS", ... },
  "total_participants": 2973,
  "total_rows": 11892,
  "rows_per_visit": { "VISIT_1": 2973, ... },
  "variables": {
    "<key>": {
      "type": "continuous",
      "n_valid": 7757, "n_missing": 135,
      "mean": 170.4, "sd": 9.1, ...
    },
    "<key>": {
      "type": "categorical",
      "distribution": { "1": {"n": 5000, "pct": 42.1}, ... }
    }
  }
}
```

---

## Checks (C1-C11)

| Check | What it validates |
|-------|------------------|
| C1 | Total participant N preserved |
| C2 | Per-variable valid N (no silent row loss) |
| C3 | Missing value rates stable |
| C4 | Continuous mean preserved (same unit) |
| C5 | Continuous mean preserved after unit conversion |
| C6 | Standard deviation preserved |
| C7 | Categorical distributions match (with value_mappings translation) |
| C8 | Visit N distribution preserved |
| C9 | Harmonized values within clinical plausible range |
| C10 | Cross-variable consistency (SBP > DBP, FEV1 < FVC) |
| C11 | Source/harmonized type consistency (continuous vs categorical) |

Recent comparison report details:

- C7 includes full source/harmonized categorical distribution tables, with many-to-one
  YAML value mappings aggregated before percentages are compared.
- C9 annotates range findings as `[out+src]`, `[out only]`, or `[src only]` when
  source min/max context is available.
- C10 reads `_cross_variable_rules` from `clinical_ranges.yaml`; simple two-variable
  mean comparisons run automatically, while formula rules are reported as `SKIP`
  until implemented.

---

## Requirements

```
pandas >= 1.3
pyyaml >= 5.4
```

Install: `pip install pandas pyyaml`
