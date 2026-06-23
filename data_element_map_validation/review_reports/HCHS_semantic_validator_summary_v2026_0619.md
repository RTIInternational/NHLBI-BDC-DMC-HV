# HCHS Semantic Validator Summary v2026-06-19

**Generated:** 2026-06-19
**Mapreview CSV:** `HCHS_curie_mapreview.csv`
**Review MD:** `HCHS_Semantic_Review_Final_Reviewer-2026-05-31.md`

---

## Overview

| Metric | Count |
| :---- | ----: |
| Total rows in mapreview CSV | 221 |
| Admin variables skipped | 1 |
| Substantive variables reviewed | 220 |
| Unique CURIEs validated | 88 |
| Unique YAML files referenced | 74 |
| Final Confirmed Findings rows | 54 |
| Anne Review Required rows | 6 |

## YAML Spot-Check

| Result | Count |
| :---- | ----: |
| Matches (✓) | 156 |
| Mismatches (⚠) | 10 |
| Not checked (admin / no YAML) | 54 |

**10 mismatch(es) require correction:**

| Variable | YAML File | CSV CURIE | YAML CURIE |
| :---- | :---- | :---- | :---- |
| AGE | cig_smok.yaml | `OMOP:40766945` | `OMOP:45883537` |
| AGE | cig_smok.yaml | `OMOP:45883458` | `OMOP:45883537` |
| TBEA1 | cig_smok.yaml | `OMOP:40766945` | `OMOP:45883537` |
| TBEA1 | cig_smok.yaml | `OMOP:45883458` | `OMOP:45883537` |
| TBEA3 | cig_smok.yaml | `OMOP:40766945` | `OMOP:45883537` |
| TBEA3 | cig_smok.yaml | `OMOP:45883458` | `OMOP:45883537` |
| MED_ANTIHYPERT_ACEI | tak_aceinhib.yaml | `ATC:C09A` | `ATC:C02` |
| MED_ANTIHYPERT_AT2RAS | tak_aceinhib.yaml | `ATC:C09A` | `ATC:C02` |
| DILTIAZEM | tak_calchanblk.yaml | `RxCUI:3443` | `ATC:C08` |
| VERAPAMIL | tak_calchanblk.yaml | `RxCUI:11170` | `ATC:C08` |

## Agent Coverage by Entity Type

| Entity Type | Unique vars | MONDO | HPO | OMOP/LOINC | No suggestion |
| :---- | ----: | ----: | ----: | ----: | ----: |
| Condition | 2 | 2 | 0 | 0 | 0 |
| DrugRoute | 1 | 0 | 0 | 0 | 1 |
| Measurement | 68 | 0 | 0 | 67 | 1 |
| ValueEnum | 3 | 0 | 0 | 0 | 3 |
| **Total** | **74** | | | | **5** |

**Coverage: 69/74 unique variable-slot pairs have at least one agent suggestion (93%).**

## Agent vs CSV CURIE Alignment

Agent suggestions differ from the current CSV CURIE in **69** variable-slot pair(s).

### Potential Improvements (59 — YAML confirms CSV, agent suggests different)

These cases have a YAML-confirmed CSV CURIE but the agent suggests a different concept.
Review whether the agent suggestion is more specific or accurate.

