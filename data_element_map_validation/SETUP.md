# Semantic Review Curator — Installation & Setup

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) — install once, then from the repo root:
  ```
  uv sync
  ```

## Directory Structure

```
data_element_map_validation/
├── scripts/
│   ├── curator_review_app.py              # Streamlit app
│   ├── generate_curie_mapreview.py        # Pipeline step 1
│   ├── generate_semantic_review.py        # Pipeline step 2
│   ├── generate_release_report.py         # Release report generator
│   ├── mondo_agent.py                     # MONDO ontology CURIE lookup
│   ├── hpo_agent.py                       # HPO phenotype CURIE lookup
│   ├── omop_agent.py                      # OMOP concept CURIE lookup
│   ├── rxnorm_agent.py                    # RxNorm drug CURIE lookup
│   ├── measurementObs_agent.py            # LOINC measurement CURIE lookup
│   ├── uberon_agent.py                    # UBERON anatomy CURIE lookup
│   └── omop_visit_agent.py                # OMOP visit concept lookup
├── bdc_study_input/
│   ├── BDC_registered_study_for_semantic_review.csv     # Study registry
│   └── {STUDY}_curie.csv                                # Per-study input (one per study)
└── valueset_mapping_review_output/
    ├── {STUDY}_Semantic_Review_Final_Reviewer-*.md      # Source reviewer MD (required)
    ├── pending_change/                                  # Auto-managed
    └── change_log/                                      # Auto-managed
```

YAML transform files must exist at:
```
../priority_variables_transform/{STUDY}-ingest/*.yaml
```
(relative to `data_element_map_validation/`)

## Running the App

In a terminal from the `data_element_map_validation/` directory:
```bash
uv run streamlit run curator_review_app.py --server.port 8501
```
Then open **http://localhost:8501** in your browser.

> The terminal window must remain open while using the app. Open a separate terminal for other commands.

## Preparing a Study for Review

Each study requires two input files before it can be reviewed:

1. **`bdc_study_input/{STUDY}_curie.csv`** — CURIE mapping input (one row per variable, filtered to the study's cohort only)
2. **`valueset_mapping_review_output/{STUDY}_Semantic_Review_Final_Reviewer-*.md`** — Source reviewer markdown

Once those exist, select the study in the sidebar and click **🚀 Run {STUDY} Curie Review**. The app runs both pipeline steps sequentially and displays a live log. When complete, the study is ready for curator review.

To re-run just the semantic review step (e.g. after a fix), go to:
**⚙️ Setup tab → Run individual steps → 📝 Generate semantic review MD**

## Adding a New Study

Add a row to `bdc_study_input/BDC_registered_study_for_semantic_review.csv` with:

| Column | Description |
|---|---|
| `cohort_study_short_name` | Short identifier used as file prefix — no `/` characters (e.g. `HCHS` not `HCHS/SOL`) |
| `cohort_study_description` | Full display label shown in the sidebar |
| `short_name_and_description` | Formatted label for the review MD header |
| `yaml_file_path` | Relative path from the CSV to the study's YAML ingest directory (e.g. `../../priority_variables_transform/HCHS-ingest`) |

## Study File Naming Convention

All generated files are prefixed with the study's short name:

| File | Location |
|---|---|
| `{STUDY}_curie.csv` | `bdc_study_input/` |
| `{STUDY}_curie_mapreview.csv` | `bdc_study_input/` |
| `{STUDY}_semantic_review_v{YYYY_MMDD}.md` | `valueset_mapping_review_output/` |
| `{STUDY}_semantic_validator_summary_v{YYYY_MMDD}.md` | `valueset_mapping_review_output/` |
| `{STUDY}_pending_changes.json` | `valueset_mapping_review_output/pending_change/` |
| `{STUDY}_change_request_{YYYYMMDD}_{NN}.json` | `valueset_mapping_review_output/change_log/` |

## Running Pipeline Steps Manually

Both pipeline scripts accept a `--study` argument:

```bash
# Step 1 — CURIE map-review (slow: makes live API calls)
uv run python scripts/generate_curie_mapreview.py --study CHS

# Step 2 — Semantic review MD generation (fast: no API calls)
uv run python scripts/generate_semantic_review.py --study CHS

# Release report — aggregates all applied changes across studies
uv run python scripts/generate_release_report.py
```

Available study names match the `cohort_study_short_name` values in the registry CSV.
