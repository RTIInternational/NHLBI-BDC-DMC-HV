# extract-harmonized — dm-bip Harmonized Summarizer

Extracts aggregate statistics from dm-bip harmonized output TSV files (entity
files produced by the pipeline) and exports an aggregate-only JSON artifact.
Run this **inside the data enclave** after each pipeline execution.

---

## What It Does

- Reads entity TSVs from dm-bip mapped-data directories:
  `Demography.tsv`, `MeasurementObservation.tsv`, `MeasurementObservationSet.tsv`,
  `Condition.tsv`, `Observation.tsv`, `Visit.tsv`, and others
- **Loads Visit.tsv first** and builds a UUID → visit_label map. This resolves
  UUID values in `associated_visit` columns (produced when `visit.yaml` uses
  `id: expr: uuid5(...)`) to human-readable labels before building per-visit stats.
  Without this fix, by-visit stats would have UUID keys that can't be matched
  against source visit labels in the C8 check.
- Visit labels prefer `name`, then `visit_type`, then `visit_category`, preserving
  distinct timepoints when available.
- Participant counts prefer `Demography.associated_participant`, then fall back to
  `Participant`, `Person`, or associated participant columns on entity tables.
- JSON is written atomically and non-finite numeric summaries are exported as `null`.
- Discovers observation types, condition concepts, and value distributions
  directly from the TSV data — no YAML dependency.
- Writes a per-pipeline-run JSON artifact (regenerate after each dm-bip run).

---

## UUID Resolution

When visit.yaml uses `uuid5()` to generate Visit IDs:

```yaml
# visit.yaml (example)
- class_derivations:
    Visit:
      slot_derivations:
        id:
          expr: "uuid5('spiromics_visit', str(VISIT))"
        visit_category:
          value: "HEALTH_EXAMINATION"
```

The resulting `MeasurementObservation.tsv` has:
```
associated_visit = "3c4a8f21-9e5a-5b7f-a234-1d2e3f4a5b6c"
```

This extractor joins `Visit.tsv` to resolve that UUID to `"HEALTH_EXAMINATION"`
before building per-visit stats, so C8 can compare visit distributions correctly.

---

## Usage

```bash
# Minimal — run from the directory containing DMC_* folders
python extract_harmonized_summaries.py --cohort COPDGene

# With explicit harmonized root
python extract_harmonized_summaries.py \
    --cohort SPIROMICS \
    --harmonized-root /enclave/SPIROMICS-BDCHM

# Including per-visit breakdowns
python extract_harmonized_summaries.py \
    --cohort SPIROMICS \
    --harmonized-root /enclave/SPIROMICS-BDCHM \
    --by-visit

# Write to a specific directory
python extract_harmonized_summaries.py \
    --cohort SPIROMICS \
    --harmonized-root /enclave/SPIROMICS-BDCHM \
    --output-dir /enclave/dataqc-runs/
```

### All Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--cohort NAME` | Yes | Cohort name (used in output filename) |
| `--harmonized-root DIR` | No | Root dir containing `DMC_*` run directories. Defaults to `.` (current directory) if omitted. |
| `--mapped-data-dirs DIR ...` | No | Explicit list of `mapped-data/` directories (mutually exclusive with `--harmonized-root`). |
| `--by-visit` | No | Include per-visit variable breakdowns. |
| `--output-dir DIR` | No | Output directory. Defaults to `<harmonized-root>/dataqc-runs/`. |
| `--output FILE` | No | Override output JSON filename |

---

## Output JSON Format

```json
{
  "metadata": {
    "source": "bdc_dmbip",
    "cohort": "SPIROMICS",
    "generated_at": "2025-01-01T12:00:00+00:00",
    "run_timestamp": "20250101_120000",
    "by_visit": false,
    "uuid_map_size": 8
  },
  "total_participants": 2973,
  "total_rows": 62437,
  "datasets_loaded": ["Visit", "Demography", "MeasurementObservation", ...],
  "entity_counts": {"Visit": 8, "Demography": 2973, ...},
  "rows_per_visit": {"HEALTH_EXAMINATION": 8},
  "variables": {
    "measurement_OMOP:4152194": {
      "type": "continuous",
      "entity": "MeasurementObservationSet",
      "observation_type": "OMOP:4152194",
      "n_valid": 7757, "n_missing": 135,
      "mean": 126.4, "sd": 18.2, ...
    },
    "condition_MONDO:0005002": {
      "type": "categorical",
      "entity": "Condition",
      "condition_concept": "MONDO:0005002",
      "distribution": {"PRESENT": {"n": 2973, "pct": 100.0}}
    }
  }
}
```

---

## Expected dm-bip Directory Layout

```
<harmonized-root>/
    DMC_<cohort>_<study>_c1_<COHORT>_Processed_<timestamp>/
        <cohort>_<study>_c1_BDCHM/
            mapped-data/
                Demography.tsv
                MeasurementObservation.tsv
                MeasurementObservationSet.tsv
                Condition.tsv
                Observation.tsv
                Visit.tsv
                ...
            validation-logs/
    DMC_..._c2_.../ ...
```

---

## Requirements

```
pandas >= 1.3
```

No YAML dependency. No dependency on any other hv-dataqc script.
