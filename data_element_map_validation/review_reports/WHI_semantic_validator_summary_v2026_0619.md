# WHI Semantic Validator Summary v2026-06-19

**Generated:** 2026-06-19
**Mapreview CSV:** `WHI_curie_mapreview.csv`
**Review MD:** `(none — generated from mapreview CSV only)`

---

## Overview

| Metric | Count |
| :---- | ----: |
| Total rows in mapreview CSV | 776 |
| Admin variables skipped | 0 |
| Substantive variables reviewed | 776 |
| Unique CURIEs validated | 116 |
| Unique YAML files referenced | 69 |
| Final Confirmed Findings rows | 23 |
| Anne Review Required rows | 0 |

## YAML Spot-Check

| Result | Count |
| :---- | ----: |
| Matches (✓) | 581 |
| Mismatches (⚠) | 32 |
| Not checked (admin / no YAML) | 163 |

**32 mismatch(es) require correction:**

| Variable | YAML File | CSV CURIE | YAML CURIE |
| :---- | :---- | :---- | :---- |
| SPANISH | demography.yaml | `OMOP:45880900` | `[5 mappings]` |
| SPANISH | demography.yaml | `OMOP:8557` | `[5 mappings]` |
| WHITE | demography.yaml | `OMOP:45880900` | `[5 mappings]` |
| WHITE | demography.yaml | `OMOP:8557` | `[5 mappings]` |
| BLACK | demography.yaml | `OMOP:45880900` | `[5 mappings]` |
| BLACK | demography.yaml | `OMOP:8557` | `[5 mappings]` |
| AMERINDIAN | demography.yaml | `OMOP:45880900` | `[5 mappings]` |
| AMERINDIAN | demography.yaml | `OMOP:8557` | `[5 mappings]` |
| ASIAINDIAN | demography.yaml | `OMOP:45880900` | `[5 mappings]` |
| ASIAINDIAN | demography.yaml | `OMOP:8557` | `[5 mappings]` |
| CHINESE | demography.yaml | `OMOP:45880900` | `[5 mappings]` |
| CHINESE | demography.yaml | `OMOP:8557` | `[5 mappings]` |
| FILIPINO | demography.yaml | `OMOP:45880900` | `[5 mappings]` |
| FILIPINO | demography.yaml | `OMOP:8557` | `[5 mappings]` |
| JAPANESE | demography.yaml | `OMOP:45880900` | `[5 mappings]` |
| JAPANESE | demography.yaml | `OMOP:8557` | `[5 mappings]` |
| KOREAN | demography.yaml | `OMOP:45880900` | `[5 mappings]` |
| KOREAN | demography.yaml | `OMOP:8557` | `[5 mappings]` |
| VIETNAMESE | demography.yaml | `OMOP:45880900` | `[5 mappings]` |
| VIETNAMESE | demography.yaml | `OMOP:8557` | `[5 mappings]` |
| OTHERASIAN | demography.yaml | `OMOP:45880900` | `[5 mappings]` |
| OTHERASIAN | demography.yaml | `OMOP:8557` | `[5 mappings]` |
| HAWAIIAN | demography.yaml | `OMOP:45880900` | `[5 mappings]` |
| HAWAIIAN | demography.yaml | `OMOP:8557` | `[5 mappings]` |
| GUAMANIAN | demography.yaml | `OMOP:45880900` | `[5 mappings]` |
| GUAMANIAN | demography.yaml | `OMOP:8557` | `[5 mappings]` |
| SAMOAN | demography.yaml | `OMOP:45880900` | `[5 mappings]` |
| SAMOAN | demography.yaml | `OMOP:8557` | `[5 mappings]` |
| OTHRPACISL | demography.yaml | `OMOP:45880900` | `[5 mappings]` |
| OTHRPACISL | demography.yaml | `OMOP:8557` | `[5 mappings]` |
| OTHERRACE | demography.yaml | `OMOP:45880900` | `[5 mappings]` |
| OTHERRACE | demography.yaml | `OMOP:8557` | `[5 mappings]` |

## Agent Coverage by Entity Type

