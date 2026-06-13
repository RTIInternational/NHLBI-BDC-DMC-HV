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
