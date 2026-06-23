# ARIC Semantic Validator Summary v2026-06-19

**Generated:** 2026-06-19
**Mapreview CSV:** `ARIC_curie_mapreview.csv`
**Review MD:** `(none — generated from mapreview CSV only)`

---

## Overview

| Metric | Count |
| :---- | ----: |
| Total rows in mapreview CSV | 1762 |
| Admin variables skipped | 6 |
| Substantive variables reviewed | 1756 |
| Unique CURIEs validated | 128 |
| Unique YAML files referenced | 94 |
| Final Confirmed Findings rows | 7 |
| Anne Review Required rows | 0 |

## YAML Spot-Check

| Result | Count |
| :---- | ----: |
| Matches (✓) | 1313 |
| Mismatches (⚠) | 0 |
| Not checked (admin / no YAML) | 443 |

No YAML mismatches found — all spot-checked CURIEs match their YAML files.

## Agent Coverage by Entity Type

| Entity Type | Unique vars | MONDO | HPO | OMOP/LOINC | No suggestion |
| :---- | ----: | ----: | ----: | ----: | ----: |
| Condition (HPO) | 1 | 0 | 1 | 0 | 0 |
| Measurement | 595 | 0 | 0 | 503 | 92 |
| Person | 12 | 0 | 0 | 0 | 12 |
| ValueEnum | 21 | 0 | 0 | 0 | 21 |
| **Total** | **629** | | | | **125** |

**Coverage: 504/629 unique variable-slot pairs have at least one agent suggestion (80%).**

## Agent vs CSV CURIE Alignment

Agent suggestions differ from the current CSV CURIE in **504** variable-slot pair(s).

### Potential Improvements (384 — YAML confirms CSV, agent suggests different)

These cases have a YAML-confirmed CSV CURIE but the agent suggests a different concept.
Review whether the agent suggestion is more specific or accurate.

