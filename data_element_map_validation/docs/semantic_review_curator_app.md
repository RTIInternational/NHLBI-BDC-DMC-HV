# Semantic Review Curator — Developer Notes

## Purpose

A Streamlit web app that supports human curation of CURIE (ontology concept identifier) mappings across 11 NHLBI BioData Catalyst (BDC) cohort studies. The app sits at the end of a two-step automated pipeline and provides a structured interface for reviewing agent suggestions, recording curation decisions, and applying corrections to the YAML transform files and curie CSV inputs.

---

## Repository Layout

```
data_element_map_validation/
├── curator_review_app.py              # Streamlit app — single-file, ~1700 lines
├── scripts/
│   ├── generate_curie_mapreview.py    # Step 1 — REST agent queries + YAML spot-check
│   ├── generate_semantic_review.py    # Step 2 — findings MD + summary MD
│   └── pipeline_status.py            # Scans outputs, writes pipeline_status.json
├── bdc_study_input/
│   ├── {STUDY}_curie.csv              # Source CURIE mapping (input, versioned)
│   ├── {STUDY}_curie_mapreview.csv    # Step 1 output — enriched with agent results
│   └── BDC_registered_study_for_semantic_review.csv  # Study registry
├── valueset_mapping_review_output/
│   ├── {STUDY}_semantic_review_v{date}.md             # Step 2 output — findings table
│   ├── {STUDY}_semantic_validator_summary_v{date}.md  # Step 2 output — QC summary
│   ├── pipeline_status.json           # Tracks completion state per study
│   ├── pending_change/
│   │   └── {STUDY}_pending_changes.json   # Curator decision store (git-tracked)
│   └── change_log/
│       └── {STUDY}_change_request_{date}_{n}.json     # Immutable audit log
└── docs/
    ├── mapping_validation_preferences.md   # Vocabulary preferences by domain
    └── semantic_curator_app.md             # This document
```

---

## Two-Step Pipeline

### Step 1 — `generate_curie_mapreview.py`

Reads `{STUDY}_curie.csv` (303–1762 rows per study), queries agents per variable slot, performs a live YAML spot-check, and writes `{STUDY}_curie_mapreview.csv` with the following enriched columns. Five agents make live REST API calls (MONDO, HPO, OMOP, RxNorm, LOINC); one agent (`meds_route_agent`) resolves `route_concept` offline from a curated CSV table with no API call:

| Column | Source |
|:---|:---|
| `yaml_curie` | Live read from the YAML transform file |
| `yaml_match` | `match` / `mismatch` / blank |
| `mondo_maps_to` | MONDO OLS4 REST API best match |
| `hpo_maps_to` | HPO OLS4 REST API best match |
| `omop_maps_to` | OMOP/LOINC Athena API best match |

### Step 2 — `generate_semantic_review.py`

Reads the mapreview CSV and optionally a human reviewer MD file. Produces:

- `{STUDY}_semantic_review_v{date}.md` — findings table with a `semantic validator review` column added to each reviewer row
- `{STUDY}_semantic_validator_summary_v{date}.md` — QC statistics including YAML spot-check, agent coverage by entity type, vocab/slot validation suppression counts, and agent vs CSV misalignment tables

Both steps call `pipeline_status.write_status()` on completion to update `pipeline_status.json`.

---

## Semantic Review Generation Logic

### Row sources — merged in priority order

1. **Human reviewer MD rows** (P1/P2/P3 priority) parsed from the "Reviewer Confirmed Findings" and "Reviewer Questions" sections of the source reviewer MD file
2. **Auto-generated rows** for YAML files not already covered by the reviewer MD (High/Medium priority)

For studies with no human reviewer MD, all rows are auto-generated.

### Auto-generation priority rules (`_auto_generate_rows`)

| Priority | Condition | Rationale |
|:---|:---|:---|
| **High** | Agent suggests a CURIE from a valid vocabulary that differs from the CSV CURIE | Primary goal — fixing incorrect CURIEs in the source CSV |
| **Medium** | CSV CURIE differs from the live value in the YAML file | Secondary — sync issue between CSV and YAML transform |

### Vocab/Slot Validation (`_SLOT_VOCAB_RULES`)

