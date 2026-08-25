#!/usr/bin/env python3
"""Generate COPDGene_curie_mapreview.csv from COPDGene_curie.csv.

For each substantive clinical variable (skipping admin fields), calls the
appropriate mapping agent based on Slot / Entity Type and suggests a better
CURIE. Also spot-checks the YAML file to compare its actual CURIE against
the CSV value.

New columns added:
  yaml_curie         - CURIE extracted from the actual YAML file (or blank if admin)
  yaml_match         - '✓' if CSV CURIE == yaml_curie, '⚠' if different, '' if N/A
  omop_maps_to       - agent suggestion: LOINC:xxx (measurements), OMOP:xxx (procedure/obs)
  mondo_maps_to      - agent suggestion: MONDO:xxx for disease conditions
  hpo_maps_to        - agent suggestion: HP:xxx for phenotype conditions (fallback when MONDO finds nothing)
  uberon_maps_to     - agent suggestion: UBERON:xxx for anatomical sites / drug routes
  maps_to_entity_type - derived entity category
  suggestion_confidence - curator-facing confidence tag for the suggested change:
                       condition_concept  → Translator Node Normalizer clique check
                                            (curie_normalizer.py) — confirmed synonym
                                            vs distinct concept vs (MONDO/HP only)
                       observation_type   → OBA agent text-similarity tier
                                            (oba_agent.get_oba_id_with_score)

Agent routing by Slot + Entity Type:
  condition_concept  (Condition)               → MONDO → HPO → OMOP (priority cascade)
  observation_type   (MeasurementObservation, Observation) → measurementObs_agent → omop_maps_to
  observations       (MeasurementObservationSet) → measurementObs_agent → omop_maps_to
  procedure_concept  (Procedure)               → omop_agent   → omop_maps_to
  drug_concept       (DrugExposure)            → rxnorm_agent → omop_maps_to
  route_concept      (DrugExposure)            → omop_agent   → omop_maps_to
  race, sex          (Demography)              → omop_agent   → omop_maps_to
  value_enum, species                          → no suggestion

Usage:
  python generate_curie_mapreview.py
  python generate_curie_mapreview.py --no-agents   # skip API calls, YAML check only
"""

import csv
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Path constants — resolved at runtime from --study argument
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent.parent  # data_element_map_validation/

_REGISTRY_CSV = BASE_DIR / "bdc_study_input" / "BDC_registered_study_for_semantic_review.csv"


def _file_key(short_name: str) -> str:
    return short_name.replace("/", "_").replace(" ", "_")


def _load_study_configs() -> dict[str, dict]:
    configs: dict[str, dict] = {}
    if _REGISTRY_CSV.exists():
        import csv as _csv
        with open(_REGISTRY_CSV, newline="", encoding="utf-8-sig") as f:
            for row in _csv.DictReader(f):
                short = row["cohort_study_short_name"].strip()
                fk = _file_key(short)
                yaml_rel = row.get("yaml_file_path", "").strip()
                yaml_dir = (_REGISTRY_CSV.parent / yaml_rel).resolve() if yaml_rel else (
                    BASE_DIR.parent / "priority_variables_transform" / f"{fk}-ingest"
                )
                configs[short] = {
                    "input_csv":  BASE_DIR / "bdc_study_input" / f"{fk}_curie.csv",
                    "output_csv": BASE_DIR / "bdc_study_input" / f"{fk}_curie_mapreview.csv",
                    "dbgap_csv":  BASE_DIR / "bdc_study_input" / f"{fk}_dbgap_study_variable.csv",
                    "yaml_dir":   yaml_dir,
                }
    if not configs:
        configs["COPDGene"] = {
            "input_csv":  BASE_DIR / "bdc_study_input" / "COPDGene_curie.csv",
            "output_csv": BASE_DIR / "bdc_study_input" / "COPDGene_curie_mapreview.csv",
            "dbgap_csv":  BASE_DIR / "bdc_study_input" / "COPDGene_dbgap_study_variable.csv",
            "yaml_dir":   BASE_DIR.parent / "priority_variables_transform" / "COPDGene-ingest",
        }
        # BASE_DIR is data_element_map_validation/, so BASE_DIR.parent is the repo root
    return configs


_STUDY_CONFIGS = _load_study_configs()

# Defaults — overridden by _resolve_paths() once argparse runs
INPUT_CSV  = _STUDY_CONFIGS["COPDGene"]["input_csv"]
OUTPUT_CSV = _STUDY_CONFIGS["COPDGene"]["output_csv"]
DBGAP_CSV  = _STUDY_CONFIGS["COPDGene"]["dbgap_csv"]
YAML_DIR   = _STUDY_CONFIGS["COPDGene"]["yaml_dir"]


def _resolve_paths(study: str) -> None:
    global INPUT_CSV, OUTPUT_CSV, DBGAP_CSV, YAML_DIR
    cfg = _STUDY_CONFIGS.get(study)
    if cfg is None:
        print(f"Unknown study '{study}'. Known: {list(_STUDY_CONFIGS)}", file=sys.stderr)
        sys.exit(1)
    INPUT_CSV  = cfg["input_csv"]
    OUTPUT_CSV = cfg["output_csv"]
    DBGAP_CSV  = cfg["dbgap_csv"]
    YAML_DIR   = cfg["yaml_dir"]


# ---------------------------------------------------------------------------
# dbGaP source verification — ground truth for MeasurementObservation /
# observation_type rows only (see docs/semantic_review_curator_app.md).
# Run scripts/dbgap_variable_fetch.py --study <STUDY> to (re)generate the file
# this reads. Studies with no dbGaP file yet are simply unverified — every row
# falls back to the CSV's own description, same as before this feature existed.
# ---------------------------------------------------------------------------

