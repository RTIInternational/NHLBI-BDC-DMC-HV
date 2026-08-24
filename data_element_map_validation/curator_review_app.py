#!/usr/bin/env python3
"""
Semantic Review Curator — multi-study CURIE change-request web app.

Usage:
    python -m streamlit run curator_review_app.py
"""

import csv
import json
import re
import subprocess
import sys
import threading
import time
from datetime import date
from pathlib import Path

import streamlit as st

# ── Base paths ────────────────────────────────────────────────────────────────
_HERE        = Path(__file__).parent          # data_element_map_validation/
_SCRIPTS_DIR = _HERE / "scripts"              # data_element_map_validation/scripts/
DATA_ROOT    = _HERE.parent
REVIEW_OUT   = _HERE / "valueset_mapping_review_output"
LOG_DIR      = REVIEW_OUT / "change_log"
PENDING_DIR  = REVIEW_OUT / "pending_change"


def _pending_path(study: str) -> Path:
    return PENDING_DIR / f"{_file_key(study)}_pending_changes.json"


# ── Study registry — loaded from CSV ─────────────────────────────────────────
_REGISTRY_CSV = _HERE / "bdc_study_input" / "BDC_registered_study_for_semantic_review.csv"


def _file_key(short_name: str) -> str:
    """Filesystem-safe stem: 'HCHS/SOL' → 'HCHS_SOL'."""
    return short_name.replace("/", "_").replace(" ", "_")


def _find_review_md(fk: str) -> Path:
    """Return most-recent generated review MD, or today-dated expected path if none exists."""
    matches = sorted(REVIEW_OUT.glob(f"{fk}_semantic_review_v*.md"), reverse=True)
    return matches[0] if matches else (
        REVIEW_OUT / f"{fk}_semantic_review_v{date.today().strftime('%Y_%m%d')}.md"
    )


def _find_summary_md(fk: str) -> Path | None:
    """Return most-recent study-prefixed summary MD, or None if not yet generated."""
    matches = sorted(REVIEW_OUT.glob(f"{fk}_semantic_validator_summary_v*.md"), reverse=True)
    return matches[0] if matches else None