Agent suggestions are suppressed (not surfaced as High findings) when they propose a CURIE from the wrong vocabulary for the slot's declared bdchm schema range. This prevents false positives from polluting the findings list.

| Slot | Valid vocabularies | Invalid (suppressed) | Reason |
|:---|:---|:---|:---|
| `observation_type` | OBA, OMOP | LOINC | LOINC encodes assay procedures (*how*); OBA/OMOP encode biological attributes (*what*). LOINC belongs in `method_type`. |
| `condition_concept` | MONDO, HP | OMOP, SNOMED, LOINC | `ConditionConceptEnum` is typed to MONDO + HP only. OMOP concept IDs belong in the OMOP CDM target column, not the bdchm slot. |

Suppression counts are reported per slot in the summary MD's **Vocab/Slot Validation** section. The `⚠ Vocab/slot mismatch` warning also appears inline in the `semantic validator review` column for reviewer MD rows via `_agent_text()`.

To add a new rule, append an entry to `_SLOT_VOCAB_RULES` in `scripts/generate_semantic_review.py`, re-run the affected studies, and document the rule in `docs/mapping_validation_preferences.md`.

---

## App Architecture

### Session state

| Key | Type | Purpose |
|:---|:---|:---|
| `pending_{study}` | dict | Per-study curation decisions, loaded from JSON on first access |
| `pipeline_running` | bool | Gates pipeline buttons to prevent concurrent runs |
| `_bg_job_id` | str | UUID key into module-level `_BG_JOBS` |
| `_pipeline_result` | dict | Last pipeline run result; displayed in Setup tab with Dismiss button |

### Threading model

Pipeline subprocesses run in a background thread via `_start_bg_pipeline()`. Results are written to the **module-level `_BG_JOBS` dict** — not `st.session_state`, which is unreliable across threads. The main thread polls every 0.5 s via `st.rerun()` until the job completes. Two safety mechanisms guard against stuck state after hot-reloads:

1. **10-minute auto-timeout** via `_pipeline_start_ts`
2. **"Reset stuck pipeline" button** in the sidebar — clears all related session state keys

### Caching

`load_review_rows`, `load_curie_csv`, and `load_mapreview_csv` use `@st.cache_data`. They are explicitly cleared after pipeline runs and after applying changes to ensure the UI reflects the latest file state.

---

## Tab Structure

| Tab | Content |
|:---|:---|
| ⚙️ Setup | Pipeline status table (all studies with input version and release), step 1 and step 2 run buttons, pipeline output log with Dismiss |
| 🔬 Reviewer Findings | Priority-filtered findings list; each row expands to Details + Change Request sub-tabs |
| ✅ Committed | Applied changes (with edit/revert); Reviewed — no change entries (with reopen) |
| 📤 Submit | Pending change request table, batch apply to YAML + curie CSV, CR CSV download |
| 📋 Change Log | Immutable JSON log of all submissions, pending summary, download/clear |
| 📊 Semantic Summary | Summary MD and detailed review MD viewer with download buttons |

### Reviewer Findings row detail

Each row in the findings list expands to two sub-tabs:

- **📋 Details** — issue text, confidence, reviewer, recommended action with linkified CURIEs, current CURIE from live YAML, agent suggestion with OLS hyperlinks, semantic validator review text
- **✏️ Change Request** — slot override, new CURIE input with live validation and OLS preview link, curator notes, Save button; lower section: "Mark reviewed — no change" with required reason field

---

## Curation States

Each finding is tracked in `valueset_mapping_review_output/pending_change/{STUDY}_pending_changes.json`.

| Badge | JSON field | Meaning |
|:---:|:---|:---|
| (none) | — | Unreviewed |
| 📝 | `notes` | Draft notes saved, no CURIE decision yet |
| 💾 | `change_request` | New CURIE proposed, pending application |
| ✅ | `applied: true` | Change written to YAML transform file and curie CSV |
| ☑ | `no_change: true` | Reviewed; deliberately kept existing mapping; reason, reviewer name, and date recorded |

The **☑ Reviewed — no change** state is the correct action for confirmed vocab/slot false positives. It provides a dated audit trail that the finding was seen and evaluated without requiring any file change.

