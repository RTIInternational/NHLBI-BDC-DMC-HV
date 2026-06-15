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
_CURIE_RE = re.compile(r"`([A-Z][A-Z0-9_]*:[A-Z0-9.]+)`|([A-Z][A-Z0-9_]*:[A-Z0-9.]+)")

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
    text = re.sub(r'`([A-Z][A-Z0-9_]*:[A-Z0-9.]+)`', r'\1', text)
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


def _curie_link_md(curie: str) -> None:
    url = _curie_to_url(curie)
    if url:
        st.markdown(f'<a href="{url}" target="_blank"><code>{curie}</code></a>', unsafe_allow_html=True)
    else:
        st.code(curie, language=None)


def _extract_agent_curies(validator_text: str) -> list[str]:
    hits = re.findall(r"agent\s*→\s*`([^`]+)`", validator_text)
    result: list[str] = []
    for h in hits:
        for part in h.split(","):
            c = part.strip()
            if c:
                result.append(c)
    return result


def _unescape_md(s: str) -> str:
    return re.sub(r"\\(.)", r"\1", s.strip())


# ── MD parsing — Confirmed Findings only ──────────────────────────────────────
_CONF_HEADERS = [
    "Priority", "File", "Final issue", "Evidence to confirm",
    "Recommended action", "Confidence", "Reviewer",
    "Source alignment", "semantic validator review",
]


def _parse_md_table(lines: list[str], headers: list[str]) -> list[dict]:
    rows = []
    for line in lines:
        s = line.strip()
        if not s.startswith("|") or re.match(r"^\|[\s:|-]+\|", s):
            continue
        # Unescape markdown-escaped characters (e.g. \` → `) so downstream
        # rendering helpers see bare backticks rather than backslash+backtick sequences.
        cells = [_unescape_md(c) for c in s.strip("|").split("|")]
        if not cells or cells[0] == headers[0]:
            continue
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


def get_curie_csv_rows_for_file(study: str, yaml_file: str, slot: str) -> list[dict]:
    """Return all curie CSV rows matching yaml_file (basename) + slot."""
    _, rows = load_curie_csv(study)
    fname = Path(yaml_file).name
    return [r for r in rows if r.get("YAML File") == fname and r.get("Slot") == slot]


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
def _apply_yaml(study: str, yaml_file: str, slot: str, new_curie: str) -> str:
    yaml_path = STUDIES[study]["yaml_dir"] / Path(yaml_file).name
    if not yaml_path.exists():
        return f"❌ YAML not found: `{yaml_file}`"
    text = yaml_path.read_text(encoding="utf-8")
    pattern = rf"(\b{re.escape(slot)}:\s*\n[ \t]+value:\s+)\S+"
    new_text, n = re.subn(pattern, rf"\g<1>{new_curie}", text)
    if n == 0:
        return f"⚠ No `{slot}: value:` pattern in `{yaml_file}`"
    yaml_path.write_text(new_text, encoding="utf-8")
    return f"✓ YAML `{yaml_file}` [{slot}] → `{new_curie}` ({n} match)"


