# Mapping Validation Preferences

Reference for validating mapped terms in the semantic validator. For each domain (slot / enum), this specifies the controlled vocabulary that backs the CURIE or concept, and **how that vocabulary should be resolved** when validating a mapped term.

## Resolution sources

- **RTI International (bdchm)** — validate against the BioData Catalyst harmonized model's ontology-backed enums (CURIE-based).
- **OMOP WebAPI** — resolve and validate concept IDs through the OHDSI OMOP WebAPI / Athena vocabulary service.
- **EMBL-EBI OLS4 REST APIS** - Condition concept use the MONDO ontology
- **SIREN / HL7 FHIR Gravity Project** — validate SDOH domain terms against the Gravity Project's SDOH Clinical Care FHIR Implementation Guide (LOINC-coded screening instruments; SNOMED CT / ICD-10-CM coded problems, goals, and interventions). The Gravity Project originated as an independent, multi-stakeholder SDOH data-standards initiative (led by SIREN — the Social Interventions Research and Evaluation Network — with philanthropic backing) before becoming an HL7 FHIR Accelerator project; RTI International/BDCHM consumes this vocabulary but did not originate it.

## Preferences by domain

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
| SDOH | Gravity Project domains | SIREN / HL7 FHIR Gravity Project |
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

## Curated Drug-Name Overrides

Free-text medication-name fields (e.g. "name of chol lowering medication") sometimes get `case()`-matched against specific drug names during curation. `DRUG_CURIE_OVERRIDES` in `scripts/rxnorm_agent.py` exists for any drug name whose correct CURIE shouldn't be left to the live RxNorm/Atlas lookup — either because the right answer is an ATC therapeutic class (the live lookup only ever returns OMOP concept IDs, wrapped as `OMOP:<id>`, and cannot produce an ATC code at all), or because the right answer is a specific dose/form-level RxCUI that live search ranks unreliably (see the `niacin 500mg tablets` entry below — confirmed 2026-08-26 to rank anywhere from 3rd to not-found-at-all across several reasonable query phrasings). The override is checked first in the `drug_concept` branch of `_agent_suggestion()`, against the row's actual free-text value (not the generic field description — see "How free-text drug rows are matched" below), and returns the full CURIE directly, bypassing the `OMOP:` wrapping — so a pipeline re-run lands on the correct value instead of drifting back to a bare RxCUI/OMOP concept.

Matching is case-insensitive and whole-word, so "niacin 500mg tablets" matches its own dedicated entry below (not the older, now-removed generic "niacin" entry — see 2026-08-26 row in Confirmed Corrections).

| Drug name | CURIE | Why |
|:---|:---|:---|
| `gemfibrozil` | `ATC:C10AB` | Fibrate — found mismapped to an RxCUI inside CARDIA's `tak_statin.yaml` free-text medication list. Confirmed correct as the class-level answer per PR review (2026-08-26) — not a candidate for upgrading to an ingredient-level RxCUI. |
| `metoprolol` | `RxCUI:6918` | Beta blocker, ingredient-level. Briefly overridden to `ATC:C07AB` (2026-08-18), reverted to this RxCUI after PR review (2026-08-25) — metoprolol isn't a lipid drug at all, so an ATC code from the lipid-modifying-agent hierarchy was never appropriate for it. |
| `niacin 500mg tablets` | `RxCUI:198024` | niacin 500 MG Oral Tablet — immediate-release, matching the source text exactly ("niacin 500mg tablets," no "ER"/"extended-release" wording). The extended-release form (`RxCUI:311960`/`OMOP:19078988`) was checked and ruled out for the same reason. |

**How free-text drug rows are matched (added 2026-08-26)**: a `{study}_curie.csv` row for a multi-value free-text `case()` field can carry a `Free Text Value` column giving the exact source string that row's CURIE corresponds to (e.g. CARDIA's `tak_statin.yaml`, which packs up to 7 distinct drug names into one field per PHV). When present, this value — not the generic `Variable Description` — is what gets checked against `DRUG_CURIE_OVERRIDES` and used as the live-search query. This is what makes the overrides above actually able to fire: matching against the generic field description (e.g. "NAME OF CHOL LOWERING MED. Q 25a") can never match a specific drug name. A cell can collapse multiple source strings sharing one CURIE (e.g. "mevacor; mevacoh") — the first is used for matching/search. This column is opt-in per study; studies without it are completely unaffected and behave exactly as before.

