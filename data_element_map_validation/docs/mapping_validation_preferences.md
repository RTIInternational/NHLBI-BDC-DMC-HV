# Mapping Validation Preferences

Reference for validating mapped terms in the semantic validator. For each domain (slot / enum), this specifies the controlled vocabulary that backs the CURIE or concept, and **how that vocabulary should be resolved** when validating a mapped term.

## Resolution sources

- **RTI International (bdchm)** — validate against the BioData Catalyst harmonized model's ontology-backed enums (CURIE-based).
- **OMOP WebAPI** — resolve and validate concept IDs through the OHDSI OMOP WebAPI / Athena vocabulary service.
- **EMBL-EBI OLS4 REST APIS** - Condition concept use the MONDO ontology

## Preferences by domainRTI International (bdchm) — validate 

| Domain (slot / enum) | Vocabulary behind the CURIE | Validation source |
|---|---|---|
| Condition | MONDO (and the broader `ConditionConcept` set) | EMBL-EBI OLS4 REST APIs - EMBL-EBI's open-source search engine for ontologies, used to annotate biomedical data with ontology terms (bdchm) |
| Drug exposure | RxNorm | OMOP WebAPI |
| Device exposure | SNOMED | OMOP WebAPI |
| Procedure / provenance / sex / visit / vital status | OMOP concept IDs | OMOP WebAPI |
| Anatomic site | Uberon |  EMBL-EBI OLS4 REST API.  (bdchm) |
| Phenotypic abnormality | HP | OLS4 REST API, (bdchm) |
| Assay method / instrument | LOINC | NLM LOINC clinical tables API at https://clinicaltables.nlm.nih.gov/api/loinc_items/v3/search |
| Cause of death | ICD-10CM | OMOP Concept ID(bdchm) |
| Species / breed | NCBITaxon and Vertebrate Breed Ontology (VBO) | RTI International (bdchm) |
| Units | Units of Measurement ontology (UOM) or UCUM | OMOP vocabulary (UCUM unit concept IDs) |
| Consent / data use | Data Use Ontology (DUO) | RTI International (bdchm) |
| SDOH | Gravity Project domains | RTI International (bdchm) |
| Race / ethnicity | US OMB categories | OMB standard categories |

---

## Vocab/Slot Validation Rules

The automated agent pipeline queries MONDO, HPO, OMOP, LOINC, and RxNorm REST APIs to suggest CURIEs for each variable slot. However, **bdchm slots are ontology-typed** — each slot has a declared vocabulary range enforced by the schema enum. An agent suggestion from the wrong vocabulary is a slot-type mismatch, not a quality improvement.

The rules below are implemented in `_SLOT_VOCAB_RULES` in `scripts/generate_semantic_review.py` and are applied automatically during semantic review generation. Mismatched suggestions are suppressed from the High-priority findings list and counted in the summary report's **Vocab/Slot Validation** section.

### Rule table

| Slot | Valid vocabularies | Invalid (flagged as mismatch) | Schema reference |
|:---|:---|:---|:---|
| `observation_type` | OBA, OMOP | **LOINC** | `MeasurementObservationTypeEnum` — OBA/OMOP biological attributes only |
| `condition_concept` | MONDO, HP | **OMOP, SNOMED, LOINC** | `ConditionConceptEnum` — union of `MondoHumanDiseaseEnum` + `HpoPhenotypicAbnormalityEnum` |

### Why the distinction matters

**`observation_type` (OBA vs LOINC)**
- OBA/VT terms answer *"what biological attribute is being measured?"* (e.g. OBA:VT0000217 = leukocyte quantity). This is the role of `observation_type`.
- LOINC codes answer *"what assay procedure was performed?"* (e.g. LOINC:6690-2 = Leukocytes by automated count in blood). This belongs in `method_type`, not `observation_type`.
- Swapping an OBA term for a LOINC term in `observation_type` is a vocabulary/slot mismatch — the agent is conflating *what trait* with *what test*.

**`condition_concept` (MONDO/HP vs OMOP)**
- MONDO and HP terms are the ontology-backed CURIEs the bdchm model is typed for. The `ConditionConceptEnum` explicitly lists only MONDO: and HP: prefixes.
- OMOP concept IDs belong in the OMOP CDM `condition_concept_id` column of the target data model — they are not valid values in the bdchm `condition_concept` slot.
- An agent proposing OMOP:313217 to replace MONDO:0004981 (Atrial Fibrillation) is not an improvement; MONDO:0004981 is confirmed correct via MalaCards, ClinVar, and OLS.

