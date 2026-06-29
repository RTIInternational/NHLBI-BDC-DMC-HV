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

from hv_dataqc.hv_dataqc_common import load_phv_name_map, write_xlsx, XLSX_FMT_COUNT

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
                   help="Output CSV path. A formatted .xlsx is also written alongside it "
                        "(same stem, .xlsx) unless --no-xlsx is given.")
    p.add_argument("--no-xlsx", action="store_true",
                   help="Do not also write the formatted .xlsx (CSV only).")
    p.add_argument("--layout", type=Path, default=None,
                   help=f"S4 layout config (canonical cohort columns + variable rows). "
                        f"Default: {DEFAULT_LAYOUT_PATH}")
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

    layout = load_layout(args.layout)
    _write_csv(args.output, per_cohort, var_labels, layout)
    print(f"\nWrote {args.output}")
    if not args.no_xlsx:
        xlsx_path = args.output.with_suffix(".xlsx")
        _write_xlsx(xlsx_path, per_cohort, var_labels, layout)
        print(f"Wrote {xlsx_path}")
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


DEFAULT_LAYOUT_PATH = Path(__file__).parent / "config" / "s4_layout.yaml"


def load_layout(path: Path | None) -> dict:
    """Load the S4 layout config (canonical cohort columns + variable rows).

    Returns a dict with:
      - cohorts: ordered display cohort names (column order)
      - cohort_keys: {display_name -> internal cohort key} for names that
        differ between the template and the ingest-dir cohort (e.g.
        "HCHS/SOL" -> "HCHS"). Names not listed map to themselves.
      - variables: ordered template row labels (may be empty)
    Returns empty/defaults if the file is absent.
    """
    effective = path or DEFAULT_LAYOUT_PATH
    if not effective.exists():
        return {"cohorts": [], "cohort_keys": {}, "variables": []}
    cfg = yaml.safe_load(effective.read_text()) or {}
    return {
        "cohorts": list(cfg.get("cohorts") or []),
        "cohort_keys": dict(cfg.get("cohort_keys") or {}),
        "variables": list(cfg.get("variables") or []),
        "aliases": dict(cfg.get("aliases") or {}),
        "unmatched_note": cfg.get("unmatched_note") or "",
    }


def _build_label_resolver(template_labels: list[str], aliases: dict) -> dict[str, str]:
    """Map a normalized spec label -> the template label it belongs in.

    Matching is case-insensitive (keys are lowercased/stripped). Each template
    label maps to itself; each alias maps to its template label. Aliases win
    only for genuine spelling differences — case is already handled by the
    normalization, so plain capitalization variants need no alias entry.
    """
    def norm(s: str) -> str:
        return str(s).strip().lower()

    resolver: dict[str, str] = {}
    for tpl in template_labels:
        resolver[norm(tpl)] = tpl
    for tpl, alts in aliases.items():
        for alt in alts or []:
            resolver[norm(alt)] = tpl
    return resolver


def _build_table(per_cohort, var_labels, layout: dict | None = None) -> tuple[list[str], list[list], list[str]]:
    """Build the S4 table as (headers, rows) — shared by the CSV and xlsx writers.

    Rows are value lists aligned to headers. When a canonical variable list is
    configured, rows follow it (blank where no data), then unmatched spec
    variables are appended after a blank separator + note row.
    """
    layout = layout or {}

    if layout.get("cohorts"):
        display_cohorts = layout["cohorts"]
        key_for = lambda disp: layout.get("cohort_keys", {}).get(disp, disp)
    else:
        display_cohorts = sorted(per_cohort)
        key_for = lambda disp: disp

    by_label: dict[str, dict[str, dict]] = {}
    for ckey, rows in per_cohort.items():
        for short, row in rows.items():
            by_label.setdefault(row.get("label", short), {})[ckey] = row

    headers = ["variable"]
    for disp in display_cohorts:
        headers += [f"{disp}_phv", f"{disp}_n"]

    def cells_for(label, label_rows: dict) -> list:
        out = [label]
        for disp in display_cohorts:
            row = label_rows.get(key_for(disp))
            out.append(row["phv_count"] if row else "")
            out.append(row["total_n"] if row and row["total_n"] is not None else "")
        return out

    template_labels = layout.get("variables") or []
    out_rows: list[list] = []

    if not template_labels:
        for label in sorted(by_label):
            out_rows.append(cells_for(label, by_label[label]))
        return headers, out_rows, []

    resolver = _build_label_resolver(template_labels, layout.get("aliases") or {})
    matched: dict[str, dict[str, dict]] = {}
    unmatched: list[str] = []
    for spec_label, cohort_rows in by_label.items():
        tpl = resolver.get(spec_label.strip().lower())
        if tpl is None:
            unmatched.append(spec_label)
            continue
        matched.setdefault(tpl, {}).update(cohort_rows)

    for label in template_labels:
        out_rows.append(cells_for(label, matched.get(label, {})))

    if unmatched:
        blank = [""] * len(headers)
        out_rows.append(blank)
        note = layout.get("unmatched_note") or (
            "Variables below have spec data but no matching Table S4 row."
        )
        out_rows.append([note] + [""] * (len(headers) - 1))
        for spec_label in sorted(unmatched):
            out_rows.append(cells_for(spec_label, by_label[spec_label]))

    return headers, out_rows, sorted(unmatched)


def _write_csv(output: Path, per_cohort, var_labels, layout: dict | None = None) -> None:
    headers, rows, unmatched = _build_table(per_cohort, var_labels, layout)
    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(headers)
        writer.writerows(rows)
    if unmatched:
        print(
            f"NOTE: {len(unmatched)} spec variable(s) had no template row; "
            f"appended at the bottom: {', '.join(unmatched)}",
            file=sys.stderr,
        )


def _write_xlsx(output: Path, per_cohort, var_labels, layout: dict | None = None) -> None:
    headers, rows, _ = _build_table(per_cohort, var_labels, layout)
    # Every numeric column (all *_phv and *_n counts) gets the integer-count
    # format; the leading "variable" column stays text.
    column_formats = [None] + [XLSX_FMT_COUNT] * (len(headers) - 1)
    write_xlsx(output, headers, rows, column_formats=column_formats, sheet_title="Table S4")


if __name__ == "__main__":
    raise SystemExit(main())
