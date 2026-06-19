# JHS Semantic Validator Summary v2026-06-19

**Generated:** 2026-06-19
**Mapreview CSV:** `JHS_curie_mapreview.csv`
**Review MD:** `JHS_Semantic_Review_Final_Reviewer-2026-05-31.md`

---

## Overview

| Metric | Count |
| :---- | ----: |
| Total rows in mapreview CSV | 584 |
| Admin variables skipped | 2 |
| Substantive variables reviewed | 582 |
| Unique CURIEs validated | 104 |
| Unique YAML files referenced | 81 |
| Final Confirmed Findings rows | 24 |
| Anne Review Required rows | 13 |

## YAML Spot-Check

| Result | Count |
| :---- | ----: |
| Matches (✓) | 462 |
| Mismatches (⚠) | 0 |
| Not checked (admin / no YAML) | 120 |

No YAML mismatches found — all spot-checked CURIEs match their YAML files.

## Agent Coverage by Entity Type

| Entity Type | Unique vars | MONDO | HPO | OMOP/LOINC | No suggestion |
| :---- | ----: | ----: | ----: | ----: | ----: |
| Condition | 5 | 5 | 0 | 0 | 0 |
| Condition (HPO) | 4 | 0 | 4 | 0 | 0 |
| Condition (OMOP fallback) | 9 | 0 | 0 | 9 | 0 |
| Measurement | 220 | 0 | 0 | 174 | 46 |
| Procedure | 2 | 0 | 0 | 2 | 0 |
| ValueEnum | 5 | 0 | 0 | 0 | 5 |
| **Total** | **245** | | | | **51** |

**Coverage: 194/245 unique variable-slot pairs have at least one agent suggestion (79%).**

## Agent vs CSV CURIE Alignment

Agent suggestions differ from the current CSV CURIE in **193** variable-slot pair(s).

### Potential Improvements (155 — YAML confirms CSV, agent suggests different)

These cases have a YAML-confirmed CSV CURIE but the agent suggests a different concept.
Review whether the agent suggestion is more specific or accurate.