### Curator decision framework

| Agent suggestion | CSV CURIE | Action |
|:---|:---|:---|
| Same vocabulary, different concept | MONDO, HP, OBA, etc. | Evaluate as genuine improvement — check whether agent concept is more specific or accurate |
| HP suggested for MONDO slot | MONDO | Both are valid — evaluate whether HP phenotype term is more appropriate than disease term for this variable |
| LOINC suggested for OBA `observation_type` | OBA | **Reject** — vocab/slot mismatch. Keep OBA. If the LOINC code is relevant, it belongs in `method_type`. |
| OMOP suggested for MONDO `condition_concept` | MONDO | **Reject** — vocab/slot mismatch. Keep MONDO. OMOP belongs in CDM target, not bdchm slot. |
| Agent matches existing CSV CURIE | any | No action needed — agent confirms current mapping |

---

## Curation States

The Semantic Review Curator app tracks four states per finding, recorded in `pending_change/{STUDY}_pending_changes.json`.

| Badge | State | Meaning |
|:---:|:---|:---|
| (none) | Unreviewed | Finding has not been actioned |
| 📝 | Notes saved | Curator added notes but no CURIE decision yet |
| 💾 | Change request | New CURIE proposed, pending application to YAML and CSV |
| ✅ | Applied | CURIE change written to YAML transform file and curie CSV |
| ☑ | Reviewed — no change | Curator reviewed and deliberately kept existing mapping; reason recorded |

The **☑ Reviewed — no change** state is the correct action for confirmed vocab/slot mismatches (e.g. LOINC-over-OBA, OMOP-over-MONDO) so there is a dated audit trail that the finding was seen and evaluated.

---

## Confirmed Corrections

Curation fixes applied and recorded as of the dates below.

| Date | Study | File | Slot | Old CURIE | New CURIE | Reason |
|:---|:---|:---|:---|:---|:---|:---|
| 2026-06-15 | COPDGene | `lymphocyte_ct.yaml` | `observation_type` | OBA:VT0000217 | OBA:VT0000717 | OBA:VT0000217 is "leukocyte quantity" (total WBC count) — wrong for lymphocytes. OBA:VT0000717 is "lymphocyte quantity". The bdchm schema `LYMPHOCYTES_COUNT` enum entry also had this wrong code. |

---

## Known False Positive Patterns

These patterns systematically produce incorrect High-priority findings and are suppressed by `_SLOT_VOCAB_RULES`. They do not indicate errors in the existing CURIEs.

1. **LOINC replacing OBA in `observation_type`** — agent returns lab-test codes (LOINC) for measurement variables; bdchm `observation_type` requires biological-attribute terms (OBA/OMOP). Suppressed count ranged from 21 (COPDGene) to 61 (ARIC) per study as of 2026-06-15.
2. **OMOP replacing MONDO in `condition_concept`** — agent returns OMOP CDM concept IDs for condition variables; bdchm `condition_concept` is typed to MONDO/HP only. Suppressed count ranged from 3 (CHS) to 15 (ARIC) per study as of 2026-06-15.

To add a new false-positive rule, append an entry to `_SLOT_VOCAB_RULES` in `scripts/generate_semantic_review.py` and re-run the semantic review for affected studies.

#### Vocabulary selection: OBA vs LOINC

Rule: vocabulary is chosen by (target model × slot semantics), not by ontology preference.
LOINC and OBA are NOT substitutes — LOINC names the observation/survey item;
OBA names the biological attribute/trait itself.

- OMOP target → LOINC or SNOMED standard concept_id. OBA is NOT an OMOP vocabulary;
  never assign an OBA CURIE on the OMOP path (no concept_id, no domain routing).
- bdchm target → assign the CURIE from the vocabulary the target slot's `range`/binding
  declares. Use OBA ONLY where the slot is an OBA/PATO-bound attribute enum.
  Measurement/observation-type slots take the LOINC CURIE.
- Survey/measurement items default to LOINC (LOINC covers survey & screening instruments).

#### OLS4 (OBA)
- Discovery:  https://www.ebi.ac.uk/ols4/api/search?ontology=oba&q=<term>
- Validate:   https://www.ebi.ac.uk/ols4/api/ontologies/oba/terms?obo_id=OBA:<id>
- Note: OBA results may surface VT: and PATO-derived CURIEs; decide whether the slot
  wants the OBA composite or the underlying PATO quality before auto-assigning.