def _apply_csv(study: str, yaml_file: str, slot: str, new_curie: str) -> str:
    fieldnames, rows = load_curie_csv(study)
    updated, changed = [], 0
    for row in rows:
        if row.get("YAML File") == Path(yaml_file).name and row.get("Slot") == slot:
            row = dict(row)
            row["CURIE"] = new_curie
            changed += 1
        updated.append(row)
    if changed == 0:
        return f"⚠ No CSV rows match `{yaml_file}` / `{slot}`"
    with open(STUDIES[study]["curie_csv"], "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(updated)
    load_curie_csv.clear()
    return f"✓ CSV: {changed} row(s) → `{new_curie}` for `{yaml_file}` [{slot}]"


# ── Batch submit ──────────────────────────────────────────────────────────────
def submit_all(study: str, pending: dict, curator: str) -> tuple[list[str], Path]:
    results: list[str] = []
    submitted: dict = {}
    for key, val in pending.items():
        new_curie = val.get("change_request", "").strip()
        if not new_curie or val.get("applied"):
            continue
        slot    = val.get("slot", "")
        yf_list = val.get("yaml_files", [])
        row_res: list[str] = []
        for yf in yf_list:
            r1 = _apply_yaml(study, yf, slot, new_curie)
            r2 = _apply_csv(study, yf, slot, new_curie)
            row_res.extend([r1, r2])
        results.extend(row_res)
        val.update({"applied": True, "applied_date": date.today().isoformat(), "applied_by": curator})
        submitted[key] = {**val, "apply_results": row_res}

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
    return results, log_path


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


def _row_key(study: str, file_field: str) -> str:
    return f"{study}::confirmed::{_unescape_md(file_field)}"


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


def render_row(row: dict, study: str, pending: dict, idx: int) -> None:
    file_field  = row.get("File", "")
    yaml_files  = _extract_yaml_files(file_field)
    auto_slot   = _detect_slot(row.get("semantic validator review", ""))
    priority    = row.get("Priority", "")
    issue       = row.get("Final issue", "")
    recommended = row.get("Recommended action", "")
    validator   = row.get("semantic validator review", "")

    row_id = _row_key(study, file_field)
    saved  = pending.get(row_id, {})

    badge      = {"P1": "🔴", "P2": "🟡", "P3": "🟢"}.get(priority, "⚪")
    done_badge = (
        " ✅" if saved.get("applied")
        else " ☑" if saved.get("no_change")
        else " 💾" if saved.get("change_request")
        else " 📝" if saved.get("notes")
        else ""
    )
    label = f"{badge} **{priority}** · `{_unescape_md(file_field)}` — {issue[:70]}{'…' if len(issue)>70 else ''}{done_badge}"

    with st.expander(label, expanded=False):
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
                _orig_html   = f" &nbsp;(was: <code>{_orig_curie}</code>)" if _orig_curie else ""
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
                det_suggestions = _extract_agent_curies(validator)
                st.markdown("**Agent suggestion:**")
                if det_suggestions:
                    for s in det_suggestions:
                        _curie_link_md(s)
                else:
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

                agent_suggestions = _extract_agent_curies(validator)
                if agent_suggestions:
                    st.markdown("**Agent suggestion:**")
                    for s in agent_suggestions:
                        _curie_link_md(s)

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
    anchored = {_row_key(study, row["File"]) for row in confirmed_rows if row.get("File")}
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
                    st.markdown(f"**Original CURIE:** `{orig_curie}`")

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
            results, log_path = submit_all(study, pending, curator)
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
def _stream_subprocess(cmd: list[str], log_area) -> tuple[int, list[str]]:
    """Run cmd, stream combined stdout/stderr into log_area. Returns (returncode, lines)."""
    lines: list[str] = []
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(_HERE),
    )
    for line in proc.stdout:  # type: ignore[union-attr]
        lines.append(line.rstrip())
        log_area.code("\n".join(lines[-50:]))
    proc.wait()
    return proc.returncode, lines


def _run_pipeline_cmd(label: str, cmd: list[str]) -> None:
    """In-tab subprocess runner with spinner + rolling log + final expander."""
    log_area = st.empty()
    with st.spinner(f"{label} …"):
        rc, lines = _stream_subprocess(cmd, log_area)
    log_area.empty()
    if rc == 0:
        st.success(f"✅ {label} — done.")
    else:
        st.error(f"❌ {label} — failed (exit {rc}).")
    with st.expander("Output log", expanded=rc != 0):
        st.code("\n".join(lines) if lines else "(no output)")


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


