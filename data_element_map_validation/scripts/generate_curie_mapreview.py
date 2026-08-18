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
                    "yaml_dir":   yaml_dir,
                }
    if not configs:
        configs["COPDGene"] = {
            "input_csv":  BASE_DIR / "bdc_study_input" / "COPDGene_curie.csv",
            "output_csv": BASE_DIR / "bdc_study_input" / "COPDGene_curie_mapreview.csv",
            "yaml_dir":   BASE_DIR.parent / "priority_variables_transform" / "COPDGene-ingest",
        }
        # BASE_DIR is data_element_map_validation/, so BASE_DIR.parent is the repo root
    return configs


_STUDY_CONFIGS = _load_study_configs()

# Defaults — overridden by _resolve_paths() once argparse runs
INPUT_CSV  = _STUDY_CONFIGS["COPDGene"]["input_csv"]
OUTPUT_CSV = _STUDY_CONFIGS["COPDGene"]["output_csv"]
YAML_DIR   = _STUDY_CONFIGS["COPDGene"]["yaml_dir"]


def _resolve_paths(study: str) -> None:
    global INPUT_CSV, OUTPUT_CSV, YAML_DIR
    cfg = _STUDY_CONFIGS.get(study)
    if cfg is None:
        print(f"Unknown study '{study}'. Known: {list(_STUDY_CONFIGS)}", file=sys.stderr)
        sys.exit(1)
    INPUT_CSV  = cfg["input_csv"]
    OUTPUT_CSV = cfg["output_csv"]
    YAML_DIR   = cfg["yaml_dir"]

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
    from mondo_agent import get_mondo_id, _extract_clinical_term
    from hpo_agent import get_hpo_id
    from omop_agent import get_omop_concept_id
    from rxnorm_agent import get_omop_concept_id as get_rxnorm_id
    from measurementObs_agent import get_loinc_id
    from meds_route_agent import get_omop_route_id
    from oba_agent import get_oba_id, get_oba_id_with_score
    from measurementObs_agent import get_loinc_id_with_score
    from curie_normalizer import confidence_label as get_normalizer_confidence
    return get_mondo_id, get_hpo_id, get_omop_concept_id, get_rxnorm_id, get_loinc_id, _extract_clinical_term, get_omop_route_id, get_oba_id, get_normalizer_confidence, get_oba_id_with_score, get_loinc_id_with_score


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
) -> tuple[str, str, str, str, str, str, str]:
    """Return (omop_maps_to, mondo_maps_to, hpo_maps_to, oba_maps_to,
    maps_to_entity_type, confidence, loinc_confidence).

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
        return "", "", "", "", "", "", ""

    omop_maps_to = ""
    mondo_maps_to = ""
    hpo_maps_to = ""
    oba_maps_to = ""
    maps_to_entity_type = ""
    confidence = ""
    loinc_confidence = ""

    try:
        if slot == "condition_concept":
            clean_query = extract_clinical_term(query)
            # Priority: MONDO → HPO → OMOP
            mondo_curie = get_mondo_id(clean_query)
            if mondo_curie:
                mondo_maps_to = mondo_curie
                maps_to_entity_type = "Condition"
                candidate = mondo_curie
            else:
                hp_curie = get_hpo_id(clean_query)
                if hp_curie:
                    hpo_maps_to = hp_curie
                    maps_to_entity_type = "Condition (HPO)"
                    candidate = hp_curie
                else:
                    omop_curie = get_omop_concept_id(clean_query)
                    if omop_curie:
                        omop_maps_to = omop_curie
                        maps_to_entity_type = "Condition (OMOP fallback)"
                    else:
                        maps_to_entity_type = "Condition"
                    candidate = ""

            if get_normalizer_confidence and candidate and csv_curie and candidate != csv_curie:
                confidence = get_normalizer_confidence(csv_curie, candidate)

        elif slot in ("observation_type", "observations") and entity_type in (
            "MeasurementObservation", "MeasurementObservationSet", "Observation"
        ):
            if get_loinc_id_with_score:
                loinc_id, loinc_score = get_loinc_id_with_score(query)
                omop_maps_to = loinc_id or ""
                if omop_maps_to:
                    loinc_confidence = _similarity_confidence_tier(loinc_score, "LOINC term")
            else:
                curie = get_loinc_id(query)
                omop_maps_to = curie or ""
            if slot == "observation_type":
                if get_oba_id_with_score:
                    oba_id, oba_score = get_oba_id_with_score(query)
                    oba_maps_to = oba_id or ""
                    if oba_maps_to and oba_maps_to != csv_curie:
                        confidence = _similarity_confidence_tier(oba_score, "OBA term")
                else:
                    oba_maps_to = get_oba_id(query) or ""
            maps_to_entity_type = "Measurement"

        elif slot == "procedure_concept":
            curie = get_omop_concept_id(query)
            omop_maps_to = curie or ""
            maps_to_entity_type = "Procedure"

        elif slot == "drug_concept":
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

    return omop_maps_to, mondo_maps_to, hpo_maps_to, oba_maps_to, maps_to_entity_type, confidence, loinc_confidence


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
        get_mondo_id = get_hpo_id = get_omop_concept_id = get_rxnorm_id = get_loinc_id = extract_clinical_term = get_omop_route_id = get_oba_id = get_normalizer_confidence = get_oba_id_with_score = get_loinc_id_with_score = None
        print("Running in --no-agents mode: YAML spot-check only.", file=sys.stderr)
    else:
        print("Loading agents ...", file=sys.stderr)
        get_mondo_id, get_hpo_id, get_omop_concept_id, get_rxnorm_id, get_loinc_id, extract_clinical_term, get_omop_route_id, get_oba_id, get_normalizer_confidence, get_oba_id_with_score, get_loinc_id_with_score = _import_agents()  # noqa: E501
        print("Agents loaded.", file=sys.stderr)

    start_time = datetime.now()
    print(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}", file=sys.stderr)

    # Read all input rows into memory first
    with open(INPUT_CSV, newline="", encoding="utf-8") as fin:
        reader = csv.DictReader(fin)
        all_rows = list(reader)
        orig_fields = reader.fieldnames or []
    total = len(all_rows)

    # Cache: (var_name, slot, entity_type) → (omop, mondo, hpo, oba, entity, confidence, loinc_confidence)
    suggestion_cache: dict[tuple, tuple] = {}

    if not no_agents:
        # Collect unique (var_name, slot, entity_type) keys with first-seen var_desc/csv_curie
        unique_keys: dict[tuple, tuple[str, str]] = {}
        for r in all_rows:
            vn  = r.get("Variable Name", "").strip()
            sl  = r.get("Slot", "").strip()
            et  = r.get("Entity Type", "").strip()
            vd  = r.get("Variable Description", "").strip()
            cc  = r.get("CURIE", "").strip()
            if vn and vn not in ADMIN_VARS and sl:
                key = (vn, sl, et)
                if key not in unique_keys:
                    unique_keys[key] = (vd, cc)

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
            (vn, sl, et), (vd, cc) = item
            result = _agent_suggestion(
                sl, et, vn, vd,
                get_mondo_id, get_hpo_id, get_omop_concept_id,
                get_rxnorm_id, get_loinc_id, extract_clinical_term, get_omop_route_id, get_oba_id,
                get_normalizer_confidence, cc, get_oba_id_with_score, get_loinc_id_with_score,
            )
            with cache_lock:
                suggestion_cache[(vn, sl, et)] = result
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
        "maps_to_entity_type",
        "suggestion_confidence",
        "loinc_confidence",
    ]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as fout:
        writer = csv.DictWriter(fout, fieldnames=new_fields)
        writer.writeheader()

        for row in all_rows:
            var_name    = row.get("Variable Name", "").strip()
            var_desc    = row.get("Variable Description", "").strip()
            slot        = row.get("Slot", "").strip()
            entity_type = row.get("Entity Type", "").strip()
            csv_curie   = row.get("CURIE", "").strip()
            yaml_file   = row.get("YAML File", "").strip()

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
            else:
                cache_key = (var_name, slot, entity_type)
                if cache_key in suggestion_cache:
                    omop_val, mondo_val, hpo_val, oba_val, entity_val, confidence_val, loinc_confidence_val = suggestion_cache[cache_key]
                else:
                    omop_val, mondo_val, hpo_val, oba_val, entity_val, confidence_val, loinc_confidence_val = _agent_suggestion(
                        slot, entity_type, var_name, var_desc,
                        get_mondo_id, get_hpo_id, get_omop_concept_id,
                        get_rxnorm_id, get_loinc_id, extract_clinical_term, get_omop_route_id, get_oba_id,
                        get_normalizer_confidence, csv_curie, get_oba_id_with_score, get_loinc_id_with_score,
                    )
                    suggestion_cache[cache_key] = (omop_val, mondo_val, hpo_val, oba_val, entity_val, confidence_val, loinc_confidence_val)

            out_row = dict(row)
            out_row["yaml_curie"] = yaml_curie_val
            out_row["yaml_match"] = yaml_match_val
            out_row["omop_maps_to"] = omop_val
            out_row["mondo_maps_to"] = mondo_val
            out_row["hpo_maps_to"] = hpo_val
            out_row["oba_maps_to"] = oba_val
            out_row["maps_to_entity_type"] = entity_val
            out_row["loinc_confidence"] = loinc_confidence_val
            out_row["suggestion_confidence"] = confidence_val
            writer.writerow(out_row)

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