def _load_dbgap_map() -> dict[str, dict]:
    """Return {PHV: {'name', 'description', 'pht'}} from DBGAP_CSV, or {} if absent.

    DBGAP_CSV uses the same column names as {STUDY}_curie.csv (PHV, PHT, Variable
    Name, Variable Description) — see dbgap_variable_fetch.py — so this is a
    straight join on PHV.
    """
    if not DBGAP_CSV.exists():
        print(
            f"No dbGaP source file at {DBGAP_CSV.name} — MeasurementObservation rows "
            "will use the CSV's own description, unverified. Run "
            "dbgap_variable_fetch.py to enable source verification.",
            file=sys.stderr,
        )
        return {}
    with open(DBGAP_CSV, newline="", encoding="utf-8-sig") as f:
        return {
            row["PHV"].strip(): {
                "name": row["Variable Name"].strip(),
                "description": row["Variable Description"].strip(),
                "pht": row["PHT"].strip(),
            }
            for row in csv.DictReader(f)
            if row.get("PHV", "").strip()
        }


# ---------------------------------------------------------------------------
# LOINC -> OMOP concept_id resolution — local vocabulary table, not a live API
# call. bdc_study_input/loinc2omop_curie.tsv is a full export of OMOP's
# concept_relationship table filtered to relationship_id == "Maps to" and
# source_vocabulary_id == "LOINC" (277,764 rows as of 2026-08-24). Tab-delimited
# rather than comma-delimited — several source_concept_name/target_concept_name
# values contain a literal " | " (LOINC's own hierarchy naming convention) or
# embedded commas, and tab does not appear anywhere in the file, so it can be
# split safely without relying on quote-aware parsing downstream. Replaces
# the earlier atlas-demo.ohdsi.org-based get_omop_concept_id_from_loinc(),
# which reliably timed out under concurrent load (observed ~93% failure rate
# at 8 workers) and left large numbers of rows with an unresolved OMOP
# candidate — silently dropping an otherwise-eligible candidate out of
# priority_curie contention purely due to network flakiness, not because it
# didn't exist. A local dict lookup has no failure mode of that kind: every
# code is either in the table (resolved) or genuinely absent (no_exact_match)
# — "api_error" is no longer a possible outcome for this step.
# ---------------------------------------------------------------------------
_LOINC_OMOP_CSV = BASE_DIR / "bdc_study_input" / "loinc2omop_curie.tsv"


def _load_loinc_omop_map() -> dict[str, str]:
    """Return {LOINC source_concept_code: target_concept_id} from _LOINC_OMOP_CSV.

    Uses the file's own precomputed target_concept_id column directly — no
    need to re-derive anything, since the export already resolved the "Maps
    to" relationship. Returns {} (not an error) if the file is absent, so a
    checkout without it degrades to "no_exact_match" for every LOINC code
    rather than crashing.
    """
    if not _LOINC_OMOP_CSV.exists():
        print(
            f"No local LOINC->OMOP vocabulary at {_LOINC_OMOP_CSV.name} — "
            "observation_type/observations rows with a LOINC candidate will "
            "show no OMOP resolution. See scripts/README or the notes on "
            "generating this file via a Databricks OMOP vocabulary export.",
            file=sys.stderr,
        )
        return {}
    with open(_LOINC_OMOP_CSV, encoding="utf-8-sig", errors="replace", newline="") as f:
        return {
            row["source_concept_code"]: row["target_concept_id"]
            for row in csv.DictReader(f, delimiter="\t")
            if row.get("source_concept_code")
        }


def _resolve_loinc_to_omop(loinc_curie: str, loinc_omop_map: dict[str, str]) -> tuple[str | None, str]:
    """Resolve 'LOINC:<code>' to ('OMOP:<id>', 'resolved') via the local
    vocabulary table, or (None, 'no_exact_match') if the code isn't in it.

    Local-table equivalent of the old get_omop_concept_id_from_loinc_with_status()
    API call — same (concept_id, status) contract, minus the "api_error" status,
    since a dict lookup can't time out."""
    code = loinc_curie.split(":", 1)[1] if ":" in loinc_curie else loinc_curie
    target = loinc_omop_map.get(code)
    if target:
        return f"OMOP:{target}", "resolved"
    return None, "no_exact_match"

# ---------------------------------------------------------------------------
# Admin variables that appear on every YAML file — skip agent calls for these
# ---------------------------------------------------------------------------
ADMIN_VARS = frozenset({"SUBJECT_ID", "phase_study", "age_visit"})

# ---------------------------------------------------------------------------
# CURIE pattern
# ---------------------------------------------------------------------------
_CURIE_RE = re.compile(r"\b([A-Z][A-Z0-9_]*:[A-Z0-9.]+)\b")

# ---------------------------------------------------------------------------
# YAML CURIE extraction (no pyyaml required — regex on known structure)
# ---------------------------------------------------------------------------
# Strategy 1: slot:\n<indent>  value: CURIE  (most slots)
_SLOT_VALUE_RE = re.compile(
    r"^(\s+)(\w+):\s*\n\1  value:\s+([^\n\r#]+)",
    re.MULTILINE,
)
# Strategy 2: value_mappings block  →  '1': CURIE lines
_SLOT_HEADER_RE = re.compile(r"^(\s{4,})(\w+):\s*$", re.MULTILINE)
_MAPPING_LINE_RE = re.compile(r"^\s+'[^']*':\s+([A-Z][A-Z0-9_]*:[A-Z0-9.]+)", re.MULTILINE)


