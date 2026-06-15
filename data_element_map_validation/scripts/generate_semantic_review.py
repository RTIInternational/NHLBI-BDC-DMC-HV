#!/usr/bin/env python3
"""Generate COPDGene_semantic_review_v2026_0610.md.

Reads pre-computed data from COPDGene_curie_mapreview.csv (YAML spot-check
results + agent CURIE suggestions), then cross-references those findings with
the structured review table in the Final-Reviewer MD to produce a new markdown
report with an additional "semantic validator review" column.

No live API calls are made — all suggestions come from the mapreview CSV.

Inputs:
  bdc_study_input/COPDGene_curie_mapreview.csv
  valueset_mapping_review_output/COPDGene Semantic-Review-Final-Reviewer-2026-05-31.md

Output:
  valueset_mapping_review_output/COPDGene_semantic_review_v2026_0610.md
"""

import csv
import re
from pathlib import Path
from datetime import date

# ---------------------------------------------------------------------------
# Paths — resolved at runtime from --study argument
# ---------------------------------------------------------------------------
BASE_DIR    = Path(__file__).parent.parent   # scripts/ → data_element_map_validation/
_REVIEW_OUT = BASE_DIR / "valueset_mapping_review_output"
_REGISTRY_CSV = BASE_DIR / "bdc_study_input" / "BDC_registered_study_for_semantic_review.csv"


def _file_key(short_name: str) -> str:
    return short_name.replace("/", "_").replace(" ", "_")


def _resolve_yaml_dir(row: dict) -> Path:
    """Resolve yaml_file_path from registry row relative to the registry CSV's directory."""
    yaml_rel = row.get("yaml_file_path", "").strip()
    if yaml_rel:
        return (_REGISTRY_CSV.parent / yaml_rel).resolve()
    fk = _file_key(row["cohort_study_short_name"].strip())
    return BASE_DIR.parent / "priority_variables_transform" / f"{fk}-ingest"


def _find_source_reviewer_md(fk: str) -> Path | None:
    """Find the human-authored reviewer MD that serves as input to this script."""
    # Match e.g. "COPDGene Semantic-Review-Final-Reviewer-*.md"
    #         or "CHS_Semantic_Review_Final-Reviewer-*.md"
    for pattern in (f"{fk}*Semantic*Final*.md", f"{fk}*Semantic*Review*.md", f"{fk}*Review*.md"):
        matches = [p for p in _REVIEW_OUT.glob(pattern)
                   if "semantic_review_v" not in p.name]  # exclude generated output files
        if matches:
            return sorted(matches, reverse=True)[0]
    return None


def _load_study_configs() -> dict[str, dict]:
    configs: dict[str, dict] = {}
    if _REGISTRY_CSV.exists():
        import csv as _csv
        with open(_REGISTRY_CSV, newline="", encoding="utf-8-sig") as f:
            for row in _csv.DictReader(f):
                short = row["cohort_study_short_name"].strip()
                fk = _file_key(short)
                src_md = _find_source_reviewer_md(fk)
                out_matches = sorted(_REVIEW_OUT.glob(f"{fk}_semantic_review_v*.md"), reverse=True)
                out_md = out_matches[0] if out_matches else (
                    _REVIEW_OUT / f"{fk}_semantic_review_v{date.today().strftime('%Y_%m%d')}.md"
                )
                configs[short] = {
                    "mapreview_csv": BASE_DIR / "bdc_study_input" / f"{fk}_curie_mapreview.csv",
                    "review_md":     src_md,
                    "output_md":     out_md,
                    # yaml_dir resolved from registry for completeness
                    "yaml_dir":      _resolve_yaml_dir(row),
                }
    if not configs:
        configs["COPDGene"] = {
            "mapreview_csv": BASE_DIR / "bdc_study_input" / "COPDGene_curie_mapreview.csv",
            "review_md":     _REVIEW_OUT / "COPDGene Semantic-Review-Final-Reviewer-2026-05-31.md",
            "output_md":     _REVIEW_OUT / "COPDGene_semantic_review_v2026_0610.md",
            "yaml_dir":      BASE_DIR.parent / "priority_variables_transform" / "COPDGene-ingest",
        }
    return configs


_STUDY_CONFIGS = _load_study_configs()

MAPREVIEW_CSV = _STUDY_CONFIGS["COPDGene"]["mapreview_csv"]
REVIEW_MD     = _STUDY_CONFIGS["COPDGene"]["review_md"]
OUTPUT_MD     = _STUDY_CONFIGS["COPDGene"]["output_md"]
TODAY         = date.today().strftime("%Y-%m-%d")
STUDY         = "COPDGene"


def _resolve_paths(study: str) -> None:
    import sys
    global MAPREVIEW_CSV, REVIEW_MD, OUTPUT_MD, STUDY
    cfg = _STUDY_CONFIGS.get(study)
    if cfg is None:
        print(f"Unknown study '{study}'. Known: {list(_STUDY_CONFIGS)}", file=sys.stderr)
        sys.exit(1)
    src_md = cfg.get("review_md")
    if src_md is None:
        print(
            f"No source reviewer MD found for '{study}' in {_REVIEW_OUT}. "
            "Generating from mapreview CSV only — Final Confirmed Findings and "
            "Anne Review Required tables will be empty.",
            file=sys.stderr,
        )
    MAPREVIEW_CSV = cfg["mapreview_csv"]
    REVIEW_MD     = src_md  # may be None
    OUTPUT_MD     = cfg["output_md"]
    STUDY         = study