| Entity Type | Unique vars | MONDO | HPO | OMOP/LOINC | No suggestion |
| :---- | ----: | ----: | ----: | ----: | ----: |
| Condition | 44 | 44 | 0 | 0 | 0 |
| Condition (HPO) | 1 | 0 | 1 | 0 | 0 |
| Condition (OMOP fallback) | 12 | 0 | 0 | 12 | 0 |
| Demography | 10 | 0 | 0 | 5 | 5 |
| Measurement | 79 | 0 | 0 | 79 | 0 |
| Person | 5 | 0 | 0 | 0 | 5 |
| Procedure | 2 | 0 | 0 | 2 | 0 |
| ValueEnum | 1 | 0 | 0 | 0 | 1 |
| **Total** | **154** | | | | **11** |

**Coverage: 143/154 unique variable-slot pairs have at least one agent suggestion (92%).**

## Agent vs CSV CURIE Alignment

Agent suggestions differ from the current CSV CURIE in **121** variable-slot pair(s).

### Potential Improvements (106 — YAML confirms CSV, agent suggests different)

These cases have a YAML-confirmed CSV CURIE but the agent suggests a different concept.
Review whether the agent suggestion is more specific or accurate.

| Variable | Slot | Entity Type | CSV / YAML CURIE | Agent Suggestion |
| :---- | :---- | :---- | :---- | :---- |
| AFEMBOSTRK | condition_concept | Condition | `MONDO:0006809` | `MONDO:1060198` |
| AGE | condition_concept | Condition | `MONDO:0004981` | `MONDO:0018083` |
| ANGINA_3 | condition_concept | Condition | `HP:0001681` | `MONDO:0006576` |
| ANGINA_4 | condition_concept | Condition | `HP:0001681` | `MONDO:0006576` |
| ANGINA_5 | condition_concept | Condition | `HP:0001681` | `MONDO:0006576` |
| ANGINA_6 | condition_concept | Condition | `HP:0001681` | `MONDO:0006576` |
| ANGINA_7 | condition_concept | Condition | `HP:0001681` | `MONDO:0006576` |
| ANGINA_8 | condition_concept | Condition | `HP:0001681` | `MONDO:0006576` |
| CAROTID | condition_concept | Condition | `OMOP:4102124` | `MONDO:0005269` |
| EMPHYSEM_3 | condition_concept | Condition | `MONDO:0005002` | `MONDO:0004849` |
| EMPHYSEM_4 | condition_concept | Condition | `MONDO:0005002` | `MONDO:0004849` |
| EMPHYSEM_5 | condition_concept | Condition | `MONDO:0005002` | `MONDO:0004849` |
| EMPHYSEM_6 | condition_concept | Condition | `MONDO:0005002` | `MONDO:0004849` |
| EMPHYSEM_7 | condition_concept | Condition | `MONDO:0005002` | `MONDO:0004849` |
| EMPHYSEM_8 | condition_concept | Condition | `MONDO:0005002` | `MONDO:0004849` |
| HTNTRT | condition_concept | Condition | `HP:0000822` | `MONDO:0001105` |
| MI | condition_concept | Condition | `MONDO:0005068` | `MONDO:0008097` |
| MIAGE | condition_concept | Condition | `MONDO:0005068` | `MONDO:0700247` |
| PADDX | condition_concept | Condition | `HP:0002621` | `MONDO:0002687` |
| STRKHEMO | condition_concept | Condition | `HP:0001342` | `MONDO:1060199` |
| STRKISCH | condition_concept | Condition | `HP:0002140` | `MONDO:1060198` |
| STRKREL | condition_concept | Condition | `HP:0001297` | `MONDO:0100150` |
| STROKEDX | condition_concept | Condition (HPO) | `HP:0002170` | `HP:0030907` |
| ANGECGST | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:315832` |
| ANGINAHX | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:45766938` |
| ASTHMA | condition_concept | Condition (OMOP fallback) | `MONDO:0004979` | `OMOP:317009` |
| ATRIALFB | condition_concept | Condition (OMOP fallback) | `MONDO:0004981` | `OMOP:313217` |
| CAROTIDDY | condition_concept | Condition (OMOP fallback) | `OMOP:4102124` | `OMOP:36308753` |
| ECGVTYP | condition_concept | Condition (OMOP fallback) | `MONDO:0004981` | `OMOP:4259643` |
| ECGVY | condition_concept | Condition (OMOP fallback) | `MONDO:0004981` | `OMOP:9448` |
| HFDIAG | condition_concept | Condition (OMOP fallback) | `MONDO:0005252` | `OMOP:36308337` |
| PAD | condition_concept | Condition (OMOP fallback) | `MONDO:0005386` | `OMOP:21498362` |
| PEHX | condition_concept | Condition (OMOP fallback) | `MONDO:0005279` | `OMOP:45883963` |
| PULMHTNHX | condition_concept | Condition (OMOP fallback) | `MONDO:0005149` | `OMOP:42538094` |
| PVDHX | condition_concept | Condition (OMOP fallback) | `MONDO:0005294` | `OMOP:4031511` |
| ALCSWK | observation_type | Measurement | `OMOP:35609491` | `LOINC:106630-7` |
| BMI | observation_type | Measurement | `OBA:2045455` | `LOINC:39156-5` |
| BMIX | observation_type | Measurement | `OBA:2045455` | `LOINC:39156-5` |
| BNPLAST | observation_type | Measurement | `OBA:2045303` | `LOINC:63201-8` |
| BNPULN | observation_type | Measurement | `OBA:2045303` | `LOINC:63201-8` |
| BNPWORST | observation_type | Measurement | `OBA:2045303` | `LOINC:63201-8` |
| BUN | observation_type | Measurement | `OBA:VT0005265` | `LOINC:63201-8` |
| CBCVTYP | observation_type | Measurement | `OBA:2045381` | `LOINC:99633-0` |
| CBCVY | observation_type | Measurement | `OBA:2045381` | `LOINC:99633-0` |
| COREF7AG | observation_type | Measurement | `OBA:2041535` | `LOINC:51662-5` |
| COREF7C | observation_type | Measurement | `OBA:2041535` | `LOINC:52515-4` |
| COREFIBR | observation_type | Measurement | `OBA:0000061` | `LOINC:52514-7` |
| COREGLUC | observation_type | Measurement | `OBA:VT0000188` | `LOINC:52514-7` |
| COREHDLC | observation_type | Measurement | `OBA:VT0000184` | `LOINC:52514-7` |
| CORELDLC | observation_type | Measurement | `OBA:VT0000181` | `LOINC:52514-7` |
| CORETCHO | observation_type | Measurement | `OBA:VT0000180` | `LOINC:52515-4` |
| CORETRI | observation_type | Measurement | `OBA:VT0002644` | `LOINC:51662-5` |
| COREVTYP | observation_type | Measurement | `OBA:2041535` | `LOINC:76427-4` |
| COREVY | observation_type | Measurement | `OBA:2041535` | `LOINC:76427-4` |
| ECGVTYP | observation_type | Measurement | `OBA:1001087` | `LOINC:71575-5` |
| ECGVY | observation_type | Measurement | `OBA:1001087` | `LOINC:71575-5` |
| F60ALCWK | observation_type | Measurement | `OMOP:35609491` | `LOINC:106630-7` |
| F60FRUIT | observation_type | Measurement | `OMOP:21493059` | `LOINC:46013-9` |
| F60SODUM | observation_type | Measurement | `OMOP:606729` | `LOINC:77243-4` |
| F80VTYP | observation_type | Measurement | `OBA:VT0001253` | `LOINC:76427-4` |
| F80VY | observation_type | Measurement | `OBA:VT0001253` | `LOINC:76427-4` |
| FRUITS | observation_type | Measurement | `OMOP:21493059` | `LOINC:45239-1` |
| HEARTRATE | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| HEART_RT | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| HEI1 | observation_type | Measurement | `OMOP:21493059` | `LOINC:32897-1` |
| HEI3 | observation_type | Measurement | `OMOP:4042886` | `LOINC:112280-3` |
| HEIGHT | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| HEIGHTX | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| HEMATOCR | observation_type | Measurement | `OBA:2045381` | `LOINC:4544-3` |
| HEMATOCRIT | observation_type | Measurement | `OBA:2045381` | `LOINC:4544-3` |
| HEMOGLBN | observation_type | Measurement | `OBA:2060175` | `LOINC:718-7` |
| HEMOGLOBIN | observation_type | Measurement | `OBA:2060175` | `LOINC:718-7` |
| HIPX | observation_type | Measurement | `OBA:1000032` | `LOINC:7471-6` |
| HRSSLP | observation_type | Measurement | `OBA:2040171` | `LOINC:65968-0` |
| INCOME | observation_type | Measurement | `OMOP:4076114` | `LOINC:97075-6` |
| INCOME_3 | observation_type | Measurement | `OMOP:4076114` | `LOINC:63507-8` |
| INCOME_6 | observation_type | Measurement | `OMOP:4076114` | `LOINC:63508-6` |
| PLATELET | observation_type | Measurement | `OMOP:4267147` | `LOINC:777-3` |
| PROBNPLAST | observation_type | Measurement | `OBA:2045303` | `LOINC:63201-8` |
| PROBNPULN | observation_type | Measurement | `OBA:2045303` | `LOINC:63201-8` |
| PROBNPWORST | observation_type | Measurement | `OBA:2045303` | `LOINC:63201-8` |
| PR_DUR | observation_type | Measurement | `OMOP:4274406` | `LOINC:18529-8` |
| QRS_DUR | observation_type | Measurement | `OBA:1001086` | `LOINC:8633-0` |
| QT_DUR | observation_type | Measurement | `OMOP:4273023` | `LOINC:8634-8` |
| SERUMCREAT | observation_type | Measurement | `OBA:2050096` | `LOINC:63201-8` |
| SLEEPING | observation_type | Measurement | `OBA:2040171` | `LOINC:9800-4` |
| SLEEPING_3 | observation_type | Measurement | `OBA:2040171` | `LOINC:55420-4` |
| SLEEPING_6 | observation_type | Measurement | `OBA:2040171` | `LOINC:55420-4` |
| SMOKING | observation_type | Measurement | `OMOP:4282779` | `LOINC:111839-7` |
| SODIUM | observation_type | Measurement | `OBA:VT0001776` | `LOINC:7146-4` |
| SUBJID | observation_type | Measurement | `OBA:VT0001253` | `LOINC:106515-0` |
| TROPWORSTVAL | observation_type | Measurement | `OMOP:4021291` | `LOINC:7146-4` |
| VEGTABLS | observation_type | Measurement | `OMOP:4042886` | `LOINC:45239-1` |
| WAIST | observation_type | Measurement | `OBA:1001085` | `LOINC:8280-0` |
| WAISTX | observation_type | Measurement | `OBA:1001085` | `LOINC:8280-0` |
| WBC | observation_type | Measurement | `OBA:VT0000217` | `LOINC:67750-0` |
| WEIGHT | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| WEIGHTX | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| WHRX | observation_type | Measurement | `OMOP:4087501` | `LOINC:56087-0` |
| WTCUR_4 | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| WTCUR_5 | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| WTCUR_6 | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| WTCUR_7 | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| WTCUR_8 | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| WTCUR_X2 | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| CABG | procedure_concept | Procedure | `OMOP:4336464` | `OMOP:45883443` |

