#!/usr/bin/env python3
"""Refresh mapreview.csv for only the rows a specific fix touched.

Unlike generate_curie_mapreview.py's full run (which calls every agent for
every unique row in the study), this script re-runs the *exact same* agent
logic — imported directly from generate_curie_mapreview.py, never
reimplemented — for only the (YAML File, PHV) pairs named in an explicit
manifest. Every other row in mapreview.csv is left byte-for-byte untouched.

This exists because a full Step 1 re-run for a large study can take hours
(live API calls against a flaky endpoint) even when a fix only touched a
handful of rows. It intentionally does NOT auto-detect "what changed" by
diffing curie.csv against the last mapreview.csv snapshot — the manifest
must be supplied explicitly, so nothing gets refreshed (and no stale
agent-suggestion column gets silently overwritten) for a row nobody asked
about.

Manifest format (JSON):
  [
    {"yaml_file": "hyperten.yaml", "phvs": ["phv00206806", "phv00296245"]},
    {"yaml_file": "tak_vasodil.yaml", "phvs": ["phv00207048"]}
  ]

Usage:
  python sync_affected_rows.py --study ARIC --manifest aric_fix18_19.json
"""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import generate_curie_mapreview as gcm  # noqa: E402


def load_manifest(path: Path) -> dict[str, set[str]]:
    """Return {yaml_file: {phv, ...}} from the manifest JSON."""
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, set[str]] = {}
    for entry in data:
        out.setdefault(entry["yaml_file"], set()).update(entry["phvs"])
    return out