| Variable | Slot | Entity Type | CSV / YAML CURIE | Agent Suggestion |
| :---- | :---- | :---- | :---- | :---- |
| ASTHMA_CURR | condition_concept | Condition | `MONDO:0004979` | `MONDO:0005959` |
| MHEA16 | condition_concept | Condition | `MONDO:0005015` | `MONDO:0006606` |
| AGE | observation_type | Measurement | `OMOP:4154347` | `LOINC:30525-0` |
| AGE | observation_type | Measurement | `OMOP:4282779` | `LOINC:30525-0` |
| ANTA10A | observation_type | Measurement | `OBA:1001085` | `LOINC:56114-2` |
| ANTA10B | observation_type | Measurement | `OBA:1000032` | `LOINC:66513-3` |
| ANTA4 | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| BMI | observation_type | Measurement | `OBA:2045455` | `LOINC:39156-5` |
| CESD10 | observation_type | Measurement | `OMOP:36303297` | `LOINC:28362-2` |
| ECGA10 | observation_type | Measurement | `OBA:1001086` | `LOINC:8633-0` |
| ECGA11 | observation_type | Measurement | `OMOP:4273023` | `LOINC:8636-3` |
| ECGA12 | observation_type | Measurement | `OMOP:4273023` | `LOINC:8636-3` |
| ECGA277 | observation_type | Measurement | `OMOP:45772840` | `LOINC:74041-5` |
| ECGA7 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ECGA8 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ECGA9 | observation_type | Measurement | `OMOP:4274406` | `LOINC:81269-3` |
| EGFRCKD | observation_type | Measurement | `OMOP:37208635` | `LOINC:55764-5` |
| EGFRMDRD | observation_type | Measurement | `OMOP:37208635` | `LOINC:21666-3` |
| HEIGHT | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| INSULIN_FAST | observation_type | Measurement | `OBA:2060174` | `LOINC:95110-3` |
| LABA1 | observation_type | Measurement | `OBA:VT0000217` | `LOINC:67750-0` |
| LABA10 | observation_type | Measurement | `OMOP:37208698` | `LOINC:26499-4` |
| LABA101 | observation_type | Measurement | `OBA:2052375` | `LOINC:33863-2` |
| LABA103 | observation_type | Measurement | `OBA:VT0010513` | `LOINC:14723-1` |
| LABA11 | observation_type | Measurement | `OMOP:37208690` | `LOINC:26474-7` |
| LABA2 | observation_type | Measurement | `OBA:VT0001586` | `LOINC:106763-6` |
| LABA23 | observation_type | Measurement | `OBA:VT0000222` | `LOINC:26499-4` |
| LABA24 | observation_type | Measurement | `OBA:VT0000717` | `LOINC:26474-7` |
| LABA25 | observation_type | Measurement | `OBA:VT0000223` | `LOINC:26484-6` |
| LABA26 | observation_type | Measurement | `OBA:VT0002602` | `LOINC:26449-9` |
| LABA27 | observation_type | Measurement | `OBA:VT0002607` | `LOINC:26444-0` |
| LABA3 | observation_type | Measurement | `OBA:2060175` | `LOINC:718-7` |
| LABA4 | observation_type | Measurement | `OBA:2045381` | `LOINC:4544-3` |
| LABA5 | observation_type | Measurement | `OBA:0003460` | `LOINC:787-2` |
| LABA6 | observation_type | Measurement | `OBA:2045301` | `LOINC:785-6` |
| LABA66 | observation_type | Measurement | `OBA:VT0000180` | `LOINC:110258-1` |
| LABA67 | observation_type | Measurement | `OBA:VT0002644` | `LOINC:30570-6` |
| LABA68 | observation_type | Measurement | `OBA:VT0000184` | `LOINC:96596-2` |
| LABA69 | observation_type | Measurement | `OBA:VT0000181` | `LOINC:14155-6` |
| LABA7 | observation_type | Measurement | `OMOP:37393850` | `LOINC:786-4` |
| LABA70 | observation_type | Measurement | `OMOP:4156660` | `LOINC:105272-9` |
| LABA72 | observation_type | Measurement | `OMOP:4184637` | `LOINC:718-7` |
| LABA76 | observation_type | Measurement | `OBA:2050096` | `LOINC:93736-7` |
| LABA79 | observation_type | Measurement | `OBA:VT0010540` | `LOINC:34535-5` |
| LABA8 | observation_type | Measurement | `OMOP:37397924` | `LOINC:21000-5` |
| LABA80 | observation_type | Measurement | `OBA:VT0002871` | `LOINC:34535-5` |
| LABA81 | observation_type | Measurement | `OMOP:4154347` | `LOINC:32294-1` |
| LABA9 | observation_type | Measurement | `OMOP:4267147` | `LOINC:777-3` |
| LABA91 | observation_type | Measurement | `OMOP:4208414` | `LOINC:71426-1` |
| SLPA54 | observation_type | Measurement | `OMOP:37396400` | `LOINC:69990-0` |
| SLPA92 | observation_type | Measurement | `OBA:2045443` | `LOINC:59408-5` |
| SLPDUR | observation_type | Measurement | `OBA:2040171` | `LOINC:96917-0` |
| TBEA1 | observation_type | Measurement | `OMOP:4282779` | `LOINC:63580-5` |
| TBEA3 | observation_type | Measurement | `OMOP:4282779` | `LOINC:8684-3` |
| WAIST_HIP | observation_type | Measurement | `OMOP:4087501` | `LOINC:56117-5` |
| WHEA2A_CM | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| WHEA3A_KG | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| WHEA4A_KG | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| WHEA5A_KG | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |

### Unverified Misalignments (10 — no YAML confirmation)

| Variable | Slot | Entity Type | CSV CURIE | Agent Suggestion |
| :---- | :---- | :---- | :---- | :---- |
| AGE | observations | Measurement | `OMOP:4152194` | `LOINC:30525-0` |
| FEV1_FVC_RATIO | observations | Measurement | `OMOP:3002094` | `LOINC:20157-4` |
| POSTBD_PREBD_DIFF | observations | Measurement | `OMOP:44813037` | `LOINC:20150-9` |
| PRBA25 | observations | Measurement | `OMOP:3002094` | `LOINC:20152-5` |
| PRBA29 | observations | Measurement | `OMOP:3002094` | `LOINC:20150-9` |
| PRBA36 | observations | Measurement | `OMOP:3002094` | `LOINC:20152-5` |
| PRBA37 | observations | Measurement | `OMOP:3002094` | `LOINC:20150-9` |
| PRBA39 | observations | Measurement | `OMOP:3002094` | `LOINC:20150-9` |
| SBPA5 | observations | Measurement | `OMOP:4152194` | `LOINC:96608-5` |
| SBPA6 | observations | Measurement | `OMOP:4152194` | `LOINC:96609-3` |

## Vocab/Slot Validation

Agent suggestions suppressed as vocabulary/slot mismatches (evaluated but not surfaced as findings): **47**

| Slot | Invalid vocab proposed | Suppressed count | Rule |
| :---- | :---- | ----: | :---- |
| `observation_type` | LOINC | 47 | Valid: OBA, OMOP |
| **Total** | | **47** | |

_These are not errors — they confirm the existing CURIEs are correct for their slots. The agent proposed codes from a vocabulary the bdchm slot is not typed for (e.g. OMOP in a MONDO-typed slot, LOINC in an OBA-typed slot). See `_SLOT_VOCAB_RULES` in `generate_semantic_review.py` for the full rule definitions._

## Error Cases Requiring Fix

### YAML Mismatches — 10 must be corrected
See the YAML Spot-Check section above.

### Missing Agent Suggestions — 2 variable-slot pair(s)

These substantive variables received no suggestion from any agent.
Investigate whether a suitable ontology term exists or the slot routing needs updating.

| Variable | Slot | Entity Type | Description |
| :---- | :---- | :---- | :---- |
| INCOME | observation_type | Measurement | Yearly Household Income (ECEA3 and ECEA4) |
| MED_BB | route_concept | DrugRoute | Beta Blockers |
