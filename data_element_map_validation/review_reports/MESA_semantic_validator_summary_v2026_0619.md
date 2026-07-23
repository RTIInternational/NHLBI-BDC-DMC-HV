# MESA Semantic Validator Summary v2026-06-19

**Generated:** 2026-06-19
**Mapreview CSV:** `MESA_curie_mapreview.csv`
**Review MD:** `MESA_Semantic_Review_Final_Reviewer-2026-05-31.md`

---

## Overview

| Metric | Count |
| :---- | ----: |
| Total rows in mapreview CSV | 1807 |
| Admin variables skipped | 0 |
| Substantive variables reviewed | 1807 |
| Unique CURIEs validated | 164 |
| Unique YAML files referenced | 119 |
| Final Confirmed Findings rows | 71 |
| Anne Review Required rows | 16 |

## YAML Spot-Check

| Result | Count |
| :---- | ----: |
| Matches (✓) | 1405 |
| Mismatches (⚠) | 111 |
| Not checked (admin / no YAML) | 291 |

**111 mismatch(es) require correction:**

| Variable | YAML File | CSV CURIE | YAML CURIE |
| :---- | :---- | :---- | :---- |
| afibcd | afib.yaml | `MONDO:0005310` | `[6 mappings]` |
| age3c | egfr.yaml | `OMOP:4213477` | `[13 mappings]` |
| egfr3c | egfr.yaml | `OMOP:4213477` | `[13 mappings]` |
| age1c | hdl.yaml | `OMOP:4041720` | `[5 mappings]` |
| hdl1 | hdl.yaml | `OMOP:4041720` | `[5 mappings]` |
| lastdrk1 | hdl.yaml | `OMOP:4041720` | `[5 mappings]` |
| age1c | hdl.yaml | `OMOP:4041720` | `[5 mappings]` |
| hdl1 | hdl.yaml | `OMOP:4041720` | `[5 mappings]` |
| lastdrk1 | hdl.yaml | `OMOP:4041720` | `[5 mappings]` |
| nhdlc31c | hdl.yaml | `OMOP:4041720` | `[5 mappings]` |
| agefc | hdl.yaml | `OMOP:4041720` | `[5 mappings]` |
| hdlf | hdl.yaml | `OMOP:4041720` | `[5 mappings]` |
| lastdrkf | hdl.yaml | `OMOP:4041720` | `[5 mappings]` |
| age1c | ldl.yaml | `OMOP:4041721` | `[9 mappings]` |
| ldl1 | ldl.yaml | `OMOP:4041721` | `[9 mappings]` |
| lastdrk1 | ldl.yaml | `OMOP:4041721` | `[9 mappings]` |
| age1c | ldl.yaml | `OMOP:4041721` | `[9 mappings]` |
| ldl1 | ldl.yaml | `OMOP:4041721` | `[9 mappings]` |
| lastdrk1 | ldl.yaml | `OMOP:4041721` | `[9 mappings]` |
| bphxage1 | tak_alphablk.yaml | `ATC:C03` | `VANDF:CV150` |
| alphad1c | tak_alphablk.yaml | `ATC:C03` | `VANDF:CV150` |
| bphxage1 | tak_alphablk.yaml | `ATC:C03` | `VANDF:CV150` |
| alphad1c | tak_alphablk.yaml | `ATC:C03` | `VANDF:CV150` |
| alphad2c | tak_alphablk.yaml | `ATC:C03` | `VANDF:CV150` |
| alphad3c | tak_alphablk.yaml | `ATC:C03` | `VANDF:CV150` |
| alphad4c | tak_alphablk.yaml | `ATC:C03` | `VANDF:CV150` |
| bphxagef | tak_alphablk.yaml | `ATC:C03` | `VANDF:CV150` |
| alphadfc | tak_alphablk.yaml | `ATC:C03` | `VANDF:CV150` |
| alphad5c | tak_alphablk.yaml | `ATC:C03` | `VANDF:CV150` |
| alphad5c | tak_alphablk.yaml | `ATC:C03` | `VANDF:CV150` |
| bphxage1 | tak_angiorecepblk.yaml | `ATC:C09DA` | `ATC:C09C` |
| a2ad1c | tak_angiorecepblk.yaml | `ATC:C09DA` | `ATC:C09C` |
| bphxage1 | tak_angiorecepblk.yaml | `ATC:C09DA` | `ATC:C09C` |
| a2a1c | tak_angiorecepblk.yaml | `ATC:C09DA` | `ATC:C09C` |
| a2ad2c | tak_angiorecepblk.yaml | `ATC:C09DA` | `ATC:C09C` |
| a2ad3c | tak_angiorecepblk.yaml | `ATC:C09DA` | `ATC:C09C` |
| a2ad4c | tak_angiorecepblk.yaml | `ATC:C09DA` | `ATC:C09C` |
| bphxagef | tak_angiorecepblk.yaml | `ATC:C09DA` | `ATC:C09C` |
| a2adfc | tak_angiorecepblk.yaml | `ATC:C09DA` | `ATC:C09C` |
| a2ad5c | tak_angiorecepblk.yaml | `ATC:C09DA` | `ATC:C09C` |
| a2ad5c | tak_angiorecepblk.yaml | `ATC:C09DA` | `ATC:C09C` |
| diur1c | tak_diuret.yaml | `ATC:C03` | `NDFRT:N0000175419` |
| diur1c | tak_diuret.yaml | `ATC:C03` | `NDFRT:N0000175419` |
| diur2c | tak_diuret.yaml | `ATC:C03` | `NDFRT:N0000175419` |
| diur3c | tak_diuret.yaml | `ATC:C03` | `NDFRT:N0000175419` |
| diur4c | tak_diuret.yaml | `ATC:C03` | `NDFRT:N0000175419` |
| diurfc | tak_diuret.yaml | `ATC:C03` | `NDFRT:N0000175419` |
| diur5c | tak_diuret.yaml | `ATC:C03` | `NDFRT:N0000175419` |
| diur5c | tak_diuret.yaml | `ATC:C03` | `NDFRT:N0000175419` |
| dbage1 | tak_insulin.yaml | `MeSH:D007328` | `VANDF:HS500` |
| insln1c | tak_insulin.yaml | `MeSH:D007328` | `VANDF:HS500` |
| dbage1 | tak_insulin.yaml | `MeSH:D007328` | `VANDF:HS500` |
| insln1c | tak_insulin.yaml | `MeSH:D007328` | `VANDF:HS500` |
| insln2c | tak_insulin.yaml | `MeSH:D007328` | `VANDF:HS500` |
| insln3c | tak_insulin.yaml | `MeSH:D007328` | `VANDF:HS500` |
| insln4c | tak_insulin.yaml | `MeSH:D007328` | `VANDF:HS500` |
| insln5c | tak_insulin.yaml | `MeSH:D007328` | `VANDF:HS500` |
| insln5c | tak_insulin.yaml | `MeSH:D007328` | `VANDF:HS500` |
| bphxage1 | tak_vasodil.yaml | `ATC:C02L` | `ATC:C01D` |
| bphxage1 | tak_vasodil.yaml | `ATC:C04` | `ATC:C01D` |
| pvdl1c | tak_vasodil.yaml | `ATC:C04` | `ATC:C01D` |
| vasod1c | tak_vasodil.yaml | `ATC:C02L` | `ATC:C01D` |
| bphxage1 | tak_vasodil.yaml | `ATC:C02L` | `ATC:C01D` |
| bphxage1 | tak_vasodil.yaml | `ATC:C04` | `ATC:C01D` |
| pvdl1c | tak_vasodil.yaml | `ATC:C04` | `ATC:C01D` |
| vasod1c | tak_vasodil.yaml | `ATC:C02L` | `ATC:C01D` |
| pvdl2c | tak_vasodil.yaml | `ATC:C04` | `ATC:C01D` |
| vasod2c | tak_vasodil.yaml | `ATC:C02L` | `ATC:C01D` |
| pvdl3c | tak_vasodil.yaml | `ATC:C04` | `ATC:C01D` |
| vasod3c | tak_vasodil.yaml | `ATC:C02L` | `ATC:C01D` |
| pvdl4c | tak_vasodil.yaml | `ATC:C04` | `ATC:C01D` |
| vasod4c | tak_vasodil.yaml | `ATC:C02L` | `ATC:C01D` |
| bphxagef | tak_vasodil.yaml | `ATC:C02L` | `ATC:C01D` |
| bphxagef | tak_vasodil.yaml | `ATC:C04` | `ATC:C01D` |
| pvdlfc | tak_vasodil.yaml | `ATC:C04` | `ATC:C01D` |
| vasodfc | tak_vasodil.yaml | `ATC:C02L` | `ATC:C01D` |
| pvdl5c | tak_vasodil.yaml | `ATC:C04` | `ATC:C01D` |
| vasod5c | tak_vasodil.yaml | `ATC:C02L` | `ATC:C01D` |
| pvdl5c | tak_vasodil.yaml | `ATC:C04` | `ATC:C01D` |
| vasod5c | tak_vasodil.yaml | `ATC:C02L` | `ATC:C01D` |
| cholage1 | taking_non_statin_medication.yaml | `ATC:C10AB` | `ATC:C10AC` |
| cholage1 | taking_non_statin_medication.yaml | `ATC:C10AD` | `ATC:C10AC` |
| fibr1c | taking_non_statin_medication.yaml | `ATC:C10AB` | `ATC:C10AC` |
| niac1c | taking_non_statin_medication.yaml | `ATC:C10AD` | `ATC:C10AC` |
| cholage1 | taking_non_statin_medication.yaml | `ATC:C10AB` | `ATC:C10AC` |
| cholage1 | taking_non_statin_medication.yaml | `ATC:C10AD` | `ATC:C10AC` |
| fibr1c | taking_non_statin_medication.yaml | `ATC:C10AB` | `ATC:C10AC` |
| niac1c | taking_non_statin_medication.yaml | `ATC:C10AD` | `ATC:C10AC` |
| fibr2c | taking_non_statin_medication.yaml | `ATC:C10AB` | `ATC:C10AC` |
| niac2c | taking_non_statin_medication.yaml | `ATC:C10AD` | `ATC:C10AC` |
| fibr3c | taking_non_statin_medication.yaml | `ATC:C10AB` | `ATC:C10AC` |
| niac3c | taking_non_statin_medication.yaml | `ATC:C10AD` | `ATC:C10AC` |
| fibr4c | taking_non_statin_medication.yaml | `ATC:C10AB` | `ATC:C10AC` |
| niac4c | taking_non_statin_medication.yaml | `ATC:C10AD` | `ATC:C10AC` |
| cholagef | taking_non_statin_medication.yaml | `ATC:C10AB` | `ATC:C10AC` |
| cholagef | taking_non_statin_medication.yaml | `ATC:C10AD` | `ATC:C10AC` |
| fibrfc | taking_non_statin_medication.yaml | `ATC:C10AB` | `ATC:C10AC` |
| niacfc | taking_non_statin_medication.yaml | `ATC:C10AD` | `ATC:C10AC` |
| fibr5c | taking_non_statin_medication.yaml | `ATC:C10AB` | `ATC:C10AC` |
| niac5c | taking_non_statin_medication.yaml | `ATC:C10AD` | `ATC:C10AC` |
| fibr5c | taking_non_statin_medication.yaml | `ATC:C10AB` | `ATC:C10AC` |
| niac5c | taking_non_statin_medication.yaml | `ATC:C10AD` | `ATC:C10AC` |
| age1c | triglyc_bld.yaml | `OMOP:4041722` | `[5 mappings]` |
| trig1 | triglyc_bld.yaml | `OMOP:4041722` | `[5 mappings]` |
| lastdrk1 | triglyc_bld.yaml | `OMOP:4041722` | `[5 mappings]` |
| age1c | triglyc_bld.yaml | `OMOP:4041722` | `[5 mappings]` |
| trig1 | triglyc_bld.yaml | `OMOP:4041722` | `[5 mappings]` |
| lastdrk1 | triglyc_bld.yaml | `OMOP:4041722` | `[5 mappings]` |
| agefc | triglyc_bld.yaml | `OMOP:4041722` | `[5 mappings]` |
| trigf | triglyc_bld.yaml | `OMOP:4041722` | `[5 mappings]` |
| lastdrkf | triglyc_bld.yaml | `OMOP:4041722` | `[5 mappings]` |

