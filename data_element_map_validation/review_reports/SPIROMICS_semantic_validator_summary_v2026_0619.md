# SPIROMICS Semantic Validator Summary v2026-06-19

**Generated:** 2026-06-19
**Mapreview CSV:** `SPIROMICS_curie_mapreview.csv`
**Review MD:** `(none — generated from mapreview CSV only)`

---

## Overview

| Metric | Count |
| :---- | ----: |
| Total rows in mapreview CSV | 208 |
| Admin variables skipped | 1 |
| Substantive variables reviewed | 207 |
| Unique CURIEs validated | 39 |
| Unique YAML files referenced | 19 |
| Final Confirmed Findings rows | 9 |
| Anne Review Required rows | 0 |

## YAML Spot-Check

| Result | Count |
| :---- | ----: |
| Matches (✓) | 57 |
| Mismatches (⚠) | 0 |
| Not checked (admin / no YAML) | 150 |

No YAML mismatches found — all spot-checked CURIEs match their YAML files.

## Agent Coverage by Entity Type

| Entity Type | Unique vars | MONDO | HPO | OMOP/LOINC | No suggestion |
| :---- | ----: | ----: | ----: | ----: | ----: |
| Condition | 3 | 3 | 0 | 0 | 0 |
| Condition (HPO) | 1 | 0 | 1 | 0 | 0 |
| Condition (OMOP fallback) | 6 | 0 | 0 | 6 | 0 |
| Demography | 6 | 0 | 0 | 3 | 3 |
| Measurement | 25 | 0 | 0 | 22 | 3 |
| ValueEnum | 2 | 0 | 0 | 0 | 2 |
| **Total** | **43** | | | | **8** |

**Coverage: 35/43 unique variable-slot pairs have at least one agent suggestion (81%).**

## Agent vs CSV CURIE Alignment

Agent suggestions differ from the current CSV CURIE in **34** variable-slot pair(s).

### Potential Improvements (19 — YAML confirms CSV, agent suggests different)

These cases have a YAML-confirmed CSV CURIE but the agent suggests a different concept.
Review whether the agent suggestion is more specific or accurate.

| Variable | Slot | Entity Type | CSV / YAML CURIE | Agent Suggestion |
| :---- | :---- | :---- | :---- | :---- |
| DIABETES_DERV | condition_concept | Condition | `MONDO:0005015` | `MONDO:0006920` |
| HYPERTENSION_DERV | condition_concept | Condition | `HP:0000822` | `MONDO:0001105` |
| STROKE_DERV | condition_concept | Condition | `HP:0001297` | `MONDO:0005098` |
| CHF_DERV | condition_concept | Condition (HPO) | `MONDO:0005009` | `HP:6001138` |
| APNEA_DIAGNOSED | condition_concept | Condition (OMOP fallback) | `HP:0010535` | `OMOP:4123007` |
| CHD_DERV | condition_concept | Condition (OMOP fallback) | `MONDO:0005010` | `OMOP:4250313` |
| CHRONIC_BRONCHITIS | condition_concept | Condition (OMOP fallback) | `MONDO:0005607` | `OMOP:45882678` |
| COPD_DIAGNOSED | condition_concept | Condition (OMOP fallback) | `MONDO:0005002` | `OMOP:45877605` |
| EMPHYSEMA_DIAGNOSED | condition_concept | Condition (OMOP fallback) | `MONDO:0004849` | `OMOP:36769994` |
| OBESITY_DERV | condition_concept | Condition (OMOP fallback) | `OMOP:433736` | `OMOP:45877450` |
| ETHNICITY | race | Demography | `OMOP:45880900` | `OMOP:38003563` |
| RACE | race | Demography | `OMOP:45880900` | `OMOP:8527` |
| AGE_DERV | observation_type | Measurement | `OBA:VT0001253` | `LOINC:30525-0` |
| AGE_DERV | observation_type | Measurement | `OMOP:35811013` | `LOINC:30525-0` |
| AVGHR | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| BMI | observation_type | Measurement | `OBA:2045455` | `LOINC:39156-5` |
| CURRENT_SMOKER | observation_type | Measurement | `OMOP:35811013` | `LOINC:63900-5` |
| HT_CM | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| WT_KG | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |

### Unverified Misalignments (15 — no YAML confirmation)

| Variable | Slot | Entity Type | CSV CURIE | Agent Suggestion |
| :---- | :---- | :---- | :---- | :---- |
| AGE_DERV | observations | Measurement | `OMOP:4152194` | `LOINC:30525-0` |
| AVGDIA | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| AVGSYS | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| PCT_POST_FEV1 | observations | Measurement | `OMOP:3002094` | `LOINC:20150-9` |
| PCT_POST_FEV1FVC | observations | Measurement | `OMOP:3002094` | `LOINC:104637-4` |
| PCT_POST_FVC | observations | Measurement | `OMOP:3002094` | `LOINC:20152-5` |
| PCT_PRE_FEV1 | observations | Measurement | `OMOP:3002094` | `LOINC:20150-9` |
| PCT_PRE_FEV1FVC | observations | Measurement | `OMOP:3002094` | `LOINC:104637-4` |
| PCT_PRE_FVC | observations | Measurement | `OMOP:3002094` | `LOINC:20152-5` |
| POST_FEV1FVC_DERV | observations | Measurement | `OMOP:3002094` | `LOINC:20150-9` |
| POST_FEV1_DERV | observations | Measurement | `OMOP:3002094` | `LOINC:20150-9` |
| POST_FVC_DERV | observations | Measurement | `OMOP:3002094` | `LOINC:20152-5` |
| PRED_FEV1 | observations | Measurement | `OMOP:3002094` | `LOINC:8302-2` |
| PRED_FEV1FVC | observations | Measurement | `OMOP:3002094` | `LOINC:8302-2` |
| PRED_FVC | observations | Measurement | `OMOP:3002094` | `LOINC:8302-2` |

## Vocab/Slot Validation

Agent suggestions suppressed as vocabulary/slot mismatches (evaluated but not surfaced as findings): **11**

| Slot | Invalid vocab proposed | Suppressed count | Rule |
| :---- | :---- | ----: | :---- |
| `condition_concept` | LOINC, OMOP, SNOMED | 6 | Valid: HP, MONDO |
| `observation_type` | LOINC | 5 | Valid: OBA, OMOP |
| **Total** | | **11** | |

_These are not errors — they confirm the existing CURIEs are correct for their slots. The agent proposed codes from a vocabulary the bdchm slot is not typed for (e.g. OMOP in a MONDO-typed slot, LOINC in an OBA-typed slot). See `_SLOT_VOCAB_RULES` in `generate_semantic_review.py` for the full rule definitions._

## Error Cases Requiring Fix

### Missing Agent Suggestions — 3 variable-slot pair(s)

These substantive variables received no suggestion from any agent.
Investigate whether a suitable ontology term exists or the slot routing needs updating.

| Variable | Slot | Entity Type | Description |
| :---- | :---- | :---- | :---- |
| PRE_FEV1FVC_DERV | observations | Measurement | PRE_FEV1FVC_DERV |
| PRE_FEV1_DERV | observations | Measurement | PRE_FEV1_DERV |
| PRE_FVC_DERV | observations | Measurement | PRE_FVC_DERV |
