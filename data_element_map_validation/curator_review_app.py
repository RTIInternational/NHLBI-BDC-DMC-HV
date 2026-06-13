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
        cells = [c.strip() for c in s.strip("|").split("|")]
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
        if "## Final Confirmed Findings" in line:
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


def get_current_curies(study: str, yaml_file: str, slot: str) -> list[str]:
    _, rows = load_curie_csv(study)
    return sorted({
        r["CURIE"] for r in rows
        if r.get("YAML File") == yaml_file and r.get("Slot") == slot and r.get("CURIE")
    })


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
    done_badge = " ✅" if saved.get("applied") else (" 💾" if saved.get("change_request") else "")
    label = f"{badge} **{priority}** · `{_unescape_md(file_field)}` — {issue[:70]}{'…' if len(issue)>70 else ''}{done_badge}"

    with st.expander(label, expanded=False):
        tab_detail, tab_cr = st.tabs(["📋 Details", "✏️ Change request"])

        # ── Details ──────────────────────────────────────────────────────────
        with tab_detail:
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
                        for c in det_curies:
                            _curie_link_md(c)
                    else:
                        st.caption("_Not found in mapreview CSV — variable may be admin/skipped or not in the curie file._")
            with d_right:
                det_suggestions = _extract_agent_curies(validator)
                if det_suggestions:
                    st.markdown("**Agent suggestion:**")
                    for s in det_suggestions:
                        _curie_link_md(s)
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
                        for c in curies:
                            _curie_link_md(c)
                    else:
                        st.caption("_Not found in mapreview CSV — variable may be admin/skipped or not in the curie file._")

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
                    "New CURIE *",
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
                    "💾 Save change request", key=f"save_{study}_{idx}",
                    type="primary", use_container_width=True,
                ):
                    err = _validate_curie(new_cr)
                    if err:
                        st.error(f"Invalid CURIE — {err}")
                    elif not use_slot:
                        st.error("Slot is required.")
                    else:
                        # Capture original CURIE now, before any apply overwrites it
                        original_curies = get_current_curies(study, yaml_files[0], use_slot) if yaml_files else []
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
                        st.toast(f"✓ Saved — CR CSV updated ({n} row(s))")
                        st.rerun()

                if saved.get("change_request") and not saved.get("applied"):
                    url = _curie_to_url(saved["change_request"])
                    link = (
                        f'<a href="{url}" target="_blank"><code>{saved["change_request"]}</code></a>'
                        if url else f'<code>{saved["change_request"]}</code>'
                    )
                    st.markdown(f"💾 Saved: {link} → `{saved.get('slot')}`", unsafe_allow_html=True)
                elif saved.get("applied"):
                    st.success(f"✅ Applied: `{saved['change_request']}`")


# ── Previously Committed tab ──────────────────────────────────────────────────
def render_committed_tab(study: str, pending: dict) -> None:
    applied = {k: v for k, v in pending.items() if v.get("applied") and v.get("study", study) == study}

    if not applied:
        st.info("No committed changes for this study yet. Changes appear here after you submit.")
        return

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


# ── Submit tab ────────────────────────────────────────────────────────────────
def render_submit_tab(study: str, pending: dict) -> None:
    not_applied = {
        k: v for k, v in pending.items()
        if v.get("change_request") and not v.get("applied")
    }

    st.subheader("Pending change requests")
    if not not_applied:
        st.info("No pending change requests. Save requests in the ✏️ Change request tab.")
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
def render_setup_tab(study: str) -> None:
    cfg = STUDIES[study]
    label = STUDIES[study]["label"]

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
            st.code(
                str(path.relative_to(_HERE.parent)) if exists else f"{path.name}  — not found",
                language=None,
            )

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
    with st.expander("⚙️ Run individual steps", expanded=True):
        st.caption("Use these for partial re-runs after fixing issues.")

        st.markdown("**Step 1 — CURIE map-review**")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔍 YAML check only (fast)", key=f"noagents_{study}", use_container_width=True):
                _run_pipeline_cmd(
                    f"Map-review YAML check — {label}",
                    [sys.executable, str(_SCRIPTS_DIR / "generate_curie_mapreview.py"),
                     "--study", study, "--no-agents"],
                )
                load_mapreview_csv.clear()
                st.rerun()
        with c2:
            if st.button("🤖 Full agent run", key=f"agents_{study}", use_container_width=True):
                _run_pipeline_cmd(
                    f"Map-review full agents — {label}",
                    [sys.executable, str(_SCRIPTS_DIR / "generate_curie_mapreview.py"), "--study", study],
                )
                load_mapreview_csv.clear()
                st.rerun()

        st.markdown("**Step 2 — Semantic review MD**")
        mapreview_ready = cfg["mapreview_csv"].exists()
        if not mapreview_ready:
            st.caption("⏳ Step 1 must be run first.")
        if st.button(
            "📝 Generate semantic review MD",
            key=f"semantic_{study}",
            use_container_width=True,
            disabled=not mapreview_ready,
        ):
            _run_pipeline_cmd(
                f"Semantic review — {label}",
                [sys.executable, str(_SCRIPTS_DIR / "generate_semantic_review.py"), "--study", study],
            )
            load_review_rows.clear()
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
    n_pending = sum(1 for v in pending.values() if v.get("change_request") and not v.get("applied"))
    n_applied = sum(1 for v in pending.values() if v.get("applied"))

    study_ready = (
        STUDIES[study]["review_md"].exists() and STUDIES[study]["mapreview_csv"].exists()
    )
    if not study_ready:
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

    st.sidebar.metric("Confirmed findings", len(confirmed_rows))
    st.sidebar.metric("Pending 💾",         n_pending)
    st.sidebar.metric("Applied ✅",          n_applied)
    st.sidebar.divider()

    priority_filter = st.sidebar.multiselect(
        "Priority filter", ["P1", "P2", "P3"], default=["P1", "P2", "P3"]
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

    tab_conf, tab_summary, tab_committed, tab_submit, tab_log, tab_setup = st.tabs([
        f"Confirmed Findings ({len(confirmed_rows)})",
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