# ── Full-page Registration flow ───────────────────────────────────────────────
def render_registration_page(study: str) -> None:
    """Replaces the entire UI while the pipeline runs. Nothing else is rendered."""
    cfg = STUDIES[study]
    label = STUDIES[study]["label"]

    st.markdown(
        '<p style="font-size:0.85em;color:#888;margin-bottom:0;letter-spacing:0.08em">'
        "SEMANTIC REVIEW CURATOR — CURIE REVIEW IN PROGRESS</p>",
        unsafe_allow_html=True,
    )
    st.title(f"⚙️ Preparing {label} Curie Review")

    st.markdown(
        f"""
        <div style="background:#fff8e1;padding:14px 18px;border-radius:6px;
                    border-left:5px solid #f9a825;margin-bottom:1rem;font-size:0.95em">
        ⏳ <strong>Generating all required files for {label}.</strong><br>
        This may take <strong>10–20 minutes</strong>. Please keep this window open and do not
        navigate away. All other controls are disabled until this process completes.
        </div>
        """,
        unsafe_allow_html=True,
    )

    overall_ok = True

    # ── Step 1: CURIE map-review (full agents) ────────────────────────────────
    st.subheader("Step 1 of 2 — CURIE map-review (agent run)")
    st.caption(f"Input: `{cfg['curie_csv'].name}` → Output: `{cfg['mapreview_csv'].name}`")
    log1 = st.empty()
    with st.spinner(f"Running MONDO / HPO / OMOP / RxNorm / LOINC agents for {label} …"):
        rc1, lines1 = _stream_subprocess(
            [sys.executable, str(_SCRIPTS_DIR / "generate_curie_mapreview.py"), "--study", study],
            log1,
        )
    log1.empty()
    if rc1 == 0:
        st.success(f"✅ Step 1 complete — `{cfg['mapreview_csv'].name}` written.")
        load_mapreview_csv.clear()
    else:
        st.error(f"❌ Step 1 failed (exit {rc1}). Step 2 will be skipped.")
        overall_ok = False
    with st.expander("Step 1 output log", expanded=rc1 != 0):
        st.code("\n".join(lines1) if lines1 else "(no output)")

    st.divider()

    # ── Step 2: semantic review MD ────────────────────────────────────────────
    st.subheader("Step 2 of 2 — Semantic review MD")
    st.caption(
        f"Input: `{cfg['mapreview_csv'].name}` + source reviewer MD "
        f"→ Output: `{cfg['review_md'].name}`"
    )
    if not overall_ok:
        st.warning("⚠️ Skipped because Step 1 failed.")
    else:
        log2 = st.empty()
        with st.spinner(f"Generating semantic review for {label} …"):
            rc2, lines2 = _stream_subprocess(
                [sys.executable, str(_SCRIPTS_DIR / "generate_semantic_review.py"), "--study", study],
                log2,
            )
        log2.empty()
        if rc2 == 0:
            st.success(f"✅ Step 2 complete — `{cfg['review_md'].name}` written.")
            load_review_rows.clear()
        else:
            st.error(f"❌ Step 2 failed (exit {rc2}).")
            overall_ok = False
        with st.expander("Step 2 output log", expanded=rc2 != 0):
            st.code("\n".join(lines2) if lines2 else "(no output)")

    st.divider()

    # ── Final result ──────────────────────────────────────────────────────────
    if overall_ok:
        st.balloons()
        fk = _file_key(study)
        summary_path = _find_summary_md(fk)
        st.success(
            f"🎉 **{label} is ready for review!** "
            "Click the button below to open the review."
        )
        if summary_path and summary_path.exists():
            st.info(
                f"📊 **Semantic summary generated:** `{summary_path.name}` — "
                "open the **📊 Semantic Review Summary** tab after returning to view it."
            )
            with st.expander("Preview summary", expanded=True):
                st.markdown(summary_path.read_text(encoding="utf-8"))
    else:
        st.error(
            "Curie review preparation did not complete successfully. "
            "Check the logs above for details, fix any issues, and try again."
        )

    if st.button(
        f"{'🔬 Open review' if overall_ok else '← Return to app'}",
        type="primary",
        use_container_width=True,
    ):
        st.session_state.is_registering = False
        st.session_state.pop("register_study", None)
        st.rerun()


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

    # ── Register for Review (full pipeline, single button) ────────────────────
    st.subheader(f"Prepare {label} Curie Review")
    st.caption(
        "Runs both pipeline steps in sequence: full agent map-review (Step 1) then "
        "semantic review MD generation (Step 2). The entire UI is replaced with a "
        "progress screen until both steps complete."
    )

    curie_csv_name = cfg["curie_csv"].name
    curie_ok = cfg["curie_csv"].exists()
    if not curie_ok:
        st.error(f"❌ CURIE CSV `{curie_csv_name}` not found — cannot register.")
    else:
        st.info(f"📄 CURIE file: **`{curie_csv_name}`** ({label})")

    if st.button(
        f"🚀 Register {label} for Full Review",
        key=f"register_{study}",
        type="primary",
        use_container_width=True,
        disabled=not curie_ok,
        help="Runs both pipeline steps. Takes 10–20 minutes. All controls are locked during processing.",
    ):
        st.session_state.is_registering = True
        st.session_state.register_study = study
        st.rerun()

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

    # ── Registration intercept — full-page takeover while pipeline runs ────────
    if st.session_state.get("is_registering"):
        reg_study = st.session_state.get("register_study", list(STUDIES)[0])
        render_registration_page(reg_study)
        st.stop()  # nothing else renders until registration is done

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
        else:
            if st.sidebar.button(
                f"🚀 Run {STUDIES[study]['label']} Curie Review",
                type="primary",
                use_container_width=True,
                help="Run the full pipeline to generate review files for this study.",
            ):
                st.session_state.is_registering = True
                st.session_state.register_study = study
                st.rerun()
        st.sidebar.divider()

    st.sidebar.metric("Reviewer findings", len(confirmed_rows))
    st.sidebar.metric("Pending 💾",         n_pending)
    st.sidebar.metric("Applied ✅",          n_applied)
    st.sidebar.metric("Reviewed ☑",         n_no_change)
    st.sidebar.divider()

    _all_priorities = sorted({row.get("Priority", "") for row in confirmed_rows if row.get("Priority", "")})
    if not _all_priorities:
        _all_priorities = ["P1", "P2", "P3"]
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
                results, log_path = submit_all(study, pending, curator_sidebar)
                st.session_state[pending_key] = pending
            ok  = sum(1 for r in results if r.startswith("✓"))
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
            shown = 0
            for i, row in enumerate(confirmed_rows):
                if row.get("Priority") not in priority_filter:
                    continue
                render_row(row, study, pending, i)
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
