# COPDGene Semantic Validator Summary v2026-06-19

**Generated:** 2026-06-19
**Mapreview CSV:** `COPDGene_curie_mapreview.csv`
**Review MD:** `COPDGene Semantic-Review-Final-Reviewer-2026-05-31.md`

---

## Overview

| Metric | Count |
| :---- | ----: |
| Total rows in mapreview CSV | 302 |
| Admin variables skipped | 160 |
| Substantive variables reviewed | 142 |
| Unique CURIEs validated | 64 |
| Unique YAML files referenced | 45 |
| Final Confirmed Findings rows | 21 |
| Anne Review Required rows | 8 |

## YAML Spot-Check

| Result | Count |
| :---- | ----: |
| Matches (✓) | 76 |
| Mismatches (⚠) | 1 |
| Not checked (admin / no YAML) | 65 |

**1 mismatch(es) require correction:**

| Variable | YAML File | CSV CURIE | YAML CURIE |
| :---- | :---- | :---- | :---- |
| lymphcyt | lymphocyte_ct.yaml | `OBA:VT0000217` | `OBA:VT0000717` |

## Agent Coverage by Entity Type

| Entity Type | Unique vars | MONDO | HPO | OMOP/LOINC | No suggestion |
| :---- | ----: | ----: | ----: | ----: | ----: |
| Condition | 19 | 19 | 0 | 0 | 0 |
| Demography | 4 | 0 | 0 | 2 | 2 |
| DrugExposure | 2 | 0 | 0 | 0 | 2 |
| DrugRoute | 1 | 0 | 0 | 1 | 0 |
| Measurement | 34 | 0 | 0 | 34 | 0 |
| ValueEnum | 1 | 0 | 0 | 0 | 1 |
| **Total** | **61** | | | | **5** |

**Coverage: 56/61 unique variable-slot pairs have at least one agent suggestion (91%).**

## Agent vs CSV CURIE Alignment

Agent suggestions differ from the current CSV CURIE in **40** variable-slot pair(s).

### Potential Improvements (26 — YAML confirms CSV, agent suggests different)

These cases have a YAML-confirmed CSV CURIE but the agent suggests a different concept.
Review whether the agent suggestion is more specific or accurate.

| Variable | Slot | Entity Type | CSV / YAML CURIE | Agent Suggestion |
| :---- | :---- | :---- | :---- | :---- |
| Angina | condition_concept | Condition | `HP:0001681` | `MONDO:0006576` |
| HighBloodPres | condition_concept | Condition | `HP:0000822` | `MONDO:0005044` |
| SleepApAge | condition_concept | Condition | `HP:0010535` | `MONDO:0005296` |
| SleepApnea | condition_concept | Condition | `HP:0010535` | `MONDO:0005296` |
| Stroke | condition_concept | Condition | `HP:0001297` | `MONDO:0005098` |
| race | race | Demography | `OMOP:45880900` | `OMOP:8527` |
| BMI | observation_type | Measurement | `OBA:2045455` | `LOINC:39156-5` |
| HR | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| Height_CM | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| MCH | observation_type | Measurement | `OBA:2045301` | `LOINC:785-6` |
| MCHC | observation_type | Measurement | `OMOP:37393850` | `LOINC:786-4` |
| MCV | observation_type | Measurement | `OBA:0003460` | `LOINC:787-2` |
| Platelets | observation_type | Measurement | `OMOP:4267147` | `LOINC:777-3` |
| RBC | observation_type | Measurement | `OBA:VT0001586` | `LOINC:789-8` |
| Resting_SaO2 | observation_type | Measurement | `OBA:2045443` | `LOINC:59408-5` |
| Waist_CM | observation_type | Measurement | `OBA:1001085` | `LOINC:8280-0` |
| Weight_KG | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| alcohol_how_often | observation_type | Measurement | `OMOP:35609491` | `LOINC:68518-0` |
| basophl | observation_type | Measurement | `OBA:VT0002607` | `LOINC:26444-0` |
| eosinphl | observation_type | Measurement | `OBA:VT0002602` | `LOINC:26449-9` |
| hematocrit | observation_type | Measurement | `OBA:2045381` | `LOINC:4544-3` |
| hemoglobin | observation_type | Measurement | `OBA:2060175` | `LOINC:718-7` |
| monocyt | observation_type | Measurement | `OBA:VT0000223` | `LOINC:26484-6` |
| neutrophl | observation_type | Measurement | `OBA:VT0000222` | `LOINC:26499-4` |
| smoking_status | observation_type | Measurement | `OMOP:4282779` | `LOINC:111839-7` |
| wbc | observation_type | Measurement | `OBA:VT0000217` | `LOINC:6690-2` |

### Unverified Misalignments (14 — no YAML confirmation)

| Variable | Slot | Entity Type | CSV CURIE | Agent Suggestion |
| :---- | :---- | :---- | :---- | :---- |
| FEV1_FVC_post | observations | Measurement | `OMOP:3005600` | `LOINC:19875-1` |
| FEV1_FVC_pre | observations | Measurement | `OMOP:3002094` | `LOINC:19874-4` |
| FEV1_post | observations | Measurement | `OMOP:3005600` | `LOINC:20155-8` |
| FEV1_pre | observations | Measurement | `OMOP:3002094` | `LOINC:20150-9` |
| FEV1pp_post | observations | Measurement | `OMOP:3005600` | `LOINC:20151-7` |
| FVC_post | observations | Measurement | `OMOP:3005600` | `LOINC:19870-2` |
| FVC_pre | observations | Measurement | `OMOP:3002094` | `LOINC:19868-6` |
| FVCpp_post | observations | Measurement | `OMOP:3005600` | `LOINC:20152-5` |
| Pred_FEV1 | observations | Measurement | `OMOP:3002094` | `LOINC:20150-9` |
| Pred_FEV1_FVC | observations | Measurement | `OMOP:3002094` | `LOINC:20150-9` |
| Pred_FVC | observations | Measurement | `OMOP:3002094` | `LOINC:20152-5` |
| diasBP | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| lymphcyt | observation_type | Measurement | `OBA:VT0000217` | `LOINC:26474-7` |
| sysBP | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |

## Vocab/Slot Validation

Agent suggestions suppressed as vocabulary/slot mismatches (evaluated but not surfaced as findings): **21**

| Slot | Invalid vocab proposed | Suppressed count | Rule |
| :---- | :---- | ----: | :---- |
| `observation_type` | LOINC | 21 | Valid: OBA, OMOP |
| **Total** | | **21** | |

_These are not errors — they confirm the existing CURIEs are correct for their slots. The agent proposed codes from a vocabulary the bdchm slot is not typed for (e.g. OMOP in a MONDO-typed slot, LOINC in an OBA-typed slot). See `_SLOT_VOCAB_RULES` in `generate_semantic_review.py` for the full rule definitions._

## Error Cases Requiring Fix

### YAML Mismatches — 1 must be corrected
See the YAML Spot-Check section above.

### Missing Agent Suggestions — 2 variable-slot pair(s)

These substantive variables received no suggestion from any agent.
Investigate whether a suitable ontology term exists or the slot routing needs updating.

| Variable | Slot | Entity Type | Description |
| :---- | :---- | :---- | :---- |
| CortsterOral | drug_concept | DrugExposure | Oral corticosteroids |
| Cortsterinhal | drug_concept | DrugExposure | Inhaled corticosteroids |