def _load_study_registry() -> dict[str, dict]:
    """Build STUDIES dict from BDC_registered_study_for_semantic_review.csv."""
    if not _REGISTRY_CSV.exists():
        # Minimal fallback so the app still starts
        return {
            "COPDGene": {
                "label": "COPDGene", "description": "Genetic Epidemiology of COPD",
                "file_key": "COPDGene",
                "review_md":     _find_review_md("COPDGene"),
                "curie_csv":     _HERE / "bdc_study_input" / "COPDGene_curie.csv",
                "mapreview_csv": _HERE / "bdc_study_input" / "COPDGene_curie_mapreview.csv",
                "yaml_dir":      DATA_ROOT / "priority_variables_transform" / "COPDGene-ingest",
            },
        }
    studies: dict[str, dict] = {}
    with open(_REGISTRY_CSV, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            short = row["cohort_study_short_name"].strip()
            desc_raw = row["cohort_study_description"].strip()
            desc = desc_raw.split(" | ")[0].strip() if " | " in desc_raw else desc_raw
            fk = _file_key(short)
            # Resolve yaml_file_path relative to the registry CSV's directory
            yaml_rel = row.get("yaml_file_path", "").strip()
            yaml_dir = (_REGISTRY_CSV.parent / yaml_rel).resolve() if yaml_rel else (
                DATA_ROOT / "priority_variables_transform" / f"{fk}-ingest"
            )
            studies[short] = {
                "label":         short,
                "description":   desc,
                "file_key":      fk,
                "review_md":     _find_review_md(fk),
                "curie_csv":     _HERE / "bdc_study_input" / f"{fk}_curie.csv",
                "mapreview_csv": _HERE / "bdc_study_input" / f"{fk}_curie_mapreview.csv",
                "yaml_dir":      yaml_dir,
            }
    return studies


# Evaluated each Streamlit rerun so newly-generated review MDs are discovered automatically
STUDIES: dict[str, dict] = _load_study_registry()

# ── CURIE utilities ───────────────────────────────────────────────────────────
_CURIE_RE = re.compile(r"`([A-Z][A-Z0-9_]*:[A-Z0-9._-]+)`|([A-Z][A-Z0-9_]*:[A-Z0-9._-]+)")

_CURIE_URLS: list[tuple[str, str]] = [
    ("MONDO",   "https://www.ebi.ac.uk/ols4/ontologies/mondo/terms?obo_id={c}"),
    ("HP",      "https://www.ebi.ac.uk/ols4/ontologies/hp/terms?obo_id={c}"),
    ("OBA",     "https://www.ebi.ac.uk/ols4/ontologies/oba/terms?obo_id={c}"),
    ("SNOMED",  "https://www.ebi.ac.uk/ols4/ontologies/snomed/terms?obo_id={c}"),
    ("LOINC",   "https://loinc.org/{id}"),
    ("OMOP",    "https://athena.ohdsi.org/search-terms/terms/{id}"),
    ("ATC",     "https://www.whocc.no/atc_ddd_index/?code={id}"),
    ("RXNORM",  "https://mor.nlm.nih.gov/RxNav/search?searchBy=RXCUI&searchTerm={id}"),
    ("MESH",    "https://meshb.nlm.nih.gov/record/ui?ui={id}"),
    ("UBERON",  "https://www.ebi.ac.uk/ols4/ontologies/uberon/terms?obo_id={c}"),
]

_PREFIX_ENTITY: list[tuple[str, str]] = [
    ("MONDO",   "Condition"),
    ("HP",      "Condition (HPO)"),
    ("LOINC",   "Measurement"),
    ("OBA",     "Measurement"),
    ("ATC",     "DrugExposure"),
    ("RXNORM",  "DrugExposure"),
    ("SNOMED",  "DrugExposure"),
    ("MESH",    "DrugExposure"),
    ("OMOP",    "Observation"),
    ("UBERON",  "AnatomicalSite"),
]

_VALID_PREFIXES = {p for p, _ in _PREFIX_ENTITY} | {"LOINC", "ATC", "RXNORM", "MESH"}


def _curie_to_url(curie: str) -> str:
    c  = curie.strip("`").strip()
    up = c.split(":")[0].upper()
    cid = c.split(":", 1)[1] if ":" in c else ""
    for prefix, tmpl in _CURIE_URLS:
        if up == prefix:
            return tmpl.format(c=c, id=cid)
    return ""


def _infer_entity_type(curie: str) -> str:
    up = curie.strip().split(":")[0].upper()
    for prefix, etype in _PREFIX_ENTITY:
        if up == prefix:
            return etype
    return ""


def _validate_curie(curie: str) -> str:
    curie = curie.strip()
    if not curie:
        return "CURIE cannot be empty."
    if ":" not in curie:
        return (
            f"Missing prefix — use PREFIX:ID format (e.g. MONDO:0004849). "
            f"Recognized prefixes: {', '.join(sorted(_VALID_PREFIXES))}"
        )
    prefix = curie.split(":")[0].upper()
    if prefix not in _VALID_PREFIXES:
        return (
            f"Unrecognized prefix '{curie.split(':')[0]}:'. "
            f"Recognized: {', '.join(sorted(_VALID_PREFIXES))}"
        )
    return ""


def _linkify(text: str) -> str:
    """Replace CURIE patterns with HTML anchor tags (new tab)."""
    # Strip backtick wrappers around CURIEs so they don't produce malformed HTML
    text = re.sub(r'`([A-Z][A-Z0-9_]*:[A-Z0-9._-]+)`', r'\1', text)
    def _sub(m: re.Match) -> str:
        curie = m.group(1) or m.group(2)
        url = _curie_to_url(curie)
        if url:
            return f'<a href="{url}" target="_blank"><code>{curie}</code></a>'
        return m.group(0)
    return _CURIE_RE.sub(_sub, text)


def _info_box(text: str) -> None:
    """Render linkified text in a styled info box (HTML-safe)."""
    st.markdown(
        f'<div style="background:#e8f4f8;padding:10px 14px;border-radius:4px;'
        f'border-left:4px solid #4a90e2;font-size:0.9em;line-height:1.6">'
        f'{_linkify(text)}</div>',
        unsafe_allow_html=True,
    )


def _curie_link_md(curie: str, label: str = "") -> None:
    url = _curie_to_url(curie)
    prefix = f"**{label}:** " if label else ""
    if url:
        st.markdown(f'{prefix}<a href="{url}" target="_blank"><code>{curie}</code></a>', unsafe_allow_html=True)
    else:
        if prefix:
            st.markdown(prefix, unsafe_allow_html=True)
        st.code(curie, language=None)


def _extract_confidence_notes(validator_text: str) -> list[str]:
    """Pull out confidence/vocab-mismatch caveat sentences (e.g. '⚠ **Normalizer
    confidence**: needs review — normalizer resolves to a different concept.')
    so they can be shown alongside the vocab-labeled CURIE links from
    get_terminology_matches(). Without this, a suggestion the system itself
    already flagged as low-confidence or wrong-vocabulary displays as a clean,
    unqualified recommendation."""
    return re.findall(r"(?:✅|⚠)\s*\*\*[^*]+\*\*:[^.]*\.", validator_text)


def _unescape_md(s: str) -> str:
    return re.sub(r"\\(.)", r"\1", s.strip())


# ── MD parsing — Confirmed Findings only ──────────────────────────────────────
_CONF_HEADERS = [
    "Priority", "File", "Final issue", "Evidence to confirm",
    "Recommended action", "Confidence", "Reviewer",
    "Source alignment", "semantic validator review",
]


def _parse_md_table(lines: list[str], fallback_headers: list[str]) -> list[dict]:
    """Parse a markdown table, using the table's OWN header row rather than
    trusting a hardcoded column list. generate_semantic_review.py's schema has
    changed over time (e.g. adding a PHV column) — different studies' MD files
    on disk may be at different schema versions, so the header must be read
    from each file rather than assumed, or old/new files silently misalign
    when zipped against a fixed-length header list."""
    table_lines = [ln.strip() for ln in lines if ln.strip().startswith("|")]
    if not table_lines:
        return []

    headers = [_unescape_md(c).strip() for c in table_lines[0].strip("|").split("|")]
    if not headers or headers[0] != fallback_headers[0]:
        headers = fallback_headers  # detection failed unexpectedly — fall back

    rows = []
    for line in table_lines[1:]:
        if re.match(r"^\|[\s:|-]+\|", line):
            continue  # separator row
        cells = [_unescape_md(c) for c in line.strip("|").split("|")]
        if len(cells) >= len(headers):
            row_dict = dict(zip(headers, cells))
            if "Priority" in row_dict:
                row_dict["Priority"] = re.sub(r"\*+", "", row_dict["Priority"]).strip()
            rows.append(row_dict)
    return rows


@st.cache_data
def load_review_rows(study: str) -> list[dict]:
    path = STUDIES[study]["review_md"]
    if not path.exists():
        return []
    conf_lines: list[str] = []
    in_conf = False
    for line in path.read_text(encoding="utf-8").splitlines():
        # Accept both legacy "Final Confirmed Findings" and new "Reviewer Confirmed Findings"
        if line.startswith("## ") and "Confirmed Findings" in line:
            in_conf = True
        elif line.startswith("## "):
            in_conf = False
        if in_conf:
            conf_lines.append(line)
    return _parse_md_table(conf_lines, _CONF_HEADERS)


@st.cache_data
def load_curie_csv(study: str) -> tuple[list[str], list[dict]]:
    path = STUDIES[study]["curie_csv"]
    if not path.exists():
        return [], []
    with open(path, newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        return list(r.fieldnames or []), list(r)


@st.cache_data
def load_mapreview_csv(study: str) -> tuple[list[str], list[dict]]:
    path = STUDIES[study]["mapreview_csv"]
    if not path.exists():
        return [], []
    with open(path, newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        return list(r.fieldnames or []), list(r)


# Slot names that carry unit information in measurement YAMLs
_UNIT_SLOT_NAMES = {"unit_concept", "unit", "unit_source_value"}


def _curie_csv_has_unit_column(study: str) -> bool:
    fieldnames, _ = load_curie_csv(study)
    return any(f.strip().lower() == "unit" for f in fieldnames)


def get_current_curies(study: str, yaml_file: str, slot: str) -> list[str]:
    _, rows = load_curie_csv(study)
    fname = Path(yaml_file).name
    return sorted({
        r["CURIE"] for r in rows
        if r.get("YAML File") == fname and r.get("Slot") == slot and r.get("CURIE")
    })


def get_priority_curies(study: str, yaml_file: str, slot: str, phv: str = "") -> list[str]:
    """Distinct priority_curie values (mapreview.csv's MONDO>HPO>OBA>OMOP best-guess
    cascade) for this (yaml_file, slot) — read directly from the structured column
    rather than regex-parsed out of the validator review text, so it can't drift
    from what generate_curie_mapreview.py actually computed.

    When phv is known, narrows to that exact variable — a (yaml_file, slot) pair
    routinely spans several distinct source variables (the MeasurementObservationSet
    cross-product pattern), so pooling here would silently mix in another variable's
    unrelated best guess. Falls back to the pooled set only when phv is unknown."""
    _, rows = load_mapreview_csv(study)
    fname = Path(yaml_file).name
    matches = [r for r in rows if r.get("YAML File") == fname and r.get("Slot") == slot]
    if phv:
        # Strict: this variable's own suggestion only, even if that means none —
        # falling back to the pooled set here would silently borrow another
        # variable's unrelated best guess for a PHV that genuinely has no match.
        matches = [r for r in matches if r.get("PHV", "").strip() == phv]
    return sorted({r["priority_curie"] for r in matches if r.get("priority_curie")})


def get_priority_curie_context(study: str, yaml_file: str, slot: str, phv: str) -> tuple[list[str], bool]:
    """Priority CURIE(s) for display, plus whether they're an ambiguous pooled guess.

    get_priority_curies() falls back to pooling every variable sharing (yaml_file,
    slot) when phv is unknown — harmless when only one variable lives there, but
    actively misleading when several do (the MeasurementObservationSet cross-product
    pattern): the pooled CURIEs can belong to an unrelated sibling variable entirely
    (e.g. a finding about the asthma block's logic showing another variable's
    "sick building syndrome" CURIE as if it were the recommendation). Flag that case
    so callers can defer to the per-variable provenance table instead of presenting
    a single confident-looking answer that doesn't belong to this row."""
    prio = get_priority_curies(study, yaml_file, slot, phv)
    ambiguous = False
    if prio and not phv:
        n_vars = len({v["phv"] for v in get_variable_provenance(study, yaml_file, slot)})
        ambiguous = n_vars > 1
    return prio, ambiguous


_TERMINOLOGY_COLUMNS = [
    ("MONDO", "mondo_maps_to"),
    ("HPO", "hpo_maps_to"),
    ("OBA", "oba_maps_to"),
    ("OMOP", "omop_maps_to"),
    ("LOINC", "loinc_maps_to"),
]


_MIN_PRIORITY_SCORE = 0.6  # mirrors generate_curie_mapreview.py's _MIN_PRIORITY_SCORE
_TERMINOLOGY_SCORE_COLUMNS = {
    "MONDO": "mondo_score", "HPO": "hpo_score", "OBA": "oba_score",
    "OMOP": "omop_score", "LOINC": "loinc_score",
}


def get_terminology_matches(study: str, yaml_file: str, slot: str, phv: str) -> list[tuple[str, str, bool]]:
    """Per-vocabulary candidates for this exact variable — (vocab_label, curie,
    is_weak) triples for whichever of mondo_maps_to/hpo_maps_to/oba_maps_to/
    omop_maps_to/loinc_maps_to are populated. loinc_maps_to is the raw LOINC
    code the measurementObs agent found (kept as its own audit column even
    when its own match was weak) — shown here as its own entry so a curator
    can see and click through to the actual LOINC term, not just its
    OMOP-resolved concept.

    Seeing the same real-world concept confirmed across independent terminologies
    (e.g. OBA and OMOP both landing on "waist to hip ratio") is valuable to a
    curator on its own — this reads the structured per-vocab columns directly
    rather than regex-parsing the validator text, so results can't drift and
    can't get mislabeled by vocab. Strictly PHV-scoped — no fallback pooling,
    per the lesson from priority_curie.

    is_weak mirrors generate_curie_mapreview.py's _pick_priority_curie eligibility
    floor: a candidate below _MIN_PRIORITY_SCORE can't win priority_curie there,
    but it isn't deleted from its own *_maps_to column either — the curator
    should still see it, just clearly labeled as a weak match rather than
    presented at the same weight as a confident one. OMOP's score falls back to
    loinc_score when unset, since a measurement row's OMOP candidate is resolved
    through the LOINC agent (see generate_curie_mapreview.py's LOINC→OMOP path)."""
    if not phv:
        return []
    _, rows = load_mapreview_csv(study)
    fname = Path(yaml_file).name
    for r in rows:
        if r.get("YAML File") != fname or r.get("Slot") != slot or r.get("PHV", "").strip() != phv:
            continue
        results = []
        for label, col in _TERMINOLOGY_COLUMNS:
            curie = r.get(col, "")
            if not curie:
                continue
            score_str = r.get(_TERMINOLOGY_SCORE_COLUMNS[label], "")
            score = float(score_str) if score_str else 0.0
            if label == "OMOP" and not score:
                loinc_score_str = r.get("loinc_score", "")
                score = float(loinc_score_str) if loinc_score_str else 0.0
            is_weak = bool(score) and score < _MIN_PRIORITY_SCORE
            results.append((label, curie, is_weak))
        return results
    return []


def get_loinc_omop_resolution_caveat(study: str, yaml_file: str, slot: str, phv: str) -> str:
    """Return an honest caveat when a LOINC candidate exists but its OMOP
    resolution is blank because the lookup itself failed (Atlas API
    timeout/error) — never returns anything for a confirmed "no exact match".

    Without this, a blank OMOP candidate caused by a technical failure is
    visually indistinguishable from one where the agent genuinely checked and
    found nothing — a curator (or the priority_curie scoring logic) can't tell
    "unresolved" from "confirmed absent" otherwise. See
    generate_curie_mapreview.py's loinc_omop_resolution_status column and
    omop_agent.get_omop_concept_id_from_loinc_with_status()."""
    if not phv:
        return ""
    _, rows = load_mapreview_csv(study)
    fname = Path(yaml_file).name
    for r in rows:
        if r.get("YAML File") != fname or r.get("Slot") != slot or r.get("PHV", "").strip() != phv:
            continue
        if r.get("loinc_omop_resolution_status", "") == "api_error":
            loinc_code = r.get("loinc_maps_to", "")
            return (
                f"⚠ LOINC→OMOP lookup for `{loinc_code}` failed (API timeout/error) — "
                "this is NOT a confirmed absence of a match, just an unresolved lookup. "
                "Re-run Step 1 for this study to retry."
            )
        return ""
    return ""


def get_curie_csv_rows_for_file(study: str, yaml_file: str, slot: str) -> list[dict]:
    """Return all curie CSV rows matching yaml_file (basename) + slot."""
    _, rows = load_curie_csv(study)
    fname = Path(yaml_file).name
    return [r for r in rows if r.get("YAML File") == fname and r.get("Slot") == slot]


def get_variable_provenance(study: str, yaml_file: str, slot: str) -> list[dict]:
    """One row per distinct PHV mapped to (yaml_file, slot) — the full breakdown of
    which real study variables underlie this slot. A single (file, slot) pair
    routinely spans several genuinely distinct variables (the MeasurementObservationSet
    cross-product pattern behind both the corruption incident and the findings-pooling
    bug fixed today) — this makes that visible directly in the UI instead of leaving it
    implicit in a concatenated validator-text paragraph."""
    _, rows = load_mapreview_csv(study)
    fname = Path(yaml_file).name
    seen: dict[str, dict] = {}
    for r in rows:
        if r.get("YAML File") != fname or r.get("Slot") != slot:
            continue
        phv = r.get("PHV", "").strip()
        if not phv or phv in seen:
            continue
        seen[phv] = {
            "phv":            phv,
            "variable_name":  r.get("Variable Name", ""),
            "description":    r.get("Variable Description", ""),
            "current_curie":  r.get("CURIE", ""),
            "priority_curie": r.get("priority_curie", ""),
            "source_verified": r.get("source_verified", "") == "True",
        }
    return sorted(seen.values(), key=lambda x: x["variable_name"])


def _render_provenance_table(study: str, yaml_file: str, slot: str) -> None:
    all_prov = get_variable_provenance(study, yaml_file, slot)
    # Rows with no agent suggestion at all add no decision-relevant information here
    # (they're already visible in the curie CSV) — drop them to keep this table
    # focused on variables that actually need a curator's attention.
    prov = [v for v in all_prov if v["priority_curie"]]
    if len(prov) < 2:
        return  # only worth showing when the slot genuinely spans >1 variable
    n_dropped = len(all_prov) - len(prov)
    dropped_note = f" ({n_dropped} more with no agent suggestion, not shown)" if n_dropped else ""
    st.markdown(
        f"**📋 Source variables mapped to `{slot}` in this file** "
        f"({len(prov)} with a suggestion{dropped_note}):"
    )
    lines = [
        "| PHV | Variable Name | Description | Current CURIE | Priority CURIE | dbGaP verified |",
        "|---|---|---|---|---|---|",
    ]
    for v in prov:
        desc = (v["description"] or "").replace("|", "\\|")[:60]
        verified = "✓" if v["source_verified"] else ""
        current_cell = _linkify(f"`{v['current_curie']}`") if v["current_curie"] else "—"
        priority_cell = _linkify(f"`{v['priority_curie']}`") if v["priority_curie"] else "—"
        lines.append(
            f"| `{v['phv']}` | {v['variable_name']} | {desc} | "
            f"{current_cell} | {priority_cell} | {verified} |"
        )
    st.markdown("\n".join(lines), unsafe_allow_html=True)


def _yaml_has_family_history_blocks(study: str, yaml_file: str) -> bool:
    """Return True if the YAML file contains any non-ONESELF relationship_to_participant block."""
    yaml_path = STUDIES[study]["yaml_dir"] / Path(yaml_file).name
    try:
        return bool(_REL_NON_SELF_RE.search(yaml_path.read_text(encoding="utf-8")))
    except OSError:
        return False


# Slots for which OBA live suggestions are shown in the Details panel.
_OBA_SLOTS = frozenset({"observation_type", "observations"})


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_oba_suggestions(query: str, max_results: int = 5) -> list[tuple[str, str]]:
    """Return [(obo_id, label), ...] from OLS4 OBA search. Cached 1 hour."""
    import urllib.request
    import urllib.parse
    import json as _json

    if not query.strip():
        return []
    params = urllib.parse.urlencode({
        "q":          query.strip(),
        "ontology":   "oba",
        "rows":       max_results,
        "fieldList":  "obo_id,label",
    })
    url = f"https://www.ebi.ac.uk/ols4/api/search?{params}"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
        return [
            (d["obo_id"], d.get("label", d["obo_id"]))
            for d in data.get("response", {}).get("docs", [])
            if d.get("obo_id")
        ]
    except Exception:
        return []


def _render_var_row_caption(r: dict) -> None:
    """One caption line showing PHV, Variable Name, and Variable Description (explicitly blank if missing)."""
    phv  = r.get("PHV", "").strip()
    name = r.get("Variable Name", "").strip()
    desc = r.get("Variable Description", "").strip()
    parts = []
    if phv:
        parts.append(f"`{phv}`")
    parts.append(f"**Variable:** {name if name else '_blank_'}")
    parts.append(f"**Description:** {desc if desc else '_blank_'}")
    st.caption("↳ " + " · ".join(parts))


def _render_curies_with_vars(study: str, yaml_file: str, slot: str, curies: list[str]) -> None:
    """Show CURIE links followed by variable metadata (PHV, name, description) from curie CSV.

    Also shows rows where CURIE is blank, labelled explicitly.
    """
    csv_rows = get_curie_csv_rows_for_file(study, yaml_file, slot)
    by_curie: dict[str, list[dict]] = {}
    for r in csv_rows:
        by_curie.setdefault(r.get("CURIE", "").strip(), []).append(r)
    for c in curies:
        _curie_link_md(c)
        for r in by_curie.get(c, []):
            _render_var_row_caption(r)
    # Rows where CURIE column is blank
    for r in by_curie.get("", []):
        st.caption("_CURIE is blank:_")
        _render_var_row_caption(r)


def _check_yaml_slot(
    study: str, yaml_file: str, slot: str
) -> tuple[bool, bool, list[str], dict[str, list[str]], list[str]]:
    """Read YAML directly and scan all entity types and slots.

    Returns (yaml_exists, slot_found, curie_values, all_slots, entity_types).
      all_slots    — {slot_name: [unique curie values]} across all classes
      entity_types — class names found (e.g. MeasurementObservation, DrugExposure)
    Handles: list-of-blocks YAML, direct value, value_mappings,
             nested object_derivations (e.g. value_quantity → unit).
    Excludes slots that carry PHV/expr references rather than ontology CURIEs.
    """
    _NON_CURIE_SLOTS = {"associated_participant", "associated_visit",
                        "age_at_observation", "value_decimal", "value_integer",
                        "value_boolean", "value_string"}

    yaml_path = STUDIES[study]["yaml_dir"] / Path(yaml_file).name
    if not yaml_path.exists():
        return False, False, [], {}, []
    try:
        import yaml as _yaml
        raw = _yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        # YAML may be a list of blocks or a single dict
        blocks: list[dict] = raw if isinstance(raw, list) else [raw] if raw else []

        all_slots: dict[str, list[str]] = {}
        entity_types: list[str] = []

        def _scan_slot_derivations(slot_derivs: dict) -> None:
            for s, s_data in (slot_derivs or {}).items():
                if s in _NON_CURIE_SLOTS:
                    continue
                s_data = s_data or {}
                # Direct value
                val = s_data.get("value")
                if val and not str(val).startswith("{"):
                    all_slots.setdefault(s, []).append(str(val))
                # CURIEs embedded in case() expressions: case(({phv} == 1, "ATC:C10A"))
                expr = s_data.get("expr")
                if expr:
                    for emb in re.findall(r'\b([A-Z][A-Z0-9_]*:[A-Z0-9.]+)\b', str(expr)):
                        all_slots.setdefault(s, []).append(emb)
                # Coded value_mappings
                for mapping in s_data.get("value_mappings", []) or []:
                    mval = (mapping or {}).get("value")
                    if mval:
                        all_slots.setdefault(s, []).append(str(mval))
                # Nested object_derivations (e.g. value_quantity → Quantity → unit)
                for obj_block in s_data.get("object_derivations", []) or []:
                    for inner_class in (obj_block or {}).get("class_derivations", {}).values():
                        _scan_slot_derivations(
                            (inner_class or {}).get("slot_derivations", {})
                        )

        for block in blocks:
            for class_name, class_data in (block or {}).get("class_derivations", {}).items():
                if class_name not in entity_types:
                    entity_types.append(class_name)
                _scan_slot_derivations((class_data or {}).get("slot_derivations", {}))

        # Deduplicate preserving order
        all_slots = {s: list(dict.fromkeys(vs)) for s, vs in all_slots.items()}
        curies = all_slots.get(slot, [])
        return True, bool(curies), curies, all_slots, entity_types
    except Exception:
        return True, False, [], {}, []


def _render_curie_not_in_mapreview(study: str, yaml_file: str, slot: str) -> None:
    """Show diagnostic when get_current_curies() returns empty."""
    yaml_exists, slot_found, yaml_curies, all_slots, entity_types = _check_yaml_slot(
        study, yaml_file, slot
    )
    fname = Path(yaml_file).name
    curie_csv_name = STUDIES[study]["curie_csv"].name

    if not yaml_exists:
        st.warning(f"`{fname}` not found in ingest directory — YAML has not been created for this study.")
        return

    if entity_types:
        st.caption(f"_Entity type(s) in YAML: {', '.join(f'`{e}`' for e in entity_types)}_")

    # Measurement-specific: show unit info and flag missing Unit column in curie CSV
    if any("measurement" in e.lower() for e in entity_types):
        unit_parts: list[str] = []
        for uslot in sorted(_UNIT_SLOT_NAMES & all_slots.keys()):
            for uval in all_slots[uslot]:
                unit_parts.append(f"`{uslot}` = `{uval}`")
        if unit_parts:
            st.caption("**Unit info from YAML:** " + " · ".join(unit_parts))
        else:
            st.caption("_No unit slot found in YAML — unit may not be mapped yet._")

        if not _curie_csv_has_unit_column(study):
            st.warning(
                f"⚠ **`Unit` column missing from `{STUDIES[study]['curie_csv'].name}`.**  \n"
                "For measurement variables, the unit convention (e.g. FEU vs DDU, mg/L vs µg/mL) "
                "and specimen type (plasma vs blood) determine which LOINC code is correct.  \n"
                "Adding a `Unit` column to the curie CSV would allow the mapreview agent to "
                "suggest the correct LOINC disambiguation automatically."
            )

    if slot_found:
        st.caption("_(Read directly from YAML — not yet in curie CSV)_")
        for c in yaml_curies:
            _curie_link_md(c)
        st.caption(
            f"⚠ `{fname}` is missing from `{curie_csv_name}`. "
            f"To fix: add this file with slot `{slot}` and its CURIE to the curie CSV, "
            f"then re-run **Step 1** (mapreview)."
        )
    elif all_slots:
        st.caption(
            f"_Inferred slot `{slot}` not found — actual slots in `{fname}`:_"
        )
        for actual_slot, actual_curies in sorted(all_slots.items()):
            st.markdown(f"**`{actual_slot}`**")
            for c in actual_curies:
                _curie_link_md(c)
        st.caption(
            "The slot type above was inferred from the review text and may not match the YAML. "
            "Use the actual slots shown above when entering a change request."
        )
    else:
        st.caption(f"`{fname}` exists but no CURIE slot values were found.")
        st.caption(
            "The YAML may not yet have concept mappings defined, "
            "or it uses a structure not yet supported by this scanner."
        )


# ── Pending tracking ──────────────────────────────────────────────────────────
def _load_pending(study: str) -> dict:
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    dest = _pending_path(study)
    # Migrate from old unsegregated file if study-specific file doesn't exist yet
    if not dest.exists():
        for old in (PENDING_DIR / "pending_changes.json",
                    REVIEW_OUT / "pending_changes.json",
                    REVIEW_OUT / "change_requests.json"):
            if old.exists():
                all_data = json.loads(old.read_text(encoding="utf-8"))
                # Keep only entries that belong to this study
                study_data = {k: v for k, v in all_data.items()
                              if v.get("study", study) == study}
                if study_data:
                    dest.write_text(
                        json.dumps(study_data, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                break
    if dest.exists():
        return json.loads(dest.read_text(encoding="utf-8"))
    return {}


def _save_pending(data: dict, study: str) -> None:
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    _pending_path(study).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ── Change-log helpers ────────────────────────────────────────────────────────
def _next_log_path(study: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().strftime("%Y%m%d")
    n = 1
    while True:
        p = LOG_DIR / f"{_file_key(study)}_change_request_{today}_{n:02d}.json"
        if not p.exists():
            return p
        n += 1


def _list_change_logs(study: str) -> list[Path]:
    if not LOG_DIR.exists():
        return []
    return sorted(LOG_DIR.glob(f"{_file_key(study)}_change_request_*.json"), reverse=True)


# ── Change-request CSV ────────────────────────────────────────────────────────
_CR_EXTRA = [
    "changerequest_maps_to_curie",
    "changerequest_maps_to_entity_type",
    "changerequest_maps_to_curie_hyperlink",
]


def _rebuild_cr_csv(study: str, pending: dict) -> tuple[Path, int]:
    mr_fields, mr_rows = load_mapreview_csv(study)
    mr_index: dict[tuple, list[dict]] = {}
    for r in mr_rows:
        key = (r.get("YAML File", ""), r.get("Slot", ""))
        mr_index.setdefault(key, []).append(r)

    fieldnames = mr_fields + _CR_EXTRA
    cr_rows: list[dict] = []
    for val in pending.values():
        new_curie = val.get("change_request", "").strip()
        if not new_curie or val.get("applied"):
            continue
        slot    = val.get("slot", "")
        yf_list = val.get("yaml_files", [])
        etype   = _infer_entity_type(new_curie)
        url     = _curie_to_url(new_curie)
        for yf in yf_list:
            for base in (mr_index.get((yf, slot)) or [{}]):
                row = dict(base)
                row.update({
                    "YAML File": yf, "Slot": slot,
                    "changerequest_maps_to_curie":           new_curie,
                    "changerequest_maps_to_entity_type":     etype,
                    "changerequest_maps_to_curie_hyperlink": url,
                })
                cr_rows.append(row)

    today = date.today().strftime("%Y%m%d")
    cr_path = REVIEW_OUT / f"{study}_curie_changerequest_v{today}.csv"
    if cr_rows:
        with open(cr_path, "w", newline="", encoding="utf-8-sig") as f:
            csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore").writeheader()
            csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore").writerows(cr_rows)
    return cr_path, len(cr_rows)


# ── YAML / CSV apply ──────────────────────────────────────────────────────────
# Detects blocks whose relationship_to_participant is not ONESELF — used only
# for the informational warning in the Details panel; _apply_yaml updates all
# blocks uniformly (family-history blocks share the same concept CURIE as the
# self-report blocks in BDCHM, so all blocks should be updated together).
_REL_NON_SELF_RE = re.compile(
    r"\brelationship_to_participant:\s*\n[ \t]+value:\s+(?!ONESELF\b)\S+"
)

# Slots that must never be updated via submit because each block intentionally
# holds a different value — uniform file-wide replacement would corrupt the YAML.
_SUBMIT_BLOCKED_SLOTS = frozenset({"relationship_to_participant"})

_BLOCK_MARKER_RE = re.compile(r"^([ \t]*)- class_derivations:", re.MULTILINE)


def _find_block_for_phv(text: str, slot: str, phv: str) -> tuple[int, int, int] | None:
    """Return (block_start, block_end, line_number) for the single smallest
    "- class_derivations:" block that both (a) directly contains a `{slot}:`
    value/expr line and (b) contains *phv* anywhere in its span (including
    nested descendant blocks, e.g. a sibling Quantity sub-block one level
    deeper that holds the identifying phv via value_decimal/expr while the
    slot's own value line sits one level up) — or None if no block, or more
    than one block of the same smallest size, matches unambiguously.

    Blocks nest: "- class_derivations:" recurs at every list-item level (a
    MeasurementObservation's own block, and its nested value_quantity's
    Quantity block, both start with this exact marker at different
    indentation). A block's span runs from its own marker to the next marker
    at the same-or-shallower indentation (its next sibling, or the end of its
    parent) — so a block's span naturally includes all of its descendants'
    text too. Picking the *smallest* matching span is what selects the
    innermost/most specific block instead of an ancestor that merely contains
    it transitively.
    """
    markers = [(m.start(1), len(m.group(1))) for m in _BLOCK_MARKER_RE.finditer(text)]
    if not markers:
        return None

    slot_re = re.compile(rf"^[ \t]*{re.escape(slot)}:\s*\n[ \t]+(?:value|expr):", re.MULTILINE)
    phv_re = re.compile(rf"\b{re.escape(phv)}\b")
    # A phv referenced only inside age_at_observation doesn't identify the block —
    # every block in a MeasurementObservationSet routinely shares the same age
    # source while holding entirely different observation_type values (this is
    # the same Age cross-product artifact found earlier). Strip those lines
    # before the phv search so an Age-only "finding" correctly matches nothing
    # here (falls through to the file-wide check, which fails safe) instead of
    # silently latching onto an unrelated real variable's block.
    age_line_re = re.compile(r"^[ \t]*age_at_observation:\s*\n[ \t]+(?:expr|value|populated_from):[^\n]*\n?", re.MULTILINE)

    candidates: list[tuple[int, int, int]] = []  # (span_len, start, end)
    for i, (start, indent) in enumerate(markers):
        end = len(text)
        for j in range(i + 1, len(markers)):
            if markers[j][1] <= indent:
                end = markers[j][0]
                break
        span = text[start:end]
        phv_search_span = age_line_re.sub("", span)
        if slot_re.search(span) and phv_re.search(phv_search_span):
            candidates.append((end - start, start, end))

    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0])
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        return None  # ambiguous — two equally-specific blocks both match
    _, start, end = candidates[0]
    line_number = text.count("\n", 0, start) + 1
    return start, end, line_number


def _apply_yaml(
    study: str, yaml_file: str, slot: str, new_curie: str, phv: str = "", original_curie: str = "",
) -> tuple[bool, str]:
    if slot in _SUBMIT_BLOCKED_SLOTS:
        return False, (
            f"⚠ `{slot}` values are set per block in the YAML and were not updated — "
            "review and correct them directly in the YAML file."
        )
    yaml_path = STUDIES[study]["yaml_dir"] / Path(yaml_file).name
    if not yaml_path.exists():
        return False, f"❌ YAML not found: `{yaml_file}`"
    text = yaml_path.read_text(encoding="utf-8")

    # PHV-targeted path: locate the one specific block for this variable and edit
    # only that block, regardless of what other blocks in the file hold. This is
    # the primary targeting mechanism — the line number below is recorded purely
    # for the audit trail (change_log), never used to locate anything; it's
    # re-derived fresh from a live text search every time, so it can't go stale.
    if phv:
        found = _find_block_for_phv(text, slot, phv)
        if found:
            start, end, line_number = found
            block = text[start:end]
            pattern = rf"(^[ \t]*{re.escape(slot)}:\s*\n[ \t]+value:\s+)\S+"
            new_block, n = re.subn(pattern, lambda m: m.group(1) + new_curie, block, count=1, flags=re.MULTILINE)
            if n:
                new_text = text[:start] + new_block + text[end:]
                yaml_path.write_text(new_text, encoding="utf-8")
                return True, (
                    f"✓ YAML `{yaml_file}` [{slot}] → `{new_curie}` "
                    f"(block for phv `{phv}`, line {line_number})"
                )
            # Slot value is embedded in an expr string (e.g. case() drug_concept
            # pattern: expr: 'case(({phv} == 1, "CURIE"))') rather than a plain
            # "value:" line — replace the CURIE literal within just this
            # block's expr line, not the whole line, and only when it's
            # unambiguous: the phv must appear literally in that expr line
            # (confirms it's this variable's own condition, not a sibling's on
            # the same line) and there must be exactly one CURIE-shaped quoted
            # literal to replace — a case() with multiple conditions on one
            # line is refused rather than guessed at.
            expr_m = re.search(
                rf"^[ \t]*{re.escape(slot)}:\s*\n([ \t]+expr:.*\n?)", block, re.MULTILINE,
            )
            if expr_m and f"{{{phv}}}" in expr_m.group(1):
                expr_line = expr_m.group(1)
                curie_literals = re.findall(r'"([A-Za-z][A-Za-z0-9_]*:[A-Za-z0-9.\-]+)"', expr_line)
                if len(curie_literals) == 1:
                    new_expr_line = expr_line.replace(f'"{curie_literals[0]}"', f'"{new_curie}"', 1)
                    new_block = block[:expr_m.start(1)] + new_expr_line + block[expr_m.end(1):]
                    new_text = text[:start] + new_block + text[end:]
                    yaml_path.write_text(new_text, encoding="utf-8")
                    return True, (
                        f"✓ YAML `{yaml_file}` [{slot}] → `{new_curie}` "
                        f"(expr block for phv `{phv}`, line {line_number}, was `{curie_literals[0]}`)"
                    )
                return False, (
                    f"⚠ `{slot}` expr for phv `{phv}` (line {line_number}) has "
                    f"{len(curie_literals)} CURIE-shaped literals on one line — ambiguous which to "
                    "replace. Edit that block's literal CURIE string directly in the YAML file."
                )
            return False, (
                f"⚠ `{slot}` block for phv `{phv}` found (line {line_number}) but doesn't use a "
                "plain `value:` line, and its `expr:` (if any) doesn't reference this phv "
                "directly — can't confirm which literal is this variable's own. "
                "Edit that block's literal CURIE string directly in the YAML file."
            )
        # A phv was given but doesn't resolve to a unique block. This is NOT the
        # same as "no phv known" (old-format entries, handled below) — it means
        # either this finding is a known artifact (e.g. an "Age" variable that
        # only ever appears as age_at_observation, never as this slot's own
        # value — see the 2026-08-19/20 Age-artifact incidents) or the block
        # structure is unrecognized. Refuse outright rather than falling back to
        # the file-wide check: that check only looks at whether blocks *agree*,
        # which can look "safe" purely by coincidence (as happened here — two
        # unrelated real variables happened to share the same current CURIE)
        # and silently overwrite both.
        return False, (
            f"⚠ No YAML block found for phv `{phv}` under `{slot}` in `{yaml_file}` — this finding "
            "likely doesn't correspond to a real value in this slot (e.g. an Age-type variable that "
            "only appears as age_at_observation). Refusing to apply a file-wide blanket update, since "
            "that could silently overwrite a different, unrelated variable's correct value. "
            "If this finding is genuinely wrong, mark it 'Reviewed — no change' instead."
        )

    # Reached only when no phv was supplied at all (old-format pending entries) —
    # every phv-known path above already returned.
    #
    # When original_curie is known, filter to just the block(s) whose CURRENT
    # value matches what the curator actually reviewed — mirrors _apply_csv's
    # existing original_curie safety filter, and covers both plain "value:"
    # lines and expr: 'case((..., "CURIE"))' literals (e.g. drug_concept),
    # which the coarser "do ALL blocks already agree" check below can't reach
    # at all since it only understands "value:". Every matching occurrence is
    # updated together (not just one), same as _apply_csv updating every row
    # sharing that original value.
    if original_curie:
        value_pattern = rf"(^[ \t]*{re.escape(slot)}:\s*\n[ \t]+value:\s+){re.escape(original_curie)}\b"
        new_text, n = re.subn(value_pattern, lambda m: m.group(1) + new_curie, text, flags=re.MULTILINE)
        if n:
            yaml_path.write_text(new_text, encoding="utf-8")
            return True, (
                f"✓ YAML `{yaml_file}` [{slot}] → `{new_curie}` "
                f"({n} block(s) matching original `{original_curie}`)"
            )
        expr_pattern = rf'(^[ \t]*{re.escape(slot)}:\s*\n[ \t]+expr:.*?)"{re.escape(original_curie)}"'
        new_text, n = re.subn(
            expr_pattern, lambda m: m.group(1) + f'"{new_curie}"', text, flags=re.MULTILINE,
        )
        if n:
            yaml_path.write_text(new_text, encoding="utf-8")
            return True, (
                f"✓ YAML `{yaml_file}` [{slot}] → `{new_curie}` "
                f"({n} expr literal(s) matching original `{original_curie}`)"
            )
        # original_curie given but found nowhere in this file/slot — fall
        # through to the coarser check below rather than failing outright,
        # in case original_curie itself is stale (e.g. YAML already updated
        # since the finding was saved).

    existing = re.findall(rf"^[ \t]*{re.escape(slot)}:\s*\n[ \t]+value:\s+(\S+)", text, re.MULTILINE)
    if not existing:
        return False, f"⚠ No `{slot}: value:` pattern in `{yaml_file}`"
    unique_existing = set(existing)
    if len(unique_existing) > 1:
        vals = ", ".join(f"`{v}`" for v in sorted(unique_existing))
        return False, (
            f"⚠ `{slot}` has {len(existing)} blocks with differing values ({vals}) — "
            "cannot apply uniformly. Edit the YAML file directly."
        )
    pattern = rf"(^[ \t]*{re.escape(slot)}:\s*\n[ \t]+value:\s+)\S+"
    new_text, n = re.subn(pattern, lambda m: m.group(1) + new_curie, text, flags=re.MULTILINE)
    yaml_path.write_text(new_text, encoding="utf-8")
    return True, f"✓ YAML `{yaml_file}` [{slot}] → `{new_curie}` ({n} block(s) updated)"


def _apply_csv(
    study: str, yaml_file: str, slot: str, new_curie: str,
    original_curie: str = "", phv: str = "",
) -> tuple[bool, str]:
    fieldnames, rows = load_curie_csv(study)
    updated, changed, skipped_other_curie, skipped_other_phv = [], 0, 0, 0
    for row in rows:
        if row.get("YAML File") == Path(yaml_file).name and row.get("Slot") == slot:
            # A (yaml_file, slot) pair can span multiple rows carrying distinct
            # pre-existing CURIEs (e.g. FVC vs FEV1 vs FEV1/FVC all filed under the
            # same "observations" slot). Only touch rows whose current CURIE matches
            # what the curator actually reviewed — otherwise a blanket match here
            # would silently overwrite unrelated concepts sharing the same slot.
            if original_curie and row.get("CURIE") != original_curie:
                skipped_other_curie += 1
                updated.append(row)
                continue
            # PHV is the most precise available filter — apply it whenever the
            # finding carries one, on top of (not instead of) original_curie,
            # since original_curie alone could coincidentally match more than
            # one variable's row (as happened with the Age-variable incident).
            if phv and row.get("PHV") != phv:
                skipped_other_phv += 1
                updated.append(row)
                continue
            row = dict(row)
            row["CURIE"] = new_curie
            changed += 1
        updated.append(row)
    if changed == 0:
        if skipped_other_phv:
            return False, (
                f"⚠ No CSV rows match `{yaml_file}` / `{slot}` with PHV `{phv}` — "
                f"{skipped_other_phv} row(s) for this file/slot exist but belong to a different "
                "variable and were left untouched. Re-check the finding before applying."
            )
        if skipped_other_curie:
            return False, (
                f"⚠ No CSV rows match `{yaml_file}` / `{slot}` with CURIE `{original_curie}` — "
                f"{skipped_other_curie} row(s) for this file/slot exist but hold a different CURIE "
                "and were left untouched. Re-check the finding before applying."
            )
        return False, f"⚠ No CSV rows match `{yaml_file}` / `{slot}`"
    csv_path = STUDIES[study]["curie_csv"]
    try:
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(updated)
    except OSError as e:
        return False, (
            f"✗ Could not write `{csv_path.name}`: {e}. "
            "Close the file in Excel or any other application and try again."
        )
    load_curie_csv.clear()
    phv_note = f" (phv `{phv}`)" if phv else ""
    return True, f"✓ CSV: {changed} row(s) → `{new_curie}` for `{yaml_file}` [{slot}]{phv_note}"


# ── Batch submit ──────────────────────────────────────────────────────────────
def submit_all(study: str, pending: dict, curator: str) -> tuple[list[str], int, Path]:
    results: list[str] = []
    ok_count: int = 0
    submitted: dict = {}
    for key, val in pending.items():
        new_curie = val.get("change_request", "").strip()
        if not new_curie or val.get("applied"):
            continue
        slot           = val.get("slot", "")
        original_curie = val.get("original_curie", "")
        phv            = val.get("phv", "")
        yf_list        = val.get("yaml_files", [])
        row_res: list[tuple[bool, str]] = []
        if slot in _SUBMIT_BLOCKED_SLOTS:
            msg = (
                f"⚠ `{slot}` values are set per block in the YAML and were not updated — "
                "review and correct them directly in the YAML file."
            )
            results.append(msg)
            # Do not mark applied — YAML and CSV are untouched
            continue
        for yf in yf_list:
            row_res.append(_apply_yaml(study, yf, slot, new_curie, phv, original_curie))
            row_res.append(_apply_csv(study, yf, slot, new_curie, original_curie, phv))
        msgs = [msg for _, msg in row_res]
        results.extend(msgs)
        ok_count += sum(1 for ok, _ in row_res if ok)
        all_ok = all(ok for ok, _ in row_res)
        if all_ok:
            val.update({"applied": True, "applied_date": date.today().isoformat(), "applied_by": curator})
        submitted[key] = {**val, "apply_results": msgs}

    _save_pending(pending, study)

    log_path = _next_log_path(study)
    log_path.write_text(
        json.dumps({
            "submitted_date": date.today().isoformat(),
            "study": study, "curator": curator,
            "changes": submitted,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    load_curie_csv.clear()
    load_mapreview_csv.clear()
    return results, ok_count, log_path


# ── Slot / file helpers ───────────────────────────────────────────────────────
_KNOWN_SLOTS = [
    "condition_concept", "drug_concept", "observation_type", "observations",
    "procedure_concept", "route_concept", "race", "sex",
]

# Maps slot → which agent handles it (mirrors generate_curie_mapreview.py routing)
_SLOT_AGENT: dict[str, str] = {
    "condition_concept":  "MONDO / HPO / OMOP",
    "drug_concept":       "RxNorm",
    "observation_type":   "LOINC (measurementObs)",
    "observations":       "LOINC (measurementObs)",
    "procedure_concept":  "OMOP",
    "route_concept":      "OMOP (route)",
    "race":               "OMOP (race/ethnicity)",
    "sex":                "OMOP (gender)",
}


def _detect_slot(text: str) -> str:
    for slot in _KNOWN_SLOTS:
        if slot in text:
            return slot
    return ""


def _extract_yaml_files(raw: str) -> list[str]:
    clean = _unescape_md(raw)
    return [f.strip() for f in re.split(r"[;,]+", clean) if f.strip().endswith(".yaml")]


def _row_key(study: str, file_field: str, phv: str = "") -> str:
    """Identity key for a finding. Includes PHV when known, since a single
    YAML file can now carry multiple distinct per-variable findings (the
    MeasurementObservationSet cross-product pattern) — without PHV, two
    different variables' decisions would collide on the same pending-changes
    entry. phv="" preserves the old file-only key for backward compatibility
    with existing pending_changes.json entries and studies not yet re-run
    under the per-variable finding schema."""
    base = f"{study}::confirmed::{_unescape_md(file_field)}"
    return f"{base}::{phv}" if phv else base


# ── Confirmed Findings row renderer ──────────────────────────────────────────
_DRUG_NUANCE_HTML = (
    '<div style="background:#fff8e1;padding:10px 14px;border-radius:4px;'
    'border-left:4px solid #f9a825;font-size:0.9em;margin-top:8px">'
    "💊 <strong>Drug therapy note:</strong> ATC classification codes differ by therapy type. "
    "Two-drug combinations (e.g. ICS+LABA) and triple-therapy products (ICS+LABA+LAMA) map to "
    "different ATC subgroups — adding an anticholinergic moves the product out of the dual-combination "
    "subgroup. Verify whether the study variable captures mono, dual, or triple therapy before "
    "assigning a single ATC class. The RxNorm agent returns ingredient-level concepts; the ATC "
    "classification may need to be assigned manually based on the exact combination."
    "</div>"
)


def render_row(row: dict, study: str, pending: dict, idx: int, force_expanded: bool = False) -> None:
    file_field  = row.get("File", "")
    yaml_files  = _extract_yaml_files(file_field)
    auto_slot   = _detect_slot(row.get("semantic validator review", ""))
    priority    = row.get("Priority", "")
    issue       = row.get("Final issue", "")
    recommended = row.get("Recommended action", "")
    validator   = row.get("semantic validator review", "")
    phv         = row.get("PHV", "").strip()

    row_id = _row_key(study, file_field, phv)
    saved  = pending.get(row_id, {})

    badge      = "🎯" if priority.startswith("🎯") else {"P1": "🔴", "P2": "🟡", "P3": "🟢"}.get(priority, "⚪")
    done_badge = (
        " ✅" if saved.get("applied")
        else " ☑" if saved.get("no_change")
        else " 💾" if saved.get("change_request")
        else " 📝" if saved.get("notes")
        else ""
    )
    label = f"{badge} **{priority}** · `{_unescape_md(file_field)}` — {issue[:70]}{'…' if len(issue)>70 else ''}{done_badge}"

    with st.expander(label, expanded=force_expanded):
        tab_detail, tab_cr = st.tabs(["📋 Details", "✏️ Change request"])

        # ── Details ──────────────────────────────────────────────────────────
        with tab_detail:
            # Applied / reviewed-no-change banner
            if saved.get("applied"):
                _new_curie   = saved.get("change_request", "")
                _orig_curie  = saved.get("original_curie", "")
                _applied_by  = saved.get("applied_by", "")
                _applied_dt  = saved.get("applied_date", "")
                _banner_note = saved.get("notes", "")
                _curie_url   = _curie_to_url(_new_curie) if _new_curie else ""
                _curie_html  = (
                    f'<a href="{_curie_url}" target="_blank"><code>{_new_curie}</code></a>'
                    if _curie_url else f"<code>{_new_curie}</code>"
                ) if _new_curie else "—"
                _orig_url    = _curie_to_url(_orig_curie) if _orig_curie else ""
                _orig_code   = (
                    f'<a href="{_orig_url}" target="_blank"><code>{_orig_curie}</code></a>'
                    if _orig_url else f"<code>{_orig_curie}</code>"
                )
                _orig_html   = f" &nbsp;(was: {_orig_code})" if _orig_curie else ""
                _by_html     = f" &nbsp;·&nbsp; by {_applied_by}" if _applied_by else ""
                _dt_html     = f" on {_applied_dt}" if _applied_dt else ""
                _note_html   = f"<br><span style='color:#555'>{_banner_note[:200]}</span>" if _banner_note else ""
                st.markdown(
                    f'<div style="background:#e6f4ea;padding:10px 14px;border-radius:4px;'
                    f'border-left:4px solid #34a853;font-size:0.9em;margin-bottom:8px">'
                    f'✅ <strong>Applied</strong>{_dt_html}{_by_html}<br>'
                    f'Changed to: {_curie_html}{_orig_html}{_note_html}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            elif saved.get("no_change"):
                _nc_by      = saved.get("no_change_by", "")
                _nc_dt      = saved.get("no_change_date", "")
                _nc_reason  = saved.get("no_change_reason", "")
                _by_html    = f" &nbsp;·&nbsp; by {_nc_by}" if _nc_by else ""
                _dt_html    = f" on {_nc_dt}" if _nc_dt else ""
                _reason_html = f"<br><span style='color:#555'>Reason: {_nc_reason[:200]}</span>" if _nc_reason else ""
                st.markdown(
                    f'<div style="background:#f0f4ff;padding:10px 14px;border-radius:4px;'
                    f'border-left:4px solid #6c8ebf;font-size:0.9em;margin-bottom:8px">'
                    f'☑ <strong>Reviewed — no change</strong>{_dt_html}{_by_html}{_reason_html}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            # Family-history info note — shown when the YAML has non-ONESELF blocks.
            if yaml_files and _yaml_has_family_history_blocks(study, yaml_files[0]):
                st.markdown(
                    '<div style="background:#fff8e1;padding:9px 14px;border-radius:4px;'
                    'border-left:4px solid #f9a825;font-size:0.88em;margin-bottom:8px">'
                    f'ℹ <strong>Family-history blocks present in '
                    f'<code>{Path(yaml_files[0]).name}</code></strong><br>'
                    'This file contains blocks where <code>relationship_to_participant</code> '
                    'is not <code>ONESELF</code> (e.g. mother, father, sibling).<br>'
                    '• <strong>Condition concept changes</strong> (e.g. <code>condition_concept</code>) '
                    '— submit works correctly and updates all blocks, including family-history blocks.<br>'
                    '• <strong><code>relationship_to_participant</code> values</strong> '
                    '— these are set per block and must be reviewed and corrected directly in the YAML file; '
                    'they cannot be changed via submit.'
                    '</div>',
                    unsafe_allow_html=True,
                )
            st.markdown(f"**Issue:** {issue}")
            if row.get("Confidence") or row.get("Reviewer"):
                st.markdown(
                    f"**Confidence:** {row.get('Confidence','—')} &nbsp;|&nbsp; "
                    f"**Reviewer:** {row.get('Reviewer','—')}"
                )
            if recommended:
                st.markdown("**Recommended action:**")
                st.markdown(_linkify(recommended), unsafe_allow_html=True)
                if auto_slot == "drug_concept":
                    st.markdown(_DRUG_NUANCE_HTML, unsafe_allow_html=True)
            st.divider()
            d_left, d_right = st.columns(2)
            with d_left:
                st.markdown(f"**Slot:** `{auto_slot or '—'}`")
                st.markdown("**Current CURIE:**")
                if not auto_slot:
                    st.caption("_Slot not detected — check the Semantic Validator Review column for slot details._")
                elif not yaml_files:
                    st.caption("_No YAML file linked — refer to the source reviewer MD for context._")
                else:
                    det_curies = get_current_curies(study, yaml_files[0], auto_slot)
                    if det_curies:
                        _render_curies_with_vars(study, yaml_files[0], auto_slot, det_curies)
                    else:
                        blank_rows = get_curie_csv_rows_for_file(study, yaml_files[0], auto_slot)
                        if blank_rows:
                            st.caption("_CURIE is blank in curie CSV:_")
                            for _r in blank_rows:
                                _render_var_row_caption(_r)
                        else:
                            _render_curie_not_in_mapreview(study, yaml_files[0], auto_slot)
            with d_right:
                det_terms = get_terminology_matches(study, yaml_files[0], auto_slot, phv) if auto_slot and yaml_files else []
                det_conf_notes = _extract_confidence_notes(validator)
                det_resolution_caveat = get_loinc_omop_resolution_caveat(study, yaml_files[0], auto_slot, phv) if auto_slot and yaml_files else ""
                st.markdown("**Agent suggestion:**")
                if det_terms:
                    for _label, _curie, _weak in det_terms:
                        _curie_link_md(_curie, label=f"{_label} ⚠ weak match" if _weak else _label)
                    # Surface the system's own confidence/vocab-mismatch caveats right
                    # here — without this a low-confidence or wrong-vocabulary match
                    # (e.g. a normalizer flag saying it resolves to a DIFFERENT concept)
                    # reads as a clean recommendation instead of one to be skeptical of.
                    for note in det_conf_notes:
                        st.caption(note)
                if det_resolution_caveat:
                    st.caption(det_resolution_caveat)
                if not det_terms:
                    if not auto_slot:
                        st.caption("_Slot not detected — cannot determine expected agent._")
                    else:
                        agent_label = _SLOT_AGENT.get(auto_slot)
                        if agent_label:
                            st.caption(f"_Expected agent: **{agent_label}**_")
                        else:
                            st.caption(f"_No agent routing defined for slot `{auto_slot}`._")
                        # Try entity type from curie CSV first, then YAML scan
                        etype, etype_src = "", ""
                        if yaml_files:
                            _cr = get_curie_csv_rows_for_file(study, yaml_files[0], auto_slot)
                            if _cr:
                                etype = _cr[0].get("Entity Type", "").strip()
                                etype_src = "curie CSV"
                            else:
                                _, _, _, _, _etypes = _check_yaml_slot(study, yaml_files[0], auto_slot)
                                if _etypes:
                                    etype = ", ".join(_etypes)
                                    etype_src = "YAML"
                        if etype:
                            st.caption(f"_Entity type ({etype_src}): `{etype}`_")
                        st.caption("_No suggestion found in curie map review._")



                # ── Priority CURIE — mapreview.csv's own MONDO>HPO>OBA>OMOP cascade.
                # Shown alongside (never instead of) the per-agent list above: it's a
                # mechanical fixed-priority pick with no vocab/slot-rule awareness, so
                # it can rank a technically-wrong-vocabulary CURIE above a better one
                # the individual agents already found. Seeing both lets the curator
                # judge disagreement rather than trust a single collapsed answer.
                if auto_slot and yaml_files:
                    _prio, _prio_ambiguous = get_priority_curie_context(study, yaml_files[0], auto_slot, phv)
                    if _prio_ambiguous:
                        st.caption(
                            "_🏆 Priority CURIE is ambiguous here — this slot maps to "
                            "multiple source variables; see the per-variable table below._"
                        )
                    elif _prio:
                        st.markdown("**🏆 Priority CURIE** _(best-guess cascade — verify against agent list above)_:")
                        for _p in _prio:
                            _curie_link_md(_p)

                # ── OBA live suggestions (measurement slots only) ──────────────
                # Prefer auto_slot; fall back to curie CSV if the review MD text
                # doesn't mention the slot name explicitly.
                _oba_slot = auto_slot if auto_slot in _OBA_SLOTS else ""
                if not _oba_slot and yaml_files:
                    for _try_slot in ("observation_type", "observations"):
                        if get_curie_csv_rows_for_file(study, yaml_files[0], _try_slot):
                            _oba_slot = _try_slot
                            break
                if _oba_slot and yaml_files:
                    st.markdown("**OBA suggestion** _(OLS4 live)_:")
                    _oba_rows = get_curie_csv_rows_for_file(study, yaml_files[0], _oba_slot)
                    _oba_query = ""
                    if _oba_rows:
                        _oba_query = (
                            _oba_rows[0].get("Variable Description", "").strip()
                            or _oba_rows[0].get("Variable Name", "").strip()
                        )
                    if not _oba_query:
                        _oba_query = Path(yaml_files[0]).stem.replace("_", " ")
                    _oba_hits = _fetch_oba_suggestions(_oba_query)
                    if _oba_hits:
                        for _obo_id, _label in _oba_hits:
                            _oba_url = _curie_to_url(_obo_id)
                            _id_part = (
                                f'<a href="{_oba_url}" target="_blank"><code>{_obo_id}</code></a>'
                                if _oba_url else f"<code>{_obo_id}</code>"
                            )
                            st.markdown(
                                f'{_id_part} &nbsp;—&nbsp; {_label}',
                                unsafe_allow_html=True,
                            )
                    else:
                        st.caption(f'_No OBA terms found for "{_oba_query}"._')
            if auto_slot and yaml_files:
                st.divider()
                _render_provenance_table(study, yaml_files[0], auto_slot)
            st.divider()
            st.markdown("**Semantic validator review:**")
            _info_box(validator)

        # ── Change request ────────────────────────────────────────────────────
        with tab_cr:
            left, right = st.columns([1, 2])

            with left:
                st.markdown("**YAML file(s):**")
                for yf in yaml_files:
                    st.code(yf, language=None)
                st.markdown(f"**Slot:** `{auto_slot or '—'}`")

                st.markdown("**Current CURIE:**")
                if not auto_slot:
                    st.caption("_Slot not detected — check the Semantic Validator Review column for slot details._")
                elif not yaml_files:
                    st.caption("_No YAML file linked — refer to the source reviewer MD for context._")
                else:
                    curies = get_current_curies(study, yaml_files[0], auto_slot)
                    if curies:
                        _render_curies_with_vars(study, yaml_files[0], auto_slot, curies)
                    else:
                        blank_rows = get_curie_csv_rows_for_file(study, yaml_files[0], auto_slot)
                        if blank_rows:
                            st.caption("_CURIE is blank in curie CSV:_")
                            for _r in blank_rows:
                                _render_var_row_caption(_r)
                        else:
                            _render_curie_not_in_mapreview(study, yaml_files[0], auto_slot)

                cr_terms = get_terminology_matches(study, yaml_files[0], auto_slot, phv) if auto_slot and yaml_files else []
                if cr_terms:
                    st.markdown("**Agent suggestion:**")
                    for _label, _curie, _weak in cr_terms:
                        _curie_link_md(_curie, label=f"{_label} ⚠ weak match" if _weak else _label)
                    for note in _extract_confidence_notes(validator):
                        st.caption(note)
                cr_resolution_caveat = get_loinc_omop_resolution_caveat(study, yaml_files[0], auto_slot, phv) if auto_slot and yaml_files else ""
                if cr_resolution_caveat:
                    st.caption(cr_resolution_caveat)

                if auto_slot and yaml_files:
                    _prio_cr, _prio_cr_ambiguous = get_priority_curie_context(study, yaml_files[0], auto_slot, phv)
                    if _prio_cr_ambiguous:
                        st.caption(
                            "_🏆 Priority CURIE is ambiguous here — this slot maps to "
                            "multiple source variables; see the provenance table on the "
                            "📋 Details tab._"
                        )
                    elif _prio_cr:
                        st.markdown("**🏆 Priority CURIE** _(best-guess cascade)_:")
                        for _p in _prio_cr:
                            _curie_link_md(_p)

            with right:
                use_slot = st.text_input(
                    "Slot (override if needed)",
                    value=saved.get("slot", auto_slot),
                    key=f"slot_{study}_{idx}",
                )
                new_cr = st.text_input(
                    "New CURIE (optional — add when ready to submit)",
                    value=saved.get("change_request", ""),
                    key=f"cr_{study}_{idx}",
                    placeholder="e.g. MONDO:0004849",
                )
                notes = st.text_area(
                    "Curator notes",
                    value=saved.get("notes", ""),
                    key=f"notes_{study}_{idx}",
                    height=70,
                )

                if new_cr:
                    err = _validate_curie(new_cr)
                    if err:
                        st.error(f"⚠ {err}")
                    else:
                        url = _curie_to_url(new_cr.strip())
                        if url:
                            st.markdown(
                                f'🔗 <a href="{url}" target="_blank">Preview '
                                f'<code>{new_cr.strip()}</code></a>',
                                unsafe_allow_html=True,
                            )
                        etype = _infer_entity_type(new_cr.strip())
                        if etype:
                            st.caption(f"Entity type: {etype}")

                st.divider()

                if st.button(
                    "💾 Save", key=f"save_{study}_{idx}",
                    type="primary", use_container_width=True,
                ):
                    curie_err = _validate_curie(new_cr) if new_cr.strip() else ""
                    if curie_err:
                        st.error(f"Invalid CURIE — {curie_err}")
                    elif not use_slot:
                        st.error("Slot is required.")
                    elif not new_cr.strip() and not notes.strip():
                        st.error("Enter a CURIE, notes, or both before saving.")
                    else:
                        original_curies = get_current_curies(study, yaml_files[0], use_slot) if yaml_files and new_cr.strip() else []
                        pending[row_id] = {
                            "study":           study,
                            "phv":             phv,
                            "change_request":  new_cr.strip(),
                            "original_curie":  original_curies[0] if original_curies else "",
                            "slot":            use_slot,
                            "yaml_files":      yaml_files,
                            "notes":           notes,
                            "applied":         False,
                            "saved_date":      date.today().isoformat(),
                        }
                        _save_pending(pending, study)
                        _, n = _rebuild_cr_csv(study, pending)
                        st.session_state[f"pending_{study}"] = pending
                        if new_cr.strip():
                            st.toast(f"✓ Saved — CR CSV updated ({n} row(s))")
                        else:
                            st.toast("📝 Notes saved — add a CURIE when ready to submit.")
                        st.rerun()

                if saved.get("applied"):
                    st.success(f"✅ Applied: `{saved['change_request']}`")
                elif saved.get("no_change"):
                    st.success(
                        f"☑ Reviewed — no change · {saved.get('reviewed_date', '')} "
                        f"· {saved.get('reviewed_by', '')}"
                    )
                    if saved.get("no_change_reason"):
                        st.caption(f"Reason: {saved['no_change_reason']}")
                elif saved.get("change_request") and not saved.get("applied"):
                    url = _curie_to_url(saved["change_request"])
                    link = (
                        f'<a href="{url}" target="_blank"><code>{saved["change_request"]}</code></a>'
                        if url else f'<code>{saved["change_request"]}</code>'
                    )
                    st.markdown(f"💾 Saved: {link} → `{saved.get('slot')}`", unsafe_allow_html=True)
                elif saved.get("notes") and not saved.get("applied"):
                    st.info("📝 Notes saved — no CURIE yet. Add a CURIE before submitting.")

                # ── Reviewed — no change ──────────────────────────────────────
                st.divider()
                if saved.get("no_change"):
                    if st.button(
                        "↩ Reopen for editing",
                        key=f"nc_undo_{study}_{idx}",
                        use_container_width=True,
                    ):
                        entry = dict(pending.get(row_id, {}))
                        for _k in ("no_change", "no_change_reason", "reviewed_date", "reviewed_by"):
                            entry.pop(_k, None)
                        pending[row_id] = entry
                        _save_pending(pending, study)
                        st.session_state[f"pending_{study}"] = pending
                        st.toast("↩ Reopened for editing.")
                        st.rerun()
                else:
                    st.markdown("**Or — mark as reviewed with no change needed:**")
                    no_change_reason = st.text_area(
                        "Reason (required)",
                        value=saved.get("no_change_reason", ""),
                        key=f"nc_reason_{study}_{idx}",
                        height=55,
                        placeholder="e.g. OBA term is correct for observation_type — LOINC suggestion is a vocab/slot mismatch.",
                    )
                    if st.button(
                        "☑ Mark reviewed — no change",
                        key=f"nc_btn_{study}_{idx}",
                        use_container_width=True,
                    ):
                        if not no_change_reason.strip():
                            st.error("A reason is required before marking as reviewed.")
                        else:
                            entry = dict(pending.get(row_id, {}))
                            entry.update({
                                "study":            study,
                                "phv":              phv,
                                "slot":             use_slot,
                                "yaml_files":       yaml_files,
                                "no_change":        True,
                                "no_change_reason": no_change_reason.strip(),
                                "reviewed_date":    date.today().isoformat(),
                                "reviewed_by":      st.session_state.get("curator_sidebar", "Curator"),
                                "change_request":   "",
                                "applied":          False,
                            })
                            pending[row_id] = entry
                            _save_pending(pending, study)
                            st.session_state[f"pending_{study}"] = pending
                            st.toast("☑ Marked as reviewed — no change recorded.")
                            st.rerun()


# ── Manual Curation Notes helpers ────────────────────────────────────────────
def _orphan_pending(study: str, pending: dict, confirmed_rows: list[dict]) -> dict:
    """Return pending entries that have no corresponding review-MD row."""
    anchored = {
        _row_key(study, row["File"], row.get("PHV", "").strip())
        for row in confirmed_rows if row.get("File")
    }
    return {
        k: v for k, v in pending.items()
        if k not in anchored
        and not v.get("applied")
        and not v.get("no_change")
        and (v.get("notes") or v.get("change_request"))
        and v.get("study", study) == study
    }


def render_manual_notes_tab(study: str, pending: dict, confirmed_rows: list[dict]) -> None:
    """Show pending entries that have no corresponding reviewer-findings row."""
    orphans = _orphan_pending(study, pending, confirmed_rows)

    st.caption(
        "Variables noted here were not flagged by the semantic review generator "
        "(e.g. CSV and YAML matched, no agent suggestion) but have curator notes or a "
        "proposed change. Use the form below to update, submit, or close each note."
    )

    if not orphans:
        st.info("No manual curation notes for this study.")
        return

    for i, (row_id, val) in enumerate(sorted(orphans.items())):
        file_label  = row_id.split("::", 2)[-1]
        slot        = val.get("slot", "")
        cr          = val.get("change_request", "")
        notes       = val.get("notes", "")
        yaml_files  = val.get("yaml_files", [file_label] if file_label else [])
        saved_date  = val.get("saved_date", "")
        orig_curie  = val.get("original_curie", "")

        badge = "💾" if cr else "📝"
        cr_suffix = f" → {cr}" if cr else ""
        slot_suffix = f" [{slot}]" if slot else ""
        exp_label = f"{badge} `{file_label}`{slot_suffix}{cr_suffix}"

        with st.expander(exp_label, expanded=False):
            left, right = st.columns([1, 2])

            with left:
                st.markdown("**YAML file(s):**")
                for yf in yaml_files:
                    st.code(yf, language=None)
                if slot:
                    st.markdown(f"**Slot:** `{slot}`")
                if saved_date:
                    st.caption(f"Saved: {saved_date}")
                if orig_curie:
                    st.markdown("**Original CURIE:**")
                    _curie_link_md(orig_curie)

                if slot and yaml_files:
                    st.markdown("**Current CURIE in YAML:**")
                    _curies = get_current_curies(study, yaml_files[0], slot)
                    if _curies:
                        _render_curies_with_vars(study, yaml_files[0], slot, _curies)
                    else:
                        st.caption("_Not found in YAML_")

            with right:
                new_cr = st.text_input(
                    "Change request CURIE",
                    value=cr,
                    key=f"mn_cr_{study}_{i}",
                    placeholder="e.g. MONDO:0004668",
                )
                new_notes = st.text_area(
                    "Notes",
                    value=notes,
                    key=f"mn_notes_{study}_{i}",
                    height=100,
                )

                col_save, col_nc, col_del = st.columns(3)
                with col_save:
                    if st.button("💾 Save", key=f"mn_save_{study}_{i}", use_container_width=True):
                        pending[row_id] = {
                            **val,
                            "change_request": new_cr.strip(),
                            "notes":          new_notes.strip(),
                            "saved_date":     date.today().isoformat(),
                        }
                        _save_pending(pending, study)
                        st.toast("Note saved.")
                        st.rerun()

                with col_nc:
                    if st.button("☑ No change", key=f"mn_nc_{study}_{i}", use_container_width=True):
                        curator = st.session_state.get("curator_sidebar", "Curator")
                        pending[row_id] = {
                            **val,
                            "no_change":        True,
                            "no_change_date":   date.today().isoformat(),
                            "no_change_by":     curator,
                            "no_change_reason": new_notes.strip() or "Reviewed manually — no change needed.",
                        }
                        _save_pending(pending, study)
                        st.toast("☑ Marked as reviewed — no change.")
                        st.rerun()

                with col_del:
                    if st.button("🗑 Remove", key=f"mn_del_{study}_{i}", use_container_width=True):
                        pending.pop(row_id, None)
                        _save_pending(pending, study)
                        st.toast("Note removed.")
                        st.rerun()


# ── Cross-Study Consistency tab ───────────────────────────────────────────────
def render_cross_study_tab() -> None:
    """Flag YAML files where the same slot maps to different CURIEs across studies."""

    # Build index: {(canonical_yaml_name, slot) -> {study_short -> [csv_row, ...]}}
    index: dict[tuple[str, str], dict[str, list[dict]]] = {}
    for s in STUDIES:
        if not STUDIES[s]["curie_csv"].exists():
            continue
        _, rows = load_curie_csv(s)
        for r in rows:
            yaml_file = r.get("YAML File", "").strip()
            slot      = r.get("Slot", "").strip()
            if not yaml_file or not slot:
                continue
            canonical = Path(yaml_file).name
            index.setdefault((canonical, slot), {}).setdefault(s, []).append(r)

    # Keep only entries where ≥ 2 distinct non-blank CURIEs exist across studies
    inconsistencies: dict[tuple[str, str], dict[str, list[dict]]] = {}
    for key, study_map in index.items():
        distinct = {r.get("CURIE", "").strip()
                    for rows in study_map.values() for r in rows
                    if r.get("CURIE", "").strip()}
        if len(distinct) > 1:
            inconsistencies[key] = study_map

    st.caption(
        "Variables where the same YAML file and slot are mapped to different CURIEs "
        "across studies. Blank CURIEs are excluded from the conflict check."
    )

    if not inconsistencies:
        st.success("No cross-study CURIE inconsistencies found.")
        return

    st.info(
        f"{len(inconsistencies)} inconsistenc{'y' if len(inconsistencies) == 1 else 'ies'} "
        f"detected across {len(STUDIES)} studies."
    )

    for (canonical, slot), study_map in sorted(inconsistencies.items()):
        distinct_curies = sorted({
            r.get("CURIE", "").strip()
            for rows in study_map.values() for r in rows
            if r.get("CURIE", "").strip()
        })
        n_studies = len(study_map)
        exp_label = (
            f"⚠ `{canonical}` [{slot}] — "
            f"{len(distinct_curies)} distinct CURIEs across {n_studies} "
            f"{'study' if n_studies == 1 else 'studies'}"
        )

        with st.expander(exp_label, expanded=False):
            for s in sorted(study_map):
                rows = study_map[s]
                # Pending / curation state for this file in this study
                _pend  = st.session_state.get(f"pending_{s}") or _load_pending(s)
                _saved = _pend.get(_row_key(s, canonical), {})
                if _saved.get("applied"):
                    _status = f" ✅ → `{_saved.get('change_request', '')}`"
                elif _saved.get("no_change"):
                    _status = " ☑"
                elif _saved.get("change_request"):
                    _status = f" 💾 → `{_saved.get('change_request', '')}`"
                elif _saved.get("notes"):
                    _status = " 📝"
                else:
                    _status = ""

                st.markdown(f"**{STUDIES[s]['label']}**{_status}")

                # Group rows by CURIE so the link appears once per CURIE
                by_curie: dict[str, list[dict]] = {}
                for r in rows:
                    by_curie.setdefault(r.get("CURIE", "").strip(), []).append(r)

                for curie in sorted(by_curie):
                    if curie:
                        _curie_link_md(curie)
                    else:
                        st.caption("_(no CURIE)_")
                    for r in by_curie[curie]:
                        _render_var_row_caption(r)

                st.divider()


# ── Previously Committed tab ──────────────────────────────────────────────────
def render_committed_tab(study: str, pending: dict) -> None:
    applied    = {k: v for k, v in pending.items() if v.get("applied")   and v.get("study", study) == study}
    no_changes = {k: v for k, v in pending.items() if v.get("no_change") and v.get("study", study) == study}

    if not applied and not no_changes:
        st.info("No committed changes for this study yet. Changes appear here after you submit.")
        return

    if applied:
        st.caption(f"{len(applied)} committed change(s) — click ✏️ Edit to queue a correction.")

    for i, (row_id, val) in enumerate(sorted(applied.items())):
        file_label = row_id.split("::", 2)[-1]
        new_curie  = val.get("change_request", "")
        url        = _curie_to_url(new_curie)
        curie_html = (
            f'<a href="{url}" target="_blank"><code>{new_curie}</code></a>'
            if url else f"<code>{new_curie}</code>"
        )
        edit_key   = f"edit_mode_{study}_{i}"

        header = f"✅ `{file_label}` [{val.get('slot','')}] → {new_curie}"
        if val.get("corrects"):
            header += " ↩ (correction)"

        with st.expander(header, expanded=False):
            col_info, col_btn = st.columns([5, 1])
            with col_info:
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**Slot:**")
                    st.code(val.get("slot", "—"), language=None)
                    orig = val.get("original_curie", "")
                    if orig:
                        st.markdown("**Original CURIE (before change):**")
                        _curie_link_md(orig)
                with c2:
                    st.markdown("**Applied CURIE:**")
                    st.markdown(curie_html, unsafe_allow_html=True)
                    yf_list = val.get("yaml_files", [])
                    if yf_list:
                        st.markdown("**YAML file(s) updated:**")
                        for yf in yf_list:
                            st.code(yf, language=None)
                meta = []
                if val.get("applied_date"):
                    meta.append(f"Applied {val['applied_date']}")
                if val.get("applied_by"):
                    meta.append(f"by {val['applied_by']}")
                if meta:
                    st.caption(" · ".join(meta))
                if val.get("notes"):
                    st.caption(f"Notes: {val['notes']}")

            with col_btn:
                if st.button("✏️ Edit", key=f"edit_btn_{study}_{i}", use_container_width=True):
                    st.session_state[edit_key] = not st.session_state.get(edit_key, False)
                    st.rerun()

            if st.session_state.get(edit_key, False):
                st.divider()
                orig = val.get("original_curie", "")
                yf_list = val.get("yaml_files", [])

                st.markdown(
                    f"Queuing a correction will create a new pending request targeting "
                    f"**{len(yf_list)} YAML file(s)**: `{'`, `'.join(yf_list)}`"
                )

                col_revert, col_manual = st.columns(2)
                with col_revert:
                    revert_disabled = not orig
                    if st.button(
                        f"↩ Revert to original{(' (' + orig + ')') if orig else ' (unknown)'}",
                        key=f"revert_{study}_{i}",
                        disabled=revert_disabled,
                        use_container_width=True,
                        help="Pre-fills the correction field with the original CURIE captured at save time.",
                    ):
                        st.session_state[f"correction_{study}_{i}"] = orig
                        st.rerun()
                with col_manual:
                    st.caption("Or enter a different CURIE below ↓")

                new_correction = st.text_input(
                    "Corrected CURIE *",
                    key=f"correction_{study}_{i}",
                    placeholder="e.g. MONDO:0004848",
                )
                if new_correction:
                    url = _curie_to_url(new_correction.strip())
                    if url:
                        st.markdown(
                            f'🔗 <a href="{url}" target="_blank">Preview <code>{new_correction.strip()}</code></a>',
                            unsafe_allow_html=True,
                        )
                corr_notes = st.text_area(
                    "Reason for correction",
                    key=f"corr_notes_{study}_{i}",
                    height=55,
                )
                if st.button("💾 Save correction as pending", key=f"corr_save_{study}_{i}",
                             type="primary"):
                    err = _validate_curie(new_correction)
                    if err:
                        st.error(f"Invalid CURIE — {err}")
                    else:
                        corr_key = f"{row_id}::correction_{i}"
                        pending[corr_key] = {
                            "study":           study,
                            "phv":             val.get("phv", ""),
                            "change_request":  new_correction.strip(),
                            "original_curie":  new_curie,   # current applied value is now "original" for this correction
                            "slot":            val.get("slot", ""),
                            "yaml_files":      val.get("yaml_files", []),
                            "notes":           corr_notes,
                            "applied":         False,
                            "saved_date":      date.today().isoformat(),
                            "corrects":        row_id,
                        }
                        _save_pending(pending, study)
                        st.session_state[f"pending_{study}"] = pending
                        st.session_state[edit_key] = False
                        st.toast("✓ Correction queued — go to Submit tab to apply.")
                        st.rerun()

    # ── Reviewed — Kept As-Is ─────────────────────────────────────────────────
    if no_changes:
        if applied:
            st.divider()
        st.subheader(f"Reviewed — Kept As-Is ({len(no_changes)})")
        st.caption("Curator reviewed these findings and deliberately decided to keep the existing mapping.")
        for i, (row_id, val) in enumerate(sorted(no_changes.items())):
            file_label = row_id.split("::", 2)[-1]
            slot_label = f" [{val.get('slot','')}]" if val.get("slot") else ""
            with st.expander(f"☑ `{file_label}`{slot_label}", expanded=False):
                col_info, col_btn = st.columns([5, 1])
                with col_info:
                    if val.get("no_change_reason"):
                        st.markdown(f"**Reason:** {val['no_change_reason']}")
                    meta = []
                    if val.get("reviewed_date"):
                        meta.append(f"Reviewed {val['reviewed_date']}")
                    if val.get("reviewed_by"):
                        meta.append(f"by {val['reviewed_by']}")
                    if meta:
                        st.caption(" · ".join(meta))
                    if val.get("yaml_files"):
                        st.caption(f"YAML: {', '.join(val['yaml_files'])}")
                with col_btn:
                    if st.button(
                        "↩ Reopen",
                        key=f"nc_reopen_{study}_{i}",
                        use_container_width=True,
                        help="Remove the no-change decision and reopen for editing.",
                    ):
                        entry = dict(val)
                        for _k in ("no_change", "no_change_reason", "reviewed_date", "reviewed_by"):
                            entry.pop(_k, None)
                        pending[row_id] = entry
                        _save_pending(pending, study)
                        st.session_state[f"pending_{study}"] = pending
                        st.toast("↩ Reopened for editing.")
                        st.rerun()


# ── Submit tab ────────────────────────────────────────────────────────────────
def render_submit_tab(study: str, pending: dict) -> None:
    not_applied = {
        k: v for k, v in pending.items()
        if v.get("change_request") and not v.get("applied")
    }
    notes_only = {
        k: v for k, v in pending.items()
        if not v.get("change_request") and v.get("notes") and not v.get("applied")
    }

    st.subheader("Pending change requests")
    if not not_applied and not notes_only:
        st.info("No pending change requests. Save requests in the ✏️ Change request tab.")
        return

    if notes_only:
        files = ", ".join(k.split("::", 2)[-1] for k in notes_only)
        st.warning(
            f"📝 **{len(notes_only)} entry/entries have notes but no CURIE** — "
            f"they will not be applied on submit: `{files}`"
        )

    if not not_applied:
        st.info("No CURIE change requests ready to submit yet.")
        return

    table = []
    for key, val in not_applied.items():
        new_curie = val.get("change_request", "")
        table.append({
            "File":        key.split("::", 2)[-1],
            "Slot":        val.get("slot", ""),
            "New CURIE":   new_curie,
            "Entity type": _infer_entity_type(new_curie),
            "Saved":       val.get("saved_date", ""),
            "Notes":       val.get("notes", ""),
        })
    st.dataframe(table, use_container_width=True)

    today = date.today().strftime("%Y%m%d")
    cr_path = REVIEW_OUT / f"{study}_curie_changerequest_v{today}.csv"
    if cr_path.exists():
        st.download_button(
            f"⬇ Download {cr_path.name}",
            data=cr_path.read_bytes(),
            file_name=cr_path.name,
            mime="text/csv",
        )

    st.divider()
    curator = st.text_input(
        "Curator name",
        value="Curator",
        key="curator_submit",
        help="Recorded in the change log.",
    )
    curie_csv_name = STUDIES[study]["curie_csv"].name
    st.warning(
        f"⚠️ Submitting writes all pending changes to YAML transform files "
        f"and `{curie_csv_name}`. This cannot be automatically undone."
    )

    if st.button("🚀 Submit all change requests", type="primary", use_container_width=True):
        with st.spinner("Applying changes …"):
            results, _ok, log_path = submit_all(study, pending, curator)
            st.session_state[f"pending_{study}"] = pending
        for r in results:
            (st.success if r.startswith("✓") else st.warning if r.startswith("⚠") else st.error)(r)
        st.success(f"✅ Change log saved: `{log_path.name}`")
        load_review_rows.clear()
        st.balloons()
        st.rerun()


# ── Change Log tab ────────────────────────────────────────────────────────────
def render_log_tab(study: str, pending: dict) -> None:
    logs = _list_change_logs(study)

    if logs:
        st.subheader(f"Committed change logs — {len(logs)} submission(s)")
        for lp in logs:
            data = json.loads(lp.read_text(encoding="utf-8"))
            n = len(data.get("changes", {}))
            with st.expander(
                f"📄 {lp.name} · {data.get('study','')} · {n} change(s) · {data.get('curator','')} · {data.get('submitted_date','')}",
                expanded=False,
            ):
                st.json(data)
                st.download_button(
                    f"⬇ {lp.name}",
                    data=lp.read_bytes(),
                    file_name=lp.name,
                    mime="application/json",
                    key=f"dl_{lp.name}",
                )

    pending_rows = [
        {
            "File":      k.split("::", 2)[-1],
            "Slot":      v.get("slot", ""),
            "New CURIE": v.get("change_request", ""),
            "Saved":     v.get("saved_date", ""),
        }
        for k, v in pending.items()
        if v.get("change_request") and not v.get("applied")
    ]
    if pending_rows:
        st.divider()
        st.subheader(f"Pending (not yet submitted) — {len(pending_rows)} item(s)")
        st.dataframe(pending_rows, use_container_width=True)

    if not logs and not pending_rows:
        st.info("No change history yet.")

    if pending_rows or logs:
        st.divider()
        col_dl, col_clear = st.columns([3, 1])
        with col_dl:
            ppath = _pending_path(study)
            st.download_button(
                f"⬇ Download {ppath.name}",
                data=ppath.read_bytes() if ppath.exists() else b"{}",
                file_name=ppath.name,
                mime="application/json",
            )
        with col_clear:
            if st.button("🗑️ Clear pending", type="secondary"):
                cleared = {k: v for k, v in pending.items() if v.get("applied")}
                st.session_state[f"pending_{study}"] = cleared
                _save_pending(cleared, study)
                st.rerun()


# ── Pipeline helpers ──────────────────────────────────────────────────────────
# Module-level job store — threads write here; avoids cross-thread session_state writes
_BG_JOBS: dict[str, dict] = {}


def _start_bg_pipeline(label: str, cmd: list[str], cmd_type: str) -> None:
    """Launch subprocess in a background thread so the UI stays interactive."""
    import uuid
    job_id = str(uuid.uuid4())
    _BG_JOBS[job_id] = {"label": label, "lines": [], "rc": None, "done": False, "cmd_type": cmd_type}
    st.session_state._bg_job_id = job_id

    def _worker() -> None:
        job = _BG_JOBS[job_id]
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=str(_HERE),
            )
            for line in proc.stdout:  # type: ignore[union-attr]
                job["lines"].append(line.rstrip())
            proc.wait()
            job["rc"] = proc.returncode
        except Exception as exc:
            job["lines"].append(f"ERROR: {exc}")
            job["rc"] = -1
        finally:
            job["done"] = True

    threading.Thread(target=_worker, daemon=True).start()


# ── Semantic Summary tab ──────────────────────────────────────────────────────
def render_summary_tab(study: str) -> None:
    fk = STUDIES[study]["file_key"]
    summary_path = _find_summary_md(fk)
    review_md_path = STUDIES[study]["review_md"]

    summary_label = "📊 Summary ✅" if summary_path else "📊 Summary"
    detail_label  = "📄 Detailed Review ✅" if review_md_path.exists() else "📄 Detailed Review"
    tab_summary, tab_detail = st.tabs([summary_label, detail_label])

    with tab_summary:
        if summary_path:
            st.caption(f"Source: `{summary_path.name}` — last generated {date.fromtimestamp(summary_path.stat().st_mtime)}")
            st.download_button(
                f"⬇ Download {summary_path.name}",
                data=summary_path.read_bytes(),
                file_name=summary_path.name,
                mime="text/markdown",
                key=f"dl_summary_{study}",
            )
            st.divider()
            st.markdown(summary_path.read_text(encoding="utf-8"))
        else:
            st.info(
                f"No summary file generated for **{STUDIES[study]['label']}** yet. "
                "Run **📝 Generate semantic review MD** (⚙️ Setup tab) to create it."
            )

    with tab_detail:
        if review_md_path.exists():
            st.caption(f"Source: `{review_md_path.name}` — last generated {date.fromtimestamp(review_md_path.stat().st_mtime)}")
            st.download_button(
                f"⬇ Download {review_md_path.name}",
                data=review_md_path.read_bytes(),
                file_name=review_md_path.name,
                mime="text/markdown",
                key=f"dl_review_{study}",
            )
            st.divider()
            st.markdown(review_md_path.read_text(encoding="utf-8"))
        else:
            st.info("Detailed review file not yet generated. Run **Curie Review** (⚙️ Setup tab).")


# ── Setup tab ─────────────────────────────────────────────────────────────────
_STATUS_JSON = _HERE / "valueset_mapping_review_output" / "pipeline_status.json"


def _render_all_studies_status() -> None:
    import json as _json
    st.subheader("All studies — pipeline overview")
    if not _STATUS_JSON.exists():
        st.caption("No `pipeline_status.json` yet — run any pipeline step to generate it.")
        return

    try:
        status = _json.loads(_STATUS_JSON.read_text(encoding="utf-8"))
    except Exception as exc:
        st.warning(f"Could not read pipeline_status.json: {exc}")
        return

    studies_data = status.get("studies", {})
    last_updated = status.get("last_updated", "")

    rows_md = []
    for study_name, s in studies_data.items():
        mp = s.get("mapreview")
        sr = s.get("semantic_review")
        input_ver = s.get("input_version", 1)
        release   = s.get("release") or "—"
        if mp:
            mp_cell = f"✅ {mp['completed'][:10]} ({mp['rows']} rows)"
        else:
            mp_cell = "⏳ not run"
        sr_cell = f"✅ {sr['completed'][:10]}" if sr else "⏳ not run"
        rows_md.append(f"| {study_name} | v{input_ver} | {mp_cell} | {sr_cell} | {release} |")

    md_lines = [
        "| Study | Input ver | Mapreview (step 1) | Semantic Review MD (step 2) | Release |",
        "| :---- | :---: | :---- | :---- | :---: |",
    ] + rows_md
    st.markdown("\n".join(md_lines))
    if last_updated:
        st.caption(f"Status file last updated: {last_updated}")
    st.divider()


def render_setup_tab(study: str) -> None:
    cfg = STUDIES[study]
    label = STUDIES[study]["label"]

    # ── Last pipeline result (shown here, dismissed by user) ──────────────────
    result = st.session_state.get("_pipeline_result")
    if result:
        rc    = result["rc"]
        lbl   = result["label"]
        lines = result["lines"]
        if rc == 0:
            st.success(f"✅ {lbl} — done.")
        else:
            st.error(f"❌ {lbl} — failed (exit {rc}).")
        if lines:
            with st.expander("Output log", expanded=rc != 0):
                st.code("\n".join(lines), language=None)
        if st.button("Dismiss", key="dismiss_pipeline_result"):
            st.session_state.pop("_pipeline_result", None)
            st.rerun()
        st.divider()

    _render_all_studies_status()

    # ── File status ───────────────────────────────────────────────────────────
    st.subheader("Pipeline file status")
    status_rows = [
        ("CURIE CSV (input)",            cfg["curie_csv"],      True),
        ("Map-review CSV (step 1 out)",  cfg["mapreview_csv"],  False),
        ("Semantic review MD (step 2 out)", cfg["review_md"],   False),
    ]
    all_ready = all(p.exists() for _, p, _ in status_rows)
    for lbl, path, required in status_rows:
        exists = path.exists()
        icon = "✅" if exists else ("❌" if required else "⏳")
        c1, c2 = st.columns([2, 5])
        with c1:
            st.markdown(f"{icon} **{lbl}**")
        with c2:
            if exists:
                from datetime import datetime as _dt
                mtime = _dt.fromtimestamp(path.stat().st_mtime)
                st.code(str(path.relative_to(_HERE.parent)), language=None)
                st.caption(f"completed {mtime.strftime('%Y-%m-%d %H:%M')}")
            else:
                st.code(f"{path.name}  — not found", language=None)

    st.divider()

    # ── Individual steps (for re-runs / partial updates) ─────────────────────
    pipeline_running = st.session_state.get("pipeline_running", False)
    with st.expander("⚙️ Run individual steps", expanded=True):
        st.caption("Use these for partial re-runs after fixing issues.")

        st.markdown("**Step 1 — CURIE map-review**")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔍 YAML check only (fast)", key=f"noagents_{study}",
                         use_container_width=True, disabled=pipeline_running):
                st.session_state.pipeline_running = True
                st.session_state._pipeline_cmd = ("step1_noagents", study)
                st.rerun()
        with c2:
            if st.button("🤖 Full agent run", key=f"agents_{study}",
                         use_container_width=True, disabled=pipeline_running):
                st.session_state.pipeline_running = True
                st.session_state._pipeline_cmd = ("step1_agents", study)
                st.rerun()

        st.markdown("**Step 2 — Semantic review MD**")
        mapreview_ready = cfg["mapreview_csv"].exists()
        if not mapreview_ready:
            st.caption("⏳ Step 1 must be run first.")
        if st.button(
            "📝 Generate semantic review MD",
            key=f"semantic_{study}",
            use_container_width=True,
            disabled=not mapreview_ready or pipeline_running,
        ):
            st.session_state.pipeline_running = True
            st.session_state._pipeline_cmd = ("step2", study)
            st.rerun()


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    st.set_page_config(
        page_title="Semantic Review Curator",
        page_icon="🔬",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown("""
    <style>
    /* Reduce top padding in sidebar and main content */
    section[data-testid="stSidebar"] > div:first-child { padding-top: 0.5rem !important; }
    .block-container { padding-top: 1rem !important; }

    /* Sidebar — compact fonts and tighter spacing */
    section[data-testid="stSidebar"] .stSelectbox label,
    section[data-testid="stSidebar"] .stMultiSelect label,
    section[data-testid="stSidebar"] .stTextInput label,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] p {
        font-size: 0.78rem !important;
        line-height: 1.3 !important;
    }
    section[data-testid="stSidebar"] h1 { font-size: 1.0rem !important; margin-bottom: 0.3rem !important; }
    section[data-testid="stSidebar"] h2 { font-size: 0.88rem !important; }
    section[data-testid="stSidebar"] [data-testid="stMetric"] {
        padding: 0.15rem 0 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stMetricLabel"] {
        font-size: 0.72rem !important;
    }
    section[data-testid="stSidebar"] [data-testid="stMetricValue"] {
        font-size: 1.1rem !important;
    }
    section[data-testid="stSidebar"] hr { margin: 0.4rem 0 !important; }
    section[data-testid="stSidebar"] .stButton button {
        font-size: 0.78rem !important;
        padding: 0.25rem 0.5rem !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # ── Sidebar ───────────────────────────────────────────────────────────────
    def _on_study_change() -> None:
        new_study = st.session_state["selected_study"]
        pk = f"pending_{new_study}"
        if pk not in st.session_state:
            st.session_state[pk] = _load_pending(new_study)
        # Clear cached review data so the new study loads fresh on next render
        load_review_rows.clear()
        load_curie_csv.clear()

    st.sidebar.title("🔬 Semantic Review Curator")
    study = st.sidebar.selectbox(
        "Clinical research study dataset",
        options=list(STUDIES),
        format_func=lambda s: f"{STUDIES[s]['label']} — {STUDIES[s]['description']}",
        key="selected_study",
        on_change=_on_study_change,
    )
    st.sidebar.divider()

    # Load pending changes per-study so switching studies loads the correct set
    pending_key = f"pending_{study}"
    if pending_key not in st.session_state:
        st.session_state[pending_key] = _load_pending(study)
    pending = st.session_state[pending_key]

    confirmed_rows = load_review_rows(study)
    n_pending   = sum(1 for v in pending.values() if v.get("change_request") and not v.get("applied"))
    n_applied   = sum(1 for v in pending.values() if v.get("applied"))
    n_no_change = sum(1 for v in pending.values() if v.get("no_change"))

    study_ready = (
        STUDIES[study]["review_md"].exists() and STUDIES[study]["mapreview_csv"].exists()
    )
    pipeline_running = st.session_state.get("pipeline_running", False)

    if not study_ready or pipeline_running:
        if pipeline_running:
            st.sidebar.button(
                f"⏳ Pipeline running…",
                disabled=True,
                use_container_width=True,
                type="primary",
            )
            if st.sidebar.button("🔄 Reset stuck pipeline", key="reset_pipeline",
                                 use_container_width=True):
                for _k in ("pipeline_running", "_bg_job_id", "_pipeline_result",
                           "_bg_label", "_bg_lines", "_bg_rc", "_bg_done", "_bg_cmd_type"):
                    st.session_state.pop(_k, None)
                st.rerun()
        st.sidebar.divider()

    st.sidebar.metric("Reviewer findings", len(confirmed_rows))
    st.sidebar.metric("Pending 💾",         n_pending)
    st.sidebar.metric("Applied ✅",          n_applied)
    st.sidebar.metric("Reviewed — no change needed ☑", n_no_change)

    _all_priorities = sorted({row.get("Priority", "") for row in confirmed_rows if row.get("Priority", "")})
    if not _all_priorities:
        _all_priorities = ["P1", "P2", "P3"]

    if n_pending > 0:
        # st.metric can't be clicked — list the pending rows individually so a
        # curator can jump straight to one instead of scrolling/scanning the
        # (potentially long) findings list to find whichever row they left
        # mid-edit.
        with st.sidebar.expander(f"💾 Jump to pending ({n_pending})", expanded=False):
            for _row in confirmed_rows:
                _rid = _row_key(study, _row.get("File", ""), _row.get("PHV", "").strip())
                _saved = pending.get(_rid, {})
                if not (_saved.get("change_request") and not _saved.get("applied")):
                    continue
                _jump_label = f"`{_unescape_md(_row.get('File',''))[:40]}` — {_row.get('Final issue','')[:40]}"
                if st.button(_jump_label, key=f"jump_{_rid}", use_container_width=True):
                    _row_priority = _row.get("Priority", "")
                    if _row_priority and _row_priority not in _all_priorities:
                        _all_priorities = sorted(set(_all_priorities) | {_row_priority})
                    if _row_priority:
                        st.session_state[f"priority_filter_{study}"] = sorted(
                            set(st.session_state.get(f"priority_filter_{study}", _all_priorities)) | {_row_priority}
                        )
                    st.session_state["jump_to_row_id"] = _rid
                    st.rerun()
    st.sidebar.divider()

    priority_filter = st.sidebar.multiselect(
        "Priority filter", _all_priorities, default=_all_priorities,
        key=f"priority_filter_{study}",
    )
    st.sidebar.divider()

    curator_sidebar = st.sidebar.text_input("Curator name", value="Curator", key="curator_sidebar")

    if n_pending > 0:
        if st.sidebar.button(
            f"🚀 Submit all ({n_pending})", type="primary", use_container_width=True
        ):
            with st.spinner("Applying …"):
                results, ok, log_path = submit_all(study, pending, curator_sidebar)
                st.session_state[pending_key] = pending
            err = len(results) - ok
            st.sidebar.success(f"{ok} applied · {log_path.name}")
            if err:
                st.sidebar.warning(f"{err} warning(s) — see Submit tab.")
            load_review_rows.clear()
            st.rerun()
    else:
        st.sidebar.button(
            "🚀 Submit all", disabled=True, use_container_width=True,
            help="Save at least one change request first.",
        )

    if st.sidebar.button("♻️ Reload review file", use_container_width=True):
        load_review_rows.clear()
        load_curie_csv.clear()
        load_mapreview_csv.clear()
        st.rerun()

    # ── Study dataset stats ───────────────────────────────────────────────────
    _, curie_rows    = load_curie_csv(study)
    _, mapreview_rows = load_mapreview_csv(study)
    if curie_rows or mapreview_rows:
        st.sidebar.divider()
        st.sidebar.caption("📋 Study dataset stats")
        if curie_rows:
            distinct_vars = len({r.get("Variable Name", "") for r in curie_rows if r.get("Variable Name", "")})
            st.sidebar.metric("Distinct variables", distinct_vars)
        if mapreview_rows:
            missing_curies = sum(
                1 for r in mapreview_rows
                if not r.get("CURIE", "").strip()
            )
            yaml_not_found = len({
                r.get("YAML File", "") for r in mapreview_rows
                if r.get("yaml_curie", "").strip() == "(file not found)"
                and r.get("YAML File", "").strip()
            })
            st.sidebar.metric("Missing CURIEs", missing_curies)
            st.sidebar.metric("YAML files not found", yaml_not_found)

    # ── Cross-study aggregate ─────────────────────────────────────────────────
    st.sidebar.divider()
    with st.sidebar.expander("All studies aggregate", expanded=False):
        _agg_vars       = 0
        _agg_reviewed   = 0
        _agg_applied    = 0
        _agg_pending    = 0
        _agg_no_change  = 0
        _agg_done_count = 0
        for _s in STUDIES:
            _, _csv_rows = load_curie_csv(_s)
            _agg_vars += len(_csv_rows)
            if STUDIES[_s]["review_md"].exists():
                _agg_reviewed   += len(load_review_rows(_s))
                _agg_done_count += 1
            _p = st.session_state.get(f"pending_{_s}") or _load_pending(_s)
            _agg_applied   += sum(1 for v in _p.values() if v.get("applied"))
            _agg_pending   += sum(1 for v in _p.values() if v.get("change_request") and not v.get("applied"))
            _agg_no_change += sum(1 for v in _p.values() if v.get("no_change"))
        st.metric("Total variables", f"{_agg_vars:,}")
        st.metric(f"Review findings ({_agg_done_count}/{len(STUDIES)} studies)", _agg_reviewed)
        st.metric("Applied ✅", _agg_applied)
        st.metric("Pending 💾", _agg_pending)
        st.metric("Reviewed ☑", _agg_no_change)

    # ── Deferred pipeline command (set by individual step buttons) ───────────
    _pcmd = st.session_state.pop("_pipeline_cmd", None)
    if _pcmd:
        _cmd_type, _cmd_study = _pcmd
        _cfg = STUDIES[_cmd_study]
        _lbl = _cfg["label"]
        if _cmd_type == "step1_noagents":
            _start_bg_pipeline(
                f"Map-review YAML check — {_lbl}",
                [sys.executable, str(_SCRIPTS_DIR / "generate_curie_mapreview.py"),
                 "--study", _cmd_study, "--no-agents"],
                _cmd_type,
            )
        elif _cmd_type == "step1_agents":
            _start_bg_pipeline(
                f"Map-review full agents — {_lbl}",
                [sys.executable, str(_SCRIPTS_DIR / "generate_curie_mapreview.py"),
                 "--study", _cmd_study],
                _cmd_type,
            )
        elif _cmd_type == "step2":
            _start_bg_pipeline(
                f"Semantic review — {_lbl}",
                [sys.executable, str(_SCRIPTS_DIR / "generate_semantic_review.py"),
                 "--study", _cmd_study],
                _cmd_type,
            )
        # pipeline_running stays True — cleared below when the bg thread finishes
        st.session_state._pipeline_start_ts = time.time()

    # ── Background pipeline polling ───────────────────────────────────────────
    if st.session_state.get("pipeline_running"):
        # Auto-clear if stuck for more than 10 minutes (e.g. after hot-reload)
        _start_ts = st.session_state.setdefault("_pipeline_start_ts", time.time())
        if time.time() - _start_ts > 600:
            for _k in ("pipeline_running", "_bg_job_id", "_pipeline_start_ts",
                       "_bg_label", "_bg_lines", "_bg_rc", "_bg_done", "_bg_cmd_type"):
                st.session_state.pop(_k, None)
            st.rerun()

        job_id = st.session_state.get("_bg_job_id", "")
        job    = _BG_JOBS.get(job_id)
        if job and not job["done"]:
            # Still running — poll silently; sidebar button already shows ⏳
            time.sleep(0.5)
            st.rerun()
        else:
            # Thread finished (or job not found) — save result for Setup tab
            if job:
                st.session_state._pipeline_result = {
                    "label": job["label"],
                    "rc":    job["rc"] if job["rc"] is not None else -1,
                    "lines": job["lines"],
                }
                cmd_type = job["cmd_type"]
                _BG_JOBS.pop(job_id, None)
            else:
                cmd_type = ""
            if cmd_type in ("step1_noagents", "step1_agents"):
                load_mapreview_csv.clear()
            elif cmd_type == "step2":
                load_review_rows.clear()
            st.session_state.pipeline_running = False
            st.session_state.pop("_bg_job_id", None)
            st.rerun()

    # ── Main content area ─────────────────────────────────────────────────────
    st.markdown(
        '<p style="font-size:0.85em;color:#888;margin-bottom:0;letter-spacing:0.08em">'
        'SEMANTIC REVIEW CURATOR</p>',
        unsafe_allow_html=True,
    )
    st.title(f"🔬 {STUDIES[study]['label']} — {STUDIES[study]['description']}")

    # Nudge toward Setup tab when files are missing
    review_ready    = STUDIES[study]["review_md"].exists()
    mapreview_ready = STUDIES[study]["mapreview_csv"].exists()
    if not review_ready or not mapreview_ready:
        st.warning(
            f"**{STUDIES[study]['label']} semantic review files must be generated first.** "
            f"Go to the **⚙️ Setup** tab to generate the required files."
        )

    fk = STUDIES[study]["file_key"]
    summary_exists = _find_summary_md(fk) is not None
    summary_label = "📊 Semantic Review Summary ✅" if summary_exists else "📊 Semantic Review Summary"

    n_orphans = len(_orphan_pending(study, pending, confirmed_rows))
    notes_label = f"📝 Manual Notes ({n_orphans})" if n_orphans else "📝 Manual Notes"

    tab_conf, tab_notes, tab_xstudy, tab_summary, tab_committed, tab_submit, tab_log, tab_setup = st.tabs([
        f"Reviewer Findings ({len(confirmed_rows)})",
        notes_label,
        "Cross-Study Consistency",
        summary_label,
        f"Previously Committed ✅ ({n_applied})",
        f"Submit 🚀 ({n_pending} pending)",
        "Change Log 📋",
        "⚙️ Setup",
    ])

    with tab_conf:
        if not confirmed_rows and not review_ready:
            st.info(
                f"No semantic review file found for **{STUDIES[study]['label']}**. "
                f"Go to the **⚙️ Setup** tab to generate it."
            )
        else:
            # Pop (not peek) so the jump only forces that row open on this one
            # rerun — the expander's own widget state takes over from there,
            # same as every other row, rather than fighting the user if they
            # manually collapse it again later.
            _jump_to_row_id = st.session_state.pop("jump_to_row_id", None)
            shown = 0
            for i, row in enumerate(confirmed_rows):
                if row.get("Priority") not in priority_filter:
                    continue
                _rid = _row_key(study, row.get("File", ""), row.get("PHV", "").strip())
                render_row(row, study, pending, i, force_expanded=(_rid == _jump_to_row_id))
                shown += 1
            if shown == 0:
                st.info("No rows match current filters.")

    with tab_notes:
        render_manual_notes_tab(study, pending, confirmed_rows)

    with tab_xstudy:
        render_cross_study_tab()

    with tab_summary:
        render_summary_tab(study)

    with tab_committed:
        render_committed_tab(study, pending)

    with tab_submit:
        render_submit_tab(study, pending)

    with tab_log:
        render_log_tab(study, pending)

    with tab_setup:
        render_setup_tab(study)


if __name__ == "__main__":
    main()