| Variable | Slot | Entity Type | CSV / YAML CURIE | Agent Suggestion |
| :---- | :---- | :---- | :---- | :---- |
| INCHF18 | condition_concept | Condition (HPO) | `MONDO:0005252` | `HP:0006682` |
| ABI32 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ABI4 | observation_type | Measurement | `OBA:1001087` | `LOINC:30525-0` |
| AGE | observation_type | Measurement | `OBA:2045303` | `LOINC:30525-0` |
| AGE_V1 | observation_type | Measurement | `OBA:2050096` | `LOINC:9991-1` |
| AGE_V2 | observation_type | Measurement | `OBA:2050096` | `LOINC:9992-9` |
| AGE_V3 | observation_type | Measurement | `OBA:VT0000188` | `LOINC:9897-0` |
| AGE_V4 | observation_type | Measurement | `OBA:2050096` | `LOINC:10043-8` |
| AGE_V5 | observation_type | Measurement | `OBA:2050096` | `LOINC:9995-2` |
| ANBPAV01 | observation_type | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| ANKSBP01 | observation_type | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| ANKSBP02 | observation_type | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| ANKSBP03 | observation_type | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| ANKSBP04 | observation_type | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| ANKSBP13 | observation_type | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| ANT10a | observation_type | Measurement | `OBA:1001085` | `LOINC:93198-0` |
| ANT3 | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| ANTA01 | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| ANTA04 | observation_type | Measurement | `OBA:VT0001259` | `LOINC:8302-2` |
| ANTA07A | observation_type | Measurement | `OBA:1001085` | `LOINC:94937-0` |
| ANTA07B | observation_type | Measurement | `OBA:1000032` | `LOINC:94937-0` |
| ANTB01 | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| ANTB04A | observation_type | Measurement | `OBA:1001085` | `LOINC:94937-0` |
| ANTB04B | observation_type | Measurement | `OBA:1000032` | `LOINC:94937-0` |
| ANTC1 | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| ANTC2 | observation_type | Measurement | `OBA:VT0001259` | `LOINC:8302-2` |
| ANTC3A | observation_type | Measurement | `OBA:1001085` | `LOINC:94937-0` |
| ANTC3B | observation_type | Measurement | `OBA:1000032` | `LOINC:94937-0` |
| ANTD1 | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| ANTD2 | observation_type | Measurement | `OBA:VT0001259` | `LOINC:8302-2` |
| ANTD3A | observation_type | Measurement | `OBA:1001085` | `LOINC:94937-0` |
| ANTD3B | observation_type | Measurement | `OBA:1000032` | `LOINC:8302-2` |
| ARBPAV01 | observation_type | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| ARMSBP01 | observation_type | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| ARMSBP02 | observation_type | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| ARMSBP13 | observation_type | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| ARMSBP33 | observation_type | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| ARMSBP43 | observation_type | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| BMI | observation_type | Measurement | `OBA:2045455` | `LOINC:39156-5` |
| BMI01 | observation_type | Measurement | `OBA:2045455` | `LOINC:39156-5` |
| BNP_LAST | observation_type | Measurement | `OBA:2045303` | `LOINC:76419-1` |
| BNP_WORST | observation_type | Measurement | `OBA:2045303` | `LOINC:77508-0` |
| BPUA02 | observation_type | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| BPUB02 | observation_type | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| CBC10 | observation_type | Measurement | `OMOP:37393850` | `LOINC:718-7` |
| CBC11 | observation_type | Measurement | `OMOP:37397924` | `LOINC:48244-8` |
| CBC12 | observation_type | Measurement | `OBA:0003277` | `LOINC:75996-9` |
| CBC13 | observation_type | Measurement | `OMOP:37208690` | `LOINC:26474-7` |
| CBC17 | observation_type | Measurement | `OBA:VT0000223` | `LOINC:26484-6` |
| CBC3 | observation_type | Measurement | `OBA:VT0000217` | `LOINC:6690-2` |
| CBC4 | observation_type | Measurement | `OBA:VT0001586` | `LOINC:789-8` |
| CBC5 | observation_type | Measurement | `OBA:2060175` | `LOINC:718-7` |
| CBC6 | observation_type | Measurement | `OBA:2045381` | `LOINC:4544-3` |
| CBC7 | observation_type | Measurement | `OMOP:4267147` | `LOINC:777-3` |
| CBC8 | observation_type | Measurement | `OBA:0003460` | `LOINC:787-2` |
| CBC9 | observation_type | Measurement | `OBA:2045301` | `LOINC:718-7` |
| CEAD141 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| CEAD142 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| CEBD141 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| CEBD142 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| CELB15H1 | observation_type | Measurement | `OBA:2050096` | `LOINC:1021-5` |
| CELB15I1 | observation_type | Measurement | `OBA:2050096` | `LOINC:14971-6` |
| CELB15J1 | observation_type | Measurement | `OBA:2050096` | `LOINC:18040-6` |
| CESD51 | observation_type | Measurement | `OMOP:36303297` | `LOINC:100766-5` |
| CESD61 | observation_type | Measurement | `OMOP:36303297` | `LOINC:100766-5` |
| CESD71 | observation_type | Measurement | `OMOP:36303297` | `LOINC:100766-5` |
| CHEM12 | observation_type | Measurement | `OBA:2052375` | `LOINC:30065-7` |
| CHEM15 | observation_type | Measurement | `OBA:VT0002668` | `LOINC:57379-0` |
| CHEM19 | observation_type | Measurement | `OBA:2060175` | `LOINC:718-7` |
| CHEM20 | observation_type | Measurement | `OMOP:4267147` | `LOINC:777-3` |
| CHEM21 | observation_type | Measurement | `OBA:VT0000217` | `LOINC:6690-2` |
| CHEM24 | observation_type | Measurement | `OBA:0003460` | `LOINC:787-2` |
| CHEM26 | observation_type | Measurement | `OMOP:37393850` | `LOINC:718-7` |
| CHEM27 | observation_type | Measurement | `OMOP:37397924` | `LOINC:21000-5` |
| CHEM28 | observation_type | Measurement | `OBA:0003277` | `LOINC:104610-1` |
| CHEM4 | observation_type | Measurement | `OBA:VT0010540` | `LOINC:108024-1` |
| CHEM5 | observation_type | Measurement | `OBA:VT0000188` | `LOINC:61153-3` |
| CHEM6 | observation_type | Measurement | `OBA:2050096` | `LOINC:56650-5` |
| CHM15 | observation_type | Measurement | `OMOP:4184637` | `LOINC:17856-6` |
| CHM21 | observation_type | Measurement | `OBA:2050096` | `LOINC:34555-3` |
| CHM33 | observation_type | Measurement | `OBA:VT0002871` | `LOINC:9195-9` |
| CHM39 | observation_type | Measurement | `OBA:VT0002871` | `LOINC:9195-9` |
| CHM45 | observation_type | Measurement | `OBA:VT0002871` | `LOINC:10274-9` |
| CHMA05 | observation_type | Measurement | `OBA:VT0001776` | `LOINC:12907-2` |
| CHMA06 | observation_type | Measurement | `OBA:VT0002668` | `LOINC:57379-0` |
| CHMA08 | observation_type | Measurement | `OBA:VT0005265` | `LOINC:57388-1` |
| CHMA09 | observation_type | Measurement | `OBA:2050096` | `LOINC:59834-2` |
| CHMA13 | observation_type | Measurement | `OBA:2050068` | `LOINC:100158-5` |
| CHMA16 | observation_type | Measurement | `OBA:2060174` | `LOINC:58522-4` |
| CHMB05 | observation_type | Measurement | `OBA:VT0001776` | `LOINC:12907-2` |
| CHMB06 | observation_type | Measurement | `OBA:VT0002668` | `LOINC:57379-0` |
| CHMB07 | observation_type | Measurement | `OBA:VT0000188` | `LOINC:105272-9` |
| CHMB08 | observation_type | Measurement | `OBA:2050096` | `LOINC:34555-3` |
| CIGT01 | observation_type | Measurement | `OMOP:4282779` | `LOINC:92290-6` |
| CIGT31 | observation_type | Measurement | `OMOP:4282779` | `LOINC:21830-5` |
| CIGT41 | observation_type | Measurement | `OMOP:4282779` | `LOINC:92290-6` |
| CIGT52 | observation_type | Measurement | `OMOP:4282779` | `LOINC:92290-6` |
| CIGT62 | observation_type | Measurement | `OMOP:4282779` | `LOINC:92290-6` |
| CIGT72 | observation_type | Measurement | `OMOP:4282779` | `LOINC:92290-6` |
| CORA22B | observation_type | Measurement | `OMOP:4282779` | `LOINC:35089-2` |
| CRP_V4 | observation_type | Measurement | `OMOP:4208414` | `LOINC:10043-8` |
| CYSC3 | observation_type | Measurement | `OBA:2052375` | `LOINC:33863-2` |
| CYSC_V2 | observation_type | Measurement | `OBA:2052375` | `LOINC:9908-5` |
| CYSC_V4 | observation_type | Measurement | `OBA:2052375` | `LOINC:18577-7` |
| CYSC_V5 | observation_type | Measurement | `OBA:2052375` | `LOINC:69081-8` |
| Chloride | observation_type | Measurement | `OBA:VT0003018` | `LOINC:100745-9` |
| DLC1a | observation_type | Measurement | `OMOP:4176265` | `LOINC:20152-5` |
| DSRA9 | observation_type | Measurement | `OMOP:45772840` | `LOINC:991-0` |
| ECAC26 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ECAD26 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ECGB31 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ECGB54 | observation_type | Measurement | `OBA:1001086` | `LOINC:9967-1` |
| ECGC31 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ECGC54 | observation_type | Measurement | `OBA:1001086` | `LOINC:9968-9` |
| ECGD31 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ECGD54 | observation_type | Measurement | `OBA:1001086` | `LOINC:9978-8` |
| ECGE31 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ECGE54 | observation_type | Measurement | `OBA:1001086` | `LOINC:9970-5` |
| ECGMA31 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ECGMA54 | observation_type | Measurement | `OBA:1001086` | `LOINC:9978-8` |
| ECGMB31 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ECGMB54 | observation_type | Measurement | `OBA:1001086` | `LOINC:9978-8` |
| ECGMC31 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ECGMC54 | observation_type | Measurement | `OBA:1001086` | `LOINC:9978-8` |
| ECGMD31 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ECGMD54 | observation_type | Measurement | `OBA:1001086` | `LOINC:9978-8` |
| ECGRA078 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ECGRA277 | observation_type | Measurement | `OBA:1001086` | `LOINC:9970-5` |
| ECGRA280 | observation_type | Measurement | `OBA:1001087` | `LOINC:30525-0` |
| ECHA1 | observation_type | Measurement | `OBA:1001087` | `LOINC:30525-0` |
| ECHA62 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ECHA77 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| EGFR2 | observation_type | Measurement | `OMOP:37208635` | `LOINC:98979-8` |
| EGFR51 | observation_type | Measurement | `OMOP:37208635` | `LOINC:73811-2` |
| EGFR61 | observation_type | Measurement | `OMOP:37208635` | `LOINC:73811-2` |
| EGFR71 | observation_type | Measurement | `OMOP:37208635` | `LOINC:53844-7` |
| EGFRCR51 | observation_type | Measurement | `OMOP:37208635` | `LOINC:65902-9` |
| EGFRCR61 | observation_type | Measurement | `OMOP:37208635` | `LOINC:73811-2` |
| EGFRCR71 | observation_type | Measurement | `OMOP:37208635` | `LOINC:65902-9` |
| EGFRCYSC51 | observation_type | Measurement | `OMOP:37208635` | `LOINC:73811-2` |
| EGFRCYSC61 | observation_type | Measurement | `OMOP:37208635` | `LOINC:73811-2` |
| EGFRCYSC71 | observation_type | Measurement | `OMOP:37208635` | `LOINC:73811-2` |
| EGFRCYSC_V2 | observation_type | Measurement | `OMOP:37208635` | `LOINC:9980-4` |
| EGFRCYSC_V4 | observation_type | Measurement | `OMOP:37208635` | `LOINC:9982-0` |
| EGFRCYSC_V5 | observation_type | Measurement | `OMOP:37208635` | `LOINC:10128-7` |
| EGFRSCRCYSC_V2 | observation_type | Measurement | `OMOP:37208635` | `LOINC:83021-6` |
| EGFRSCRCYSC_V4 | observation_type | Measurement | `OMOP:37208635` | `LOINC:103312-5` |
| EGFRSCRCYSC_V5 | observation_type | Measurement | `OMOP:37208635` | `LOINC:83038-0` |
| EGFRSCR_V1 | observation_type | Measurement | `OMOP:37208635` | `LOINC:9907-7` |
| EGFRSCR_V2 | observation_type | Measurement | `OMOP:37208635` | `LOINC:9908-5` |
| EGFRSCR_V4 | observation_type | Measurement | `OMOP:37208635` | `LOINC:9910-1` |
| EGFRSCR_V5 | observation_type | Measurement | `OMOP:37208635` | `LOINC:103346-3` |
| ERHA18 | observation_type | Measurement | `OMOP:4273023` | `LOINC:29669-9` |
| ERHA21 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ESMA141 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ESMA142 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ESMB141 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ESMB142 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ESMC141 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ESMC142 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ETLA26 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ETLB26 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ETLC26 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ETLD26 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| GLUCOS01 | observation_type | Measurement | `OBA:VT0000188` | `LOINC:59530-6` |
| GLUC_V1 | observation_type | Measurement | `OBA:VT0000188` | `LOINC:9967-1` |
| GLUC_V2 | observation_type | Measurement | `OBA:VT0000188` | `LOINC:10089-1` |
| GLUC_V3 | observation_type | Measurement | `OBA:VT0000188` | `LOINC:10090-9` |
| GLUC_V4 | observation_type | Measurement | `OBA:VT0000188` | `LOINC:10091-7` |
| GLUC_V5 | observation_type | Measurement | `OBA:VT0000188` | `LOINC:10092-5` |
| GLUSIU41 | observation_type | Measurement | `OMOP:4156660` | `LOINC:60965-1` |
| GLUSIU51 | observation_type | Measurement | `OMOP:4156660` | `LOINC:14771-0` |
| GLUSIU62 | observation_type | Measurement | `OMOP:4156660` | `LOINC:95102-0` |
| GLUSIU71 | observation_type | Measurement | `OBA:VT0000188` | `LOINC:105272-9` |
| GLUSIU72 | observation_type | Measurement | `OMOP:4156660` | `LOINC:95102-0` |
| HDL01 | observation_type | Measurement | `OBA:VT0000184` | `LOINC:50840-8` |
| HDLSIU51 | observation_type | Measurement | `OBA:VT0000184` | `LOINC:96596-2` |
| HDLSIU61 | observation_type | Measurement | `OBA:VT0000184` | `LOINC:9832-7` |
| HDLSIU71 | observation_type | Measurement | `OBA:VT0000184` | `LOINC:9832-7` |
| HDL_V1 | observation_type | Measurement | `OBA:VT0000184` | `LOINC:60962-8` |
| HDL_V2 | observation_type | Measurement | `OBA:VT0000184` | `LOINC:103280-4` |
| HDL_V3 | observation_type | Measurement | `OBA:VT0000184` | `LOINC:66863-2` |
| HDL_V4 | observation_type | Measurement | `OBA:VT0000184` | `LOINC:39099-7` |
| HDL_V5 | observation_type | Measurement | `OBA:VT0000184` | `LOINC:83038-0` |
| HEMA09 | observation_type | Measurement | `OBA:0000061` | `LOINC:3255-7` |
| HEMA11 | observation_type | Measurement | `OBA:2041535` | `LOINC:65644-7` |
| HEMA17 | observation_type | Measurement | `OBA:2052741` | `LOINC:41867-3` |
| HEMC01 | observation_type | Measurement | `OBA:2041535` | `LOINC:65644-7` |
| HEMC03 | observation_type | Measurement | `OBA:0000061` | `LOINC:3255-7` |
| HFAA18A | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| HFAA19A | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| HFAA19A1 | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| HFAA37A | observation_type | Measurement | `OBA:2060175` | `LOINC:718-7` |
| HFAA37B | observation_type | Measurement | `OBA:2060175` | `LOINC:718-7` |
| HFAA38A | observation_type | Measurement | `OBA:2045381` | `LOINC:4544-3` |
| HFAA38B | observation_type | Measurement | `OBA:2045381` | `LOINC:4544-3` |
| HFAA39A | observation_type | Measurement | `OBA:2045303` | `LOINC:69919-9` |
| HFAA39B | observation_type | Measurement | `OBA:2045303` | `LOINC:69919-9` |
| HFAA39C | observation_type | Measurement | `OBA:2045303` | `LOINC:75254-3` |
| HFAA40A | observation_type | Measurement | `OBA:2045303` | `LOINC:60502-2` |
| HFAA40B | observation_type | Measurement | `OBA:2045303` | `LOINC:60502-2` |
| HFAA40C | observation_type | Measurement | `OBA:2045303` | `LOINC:75254-3` |
| HFAA41A | observation_type | Measurement | `OMOP:4021291` | `LOINC:90112-4` |
| HFAA41B | observation_type | Measurement | `OMOP:4021291` | `LOINC:90112-4` |
| HFAA41C | observation_type | Measurement | `OMOP:4021291` | `LOINC:75254-3` |
| HFAA42A | observation_type | Measurement | `OMOP:4021291` | `LOINC:90112-4` |
| HFAA42B | observation_type | Measurement | `OMOP:4021291` | `LOINC:90112-4` |
| HFAA42C | observation_type | Measurement | `OMOP:4021291` | `LOINC:75254-3` |
| HFAA43A | observation_type | Measurement | `OBA:VT0001776` | `LOINC:75256-8` |
| HFAA43B | observation_type | Measurement | `OBA:VT0001776` | `LOINC:75256-8` |
| HFAA44A | observation_type | Measurement | `OBA:2050096` | `LOINC:60502-2` |
| HFAA44A1 | observation_type | Measurement | `OBA:2050096` | `LOINC:60502-2` |
| HFAA44B | observation_type | Measurement | `OBA:2050096` | `LOINC:75254-3` |
| HFAA44B1 | observation_type | Measurement | `OBA:2050096` | `LOINC:75254-3` |
| HFAA44C1 | observation_type | Measurement | `OBA:2050096` | `LOINC:75254-3` |
| HFAA50 | observation_type | Measurement | `OMOP:45772840` | `LOINC:1429-0` |
| HMTA01 | observation_type | Measurement | `OBA:2045381` | `LOINC:4544-3` |
| HMTA02 | observation_type | Measurement | `OBA:2060175` | `LOINC:718-7` |
| HMTA03 | observation_type | Measurement | `OBA:VT0000217` | `LOINC:48247-1` |
| HMTA04 | observation_type | Measurement | `OMOP:4267147` | `LOINC:777-3` |
| HMTA05 | observation_type | Measurement | `OMOP:37208698` | `LOINC:26499-4` |
| HMTA07 | observation_type | Measurement | `OMOP:37208690` | `LOINC:26474-7` |
| HMTB01 | observation_type | Measurement | `OBA:2045381` | `LOINC:4544-3` |
| HMTB02 | observation_type | Measurement | `OBA:2060175` | `LOINC:718-7` |
| HMTB03 | observation_type | Measurement | `OBA:VT0000217` | `LOINC:48247-1` |
| HMTB04 | observation_type | Measurement | `OMOP:4267147` | `LOINC:777-3` |
| HMTB05 | observation_type | Measurement | `OMOP:37208698` | `LOINC:26499-4` |
| HMTB07 | observation_type | Measurement | `OMOP:37208690` | `LOINC:26474-7` |
| HMTB13 | observation_type | Measurement | `OBA:0003460` | `LOINC:787-2` |
| HMTC10 | observation_type | Measurement | `OMOP:4267147` | `LOINC:777-3` |
| HMTC2 | observation_type | Measurement | `OBA:VT0000217` | `LOINC:63079-8` |
| HMTC3 | observation_type | Measurement | `OBA:VT0001586` | `LOINC:63201-8` |
| HMTC4 | observation_type | Measurement | `OBA:2060175` | `LOINC:718-7` |
| HMTC5 | observation_type | Measurement | `OBA:2045381` | `LOINC:4544-3` |
| HMTC6 | observation_type | Measurement | `OBA:0003460` | `LOINC:787-2` |
| HMTC7 | observation_type | Measurement | `OBA:2045301` | `LOINC:785-6` |
| HMTC8 | observation_type | Measurement | `OMOP:37393850` | `LOINC:786-4` |
| HMTC9 | observation_type | Measurement | `OMOP:37397924` | `LOINC:789-8` |
| HOM28 | observation_type | Measurement | `OMOP:4282779` | `LOINC:70805-7` |
| HOM30 | observation_type | Measurement | `OMOP:4282779` | `LOINC:2201-2` |
| HOM62 | observation_type | Measurement | `OMOP:4076114` | `LOINC:99946-6` |
| HRAA21D | observation_type | Measurement | `OMOP:4282779` | `LOINC:21793-5` |
| IFIA19B | observation_type | Measurement | `OMOP:4282779` | `LOINC:38865-2` |
| INSSIU01 | observation_type | Measurement | `OBA:2060174` | `LOINC:109075-2` |
| LANAAV45 | observation_type | Measurement | `OMOP:4138462` | `LOINC:77552-8` |
| LANAMX23 | observation_type | Measurement | `OMOP:4138462` | `LOINC:81265-1` |
| LANAMX45 | observation_type | Measurement | `OMOP:4138462` | `LOINC:81265-1` |
| LANBAV45 | observation_type | Measurement | `OMOP:4138462` | `LOINC:77552-8` |
| LANBMX23 | observation_type | Measurement | `OMOP:4138462` | `LOINC:81265-1` |
| LDL_V1 | observation_type | Measurement | `OBA:VT0000181` | `LOINC:60962-8` |
| LDL_V2 | observation_type | Measurement | `OBA:VT0000181` | `LOINC:60963-6` |
| LDL_V3 | observation_type | Measurement | `OBA:VT0000181` | `LOINC:60964-4` |
| LDL_V4 | observation_type | Measurement | `OBA:VT0000181` | `LOINC:60965-1` |
| LDL_V5 | observation_type | Measurement | `OBA:VT0000181` | `LOINC:60966-9` |
| LIP13 | observation_type | Measurement | `OBA:VT0000184` | `LOINC:96596-2` |
| LIP23 | observation_type | Measurement | `OMOP:4156660` | `LOINC:16913-6` |
| LIP3 | observation_type | Measurement | `OBA:VT0000180` | `LOINC:97075-6` |
| LIP33 | observation_type | Measurement | `OMOP:4208414` | `LOINC:76190-8` |
| LIP38 | observation_type | Measurement | `OMOP:4021291` | `LOINC:76190-8` |
| LIP43 | observation_type | Measurement | `OBA:2045303` | `LOINC:3269-8` |
| LIP8 | observation_type | Measurement | `OBA:VT0002644` | `LOINC:82665-1` |
| LIPA01 | observation_type | Measurement | `OBA:VT0000180` | `LOINC:75841-7` |
| LIPA02 | observation_type | Measurement | `OBA:VT0002644` | `LOINC:82665-1` |
| LIPB02A | observation_type | Measurement | `OBA:VT0002644` | `LOINC:12951-0` |
| LIPB03A | observation_type | Measurement | `OBA:VT0000184` | `LOINC:96596-2` |
| LIPC2A | observation_type | Measurement | `OBA:VT0002644` | `LOINC:12951-0` |
| LIPC3A | observation_type | Measurement | `OBA:VT0000184` | `LOINC:2085-9` |
| LIPC4A | observation_type | Measurement | `OBA:VT0000188` | `LOINC:105272-9` |
| LIPC5 | observation_type | Measurement | `OBA:VT0000181` | `LOINC:55440-2` |
| LIPD2A | observation_type | Measurement | `OBA:VT0002644` | `LOINC:12951-0` |
| LIPD3A | observation_type | Measurement | `OBA:VT0000184` | `LOINC:96596-2` |
| LIPD4A | observation_type | Measurement | `OMOP:4156660` | `LOINC:1557-8` |
| LIPD6A | observation_type | Measurement | `OBA:2050096` | `LOINC:34555-3` |
| LIPD7A | observation_type | Measurement | `OBA:2060174` | `LOINC:1986-9` |
| LIPD8 | observation_type | Measurement | `OBA:VT0000181` | `LOINC:91108-1` |
| LIPF1b | observation_type | Measurement | `OBA:VT0000180` | `LOINC:72636-4` |
| LIPF2b | observation_type | Measurement | `OBA:VT0000184` | `LOINC:96596-2` |
| LIPF3b | observation_type | Measurement | `OBA:VT0002644` | `LOINC:72636-4` |
| LIPF4b | observation_type | Measurement | `OBA:VT0000181` | `LOINC:91108-1` |
| LIPF6b | observation_type | Measurement | `OMOP:4208414` | `LOINC:71426-1` |
| LOPAAV45 | observation_type | Measurement | `OMOP:4138462` | `LOINC:77555-1` |
| LOPAMX23 | observation_type | Measurement | `OMOP:4138462` | `LOINC:81265-1` |
| LOPAMX45 | observation_type | Measurement | `OMOP:4138462` | `LOINC:81265-1` |
| LOPBAV45 | observation_type | Measurement | `OMOP:4138462` | `LOINC:77555-1` |
| LOPBMX23 | observation_type | Measurement | `OMOP:4138462` | `LOINC:81265-1` |
| LOPCMX23 | observation_type | Measurement | `OMOP:4138462` | `LOINC:104790-1` |
| LOPDAV45 | observation_type | Measurement | `OMOP:4138462` | `LOINC:77555-1` |
| LOPDMX23 | observation_type | Measurement | `OMOP:4138462` | `LOINC:81265-1` |
| LPOAAV45 | observation_type | Measurement | `OMOP:4138462` | `LOINC:77552-8` |
| LPOAMX23 | observation_type | Measurement | `OMOP:4138462` | `LOINC:81265-1` |
| LPOAMX45 | observation_type | Measurement | `OMOP:4138462` | `LOINC:81265-1` |
| LPOBAV45 | observation_type | Measurement | `OMOP:4138462` | `LOINC:77552-8` |
| LPOBMX23 | observation_type | Measurement | `OMOP:4138462` | `LOINC:81265-1` |
| PFTB03 | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| PFTB04 | observation_type | Measurement | `OBA:VT0001253` | `LOINC:30525-0` |
| PRO_BNP_V4 | observation_type | Measurement | `OBA:2045303` | `LOINC:103349-7` |
| PRO_BNP_V5 | observation_type | Measurement | `OBA:2045303` | `LOINC:18530-6` |
| PULB20 | observation_type | Measurement | `OBA:VT0001253` | `LOINC:30525-0` |
| PULB21 | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| PULB22 | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| PULP20 | observation_type | Measurement | `OBA:VT0001253` | `LOINC:30525-0` |
| PULP21 | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| PULP22 | observation_type | Measurement | `OBA:VT0001259` | `LOINC:29463-7` |
| PWV1 | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8867-4` |
| Potassium | observation_type | Measurement | `OBA:VT0002668` | `LOINC:57379-0` |
| RANAAV45 | observation_type | Measurement | `OMOP:4138462` | `LOINC:77559-3` |
| RANAMX23 | observation_type | Measurement | `OMOP:4138462` | `LOINC:81265-1` |
| RANAMX45 | observation_type | Measurement | `OMOP:4138462` | `LOINC:81265-1` |
| RANBAV45 | observation_type | Measurement | `OMOP:4138462` | `LOINC:77552-8` |
| RANBMX23 | observation_type | Measurement | `OMOP:4138462` | `LOINC:81265-1` |
| ROPAAV45 | observation_type | Measurement | `OMOP:4138462` | `LOINC:96917-0` |
| ROPAMX23 | observation_type | Measurement | `OMOP:4138462` | `LOINC:81265-1` |
| ROPAMX45 | observation_type | Measurement | `OMOP:4138462` | `LOINC:81265-1` |
| ROPBAV45 | observation_type | Measurement | `OMOP:4138462` | `LOINC:77552-8` |
| ROPBMX23 | observation_type | Measurement | `OMOP:4138462` | `LOINC:81265-1` |
| ROPCMX23 | observation_type | Measurement | `OMOP:4138462` | `LOINC:104790-1` |
| ROPDAV45 | observation_type | Measurement | `OMOP:4138462` | `LOINC:77552-8` |
| ROPDMX23 | observation_type | Measurement | `OMOP:4138462` | `LOINC:81265-1` |
| RPOAAV45 | observation_type | Measurement | `OMOP:4138462` | `LOINC:77559-3` |
| RPOAMX23 | observation_type | Measurement | `OMOP:4138462` | `LOINC:81265-1` |
| RPOAMX45 | observation_type | Measurement | `OMOP:4138462` | `LOINC:81265-1` |
| RPOBAV45 | observation_type | Measurement | `OMOP:4138462` | `LOINC:77552-8` |
| RPOBMX23 | observation_type | Measurement | `OMOP:4138462` | `LOINC:81265-1` |
| RSE21 | observation_type | Measurement | `OBA:2040171` | `LOINC:1167-6` |
| SBPC8 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| SBPD8 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| SCR_V1 | observation_type | Measurement | `OBA:2050096` | `LOINC:60962-8` |
| SCR_V2 | observation_type | Measurement | `OBA:2050096` | `LOINC:18563-7` |
| SCR_V4 | observation_type | Measurement | `OBA:2050096` | `LOINC:18577-7` |
| SCR_V5 | observation_type | Measurement | `OBA:2050096` | `LOINC:10008-1` |
| SODI | observation_type | Measurement | `OMOP:606729` | `LOINC:12907-2` |
| STRC53C1 | observation_type | Measurement | `OMOP:43021859` | `LOINC:94422-3` |
| STRC53D1 | observation_type | Measurement | `OMOP:43020498` | `LOINC:94422-3` |
| STRC63A1 | observation_type | Measurement | `OBA:2050096` | `LOINC:1017-3` |
| STRC63A3 | observation_type | Measurement | `OBA:2050096` | `LOINC:1017-3` |
| Sodium | observation_type | Measurement | `OBA:VT0001776` | `LOINC:12907-2` |
| TCHSIU01 | observation_type | Measurement | `OBA:VT0000180` | `LOINC:97075-6` |
| TCHSIU31 | observation_type | Measurement | `OBA:VT0000180` | `LOINC:97075-6` |
| TCHSIU41 | observation_type | Measurement | `OBA:VT0000180` | `LOINC:60965-1` |
| TCHSIU51 | observation_type | Measurement | `OBA:VT0000180` | `LOINC:97885-8` |
| TCHSIU61 | observation_type | Measurement | `OBA:VT0000180` | `LOINC:97885-8` |
| TCHSIU71 | observation_type | Measurement | `OBA:VT0000180` | `LOINC:112544-2` |
| TOTCHOL_V1 | observation_type | Measurement | `OBA:VT0000180` | `LOINC:18538-9` |
| TOTCHOL_V2 | observation_type | Measurement | `OBA:VT0000180` | `LOINC:103280-4` |
| TOTCHOL_V3 | observation_type | Measurement | `OBA:VT0000180` | `LOINC:84428-2` |
| TOTCHOL_V4 | observation_type | Measurement | `OBA:VT0000180` | `LOINC:36321-8` |
| TOTCHOL_V5 | observation_type | Measurement | `OBA:VT0000180` | `LOINC:103346-3` |
| TRGSIU01 | observation_type | Measurement | `OBA:VT0002644` | `LOINC:97075-6` |
| TRGSIU31 | observation_type | Measurement | `OBA:VT0002644` | `LOINC:14449-3` |
| TRGSIU41 | observation_type | Measurement | `OBA:VT0002644` | `LOINC:60965-1` |
| TRGSIU51 | observation_type | Measurement | `OBA:VT0002644` | `LOINC:69947-0` |
| TRGSIU61 | observation_type | Measurement | `OBA:VT0002644` | `LOINC:69947-0` |
| TRGSIU71 | observation_type | Measurement | `OBA:VT0002644` | `LOINC:69947-0` |
| TROP_V4 | observation_type | Measurement | `OMOP:4021291` | `LOINC:18577-7` |
| TROP_V5 | observation_type | Measurement | `OMOP:4021291` | `LOINC:9959-8` |
| V1AGE01 | observation_type | Measurement | `OMOP:4282779` | `LOINC:30525-0` |
| V1AGE01 | observation_type | Measurement | `OBA:VT0000188` | `LOINC:30525-0` |
| V3AGE31 | observation_type | Measurement | `OBA:VT0000184` | `LOINC:30525-0` |
| V4AGE41 | observation_type | Measurement | `OMOP:4156660` | `LOINC:30525-0` |
| V5AGE51 | observation_type | Measurement | `OMOP:36303297` | `LOINC:78025-4` |
| V6AGE61 | observation_type | Measurement | `OMOP:36303297` | `LOINC:78025-4` |
| V6IN129 | observation_type | Measurement | `OBA:VT0001253` | `LOINC:8302-2` |
| V7AGE71 | observation_type | Measurement | `OMOP:36303297` | `LOINC:76428-2` |
| ddimer | observation_type | Measurement | `OMOP:37393605` | `LOINC:38898-3` |
| ecg6 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| ecg7 | observation_type | Measurement | `OMOP:4274406` | `LOINC:46357-0` |
| ecg8 | observation_type | Measurement | `OBA:1001086` | `LOINC:8633-0` |
| ecg9 | observation_type | Measurement | `OMOP:4273023` | `LOINC:8636-3` |
| v1ecg6 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| v1ecg7 | observation_type | Measurement | `OMOP:4274406` | `LOINC:30636-5` |
| v1ecg8 | observation_type | Measurement | `OBA:1001086` | `LOINC:8633-0` |
| v1ecg9 | observation_type | Measurement | `OMOP:4273023` | `LOINC:8636-3` |
| v2ecg6 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| v2ecg7 | observation_type | Measurement | `OMOP:4274406` | `LOINC:30636-5` |
| v2ecg8 | observation_type | Measurement | `OBA:1001086` | `LOINC:8633-0` |
| v2ecg9 | observation_type | Measurement | `OMOP:4273023` | `LOINC:8636-3` |
| v3ecg6 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| v3ecg7 | observation_type | Measurement | `OMOP:4274406` | `LOINC:30636-5` |
| v3ecg8 | observation_type | Measurement | `OBA:1001086` | `LOINC:8633-0` |
| v3ecg9 | observation_type | Measurement | `OMOP:4273023` | `LOINC:8636-3` |
| v4ecg6 | observation_type | Measurement | `OBA:1001087` | `LOINC:8867-4` |
| v4ecg7 | observation_type | Measurement | `OMOP:4274406` | `LOINC:30636-5` |
| v4ecg8 | observation_type | Measurement | `OBA:1001086` | `LOINC:8633-0` |
| v4ecg9 | observation_type | Measurement | `OMOP:4273023` | `LOINC:8636-3` |

### Unverified Misalignments (120 — no YAML confirmation)

| Variable | Slot | Entity Type | CSV CURIE | Agent Suggestion |
| :---- | :---- | :---- | :---- | :---- |
| ABI20 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| ABI22 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| ABI23 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| ABI25 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| ABI26 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| ABI28 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| ABI29 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| ABI31 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| ABI4 | observations | Measurement | `OMOP:4152194` | `LOINC:30525-0` |
| BPUA02 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| BPUA03 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| BPUA05 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| BPUA06 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| BPUA08 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| BPUA09 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| BPUA11 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| BPUA12 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| BPUA14 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| BPUA15 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| BPUA17 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| BPUA18 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| BPUA20 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| BPUA21 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| BPUB02 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| BPUB03 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| BPUB05 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| BPUB06 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| BPUB08 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| BPUB09 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| BPUB11 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| BPUB12 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| BPUB14 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| BPUB15 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| BPUB17 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| BPUB18 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| BPUB20 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| BPUB21 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| ECHA1 | observations | Measurement | `OMOP:4152194` | `LOINC:30525-0` |
| ECHA7 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| ECHA8 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| FEF_122 | observations | Measurement | `OMOP:3002094` | `LOINC:20152-5` |
| FEV1FVC1 | observations | Measurement | `OMOP:3002094` | `LOINC:20152-5` |
| FEV_101 | observations | Measurement | `OMOP:3002094` | `LOINC:20154-1` |
| FVC01 | observations | Measurement | `OMOP:3002094` | `LOINC:20152-5` |
| FVC22 | observations | Measurement | `OMOP:3002094` | `LOINC:20152-5` |
| PFTA24 | observations | Measurement | `OMOP:3002094` | `LOINC:20152-5` |
| PFTA26 | observations | Measurement | `OMOP:3002094` | `LOINC:20156-6` |
| PFTA31 | observations | Measurement | `OMOP:3002094` | `LOINC:20152-5` |
| PFTB04 | observations | Measurement | `OMOP:3002094` | `LOINC:30525-0` |
| PFTB24 | observations | Measurement | `OMOP:3002094` | `LOINC:20152-5` |
| PFTB26 | observations | Measurement | `OMOP:3002094` | `LOINC:43261-7` |
| PFTB31 | observations | Measurement | `OMOP:3002094` | `LOINC:20152-5` |
| PPFEV151 | observations | Measurement | `OMOP:3002094` | `LOINC:20153-3` |
| PPFEV1FVC51 | observations | Measurement | `OMOP:3002094` | `LOINC:20150-9` |
| PPFVC51 | observations | Measurement | `OMOP:3002094` | `LOINC:20152-5` |
| PULB20 | observations | Measurement | `OMOP:3002094` | `LOINC:30525-0` |
| PULB27 | observations | Measurement | `OMOP:3002094` | `LOINC:20152-5` |
| PULB31 | observations | Measurement | `OMOP:3002094` | `LOINC:20150-9` |
| PULB38 | observations | Measurement | `OMOP:3002094` | `LOINC:20152-5` |
| PULB39 | observations | Measurement | `OMOP:3002094` | `LOINC:69970-2` |
| PULB41 | observations | Measurement | `OMOP:3002094` | `LOINC:20150-9` |
| PULP20 | observations | Measurement | `OMOP:3002094` | `LOINC:30525-0` |
| PULP27 | observations | Measurement | `OMOP:3002094` | `LOINC:20152-5` |
| PULP31 | observations | Measurement | `OMOP:3002094` | `LOINC:20150-9` |
| PULP38 | observations | Measurement | `OMOP:3002094` | `LOINC:20152-5` |
| PULP39 | observations | Measurement | `OMOP:3002094` | `LOINC:20154-1` |
| PULP41 | observations | Measurement | `OMOP:3002094` | `LOINC:20150-9` |
| SBP11 | observations | Measurement | `OMOP:4152194` | `LOINC:8867-4` |
| SBP12 | observations | Measurement | `OMOP:4152194` | `LOINC:8867-4` |
| SBP14 | observations | Measurement | `OMOP:4152194` | `LOINC:8867-4` |
| SBP15 | observations | Measurement | `OMOP:4152194` | `LOINC:8867-4` |
| SBP5 | observations | Measurement | `OMOP:4152194` | `LOINC:8867-4` |
| SBP6 | observations | Measurement | `OMOP:4152194` | `LOINC:8867-4` |
| SBP8 | observations | Measurement | `OMOP:4152194` | `LOINC:8867-4` |
| SBP9 | observations | Measurement | `OMOP:4152194` | `LOINC:8867-4` |
| SBPA12 | observations | Measurement | `OMOP:4152194` | `LOINC:75784-9` |
| SBPA13 | observations | Measurement | `OMOP:4152194` | `LOINC:75784-9` |
| SBPA15 | observations | Measurement | `OMOP:4152194` | `LOINC:54968-3` |
| SBPA16 | observations | Measurement | `OMOP:4152194` | `LOINC:80251-2` |
| SBPA17 | observations | Measurement | `OMOP:4152194` | `LOINC:80251-2` |
| SBPA18 | observations | Measurement | `OMOP:4152194` | `LOINC:54968-3` |
| SBPA19 | observations | Measurement | `OMOP:4152194` | `LOINC:54968-3` |
| SBPA20 | observations | Measurement | `OMOP:4152194` | `LOINC:64119-1` |
| SBPA21 | observations | Measurement | `OMOP:4152194` | `LOINC:62961-8` |
| SBPA22 | observations | Measurement | `OMOP:4152194` | `LOINC:54968-3` |
| SBPB12 | observations | Measurement | `OMOP:4152194` | `LOINC:18684-1` |
| SBPB13 | observations | Measurement | `OMOP:4152194` | `LOINC:18684-1` |
| SBPB15 | observations | Measurement | `OMOP:4152194` | `LOINC:18684-1` |
| SBPB16 | observations | Measurement | `OMOP:4152194` | `LOINC:18684-1` |
| SBPB18 | observations | Measurement | `OMOP:4152194` | `LOINC:54968-3` |
| SBPB19 | observations | Measurement | `OMOP:4152194` | `LOINC:45784-6` |
| SBPB21 | observations | Measurement | `OMOP:4152194` | `LOINC:62961-8` |
| SBPB22 | observations | Measurement | `OMOP:4152194` | `LOINC:62961-8` |
| SBPC13 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPC14 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| SBPC16 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPC17 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| SBPC19 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPC20 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| SBPC22 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPC23 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| SBPD13 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPD14 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| SBPD16 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPD17 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| SBPD19 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| SBPD20 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| UDTA05 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| UDTA06 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| UDTA07 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| UDTA08 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| UDTA09 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| UDTA10 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| UDTB05 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| UDTB06 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| UDTB07 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| UDTB08 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| UDTB09 | observations | Measurement | `OMOP:4152194` | `LOINC:8480-6` |
| UDTB10 | observations | Measurement | `OMOP:4152194` | `LOINC:8462-4` |
| V5AGE51 | observations | Measurement | `OMOP:3002094` | `LOINC:78025-4` |

## Vocab/Slot Validation

Agent suggestions suppressed as vocabulary/slot mismatches (evaluated but not surfaced as findings): **61**

| Slot | Invalid vocab proposed | Suppressed count | Rule |
| :---- | :---- | ----: | :---- |
| `observation_type` | LOINC | 61 | Valid: OBA, OMOP |
| **Total** | | **61** | |

_These are not errors — they confirm the existing CURIEs are correct for their slots. The agent proposed codes from a vocabulary the bdchm slot is not typed for (e.g. OMOP in a MONDO-typed slot, LOINC in an OBA-typed slot). See `_SLOT_VOCAB_RULES` in `generate_semantic_review.py` for the full rule definitions._

## Error Cases Requiring Fix

### Missing Agent Suggestions — 92 variable-slot pair(s)

These substantive variables received no suggestion from any agent.
Investigate whether a suitable ontology term exists or the slot routing needs updating.

| Variable | Slot | Entity Type | Description |
| :---- | :---- | :---- | :---- |
| CHEM10 | observation_type | Measurement | AALB - Albumin (for glycated alb) Numeric Value g/dL [Chemis |
| CHEM3 | observation_type | Measurement | UALB - Urine Albumin Numeric Value mg/L [Chemistry Lab, CHEM |
| HRAA43CC | observation_type | Measurement | Q43cc. Range 1: Upper Limit Normal: BNP pg/ml [Hospital Abst |
| HRAA56AB1 | observation_type | Measurement | Q56ab1. BNP First [Hospital Abstraction Form. HRA. Version F |
| HRAA56AB3 | observation_type | Measurement | Q56ab3. BNP Last (if more than one) [Hospital Abstraction Fo |
| HRAA56AB5 | observation_type | Measurement | Q56ab5. BNP Highest of remaining values [Hospital Abstractio |
| V6IN14 | observation_type | Measurement | CESD51 - CESD depression score V5 |
| HFAA9G | observation_type | Measurement | Q9G - Gen his: Ex-smoker [Heart Failure Hospital Record Abst |
| HHXB44 | observation_type | Measurement | [Smoking]. Have you ever smoked cigarettes? [Code No if less |
| HHXB45 | observation_type | Measurement | [Smoking]. Do you now smoke cigarettes? Q45 [Health/Medical  |
| PHXA25 | observation_type | Measurement | [Smoking]. Have you ever smoked cigarettes? Q25 [Personal Hi |
| PHXA27 | observation_type | Measurement | [Smoking]. Do you now smoke cigarettes? Q27 [Personal Histor |
| PHXB7 | observation_type | Measurement | [Smoking]. Have you ever smoked cigarettes? Q7 [Personal His |
| PHXB8 | observation_type | Measurement | [Smoking]. Do you now smoke cigarettes? Q8 [Personal History |
| HRAA43DD | observation_type | Measurement | Q43dd. Range 1: Upper Limit Normal: Serum Creatinine [Hospit |
| HRAA56AD1 | observation_type | Measurement | Q56ad1. Serum Creatinine First [Hospital Abstraction Form. H |
| HRAA56AD3 | observation_type | Measurement | Q56ad3. Serum Creatinine Second [Hospital Abstraction Form.  |
| HRAA56AD5 | observation_type | Measurement | Q56d5. Serum Creatinine Last [Hospital Abstraction Form. HRA |
| PHXA60 | observation_type | Measurement | [Occupation]. Please look at this card. Which of these incom |
| DTIA09 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIA10 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIA11 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIA12 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIA13 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIA14 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIB09 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIB10 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIB11 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIB12 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIB13 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIB14 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIC9 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIC10 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIC11 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIC12 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIC13 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIC14 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| GLUSIU01 | observation_type | Measurement | Recalibrated glucose in SI units [Cohort. Visit 1] |
| HDLSIU02 | observation_type | Measurement | Recalibrated HDL cholesterol in SI units [Cohort. Visit 1] |
| HDLSIU31 | observation_type | Measurement | Re-calibrated HDL cholesterol in mmol/L [Cohort. Visit 3] |
| HDLSIU41 | observation_type | Measurement | Re-Calibrated HDL Cholesterol In mmol/L [Derived Variable Da |
| CHEM1 | observation_type | Measurement | GLYHB - HbA1c Numeric Value % [Chemistry Lab, CHEM2] |
| ANT10b | observation_type | Measurement | Q10b. D. Body size. Hip girth [Anthropometry Form, ANT] |
| LIP18 | observation_type | Measurement | LDLCC cholesterol calculated [Central Lab Data] |
| LDL71 | observation_type | Measurement | Recalculated LDL Cholesterol [Visit 7/NCS Derived Variable D |
| LDL51 | observation_type | Measurement | Recalculated LDL Cholesterol [Cohort Visit Derived Variables |
| LDL61 | observation_type | Measurement | Recalculated LDL Cholesterol [4.2 - 390.8 ( median=95.4 mean |
| HFAA31B2 | observation_type | Measurement | Q31B2 - Rt.cath measures: Pulmonary arterial pressure(value) |
| HRAA43EE | observation_type | Measurement | Q43ee. Range 1: Upper Limit of Normal: Pro-BNP [Hospital Abs |
| HRAA56AG1 | observation_type | Measurement | Q56ag1. Pro-BNP: First Q56AG1 [Hospital Abstraction Form. HR |
| HRAA56AG3 | observation_type | Measurement | Q56ag3. Pro-BNP: Last(if more than one) QAG3 [Hospital Abstr |
| HRAA56AG5 | observation_type | Measurement | Q56ag5. Pro-BNP: Highest of remaining values QAG5 [Hospital  |
| MSCA4 | observation_type | Measurement | [Exclusion]. Do you have a cardiac pacemaker or a heart valv |
| DTIA15 | observation_type | Measurement | [Vegetables]. In the past year, how often on average did you |
| DTIA16 | observation_type | Measurement | [Vegetables]. In the past year, how often on average did you |
| DTIA17 | observation_type | Measurement | [Vegetables]. In the past year, how often on average did you |
| DTIA18 | observation_type | Measurement | [Vegetables]. In the past year, how often on average did you |
| DTIA19 | observation_type | Measurement | [Vegetables]. In the past year, how often on average did you |
| DTIA20 | observation_type | Measurement | [Vegetables]. In the past year, how often on average did you |
| DTIA21 | observation_type | Measurement | [Vegetables]. In the past year, how often on average did you |
| DTIA22 | observation_type | Measurement | [Vegetables]. In the past year, how often on average did you |
| DTIA23 | observation_type | Measurement | [Vegetables]. In the past year, how often on average did you |
| DTIA24 | observation_type | Measurement | [Vegetables]. In the past year, how often on average did you |
| DTIA25 | observation_type | Measurement | [Vegetables]. In the past year, how often on average did you |
| DTIB15 | observation_type | Measurement | [Vegetables]. In the past year, how often on average did you |
| DTIB16 | observation_type | Measurement | [Vegetables]. In the past year, how often on average did you |
| DTIB17 | observation_type | Measurement | [Vegetables]. In the past year, how often on average did you |
| DTIB18 | observation_type | Measurement | [Vegetables]. In the past year, how often on average did you |
| DTIB19 | observation_type | Measurement | [Vegetables]. In the past year, how often on average did you |
| DTIB20 | observation_type | Measurement | [Vegetables]. In the past year, how often on average did you |
| DTIB21 | observation_type | Measurement | [Vegetables]. In the past year, how often on average did you |
| DTIB22 | observation_type | Measurement | [Vegetables]. In the past year, how often on average did you |
| DTIB23 | observation_type | Measurement | [Vegetables]. In the past year, how often on average did you |
| DTIB24 | observation_type | Measurement | [Vegetables]. In the past year, how often on average did you |
| DTIB25 | observation_type | Measurement | [Vegetables]. In the past year, how often on average did you |
| DTIC15 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIC16 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIC17 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIC18 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIC19 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIC20 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIC21 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIC22 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIC23 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIC24 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| DTIC25 | observation_type | Measurement | [Fruits]. In the past year, how often on average did you con |
| WSTHPR01 | observation_type | Measurement | Waist-to-hip ratio [Cohort. Visit 1] |
| WSTHPR31 | observation_type | Measurement | Waist-to-hip ratio [Cohort. Visit 3] |
| WSTHPR71 | observation_type | Measurement | Waist-to-Hip Ratio [Visit 7/NCS Derived Variable Dataset. DE |
| WSTHPR41 | observation_type | Measurement | Waist-To-Hip Ratio [Derived Variable Dataset, visit 4] |
| WSTHPR51 | observation_type | Measurement | Waist-to-Hip Ratio [Cohort Visit Derived Variables. Visit 5] |
| WSTHPR61 | observation_type | Measurement | Waist-to-Hip Ratio [Cohort Visit Derived Variables. DERIVE61 |
