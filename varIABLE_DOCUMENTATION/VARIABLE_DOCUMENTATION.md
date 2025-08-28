# BDCHM Variable Documentation

## Demography

### Ethnicity

**Machine-readable name:** `ethnicity`

A person's cultural heritage or ancestry

**Properties:**
- **Datatype:** [EthnicityEnum](https://rtiinternational.github.io/NHLBI-BDC-DMC-HM/EthnicityEnum)
- **Unit:** NONE

**Ontology References:**
- **OMOP:** [OMOP:44803968](https://athena.ohdsi.org/search-terms/terms/44803968)

---

### Race

**Machine-readable name:** `race`

Self-reported category reflecting an individual's identity and social understanding of race in the United States

**Properties:**
- **Datatype:** [RaceEnum](https://rtiinternational.github.io/NHLBI-BDC-DMC-HM/RaceEnum)
- **Unit:** NONE

**Ontology References:**
- **OMOP:** [OMOP:4013886](https://athena.ohdsi.org/search-terms/terms/4013886)

---

### Sex

**Machine-readable name:** `sex`

Self-reported category reflecting an individual's biological sex and/or gender identity

**Properties:**
- **Datatype:** [SexEnum](https://rtiinternational.github.io/NHLBI-BDC-DMC-HM/SexEnum)
- **Unit:** NONE

**Ontology References:**
- **OMOP:** [OMOP:3046965](https://athena.ohdsi.org/search-terms/terms/3046965)

---

## MeasurementObservation

### 8-epi-PGF2a in urine

**Machine-readable name:** `isoprostane_8_epi_pgf2a`

Concentration of urinary 8-epi-prostaglandin F2 alpha

**Properties:**
- **Datatype:** decimal
- **Unit:** pg/mL
- **UCUM Unit:** pg/mL

**Ontology References:**
- **OMOP:** [OMOP:3011888](https://athena.ohdsi.org/search-terms/terms/3011888)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### Activity LP-PLA2 in blood

**Machine-readable name:** `lppla2_act`

Measurement of the activity of the Lp-PLA2 (lipoprotein-associated phospholipase A2) enzyme in serum or plasma. 

**Properties:**
- **Datatype:** decimal
- **Unit:** nmol/min/mL
- **UCUM Unit:** nmol/min/mL

**Ontology References:**
- **OMOP:** [OMOP:36305170](https://athena.ohdsi.org/search-terms/terms/36305170)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### AHI Apnea-Hypopnea Index

**Machine-readable name:** `apnea_hypop_index`

Measurement used to diagnose and assess the severity of sleep apnea. It is calculated by counting the number of apneas and hypopneas that occur per hour of sleep.

**Properties:**
- **Datatype:** decimal
- **Unit:** events/hr
- **UCUM Unit:** /h

**Ontology References:**
- **OMOP:** [OMOP:37396400](https://athena.ohdsi.org/search-terms/terms/37396400)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### Albumin creatinine ratio in urine

**Machine-readable name:** `albumin_creatinine`

Measurement of the ratio of albumin to creatinine in urine. Also known as uACR.

**Properties:**
- **Datatype:** decimal
- **Unit:** mg/g
- **UCUM Unit:** mg/g{creat}

**Ontology References:**
- **OMOP:** [OMOP:4154347](https://athena.ohdsi.org/search-terms/terms/4154347)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### Albumin in blood

**Machine-readable name:** `albumin_bld`

Measurement of albumin in blood serum

**Properties:**
- **Datatype:** decimal
- **Unit:** g/dL
- **UCUM Unit:** g/dL

**Ontology References:**
- **OMOP:** [OMOP:2212186](https://athena.ohdsi.org/search-terms/terms/2212186)
- **OBA:** [OBA:2050068](http://purl.obolibrary.org/obo/OBA_2050068)

---

### Alcohol

**Machine-readable name:** `alcohol_servings`

Servings of alcohol consumed per week

**Properties:**
- **Datatype:** integer
- **Unit:** servings per week
- **UCUM Unit:** {#}/wk

**Ontology References:**
- **OMOP:** [OMOP:35609491](https://athena.ohdsi.org/search-terms/terms/35609491)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### ALT SGPT

**Machine-readable name:** `alt_sgpt`

Concentration of ALT/SGPT in the blood. ALT, or alanine transaminase, is the same as SGPT, which stands for serum glutamic-pyruvic transaminase. Typically measured in serum or plasma.

**Properties:**
- **Datatype:** decimal
- **Unit:** IU/L
- **UCUM Unit:** [IU]/L

**Ontology References:**
- **OMOP:** [OMOP:4146380](https://athena.ohdsi.org/search-terms/terms/4146380)
- **OBA:** [OBA:2050062](http://purl.obolibrary.org/obo/OBA_2050062)

---

### AST SGOT

**Machine-readable name:** `ast_sgot`

Concentration of AST/SGOT in blood. AST (aspartate aminotransferase), also known as SGOT (Serum Glutamic Oxaloacetic Transaminase), is typically measured in serum or plasma.

**Properties:**
- **Datatype:** decimal
- **Unit:** IU/L
- **UCUM Unit:** [IU]/L

**Ontology References:**
- **OMOP:** [OMOP:4263457](https://athena.ohdsi.org/search-terms/terms/4263457)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### basophils count

**Machine-readable name:** `basophil_ncnc_bld`

Concentration of basophil cells in whole blood

**Properties:**
- **Datatype:** decimal
- **Unit:** x10E3/uL
- **UCUM Unit:** 10*3/uL

**Ontology References:**
- **OMOP:** [OMOP:3006315](https://athena.ohdsi.org/search-terms/terms/3006315)
- **OBA:** [OBA:VT0002607](http://purl.obolibrary.org/obo/OBA_VT0002607)

---

### Bilirubin Conjugated Direct

**Machine-readable name:** `bilirubin_con`

Concentration of conjugated (or direct) bilirubin in blood, typically measured in serum or plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** mg/dL
- **UCUM Unit:** mg/dL

**Ontology References:**
- **OMOP:** [OMOP:44805650](https://athena.ohdsi.org/search-terms/terms/44805650)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### Bilirubin total

**Machine-readable name:** `bilirubin_tot`

Concentration of total bilirubin in blood, typically measured in serum or plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** mg/dL
- **UCUM Unit:** mg/dL

**Ontology References:**
- **OMOP:** [OMOP:4230543](https://athena.ohdsi.org/search-terms/terms/4230543)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### Bilirubin Unconjugated Indirect

**Machine-readable name:** `bilirubin_uncon`

Concentration of unconjugated (or indirect) bilirubin in blood, typically measured in serum or plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** mg/dL
- **UCUM Unit:** mg/dL

**Ontology References:**
- **OMOP:** [OMOP:4018181](https://athena.ohdsi.org/search-terms/terms/4018181)
- **OBA:** [OBA:VT0001569](http://purl.obolibrary.org/obo/OBA_VT0001569)

---

### BMI

**Machine-readable name:** `bmi`

Also known as body mass index: ratio of a person's weight in kilos to the square of their height in meters

**Properties:**
- **Datatype:** decimal
- **Unit:** kg/m2
- **UCUM Unit:** kg/m2

**Ontology References:**
- **OMOP:** [OMOP:3038553](https://athena.ohdsi.org/search-terms/terms/3038553)
- **OBA:** [OBA:2045455](http://purl.obolibrary.org/obo/OBA_2045455)

---

### BNP

**Machine-readable name:** `bnp`

Concentration of BNP in blood, typically measured in plasma or whole blood. Also known as B-type natriuretic peptide, a hormone. 

**Properties:**
- **Datatype:** decimal
- **Unit:** pg/mL
- **UCUM Unit:** pg/mL

**Ontology References:**
- **OMOP:** [OMOP:4307029](https://athena.ohdsi.org/search-terms/terms/4307029)
- **OBA:** [OBA:2045303](http://purl.obolibrary.org/obo/OBA_2045303)

---

### Body weight

**Machine-readable name:** `bdy_wgt`

Mass of a person

**Properties:**
- **Datatype:** decimal
- **Unit:** kg
- **UCUM Unit:** kg

**Ontology References:**
- **OMOP:** [OMOP:4099154](https://athena.ohdsi.org/search-terms/terms/4099154)
- **OBA:** [OBA:VT0001259](http://purl.obolibrary.org/obo/OBA_VT0001259)

---

### BUN

**Machine-readable name:** `bun`

Concentration of blood urea nitrogen in blood, typically measured in serum or plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** mg/dL
- **UCUM Unit:** mg/dL

**Ontology References:**
- **OMOP:** [OMOP:4017361](https://athena.ohdsi.org/search-terms/terms/4017361)
- **OBA:** [OBA:VT0005265](http://purl.obolibrary.org/obo/OBA_VT0005265)

---

### BUN Creatinine ratio

**Machine-readable name:** `bun_creatinine`

Ratio of blood urea nitrogen (BUN) to creatinine in blood, typically measured in serum or plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** ratio
- **UCUM Unit:** {ratio}

**Ontology References:**
- **OMOP:** [OMOP:4112223](https://athena.ohdsi.org/search-terms/terms/4112223)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### c-reactive protein CRP

**Machine-readable name:** `crp`

Concentration of c-reactive protein (CRP) in blood, typically measured in serum or plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** mg/L
- **UCUM Unit:** mg/L

**Ontology References:**
- **OMOP:** [OMOP:4208414](https://athena.ohdsi.org/search-terms/terms/4208414)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### CAC Score

**Machine-readable name:** `cac_score`

The Coronary Artery Calcium Score is a measure of the amount of calcium in the arteries of the heart. Measured from a CT Scan.

**Properties:**
- **Datatype:** decimal
- **Unit:** Agatston unit
- **UCUM Unit:** {score}

**Ontology References:**
- **OMOP:** [OMOP:42872742](https://athena.ohdsi.org/search-terms/terms/42872742)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### CAC volume

**Machine-readable name:** `cac_volume`

Volume of coronarty artery calcium in the arteries of the heart. Measured by CT Scan.

**Properties:**
- **Datatype:** decimal
- **Unit:** Hounsfield units (HU)

**Ontology References:**
- **OMOP:** [OMOP:4166120](https://athena.ohdsi.org/search-terms/terms/4166120)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### Carotid IMT

**Machine-readable name:** `carotid_imt`

Carotid intima-media thickness (IMT) measures the thickness of the inner two layers (intima and media layers) of the carotid artery walls - there are many ways to take this measurement

**Properties:**
- **Datatype:** decimal
- **Unit:** mm
- **UCUM Unit:** mm

**Ontology References:**
- **OMOP:** [OMOP:4138462](https://athena.ohdsi.org/search-terms/terms/4138462)
- **OBA:** OBA_2050108 or OBA_2050107

---

### Carotid stenosis right

**Machine-readable name:** `carotid_sten_right`

**Properties:**
- **Datatype:** 
- **UCUM Unit:** %

**Ontology References:**
- **OMOP:** [OMOP:43021859](https://athena.ohdsi.org/search-terms/terms/43021859)

---

### Carotid stenosis left

**Machine-readable name:** `carotid_sten_left`

**Properties:**
- **Datatype:** 
- **UCUM Unit:** %

**Ontology References:**
- **OMOP:** [OMOP:43020498](https://athena.ohdsi.org/search-terms/terms/43020498)

---

### CD40 in blood

**Machine-readable name:** `cd40`

Concentration of CD40 (Cluster of differentiation antigen 40) in blood, typically measured in serum or plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** pg/mL
- **UCUM Unit:** pg/mL

**Ontology References:**
- **OMOP:** [OMOP:4209737](https://athena.ohdsi.org/search-terms/terms/4209737)
- **OBA:** [OBA:2052305](http://purl.obolibrary.org/obo/OBA_2052305)

---

### Chloride in blood

**Machine-readable name:** `chloride_bld`

Concentration of chloride in blood, also known as serum chloride

**Properties:**
- **Datatype:** decimal
- **Unit:** mmol/L
- **UCUM Unit:** mmol/L

**Ontology References:**
- **OMOP:** [OMOP:4188066](https://athena.ohdsi.org/search-terms/terms/4188066)
- **OBA:** [OBA:VT0003018](http://purl.obolibrary.org/obo/OBA_VT0003018)

---

### Creatinine in blood

**Machine-readable name:** `creat_bld`

Concentration of creatinine in blood, typically measured in serum or plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** mg/dL
- **UCUM Unit:** mg/dL

**Ontology References:**
- **OMOP:** [OMOP:2212294](https://athena.ohdsi.org/search-terms/terms/2212294)
- **OBA:** [OBA:2050096](http://purl.obolibrary.org/obo/OBA_2050096)

---

### Creatinine in urine

**Machine-readable name:** `creat_urin`

Concentration of creatinine in urine

**Properties:**
- **Datatype:** decimal
- **Unit:** mg/dL
- **UCUM Unit:** mg/dL

**Ontology References:**
- **OMOP:** [OMOP:3007081](https://athena.ohdsi.org/search-terms/terms/3007081)
- **OBA:** [OBA:VT0010540](http://purl.obolibrary.org/obo/OBA_VT0010540)

---

### Cystatin C in blood

**Machine-readable name:** `cysc_bld`

Concentration of cystatin C in blood, typically measured in serum or plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** mg/dL
- **UCUM Unit:** mg/dL

**Ontology References:**
- **OMOP:** [OMOP:4136584](https://athena.ohdsi.org/search-terms/terms/4136584)
- **OBA:** [OBA:2052375](http://purl.obolibrary.org/obo/OBA_2052375)

---

### D-Dimer

**Machine-readable name:** `d_dimer`

Concentration of D-dimer in blood, can be measured in whole blood or plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** mg/L FEU
- **UCUM Unit:** mg/L

**Ontology References:**
- **OMOP:** [OMOP:37393605](https://athena.ohdsi.org/search-terms/terms/37393605)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### Diastolic blood pressure

**Machine-readable name:** `bp_diastolic`

Measurement of pressure in your arteries when your heart is at rest between beats, the bottom number in a blood pressure reading

**Properties:**
- **Datatype:** decimal
- **Unit:** mmHg
- **UCUM Unit:** mm[Hg]

**Ontology References:**
- **OMOP:** [OMOP:4154790](https://athena.ohdsi.org/search-terms/terms/4154790)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### E-selectin in blood

**Machine-readable name:** `eselectin`

Concentration of E-selectin in blood, typically measured in serum or plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** ng/ML
- **UCUM Unit:** ng/mL

**Ontology References:**
- **OMOP:** [OMOP:3010372](https://athena.ohdsi.org/search-terms/terms/3010372)
- **OBA:** [OBA:2052778](http://purl.obolibrary.org/obo/OBA_2052778)

---

### EGFR

**Machine-readable name:** `egfr`

Stands for estimated glomerular filtration rate - calculated from creatinine concentration, age, sex, and body size. 

**Properties:**
- **Datatype:** decimal
- **Unit:** mL/min/1.73m2
- **UCUM Unit:** mL/min/{1.73_m2}

**Ontology References:**
- **OMOP:** [OMOP:37208635](https://athena.ohdsi.org/search-terms/terms/37208635)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### Eosinophils count

**Machine-readable name:** `eosinophil_ncnc_bld`

Concentration of eosinophil cells in whole blood

**Properties:**
- **Datatype:** decimal
- **Unit:** x10E3/uL
- **UCUM Unit:** 10*3/uL

**Ontology References:**
- **OMOP:** [OMOP:3013115](https://athena.ohdsi.org/search-terms/terms/3013115)
- **OBA:** [OBA:VT0002602](http://purl.obolibrary.org/obo/OBA_VT0002602)

---

### Erythrocyte Sed Rate

**Machine-readable name:** `ery_sed_rate`

Measurement of how quickly red blood cells (erythrocytes) settle to the bottom of a test tube in one hour. Also known as ESR

**Properties:**
- **Datatype:** decimal
- **Unit:** mm/hr
- **UCUM Unit:** mm/h

**Ontology References:**
- **OMOP:** [OMOP:4212065](https://athena.ohdsi.org/search-terms/terms/4212065)
- **OBA:** [OBA:2045235](http://purl.obolibrary.org/obo/OBA_2045235)

---

### Factor VII

**Machine-readable name:** `factor_7`

Concentration of Factor VII in blood, typically measured in plasma. Also known as FVII and proconvertin

**Properties:**
- **Datatype:** decimal
- **Unit:** % of normal
- **UCUM Unit:** %{Normal}

**Ontology References:**
- **OMOP:** [OMOP:4217630](https://athena.ohdsi.org/search-terms/terms/4217630)
- **OBA:** [OBA:2041535](http://purl.obolibrary.org/obo/OBA_2041535)

---

### Fasting blood glucose

**Machine-readable name:** `fast_gluc_bld`

Concentration of glucose in blood after not eating or drinking (except water) for a set period, typically 8-12 hours

**Properties:**
- **Datatype:** decimal
- **Unit:** mg/dL
- **UCUM Unit:** mg/dL

**Ontology References:**
- **OMOP:** [OMOP:4156660](https://athena.ohdsi.org/search-terms/terms/4156660)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### Ferritin

**Machine-readable name:** `ferritin`

Concentration of ferritin in blood, typically measured in serum or plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** ng/mL
- **UCUM Unit:** ng/mL

**Ontology References:**
- **OMOP:** [OMOP:4176561](https://athena.ohdsi.org/search-terms/terms/4176561)
- **OBA:** [OBA:VT0010513](http://purl.obolibrary.org/obo/OBA_VT0010513)

---

### FEV1 - Forced Expiratory Volume in 1 sec

**Machine-readable name:** `fev1`

Volume of air a person can exhale forcefully in one second, measured before the administration of bronchodilator medication

**Properties:**
- **Datatype:** decimal
- **Unit:** L
- **UCUM Unit:** L

**Ontology References:**
- **OMOP:** [OMOP:4241837](https://athena.ohdsi.org/search-terms/terms/4241837)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### FEV1 FVC

**Machine-readable name:** `fev1_fvc`

Ratio of the volume of air a person can exhale forcefully in one second (FEV1) to the total volume of air a person can exhale from their lungs after taking the deepest possible breath and then exhaling as forcefully and as completely as possible (FVC), measured before the administration of bronchodilator medication

**Properties:**
- **Datatype:** decimal
- **Unit:** ratio
- **UCUM Unit:** {ratio}

**Ontology References:**
- **OMOP:** [OMOP:3011505](https://athena.ohdsi.org/search-terms/terms/3011505)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### Fibrinogen

**Machine-readable name:** `fibrin`

Concentration of fibrinogen in blood, typically measured in plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** mg/dL
- **UCUM Unit:** mg/dL

**Ontology References:**
- **OMOP:** [OMOP:4094436](https://athena.ohdsi.org/search-terms/terms/4094436)
- **OBA:** [OBA:0000061](http://purl.obolibrary.org/obo/OBA_0000061)

---

### Fruits

**Machine-readable name:** `fruit_serving`

Servings of fruits consumed per week (includes fruit and fruit juice)

**Properties:**
- **Datatype:** integer
- **Unit:** servings per week
- **UCUM Unit:** {#}/wk

**Ontology References:**
- **OMOP:** [OMOP:21493059](https://athena.ohdsi.org/search-terms/terms/21493059)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### FVC - Forced Vital Capacity

**Machine-readable name:** `fvc`

Total volume of air a person can exhale from their lungs after taking the deepest possible breath and then exhaling as forcefully and as completely as possible, measured before the administration of bronchodilator medication

**Properties:**
- **Datatype:** decimal
- **Unit:** L
- **UCUM Unit:** L

**Ontology References:**
- **OMOP:** [OMOP:4176265](https://athena.ohdsi.org/search-terms/terms/4176265)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### GFR

**Machine-readable name:** `gfr`

Stands for glomerular filtration rate: a measure of how much blood passes through the glomeruli

**Properties:**
- **Datatype:** decimal
- **Unit:** mL/min/1.73 m2
- **UCUM Unit:** mL/min/{1.73_m2}

**Ontology References:**
- **OMOP:** [OMOP:4213477](https://athena.ohdsi.org/search-terms/terms/4213477)
- **OBA:** [OBA:0003747](http://purl.obolibrary.org/obo/OBA_0003747)

---

### Glucose in blood

**Machine-readable name:** `glucose_bld`

Concentration of glucose in blood, can be measured in whole blood, serum, or plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** mg/dL
- **UCUM Unit:** mg/dL

**Ontology References:**
- **OMOP:** [OMOP:4149519](https://athena.ohdsi.org/search-terms/terms/4149519)
- **OBA:** [OBA:VT0000188](http://purl.obolibrary.org/obo/OBA_VT0000188)

---

### HDL

**Machine-readable name:** `hdl`

Concentration of high-density lipoprotein (HDL) in blood, typically measured in serum

**Properties:**
- **Datatype:** decimal
- **Unit:** mg/dL
- **UCUM Unit:** mg/dL

**Ontology References:**
- **OMOP:** [OMOP:4076704](https://athena.ohdsi.org/search-terms/terms/4076704)
- **OBA:** [OBA:VT0000184](http://purl.obolibrary.org/obo/OBA_VT0000184)

---

### Heart rate

**Machine-readable name:** `hrtrt`

Number of times a heart beats per minute - also known as pulse rate

**Properties:**
- **Datatype:** integer
- **Unit:** bpm
- **UCUM Unit:** {beats}/min

**Ontology References:**
- **OMOP:** [OMOP:3027018](https://athena.ohdsi.org/search-terms/terms/3027018)
- **OBA:** [OBA:1001087](http://purl.obolibrary.org/obo/OBA_1001087)

---

### Height

**Machine-readable name:** `bdy_hgt`

Measure of the vertical distance of a standing person from head to foot

**Properties:**
- **Datatype:** decimal
- **Unit:** cm
- **UCUM Unit:** cm

**Ontology References:**
- **OMOP:** [OMOP:607590](https://athena.ohdsi.org/search-terms/terms/607590)
- **OBA:** [OBA:VT0001253](http://purl.obolibrary.org/obo/OBA_VT0001253)

---

### Hematocrit

**Machine-readable name:** `hemat`

The percentage of whole blood volume that consists of red blood cells - also known as packed cell volume (PCV)

**Properties:**
- **Datatype:** decimal
- **Unit:** percent
- **UCUM Unit:** %

**Ontology References:**
- **OMOP:** [OMOP:4151358](https://athena.ohdsi.org/search-terms/terms/4151358)
- **OBA:** [OBA:2045381](http://purl.obolibrary.org/obo/OBA_2045381)

---

### Hemoglobin

**Machine-readable name:** `hemo`

Concentration of hemoglobin (Hb) in whole blood

**Properties:**
- **Datatype:** decimal
- **Unit:** g/dL
- **UCUM Unit:** g/dL

**Ontology References:**
- **OMOP:** [OMOP:4094758](https://athena.ohdsi.org/search-terms/terms/4094758)
- **OBA:** [OBA:2060175](http://purl.obolibrary.org/obo/OBA_2060175)

---

### Hemoglobin A1c

**Machine-readable name:** `hemo_a1c`

Percentage of hemoglobin in your red blood cells that has glucose attached to it. Also known as HbA1c

**Properties:**
- **Datatype:** decimal
- **Unit:** percent
- **UCUM Unit:** %

**Ontology References:**
- **OMOP:** [OMOP:4184637](https://athena.ohdsi.org/search-terms/terms/4184637)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### Hip circumference

**Machine-readable name:** `hip_circ`

Distance measurement taken around the fullest part of the hips

**Properties:**
- **Datatype:** decimal
- **Unit:** cm
- **UCUM Unit:** cm

**Ontology References:**
- **OMOP:** [OMOP:4111665](https://athena.ohdsi.org/search-terms/terms/4111665)
- **OBA:** [OBA:1000032](http://purl.obolibrary.org/obo/OBA_1000032)

---

### ICAM1 in blood

**Machine-readable name:** `icam`

Concentration of Intercellular adhesion molecule 1 (ICAM-1) in blood, typically measured in serum or plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** ng/ML
- **UCUM Unit:** ng/mL

**Ontology References:**
- **OMOP:** [OMOP:4284103](https://athena.ohdsi.org/search-terms/terms/4284103)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### Insulin in blood

**Machine-readable name:** `insulin_blood`

Concentration of insulin in blood, typically measured in serum or plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** pmol/L
- **UCUM Unit:** pmol/L

**Ontology References:**
- **OMOP:** [OMOP:4060873](https://athena.ohdsi.org/search-terms/terms/4060873)
- **OBA:** [OBA:2060174](http://purl.obolibrary.org/obo/OBA_2060174)

---

### Interleukin 1 beta in blood

**Machine-readable name:** `il1_beta`

Concentration of Interleukin-1 beta (IL-1β) in blood, typically measured in serum or plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** pg/mL
- **UCUM Unit:** pg/mL

**Ontology References:**
- **OMOP:** [OMOP:3001804](https://athena.ohdsi.org/search-terms/terms/3001804)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### Interleukin 10 in blood

**Machine-readable name:** `il10`

Concentration of Interleukin-1 beta (IL-10) in blood, typically measured in serum or plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** pg/mL
- **UCUM Unit:** pg/mL

**Ontology References:**
- **OMOP:** [OMOP:3004578](https://athena.ohdsi.org/search-terms/terms/3004578)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### Interleukin 18 in blood

**Machine-readable name:** `il18`

Concentration of Interleukin-1 beta (IL-18) in blood, typically measured in serum or plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** pg/mL
- **UCUM Unit:** pg/mL

**Ontology References:**
- **OMOP:** [OMOP:3043144](https://athena.ohdsi.org/search-terms/terms/3043144)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### interleukin 6 in blood

**Machine-readable name:** `il6`

Concentration of Interleukin-1 beta (IL-6) in blood, typically measured in serum or plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** pg/mL
- **UCUM Unit:** pg/mL

**Ontology References:**
- **OMOP:** [OMOP:4332015](https://athena.ohdsi.org/search-terms/terms/4332015)
- **OBA:** [OBA:2052890](http://purl.obolibrary.org/obo/OBA_2052890)

---

### Lactate Dehydrogenase LDH

**Machine-readable name:** `lactate_dehyd`

Concentration of lactate dehydrogenase (LDH) in blood, typically in serum or plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** U/L

**Ontology References:**
- **OMOP:** [OMOP:4012918](https://athena.ohdsi.org/search-terms/terms/4012918)
- **OBA:** [OBA:VT0010477](http://purl.obolibrary.org/obo/OBA_VT0010477)

---

### Lactate in blood

**Machine-readable name:** `lactate_blood`

Concentration of lactate in blood, typically measured in whole blood or plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** mmol/L

**Ontology References:**
- **OMOP:** [OMOP:1246795](https://athena.ohdsi.org/search-terms/terms/1246795)
- **OBA:** [OBA:VT0010616](http://purl.obolibrary.org/obo/OBA_VT0010616)

---

### LDL

**Machine-readable name:** `ldl`

Concentration of low-density lipoprotein (LDL) in blood, typically measured in serum

**Properties:**
- **Datatype:** decimal
- **Unit:** mg/dL
- **UCUM Unit:** mg/dL

**Ontology References:**
- **OMOP:** [OMOP:4331302](https://athena.ohdsi.org/search-terms/terms/4331302)
- **OBA:** [OBA:VT0000181](http://purl.obolibrary.org/obo/OBA_VT0000181)

---

### Lymphocytes count

**Machine-readable name:** `lympho_ct`

Concentration of lymphocytes in whole blood

**Properties:**
- **Datatype:** decimal
- **Unit:** x10E3/uL
- **UCUM Unit:** 10*3/uL

**Ontology References:**
- **OMOP:** [OMOP:37208689](https://athena.ohdsi.org/search-terms/terms/37208689)
- **OBA:** [OBA:VT0000217](http://purl.obolibrary.org/obo/OBA_VT0000217)

---

### Lymphocytes percent

**Machine-readable name:** `lympho_pct`

Percent of total leukocytes that are lymphocytes

**Properties:**
- **Datatype:** decimal
- **Unit:** percent of total leukocytes
- **UCUM Unit:** %

**Ontology References:**
- **OMOP:** [OMOP:37208690](https://athena.ohdsi.org/search-terms/terms/37208690)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### Mass LP-PLA2 in blood

**Machine-readable name:** `lppla2_mass`

Concentration of Lp-PLA2 (lipoprotein-associated phospholipase A2) enzyme in serum or plasma.

**Properties:**
- **Datatype:** decimal
- **Unit:** ng/mL
- **UCUM Unit:** ng/mL

**Ontology References:**
- **OMOP:** [OMOP:3041450](https://athena.ohdsi.org/search-terms/terms/3041450)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### MCP1 in blood

**Machine-readable name:** `mcp1`

Concentration of Monocyte Chemoattractant Protein-1 (MCP-1), also known as CCL2, in blood, typically in serum or plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** pg/mL
- **UCUM Unit:** pg/mL

**Ontology References:**
- **OMOP:** [OMOP:1617307](https://athena.ohdsi.org/search-terms/terms/1617307)
- **OBA:** [OBA:2052436](http://purl.obolibrary.org/obo/OBA_2052436)

---

### Mean arterial pressure

**Machine-readable name:** `mn_art_pres`

Average pressure in your arteries throughout one complete cardiac cycle, also known as MAP

**Properties:**
- **Datatype:** decimal
- **Unit:** mmHg
- **UCUM Unit:** mm[Hg]

**Ontology References:**
- **OMOP:** [OMOP:37168599](https://athena.ohdsi.org/search-terms/terms/37168599)
- **OBA:** [OBA:VT2000000](http://purl.obolibrary.org/obo/OBA_VT2000000)

---

### mean corpuscular hemoglobin

**Machine-readable name:** `mch`

Average amount of hemoglobin in each red blood cell, also known as MCH

**Properties:**
- **Datatype:** decimal
- **Unit:** pg/cell
- **UCUM Unit:** pg/{cell}

**Ontology References:**
- **OMOP:** [OMOP:37398674](https://athena.ohdsi.org/search-terms/terms/37398674)
- **OBA:** [OBA:2045301](http://purl.obolibrary.org/obo/OBA_2045301)

---

### mean corpuscular hemoglobin concentration

**Machine-readable name:** `mchc`

Average concentration of hemoglobin within a single red blood cell, also known as MCHC

**Properties:**
- **Datatype:** decimal
- **Unit:** g/dL
- **UCUM Unit:** g/dL

**Ontology References:**
- **OMOP:** [OMOP:37393850](https://athena.ohdsi.org/search-terms/terms/37393850)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### mean corpuscular volume

**Machine-readable name:** `mcv`

Average size/volume of a red blood cell, also known as MCV

**Properties:**
- **Datatype:** decimal
- **Unit:** fL
- **UCUM Unit:** fL

**Ontology References:**
- **OMOP:** [OMOP:37393851](https://athena.ohdsi.org/search-terms/terms/37393851)
- **OBA:** [OBA:0003460](http://purl.obolibrary.org/obo/OBA_0003460)

---

### mean platelet volume

**Machine-readable name:** `pmv`

Average size/volume of a platelet, also known as MPV

**Properties:**
- **Datatype:** decimal
- **Unit:** fL
- **UCUM Unit:** fL

**Ontology References:**
- **OMOP:** [OMOP:37397923](https://athena.ohdsi.org/search-terms/terms/37397923)
- **OBA:** [OBA:0003277](http://purl.obolibrary.org/obo/OBA_0003277)

---

### MMP9 in blood

**Machine-readable name:** `mmp9`

Concentration of Matrix Metalloproteinase-9 (MMP-9) in blood, typically measured in serum or plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** ng/mL
- **UCUM Unit:** ng/mL

**Ontology References:**
- **OMOP:** [OMOP:40761106](https://athena.ohdsi.org/search-terms/terms/40761106)
- **OBA:** [OBA:2052397](http://purl.obolibrary.org/obo/OBA_2052397)

---

### Myeloperoxidase in blood

**Machine-readable name:** `mpo`

Concentration of Myeloperoxidase (MPO) in blood, typically measured in plasma or serum

**Properties:**
- **Datatype:** decimal
- **Unit:** ng/mL
- **UCUM Unit:** ng/mL

**Ontology References:**
- **OMOP:** [OMOP:1988928](https://athena.ohdsi.org/search-terms/terms/1988928)
- **OBA:** [OBA:2052389](http://purl.obolibrary.org/obo/OBA_2052389)

---

### Neutrophils count

**Machine-readable name:** `neutro_ct`

Concentration of neutrophil cells in whole blood

**Properties:**
- **Datatype:** decimal
- **Unit:** x10E3/uL
- **UCUM Unit:** 10*3/uL

**Ontology References:**
- **OMOP:** [OMOP:37208699](https://athena.ohdsi.org/search-terms/terms/37208699)
- **OBA:** [OBA:VT0000222](http://purl.obolibrary.org/obo/OBA_VT0000222)

---

### Neutrophils percent

**Machine-readable name:** `neutro_pct`

Percent of total leukocytes that are neutrophils

**Properties:**
- **Datatype:** decimal
- **Unit:** percent of total leukocytes
- **UCUM Unit:** %

**Ontology References:**
- **OMOP:** [OMOP:37208698](https://athena.ohdsi.org/search-terms/terms/37208698)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### NT pro BNP

**Machine-readable name:** `nt_bnp`

Concentration of NT-proBNP in blood, typically measured in serum or plasma. Also known as N-terminal prohormone of brain natriuretic peptide

**Properties:**
- **Datatype:** decimal
- **Unit:** pg/mL
- **UCUM Unit:** pg/mL

**Ontology References:**
- **OMOP:** [OMOP:4189511](https://athena.ohdsi.org/search-terms/terms/4189511)
- **OBA:** [OBA:2045303](http://purl.obolibrary.org/obo/OBA_2045303)

---

### Osteoprotegerin in blood

**Machine-readable name:** `opg`

Concentration of Osteoprotegerin (OPG) in blood, typically measured in serum or plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** ng/mL
- **UCUM Unit:** ng/mL

**Ontology References:**
- **OMOP:** [OMOP:1552124](https://athena.ohdsi.org/search-terms/terms/1552124)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### P-selectin in blood

**Machine-readable name:** `pselectin`

Concentration of P-selectin in blood, typicall measured in plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** ng/mL
- **UCUM Unit:** ng/mL

**Ontology References:**
- **OMOP:** [OMOP:3007356](https://athena.ohdsi.org/search-terms/terms/3007356)
- **OBA:** [OBA:2052701](http://purl.obolibrary.org/obo/OBA_2052701)

---

### pH of blood

**Machine-readable name:** `ph_blood`

pH of whole blood

**Properties:**
- **Datatype:** decimal
- **Unit:** pH
- **UCUM Unit:** [pH]

**Ontology References:**
- **OMOP:** [OMOP:3010421](https://athena.ohdsi.org/search-terms/terms/3010421)
- **OBA:** [OBA:2045409](http://purl.obolibrary.org/obo/OBA_2045409)

---

### Platelet count

**Machine-readable name:** `platelet_ct`

Concentration of platelets in whole blood

**Properties:**
- **Datatype:** decimal
- **Unit:** x10E3/uL
- **UCUM Unit:** 10*3/uL

**Ontology References:**
- **OMOP:** [OMOP:4267147](https://athena.ohdsi.org/search-terms/terms/4267147)
- **OBA:** Same as platelet quantity?

---

### Potassium in blood

**Machine-readable name:** `potassium`

Concentration of potassium in blood, typically measured in whole blood or serum

**Properties:**
- **Datatype:** decimal
- **Unit:** mmol/L
- **UCUM Unit:** mmol/L

**Ontology References:**
- **OMOP:** [OMOP:4245152](https://athena.ohdsi.org/search-terms/terms/4245152)
- **OBA:** [OBA:VT0002668](http://purl.obolibrary.org/obo/OBA_VT0002668)

---

### PR interval

**Machine-readable name:** `pr_ekg`

Time it takes for electrical impulses to travel from the atria to the ventricles of the heart. Measured using ECG/EKG

**Properties:**
- **Datatype:** decimal
- **Unit:** ms
- **UCUM Unit:** ms

**Ontology References:**
- **OMOP:** [OMOP:4274406](https://athena.ohdsi.org/search-terms/terms/4274406)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### Procalcitonin

**Machine-readable name:** `procal`

Concentration of procalcitonin (PCT) in blood, can be measured in serum, plasma, or whole blood

**Properties:**
- **Datatype:** decimal
- **Unit:** ng/mL
- **UCUM Unit:** ng/mL

**Ontology References:**
- **OMOP:** [OMOP:44791466](https://athena.ohdsi.org/search-terms/terms/44791466)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### QRS interval

**Machine-readable name:** `qrs_ekg`

Time that elapses from the beginning of the Q wave to the end of the S wave. Measured using ECG/EKG

**Properties:**
- **Datatype:** decimal
- **Unit:** ms
- **UCUM Unit:** ms

**Ontology References:**
- **OMOP:** [OMOP:4273021](https://athena.ohdsi.org/search-terms/terms/4273021)
- **OBA:** [OBA:1001086](http://purl.obolibrary.org/obo/OBA_1001086)

---

### QT interval

**Machine-readable name:** `qt_ekg`

Time it takes for the ventricles of the heart to depolarize and repolarize. Measured using ECG/EKG

**Properties:**
- **Datatype:** decimal
- **Unit:** ms
- **UCUM Unit:** ms

**Ontology References:**
- **OMOP:** [OMOP:4273023](https://athena.ohdsi.org/search-terms/terms/4273023)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### Red blood cell count

**Machine-readable name:** `rdbld_ct`

Concentration of red blood cells in whole blood

**Properties:**
- **Datatype:** decimal
- **Unit:** millions/uL
- **UCUM Unit:** 10*6/uL

**Ontology References:**
- **OMOP:** [OMOP:4030871](https://athena.ohdsi.org/search-terms/terms/4030871)
- **OBA:** [OBA:VT0001586](http://purl.obolibrary.org/obo/OBA_VT0001586)

---

### Red cell distribution width

**Machine-readable name:** `rdw`

Measure of the variation in the size and volume of red blood cells, also known as RDW. SD or CV?

**Properties:**
- **Datatype:** decimal
- **Unit:** %
- **UCUM Unit:** %

**Ontology References:**
- **OMOP:** [OMOP:37397924](https://athena.ohdsi.org/search-terms/terms/37397924)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### Respiratory rate

**Machine-readable name:** `resp_rt`

Number of breaths a person takes in one minute

**Properties:**
- **Datatype:** decimal
- **Unit:** breaths/min

**Ontology References:**
- **OMOP:** [OMOP:4313591](https://athena.ohdsi.org/search-terms/terms/4313591)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### Sleep hours

**Machine-readable name:** `sleep_duration_daily`

Cumulative amount of time spent sleeping each night

**Properties:**
- **Datatype:** decimal
- **Unit:** hours
- **UCUM Unit:** h

**Ontology References:**
- **OMOP:** [OMOP:40768653](https://athena.ohdsi.org/search-terms/terms/40768653)
- **OBA:** [OBA:2040171](http://purl.obolibrary.org/obo/OBA_2040171)

---

### Sodium in blood

**Machine-readable name:** `sodium_blood`

Concentration of sodium in blood, typically measured in serum or plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** mmol/L

**Ontology References:**
- **OMOP:** [OMOP:4097430](https://athena.ohdsi.org/search-terms/terms/4097430)
- **OBA:** [OBA:VT0001776](http://purl.obolibrary.org/obo/OBA_VT0001776)

---

### Sodium intake

**Machine-readable name:** `sodium_intak`

Mass of sodium consumed by an individual per day

**Properties:**
- **Datatype:** decimal
- **Unit:** mg/day
- **UCUM Unit:** mg/d

**Ontology References:**
- **OMOP:** [OMOP:606729](https://athena.ohdsi.org/search-terms/terms/606729)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### SpO2

**Machine-readable name:** `spo2`

Percentage of oxygen-carrying hemoglobin in the blood compared to the total amount of hemoglobin. Also known as oxygen saturation.

**Properties:**
- **Datatype:** decimal
- **Unit:** percent
- **UCUM Unit:** %

**Ontology References:**
- **OMOP:** [OMOP:4020553](https://athena.ohdsi.org/search-terms/terms/4020553)
- **OBA:** [OBA:2045443](http://purl.obolibrary.org/obo/OBA_2045443)

---

### Temperature

**Machine-readable name:** `bdy_temp`

An individual's internal body temperature

**Properties:**
- **Datatype:** decimal
- **Unit:** C
- **UCUM Unit:** Cel

**Ontology References:**
- **OMOP:** [OMOP:4302666](https://athena.ohdsi.org/search-terms/terms/4302666)
- **OBA:** [OBA:VT0005535](http://purl.obolibrary.org/obo/OBA_VT0005535)

---

### TNFa in blood

**Machine-readable name:** `tnfa`

Concentration of TNF in blood, typically measured in serum or plasma. Also known as TNF-alpha, TNFα,  and tumor necrosis factor

**Properties:**
- **Datatype:** decimal
- **Unit:** pg/mL
- **UCUM Unit:** pg/mL

**Ontology References:**
- **OMOP:** [OMOP:3004282](https://athena.ohdsi.org/search-terms/terms/3004282)
- **OBA:** [OBA:2051979](http://purl.obolibrary.org/obo/OBA_2051979)

---

### TNFa-R1 in blood

**Machine-readable name:** `tnfa_r1`

Concentration of TNF receptor 1  in blood, typically measured in serum or plasma. Also known as TNFR1, TNFRSF1A, CD120a, and tumor necrosis factor receptor 1

**Properties:**
- **Datatype:** decimal
- **Unit:** ng/mL
- **UCUM Unit:** pg/mL

**Ontology References:**
- **OMOP:** [OMOP:46235360](https://athena.ohdsi.org/search-terms/terms/46235360)
- **OBA:** [OBA:2051975](http://purl.obolibrary.org/obo/OBA_2051975)

---

### TNFR2 in blood

**Machine-readable name:** `tnfr2`

Concentration of TNFR2 in blood, typically measured in serum or plasma. Also known as tumor Necrosis Factor Receptor 2

**Properties:**
- **Datatype:** decimal
- **Unit:** ng/mL

**Ontology References:**
- **OMOP:** [OMOP:37543055](https://athena.ohdsi.org/search-terms/terms/37543055)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### Total cholesterol in blood

**Machine-readable name:** `tot_chol_bld`

Concentration of all cholesterol in your blood, including both HDL and LDL

**Properties:**
- **Datatype:** decimal
- **Unit:** mg/dL
- **UCUM Unit:** mg/dL

**Ontology References:**
- **OMOP:** [OMOP:4008265](https://athena.ohdsi.org/search-terms/terms/4008265)
- **OBA:** [OBA:VT0000180](http://purl.obolibrary.org/obo/OBA_VT0000180)

---

### Triglycerides in blood

**Machine-readable name:** `triglyc_bld`

Concentration of triglycerides in blood, typically measured in serum or plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** mg/dL
- **UCUM Unit:** mg/dL

**Ontology References:**
- **OMOP:** [OMOP:4032789](https://athena.ohdsi.org/search-terms/terms/4032789)
- **OBA:** [OBA:VT0002644](http://purl.obolibrary.org/obo/OBA_VT0002644)

---

### Troponin all types

**Machine-readable name:** `troponin`

Concentration of all types of troponin in blood

**Properties:**
- **Datatype:** decimal
- **Unit:** ng/mL

**Ontology References:**
- **OMOP:** [OMOP:4021291](https://athena.ohdsi.org/search-terms/terms/4021291)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### Vegetables

**Machine-readable name:** `vege_serving`

Servings of vegetables consumed per week

**Properties:**
- **Datatype:** integer
- **Unit:** servings per week

**Ontology References:**
- **OMOP:** [OMOP:4042886](https://athena.ohdsi.org/search-terms/terms/4042886)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### von Willebrand factor

**Machine-readable name:** `willeb_fac`

Concentration of von willebrand factor in blood

**Properties:**
- **Datatype:** decimal
- **Unit:** IU/dL
- **UCUM Unit:** %{Normal}

**Ontology References:**
- **OMOP:** [OMOP:4252203](https://athena.ohdsi.org/search-terms/terms/4252203)
- **OBA:** [OBA:2052741](http://purl.obolibrary.org/obo/OBA_2052741)

---

### Waist circumference

**Machine-readable name:** `waist_circ`

Distance measurement taken around the waist, just above the hip bone

**Properties:**
- **Datatype:** decimal
- **Unit:** cm
- **UCUM Unit:** cm

**Ontology References:**
- **OMOP:** [OMOP:4172830](https://athena.ohdsi.org/search-terms/terms/4172830)
- **OBA:** [OBA:1001085](http://purl.obolibrary.org/obo/OBA_1001085)

---

### Waist-hip ratio

**Machine-readable name:** `waist_hip`

Ratio of the circumference of the waist to the circumference of the hips

**Properties:**
- **Datatype:** decimal
- **Unit:** ratio
- **UCUM Unit:** {ratio}

**Ontology References:**
- **OMOP:** [OMOP:4087501](https://athena.ohdsi.org/search-terms/terms/4087501)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### White blood cell count

**Machine-readable name:** `whtbld_ct`

Concentration of white blood cells in whole blood

**Properties:**
- **Datatype:** decimal
- **Unit:** x10E3/uL
- **UCUM Unit:** 10*3/uL

**Ontology References:**
- **OMOP:** [OMOP:4298431](https://athena.ohdsi.org/search-terms/terms/4298431)
- **OBA:** [OBA:VT0000217](http://purl.obolibrary.org/obo/OBA_VT0000217)

---

### Albumin in urine

**Machine-readable name:** `albumin_urine`

Concentration of albumin in urine

**Properties:**
- **Datatype:** decimal
- **Unit:** mg/dL
- **UCUM Unit:** mg/L

**Ontology References:**
- **OMOP:** [OMOP:2212188](https://athena.ohdsi.org/search-terms/terms/2212188)
- **OBA:** [OBA:VT0002871](http://purl.obolibrary.org/obo/OBA_VT0002871)

---

### CESD score

**Machine-readable name:** `cesd_score`

Score from a self-report questionnaire, the CES-D (Center for Epidemiological Studies Depression Scale)

**Properties:**
- **Datatype:** integer
- **Unit:** NONE
- **UCUM Unit:** {score}

**Ontology References:**
- **OMOP:** [OMOP:36303297](https://athena.ohdsi.org/search-terms/terms/36303297)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### Factor VIII

**Machine-readable name:** `factor_8`

Measure of the amount of FVIII activity in a volume of plasma

**Properties:**
- **Datatype:** decimal
- **Unit:** IU/mL
- **UCUM Unit:** [iU]/mL

**Ontology References:**
- **OMOP:** [OMOP:4148587](https://athena.ohdsi.org/search-terms/terms/4148587)
- **OBA:** [OBA:2041536](http://purl.obolibrary.org/obo/OBA_2041536)

---

### Fasting lipids

**Machine-readable name:** `fast_lipids`

Concentration of lipids in blood after not eating or drinking (except water) for a set period, typically 8-12 hours

**Properties:**
- **Datatype:** decimal
- **Unit:** mg/dL
- **UCUM Unit:** mg/dL

**Ontology References:**
- **OMOP:** [OMOP:4150326](https://athena.ohdsi.org/search-terms/terms/4150326)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### Medication adherence

**Machine-readable name:** `med_adher`

**Properties:**
- **Datatype:** [BaseEnum](https://rtiinternational.github.io/NHLBI-BDC-DMC-HM/BaseEnum)
- **Unit:** NONE

**Ontology References:**
- **OMOP:** [OMOP:4056965](https://athena.ohdsi.org/search-terms/terms/4056965)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### Pacemaker implant status

**Machine-readable name:** `pacem_stat`

**Properties:**
- **Datatype:** [BaseEnum](https://rtiinternational.github.io/NHLBI-BDC-DMC-HM/BaseEnum)
- **Unit:** NONE

**Ontology References:**
- **OMOP:** [OMOP:45772840](https://athena.ohdsi.org/search-terms/terms/45772840)

---

### Systolic blood pressure

**Machine-readable name:** `bp_systolic`

Measurement of pressure in your arteries when your heart pumps blood, the top number in a blood pressure reading

**Properties:**
- **Datatype:** integer
- **Unit:** mmHg

**Ontology References:**
- **OMOP:** [OMOP:4152194](https://athena.ohdsi.org/search-terms/terms/4152194)
- **OBA:** [REQUESTED](https://github.com/obophenotype/bio-attribute-ontology/issues/364)

---

### monocytes count

**Machine-readable name:** `monocyte_ncnc_bld`

Concentration of monocyte cells in whole blood

**Properties:**
- **Datatype:** decimal
- **Unit:** 10^3cells/uL
- **UCUM Unit:** 10*3/uL

**Ontology References:**
- **OMOP:** [OMOP:3001604](https://athena.ohdsi.org/search-terms/terms/3001604)
- **OBA:** [OBA:VT0000223](http://purl.obolibrary.org/obo/OBA_VT0000223)

---

### RDI Respiratory Disturbance Index

**Machine-readable name:** `resp_dist_index`

Measurement used to quantify the frequency of breathing disruptions during sleep. It is calculated by counting the number of apneas hypopneas & RERAs that occur per hour of sleep.

**Properties:**
- **Datatype:** decimal
- **Unit:** events/hr
- **UCUM Unit:** /h

**Ontology References:**
- **OMOP:** [OMOP:1175351](https://athena.ohdsi.org/search-terms/terms/1175351)

---

## SdohObservation

### Education level

**Machine-readable name:** `edu_lvl`

Highest level of education that an individual has completed

**Properties:**
- **Datatype:** [BaseEnum](https://rtiinternational.github.io/NHLBI-BDC-DMC-HM/BaseEnum)
- **Unit:** NONE

**Ontology References:**
- **OMOP:** [OMOP:4022643](https://athena.ohdsi.org/search-terms/terms/4022643)

---

### Family income

**Machine-readable name:** `fam_income`

The sum of the income of all family members 15 years and older living in the household over 12 months, before taxes

**Properties:**
- **Datatype:** 
- **Unit:** NONE

**Ontology References:**
- **OMOP:** [OMOP:4076114](https://athena.ohdsi.org/search-terms/terms/4076114)

---