# ---------------------------------------------------------------------------
# Curator notes — appended verbatim after the auto-generated validator text
# for specific YAML files.  Add entries here to preserve manual annotations
# across pipeline regenerations.
# Key: yaml filename (unescaped).  Value: extra text to append.
# ---------------------------------------------------------------------------
_CURATOR_NOTES: dict[str, str] = {
    "tak_antihypertensives.yaml": (
        "→ **ATC:C02 is too narrow**: it covers only directly-acting antihypertensives "
        "(hydralazine, methyldopa, minoxidil, clonidine). "
        "The five ATC groups actually prescribed for hypertension are "
        "C02, C03 (diuretics), C07 (beta-blockers), C08 (calcium channel blockers), "
        "C09 (renin-angiotensin agents); no single RxNorm or ATC code covers all of them. "
        "**Recommended options (priority order):** "
        "(1) `SNOMED:372586001` \"Antihypertensive agent (substance)\" — canonical pharmacological "
        "class concept, non-standard in OMOP (std=N); "
        "(2) `MeSH:D000959` \"Antihypertensive Agents\" — present in OMOP vocabulary but non-standard; "
        "(3) Multi-value ATC: C02 + C03 + C07 + C08 + C09 if schema supports multiple drug_concept values; "
        "(4) Retain `ATC:C02` with a curation note that it represents only one subset of antihypertensives. "
        "Since `currmedhighbp` is a binary yes/no self-report, `drug_concept` is acting as a drug-class "
        "label — `ATC:C02` alone misrepresents the full treatment scope. "
        "→ **Flagged for Anne Review**: confirm whether SNOMED drug-class concepts are permitted in "
        "drug_concept slots, or whether multi-value ATC is preferred."
    ),
}

# ---------------------------------------------------------------------------
# Vocabulary-slot compatibility rules
# ---------------------------------------------------------------------------
# Maps slot name → which CURIE prefixes are valid/invalid.
# Used to suppress false-positive agent suggestions and warn in reviewer rows.
_SLOT_VOCAB_RULES: dict[str, dict] = {
    "observation_type": {
        "valid":   {"OBA", "OMOP"},
        "invalid": {"LOINC"},
        "note": (
            "LOINC encodes assay procedures (the *how*) and belongs in `method_type`. "
            "OBA/OMOP encode biological attributes (the *what*) — the correct vocabulary "
            "for `observation_type`. This agent suggestion is a vocabulary/slot mismatch, "
            "not a quality improvement."
        ),
    },
    "condition_concept": {
        "valid":   {"MONDO", "HP"},
        "invalid": {"OMOP", "SNOMED", "LOINC"},
        "note": (
            "`condition_concept` is typed to `ConditionConceptEnum`, defined as the union of "
            "`MondoHumanDiseaseEnum` (MONDO: prefix) and `HpoPhenotypicAbnormalityEnum` (HP: prefix). "
            "OMOP concept IDs belong in the OMOP CDM `condition_concept_id` column, not in bdchm. "
            "This agent suggestion is a vocabulary/slot mismatch, not a quality improvement. "
            "Keep the existing MONDO or HP term."
        ),
    },
}


def _curie_prefix(curie: str) -> str:
    return curie.split(":")[0].upper() if ":" in curie else ""


def _vocab_slot_mismatch_note(agent_curie: str, csv_curies: set, slot: str) -> str:
    """Return an explanatory note if agent_curie is a vocabulary/slot mismatch, else ''."""
    rule = _SLOT_VOCAB_RULES.get(slot)
    if not rule:
        return ""
    ap = _curie_prefix(agent_curie)
    csv_prefixes = {_curie_prefix(c) for c in csv_curies}
    # Agent suggests an explicitly invalid vocabulary for this slot
    if ap in rule["invalid"]:
        return rule["note"]
    # Agent suggests replacing a valid vocabulary with a non-valid one
    if csv_prefixes & rule["valid"] and ap and ap not in rule["valid"]:
        return rule["note"]
    return ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_CURIE_RE = re.compile(r"\b([A-Z][A-Z0-9_]*:[A-Z0-9.]+)\b")


def _unescape_md(s: str) -> str:
    r"""Remove markdown backslash escapes (e.g. tak\_cort → tak_cort)."""
    return re.sub(r"\\(.)", r"\1", s.strip())


def _extract_curies(text: str) -> list[str]:
    return _CURIE_RE.findall(text)


# ---------------------------------------------------------------------------
# Step 1 — Load mapreview CSV
# ---------------------------------------------------------------------------