def extract_yaml_curies(yaml_file: Path) -> dict[str, list[str]]:
    """Return {slot_name: [curie, ...]} from a YAML file.

    Handles:
      Strategy 1: slot_name:\n    value: CURIE
      Strategy 2: slot_name:\n    value_mappings:\n      'x': CURIE
      Strategy 3: slot_name:\n    expr: 'case((..., "CURIE"))' — CURIEs embedded in expressions
    """
    try:
        text = yaml_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}

    result: dict[str, list[str]] = {}

    # Strategy 1: explicit single value
    for m in _SLOT_VALUE_RE.finditer(text):
        slot = m.group(2).strip()
        value = m.group(3).strip().strip("'\"")
        if _CURIE_RE.match(value):
            result.setdefault(slot, []).append(value)

    # Strategy 2: find value_mappings headers, walk back to parent slot, collect CURIEs
    headers = list(_SLOT_HEADER_RE.finditer(text))
    for i, hm in enumerate(headers):
        if hm.group(2) != "value_mappings":
            continue
        vm_indent = len(hm.group(1))
        # Find nearest preceding header at lower indentation → that's the parent slot
        parent_slot = None
        for j in range(i - 1, -1, -1):
            if len(headers[j].group(1)) < vm_indent:
                parent_slot = headers[j].group(2)
                break
        if parent_slot is None:
            continue
        # CURIEs live in the block immediately after the value_mappings header
        block_start = hm.end()
        block_end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        block = text[block_start:block_end]
        curies = _CURIE_RE.findall(block)
        if curies:
            result.setdefault(parent_slot, []).extend(curies)

    # Strategy 3: CURIEs embedded in expr strings, e.g. case(({phv} == 1, "ATC:C10A"))
    _EXPR_LINE_RE = re.compile(
        r"^(\s+)(\w+):\s*\n\1  expr:\s+['\"](.+)['\"]", re.MULTILINE
    )
    for m in _EXPR_LINE_RE.finditer(text):
        slot = m.group(2).strip()
        if slot in result:
            continue  # already covered by strategy 1/2
        expr_val = m.group(3)
        curies = _CURIE_RE.findall(expr_val)
        if curies:
            result.setdefault(slot, []).extend(curies)

    return result


# ---------------------------------------------------------------------------
# Agent imports — loaded lazily so --no-agents skips them
# ---------------------------------------------------------------------------

def _import_agents():
    sys.path.insert(0, str(BASE_DIR))
    from mondo_agent import get_mondo_id, get_mondo_id_with_score, _extract_clinical_term
    from hpo_agent import get_hpo_id, get_hpo_id_with_score
    from omop_agent import get_omop_concept_id, get_omop_concept_id_with_score
    from rxnorm_agent import get_omop_concept_id as get_rxnorm_id, get_drug_curie_override
    from measurementObs_agent import get_loinc_id
    from meds_route_agent import get_omop_route_id
    from oba_agent import get_oba_id, get_oba_id_with_score
    from measurementObs_agent import get_loinc_id_with_score
    from curie_normalizer import confidence_label as get_normalizer_confidence
    return get_mondo_id, get_hpo_id, get_omop_concept_id, get_rxnorm_id, get_loinc_id, _extract_clinical_term, get_omop_route_id, get_oba_id, get_normalizer_confidence, get_oba_id_with_score, get_loinc_id_with_score, get_drug_curie_override, get_mondo_id_with_score, get_hpo_id_with_score, get_omop_concept_id_with_score


# ---------------------------------------------------------------------------
# Route-term extraction
# ---------------------------------------------------------------------------

_ROUTE_KEYWORDS: list[tuple[str, str]] = [
    # (search pattern, canonical query for omop_agent)
    ("inhal",       "inhalation"),
    ("respirat",    "respiratory tract"),
    ("oral",        "oral"),
    ("sublingual",  "sublingual"),
    ("buccal",      "buccal"),
    ("inject",      "injection"),
    ("subcutan",    "subcutaneous"),
    ("intramus",    "intramuscular"),
    ("intraven",    "intravenous"),
    ("topical",     "topical"),
    ("transdermal", "transdermal"),
    ("nasal",       "nasal"),
    ("ophthalm",    "ophthalmic"),
    ("rectal",      "rectal"),
    ("vaginal",     "vaginal"),
]


def _extract_route_term(text: str) -> str:
    """Return the canonical route query term found in *text*, or *text* as-is."""
    lower = text.lower()
    for fragment, canonical in _ROUTE_KEYWORDS:
        if fragment in lower:
            return canonical
    return text


# ---------------------------------------------------------------------------
# Demographic value extraction for race / sex / ethnicity lookups
# Atlas text search only surfaces individual demographic values ("Male",
# "Asian") not category labels, so we extract the specific value term.
# ---------------------------------------------------------------------------

_GENDER_KEYWORDS: list[tuple[str, str]] = [
    ("female", "Female"),
    ("woman",  "Female"),
    ("male",   "Male"),
    ("man",    "Male"),
    ("gender", "Male"),   # fallback: return Male/Female pair via "male" query
    ("sex",    "Male"),
]

_RACE_KEYWORDS: list[tuple[str, str]] = [
    ("white",    "White"),
    ("black",    "Black or African American"),
    ("african",  "Black or African American"),
    ("asian",    "Asian"),
    ("hispanic", "Hispanic or Latino"),
    ("ethnic",   "Hispanic or Latino"),
    ("native",   "American Indian or Alaska Native"),
    ("pacific",  "Native Hawaiian or Other Pacific Islander"),
    ("other",    "Some other race"),
    ("race",     "White"),   # fallback: suggest "White" to at least anchor search
]


def _extract_demo_term(text: str, slot: str) -> str:
    """Return a demographic value term appropriate for Atlas domain search."""
    lower = text.lower()
    keywords = _GENDER_KEYWORDS if slot == "sex" else _RACE_KEYWORDS
    for fragment, canonical in keywords:
        if fragment in lower:
            return canonical
    return text


# ---------------------------------------------------------------------------
# Suggestion logic
# ---------------------------------------------------------------------------

def _similarity_confidence_tier(score: float, term_label: str) -> str:
    """Bucket a text-similarity score into a curator-facing confidence tag.

    term_label names the vocabulary the score is measuring against (e.g.
    "OBA term", "LOINC term") so the tag is unambiguous when a row has more
    than one candidate (e.g. observation_type has both an OBA and a LOINC
    suggestion, each scored independently).
    """
    if score >= 0.85:
        return f"high (strong text match to {term_label})"
    if score >= 0.6:
        return f"medium (partial text match to {term_label} — verify against description)"
    return f"needs review (weak text match to {term_label})"