| Variable | Slot | Entity Type | CSV / YAML CURIE | Agent Suggestion |
| :---- | :---- | :---- | :---- | :---- |
| Diabetes | condition_concept | Condition | `MONDO:0005015` | `MONDO:0012819` |
| HTN | condition_concept | Condition | `HP:0000822` | `MONDO:0044033` |
| LVH | condition_concept | Condition | `HP:0001712` | `MONDO:0012289` |
| age | condition_concept | Condition | `HP:0001513` | `MONDO:0007244` |
| CVDHx | condition_concept | Condition (HPO) | `MONDO:0004995` | `HP:4000114` |
| HF | condition_concept | Condition (HPO) | `MONDO:0005252` | `HP:0006682` |
| abi | condition_concept | Condition (HPO) | `MONDO:0005386` | `HP:0004950` |
| stroke | condition_concept | Condition (HPO) | `HP:0001297` | `HP:0034732` |
| ANGINAEVER | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:45878116` |
| ANGINALASTCNTCT | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:41953976` |
| MSRB29C | condition_concept | Condition (OMOP fallback) | `HP:0001681` | `OMOP:45881107` |
| MSRC29H | condition_concept | Condition (OMOP fallback) | `HP:0001297` | `OMOP:36210384` |
| PFHA20A | condition_concept | Condition (OMOP fallback) | `HP:0001297` | `OMOP:45883183` |
| PFHA5A | condition_concept | Condition (OMOP fallback) | `HP:0001297` | `OMOP:45878116` |
| PFHB36A | condition_concept | Condition (OMOP fallback) | `HP:0001297` | `OMOP:45885061` |
| RPAA14 | condition_concept | Condition (OMOP fallback) | `MONDO:0004979` | `OMOP:45877009` |
| STROKELASTCNTCT | condition_concept | Condition (OMOP fallback) | `HP:0001297` | `OMOP:41953976` |
| ADRA2B | observation_type | Measurement | `OMOP:35609491` | `LOINC:93066-9` |
| ADRB2A | observation_type | Measurement | `OMOP:35609491` | `LOINC:49646-3` |
| ADRB2B | observation_type | Measurement | `OMOP:35609491` | `LOINC:93065-1` |
| ADRB3 | observation_type | Measurement | `OMOP:35609491` | `LOINC:41234-6` |
| AlbuminUSpot | observation_type | Measurement | `OBA:VT0002871` | `LOINC:101681-5` |
| BCFA12A | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| BCFA12B | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| BCFA5 | observation_type | Measurement | `OBA:1001085` | `LOINC:101706-0` |
| BCFA6 | observation_type | Measurement | `OBA:1000032` | `LOINC:110934-7` |
| BCFA8A | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| BCFA8B | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| BCFV12 | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| BCFV5 | observation_type | Measurement | `OBA:1001085` | `LOINC:101706-0` |
| BCFV6 | observation_type | Measurement | `OBA:1000032` | `LOINC:110934-7` |
| BCFV8 | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| BMI | observation_type | Measurement | `OBA:2045455` | `LOINC:39156-5` |
| CHLORIDE | observation_type | Measurement | `OBA:VT0003018` | `LOINC:100745-9` |
| CHR | observation_type | Measurement | `OBA:VT0000180` | `LOINC:93801-9` |
| CREATININE | observation_type | Measurement | `OBA:2050096` | `LOINC:93736-7` |
| CSTA24 | observation_type | Measurement | `OMOP:42872742` | `LOINC:17126-4` |
| CreatinineUSpot | observation_type | Measurement | `OBA:VT0010540` | `LOINC:101681-5` |
| ECGB145 | observation_type | Measurement | `OMOP:4274406` | `LOINC:10001-6` |
| ECGB146 | observation_type | Measurement | `OMOP:4274406` | `LOINC:9905-1` |
| ECGB147 | observation_type | Measurement | `OMOP:4274406` | `LOINC:10003-2` |
| ECGB148 | observation_type | Measurement | `OMOP:4274406` | `LOINC:9903-6` |
| ECGB149 | observation_type | Measurement | `OMOP:4274406` | `LOINC:9999-4` |
| ECGB150 | observation_type | Measurement | `OMOP:4274406` | `LOINC:9998-6` |
| ECGB151 | observation_type | Measurement | `OMOP:4274406` | `LOINC:10004-0` |
| ECGB152 | observation_type | Measurement | `OMOP:4274406` | `LOINC:10005-7` |
| ECGB153 | observation_type | Measurement | `OMOP:4274406` | `LOINC:10006-5` |
| ECGB154 | observation_type | Measurement | `OMOP:4274406` | `LOINC:10007-3` |
| ECGB155 | observation_type | Measurement | `OMOP:4274406` | `LOINC:10008-1` |
| ECGB156 | observation_type | Measurement | `OMOP:4274406` | `LOINC:9912-7` |
| ECGB42 | observation_type | Measurement | `OBA:1001086` | `LOINC:8633-0` |
| ECGB46 | observation_type | Measurement | `OMOP:4273023` | `LOINC:8634-8` |
| ECHA62 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ECHA69 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| FPG | observation_type | Measurement | `OMOP:4156660` | `LOINC:76629-5` |
| FSTA5 | observation_type | Measurement | `OBA:VT0000188` | `LOINC:9935-8` |
| FSTA7 | observation_type | Measurement | `OBA:VT0002644` | `LOINC:51867-0` |
| FSTA8 | observation_type | Measurement | `OBA:VT0000184` | `LOINC:77032-1` |
| FSTA9 | observation_type | Measurement | `OBA:VT0000181` | `LOINC:51867-0` |
| Ferritin | observation_type | Measurement | `OBA:VT0010513` | `LOINC:14723-1` |
| GLUCOSE | observation_type | Measurement | `OBA:VT0000188` | `LOINC:105272-9` |
| GLUR | observation_type | Measurement | `OBA:VT0000188` | `LOINC:105272-9` |
| GLYHB | observation_type | Measurement | `OMOP:4184637` | `LOINC:718-7` |
| HDLC | observation_type | Measurement | `OBA:VT0000184` | `LOINC:96596-2` |
| HEMATOCRIT | observation_type | Measurement | `OBA:2045381` | `LOINC:4544-3` |
| HEMOGLOBIN | observation_type | Measurement | `OBA:2060175` | `LOINC:718-7` |
| HSCRP | observation_type | Measurement | `OMOP:4208414` | `LOINC:71426-1` |
| HbA1c | observation_type | Measurement | `OMOP:4184637` | `LOINC:718-7` |
| INSULIN | observation_type | Measurement | `OBA:2060174` | `LOINC:25091-0` |
| LDL1C | observation_type | Measurement | `OBA:VT0000181` | `LOINC:91105-7` |
| LDL2C | observation_type | Measurement | `OBA:VT0000181` | `LOINC:91106-5` |
| LDL3C | observation_type | Measurement | `OBA:VT0000181` | `LOINC:91107-3` |
| LDL4C | observation_type | Measurement | `OBA:VT0000181` | `LOINC:91108-1` |
| LDLC | observation_type | Measurement | `OBA:VT0000181` | `LOINC:74249-4` |
| LDLREAL | observation_type | Measurement | `OBA:VT0000181` | `LOINC:47213-4` |
| LYMPHS | observation_type | Measurement | `OMOP:37208690` | `LOINC:30418-8` |
| MCH | observation_type | Measurement | `OBA:2045301` | `LOINC:785-6` |
| MCHC | observation_type | Measurement | `OMOP:37393850` | `LOINC:786-4` |
| MCV | observation_type | Measurement | `OBA:0003460` | `LOINC:787-2` |
| MHXA7 | observation_type | Measurement | `OBA:2040171` | `LOINC:69382-0` |
| MHXB7 | observation_type | Measurement | `OBA:2040171` | `LOINC:21767-9` |
| MPV | observation_type | Measurement | `OBA:0003277` | `LOINC:104610-1` |
| PLATELET | observation_type | Measurement | `OMOP:4267147` | `LOINC:10412-5` |
| POTASSIUM | observation_type | Measurement | `OBA:VT0002668` | `LOINC:57379-0` |
| QRS | observation_type | Measurement | `OBA:1001086` | `LOINC:9952-3` |
| QT | observation_type | Measurement | `OMOP:4273023` | `LOINC:8634-8` |
| QTcBaz | observation_type | Measurement | `OMOP:4273023` | `LOINC:76635-2` |
| QTcFram | observation_type | Measurement | `OMOP:4273023` | `LOINC:66336-9` |
| QTcFrid | observation_type | Measurement | `OMOP:4273023` | `LOINC:76634-5` |
| QTcHod | observation_type | Measurement | `OMOP:4273023` | `LOINC:86930-5` |
| RED_CELL_COUNT | observation_type | Measurement | `OBA:VT0001586` | `LOINC:106763-6` |
| SBPA8 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| SBPB10 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| SBPC10 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| SBPC15 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| SBPC18 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| SCrCC | observation_type | Measurement | `OBA:2050096` | `LOINC:60655-8` |
| SODIUM | observation_type | Measurement | `OBA:VT0001776` | `LOINC:12907-2` |
| TC | observation_type | Measurement | `OBA:VT0000180` | `LOINC:110258-1` |
| TG | observation_type | Measurement | `OBA:VT0002644` | `LOINC:105518-5` |
| TOBA1 | observation_type | Measurement | `OMOP:4282779` | `LOINC:42634-6` |
| TOBA3 | observation_type | Measurement | `OMOP:4282779` | `LOINC:88177-1` |
| UMALCR | observation_type | Measurement | `OMOP:4154347` | `LOINC:34535-5` |
| UMALI | observation_type | Measurement | `OBA:VT0002871` | `LOINC:100158-5` |
| URINE_ALBUMIN | observation_type | Measurement | `OBA:VT0002871` | `LOINC:43671-7` |
| UR_ALBUMIN_24HR | observation_type | Measurement | `OBA:VT0002871` | `LOINC:53530-2` |
| UR_CREATININE | observation_type | Measurement | `OBA:VT0010540` | `LOINC:80334-6` |
| UR_TOTAL_VOLUME | observation_type | Measurement | `OBA:VT0002871` | `LOINC:9197-5` |
| WBC | observation_type | Measurement | `OBA:VT0000217` | `LOINC:6690-2` |
| age | observation_type | Measurement | `OMOP:35609491` | `LOINC:30525-0` |
| alcw | observation_type | Measurement | `OMOP:35609491` | `LOINC:41959-8` |
| antv1 | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| antv2 | observation_type | Measurement | `OBA:VT0001259` | `LOINC:8302-2` |
| asn0027_BNP | observation_type | Measurement | `OBA:2045303` | `LOINC:42637-9` |
| asn0035_A1C | observation_type | Measurement | `OMOP:4184637` | `LOINC:718-7` |
| asn0035_HDL | observation_type | Measurement | `OBA:VT0000184` | `LOINC:76629-5` |
| asn0035_LDL | observation_type | Measurement | `OBA:VT0000181` | `LOINC:76629-5` |
| asn0035_TCH | observation_type | Measurement | `OBA:VT0000180` | `LOINC:49541-6` |
| asn0035_TRG | observation_type | Measurement | `OBA:VT0002644` | `LOINC:76629-5` |
| asn0035_age_eyevisit | observation_type | Measurement | `OBA:VT0000184` | `LOINC:30525-0` |
| bun | observation_type | Measurement | `OBA:VT0005265` | `LOINC:12963-5` |
| chr | observation_type | Measurement | `OBA:VT0000180` | `LOINC:93801-9` |
| currentSmoker | observation_type | Measurement | `OMOP:4282779` | `LOINC:104907-1` |
| cystatinC | observation_type | Measurement | `OBA:2052375` | `LOINC:82232-0` |
| darkgrnVeg | observation_type | Measurement | `OMOP:4042886` | `LOINC:46007-1` |
| depression | observation_type | Measurement | `OMOP:36303297` | `LOINC:100279-9` |
| eGFRckdepi | observation_type | Measurement | `OMOP:37208635` | `LOINC:55764-5` |
| eGFRmdrd | observation_type | Measurement | `OMOP:37208635` | `LOINC:21666-3` |
| eSelectin | observation_type | Measurement | `OBA:2052778` | `LOINC:28071-9` |
| ecgHR | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ecga170 | observation_type | Measurement | `OMOP:4274406` | `LOINC:24893-0` |
| everSmoker | observation_type | Measurement | `OMOP:4282779` | `LOINC:104907-1` |
| fmlyinc | observation_type | Measurement | `OMOP:4076114` | `LOINC:80390-8` |
| glur | observation_type | Measurement | `OBA:VT0000188` | `LOINC:105272-9` |
| glyhb | observation_type | Measurement | `OMOP:4184637` | `LOINC:718-7` |
| hdl | observation_type | Measurement | `OBA:VT0000184` | `LOINC:76629-5` |
| hdlc | observation_type | Measurement | `OBA:VT0000184` | `LOINC:96596-2` |
| height | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| hip | observation_type | Measurement | `OBA:1000032` | `LOINC:62409-8` |
| hsCRP | observation_type | Measurement | `OMOP:4208414` | `LOINC:71426-1` |
| lca_av45 | observation_type | Measurement | `OBA:2050108` | `LOINC:72070-6` |
| lcl_av45 | observation_type | Measurement | `OBA:2050108` | `LOINC:65640-5` |
| lcp_av45 | observation_type | Measurement | `OBA:2050108` | `LOINC:72083-9` |
| ldl | observation_type | Measurement | `OBA:VT0000181` | `LOINC:76629-5` |
| ldlc | observation_type | Measurement | `OBA:VT0000181` | `LOINC:14155-6` |
| pSelectin | observation_type | Measurement | `OBA:2052701` | `LOINC:32746-0` |
| rca_av45 | observation_type | Measurement | `OBA:2050108` | `LOINC:67256-8` |
| rcl_av45 | observation_type | Measurement | `OBA:2050108` | `LOINC:67256-8` |
| rcp_av45 | observation_type | Measurement | `OBA:2050108` | `LOINC:67256-8` |
| totchol | observation_type | Measurement | `OBA:VT0000180` | `LOINC:49541-6` |
| trigs | observation_type | Measurement | `OBA:VT0002644` | `LOINC:76629-5` |
| waist | observation_type | Measurement | `OBA:1001085` | `LOINC:8280-0` |
| weight | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| MHXA52C | procedure_concept | Procedure | `OMOP:1242799` | `OMOP:4007353` |
| MHXA52E1 | procedure_concept | Procedure | `OMOP:4178405` | `OMOP:4007353` |