def main(study: str, manifest_path: Path) -> None:
    gcm._resolve_paths(study)
    targets = load_manifest(manifest_path)
    n_target_files = len(targets)
    n_target_phvs = sum(len(v) for v in targets.values())
    print(f"Study: {study}  |  target files: {n_target_files}  |  target PHVs: {n_target_phvs}")

    if not gcm.INPUT_CSV.exists():
        print(f"ERROR: {gcm.INPUT_CSV} not found.", file=sys.stderr)
        sys.exit(1)
    if not gcm.OUTPUT_CSV.exists():
        print(
            f"ERROR: {gcm.OUTPUT_CSV} not found — this tool refreshes an "
            "existing mapreview.csv, it doesn't create one from scratch. "
            "Run the full generate_curie_mapreview.py once first.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Loading agents ...")
    (get_mondo_id, get_hpo_id, get_omop_concept_id, get_rxnorm_id, get_loinc_id,
     extract_clinical_term, get_omop_route_id, get_oba_id, get_normalizer_confidence,
     get_oba_id_with_score, get_loinc_id_with_score, get_drug_curie_override,
     get_mondo_id_with_score, get_hpo_id_with_score, get_omop_concept_id_with_score,
     ) = gcm._import_agents()
    print("Agents loaded.")

    dbgap_map = gcm._load_dbgap_map()
    loinc_omop_map = gcm._load_loinc_omop_map()

    # Pull current Variable Name/Slot/Entity Type/Variable Description/CURIE
    # for every curie.csv row that matches a targeted (yaml_file, phv) pair.
    with open(gcm.INPUT_CSV, newline="", encoding="utf-8-sig") as f:
        curie_rows = list(csv.DictReader(f))

    def _is_target(row: dict) -> bool:
        yf = row.get("YAML File", "").strip()
        phv = row.get("PHV", "").strip()
        return yf in targets and phv in targets[yf]

    matched_curie_rows = [r for r in curie_rows if _is_target(r)]
    if not matched_curie_rows:
        print("WARNING: no curie.csv rows matched the manifest — nothing to refresh.", file=sys.stderr)
        sys.exit(1)
    print(f"Matched {len(matched_curie_rows)} curie.csv row(s) to refresh.")

    def _is_measurement_target(slot: str, entity_type: str) -> bool:
        return slot == "observation_type" and entity_type == "MeasurementObservation"

    # Compute fresh values for each unique (var_name, slot, entity_type, phv) key.
    fresh: dict[tuple, dict] = {}
    for row in matched_curie_rows:
        vn = row.get("Variable Name", "").strip()
        sl = row.get("Slot", "").strip()
        et = row.get("Entity Type", "").strip()
        vd = row.get("Variable Description", "").strip()
        cc = row.get("CURIE", "").strip()
        phv = row.get("PHV", "").strip()
        yaml_file = row.get("YAML File", "").strip()
        free_text = row.get("Free Text Value", "").strip() if sl == "drug_concept" else ""
        # YAML File must be part of the key: a PHV can be a genuine primary
        # variable in one file and a shared "companion" reference (e.g. an
        # age variable pulled in via an age_at_observation expr) in many
        # others, all sharing the same Variable Name/Slot/Entity Type. Without
        # yaml_file here, refreshing one file's row would also silently
        # overwrite every other file's row for that same companion PHV in the
        # merge step below (this bled OMOP:37311566/MONDO:0005098 from the
        # vege_serving.yaml/stroke.yaml fixes into unrelated files' rows in
        # CHS/JHS/WHI/FHS mapreview.csv, found and fixed 2026-08-28).
        key = (vn, sl, et, phv, yaml_file, free_text) if free_text else (vn, sl, et, phv, yaml_file)
        if key in fresh:
            continue

        query_desc = vd
        source_verified = source_name_verified = source_desc_verified = source_pht_verified = ""
        if _is_measurement_target(sl, et):
            dbgap_row = dbgap_map.get(phv)
            if dbgap_row:
                source_verified = True
                source_name_verified = dbgap_row["name"]
                source_desc_verified = dbgap_row["description"]
                source_pht_verified = dbgap_row["pht"]
                query_desc = source_desc_verified or vd

        (omop_val, mondo_val, hpo_val, oba_val, entity_val, confidence_val, loinc_confidence_val,
         oba_score_val, loinc_score_val, mondo_score_val, hpo_score_val, omop_score_val) = gcm._agent_suggestion(
            sl, et, vn, query_desc,
            get_mondo_id, get_hpo_id, get_omop_concept_id,
            get_rxnorm_id, get_loinc_id, extract_clinical_term, get_omop_route_id, get_oba_id,
            get_normalizer_confidence, cc, get_oba_id_with_score, get_loinc_id_with_score, get_drug_curie_override,
            get_mondo_id_with_score, get_hpo_id_with_score, get_omop_concept_id_with_score,
            free_text,
        )

        loinc_val = ""
        loinc_omop_concept_id = ""
        loinc_omop_resolution_status = ""
        if omop_val.startswith("LOINC:"):
            loinc_val = omop_val
            loinc_omop_concept_id, loinc_omop_resolution_status = gcm._resolve_loinc_to_omop(omop_val, loinc_omop_map)
            loinc_omop_concept_id = loinc_omop_concept_id or ""
            omop_val = loinc_omop_concept_id

        priority_curie_val, priority_curie_score_val = gcm._pick_priority_curie(
            mondo_val, hpo_val, oba_val, omop_val,
            mondo_score_val or 0.0, hpo_score_val or 0.0, oba_score_val or 0.0,
            omop_score_val or 0.0, loinc_score_val or 0.0,
        )

        yaml_curie_val, yaml_match_val = gcm._yaml_check(yaml_file, sl, cc, phv=phv)

        fresh[key] = dict(
            CURIE=cc,
            yaml_curie=yaml_curie_val,
            yaml_match=yaml_match_val,
            omop_maps_to=omop_val,
            mondo_maps_to=mondo_val,
            hpo_maps_to=hpo_val,
            oba_maps_to=oba_val,
            loinc_maps_to=loinc_val,
            priority_curie=priority_curie_val,
            priority_curie_score=priority_curie_score_val,
            mondo_score=mondo_score_val,
            hpo_score=hpo_score_val,
            oba_score=oba_score_val,
            omop_score=omop_score_val,
            loinc_score=loinc_score_val,
            maps_to_entity_type=entity_val,
            suggestion_confidence=confidence_val,
            loinc_confidence=loinc_confidence_val,
            loinc_omop_concept_id=loinc_omop_concept_id,
            loinc_omop_resolution_status=loinc_omop_resolution_status,
            source_verified=source_verified,
            source_variable_name_verified=source_name_verified,
            source_variable_description_verified=source_desc_verified,
            source_pht_verified=source_pht_verified,
        )
        print(f"  refreshed: {yaml_file} / {phv} / {sl}")

    # Merge into the EXISTING mapreview.csv — only rows whose (Variable Name,
    # Slot, Entity Type, PHV, YAML File) key is in `fresh` get their columns
    # overwritten; every other row is copied through unchanged. YAML File is
    # part of the key (see comment above `fresh[key]` construction) so a
    # shared companion PHV's row in an unrelated file is never touched.
    with open(gcm.OUTPUT_CSV, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        all_rows = list(reader)

    n_updated = 0
    for row in all_rows:
        sl = row.get("Slot", "").strip()
        free_text = row.get("Free Text Value", "").strip() if sl == "drug_concept" else ""
        base_key = (
            row.get("Variable Name", "").strip(),
            sl,
            row.get("Entity Type", "").strip(),
            row.get("PHV", "").strip(),
            row.get("YAML File", "").strip(),
        )
        key = base_key + (free_text,) if free_text else base_key
        if key in fresh:
            row.update(fresh[key])
            n_updated += 1

    tmp_path = gcm.OUTPUT_CSV.with_name(gcm.OUTPUT_CSV.stem + ".tmp" + gcm.OUTPUT_CSV.suffix)
    with open(tmp_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)
    import os
    os.replace(tmp_path, gcm.OUTPUT_CSV)

    print(f"Done. {n_updated} row(s) in {gcm.OUTPUT_CSV.name} updated in place; all other rows untouched.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--study", required=True, help="Study short name, e.g. FHS")
    parser.add_argument("--manifest", required=True, type=Path, help="Path to a JSON manifest of {yaml_file, phvs}")
    args = parser.parse_args()
    main(args.study, args.manifest)