_MIN_PRIORITY_SCORE = 0.6  # matches _similarity_confidence_tier's "needs review" floor


def _pick_priority_curie(
    mondo_val: str, hpo_val: str, oba_val: str, omop_val: str,
    mondo_score: float, hpo_score: float, oba_score: float,
    omop_score: float, loinc_score: float,
) -> tuple[str, str]:
    """Pick the single best-guess CURIE among candidates that clear a minimum
    text-match confidence, by comparing their actual scores — not a fixed
    MONDO > HPO > OBA > OMOP vocabulary order, and not just "found something."

    A weak match (score < _MIN_PRIORITY_SCORE) is excluded from winning here,
    but its *_maps_to column is NOT blanked anywhere upstream — it stays
    visible to the curator via get_terminology_matches() in
    curator_review_app.py, labeled as a weak match rather than presented as
    the recommendation. Suppression (fully hiding a candidate) is reserved for
    a stronger, confirmed-wrong signal — the MONDO/HPO Translator Normalizer
    check in _agent_suggestion, which says the candidate IS a different
    concept from the current CURIE, not just an uncertain text match.

    A row only ever populates the condition_concept trio (mondo/hpo/omop_score)
    or the observation_type pair (oba/loinc_score), never both, so omop_val's
    effective score is whichever of the two is nonzero. Slots with no scoring
    mechanism at all (procedure_concept, drug_concept, route_concept, race,
    sex — all a bare omop_val with score 0.0 because no _with_score call was
    made) are exempt from the floor, since 0.0 there means "unscored", not
    "scored and weak" — otherwise every candidate from those slots would be
    wrongly excluded. Returns (priority_curie, priority_curie_score) — score
    is "" when nothing scored."""
    omop_effective_score = omop_score or loinc_score
    omop_was_scored = omop_effective_score > 0
    candidates = [
        (mondo_val, mondo_score, True),
        (hpo_val, hpo_score, True),
        (oba_val, oba_score, True),
        (omop_val, omop_effective_score, omop_was_scored),
    ]
    eligible = [
        (v, s) for v, s, scored in candidates
        if v and (not scored or s >= _MIN_PRIORITY_SCORE)
    ]
    if not eligible:
        return "", ""
    best_curie, best_score = max(eligible, key=lambda c: c[1])
    return best_curie, f"{best_score:.3f}" if best_score else ""