## Agent Coverage by Entity Type

| Entity Type | Unique vars | MONDO | HPO | OMOP/LOINC | No suggestion |
| :---- | ----: | ----: | ----: | ----: | ----: |
| Condition | 25 | 25 | 0 | 0 | 0 |
| Condition (HPO) | 4 | 0 | 4 | 0 | 0 |
| Measurement | 414 | 0 | 0 | 405 | 9 |
| Person | 3 | 0 | 0 | 0 | 3 |
| ValueEnum | 19 | 0 | 0 | 0 | 19 |
| **Total** | **465** | | | | **31** |

**Coverage: 434/465 unique variable-slot pairs have at least one agent suggestion (93%).**

## Agent vs CSV CURIE Alignment

Agent suggestions differ from the current CSV CURIE in **420** variable-slot pair(s).

### Potential Improvements (391 — YAML confirms CSV, agent suggests different)

These cases have a YAML-confirmed CSV CURIE but the agent suggests a different concept.
Review whether the agent suggestion is more specific or accurate.

| Variable | Slot | Entity Type | CSV / YAML CURIE | Agent Suggestion |
| :---- | :---- | :---- | :---- | :---- |
| ang | condition_concept | Condition | `HP:0001681` | `MONDO:0006805` |
| anginaf | condition_concept | Condition | `HP:0001681` | `MONDO:0006576` |
| chf | condition_concept | Condition | `MONDO:0005252` | `MONDO:0005009` |
| highbpf | condition_concept | Condition | `HP:0000822` | `MONDO:0005044` |
| lmorph1 | condition_concept | Condition | `OMOP:4102124` | `MONDO:0010029` |
| major55 | condition_concept | Condition | `HP:0001712` | `MONDO:0012289` |
| prafib5 | condition_concept | Condition | `MONDO:0004981` | `MONDO:0020456` |
| rmorph1 | condition_concept | Condition | `OMOP:4102124` | `MONDO:0010029` |
| strk | condition_concept | Condition | `HP:0001297` | `MONDO:0005098` |
| strktype | condition_concept | Condition | `HP:0001297` | `MONDO:0005098` |
| strokef | condition_concept | Condition | `HP:0001297` | `MONDO:0005098` |
| afibcd | condition_concept | Condition (HPO) | `MONDO:0004981` | `HP:0005110` |
| devlpyr5 | condition_concept | Condition (HPO) | `MONDO:0004979` | `HP:0030877` |
| dmage | condition_concept | Condition (HPO) | `MONDO:0005015` | `HP:0004904` |
| fhxdb2 | condition_concept | Condition (HPO) | `MONDO:0005015` | `HP:0011432` |
| AGATP12C | observation_type | Measurement | `OMOP:42872742` | `LOINC:22030-1` |
| AGATP13C | observation_type | Measurement | `OMOP:42872742` | `LOINC:22030-1` |
| AGATP14C | observation_type | Measurement | `OMOP:42872742` | `LOINC:22030-1` |
| AGATP22C | observation_type | Measurement | `OMOP:42872742` | `LOINC:22030-1` |
| AGATP23C | observation_type | Measurement | `OMOP:42872742` | `LOINC:22030-1` |
| AGATP24C | observation_type | Measurement | `OMOP:42872742` | `LOINC:22030-1` |
| AGATPM2C | observation_type | Measurement | `OMOP:42872742` | `LOINC:20071-7` |
| AGATPM3C | observation_type | Measurement | `OMOP:42872742` | `LOINC:20071-7` |
| AGATU12C | observation_type | Measurement | `OMOP:42872742` | `LOINC:22030-1` |
| AGATU13C | observation_type | Measurement | `OMOP:42872742` | `LOINC:22030-1` |
| AGATU14C | observation_type | Measurement | `OMOP:42872742` | `LOINC:22030-1` |
| AGATU22C | observation_type | Measurement | `OMOP:42872742` | `LOINC:22030-1` |
| AGATU23C | observation_type | Measurement | `OMOP:42872742` | `LOINC:22030-1` |
| AGATU24C | observation_type | Measurement | `OMOP:42872742` | `LOINC:22030-1` |
| AGATUM2C | observation_type | Measurement | `OMOP:42872742` | `LOINC:20071-7` |
| AGATUM3C | observation_type | Measurement | `OMOP:42872742` | `LOINC:20071-7` |
| CESD4C | observation_type | Measurement | `OMOP:36303297` | `LOINC:100766-5` |
| ISOPROST | observation_type | Measurement | `OMOP:3011888` | `LOINC:71391-7` |
| VOLP12C | observation_type | Measurement | `OMOP:4166120` | `LOINC:22030-1` |
| VOLP13C | observation_type | Measurement | `OMOP:4166120` | `LOINC:22030-1` |
| VOLP14C | observation_type | Measurement | `OMOP:4166120` | `LOINC:22030-1` |
| VOLP22C | observation_type | Measurement | `OMOP:4166120` | `LOINC:22030-1` |
| VOLP23C | observation_type | Measurement | `OMOP:4166120` | `LOINC:22030-1` |
| VOLP24C | observation_type | Measurement | `OMOP:4166120` | `LOINC:22030-1` |
| VOLPM2C | observation_type | Measurement | `OMOP:4166120` | `LOINC:20071-7` |
| VOLSP14C | observation_type | Measurement | `OMOP:42872742` | `LOINC:87896-7` |
| VOLSP24C | observation_type | Measurement | `OMOP:42872742` | `LOINC:87896-7` |
| VOLSU14C | observation_type | Measurement | `OMOP:42872742` | `LOINC:22030-1` |
| VOLSU24C | observation_type | Measurement | `OMOP:42872742` | `LOINC:22030-1` |
| VOLSUM2C | observation_type | Measurement | `OMOP:42872742` | `LOINC:60949-5` |
| VOLSUM3C | observation_type | Measurement | `OMOP:42872742` | `LOINC:60949-5` |
| VOLU12C | observation_type | Measurement | `OMOP:4166120` | `LOINC:22030-1` |
| VOLU13C | observation_type | Measurement | `OMOP:4166120` | `LOINC:22030-1` |
| VOLU14C | observation_type | Measurement | `OMOP:4166120` | `LOINC:22030-1` |
| VOLU22C | observation_type | Measurement | `OMOP:4166120` | `LOINC:22030-1` |
| VOLU23C | observation_type | Measurement | `OMOP:4166120` | `LOINC:22030-1` |
| VOLU24C | observation_type | Measurement | `OMOP:4166120` | `LOINC:22030-1` |
| VOLUM2C | observation_type | Measurement | `OMOP:4166120` | `LOINC:20071-7` |
| VOLUM3C | observation_type | Measurement | `OMOP:4166120` | `LOINC:20071-7` |
| abbaspha | observation_type | Measurement | `OMOP:3006315` | `LOINC:26444-0` |
| abeospha | observation_type | Measurement | `OMOP:3013115` | `LOINC:26449-9` |
| abmoncya | observation_type | Measurement | `OBA:VT0000223` | `LOINC:26484-6` |
| agatp11c | observation_type | Measurement | `OMOP:42872742` | `LOINC:87907-2` |
| agatp1fc | observation_type | Measurement | `OMOP:42872742` | `LOINC:87907-2` |
| agatp21c | observation_type | Measurement | `OMOP:42872742` | `LOINC:87907-2` |
| agatp2fc | observation_type | Measurement | `OMOP:42872742` | `LOINC:87907-2` |
| agatpm1c | observation_type | Measurement | `OMOP:42872742` | `LOINC:60949-5` |
| agatpm4c | observation_type | Measurement | `OMOP:42872742` | `LOINC:20071-7` |
| agatpmfc | observation_type | Measurement | `OMOP:42872742` | `LOINC:60949-5` |
| agatu11c | observation_type | Measurement | `OMOP:42872742` | `LOINC:90312-0` |
| agatu1fc | observation_type | Measurement | `OMOP:42872742` | `LOINC:90312-0` |
| agatu21c | observation_type | Measurement | `OMOP:42872742` | `LOINC:90312-0` |
| agatu2fc | observation_type | Measurement | `OMOP:42872742` | `LOINC:90312-0` |
| agatum1c | observation_type | Measurement | `OMOP:42872742` | `LOINC:60949-5` |
| agatum4c | observation_type | Measurement | `OMOP:42872742` | `LOINC:20071-7` |
| agatumfc | observation_type | Measurement | `OMOP:42872742` | `LOINC:60949-5` |
| age1c | observation_type | Measurement | `OMOP:4154347` | `LOINC:30525-0` |
| age1c | observation_type | Measurement | `OMOP:4282779` | `LOINC:30525-0` |
| age2c | observation_type | Measurement | `OMOP:4154347` | `LOINC:30525-0` |
| age2c | observation_type | Measurement | `OMOP:4282779` | `LOINC:30525-0` |
| age3c | observation_type | Measurement | `OMOP:4154347` | `LOINC:30525-0` |
| age3c | observation_type | Measurement | `OMOP:4282779` | `LOINC:30525-0` |
| age4c | observation_type | Measurement | `OMOP:35609491` | `LOINC:30525-0` |
| age4c | observation_type | Measurement | `OMOP:4282779` | `LOINC:30525-0` |
| age5c | observation_type | Measurement | `OMOP:4154347` | `LOINC:30525-0` |
| age5c | observation_type | Measurement | `OMOP:4282779` | `LOINC:30525-0` |
| agefc | observation_type | Measurement | `OBA:VT0002871` | `LOINC:30525-0` |
| agefc | observation_type | Measurement | `OMOP:4282779` | `LOINC:30525-0` |
| agesc | observation_type | Measurement | `OMOP:4156660` | `LOINC:30525-0` |
| alcwk1c | observation_type | Measurement | `OMOP:35609491` | `LOINC:44940-5` |
| alcwkcf | observation_type | Measurement | `OMOP:35609491` | `LOINC:64628-1` |
| atrialrt5 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| avgrate5 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| basosa5 | observation_type | Measurement | `OMOP:3006315` | `LOINC:26444-0` |
| bcswtkg5 | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| bmi1c | observation_type | Measurement | `OBA:2045455` | `LOINC:39156-5` |
| bmi2c | observation_type | Measurement | `OBA:2045455` | `LOINC:39156-5` |
| bmi3c | observation_type | Measurement | `OBA:2045455` | `LOINC:39156-5` |
| bmi4c | observation_type | Measurement | `OBA:2045455` | `LOINC:39156-5` |
| bmi5c | observation_type | Measurement | `OBA:2045455` | `LOINC:39156-5` |
| bmifc | observation_type | Measurement | `OBA:2045455` | `LOINC:39156-5` |
| cam1a | observation_type | Measurement | `OMOP:36305170` | `LOINC:39804-0` |
| ccafwm1 | observation_type | Measurement | `OMOP:4138462` | `LOINC:76287-2` |
| cd40l1 | observation_type | Measurement | `OMOP:4209737` | `LOINC:42932-4` |
| cepgfr1c | observation_type | Measurement | `OMOP:37208635` | `LOINC:100036-3` |
| cepgfr3c | observation_type | Measurement | `OMOP:37208635` | `LOINC:100035-5` |
| cepgfr4c | observation_type | Measurement | `OMOP:37208635` | `LOINC:100035-5` |
| cepgfr5c | observation_type | Measurement | `OMOP:37208635` | `LOINC:100036-3` |
| cesd1c | observation_type | Measurement | `OMOP:36303297` | `LOINC:100766-5` |
| cesd3c | observation_type | Measurement | `OMOP:36303297` | `LOINC:100766-5` |
| cesd5c | observation_type | Measurement | `OMOP:36303297` | `LOINC:100766-5` |
| cesdfc | observation_type | Measurement | `OMOP:36303297` | `LOINC:100766-5` |
| chol1 | observation_type | Measurement | `OBA:VT0000180` | `LOINC:110258-1` |
| chol2 | observation_type | Measurement | `OBA:VT0000180` | `LOINC:110258-1` |
| chol3 | observation_type | Measurement | `OBA:VT0000180` | `LOINC:110258-1` |
| chol4 | observation_type | Measurement | `OBA:VT0000180` | `LOINC:110258-1` |
| chol5 | observation_type | Measurement | `OBA:VT0000180` | `LOINC:110258-1` |
| cholf | observation_type | Measurement | `OBA:VT0000180` | `LOINC:110258-1` |
| cig1c | observation_type | Measurement | `OMOP:4282779` | `LOINC:105045-9` |
| cig1ca4 | observation_type | Measurement | `OMOP:4282779` | `LOINC:105045-9` |
| cig4c | observation_type | Measurement | `OMOP:4282779` | `LOINC:92290-6` |
| cig5c | observation_type | Measurement | `OMOP:4282779` | `LOINC:92290-6` |
| cigfc | observation_type | Measurement | `OMOP:4282779` | `LOINC:105045-9` |
| clc1 | observation_type | Measurement | `OBA:VT0003018` | `LOINC:31291-8` |
| creatin5 | observation_type | Measurement | `OMOP:2212294` | `LOINC:14682-9` |
| crp1 | observation_type | Measurement | `OMOP:4208414` | `LOINC:16503-5` |
| crp3 | observation_type | Measurement | `OMOP:4208414` | `LOINC:16503-5` |
| crp4 | observation_type | Measurement | `OMOP:4208414` | `LOINC:16503-5` |
| crpf | observation_type | Measurement | `OMOP:4208414` | `LOINC:16503-5` |
| cystatc1 | observation_type | Measurement | `OMOP:4136584` | `LOINC:33863-2` |
| cystatc5 | observation_type | Measurement | `OMOP:4136584` | `LOINC:47612-7` |
| dbp1c | observation_type | Measurement | `OMOP:4154790` | `LOINC:8462-4` |
| dbp2c | observation_type | Measurement | `OMOP:4154790` | `LOINC:8462-4` |
| dbp3c | observation_type | Measurement | `OMOP:4154790` | `LOINC:8462-4` |
| dbp4c | observation_type | Measurement | `OMOP:4154790` | `LOINC:8462-4` |
| dbp5c | observation_type | Measurement | `OMOP:4154790` | `LOINC:8462-4` |
| dbpfc | observation_type | Measurement | `OMOP:4154790` | `LOINC:8462-4` |
| ddimer1 | observation_type | Measurement | `OMOP:37393605` | `LOINC:38898-3` |
| ddimer4 | observation_type | Measurement | `OMOP:37393605` | `LOINC:38898-3` |
| ddimer_ss | observation_type | Measurement | `OMOP:37393605` | `LOINC:38898-3` |
| ddimerf | observation_type | Measurement | `OMOP:37393605` | `LOINC:38898-3` |
| ecgpmk1 | observation_type | Measurement | `OMOP:45772840` | `LOINC:99684-3` |
| egfr1c | observation_type | Measurement | `OMOP:37208635` | `LOINC:33163-7` |
| egfr5c | observation_type | Measurement | `OMOP:37208635` | `LOINC:100036-3` |
| egfrfc | observation_type | Measurement | `OMOP:37208635` | `LOINC:33163-7` |
| eosa5 | observation_type | Measurement | `OMOP:3013115` | `LOINC:26449-9` |
| eselct4 | observation_type | Measurement | `OBA:2052778` | `LOINC:28071-9` |
| eselect1 | observation_type | Measurement | `OBA:2052778` | `LOINC:28071-9` |
| exam3 | observation_type | Measurement | `OBA:2060174` | `LOINC:22029-3` |
| f81 | observation_type | Measurement | `OBA:2041536` | `LOINC:10395-2` |
| fgavocado5c | observation_type | Measurement | `OMOP:4042886` | `LOINC:80445-0` |
| fgfruit5c | observation_type | Measurement | `OMOP:21493059` | `LOINC:80445-0` |
| fgfruitjuice5c | observation_type | Measurement | `OMOP:21493059` | `LOINC:80445-0` |
| fgtomato5c | observation_type | Measurement | `OMOP:4042886` | `LOINC:80445-0` |
| fgvcrucifer5c | observation_type | Measurement | `OMOP:4042886` | `LOINC:80445-0` |
| fgvdyellow5c | observation_type | Measurement | `OMOP:4042886` | `LOINC:80445-0` |
| fgvgreenleafy5c | observation_type | Measurement | `OMOP:4042886` | `LOINC:75287-3` |
| fgvother5c | observation_type | Measurement | `OMOP:4042886` | `LOINC:49222-3` |
| fgvpotato5c | observation_type | Measurement | `OMOP:4042886` | `LOINC:80445-0` |
| fib1 | observation_type | Measurement | `OBA:0000061` | `LOINC:3255-7` |
| fib4 | observation_type | Measurement | `OBA:0000061` | `LOINC:3255-7` |
| fibrgn3 | observation_type | Measurement | `OBA:0000061` | `LOINC:3255-7` |
| fviii_ss | observation_type | Measurement | `OBA:2041536` | `LOINC:10395-2` |
| glucos1c | observation_type | Measurement | `OMOP:4156660` | `LOINC:63382-6` |
| glucos1u | observation_type | Measurement | `OMOP:4156660` | `LOINC:76629-5` |
| glucos2c | observation_type | Measurement | `OMOP:4156660` | `LOINC:100035-5` |
| glucos3c | observation_type | Measurement | `OMOP:4156660` | `LOINC:100035-5` |
| glucos4c | observation_type | Measurement | `OMOP:4156660` | `LOINC:100035-5` |
| glucose | observation_type | Measurement | `OBA:VT0000188` | `LOINC:105272-9` |
| glucose5 | observation_type | Measurement | `OMOP:4156660` | `LOINC:63382-6` |
| glucosfc | observation_type | Measurement | `OMOP:4156660` | `LOINC:100035-5` |
| glucossc | observation_type | Measurement | `OMOP:4156660` | `LOINC:63382-6` |
| hba1c2 | observation_type | Measurement | `OMOP:4184637` | `LOINC:718-7` |
| hba1c5 | observation_type | Measurement | `OMOP:4184637` | `LOINC:718-7` |
| hct5 | observation_type | Measurement | `OMOP:4151358` | `LOINC:4544-3` |
| hctdifa | observation_type | Measurement | `OMOP:4151358` | `LOINC:4544-3` |
| hdl1 | observation_type | Measurement | `OBA:VT0000184` | `LOINC:96596-2` |
| hdl2 | observation_type | Measurement | `OBA:VT0000184` | `LOINC:96596-2` |
| hdl3 | observation_type | Measurement | `OBA:VT0000184` | `LOINC:96596-2` |
| hdl4 | observation_type | Measurement | `OBA:VT0000184` | `LOINC:96596-2` |
| hdl5 | observation_type | Measurement | `OBA:VT0000184` | `LOINC:96596-2` |
| hdlf | observation_type | Measurement | `OBA:VT0000184` | `LOINC:96596-2` |
| heartrt1 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| hgb5 | observation_type | Measurement | `OMOP:4094758` | `LOINC:718-7` |
| hgbdifa | observation_type | Measurement | `OMOP:4094758` | `LOINC:718-7` |
| hipcm1 | observation_type | Measurement | `OMOP:4111665` | `LOINC:62409-8` |
| hipcm2 | observation_type | Measurement | `OMOP:4111665` | `LOINC:62409-8` |
| hipcm3 | observation_type | Measurement | `OMOP:4111665` | `LOINC:62409-8` |
| hipcm4 | observation_type | Measurement | `OMOP:4111665` | `LOINC:62409-8` |
| hipcm5 | observation_type | Measurement | `OMOP:4111665` | `LOINC:62409-8` |
| hipcmf | observation_type | Measurement | `OMOP:4087501` | `LOINC:45716-8` |
| hr1dina1 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| hr1dina2 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| hr1dina3 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| hr1dina4 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| hr1dina5 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| hr2dina1 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| hr2dina2 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| hr2dina3 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| hr2dina4 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| hr2dina5 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| hr3dina1 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| hr3dina2 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| hr3dina3 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| hr3dina4 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| hr3dina5 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| hrdina1c | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| hrdina2c | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| hrdina3c | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| hrdina4c | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| hrdina5c | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| hrtrate1 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| hrtrate5 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| htcm1 | observation_type | Measurement | `OMOP:607590` | `LOINC:8302-2` |
| htcm2 | observation_type | Measurement | `OMOP:607590` | `LOINC:8302-2` |
| htcm3 | observation_type | Measurement | `OMOP:607590` | `LOINC:8302-2` |
| htcm4 | observation_type | Measurement | `OMOP:607590` | `LOINC:8302-2` |
| htcm5 | observation_type | Measurement | `OMOP:607590` | `LOINC:8302-2` |
| htcmf | observation_type | Measurement | `OMOP:607590` | `LOINC:8302-2` |
| icam4 | observation_type | Measurement | `OMOP:4284103` | `LOINC:81058-0` |
| il10_ss | observation_type | Measurement | `OMOP:3004578` | `LOINC:34151-1` |
| il10a1m | observation_type | Measurement | `OMOP:3004578` | `LOINC:90861-6` |
| il61 | observation_type | Measurement | `OBA:2052890` | `LOINC:49732-1` |
| il63 | observation_type | Measurement | `OBA:2052890` | `LOINC:17115-7` |
| il6_ss | observation_type | Measurement | `OBA:2052890` | `LOINC:17115-7` |
| income1 | observation_type | Measurement | `OMOP:4076114` | `LOINC:82665-1` |
| income2 | observation_type | Measurement | `OMOP:4076114` | `LOINC:100279-9` |
| income3 | observation_type | Measurement | `OMOP:4076114` | `LOINC:100279-9` |
| income5 | observation_type | Measurement | `OMOP:4076114` | `LOINC:100279-9` |
| incomef | observation_type | Measurement | `OMOP:4076114` | `LOINC:112442-9` |
| insln3 | observation_type | Measurement | `OBA:2060174` | `LOINC:1987-7` |
| inslnr1t | observation_type | Measurement | `OBA:2060174` | `LOINC:62805-7` |
| insulin5 | observation_type | Measurement | `OBA:2060174` | `LOINC:19732-7` |
| kc1 | observation_type | Measurement | `OBA:VT0002668` | `LOINC:31291-8` |
| lagea4 | observation_type | Measurement | `OMOP:607590` | `LOINC:30525-0` |
| lagea4 | observation_type | Measurement | `OMOP:4282779` | `LOINC:30525-0` |
| lastdrk1 | observation_type | Measurement | `OBA:VT0000184` | `LOINC:65526-6` |
| lastdrkf | observation_type | Measurement | `OBA:VT0000184` | `LOINC:65526-6` |
| ldccamxavg5 | observation_type | Measurement | `OMOP:4138462` | `LOINC:100073-6` |
| ldl | observation_type | Measurement | `OBA:VT0000181` | `LOINC:57938-3` |
| ldl1 | observation_type | Measurement | `OBA:VT0000181` | `LOINC:14155-6` |
| ldl2 | observation_type | Measurement | `OBA:VT0000181` | `LOINC:14155-6` |
| ldl3 | observation_type | Measurement | `OBA:VT0000181` | `LOINC:14155-6` |
| ldl4 | observation_type | Measurement | `OBA:VT0000181` | `LOINC:14155-6` |
| ldl5 | observation_type | Measurement | `OBA:VT0000181` | `LOINC:14155-6` |
| ldlf | observation_type | Measurement | `OBA:VT0000181` | `LOINC:14155-6` |
| liqwk2 | observation_type | Measurement | `OMOP:35609491` | `LOINC:105997-1` |
| liqwk3 | observation_type | Measurement | `OMOP:35609491` | `LOINC:105997-1` |
| liqwk4 | observation_type | Measurement | `OMOP:35609491` | `LOINC:100418-3` |
| liqwk5 | observation_type | Measurement | `OMOP:35609491` | `LOINC:100418-3` |
| lsmoksa4 | observation_type | Measurement | `OMOP:4282779` | `LOINC:111839-7` |
| lsten1 | observation_type | Measurement | `OMOP:43020498` | `LOINC:76761-6` |
| lunghta4 | observation_type | Measurement | `OMOP:607590` | `LOINC:8302-2` |
| lymphsa5 | observation_type | Measurement | `OMOP:37208689` | `LOINC:26474-7` |
| mch5 | observation_type | Measurement | `OMOP:37398674` | `LOINC:785-6` |
| mchc5 | observation_type | Measurement | `OMOP:37393850` | `LOINC:786-4` |
| mcv5 | observation_type | Measurement | `OBA:0003460` | `LOINC:787-2` |
| mmp91 | observation_type | Measurement | `OMOP:40761106` | `LOINC:107455-8` |
| mnapcp1 | observation_type | Measurement | `OBA:VT2000000` | `LOINC:107142-2` |
| mnapwp1 | observation_type | Measurement | `OBA:VT2000000` | `LOINC:107142-2` |
| monosa5 | observation_type | Measurement | `OBA:VT0000223` | `LOINC:26484-6` |
| nac1 | observation_type | Measurement | `OBA:VT0001776` | `LOINC:31291-8` |
| nhdlc31c | observation_type | Measurement | `OBA:VT0000184` | `LOINC:80737-0` |
| ntprbnp1 | observation_type | Measurement | `OMOP:4189511` | `LOINC:22031-9` |
| ntprbnp3 | observation_type | Measurement | `OMOP:4189511` | `LOINC:22031-9` |
| pacem5 | observation_type | Measurement | `OMOP:45772840` | `LOINC:74727-9` |
| pagatm5 | observation_type | Measurement | `OMOP:42872742` | `LOINC:99946-6` |
| plac1a | observation_type | Measurement | `OMOP:3041450` | `LOINC:39804-0` |
| plt5 | observation_type | Measurement | `OMOP:4267147` | `LOINC:777-3` |
| pltca | observation_type | Measurement | `OMOP:4267147` | `LOINC:777-3` |
| pmkrf | observation_type | Measurement | `OMOP:45772840` | `LOINC:99685-0` |
| polysa5 | observation_type | Measurement | `OMOP:37208699` | `LOINC:26499-4` |
| potas4c | observation_type | Measurement | `OBA:VT0002668` | `LOINC:105906-2` |
| potasex4 | observation_type | Measurement | `OBA:VT0002668` | `LOINC:100036-3` |
| prdur1 | observation_type | Measurement | `OMOP:4274406` | `LOINC:18529-8` |
| prdur5 | observation_type | Measurement | `OMOP:4274406` | `LOINC:18529-8` |
| qrsdur1 | observation_type | Measurement | `OBA:1001086` | `LOINC:9952-3` |
| qrsdur5 | observation_type | Measurement | `OBA:1001086` | `LOINC:9952-3` |
| qtdur1 | observation_type | Measurement | `OMOP:4273023` | `LOINC:8634-8` |
| qtdur5 | observation_type | Measurement | `OMOP:4273023` | `LOINC:8634-8` |
| rbc5 | observation_type | Measurement | `OMOP:4030871` | `LOINC:789-8` |
| rbcdifa | observation_type | Measurement | `OMOP:4030871` | `LOINC:789-8` |
| rchrtrt1 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| rdccamxavg5 | observation_type | Measurement | `OMOP:4138462` | `LOINC:107440-0` |
| rsten1 | observation_type | Measurement | `OMOP:43021859` | `LOINC:67256-8` |
| rwinewk2 | observation_type | Measurement | `OMOP:35609491` | `LOINC:28859-7` |
| rwinewk3 | observation_type | Measurement | `OMOP:35609491` | `LOINC:28859-7` |
| rwinewk4 | observation_type | Measurement | `OMOP:35609491` | `LOINC:28859-7` |
| rwinewk5 | observation_type | Measurement | `OMOP:35609491` | `LOINC:28859-7` |
| sbp1c | observation_type | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| sbp2c | observation_type | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| sbp3c | observation_type | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| sbp4c | observation_type | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| sbp5c | observation_type | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| sbpfc | observation_type | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| scrc1 | observation_type | Measurement | `OMOP:42872742` | `LOINC:84969-5` |
| scrc5 | observation_type | Measurement | `OMOP:42872742` | `LOINC:84969-5` |
| sidno | observation_type | Measurement | `OMOP:4154790` | `LOINC:99417-8` |
| slad1 | observation_type | Measurement | `OMOP:42872742` | `LOINC:84969-5` |
| slad5 | observation_type | Measurement | `OMOP:42872742` | `LOINC:84969-5` |
| slft1 | observation_type | Measurement | `OMOP:42872742` | `LOINC:84969-5` |
| slft5 | observation_type | Measurement | `OMOP:42872742` | `LOINC:84969-5` |
| slpwkhr4 | observation_type | Measurement | `OBA:2040171` | `LOINC:70379-3` |
| smain3 | observation_type | Measurement | `OMOP:42872742` | `LOINC:38643-3` |
| smkstat2 | observation_type | Measurement | `OMOP:4282779` | `LOINC:111839-7` |
| smkstat3 | observation_type | Measurement | `OMOP:4282779` | `LOINC:111839-7` |
| smkstat4 | observation_type | Measurement | `OMOP:4282779` | `LOINC:63900-5` |
| smkstat5 | observation_type | Measurement | `OMOP:4282779` | `LOINC:63900-5` |
| srt1 | observation_type | Measurement | `OMOP:42872742` | `LOINC:84969-5` |
| srt5 | observation_type | Measurement | `OMOP:42872742` | `LOINC:84969-5` |
| tempca4 | observation_type | Measurement | `OBA:VT0005535` | `LOINC:76006-6` |
| tnfa3 | observation_type | Measurement | `OBA:2051979` | `LOINC:40463-2` |
| tnfa3m | observation_type | Measurement | `OBA:2051979` | `LOINC:40463-2` |
| tnfa_ss | observation_type | Measurement | `OBA:2051979` | `LOINC:3074-2` |
| tnfri1 | observation_type | Measurement | `OBA:2051975` | `LOINC:42079-4` |
| trig1 | observation_type | Measurement | `OBA:VT0002644` | `LOINC:30570-6` |
| trig2 | observation_type | Measurement | `OBA:VT0002644` | `LOINC:30570-6` |
| trig3 | observation_type | Measurement | `OBA:VT0002644` | `LOINC:30570-6` |
| trig4 | observation_type | Measurement | `OBA:VT0002644` | `LOINC:30570-6` |
| trig5 | observation_type | Measurement | `OBA:VT0002644` | `LOINC:30570-6` |
| trigf | observation_type | Measurement | `OBA:VT0002644` | `LOINC:30570-6` |
| uagatm5 | observation_type | Measurement | `OMOP:42872742` | `LOINC:82665-1` |
| ualbcre1 | observation_type | Measurement | `OMOP:4154347` | `LOINC:46943-7` |
| ualbcre2 | observation_type | Measurement | `OMOP:4154347` | `LOINC:46943-7` |
| ualbcre3 | observation_type | Measurement | `OMOP:4154347` | `LOINC:46943-7` |
| ualbcre5 | observation_type | Measurement | `OMOP:4154347` | `LOINC:46943-7` |
| ualbumn1 | observation_type | Measurement | `OBA:VT0002871` | `LOINC:69280-6` |
| ualbumn2 | observation_type | Measurement | `OBA:VT0002871` | `LOINC:69280-6` |
| ualbumn3 | observation_type | Measurement | `OBA:VT0002871` | `LOINC:69280-6` |
| ualbumn5 | observation_type | Measurement | `OBA:VT0002871` | `LOINC:69280-6` |
| ualbumnf | observation_type | Measurement | `OBA:VT0002871` | `LOINC:69280-6` |
| ucreat1 | observation_type | Measurement | `OMOP:3007081` | `LOINC:28239-2` |
| ucreat2 | observation_type | Measurement | `OMOP:3007081` | `LOINC:28239-2` |
| ucreat3 | observation_type | Measurement | `OMOP:3007081` | `LOINC:28239-2` |
| ucreat5 | observation_type | Measurement | `OMOP:3007081` | `LOINC:28239-2` |
| ucreatf | observation_type | Measurement | `OMOP:3007081` | `LOINC:28239-2` |
| usratefrst5 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| usratescnd5 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| usratethrd5 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| vcrc1 | observation_type | Measurement | `OMOP:4166120` | `LOINC:84969-5` |
| vcrc5 | observation_type | Measurement | `OMOP:4166120` | `LOINC:84969-5` |
| ventrrt5 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| vlad1 | observation_type | Measurement | `OMOP:4166120` | `LOINC:84969-5` |
| vlad5 | observation_type | Measurement | `OMOP:4166120` | `LOINC:84969-5` |
| vlft1 | observation_type | Measurement | `OMOP:4166120` | `LOINC:36905-8` |
| vlft5 | observation_type | Measurement | `OMOP:4166120` | `LOINC:36905-8` |
| vmain3 | observation_type | Measurement | `OMOP:4166120` | `LOINC:38643-3` |
| volp11c | observation_type | Measurement | `OMOP:4166120` | `LOINC:22030-1` |
| volp1fc | observation_type | Measurement | `OMOP:4166120` | `LOINC:22030-1` |
| volp21c | observation_type | Measurement | `OMOP:4166120` | `LOINC:22030-1` |
| volp2fc | observation_type | Measurement | `OMOP:4166120` | `LOINC:22030-1` |
| volpm1c | observation_type | Measurement | `OMOP:4166120` | `LOINC:20071-7` |
| volpm4c | observation_type | Measurement | `OMOP:4166120` | `LOINC:20071-7` |
| volpmfc | observation_type | Measurement | `OMOP:4166120` | `LOINC:20071-7` |
| volsp11c | observation_type | Measurement | `OMOP:42872742` | `LOINC:87896-7` |
| volsp21c | observation_type | Measurement | `OMOP:42872742` | `LOINC:87896-7` |
| volsu11c | observation_type | Measurement | `OMOP:42872742` | `LOINC:22030-1` |
| volsu21c | observation_type | Measurement | `OMOP:42872742` | `LOINC:22030-1` |
| volsum1c | observation_type | Measurement | `OMOP:42872742` | `LOINC:60949-5` |
| volu11c | observation_type | Measurement | `OMOP:4166120` | `LOINC:22030-1` |
| volu1fc | observation_type | Measurement | `OMOP:4166120` | `LOINC:22030-1` |
| volu21c | observation_type | Measurement | `OMOP:4166120` | `LOINC:22030-1` |
| volu2fc | observation_type | Measurement | `OMOP:4166120` | `LOINC:22030-1` |
| volum1c | observation_type | Measurement | `OMOP:4166120` | `LOINC:20071-7` |
| volum4c | observation_type | Measurement | `OMOP:4166120` | `LOINC:20071-7` |
| volumfc | observation_type | Measurement | `OMOP:4166120` | `LOINC:20071-7` |
| vospm1c | observation_type | Measurement | `OMOP:42872742` | `LOINC:95822-3` |
| vrt1 | observation_type | Measurement | `OMOP:4166120` | `LOINC:84969-5` |
| vrt5 | observation_type | Measurement | `OMOP:4166120` | `LOINC:84969-5` |
| vscrc1 | observation_type | Measurement | `OMOP:4166120` | `LOINC:84969-5` |
| vscrc5 | observation_type | Measurement | `OMOP:4166120` | `LOINC:84969-5` |
| vslad1 | observation_type | Measurement | `OMOP:4166120` | `LOINC:84969-5` |
| vslad5 | observation_type | Measurement | `OMOP:4166120` | `LOINC:84969-5` |
| vslft1 | observation_type | Measurement | `OMOP:4166120` | `LOINC:84969-5` |
| vslft5 | observation_type | Measurement | `OMOP:4166120` | `LOINC:84969-5` |
| vsrt1 | observation_type | Measurement | `OMOP:4166120` | `LOINC:84969-5` |
| vsrt5 | observation_type | Measurement | `OMOP:4166120` | `LOINC:84969-5` |
| vwf1 | observation_type | Measurement | `OBA:2052741` | `LOINC:69982-7` |
| waistcm1 | observation_type | Measurement | `OBA:1001085` | `LOINC:8280-0` |
| waistcm2 | observation_type | Measurement | `OBA:1001085` | `LOINC:8280-0` |
| waistcm3 | observation_type | Measurement | `OBA:1001085` | `LOINC:8280-0` |
| waistcm4 | observation_type | Measurement | `OBA:1001085` | `LOINC:8280-0` |
| waistcm5 | observation_type | Measurement | `OBA:1001085` | `LOINC:8280-0` |
| waistcmf | observation_type | Measurement | `OMOP:4087501` | `LOINC:56117-5` |
| wbc5 | observation_type | Measurement | `OBA:VT0000217` | `LOINC:6690-2` |
| wbca | observation_type | Measurement | `OBA:VT0000217` | `LOINC:6690-2` |
| wt20lb1 | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| wt20lbf | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| wt40lb1 | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| wt40lbf | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| wtlb1 | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| wtlbf | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| wwinewk2 | observation_type | Measurement | `OMOP:35609491` | `LOINC:28849-8` |
| wwinewk3 | observation_type | Measurement | `OMOP:35609491` | `LOINC:28849-8` |
| wwinewk4 | observation_type | Measurement | `OMOP:35609491` | `LOINC:28849-8` |
| wwinewk5 | observation_type | Measurement | `OMOP:35609491` | `LOINC:28849-8` |

