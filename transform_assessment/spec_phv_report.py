#!/usr/bin/env python3
"""Spec-sourced Table S4: per-variable/cohort PHV counts and source N.

Replaces the spreadsheet-driven ``preharmonized_qaqc_report.py``. The
authoritative PHV->harmonized-variable mapping is the LinkML transform
specs in ``priority_variables_transform/<cohort>-ingest/<variable>.yaml``,
which have not drifted the way the Google Sheets have (e.g. SomaScan
aptamers mis-mapped to clinical concepts survive only in the sheets and in
``_archive/`` specs, not the live specs).

Two inputs, both spec/enclave-derived — no sheets:

1. **PHV list / count / harmonized variable** come from the specs. For each
   ``<variable>.yaml`` the value-source PHVs are the ``populated_from`` (and
   ``{phv}`` refs in ``expr``) found *under the value slot subtree*
   (``value_quantity`` / ``value_decimal`` / ``value_integer`` /
   ``value_concept`` / ``value_enum``). PHVs that only appear in
   ``associated_participant`` / ``associated_visit`` / ``age_at_observation``
   are NOT value sources and are excluded from the count.

2. **N** comes from a source-extraction JSON produced by
   ``extract_source_summaries.py`` on SB, joined PHV -> column -> n_valid via
   the dbGaP cache's PHV name map. Run the source extract first (the
   ``run_extracts.sh``/``--yaml-dir`` path); this script consumes its JSON.

The bdc_label for each spec file is resolved from ``harmonized_vars.tsv``
(short ``var_name`` == spec filename stem).

Usage::

    uv run python spec_phv_report.py \\
        --specs-root ../priority_variables_transform \\
        --source-json /path/to/<cohort>_source_*.json \\
        --cache-dir ../hv_dataqc/local_output/dbgap-cache/<cohort> \\
        --cohort FHS

Multiple ``--source-json``/``--cache-dir``/``--cohort`` triples may be
passed (repeat the flags) to build the full multi-cohort table in one run.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from hv_dataqc.hv_dataqc_common import load_phv_name_map

_PHV_RE = re.compile(r"phv\d+", re.IGNORECASE)

# Value slots whose source PHV(s) count as the harmonized variable's source
# variables.  PHVs appearing only outside these slots (participant id, visit,
# age) are provenance, not source measurements, and must not inflate the count.
_VALUE_SLOTS = ("value_decimal", "value_integer", "value_coded", "value_concept", "value_enum")

# Ingest directory name -> cohort label, mirroring run_extracts/run_s5.
_INGEST_DIR_RE = re.compile(r"^(?P<cohort>.+)-ingest$")


def _phvs_in_subtree(node: Any) -> set[str]:
    """All distinct PHV accessions referenced anywhere under *node*.

    Catches both ``populated_from: phvNNNN`` and ``{phvNNNN}`` refs inside
    ``expr`` strings, recursively, by stringifying the subtree.  Lowercased.
    """
    return {m.group(0).lower() for m in _PHV_RE.finditer(json.dumps(node, default=str))}


def _value_source_phvs(body: Any) -> dict[str, str | None]:
    """Map value-source PHV -> its PHT for one MeasurementObservation block.

    Collects PHVs only from the value slots (and the value_quantity
    object_derivation that wraps them).  The PHT is the ``populated_from`` on
    the nested Quantity (or the outer block for flat slots) — needed to
    disambiguate columns whose name recurs across PHTs (e.g. "AST").
    """
    phv_pht: dict[str, str | None] = {}
    sd = (body or {}).get("slot_derivations", {})
    if not isinstance(sd, dict):
        return phv_pht
    outer_pht = (body or {}).get("populated_from")

    # value_quantity wraps a nested Quantity object_derivation carrying its
    # own populated_from (the PHT the value column lives in).
    vq = sd.get("value_quantity")
    if isinstance(vq, dict):
        for od in vq.get("object_derivations", []):
            for cd in (od.get("class_derivations", {}) or {}).values():
                q_pht = (cd or {}).get("populated_from") or outer_pht
                inner = (cd or {}).get("slot_derivations", {}) or {}
                for slot in _VALUE_SLOTS:
                    if slot in inner:
                        for phv in _phvs_in_subtree(inner[slot]):
                            phv_pht.setdefault(phv, q_pht)

    # flat (non-nested) value slots directly on the MO
    for slot in _VALUE_SLOTS:
        if slot in sd:
            for phv in _phvs_in_subtree(sd[slot]):
                phv_pht.setdefault(phv, outer_pht)

    return phv_pht


def parse_spec_file(path: Path) -> dict[str, Any]:
    """Return {variable, value_phvs (set), observation_type} for one spec file.

    A spec file is a list of class_derivation blocks all describing the same
    harmonized variable across PHTs; we union their value-source PHVs.
    """
    blocks = yaml.safe_load(path.read_text()) or []
    if isinstance(blocks, dict):
        blocks = [blocks]

    phv_pht: dict[str, str | None] = {}
    observation_type: str | None = None
    for block in blocks:
        for cls, body in (block.get("class_derivations", {}) or {}).items():
            for phv, pht in _value_source_phvs(body).items():
                # First PHT wins; a PHV should map to one value column/PHT.
                phv_pht.setdefault(phv, pht)
            sd = (body or {}).get("slot_derivations", {}) or {}
            ot = sd.get("observation_type")
            if isinstance(ot, dict) and ot.get("value") and observation_type is None:
                observation_type = str(ot["value"])

    return {
        "variable": path.stem,                 # short var_name, e.g. "ast_sgot"
        "phv_pht": phv_pht,                     # value-source phv -> pht
        "observation_type": observation_type,
    }


def load_var_labels(harmonized_vars_tsv: Path) -> dict[str, str]:
    """Map spec short name (var_name) -> publication label (var_label)."""
    labels: dict[str, str] = {}
    with harmonized_vars_tsv.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            name = (row.get("var_name") or "").strip()
            label = (row.get("var_label") or "").strip()
            if name:
                labels[name] = label or name
    return labels


def _col_n_valid(
    source_doc: dict, phv: str, pht: str | None, phv_name_map: dict[str, str]
) -> int | None:
    """Resolve a PHV's n_valid from a source-extract JSON.

    PHV -> column name (via dbGaP cache map) -> n_valid in
    ``variables_by_pht[pht][column]``.  The PHT comes from the spec, which
    disambiguates column names that recur across PHTs (e.g. "AST" appears in
    several FHS PHTs).  JSON keys are lowercased column names; the cache map
    yields original case.  Falls back to scanning all PHTs only when the spec
    gave no PHT (should not happen for value slots).
    """
    col = (phv_name_map.get(phv) or phv).lower()
    vp = source_doc.get("variables_by_pht", {})

    if pht and pht in vp:
        stat = vp[pht].get(col)
        if isinstance(stat, dict) and stat.get("n_valid") is not None:
            return int(stat["n_valid"])
        return None

    # No PHT scope — sum unique matches as a last resort.
    total, found = 0, False
    for pht_cols in vp.values():
        stat = pht_cols.get(col)
        if isinstance(stat, dict) and stat.get("n_valid") is not None:
            total += int(stat["n_valid"])
            found = True
    return total if found else None


def build_cohort_rows(
    specs_dir: Path,
    source_json: Path,
    cache_dir: Path,
    var_labels: dict[str, str],
) -> dict[str, dict[str, Any]]:
    """Per-variable {phv_count, total_n, phvs, label} for one cohort's specs."""
    source_doc = json.loads(source_json.read_text())
    phv_name_map = load_phv_name_map(cache_dir)

    rows: dict[str, dict[str, Any]] = {}
    for spec_path in sorted(specs_dir.glob("*.yaml")):
        parsed = parse_spec_file(spec_path)
        phv_pht: dict[str, str | None] = parsed["phv_pht"]
        if not phv_pht:
            continue
        phvs = sorted(phv_pht)
        total_n = 0
        n_seen = False
        for phv in phvs:
            n = _col_n_valid(source_doc, phv, phv_pht[phv], phv_name_map)
            if n is not None:
                total_n += n
                n_seen = True
        rows[parsed["variable"]] = {
            "label": var_labels.get(parsed["variable"], parsed["variable"]),
            "phv_count": len(phvs),
            "phvs": phvs,
            "phv_pht": phv_pht,
            "total_n": total_n if n_seen else None,
            "observation_type": parsed["observation_type"],
        }
    return rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--specs-root", required=True, type=Path,
                   help="priority_variables_transform/ root containing <cohort>-ingest dirs.")
    p.add_argument("--harmonized-vars", type=Path,
                   default=Path(__file__).resolve().parents[1]
                   / "hv_dataqc/extract_harmonized/config/harmonized_vars.tsv",
                   help="harmonized_vars.tsv for var_name -> var_label labels.")
    p.add_argument("--cohort", action="append", required=True,
                   help="Cohort label; repeat per cohort (matches <cohort>-ingest dir).")
    p.add_argument("--source-json", action="append", required=True, type=Path,
                   help="Source-extract JSON for the matching --cohort; repeat in order.")
    p.add_argument("--cache-dir", action="append", required=True, type=Path,
                   help="dbGaP cache dir for the matching --cohort; repeat in order.")
    p.add_argument("--output", type=Path, default=Path(__file__).parent / "spec_phv_report.csv",
                   help="Output CSV path.")
    p.add_argument("--debug-variable", metavar="VAR",
                   help="Print the resolved PHVs + per-PHV n for this variable (short name).")
    args = p.parse_args(argv)

    if not (len(args.cohort) == len(args.source_json) == len(args.cache_dir)):
        p.error("--cohort, --source-json, --cache-dir must be repeated the same number of times")

    var_labels = load_var_labels(args.harmonized_vars)

    # cohort -> {variable -> row}
    per_cohort: dict[str, dict[str, dict]] = {}
    for cohort, src, cache in zip(args.cohort, args.source_json, args.cache_dir):
        ingest_dir = args.specs_root / f"{cohort}-ingest"
        if not ingest_dir.is_dir():
            print(f"WARNING: no ingest dir for cohort {cohort}: {ingest_dir}", file=sys.stderr)
            continue
        per_cohort[cohort] = build_cohort_rows(ingest_dir, src, cache, var_labels)
        print(f"{cohort}: {len(per_cohort[cohort])} variables from {ingest_dir.name}")

    if args.debug_variable:
        _debug(args, var_labels, per_cohort)
        return 0

    _write_csv(args.output, per_cohort, var_labels)
    print(f"\nWrote {args.output}")
    return 0