def _agent_suggestion(
    slot: str,
    entity_type: str,
    var_name: str,
    var_desc: str,
    get_mondo_id,
    get_hpo_id,
    get_omop_concept_id,
    get_rxnorm_id,
    get_loinc_id,
    extract_clinical_term,
    get_omop_route_id,
    get_oba_id,
    get_normalizer_confidence=None,
    csv_curie: str = "",
    get_oba_id_with_score=None,
    get_loinc_id_with_score=None,
    get_drug_curie_override=None,
    get_mondo_id_with_score=None,
    get_hpo_id_with_score=None,
    get_omop_concept_id_with_score=None,
) -> tuple[str, str, str, str, str, str, str, float, float, float, float, float]:
    """Return (omop_maps_to, mondo_maps_to, hpo_maps_to, oba_maps_to,
    maps_to_entity_type, confidence, loinc_confidence, oba_score, loinc_score,
    mondo_score, hpo_score, omop_score).

    oba_score/loinc_score are the raw 0-1 text-similarity scores behind the
    oba_maps_to/omop_maps_to(LOINC) confidence tiers; mondo_score/hpo_score/
    omop_score are the equivalent for condition_concept. Both slots can carry
    more than one independent candidate at once (observation_type: OBA +
    LOINC/OMOP; condition_concept: MONDO + HPO + OMOP fallback are now all
    queried unconditionally rather than a fixed vocab order short-circuiting
    the rest) — picking priority_curie among survivors needs the actual
    numbers, not just which vocabulary comes first in a list.

    Routing:
      condition_concept  → MONDO → HPO → OMOP (priority cascade)
      observation_type / observations (any) → LOINC via measurementObs_agent
      procedure_concept  → omop_agent
      drug_concept       → rxnorm_agent
      route_concept      → omop_agent (OMOP route concepts)

    Two separate confidence fields, since observation_type can carry two
    independent candidates (oba_maps_to and omop_maps_to/LOINC) in the same
    row — a single shared field would silently only describe one of them:

      confidence (condition_concept) → compares the agent's candidate CURIE
        against the existing csv_curie via the Translator Node Normalizer
        (curie_normalizer.py) to flag a confirmed synonym (high confidence)
        vs a distinct concept (needs review). Normalizer coverage is MONDO/HP
        only.
      confidence (observation_type)  → the OBA agent's text-similarity score
        (oba_agent.py, get_oba_id_with_score) between the variable description
        and the OBA term's label/synonyms, bucketed into a confidence tier.
      loinc_confidence (observation_type only) → the LOINC agent's own
        text-similarity score (measurementObs_agent.py, get_loinc_id_with_score)
        for the omop_maps_to candidate. Note LOINC is always a vocabulary/slot
        mismatch for observation_type (see _SLOT_VOCAB_RULES in
        generate_semantic_review.py) — this score is match-quality context for
        when the curator relocates the code to method_type, not an accept/reject
        signal on its own.

    Both are text-match confidences, not ontological equivalence checks — the
    Translator normalizer does not cover OBA/OMOP/LOINC.
    """
    query = var_desc.strip() or var_name.strip()
    if not query:
        return "", "", "", "", "", "", "", 0.0, 0.0, 0.0, 0.0, 0.0

    omop_maps_to = ""
    mondo_maps_to = ""
    hpo_maps_to = ""
    oba_maps_to = ""
    maps_to_entity_type = ""
    confidence = ""
    loinc_confidence = ""
    oba_score_out = 0.0
    loinc_score_out = 0.0
    mondo_score_out = 0.0
    hpo_score_out = 0.0
    omop_score_out = 0.0

    try:
        if slot == "condition_concept":
            clean_query = extract_clinical_term(query)
            # Query MONDO, HPO, and OMOP unconditionally — no vocab short-
            # circuits the others. A candidate whose normalizer confidence
            # comes back "needs review" (resolves to a DIFFERENT concept than
            # csv_curie, not a confirmed synonym) is suppressed: excluded from
            # its *_maps_to column and from the scoring race below, the same
            # pattern used for the observation_type OBA/LOINC candidates.
            # Whichever survivors remain compete on their own text-match
            # score (mondo/hpo/omop_score) rather than a fixed vocab order —
            # a weak top MONDO hit no longer silently outranks a strong HPO
            # or OMOP match just because MONDO is checked first.
            if get_mondo_id_with_score:
                mondo_curie, mondo_score_out = get_mondo_id_with_score(clean_query)
            else:
                mondo_curie, mondo_score_out = get_mondo_id(clean_query), 0.0
            mondo_confidence = ""
            if mondo_curie and get_normalizer_confidence and csv_curie and mondo_curie != csv_curie:
                mondo_confidence = get_normalizer_confidence(csv_curie, mondo_curie)
                if mondo_confidence.startswith("needs review"):
                    mondo_curie = None

            if get_hpo_id_with_score:
                hp_curie, hpo_score_out = get_hpo_id_with_score(clean_query)
            else:
                hp_curie, hpo_score_out = get_hpo_id(clean_query), 0.0
            hpo_confidence = ""
            if hp_curie and get_normalizer_confidence and csv_curie and hp_curie != csv_curie:
                hpo_confidence = get_normalizer_confidence(csv_curie, hp_curie)
                if hpo_confidence.startswith("needs review"):
                    hp_curie = None

            if get_omop_concept_id_with_score:
                omop_curie, omop_score_out = get_omop_concept_id_with_score(clean_query)
            else:
                omop_curie, omop_score_out = get_omop_concept_id(clean_query), 0.0

            if mondo_curie:
                mondo_maps_to = mondo_curie
            if hp_curie:
                hpo_maps_to = hp_curie
            if omop_curie:
                omop_maps_to = omop_curie

            # Pick the entity-type label and shared confidence field from
            # whichever surviving candidate scores highest — that's the one
            # that will become priority_curie downstream (see out_row
            # assembly), so its own confidence tag is the relevant one to show.
            candidates = [
                (mondo_score_out, mondo_curie, "Condition", mondo_confidence),
                (hpo_score_out, hp_curie, "Condition (HPO)", hpo_confidence),
                (omop_score_out, omop_curie, "Condition (OMOP fallback)", ""),
            ]
            surviving = [c for c in candidates if c[1]]
            if surviving:
                _, _, maps_to_entity_type, confidence = max(surviving, key=lambda c: c[0])
            else:
                maps_to_entity_type = "Condition"

        elif slot in ("observation_type", "observations") and entity_type in (
            "MeasurementObservation", "MeasurementObservationSet", "Observation"
        ):
            if get_loinc_id_with_score:
                loinc_id, loinc_score = get_loinc_id_with_score(query)
                omop_maps_to = loinc_id or ""
                if omop_maps_to:
                    loinc_confidence = _similarity_confidence_tier(loinc_score, "LOINC term")
                    loinc_score_out = loinc_score
            else:
                curie = get_loinc_id(query)
                omop_maps_to = curie or ""
            if slot == "observation_type":
                if get_oba_id_with_score:
                    oba_id, oba_score = get_oba_id_with_score(query)
                    oba_maps_to = oba_id or ""
                    oba_score_out = oba_score
                    # Not blanked when weak — a low score just keeps it out of
                    # the priority_curie race (see _pick_priority_curie); the
                    # curator still sees it, labeled as a weak match, via
                    # get_terminology_matches() in curator_review_app.py.
                    if oba_maps_to and oba_maps_to != csv_curie and not _similarity_confidence_tier(oba_score, "OBA term").startswith("needs review"):
                        confidence = _similarity_confidence_tier(oba_score, "OBA term")
                else:
                    oba_maps_to = get_oba_id(query) or ""
            maps_to_entity_type = "Measurement"

        elif slot == "procedure_concept":
            curie = get_omop_concept_id(query)
            omop_maps_to = curie or ""
            maps_to_entity_type = "Procedure"

        elif slot == "drug_concept":
            override = get_drug_curie_override(query) if get_drug_curie_override else None
            if override:
                omop_maps_to = override
            else:
                concept_id = get_rxnorm_id(query)
                omop_maps_to = f"OMOP:{concept_id}" if concept_id else ""
            maps_to_entity_type = "DrugExposure"

        elif slot == "route_concept":
            route_term = _extract_route_term(query)
            curie = get_omop_route_id(route_term)
            omop_maps_to = curie or ""
            maps_to_entity_type = "DrugRoute"

        elif slot == "race":
            demo_term = _extract_demo_term(query, "race")
            # Route ethnicity queries to the Ethnicity domain
            cs = "ethnicity" if "hispanic" in demo_term.lower() else "race"
            curie = get_omop_concept_id(demo_term, code_system=cs)
            omop_maps_to = curie or ""
            maps_to_entity_type = "Demography"

        elif slot == "sex":
            demo_term = _extract_demo_term(query, "sex")
            curie = get_omop_concept_id(demo_term, code_system="gender")
            omop_maps_to = curie or ""
            maps_to_entity_type = "Demography"

        elif slot == "value_enum":
            maps_to_entity_type = "ValueEnum"

        elif slot == "species":
            maps_to_entity_type = "Person"

    except Exception as exc:
        print(f"  [agent error] slot={slot} query={query!r}: {exc}", file=sys.stderr)

    return (
        omop_maps_to, mondo_maps_to, hpo_maps_to, oba_maps_to, maps_to_entity_type,
        confidence, loinc_confidence, oba_score_out, loinc_score_out,
        mondo_score_out, hpo_score_out, omop_score_out,
    )