### Unverified Misalignments (29 — no YAML confirmation)

| Variable | Slot | Entity Type | CSV CURIE | Agent Suggestion |
| :---- | :---- | :---- | :---- | :---- |
| age1c | observations | Measurement | `OMOP:4152194` | `LOINC:30525-0` |
| age2c | observations | Measurement | `OMOP:4152194` | `LOINC:30525-0` |
| age3c | observations | Measurement | `OMOP:4152194` | `LOINC:30525-0` |
| age4c | observations | Measurement | `OMOP:4152194` | `LOINC:30525-0` |
| age5c | observations | Measurement | `OMOP:4152194` | `LOINC:30525-0` |
| agefc | observations | Measurement | `OMOP:4152194` | `LOINC:30525-0` |
| dbp1c | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| dbp2c | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| dbp3c | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| dbp4c | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| dbp5c | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| dbpfc | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| egfr3c | observation_type | Measurement | `OMOP:4213477` | `LOINC:100036-3` |
| egfr4c | observation_type | Measurement | `OMOP:37208635` | `LOINC:102097-3` |
| fev1a4 | observations | Measurement | `OMOP:3002094` | `LOINC:65819-5` |
| fevfvca4 | observations | Measurement | `OMOP:3002094` | `LOINC:20157-4` |
| fvca4 | observations | Measurement | `OMOP:3002094` | `LOINC:20152-5` |
| lagea4 | observations | Measurement | `OMOP:3002094` | `LOINC:30525-0` |
| lfev1fa4 | observations | Measurement | `OMOP:3002094` | `LOINC:20150-9` |
| pf1fvca4 | observations | Measurement | `OMOP:3002094` | `LOINC:20150-9` |
| pfev1a4 | observations | Measurement | `OMOP:3002094` | `LOINC:20150-9` |
| pfvca4 | observations | Measurement | `OMOP:3002094` | `LOINC:20152-5` |
| pprata4 | observations | Measurement | `OMOP:3002094` | `LOINC:20150-9` |
| sbp1c | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| sbp2c | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| sbp3c | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| sbp4c | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| sbp5c | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| sbpfc | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |

