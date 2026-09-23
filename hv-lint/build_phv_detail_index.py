#!/usr/bin/env python3
"""Build extended PHV detail indexes from cached dbGaP FTP data dictionaries.

Parses every ``*.data_dict.xml`` file in the local FTP cache and produces
compressed JSON files with per-variable metadata: name, parent PHT,
data type, unit, description, and coded value set.

These detail indexes power the semantic validation rules in Phase 3
(checks 3.9-3.12) that go beyond structural / existence checks.

Usage:
    python hv-lint/build_phv_detail_index.py
    python hv-lint/build_phv_detail_index.py --source-cache hv-lint/dbgap-cache
    python hv-lint/build_phv_detail_index.py --output-dir hv-lint/dbgap-cache

Normally invoked via ``update_data.py`` which handles source fetching
and index building together. Run standalone only when rebuilding
indexes from already-fetched FTP data dictionaries.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import gzip
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _cohorts  # noqa: E402


def parse_data_dict(path: Path) -> dict[str, dict]:
    """Parse one ``*.data_dict.xml`` and return per-PHV detail records.

    Returns
    -------
    dict mapping ``base_phv`` -> record dict with keys:
        name, pht, type, unit, description, codes
    """
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        print(f"  WARN: XML parse error in {path.name}: {exc}", file=sys.stderr)
        return {}

    root = tree.getroot()

    # Extract table-level PHT from <data_table id="phtNNNNNN.vN">
    table_id_raw = root.get("id", "")
    base_pht = table_id_raw.split(".")[0] if table_id_raw else ""

    records: dict[str, dict] = {}

    for var_elem in root.iter("variable"):
        phv_raw = var_elem.get("id", "")
        base_phv = phv_raw.split(".")[0]
        if not base_phv.startswith("phv"):
            continue

        name_el = var_elem.find("name")
        desc_el = var_elem.find("description")
        type_el = var_elem.find("type")
        unit_el = var_elem.find("unit")
        ci_el = var_elem.find("coll_interval")

        name = name_el.text.strip() if name_el is not None and name_el.text else ""
        desc = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
        vtype = type_el.text.strip() if type_el is not None and type_el.text else ""
        unit = unit_el.text.strip() if unit_el is not None and unit_el.text else None
        coll_interval = ci_el.text.strip() if ci_el is not None and ci_el.text else None

        # Normalise type to lowercase for consistent matching
        vtype = vtype.lower()

        # Extract coded values: <value code="X">Label</value>
        codes: dict[str, str] | None = None
        value_elems = var_elem.findall("value")
        if value_elems:
            codes = {}
            for ve in value_elems:
                code = ve.get("code", "")
                label = (ve.text or "").strip()
                if code:
                    codes[code] = label

        record: dict = {
            "name": name,
            "pht": base_pht,
            "type": vtype,
            "description": desc,
        }
        if unit is not None:
            record["unit"] = unit
        if codes:
            record["codes"] = codes
        if coll_interval:
            record["coll_interval"] = coll_interval

        records[base_phv] = record

    return records


def build_one(cohort_dir: Path, output: Path, source: Path) -> dict | None:
    """Build one staging directory's PHV DETAIL index. Returns its manifest entry, or ``None``.

    The companion of :func:`build_phv_index.build_one`, and callable from ``update_data.py`` for
    the same reason: the fetch orchestrator must produce the release-keyed, provenance-carrying
    artifact the mandatory release check expects, not a second one of its own.
    """
    ftp_dir = cohort_dir / "pheno_variable_summaries"
    if not ftp_dir.is_dir():
        return None

    # The release is decided FIRST, because it selects the inputs. `retire_superseded_data_dicts`
    # deliberately leaves files whose names carry no release -- it refuses to guess about a name
    # it cannot parse -- so without this filter a hand-written or legacy-named dictionary adds
    # records to an artifact whose manifest claims one specific release. The basic builder had
    # the identical hole; both are closed here rather than one at a time.
    accession, version, _seen = _cohorts.study_from_data_dicts(cohort_dir)
    prefix = f"{accession}.{version}." if accession else None
    all_files = sorted(ftp_dir.glob("*.data_dict.xml"))
    data_dict_files = [p for p in all_files if not prefix or p.name.startswith(prefix)]
    if len(all_files) != len(data_dict_files):
        print(f"  {cohort_dir.name}: skipped {len(all_files) - len(data_dict_files)} data "
              f"dictionaries not stamped {prefix[:-1]}", file=sys.stderr)
    if not data_dict_files:
        return None

    cohort_index: dict[str, dict] = {}
    for dd_file in data_dict_files:
        cohort_index.update(parse_data_dict(dd_file))

    # `parse_data_dict` turns an XML parse error into `{}`, so a wholly corrupt fetch reaches
    # here with files on disk and no records. Writing that produces an EMPTY detail index
    # carrying valid provenance, which every consumer then treats as present -- check 5.8 reads
    # it as "this cohort has no collection intervals" and skips, the one reading the absent-file
    # guard was added to prevent. The basic builder has refused an empty mapping all along;
    # this is the same refusal, and its absence here was an asymmetry between the two.
    if not cohort_index:
        print(
            f"  WARNING: {cohort_dir.name}: {len(data_dict_files)} data dictionaries parsed to "
            "ZERO records -- writing no detail index and recording no provenance",
            file=sys.stderr,
        )
        return None

    # Name the artifact by the STUDY, not by the source directory. A directory name is a local
    # convention (`aric`, `aric-v8`, `aric-v9`) that nothing validates and that cannot hold two
    # releases of one study at once; `phs000280.v8` can, and carries its own provenance. Falls
    # back to the directory name, loudly, when no accession is parseable.
    accession, version, _seen = _cohorts.study_from_data_dicts(cohort_dir)
    entry: dict = {
        "phvs": len(cohort_index),
        "phts": len({r.get("pht") for r in cohort_index.values() if r.get("pht")}),
        "data_dicts": len(data_dict_files),
        "source_dir": cohort_dir.name,
    }
    if accession:
        key = f"{accession}.{version}"
        entry.update({
            "cohort": _cohorts.cohort_from_source_dir(cohort_dir.name, source),
            "study": accession,
            "study_version": version,
            "built": _dt.datetime.now(tz=_dt.UTC).date().isoformat(),
        })
    else:
        key = cohort_dir.name.lower()
        print(
            f"  WARNING: {cohort_dir.name}: no single phs######.v# accession in its data "
            f"dictionaries -- naming by directory ('{key}') and recording NO provenance",
            file=sys.stderr,
        )

    # Write compressed JSON
    json_bytes = json.dumps(
        cohort_index, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    gz_path = output / f"{key}_detail.json.gz"
    with gzip.open(gz_path, "wb") as f:
        f.write(json_bytes)

    gz_size = gz_path.stat().st_size
    n_coded = sum(1 for r in cohort_index.values() if r.get("codes"))
    print(
        f"  {cohort_dir.name:12s}: {len(cohort_index):>7,} PHVs "
        f"({n_coded:>5,} coded), "
        f"{len(data_dict_files):>4} files -> {gz_size:>9,} bytes "
        f"({gz_path.name})"
    )
    return entry


def main() -> int:
    hvlint_dir = Path(__file__).resolve().parent
    # Default source cache is hv-lint/dbgap-cache (same dir as output)
    # Falls back to control-center data/dbgap-cache if present.
    for candidate in [hvlint_dir.parent.parent, hvlint_dir.parent]:
        if (candidate / "data" / "dbgap-cache").is_dir():
            repo_root = candidate
            break
    else:
        repo_root = hvlint_dir  # HV repo: source cache is hv-lint/dbgap-cache

    p = argparse.ArgumentParser(
        description="Build extended PHV detail indexes from FTP data dictionaries"
    )
    p.add_argument(
        "--source-cache",
        default=None,
        help="Path to dbGaP FTP cache (default: hv-lint/dbgap-cache, or data/dbgap-cache if present)",
    )
    p.add_argument(
        "--output-dir",
        default=str(hvlint_dir / "dbgap-cache"),
        help="Output directory for compressed JSON (default: hv-lint/dbgap-cache/)",
    )
    args = p.parse_args()

    if args.source_cache:
        source = Path(args.source_cache)
    elif (repo_root / "data" / "dbgap-cache").is_dir():
        source = repo_root / "data" / "dbgap-cache"
    elif (hvlint_dir / "dbgap-cache").is_dir():
        source = hvlint_dir / "dbgap-cache"
    else:
        print(
            f"ERROR: Cannot find dbGaP source cache. "
            f"Run 'python hv-lint/update_data.py' first or use --source-cache.",
            file=sys.stderr,
        )
        return 1

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)

    print(f"Source cache: {source}")
    print(f"Output dir:   {output}")
    print()

    total_phvs = 0
    manifest: dict[str, dict] = {}

    for cohort_dir in sorted(source.iterdir()):
        if not cohort_dir.is_dir():
            continue
        entry = build_one(cohort_dir, output, source)
        if entry is None:
            continue
        total_phvs += entry["phvs"]
        if entry.get("study"):
            manifest[f"{entry['study']}.{entry['study_version']}"] = entry

    print(f"\nTotal: {total_phvs:,} PHVs indexed with detail metadata")
    if manifest:
        mpath = _cohorts.write_manifest_entries(output, manifest)
        print()
        print(f"Provenance recorded for {len(manifest)} cohort(s) -> {mpath.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