def load_mapreview(path: Path) -> dict[str, list[dict]]:
    """Return {yaml_file: [row_dicts, ...]} for non-admin substantive variables."""
    ADMIN = {"SUBJECT_ID", "phase_study", "age_visit"}
    result: dict[str, list[dict]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["Variable Name"] in ADMIN or not row["Variable Name"]:
                continue
            result.setdefault(row["YAML File"], []).append(row)
    return result


def _file_summary(yaml_file: str, mapreview: dict[str, list[dict]]) -> dict:
    """Collapse all mapreview rows for a yaml_file into a summary dict."""
    rows = mapreview.get(yaml_file, [])
    if not rows:
        return {}

    summary: dict = {
        "yaml_file":    yaml_file,
        "slots":        {},    # slot → {csv_curies, yaml_curie, yaml_match, omop, mondo, hpo, vars}
        "all_csv_curies": set(),
        "all_omop":     set(),
        "all_mondo":    set(),
        "all_hpo":      set(),
        "has_mismatch": False,
    }

    for r in rows:
        slot      = r["Slot"]
        csv_curie = r["CURIE"]
        yaml_curie = r.get("yaml_curie", "")
        yaml_match = r.get("yaml_match", "")
        omop       = r.get("omop_maps_to", "")
        mondo      = r.get("mondo_maps_to", "")
        hpo        = r.get("hpo_maps_to", "")
        var_name   = r["Variable Name"]
        var_desc   = r.get("Variable Description", "")

        summary["all_csv_curies"].add(csv_curie)
        if omop:
            summary["all_omop"].add(omop)
        if mondo:
            summary["all_mondo"].add(mondo)
        if hpo:
            summary["all_hpo"].add(hpo)
        if yaml_match == "mismatch":
            summary["has_mismatch"] = True
        s = summary["slots"].setdefault(slot, {
            "csv_curies": set(),
            "yaml_curie": yaml_curie,
            "yaml_match": yaml_match,
            "omop":  set(),
            "mondo": set(),
            "hpo":   set(),
            "vars":  [],
        })
        s["csv_curies"].add(csv_curie)
        if omop:
            s["omop"].add(omop)
        if mondo:
            s["mondo"].add(mondo)
        if hpo:
            s["hpo"].add(hpo)
        var_key = (var_name, var_desc)
        if var_key not in [(v[0], v[1]) for v in s["vars"]]:
            s["vars"].append(var_key)

    return summary


# ---------------------------------------------------------------------------
# Step 2 — Parse review MD tables
# ---------------------------------------------------------------------------

def _parse_pipe_row(line: str) -> list[str]:
    """Split a markdown pipe-table row into cells, stripping whitespace."""
    parts = line.strip().split("|")
    return [c.strip() for c in parts[1:-1]]


def parse_review_md(path: Path) -> tuple[list[dict], list[dict]]:
    """Return (confirmed_rows, anne_rows) parsed from the review MD."""
    text = path.read_text(encoding="utf-8")
    confirmed_rows: list[dict] = []
    anne_rows: list[dict] = []
    current_section = None
    conf_headers: list[str] = []
    anne_headers: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        # Match section headers regardless of # depth or name version
        if stripped.startswith("#") and any(
            k in stripped for k in ("Confirmed Findings", "Reviewer Confirmed")
        ):
            current_section = "confirmed"
            continue
        if stripped.startswith("#") and any(
            k in stripped for k in ("Anne Review Required", "Reviewer Questions")
        ):
            current_section = "anne"
            continue
        if not stripped.startswith("|"):
            continue
        if re.match(r"^\|[\s\-:]+\|", stripped):
            continue

        cells = _parse_pipe_row(line)
        if not cells:
            continue

        if current_section == "confirmed":
            if not conf_headers:
                # Normalize to lowercase so COPDGene "Final issue" and CHS "Final Issue" both work
                conf_headers = [h.lower() for h in cells]
            else:
                row_dict = dict(zip(conf_headers, cells))
                if "priority" in row_dict:
                    row_dict["priority"] = re.sub(r"\*+", "", row_dict["priority"]).strip()
                confirmed_rows.append(row_dict)
        elif current_section == "anne":
            if not anne_headers:
                anne_headers = [h.lower() for h in cells]
            else:
                row_dict = dict(zip(anne_headers, cells))
                if "priority" in row_dict:
                    row_dict["priority"] = re.sub(r"\*+", "", row_dict["priority"]).strip()
                anne_rows.append(row_dict)

    return confirmed_rows, anne_rows


# ---------------------------------------------------------------------------
# Step 3 — Generate "semantic validator review" text
# ---------------------------------------------------------------------------

def _slot_check_text(sdata: dict, slot: str) -> str:
    """One-line YAML match summary for a slot."""
    yaml_curie = sdata.get("yaml_curie", "")
    yaml_match = sdata.get("yaml_match", "")
    csv_curies = sdata.get("csv_curies", set())

    if not yaml_curie or yaml_curie == "(file not found)":
        return f"`{slot}`: no YAML value found."
    if "[" in yaml_curie and "mappings]" in yaml_curie:
        sym = "✓" if yaml_match == "match" else "⚠"
        return (f"`{slot}`: {sym} CSV CURIEs ({', '.join(sorted(csv_curies))}) "
                "verified in YAML value\\_mappings.")
    if yaml_match == "match":
        return f"`{slot}`: ✓ `{yaml_curie}` matches YAML."
    if yaml_match == "mismatch":
        return (f"`{slot}`: ⚠ CSV `{', '.join(sorted(csv_curies))}` "
                f"differs from YAML `{yaml_curie}`.")
    return f"`{slot}`: YAML check not available (multi-value observations)."


def _agent_text(sdata: dict, slot: str) -> str:
    """One-line agent suggestion for a slot (empty if no suggestion)."""
    omop  = sorted(sdata.get("omop",  set()))
    mondo = sorted(sdata.get("mondo", set()))
    hpo   = sorted(sdata.get("hpo",   set()))
    vars_ = sdata.get("vars", [])
    var_desc = vars_[0][1] if vars_ else ""
    desc_frag = f' ("{var_desc}")' if var_desc else ""

    parts: list[str] = []
    if mondo:
        parts.append(f"Mondo agent → `{', '.join(mondo)}`{desc_frag}.")
    if hpo:
        parts.append(f"HPO agent → `{', '.join(hpo)}`{desc_frag}.")
    if omop:
        parts.append(f"Measurement/procedure agent → `{', '.join(omop)}`{desc_frag}.")

    # Flag vocabulary/slot mismatches so reviewers aren't misled
    best_agent = next(iter(mondo or hpo or omop), "")
    if best_agent:
        mismatch = _vocab_slot_mismatch_note(best_agent, sdata.get("csv_curies", set()), slot)
        if mismatch:
            parts.append(f"⚠ **Vocab/slot mismatch**: {mismatch}")

    return " ".join(parts)


def _alignment_text(rec_action: str, agent_curie: str, yaml_curie: str) -> str:
    """Cross-reference agent suggestion vs Recommended action CURIEs."""
    if not rec_action:
        return ""
    rec_curies = _extract_curies(_unescape_md(rec_action))
    if not rec_curies:
        return ""
    rec_set = set(rec_curies)
    lines: list[str] = []
    if agent_curie and agent_curie in rec_set:
        lines.append(f"→ Agent `{agent_curie}` aligned with Recommended action.")
    elif agent_curie:
        lines.append(
            f"→ Agent suggests `{agent_curie}`; Recommended action cites "
            f"`{', '.join(rec_curies)}` — manual curator review advised."
        )
    if yaml_curie and "[" not in yaml_curie and yaml_curie not in rec_set:
        lines.append(
            f"→ Current YAML `{yaml_curie}` differs from Recommended `{', '.join(rec_curies)}`."
        )
    return " ".join(lines)


def generate_validator_review(
    row_files_raw: str,
    slot_hint: str,
    rec_action: str,
    mapreview: dict[str, list[dict]],
) -> str:
    """Generate the semantic validator review text for one MD table row."""
    raw_files = _unescape_md(row_files_raw)
    yaml_files = [f.strip().strip("`") for f in re.split(r"[;,]", raw_files) if f.strip().strip("`")]

    if not yaml_files:
        return "No YAML file identified for this review item."

    file_reviews: list[str] = []

    for yaml_file in yaml_files:
        # Strip any path prefix (e.g. "HCHS-ingest/") — mapreview keys are basename only
        lookup_key = Path(yaml_file).name
        summary = _file_summary(lookup_key, mapreview)

        if not summary:
            file_reviews.append(f"**{yaml_file}**: not in {MAPREVIEW_CSV.name}.")
            continue

        file_label = f"**{yaml_file}**: " if len(yaml_files) > 1 else ""

        slots_to_check = (
            {slot_hint: summary["slots"][slot_hint]}
            if slot_hint and slot_hint in summary["slots"]
            else summary["slots"]
        )

        slot_lines: list[str] = []
        for slot, sdata in slots_to_check.items():
            best_omop  = next(iter(sorted(sdata.get("omop",  set()))), "")
            best_mondo = next(iter(sorted(sdata.get("mondo", set()))), "")
            best_hpo   = next(iter(sorted(sdata.get("hpo",   set()))), "")
            best_agent = best_mondo or best_hpo or best_omop
            yaml_curie = sdata.get("yaml_curie", "")

            parts: list[str] = [_slot_check_text(sdata, slot)]
            agent_line = _agent_text(sdata, slot)
            if agent_line:
                parts.append(agent_line)
            align_line = _alignment_text(rec_action, best_agent, yaml_curie)
            if align_line:
                parts.append(align_line)

            slot_lines.append(" ".join(p for p in parts if p))

        body = " \\| ".join(slot_lines) if slot_lines else "No substantive variable data."
        file_reviews.append((file_label + body).strip())

    result = " — ".join(file_reviews) if file_reviews else "No data."

    # Append any persistent curator notes for these files
    for yaml_file in yaml_files:
        note = _CURATOR_NOTES.get(yaml_file, "")
        if note:
            result = result + " " + note

    return result


# ---------------------------------------------------------------------------
# Slot-hint inference from MD row text
# ---------------------------------------------------------------------------

def _infer_slot(issue_text: str) -> str:
    t = issue_text.lower()
    if any(k in t for k in ["condition", "mondo", " hp:", "hp concept", "disease", "emphysema",
                             "angina", "hypertension", "sleep apnea", "stroke", "tia",
                             "myocardial", "heart failure", "coronary", "blood clot", "thrombotic",
                             "copd", "diabetes", "asthma"]):
        return "condition_concept"
    if any(k in t for k in ["drug", "atc:", "corticosteroid", "antihypertensive",
                             "beta-agonist", "inhaled", "medication"]):
        return "drug_concept"
    if any(k in t for k in ["fev", "fvc", "spirometry", "predicted"]):
        return "observations"
    if any(k in t for k in ["observation_type", "alcohol", "heart rate", "oba:", "loinc"]):
        return "observation_type"
    if any(k in t for k in ["race code", "omop:8552", "other race", "demograph"]):
        return "race"
    if any(k in t for k in ["sex", "gender", "biological sex"]):
        return "sex"
    if any(k in t for k in ["wbc", "lymphocyte", "blood count", "leukocyte"]):
        return "observation_type"
    if any(k in t for k in ["blood pressure", "sbp", "dbp"]):
        return "observations"
    return ""


# ---------------------------------------------------------------------------
# Step 4 — Write output markdown
# ---------------------------------------------------------------------------

def _escape_cell(text: str) -> str:
    """Escape bare pipe chars inside a table cell (not already escaped)."""
    return re.sub(r"(?<!\\)\|", r"\\|", text)


def write_output(
    confirmed_rows: list[dict],
    anne_rows: list[dict],
    mapreview: dict[str, list[dict]],
    output_path: Path,
) -> None:
    lines: list[str] = []

    review_md_name = REVIEW_MD.name if REVIEW_MD is not None else "(no source reviewer MD)"
    lines += [
        f"# {STUDY} Semantic Review v{TODAY}",
        "",
        f"> Auto-generated {TODAY} from `{MAPREVIEW_CSV.name}` and `{review_md_name}`.",
        "> **Semantic validator review** cross-references YAML spot-check results "
        "and agent CURIE suggestions (mondo\\_agent, omop\\_agent, measurementObs\\_agent) "
        "with each row's Recommended action.",
        "",
    ]

    # ---- Reviewer Confirmed Findings ----------------------------------------
    # Display headers (proper casing); access keys are lowercase (normalized in parse_review_md)
    disp_conf_headers = [
        "Priority", "File", "Final issue", "Evidence to confirm",
        "Recommended action", "Confidence", "Reviewer", "Source alignment",
    ]
    key_conf_headers = [h.lower() for h in disp_conf_headers]
    new_col = "semantic validator review"
    all_conf_headers = disp_conf_headers + [new_col]

    lines += [
        "## Reviewer Confirmed Findings",
        "",
        "| " + " | ".join(all_conf_headers) + " |",
        "| " + " | ".join(":----" for _ in all_conf_headers) + " |",
    ]

    for row in confirmed_rows:
        file_raw   = row.get("file", "")
        rec_action = row.get("recommended action", "")
        combined   = " ".join([
            row.get("final issue", ""),
            row.get("evidence to confirm", ""),
            row.get("recommended action", ""),
        ])
        slot_hint  = _infer_slot(combined)

        val = generate_validator_review(file_raw, slot_hint, rec_action, mapreview)
        cells = [row.get(k, "") for k in key_conf_headers] + [val]
        lines.append("| " + " | ".join(_escape_cell(c) for c in cells) + " |")

    lines.append("")

    # ---- Reviewer Questions -------------------------------------------------
    disp_anne_headers = ["Priority", "File", "Question", "Evidence", "Decision needed"]
    key_anne_headers  = [h.lower() for h in disp_anne_headers]
    all_anne_headers  = disp_anne_headers + [new_col]

    lines += [
        "## Reviewer Questions",
        "",
        "| " + " | ".join(all_anne_headers) + " |",
        "| " + " | ".join(":----" for _ in all_anne_headers) + " |",
    ]

    for row in anne_rows:
        file_raw  = row.get("file", "")
        combined  = " ".join([row.get("question", ""), row.get("evidence", "")])
        slot_hint = _infer_slot(combined)

        val = generate_validator_review(file_raw, slot_hint, "", mapreview)
        cells = [row.get(k, "") for k in key_anne_headers] + [val]
        lines.append("| " + " | ".join(_escape_cell(c) for c in cells) + " |")

    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Written: {output_path}")


# ---------------------------------------------------------------------------
# Summary report
# ---------------------------------------------------------------------------

_ADMIN_VARS = {"SUBJECT_ID", "phase_study", "age_visit"}

# Slots that are expected to have no agent suggestion
_NO_SUGGESTION_SLOTS = {"value_enum", "species"}


def _build_summary_stats(mapreview_path: Path) -> dict:
    """Read raw mapreview CSV and compute all QC statistics."""
    from collections import defaultdict

    ADMIN = _ADMIN_VARS
    total_rows = 0
    admin_rows = 0
    yaml_matches = 0
    yaml_mismatches: list[dict] = []
    yaml_not_checked = 0

    # entity-type coverage
    et_counts: dict[str, dict] = defaultdict(lambda: {
        "total": 0, "mondo": 0, "hpo": 0, "omop": 0, "none": 0
    })

    # no-suggestion substantive rows (not in expected-empty slots)
    missing_suggestion: list[dict] = []

    # CURIE alignment: agent differs from CSV CURIE
    misaligned: list[dict] = []

    seen_cache_keys: set[tuple] = set()
    unique_curies: set[str] = set()

    with open(mapreview_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            total_rows += 1
            vn = row["Variable Name"]
            if vn in ADMIN or not vn:
                admin_rows += 1
                continue

            curie = row.get("CURIE", "").strip()
            if curie:
                unique_curies.add(curie)

            slot = row["Slot"]
            ym = row.get("yaml_match", "")
            if ym == "match":
                yaml_matches += 1
            elif ym == "mismatch":
                yaml_mismatches.append({
                    "var": vn, "yaml_file": row["YAML File"],
                    "csv_curie": row["CURIE"], "yaml_curie": row.get("yaml_curie", ""),
                })
            else:
                yaml_not_checked += 1

            et = row.get("maps_to_entity_type", "")
            if not et:
                continue

            # De-duplicate agent stats by cache key (var+slot+entity)
            ck = (vn, slot, row.get("Entity Type", ""))
            if ck in seen_cache_keys:
                continue
            seen_cache_keys.add(ck)

            et_counts[et]["total"] += 1
            has_mondo = bool(row.get("mondo_maps_to", ""))
            has_hpo   = bool(row.get("hpo_maps_to", ""))
            has_omop  = bool(row.get("omop_maps_to", ""))
            if has_mondo: et_counts[et]["mondo"] += 1
            if has_hpo:   et_counts[et]["hpo"]   += 1
            if has_omop:  et_counts[et]["omop"]  += 1
            if not (has_mondo or has_hpo or has_omop):
                et_counts[et]["none"] += 1
                if slot not in _NO_SUGGESTION_SLOTS and et not in (
                    "Demography", "ValueEnum", "Person"
                ):
                    missing_suggestion.append({
                        "var": vn, "slot": slot, "et": et,
                        "desc": row.get("Variable Description", "")[:60],
                    })

            # Alignment check: agent suggests something different from the CSV CURIE
            csv_curie = row.get("CURIE", "")
            agent_curie = (
                row.get("mondo_maps_to", "")
                or row.get("hpo_maps_to", "")
                or row.get("omop_maps_to", "")
            )
            if csv_curie and agent_curie and agent_curie != csv_curie:
                misaligned.append({
                    "var": vn, "slot": slot, "et": et,
                    "csv": csv_curie, "agent": agent_curie,
                    "yaml_match": ym,
                })

    substantive = total_rows - admin_rows
    return {
        "total_rows": total_rows,
        "admin_rows": admin_rows,
        "substantive_rows": substantive,
        "unique_curies": len(unique_curies),
        "yaml_matches": yaml_matches,
        "yaml_mismatches": yaml_mismatches,
        "yaml_not_checked": yaml_not_checked,
        "et_counts": dict(et_counts),
        "missing_suggestion": missing_suggestion,
        "misaligned": misaligned,
    }


def write_summary(
    mapreview_path: Path,
    confirmed_rows: list[dict],
    anne_rows: list[dict],
    output_dir: Path,
    suppressed_counts: dict[str, int] | None = None,
) -> Path:
    """Write {STUDY}_semantic_validator_summary_v{YYYYMMDD}.md and return its path."""
    stats = _build_summary_stats(mapreview_path)
    date_tag = date.today().strftime("%Y_%m%d")
    date_label = date.today().strftime("%Y-%m-%d")
    out_path = output_dir / f"{STUDY}_semantic_validator_summary_v{date_tag}.md"

    lines: list[str] = []

    lines += [
        f"# {STUDY} Semantic Validator Summary v{date_label}",
        "",
        f"**Generated:** {TODAY}",
        f"**Mapreview CSV:** `{mapreview_path.name}`",
        f"**Review MD:** `{REVIEW_MD.name if REVIEW_MD is not None else '(none — generated from mapreview CSV only)'}`",
        "",
        "---",
        "",
    ]

    # ── Overview ──────────────────────────────────────────────────────────────
    substantive = stats["substantive_rows"]
    n_yaml_files = sum(
        1 for _ in set(
            row["YAML File"]
            for row in _iter_substantive(mapreview_path)
            if row["YAML File"]
        )
    )
    lines += [
        "## Overview",
        "",
        "| Metric | Count |",
        "| :---- | ----: |",
        f"| Total rows in mapreview CSV | {stats['total_rows']} |",
        f"| Admin variables skipped | {stats['admin_rows']} |",
        f"| Substantive variables reviewed | {substantive} |",
        f"| Unique CURIEs validated | {stats['unique_curies']} |",
        f"| Unique YAML files referenced | {n_yaml_files} |",
        f"| Final Confirmed Findings rows | {len(confirmed_rows)} |",
        f"| Anne Review Required rows | {len(anne_rows)} |",
        "",
    ]

    # ── YAML Spot-Check ───────────────────────────────────────────────────────
    n_mm = len(stats["yaml_mismatches"])
    lines += [
        "## YAML Spot-Check",
        "",
        "| Result | Count |",
        "| :---- | ----: |",
        f"| Matches (✓) | {stats['yaml_matches']} |",
        f"| Mismatches (⚠) | {n_mm} |",
        f"| Not checked (admin / no YAML) | {stats['yaml_not_checked']} |",
        "",
    ]
    if n_mm == 0:
        lines.append("No YAML mismatches found — all spot-checked CURIEs match their YAML files.")
    else:
        lines.append(f"**{n_mm} mismatch(es) require correction:**")
        lines.append("")
        lines.append("| Variable | YAML File | CSV CURIE | YAML CURIE |")
        lines.append("| :---- | :---- | :---- | :---- |")
        for m in stats["yaml_mismatches"]:
            lines.append(
                f"| {m['var']} | {m['yaml_file']} | `{m['csv_curie']}` | `{m['yaml_curie']}` |"
            )
    lines.append("")

    # ── Agent Coverage ────────────────────────────────────────────────────────
    lines += [
        "## Agent Coverage by Entity Type",
        "",
        "| Entity Type | Unique vars | MONDO | HPO | OMOP/LOINC | No suggestion |",
        "| :---- | ----: | ----: | ----: | ----: | ----: |",
    ]
    total_vars = total_w = total_none = 0
    for et, c in sorted(stats["et_counts"].items()):
        lines.append(
            f"| {et} | {c['total']} | {c['mondo']} | {c['hpo']} "
            f"| {c['omop']} | {c['none']} |"
        )
        total_vars += c["total"]
        total_w    += c["total"] - c["none"]
        total_none += c["none"]
    lines += [
        f"| **Total** | **{total_vars}** | | | | **{total_none}** |",
        "",
        f"**Coverage: {total_w}/{total_vars} unique variable-slot pairs have at least one agent suggestion "
        f"({100*total_w//total_vars if total_vars else 0}%).**",
        "",
    ]

    # ── Agent Misalignment (agent ≠ CSV CURIE) ────────────────────────────────
    misaligned = stats["misaligned"]
    # Only flag misalignments where YAML matches CSV (so the CSV CURIE is confirmed)
    # and the agent suggests something different — these are potential improvements
    confirmed_misaligned = [m for m in misaligned if m["yaml_match"] == "match"]
    improvement_misaligned = [m for m in misaligned if m["yaml_match"] != "match"]

    lines += [
        "## Agent vs CSV CURIE Alignment",
        "",
        f"Agent suggestions differ from the current CSV CURIE in "
        f"**{len(misaligned)}** variable-slot pair(s).",
        "",
    ]
    if confirmed_misaligned:
        lines += [
            f"### Potential Improvements ({len(confirmed_misaligned)} — YAML confirms CSV, agent suggests different)",
            "",
            "These cases have a YAML-confirmed CSV CURIE but the agent suggests a different concept.",
            "Review whether the agent suggestion is more specific or accurate.",
            "",
            "| Variable | Slot | Entity Type | CSV / YAML CURIE | Agent Suggestion |",
            "| :---- | :---- | :---- | :---- | :---- |",
        ]
        for m in sorted(confirmed_misaligned, key=lambda x: (x["et"], x["var"])):
            lines.append(
                f"| {m['var']} | {m['slot']} | {m['et']} "
                f"| `{m['csv']}` | `{m['agent']}` |"
            )
        lines.append("")

    if improvement_misaligned:
        lines += [
            f"### Unverified Misalignments ({len(improvement_misaligned)} — no YAML confirmation)",
            "",
            "| Variable | Slot | Entity Type | CSV CURIE | Agent Suggestion |",
            "| :---- | :---- | :---- | :---- | :---- |",
        ]
        for m in sorted(improvement_misaligned, key=lambda x: (x["et"], x["var"])):
            lines.append(
                f"| {m['var']} | {m['slot']} | {m['et']} "
                f"| `{m['csv']}` | `{m['agent']}` |"
            )
        lines.append("")

    # ── Vocab/Slot Validation ─────────────────────────────────────────────────
    sup = suppressed_counts or {}
    total_sup = sum(sup.values())
    lines += [
        "## Vocab/Slot Validation",
        "",
        "Agent suggestions suppressed as vocabulary/slot mismatches "
        f"(evaluated but not surfaced as findings): **{total_sup}**",
        "",
    ]
    if sup:
        lines += [
            "| Slot | Invalid vocab proposed | Suppressed count | Rule |",
            "| :---- | :---- | ----: | :---- |",
        ]
        for slot, count in sorted(sup.items()):
            rule = _SLOT_VOCAB_RULES.get(slot, {})
            valid   = ", ".join(sorted(rule.get("valid",   set())))
            invalid = ", ".join(sorted(rule.get("invalid", set())))
            lines.append(f"| `{slot}` | {invalid} | {count} | Valid: {valid} |")
        lines += [
            f"| **Total** | | **{total_sup}** | |",
            "",
            "_These are not errors — they confirm the existing CURIEs are correct "
            "for their slots. The agent proposed codes from a vocabulary the bdchm "
            "slot is not typed for (e.g. OMOP in a MONDO-typed slot, LOINC in an "
            "OBA-typed slot). See `_SLOT_VOCAB_RULES` in `generate_semantic_review.py` "
            "for the full rule definitions._",
        ]
    else:
        lines.append(
            "_No vocab/slot mismatches detected — all agent suggestions were "
            "for the correct vocabulary._"
        )
    lines.append("")

    # ── Error Cases Requiring Fix ─────────────────────────────────────────────
    missing = stats["missing_suggestion"]
    lines += [
        "## Error Cases Requiring Fix",
        "",
    ]

    if n_mm > 0:
        lines += [
            f"### YAML Mismatches — {n_mm} must be corrected",
            "See the YAML Spot-Check section above.",
            "",
        ]

    if missing:
        lines += [
            f"### Missing Agent Suggestions — {len(missing)} variable-slot pair(s)",
            "",
            "These substantive variables received no suggestion from any agent.",
            "Investigate whether a suitable ontology term exists or the slot routing needs updating.",
            "",
            "| Variable | Slot | Entity Type | Description |",
            "| :---- | :---- | :---- | :---- |",
        ]
        for m in missing:
            lines.append(
                f"| {m['var']} | {m['slot']} | {m['et']} | {m['desc']} |"
            )
        lines.append("")
    else:
        lines.append(
            "No unexpected missing suggestions — all substantive variable-slot pairs "
            "either have an agent suggestion or are in a slot type with no agent routing "
            "(ValueEnum, Demography, DrugExposure without RxNorm match)."
        )
        lines.append("")

    if n_mm == 0 and not missing:
        lines += ["**No error cases requiring immediate fix.**", ""]

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def _iter_substantive(mapreview_path: Path):
    """Yield non-admin rows from the mapreview CSV."""
    with open(mapreview_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["Variable Name"] not in _ADMIN_VARS and row["Variable Name"]:
                yield row


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _auto_generate_rows(
    mapreview: dict[str, list[dict]]
) -> tuple[list[dict], list[dict], dict[str, int]]:
    """Build confirmed_rows from mapreview data when no source reviewer MD exists.

    Two finding types (both go into Reviewer Confirmed Findings):
      High     — Agent suggests a better CURIE than what is in the curie CSV.
      Medium   — YAML mismatch: CSV CURIE differs from what is in the YAML file.

    Returns (confirmed, anne_rows, suppressed_counts) where suppressed_counts is
    {slot: n} counting agent suggestions silently dropped due to vocab/slot rules.
    Reviewer Questions is always empty — only a human reviewer can populate it.
    """
    confirmed: list[dict] = []
    suppressed: dict[str, int] = {}

    for yaml_file in sorted(mapreview):
        summary = _file_summary(yaml_file, mapreview)
        if not summary:
            continue

        for slot, sdata in summary["slots"].items():
            yaml_match  = sdata.get("yaml_match", "")
            csv_curies  = sorted(sdata.get("csv_curies", set()))
            yaml_curie  = sdata.get("yaml_curie", "")
            mondo       = sorted(sdata.get("mondo", set()))
            hpo         = sorted(sdata.get("hpo",   set()))
            omop        = sorted(sdata.get("omop",  set()))
            agent_curie = next(iter(mondo or hpo or omop), "")
            vars_       = sdata.get("vars", [])
            var_desc    = vars_[0][1] if vars_ else ""

            if agent_curie and csv_curies and agent_curie not in csv_curies:
                vocab_note = _vocab_slot_mismatch_note(agent_curie, set(csv_curies), slot)
                if not vocab_note:
                    csv_str   = ", ".join(f"`{c}`" for c in csv_curies)
                    desc_frag = f' ("{var_desc[:80]}")' if var_desc else ""
                    source    = ("MONDO" if mondo else "HPO" if hpo else "OMOP/LOINC")
                    confirmed.append({
                        "priority":            "High",
                        "file":               yaml_file,
                        "final issue":        (
                            f"Agent suggests better CURIE for `{slot}`{desc_frag}: "
                            f"{source} recommends `{agent_curie}` but CSV has {csv_str}"
                        ),
                        "evidence to confirm": (
                            f"Variable description: {var_desc[:120] if var_desc else '(none)'}. "
                            f"{source} agent returned `{agent_curie}` as best match."
                        ),
                        "recommended action":  (
                            f"Review whether `{agent_curie}` is more accurate than {csv_str} "
                            f"for `{slot}`. If yes, update the curie CSV and re-run."
                        ),
                        "confidence":  "High",
                        "reviewer":    "Auto-generated",
                        "source alignment": "",
                    })
                else:
                    suppressed[slot] = suppressed.get(slot, 0) + 1

            if yaml_match == "mismatch":
                csv_str = ", ".join(f"`{c}`" for c in csv_curies)
                confirmed.append({
                    "priority":            "Medium",
                    "file":               yaml_file,
                    "final issue":        (
                        f"YAML mismatch on `{slot}`: "
                        f"CSV has {csv_str} but YAML contains `{yaml_curie}`"
                    ),
                    "evidence to confirm": (
                        f"CSV CURIE(s): {csv_str}; "
                        f"YAML `{slot}` value: `{yaml_curie}`"
                    ),
                    "recommended action":  (
                        f"Verify correct value and update YAML to match. "
                        + (f"Agent suggests `{agent_curie}`." if agent_curie else "No agent suggestion available.")
                    ),
                    "confidence":  "Medium",
                    "reviewer":    "Auto-generated",
                    "source alignment": "",
                })

    return confirmed, [], suppressed


def main() -> None:
    print("Loading mapreview CSV ...")
    mapreview = load_mapreview(MAPREVIEW_CSV)
    print(f"  {sum(len(v) for v in mapreview.values())} rows across {len(mapreview)} YAML files.")

    if REVIEW_MD is not None:
        print("Parsing review MD ...")
        confirmed_rows, anne_rows = parse_review_md(REVIEW_MD)
        print(f"  {len(confirmed_rows)} reviewer Confirmed Findings, {len(anne_rows)} Reviewer Questions rows.")
        # Merge auto-generated findings for YAML files not already covered by the reviewer
        auto_confirmed, _, suppressed_counts = _auto_generate_rows(mapreview)
        reviewed_files = {
            Path(_unescape_md(r.get("file", ""))).name
            for r in confirmed_rows + anne_rows
        }
        added = [r for r in auto_confirmed if Path(r["file"]).name not in reviewed_files]
        if added:
            confirmed_rows = confirmed_rows + added
            print(f"  + {len(added)} auto-generated findings for files not in reviewer MD.")
    else:
        print("No source reviewer MD — generating rows from mapreview data ...")
        confirmed_rows, anne_rows, suppressed_counts = _auto_generate_rows(mapreview)
        print(f"  Auto-generated: {len(confirmed_rows)} Confirmed Findings, {len(anne_rows)} Reviewer Questions rows.")

    if suppressed_counts:
        total_sup = sum(suppressed_counts.values())
        print(f"  Vocab/slot mismatch suppressed: {total_sup} ({dict(suppressed_counts)})")

    print("Generating semantic review ...")
    write_output(confirmed_rows, anne_rows, mapreview, OUTPUT_MD)

    print("Generating summary ...")
    summary_path = write_summary(
        MAPREVIEW_CSV,
        confirmed_rows,
        anne_rows,
        OUTPUT_MD.parent,
        suppressed_counts=suppressed_counts,
    )
    print(f"Written: {summary_path}")
    print("Done.")

    from pipeline_status import write_status
    write_status()


if __name__ == "__main__":
    import argparse
    import sys
    parser = argparse.ArgumentParser(description="Generate semantic review MD for a BDC study.")
    parser.add_argument(
        "--study",
        default="COPDGene",
        choices=list(_STUDY_CONFIGS),
        metavar="STUDY",
        help=f"Study to process. Known: {list(_STUDY_CONFIGS)}. Default: COPDGene.",
    )
    args = parser.parse_args()
    _resolve_paths(args.study)
    main()