def _debug(args, var_labels, per_cohort) -> None:
    var = args.debug_variable
    print(f"\n=== DEBUG variable={var!r} ({var_labels.get(var, var)}) ===")
    for cohort, src, cache in zip(args.cohort, args.source_json, args.cache_dir):
        rows = per_cohort.get(cohort, {})
        row = rows.get(var)
        if not row:
            print(f"  {cohort}: (not present)")
            continue
        source_doc = json.loads(Path(src).read_text())
        phv_name_map = load_phv_name_map(Path(cache))
        print(f"  {cohort}: phv_count={row['phv_count']} total_n={row['total_n']} "
              f"obs_type={row['observation_type']}")
        for phv in row["phvs"]:
            col = phv_name_map.get(phv, phv)
            pht = row["phv_pht"].get(phv)
            n = _col_n_valid(source_doc, phv, pht, phv_name_map)
            print(f"      {phv}  pht={pht}  col={col!r}  n_valid={n}")


def _write_csv(output: Path, per_cohort, var_labels) -> None:
    cohorts = sorted(per_cohort)
    all_vars = sorted({v for rows in per_cohort.values() for v in rows})
    fieldnames = ["variable"]
    for c in cohorts:
        fieldnames += [f"{c}_phv", f"{c}_n"]

    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for var in all_vars:
            label = var_labels.get(var, var)
            out = {"variable": label}
            for c in cohorts:
                row = per_cohort[c].get(var)
                out[f"{c}_phv"] = row["phv_count"] if row else ""
                out[f"{c}_n"] = (row["total_n"] if row and row["total_n"] is not None else "") if row else ""
            writer.writerow(out)


if __name__ == "__main__":
    raise SystemExit(main())