### Unverified Misalignments (15 — no YAML confirmation)

| Variable | Slot | Entity Type | CSV CURIE | Agent Suggestion |
| :---- | :---- | :---- | :---- | :---- |
| BLACK | race | Demography | `OMOP:45880900` | `OMOP:8516` |
| FILIPINO | race | Demography | `OMOP:45880900` | `OMOP:38003581` |
| HAWAIIAN | race | Demography | `OMOP:45880900` | `OMOP:8657` |
| OTHERASIAN | race | Demography | `OMOP:45880900` | `OMOP:8515` |
| WHITE | race | Demography | `OMOP:45880900` | `OMOP:8527` |
| DIAS | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| DIASBP1 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| DIASBP2 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| F80VTYP | observations | Measurement | `OMOP:4152194` | `LOINC:76427-4` |
| F80VY | observations | Measurement | `OMOP:4152194` | `LOINC:76427-4` |
| SUBJID | observations | Measurement | `OMOP:4152194` | `LOINC:106515-0` |
| SYST | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SYSTBP1 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SYSTBP2 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| ECGVY | procedure_concept | Procedure | `OMOP:45772840` | `OMOP:9448` |

## Vocab/Slot Validation

Agent suggestions suppressed as vocabulary/slot mismatches (evaluated but not surfaced as findings): **35**

| Slot | Invalid vocab proposed | Suppressed count | Rule |
| :---- | :---- | ----: | :---- |
| `observation_type` | LOINC | 35 | Valid: OBA, OMOP |
| **Total** | | **35** | |

_These are not errors — they confirm the existing CURIEs are correct for their slots. The agent proposed codes from a vocabulary the bdchm slot is not typed for (e.g. OMOP in a MONDO-typed slot, LOINC in an OBA-typed slot). See `_SLOT_VOCAB_RULES` in `generate_semantic_review.py` for the full rule definitions._

## Error Cases Requiring Fix

### YAML Mismatches — 32 must be corrected
See the YAML Spot-Check section above.

No unexpected missing suggestions — all substantive variable-slot pairs either have an agent suggestion or are in a slot type with no agent routing (ValueEnum, Demography, DrugExposure without RxNorm match).