**General principle**: when a free-text or coded value names a specific drug unambiguously (ingredient, or ingredient+dose+form), prefer the most specific identifier available (RxCUI ingredient/clinical-drug level) over a broader ATC class code — unless the fact being asserted is genuinely about class membership (e.g., a yes/no "taking any statin" question where no specific drug is named), or live search is confirmed unable to reliably rank the correct specific concept first (in which case, pin it via override rather than trusting search ranking). Don't let a class-level override apply to every occurrence of a drug name if it discards information the source text actually provides.

To add a new entry: append to `DRUG_CURIE_OVERRIDES` in `scripts/rxnorm_agent.py` and re-run Step 1 for the affected study.

## Confirmed Corrections

Curation fixes applied and recorded as of the dates below.

| Date | Study | File | Slot | Old CURIE | New CURIE | Reason |
|:---|:---|:---|:---|:---|:---|:---|
| 2026-06-15 | COPDGene | `lymphocyte_ct.yaml` | `observation_type` | OBA:VT0000217 | OBA:VT0000717 | OBA:VT0000217 is "leukocyte quantity" (total WBC count) — wrong for lymphocytes. OBA:VT0000717 is "lymphocyte quantity". The bdchm schema `LYMPHOCYTES_COUNT` enum entry also had this wrong code. |
| 2026-08-18 | CARDIA | `tak_statin.yaml` | `drug_concept` | RxCUI:6918 (metoprolol), RxCUI:7393/RxCUI:316343 (niacin), RxCUI:4719 (gemfibrozil) | ATC:C07AB, ATC:C10AD, ATC:C10AB | Free-text medication names inside a statin-flag file were individually RxCUI-coded, including non-statin drugs. Corrected to proper ATC classes; codified as a durable override (see above) so future re-runs don't drift back. **Superseded 2026-08-25 for metoprolol/niacin — see row below.** |
| 2026-08-25 | CARDIA | `tak_statin.yaml` | `drug_concept` | ATC:C07AB (metoprolol), ATC:C10AD (niacin) | RxCUI:6918 (metoprolol), RxCUI:198024 (niacin 500mg, immediate-release) | PR review judged dose/form-specific RxCUI more useful than the ATC class code once the free-text value names an exact drug+dose ("niacin 500mg tablets"). Extended-release form (RxCUI:311960/OMOP:19078988) checked and ruled out — source text doesn't say "ER"/"extended-release." Supersedes the 2026-08-18 row for these two drugs only; `gemfibrozil` unchanged. |
| 2026-08-26 | CARDIA | `tak_statin.yaml` | `drug_concept` | (2026-08-25 row's values were never actually reachable — see reason) | RxCUI:6918 (metoprolol), RxCUI:198024 (niacin 500mg tablets) re-added to `DRUG_CURIE_OVERRIDES` as hard overrides; `gemfibrozil` unchanged | Root cause found: `DRUG_CURIE_OVERRIDES` was always checked against the generic field description (e.g. "NAME OF CHOL LOWERING MED. Q 25a"), never the actual free-text drug name — so it could never have matched "metoprolol" or "niacin 500mg tablets" even before the 2026-08-18 entries existed. Fixed by adding a `Free Text Value` column to `CARDIA_curie.csv` (see "How free-text drug rows are matched" above) so the override check — and the live-search fallback for un-overridden values — finally sees the real drug name. A live-search-only approach (dropping the Ingredient-only filter, querying the free text directly) was prototyped and confirmed working for plain `niacin` and `metoprolol`, but `niacin 500mg tablets` never ranked reliably (rank 3 to not-found across phrasings tried) and the endpoint itself proved too flaky to depend on for known answers — so both are pinned as overrides instead of left to live search. Plain `niacin` (no dose) is not overridden; it resolves correctly via live search on its own. |

---

## Known False Positive Patterns

These patterns systematically produce incorrect High-priority findings and are suppressed by `_SLOT_VOCAB_RULES`. They do not indicate errors in the existing CURIEs.

1. **LOINC replacing OBA in `observation_type`** — agent returns lab-test codes (LOINC) for measurement variables; bdchm `observation_type` requires biological-attribute terms (OBA/OMOP). Suppressed count ranged from 21 (COPDGene) to 61 (ARIC) per study as of 2026-06-15.
2. **OMOP replacing MONDO in `condition_concept`** — agent returns OMOP CDM concept IDs for condition variables; bdchm `condition_concept` is typed to MONDO/HP only. Suppressed count ranged from 3 (CHS) to 15 (ARIC) per study as of 2026-06-15.

To add a new false-positive rule, append an entry to `_SLOT_VOCAB_RULES` in `scripts/generate_semantic_review.py` and re-run the semantic review for affected studies.

---

## Reference data

- **`bdc_study_input/reference/who_bmi_classification.json`** — WHO/clinical BMI classification schemes seen across the fleet's dbGaP source variables. Two *distinct* schemes exist in the wild here: the modern WHO scheme (6 tiers; "Overweight" is separate from 3 obesity grades) and an older Garrow-style scheme (4 tiers; every non-normal tier is labeled "...overweight," including what the modern scheme calls obesity). A BMI-category variable's own coded labels must be checked against both before mapping it to a `condition_concept`/derived observation — assuming one scheme universally is exactly the trap that produced MESA `obesity.yaml`'s unresolved tier-mismatch defect (external review item C1, 2026-08-27; documented in full in the JSON file and in `summary_of_fix_so_far_082426.md`'s "Pinned for later" section).