### Unverified Misalignments (38 — no YAML confirmation)

| Variable | Slot | Entity Type | CSV CURIE | Agent Suggestion |
| :---- | :---- | :---- | :---- | :---- |
| FEV1 | observations | Measurement | `OMOP:4176265` | `LOINC:65819-5` |
| FVC | observations | Measurement | `OMOP:4176265` | `LOINC:20152-5` |
| SBPA13 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPA14 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPA16 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPA17 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPA19 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPA20 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPB16 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPB17 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPB19 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPB20 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPB22 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPB23 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPB25 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPB26 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPB27 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPB28 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPB29 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPB30 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPC13 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPC14 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPC16 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPC17 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPC19 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPC20 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| age | observations | Measurement | `OMOP:4152194` | `LOINC:30525-0` |
| dbp | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| pula17 | observations | Measurement | `OMOP:3011505` | `LOINC:20150-9` |
| pula18 | observations | Measurement | `OMOP:3011505` | `LOINC:20150-9` |
| pula22 | observations | Measurement | `OMOP:3011505` | `LOINC:20150-9` |
| pula27 | observations | Measurement | `OMOP:3011505` | `LOINC:20150-9` |
| pula28 | observations | Measurement | `OMOP:3011505` | `LOINC:20150-9` |
| pula32 | observations | Measurement | `OMOP:3011505` | `LOINC:20150-9` |
| pula37 | observations | Measurement | `OMOP:3011505` | `LOINC:20150-9` |
| pula38 | observations | Measurement | `OMOP:3011505` | `LOINC:20150-9` |
| pula42 | observations | Measurement | `OMOP:3011505` | `LOINC:20150-9` |
| sbp | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |

## Vocab/Slot Validation

Agent suggestions suppressed as vocabulary/slot mismatches (evaluated but not surfaced as findings): **54**

| Slot | Invalid vocab proposed | Suppressed count | Rule |
| :---- | :---- | ----: | :---- |
| `condition_concept` | LOINC, OMOP, SNOMED | 3 | Valid: HP, MONDO |
| `observation_type` | LOINC | 51 | Valid: OBA, OMOP |
| **Total** | | **54** | |

_These are not errors — they confirm the existing CURIEs are correct for their slots. The agent proposed codes from a vocabulary the bdchm slot is not typed for (e.g. OMOP in a MONDO-typed slot, LOINC in an OBA-typed slot). See `_SLOT_VOCAB_RULES` in `generate_semantic_review.py` for the full rule definitions._

## Error Cases Requiring Fix

### Missing Agent Suggestions — 46 variable-slot pair(s)

These substantive variables received no suggestion from any agent.
Investigate whether a suitable ontology term exists or the slot routing needs updating.

| Variable | Slot | Entity Type | Description |
| :---- | :---- | :---- | :---- |
| umalcr | observation_type | Measurement | Umalcr: Ratio of Albumin(mg) to creatinine(g) - mg/g Cr |
| umali | observation_type | Measurement | Umali: Albumin, Urine - mg/L |
| umali_cresult | observation_type | Measurement | Umali_cresult: Character Results for Albumin (mg/L) |
| SCrIDMS | observation_type | Measurement | IDMS Traceable Serum Creatinine (mg/dL) |
| creatr | observation_type | Measurement | Creatr: Creatinine - mg/dL |
| CRDUR | observation_type | Measurement | Crdur: Creatinine, Urine - mg/dL [Visit 6] |
| crdur | observation_type | Measurement | Crdur: Creatinine, Urine - mg/dL |
| CRPHS2 | observation_type | Measurement | Crphs2: C-Reactive Protein, High Sensitivity - mg/L [Visit 6 |
| crphs2 | observation_type | Measurement | Crphs2: C-Reactive Protein, High Sensitivity - mg/L |
| crphs2_cresult | observation_type | Measurement | Crphs2_cresult: Character Results for C-Reactive Protein (mg |
| PDSA28A | observation_type | Measurement | Q28a.  What was total combined family income in past year? [ |
| PDSB27B | observation_type | Measurement | Q27b.  You may not be able to give me an exact range for you |
| PDSB27C | observation_type | Measurement | Q27c.  You may not be able to give me an exact range for you |
| PDSB27D | observation_type | Measurement | Q27d. You may not be able to give me an exact range for your |
| PDSB27E | observation_type | Measurement | Q27e.  You may not be able to give me an exact range for you |
| PDSB27F | observation_type | Measurement | Q27f.  You may not be able to give me an exact range for you |
| PDSB27G | observation_type | Measurement | Q27g.  You may not be able to give me an exact range for you |
| insr | observation_type | Measurement | Insr: Insulin - pmol/L |
| insr_cresult | observation_type | Measurement | Insr_cresult: Character Results for Insulin (pmol/L) |
| ecga171 | observation_type | Measurement | PRDURII - PR Duration in lead II [Visit 1] |
| ecga172 | observation_type | Measurement | PRDURIII - PR Duration in lead III [Visit 1] |
| ecga173 | observation_type | Measurement | PRDURAVR - PR Duration in lead AVR [Visit 1] |
| ecga174 | observation_type | Measurement | PRDURAVL - PR Duration in lead AVL [Visit 1] |
| ecga175 | observation_type | Measurement | PRDURAVF - PR Duration in lead AVF [Visit 1] |
| ecga176 | observation_type | Measurement | PRDURV1 - PR Duration in lead V1 [Visit 1] |
| ecga177 | observation_type | Measurement | PRDURV2 - PR Duration in lead V2 [Visit 1] |
| ecga178 | observation_type | Measurement | PRDURV3 - PR Duration in lead V3 [Visit 1] |
| ecga179 | observation_type | Measurement | PRDURV4 - PR Duration in lead V4 [Visit 1] |
| ecga180 | observation_type | Measurement | PRDURV5 - PR Duration in lead V5 [Visit 1] |
| ecga181 | observation_type | Measurement | PRDURV6 - PR Duration in lead V6 [Visit 1] |
| ecga43 | observation_type | Measurement | QRSDUR - QRS Duration [Visit 1] |
| ecga302 | observation_type | Measurement | QRSDI - QRS Duration in lead I [Visit 1] |
| ecga303 | observation_type | Measurement | QRSDII - QRS Duration in lead II [Visit 1] |
| ecga304 | observation_type | Measurement | QRSDIII - QRS Duration in lead III [Visit 1] |
| ecga305 | observation_type | Measurement | QRSDAVR - QRS Duration in lead AVR [Visit 1] |
| ecga306 | observation_type | Measurement | QRSDAVL - QRS Duration in lead AVL [Visit 1] |
| ecga307 | observation_type | Measurement | QRSDAVF - QRS Duration in lead AVF [Visit 1] |
| ecga308 | observation_type | Measurement | QRSDV1 - QRS Duration in lead V1 [Visit 1] |
| ecga309 | observation_type | Measurement | QRSDV2 - QRS Duration in lead V2 [Visit 1] |
| ecga310 | observation_type | Measurement | QRSDV3 - QRS Duration in lead V3 [Visit 1] |
| ecga311 | observation_type | Measurement | QRSDV4 - QRS Duration in lead V4 [Visit 1] |
| ecga312 | observation_type | Measurement | QRSDV5 - QRS Duration in lead V5 [Visit 1] |
| ecga313 | observation_type | Measurement | QRSDV6 - QRS Duration in lead V6 [Visit 1] |
| ecga47 | observation_type | Measurement | QTDUR - QT Duration [Visit 1] |
| TRR | observation_type | Measurement | Trr: triglyceride - mg/dL [Visit 1] |
| trr | observation_type | Measurement | Trr: Triglyceride - mg/dL |