## Vocab/Slot Validation

Agent suggestions suppressed as vocabulary/slot mismatches (evaluated but not surfaced as findings): **75**

| Slot | Invalid vocab proposed | Suppressed count | Rule |
| :---- | :---- | ----: | :---- |
| `observation_type` | LOINC | 75 | Valid: OBA, OMOP |
| **Total** | | **75** | |

_These are not errors — they confirm the existing CURIEs are correct for their slots. The agent proposed codes from a vocabulary the bdchm slot is not typed for (e.g. OMOP in a MONDO-typed slot, LOINC in an OBA-typed slot). See `_SLOT_VOCAB_RULES` in `generate_semantic_review.py` for the full rule definitions._

## Error Cases Requiring Fix

### YAML Mismatches — 111 must be corrected
See the YAML Spot-Check section above.

### Missing Agent Suggestions — 9 variable-slot pair(s)

These substantive variables received no suggestion from any agent.
Investigate whether a suitable ontology term exists or the slot routing needs updating.

| Variable | Slot | Entity Type | Description |
| :---- | :---- | :---- | :---- |
| beerwk2 | observation_type | Measurement | # OF BEERS PER WEEK |
| beerwk3 | observation_type | Measurement | # OF BEERS PER WEEK |
| beerwk4 | observation_type | Measurement | BEERS PER WEEK |
| beerwk5 | observation_type | Measurement | BEERS PER WEEK |
| cig2c | observation_type | Measurement | CIGARRETTE SMOKING STATUS, EXAM 2 |
| cig3c | observation_type | Measurement | CIGARRETTE SMOKING STATUS, EXAM 3 |
| f81c | observation_type | Measurement | CALIBRATED FACTOR VIII (%) |
| icam1 | observation_type | Measurement | SICAM (ng/mL) |
| nan5c | observation_type | Measurement | NUTRIENTS: SODIUM (mg) |