# ---------------------------------------------------------------------------
# YAML spot-check helpers
# ---------------------------------------------------------------------------

def _yaml_check(yaml_file_name: str, slot: str, csv_curie: str) -> tuple[str, str]:
    """Return (yaml_curie_display, match_symbol) for this slot in the YAML file."""
    if not yaml_file_name:
        return "", ""
    yaml_path = YAML_DIR / yaml_file_name
    slot_curies_map = extract_yaml_curies(yaml_path)
    if not slot_curies_map:
        return "(file not found)", ""
    curies = slot_curies_map.get(slot, [])
    if not curies:
        return "", ""
    # For single-value slots show the value; for value_mappings show a summary
    if len(curies) == 1:
        yaml_display = curies[0]
        match_sym = "match" if curies[0] == csv_curie else "mismatch"
    else:
        yaml_display = f"[{len(curies)} mappings]"
        match_sym = "match" if csv_curie in curies else "mismatch"
    return yaml_display, match_sym


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(no_agents: bool = False, workers: int = 10) -> None:
    if not INPUT_CSV.exists():
        print(f"Input CSV not found: {INPUT_CSV}", file=sys.stderr)
        sys.exit(1)

    if no_agents:
        get_mondo_id = get_hpo_id = get_omop_concept_id = get_rxnorm_id = get_loinc_id = extract_clinical_term = get_omop_route_id = get_oba_id = get_normalizer_confidence = get_oba_id_with_score = get_loinc_id_with_score = get_drug_curie_override = get_mondo_id_with_score = get_hpo_id_with_score = get_omop_concept_id_with_score = None
        print("Running in --no-agents mode: YAML spot-check only.", file=sys.stderr)
    else:
        print("Loading agents ...", file=sys.stderr)
        get_mondo_id, get_hpo_id, get_omop_concept_id, get_rxnorm_id, get_loinc_id, extract_clinical_term, get_omop_route_id, get_oba_id, get_normalizer_confidence, get_oba_id_with_score, get_loinc_id_with_score, get_drug_curie_override, get_mondo_id_with_score, get_hpo_id_with_score, get_omop_concept_id_with_score = _import_agents()  # noqa: E501
        print("Agents loaded.", file=sys.stderr)

    dbgap_map = _load_dbgap_map()
    if dbgap_map:
        print(f"Loaded {len(dbgap_map)} dbGaP-verified variables for source checking.", file=sys.stderr)

    loinc_omop_map = _load_loinc_omop_map()
    if loinc_omop_map:
        print(f"Loaded {len(loinc_omop_map)} LOINC->OMOP mappings from local vocabulary table.", file=sys.stderr)

    start_time = datetime.now()
    print(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}", file=sys.stderr)

    # Read all input rows into memory first. utf-8-sig strips a leading BOM if
    # present — {study}_curie.csv is written with utf-8-sig elsewhere in the
    # pipeline, so a plain "utf-8" read here left the BOM embedded as literal
    # text in the first fieldname ("﻿Cohort"), which then compounded with
    # every downstream utf-8-sig write into a doubled BOM in generated outputs.
    with open(INPUT_CSV, newline="", encoding="utf-8-sig") as fin:
        reader = csv.DictReader(fin)
        all_rows = list(reader)
        orig_fields = reader.fieldnames or []
    total = len(all_rows)

    # dbGaP source verification applies only to MeasurementObservation / observation_type
    # rows (the target_domain this feature was built for) — every other slot/entity_type
    # is untouched and behaves exactly as before.
    def _is_measurement_target(slot: str, entity_type: str) -> bool:
        return slot == "observation_type" and entity_type == "MeasurementObservation"

    # Cache: (var_name, slot, entity_type, phv) →
    #   (omop, mondo, hpo, oba, entity, confidence, loinc_confidence,
    #    loinc_val, loinc_omop_concept_id, source_verified, source_name_verified,
    #    source_desc_verified, source_pht_verified)
    # Note: `omop` here is always a real OMOP:<concept_id> or "" — for
    # observation_type/observations rows it's the LOINC candidate *resolved*
    # to its OMOP concept_id, never the raw LOINC code (that's `loinc_val`).
    suggestion_cache: dict[tuple, tuple] = {}

    if not no_agents:
        # Collect unique (var_name, slot, entity_type, phv) keys with first-seen var_desc/csv_curie.
        # For measurement targets with a dbGaP match, the query description is swapped for the
        # verified one *before* it ever reaches the agents.
        unique_keys: dict[tuple, tuple[str, str, bool, str, str, str]] = {}
        for r in all_rows:
            vn  = r.get("Variable Name", "").strip()
            sl  = r.get("Slot", "").strip()
            et  = r.get("Entity Type", "").strip()
            vd  = r.get("Variable Description", "").strip()
            cc  = r.get("CURIE", "").strip()
            phv = r.get("PHV", "").strip()
            if not (vn and vn not in ADMIN_VARS and sl):
                continue

            source_verified = False
            source_name_verified = ""
            source_desc_verified = ""
            source_pht_verified = ""
            query_desc = vd
            if _is_measurement_target(sl, et):
                dbgap_row = dbgap_map.get(phv)
                if dbgap_row:
                    source_verified = True
                    source_name_verified = dbgap_row["name"]
                    source_desc_verified = dbgap_row["description"]
                    source_pht_verified = dbgap_row["pht"]
                    query_desc = source_desc_verified or vd

            key = (vn, sl, et, phv)
            if key not in unique_keys:
                unique_keys[key] = (query_desc, cc, source_verified, source_name_verified, source_desc_verified, source_pht_verified)

        n_unique = len(unique_keys)
        actual_workers = min(workers, n_unique) if n_unique else 1
        print(
            f"Pre-populating {n_unique} unique variable/slot combinations "
            f"using {actual_workers} workers...",
            file=sys.stderr,
        )

        cache_lock = threading.Lock()
        counter = [0]

        def _populate_one(item: tuple) -> None:
            (vn, sl, et, phv), (vd, cc, source_verified, source_name_verified, source_desc_verified, source_pht_verified) = item
            (omop_val, mondo_val, hpo_val, oba_val, entity_val, confidence_val, loinc_confidence_val,
             oba_score_val, loinc_score_val, mondo_score_val, hpo_score_val, omop_score_val) = _agent_suggestion(
                sl, et, vn, vd,
                get_mondo_id, get_hpo_id, get_omop_concept_id,
                get_rxnorm_id, get_loinc_id, extract_clinical_term, get_omop_route_id, get_oba_id,
                get_normalizer_confidence, cc, get_oba_id_with_score, get_loinc_id_with_score, get_drug_curie_override,
                get_mondo_id_with_score, get_hpo_id_with_score, get_omop_concept_id_with_score,
            )

            # For observation_type/observations rows, _agent_suggestion returns a LOINC
            # code in omop_val (see its docstring) — resolve it to a real OMOP concept_id
            # so omop_maps_to always actually contains OMOP:<concept_id>. The raw LOINC
            # candidate is preserved separately as loinc_val for the loinc_maps_to column.
            loinc_val = ""
            loinc_omop_concept_id = ""
            # "resolved" | "no_exact_match" | "" (no LOINC candidate to resolve
            # at all). Resolved via the local vocabulary table (see
            # _resolve_loinc_to_omop) — no network call, so "api_error" is not
            # a possible outcome here anymore.
            loinc_omop_resolution_status = ""
            if omop_val.startswith("LOINC:"):
                loinc_val = omop_val
                loinc_omop_concept_id, loinc_omop_resolution_status = _resolve_loinc_to_omop(omop_val, loinc_omop_map)
                loinc_omop_concept_id = loinc_omop_concept_id or ""
                omop_val = loinc_omop_concept_id  # "" if no exact match — never leave a LOINC code here
            # A "needs review" LOINC match is not blanked here — it just stays
            # out of the priority_curie race (see _pick_priority_curie); the
            # curator still sees it, labeled as a weak match, via
            # get_terminology_matches() in curator_review_app.py.

            result = (
                omop_val, mondo_val, hpo_val, oba_val, entity_val, confidence_val, loinc_confidence_val,
                loinc_val, loinc_omop_concept_id, source_verified, source_name_verified, source_desc_verified,
                source_pht_verified, oba_score_val, loinc_score_val, mondo_score_val, hpo_score_val, omop_score_val,
                loinc_omop_resolution_status,
            )
            with cache_lock:
                suggestion_cache[(vn, sl, et, phv)] = result
                counter[0] += 1
                pct = counter[0] / n_unique
                print(
                    f"  [{counter[0]}/{n_unique} {pct:.0%}] {vn!r} slot={sl}",
                    file=sys.stderr,
                    flush=True,
                )

        with ThreadPoolExecutor(max_workers=actual_workers) as executor:
            list(executor.map(_populate_one, unique_keys.items()))

        print(f"Cache pre-populated ({n_unique} unique keys).", file=sys.stderr)

    # Write output rows in original order
    new_fields = orig_fields + [
        "yaml_curie",
        "yaml_match",
        "omop_maps_to",
        "mondo_maps_to",
        "hpo_maps_to",
        "oba_maps_to",
        "loinc_maps_to",
        "priority_curie",
        "priority_curie_score",
        "mondo_score",
        "hpo_score",
        "oba_score",
        "omop_score",
        "loinc_score",
        "maps_to_entity_type",
        "suggestion_confidence",
        "loinc_confidence",
        "loinc_omop_concept_id",
        "loinc_omop_resolution_status",
        "source_verified",
        "source_variable_name_verified",
        "source_variable_description_verified",
        "source_pht_verified",
    ]
    # Write to a temp file first, then atomically replace OUTPUT_CSV — if the real
    # target is locked (e.g. open in the curator app or Excel), a whole run's worth
    # of API calls above isn't lost; only the final rename needs retrying.
    tmp_path = OUTPUT_CSV.with_name(OUTPUT_CSV.stem + ".tmp" + OUTPUT_CSV.suffix)
    with open(tmp_path, "w", newline="", encoding="utf-8-sig") as fout:
        writer = csv.DictWriter(fout, fieldnames=new_fields)
        writer.writeheader()

        for row in all_rows:
            var_name    = row.get("Variable Name", "").strip()
            var_desc    = row.get("Variable Description", "").strip()
            slot        = row.get("Slot", "").strip()
            entity_type = row.get("Entity Type", "").strip()
            csv_curie   = row.get("CURIE", "").strip()
            yaml_file   = row.get("YAML File", "").strip()
            phv         = row.get("PHV", "").strip()

            is_admin = var_name in ADMIN_VARS or not var_name

            # YAML spot-check (always run, even for admin vars)
            if is_admin or not slot or not yaml_file:
                yaml_curie_val = ""
                yaml_match_val = ""
            else:
                yaml_curie_val, yaml_match_val = _yaml_check(yaml_file, slot, csv_curie)

            # Agent suggestions — always hits cache after pre-population
            if is_admin or no_agents:
                omop_val = mondo_val = hpo_val = oba_val = entity_val = confidence_val = loinc_confidence_val = ""
                loinc_val = ""
                loinc_omop_concept_id = ""
                source_verified = ""
                source_name_verified = ""
                source_desc_verified = ""
                source_pht_verified = ""
                oba_score_val = loinc_score_val = mondo_score_val = hpo_score_val = omop_score_val = ""
                loinc_omop_resolution_status = ""
            else:
                cache_key = (var_name, slot, entity_type, phv)
                if cache_key not in suggestion_cache:
                    # Row wasn't covered by pre-population (shouldn't normally happen);
                    # compute on the spot with no dbGaP override, consistent with the
                    # pre-population fallback for unmatched phvs.
                    (omop_val, mondo_val, hpo_val, oba_val, entity_val, confidence_val, loinc_confidence_val,
                     oba_score_val, loinc_score_val, mondo_score_val, hpo_score_val, omop_score_val) = _agent_suggestion(
                        slot, entity_type, var_name, var_desc,
                        get_mondo_id, get_hpo_id, get_omop_concept_id,
                        get_rxnorm_id, get_loinc_id, extract_clinical_term, get_omop_route_id, get_oba_id,
                        get_normalizer_confidence, csv_curie, get_oba_id_with_score, get_loinc_id_with_score, get_drug_curie_override,
                        get_mondo_id_with_score, get_hpo_id_with_score, get_omop_concept_id_with_score,
                    )
                    loinc_val = ""
                    loinc_omop_concept_id = ""
                    loinc_omop_resolution_status = ""
                    if omop_val.startswith("LOINC:"):
                        loinc_val = omop_val
                        loinc_omop_concept_id, loinc_omop_resolution_status = _resolve_loinc_to_omop(omop_val, loinc_omop_map)
                        loinc_omop_concept_id = loinc_omop_concept_id or ""
                        omop_val = loinc_omop_concept_id
                    source_verified, source_name_verified, source_desc_verified, source_pht_verified = False, "", "", ""
                    suggestion_cache[cache_key] = (
                        omop_val, mondo_val, hpo_val, oba_val, entity_val, confidence_val, loinc_confidence_val,
                        loinc_val, loinc_omop_concept_id, source_verified, source_name_verified, source_desc_verified,
                        source_pht_verified, oba_score_val, loinc_score_val, mondo_score_val, hpo_score_val, omop_score_val,
                        loinc_omop_resolution_status,
                    )
                else:
                    (omop_val, mondo_val, hpo_val, oba_val, entity_val, confidence_val, loinc_confidence_val,
                     loinc_val, loinc_omop_concept_id, source_verified, source_name_verified, source_desc_verified,
                     source_pht_verified, oba_score_val, loinc_score_val, mondo_score_val, hpo_score_val,
                     omop_score_val, loinc_omop_resolution_status) = suggestion_cache[cache_key]

            out_row = dict(row)
            out_row["yaml_curie"] = yaml_curie_val
            out_row["yaml_match"] = yaml_match_val
            out_row["omop_maps_to"] = omop_val
            out_row["mondo_maps_to"] = mondo_val
            out_row["hpo_maps_to"] = hpo_val
            out_row["oba_maps_to"] = oba_val
            out_row["loinc_maps_to"] = loinc_val
            # Single best-guess CURIE, picked by comparing actual text-match
            # scores across whichever candidates survived suppression — not a
            # fixed MONDO > HPO > OBA > OMOP vocabulary order. Still not a
            # vocab-rule-aware decision — see generate_semantic_review.py's
            # _SLOT_VOCAB_RULES for that layer.
            priority_curie_val, priority_curie_score_val = _pick_priority_curie(
                mondo_val, hpo_val, oba_val, omop_val,
                mondo_score_val or 0.0, hpo_score_val or 0.0, oba_score_val or 0.0,
                omop_score_val or 0.0, loinc_score_val or 0.0,
            )
            out_row["priority_curie"] = priority_curie_val
            out_row["priority_curie_score"] = priority_curie_score_val
            out_row["mondo_score"] = mondo_score_val
            out_row["hpo_score"] = hpo_score_val
            out_row["oba_score"] = oba_score_val
            out_row["omop_score"] = omop_score_val
            out_row["loinc_score"] = loinc_score_val
            out_row["maps_to_entity_type"] = entity_val
            out_row["loinc_confidence"] = loinc_confidence_val
            out_row["suggestion_confidence"] = confidence_val
            out_row["loinc_omop_concept_id"] = loinc_omop_concept_id
            out_row["loinc_omop_resolution_status"] = loinc_omop_resolution_status
            out_row["source_verified"] = source_verified
            out_row["source_variable_name_verified"] = source_name_verified
            out_row["source_variable_description_verified"] = source_desc_verified
            out_row["source_pht_verified"] = source_pht_verified
            writer.writerow(out_row)

    for attempt in range(5):
        try:
            os.replace(tmp_path, OUTPUT_CSV)
            break
        except PermissionError:
            if attempt == 4:
                print(
                    f"\nERROR: {OUTPUT_CSV.name} is locked (open in another program) and "
                    f"could not be replaced after 5 tries. All results were computed "
                    f"successfully and are saved at:\n  {tmp_path}\n"
                    f"Close whatever has the file open, then rename/copy it into place — "
                    f"no need to re-run the pipeline.",
                    file=sys.stderr,
                )
                sys.exit(1)
            print(f"  {OUTPUT_CSV.name} is locked, retrying in 3s (attempt {attempt + 1}/5)...", file=sys.stderr)
            time.sleep(3)

    elapsed = datetime.now() - start_time
    total_sec = int(elapsed.total_seconds())
    h, rem = divmod(total_sec, 3600)
    m, s = divmod(rem, 60)
    elapsed_str = f"{h}h {m:02d}m {s:02d}s" if h else f"{m}m {s:02d}s"
    print(f"\nFinished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  (elapsed: {elapsed_str})", file=sys.stderr)
    print(f"Done. Output written to:\n  {OUTPUT_CSV}", file=sys.stderr)

    try:
        from pipeline_status import write_status
        write_status()
    except Exception as _e:
        print(f"Warning: could not update pipeline_status.json: {_e}", file=sys.stderr)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--study",
        default="COPDGene",
        choices=list(_STUDY_CONFIGS),
        metavar="STUDY",
        help=f"Study to process. Known: {list(_STUDY_CONFIGS)}. Default: COPDGene.",
    )
    parser.add_argument(
        "--no-agents",
        action="store_true",
        help="Skip API agent calls; only perform YAML spot-check.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=10,
        metavar="N",
        help="Number of parallel worker threads for agent calls (default: 10).",
    )
    args = parser.parse_args()
    _resolve_paths(args.study)
    main(no_agents=args.no_agents, workers=args.workers)
