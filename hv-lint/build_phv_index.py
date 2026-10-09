#!/usr/bin/env python3
"""Build compact PHV-to-PHT indexes from cached dbGaP variable lists.

Primary source: ``*.data_dict.xml`` files in the FTP cache
(``pheno_variable_summaries/`` sub-directory). These cover every table
including restricted-access and HeartGO tables.

Only inputs attributable to the release being recorded contribute: each
``*.data_dict.xml`` must carry that release's ``phs######.v#.`` stamp. The
CGI ``variables.xml`` bulk index was merged as a supplement until
2026-09-23 and is not read any more -- it carries no release, so a copy
left from an earlier one silently made the artifact a union.

Produces compressed JSON files mapping base PHV accessions to base PHT
accessions. These compact indexes are used by Phase 3
(validate_dbgap_crossref.py).

Usage:
    python hv-lint/build_phv_index.py
    python hv-lint/build_phv_index.py --source-cache hv-lint/dbgap-cache
    python hv-lint/build_phv_index.py --output-dir hv-lint/dbgap-cache

Normally invoked via ``update_data.py`` which handles source fetching
and index building together. Run standalone only when rebuilding
indexes from already-fetched source data.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import gzip
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _cohorts  # noqa: E402


def parse_data_dict_xml(path: Path) -> dict[str, str]:
    """Parse one FTP ``*.data_dict.xml`` and return {base_phv: base_pht}.

    Raises :class:`_cohorts.DataDictUnreadable` when the file cannot be read or parsed, or its
    root names no ``pht`` table: returning ``{}`` would drop the table from an index whose
    manifest digest then vouches for it.
    """
    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError) as exc:
        raise _cohorts.DataDictUnreadable(f"{path}: XML parse error: {exc}") from exc

    root = tree.getroot()
    table_id_raw = root.get("id", "")
    base_pht = table_id_raw.split(".")[0] if table_id_raw else ""
    if not base_pht.startswith("pht"):
        raise _cohorts.DataDictUnreadable(
            f"{path}: root element names no pht table (id={table_id_raw!r})")

    mapping: dict[str, str] = {}
    for var_elem in root.iter("variable"):
        phv_raw = var_elem.get("id", "")
        base_phv = phv_raw.split(".")[0]
        if base_phv.startswith("phv"):
            mapping[base_phv] = base_pht
    return mapping


def build_mapping_from_ftp(cohort_dir: Path, prefix: str | None = None) -> dict[str, str]:
    """Build {base_phv: base_pht} from FTP data dicts in pheno_variable_summaries/.

    ``prefix`` is the ``phs######.v#.`` stamp of the release being recorded. When given, only
    files carrying it contribute -- a file from another release, or one whose name cannot be
    attributed to any release, must not add PHVs to an artifact that claims this one. Omitted,
    every file contributes, which is correct only when no release is being claimed.
    """
    ftp_dir = cohort_dir / "pheno_variable_summaries"
    if not ftp_dir.is_dir():
        return {}
    mapping: dict[str, str] = {}
    skipped = 0
    for dd_file in sorted(ftp_dir.glob("*.data_dict.xml")):
        if prefix and not dd_file.name.startswith(prefix):
            skipped += 1
            continue
        mapping.update(parse_data_dict_xml(dd_file))
    if skipped:
        print(f"  {cohort_dir.name}: skipped {skipped} data dictionaries not stamped "
              f"{prefix[:-1]}", file=sys.stderr)
    return mapping


def build_one(cohort_dir: Path, output: Path, source: Path) -> dict | None:
    """Build one staging directory's PHV index. Returns its manifest entry, or ``None``.

    Callable from ``update_data.py`` so the fetch orchestrator and this script build the same
    artifact from the same source. It previously had its own ``variables.xml``-only builder that
    wrote ``<cohort>.json.gz`` and recorded no provenance, so the documented onboarding command
    produced a cache the mandatory release check then rejected.

    The returned entry carries ``study``/``study_version`` only when the data dictionaries name
    one release; callers must treat their ABSENCE as "provenance unknown" rather than filling it
    in from what a cohort declares, which would make the release check confirm itself.

    **Only inputs attributable to the recorded release contribute.** Every PHV here comes from a
    ``*.data_dict.xml`` whose ``phs######.v#.`` stamp matches the release this artifact is keyed
    and provenance-stamped by. Two sources used to slip past that and make the artifact a union
    of releases -- the thing keying by release exists to prevent:

    * ``variables.xml``, the CGI bulk index, was merged as a supplement. It carries no release
      in its name or contents, so a copy left from an earlier release was indistinguishable from
      a current one and there was no check that could tell. Removed rather than guarded, after
      three review rounds closed three separate roads to the same contamination. It cost
      nothing: every committed cache was built by ``--source-cache`` from a staging tree that
      contains no ``variables.xml`` at all, so the supplement contributed zero PHVs to all of
      them.
    * unstamped ``*.data_dict.xml`` files, which `retire_superseded_data_dicts` deliberately
      leaves alone (it refuses to guess about a name it cannot parse). They were still parsed
      into the mapping, so a hand-written or legacy-named file added PHVs to an artifact whose
      manifest claimed one specific release.
    """
    # The release is decided FIRST, because it selects the inputs. Deciding it afterwards is
    # what allowed inputs from other releases to be counted into the artifact it names.
    accession, version, seen = _cohorts.study_from_data_dicts(cohort_dir)
    # AMBIGUITY IS A REFUSAL, NOT A FALLBACK. That function returns no accession for two
    # different reasons and they are not interchangeable: nothing stamped at all (`seen == 0`),
    # or several releases stamped and it declines to choose (`seen > 0`). Falling back to an
    # unprefixed build in the second case merges every release present into one artifact named
    # by directory -- a union, the thing keying by release exists to prevent, and a mid-bump
    # staging tree is routinely in exactly that state.
    if seen and not accession:
        print(
            f"  WARNING: {cohort_dir.name}: its {seen} data dictionaries name MORE THAN ONE "
            f"release -- writing nothing, because an index over all of them is a union",
            file=sys.stderr,
        )
        return None
    prefix = f"{accession}.{version}." if accession else None
    mapping = build_mapping_from_ftp(cohort_dir, prefix)
    ftp_count = len(mapping)

    if not mapping:
        return None

    phts = len(set(mapping.values()))
    # Name the artifact by the STUDY, not by the source directory. A directory name is a
    # local convention (`aric`, `aric-v8`, `aric-v9`) that nothing validates and that cannot
    # hold two releases of one study at once; `phs000280.v8` can, and carries its own
    # provenance. Falls back to the directory name, loudly, when no accession is parseable.
    entry: dict = {"phvs": len(mapping), "phts": phts, "source_dir": cohort_dir.name}
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
    json_bytes = json.dumps(mapping, separators=(",", ":")).encode("utf-8")
    gz_path = output / f"{key}.json.gz"
    with gzip.open(gz_path, "wb") as f:
        f.write(json_bytes)

    # The digest and counts the loader verifies on every read (`_cohorts.load_cache_artifact`).
    entry[_cohorts.ARTIFACTS_FIELD] = {gz_path.name: _cohorts.artifact_record(gz_path)}
    gz_size = gz_path.stat().st_size
    print(
        f"  {cohort_dir.name:12s}: {len(mapping):>7,} PHVs "
        f"({ftp_count:,} FTP), "
        f"{phts:>4} PHTs -> {gz_size:>8,} bytes ({gz_path.name})"
    )
    return entry


def main() -> int:
    # Auto-detect repo root -- works from control center (hv-lint/)
    # or HV repo (hv-lint/). The dbGaP cache is in the control center.
    hvlint_dir = Path(__file__).resolve().parent
    # Default source cache is hv-lint/dbgap-cache (same dir as output)
    # Falls back to control-center data/dbgap-cache if present.
    for candidate in [hvlint_dir.parent.parent, hvlint_dir.parent]:
        if (candidate / "data" / "dbgap-cache").is_dir():
            repo_root = candidate
            break
    else:
        repo_root = hvlint_dir  # HV repo: source cache is hv-lint/dbgap-cache

    p = argparse.ArgumentParser(description="Build compact PHV-to-PHT indexes")
    p.add_argument(
        "--source-cache",
        default=None,
        help="Path to dbGaP HTML cache (default: hv-lint/dbgap-cache, or data/dbgap-cache if present)"
    )
    p.add_argument(
        "--output-dir",
        default=str(hvlint_dir / "dbgap-cache"),
        help="Output directory for compressed JSON (default: hv-lint/dbgap-cache/)"
    )
    args = p.parse_args()

    # Auto-detect source cache
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
    # Checked BEFORE any index is published: indexes land before the manifest does, and an
    # index left there by a run whose manifest write is then refused has no recorded release.
    try:
        _cohorts.read_manifest_for_update(output)
    except _cohorts.ManifestUnreadable as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Source cache: {source}")
    print(f"Output dir:   {output}")
    print()

    total_phvs = 0
    manifest: dict[str, dict] = {}
    # Listed BEFORE the scratch directory exists, and dot-directories skipped: `source` and
    # `output` are the same directory by default, so the scratch dir would otherwise be built.
    cohort_dirs = [d for d in sorted(source.iterdir())
                   if d.is_dir() and not d.name.startswith(".")]
    # Every index is built into scratch and published only when ALL cohorts built: an
    # unreadable data dictionary aborts the run with the cache and manifest untouched.
    scratch = output / ".build-phv-index"
    shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir()
    try:
        for cohort_dir in cohort_dirs:
            entry = build_one(cohort_dir, scratch, source)
            if entry is None:
                continue
            total_phvs += entry["phvs"]
            if entry.get("study"):
                manifest[f"{entry['study']}.{entry['study_version']}"] = entry
        for built in sorted(scratch.glob("*.json.gz")):
            built.replace(output / built.name)
    except _cohorts.DataDictUnreadable as exc:
        print(f"ERROR: {exc}\nPublishing nothing: no index or {_cohorts.MANIFEST_NAME} "
              f"entry was written.", file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    print(f"\nTotal: {total_phvs:,} PHVs indexed")
    if manifest:
        try:
            mpath = _cohorts.write_manifest_entries(output, manifest)
        except _cohorts.ManifestUnreadable as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print()
        print(f"Provenance recorded for {len(manifest)} cohort(s) -> {mpath.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
