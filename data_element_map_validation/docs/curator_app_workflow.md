# Curator App Workflow

## Phase 1 — Data Preparation
**Done once per study, or when source data changes**

### Inputs
- dbGaP variables / codebook  
  ↓ *(manual / external process)*

### Source of truth
- `{study}_curie.csv` — curator-maintained source of truth

### Columns
- Cohort
- PHT
- PHV
- Variable Name
- Variable Description
- CURIE
- Slot
- Entity Type
- YAML File

> This CSV is the only file you manually maintain. Everything downstream is generated from it.

---

## Phase 2 — Pipeline
**Setup tab → “Run full pipeline” or individual steps**

### Step 1: Generate map review
**Input**
- `{study}_curie.csv`

**Process**
- `generate_curie_mapreview.py`
- Calls MONDO / HPO / OMOP / RxNorm / LOINC agents

**Output**
- `{study}_curie_mapreview.csv`

**Adds columns**
- `yaml_curie`
- `yaml_match` (`✓` / `⚠`)
- `omop_maps_to`
- `mondo_maps_to`
- `hpo_maps_to`
- `maps_to_entity_type`

---

### Step 2: Generate semantic review
**Input**
- `{study}_curie_mapreview.csv`
- source reviewer markdown

**Process**
- `generate_semantic_review.py`
- No API calls; reads map review + source reviewer MD

**Output**
- `{study}_semantic_review_v{date}.md`  
  ← the review MD the app reads

**Adds column**
- `semantic validator review`  
  (CURIE match/mismatch analysis)

---

### Optional fast mode
Step 1 can be run with `--no-agents` for a fast YAML-check-only pass when you only edited the CURIE CSV and do not need new agent suggestions.

---

## Phase 3 — Curator Review
**Main app tabs**

### Reviewer Findings tab
- One row per mismatch (`csv_curie ≠ yaml_curie`) or flagged finding
- Details panel shows:
  - current YAML CURIE
  - CSV CURIE
  - agent suggestions
- Curator enters:
  - `change_request` CURIE
  - optional notes
- Save → writes to:
  - `pending_change/{study}_pending_changes.json`

### Other tabs during review
- **Manual Curation Notes** — orphan pending entries (no matching review row)
- **Cross-Study Consistency** — same YAML file mapped to different CURIEs across studies
- **Summary** — counts of pending / applied / no-change across all findings
- **Previously Committed** — already-applied entries with their new CURIEs

---

## Phase 4 — Submit
**Submit tab**

### Input
- `pending_change/{study}_pending_changes.json`  
  (contains `change_request` entries)

### Action
- Click **Submit All**

### Processing
- `_apply_yaml()`  
  rewrites CURIE in:
  - `priority_variables_transform/{study}-ingest/{file}.yaml`

- `_apply_csv()`  
  rewrites CURIE in:
  - `bdc_study_input/{study}_curie.csv`

- Marks entry:
  - `applied: true` in pending JSON

### Audit outputs
- `change_log/{study}_change_request_{date}_{nn}.json`  
  ← permanent log
- `{study}_curie_changerequest_v{date}.csv`  
  ← export for downstream

---

## Phase 5 — Git Commit & CI

### Modified files to commit
- `priority_variables_transform/{study}-ingest/*.yaml`  
  (CURIE values updated)

- `data_element_map_validation/bdc_study_input/{study}_curie.csv`  
  (source CSV updated)

### CI validates
- All ingest YAMLs pass linkml-map schema validation
- No stale `poetry.lock`

---

## Decision Points During Review

| Situation | Action |
|---|---|
| CSV CURIE matches YAML | No finding generated — nothing to review |
| CSV CURIE ≠ YAML CURIE | Finding generated → curator decides which is correct |
| Agent suggests a better CURIE | Shown in Details; curator can accept or override |
| Variable needs no change | “Mark as reviewed — no change” → `no_change: true` in pending |
| YAML has structural bug (wrong relationship, missing block) | Outside the app → fix YAML directly, commit, re-run pipeline |

---