---

## Suggestion Confidence

As of 2026-08-18, `generate_curie_mapreview.py` writes confidence columns alongside each agent suggestion, surfaced in the review report / curator app as part of the `semantic validator review` text (e.g. "✅ **Normalizer confidence**: high (normalizer-confirmed synonym).").

`observation_type` rows can carry **two independent candidates in the same row** — `oba_maps_to` and `omop_maps_to` (a LOINC code, despite the column name) — so there are two separate confidence columns, not one shared value. Conflating them would silently describe only one candidate while implying it covered both.

| Column | Populated for | Confidence source | Meaning |
|:---|:---|:---|:---|
| `suggestion_confidence` | `condition_concept` | NCATS Translator SRI Node Normalizer (`scripts/curie_normalizer.py`), `GET https://nodenormalization-sri.renci.org/get_normalized_nodes` | Checks whether the existing CSV CURIE and the agent's candidate CURIE resolve to the **same identifier clique**. `high` = confirmed synonym (e.g. `HP:0001297` "Stroke" and `MONDO:0005098` "Stroke disorder" are the same clique — safe to accept). `needs review` = the normalizer resolves them to **distinct concepts** — the candidate may be narrower/broader/different than the source variable describes (e.g. `MONDO:0005386` "peripheral **arterial** disease" → `MONDO:0005294` "peripheral **vascular** disease" is a scope change, not a synonym swap). Only covers MONDO/HP identifiers — it does not know about OBA or OMOP concept IDs. |
| `suggestion_confidence` | `observation_type` (`oba_maps_to` candidate) | OBA agent text-similarity score (`scripts/oba_agent.py`, `get_oba_id_with_score`) | Composite string-similarity between the variable description and the OBA term's label/synonyms. `high` (≥0.85) = strong text match. `medium` (0.6–0.85) = partial match. `needs review` (<0.6) = weak match — the candidate term's label may not actually describe what the source variable measures. Caught a real example: for "chloride level in blood," the OBA agent's top hit was `OBA:2100172` ("chloride channel protein ClC-Kb amount in blood" — a channel protein, not the electrolyte) — correctly tagged `needs review`. |
| `loinc_confidence` | `observation_type` (`omop_maps_to`/LOINC candidate) | LOINC agent's own text-similarity score (`scripts/measurementObs_agent.py`, `get_loinc_id_with_score`) | Same tiering, scored against the LOINC long/short name and component. This is match-quality context for the LOINC code itself — since LOINC is *always* a vocabulary/slot mismatch for `observation_type` (see rule table above), this score isn't an accept/reject signal on its own; it's useful when the curator is deciding whether to relocate the code to `method_type`. |

**Important:** none of these sources validate OBA-vs-OMOP or OMOP-vs-LOINC vocabulary choice — that's still the `_SLOT_VOCAB_RULES` mismatch check above. When a suggestion is tagged `needs review`, pull the source dbGaP variable description (`phv...` definition) and compare it against the candidate CURIE's OLS4/Athena label directly before accepting — the same manual check used to catch the `pad.yaml` (arterial vs. vascular) and `obesity.yaml` (morbid vs. general) cases in FHS.

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