A ☑ entry can be reopened from the Committed tab using the "↩ Reopen" button. Applied (✅) entries can be corrected by queuing a new change request from the same tab.

---

## Pipeline Status Tracking

`valueset_mapping_review_output/pipeline_status.json` is auto-written at the end of each pipeline step and can be refreshed independently by running `python scripts/pipeline_status.py`.

Per-study fields:

| Field | Type | Description |
|:---|:---|:---|
| `input_version` | int | Manually incremented when a new curie CSV is received from the data source. Preserved across pipeline rebuilds — never overwritten automatically. |
| `release` | string \| null | Set manually when a snapshot is handed off to production (e.g. `"001.000"`). Null until released. |
| `mapreview` | object \| null | `{file, completed, rows}` for the Step 1 output |
| `semantic_review` | object \| null | `{file, completed}` for the Step 2 findings MD |
| `summary` | object \| null | `{file, completed}` for the Step 2 summary MD |

**Versioning workflow:** When a new curie CSV arrives for a study, manually increment `input_version` in `pipeline_status.json`, re-run the pipeline for that study, then commit. The JSON preserves the version number through all subsequent rebuilds.

---

## Confirmed Corrections

Curation fixes applied and recorded as of the dates below.

| Date | Study | File | Slot | Old CURIE | New CURIE | Reason |
|:---|:---|:---|:---|:---|:---|:---|
| 2026-06-15 | COPDGene | `lymphocyte_ct.yaml` | `observation_type` | OBA:VT0000217 | OBA:VT0000717 | OBA:VT0000217 is "leukocyte quantity" (total WBC) — wrong for lymphocytes. Correct term is OBA:VT0000717 "lymphocyte quantity". The bdchm schema `LYMPHOCYTES_COUNT` enum entry had the same error. |

---

## Extending the App

### Add a new study

Add a row to `bdc_study_input/BDC_registered_study_for_semantic_review.csv` with the study short name, curie CSV path, and YAML ingest directory path. The app, both pipeline scripts, and `pipeline_status.py` pick it up automatically. Run Step 1 then Step 2 from the Setup tab.

### Add a new vocab/slot validation rule

1. Append an entry to `_SLOT_VOCAB_RULES` in `scripts/generate_semantic_review.py`
2. Re-run the semantic review for all affected studies
3. Document the rule in `docs/mapping_validation_preferences.md`

### Add a new agent

**REST agent** (queries an external API):
1. Add a query function in `generate_curie_mapreview.py` following the pattern of `_query_mondo`, `_query_hpo`, `_query_omop`
2. Wire the result into the mapreview CSV columns
3. Update `_agent_text()` in `generate_semantic_review.py` to include the new column in the validator review text
4. Update `_build_summary_stats()` to count coverage for the new agent

**Offline agent** (static lookup table, no API):
Follow the pattern of `scripts/meds_route_agent.py` — load a reference CSV from `bdc_study_input/`, expose a `get_omop_*_id(text)` function, import it in `_import_agents()` in `generate_curie_mapreview.py`, and wire it into the relevant slot block. To add new entries, update the reference CSV — no code change needed.

---

## Known False Positive Patterns

These patterns produce systematically incorrect High-priority findings and are suppressed by `_SLOT_VOCAB_RULES`. They do not indicate errors in the existing CURIEs.

**1. LOINC replacing OBA in `observation_type`**
The agent returns lab-test codes (LOINC) for measurement variables because the variable description mentions a specific test. The bdchm `observation_type` slot requires biological-attribute terms (OBA/OMOP), not assay codes. Suppressed counts as of 2026-06-15: COPDGene 21, CHS 44, CARDIA 49, HCHS 47, ARIC 61.

**2. OMOP replacing MONDO in `condition_concept`**
The agent returns OMOP CDM concept IDs for condition variables. The bdchm `condition_concept` slot is typed to `ConditionConceptEnum` (MONDO + HP only). OMOP IDs belong in the downstream OMOP CDM `condition_concept_id` column, not in the bdchm model. Suppressed counts as of 2026-06-15: CHS 3, CARDIA 7, HCHS 12, ARIC 15.
