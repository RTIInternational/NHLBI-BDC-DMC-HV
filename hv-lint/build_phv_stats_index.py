#!/usr/bin/env python3
"""Build compressed PHV value-count indexes from dbGaP var_report files.

Parses every ``*.var_report.xml`` for a cohort and writes
``<cache key>_stats.json.gz`` with, for every variable, the number of
non-null values, and for each coded variable also the count of each observed
code:

    {"phv00101487": {"n": 38, "c": {"1": 37, "0": 1}},
     "phv00104203": {"n": 112}, ...}

These are dbGaP's published aggregate summaries (the "Variable Report"
tables on the study pages). No participant-level data is read or stored.

The index powers the HV-Lint rules that need observed values rather than
dictionary text: 3.17b (an unlabelled 1/2-coded flag mapped with 0/1 keys)
and 3.18 (a conditional follow-up question mapped to ABSENT), and 3.19 (a
block whose source variables have no value at all), which needs ``n`` for
uncoded variables too.

Only the consent-group total is used (variable ids without a ``.cN``
suffix). ``c`` is present only for variables with ``<enum>`` counts; a reader
that wants the coded variables keys on it (``load_stats_index``). A variable
whose report has no ``<stat>`` has no ``n`` (an uncoded one has no entry): its n is
unknown, not 0.

Usage (the hv-lint cache holds no var_report files, so name the directory that does):
    python hv-lint/build_phv_stats_index.py --cohort phs000287.v7 \\
        --source-dir /path/to/phs000287.v7.p1/pheno_variable_summaries \\
        --study-prefix phs000287.v7.

``update_data.py`` fetches only the data dictionaries, so the var_report
files come from any staging of the pinned release (the hv_dataqc cache
fetcher's ``--include-var-reports``, or the AI repo's ``data/dbgap/``).
Only files stamped ``<cohort>.`` are read, so files from another release in the
same directory are ignored. ``--cohort`` is the cache key the detail index uses,
which is the study release (``phs000287.v7``); the output is named
``<key>_stats.json.gz`` next to ``<key>_detail.json.gz``.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HVLINT_DIR = Path(__file__).resolve().parent
CACHE_DIR = HVLINT_DIR / "dbgap-cache"

sys.path.insert(0, str(HVLINT_DIR))
import _cohorts  # noqa: E402


def _record_artifact(output_dir: Path, cohort_key: str, gz_path: Path) -> None:
    """Record ``gz_path``'s sha256 and counts under ``cohort_key`` in the manifest.

    ``_cohorts.load_cache_artifact`` refuses an artifact with no record, so an index written
    without one is unreadable. Merged field-wise (``write_manifest_entries`` -> ``merge_entry``):
    the release's provenance and its other artifacts' records survive.
    """
    _cohorts.write_manifest_entries(
        output_dir,
        {cohort_key: {_cohorts.ARTIFACTS_FIELD: {gz_path.name: _cohorts.artifact_record(gz_path)}}})


def parse_var_report(path: Path) -> dict[str, dict]:
    """Parse one ``*.var_report.xml`` and return ``{base_phv: {"n"[, "c"]}}``.

    ``c`` maps each observed code to its count. An ``<enum>`` with a ``code``
    attribute is a coded value whose text is the label; one without a
    ``code`` attribute is an uncoded integer value whose text is the value
    itself (CARDIA endpoint flags are published this way), so the text is
    used as the key.

    Raises :class:`_cohorts.DataDictUnreadable` when the file cannot be read or parsed:
    returning ``{}`` would drop the table's variables from an index whose manifest digest then
    vouches for it.
    """
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise _cohorts.DataDictUnreadable(f"{path}: XML parse error: {exc}") from exc

    records: dict[str, dict] = {}
    for var in root.iter("variable"):
        var_id = var.get("id", "")
        # Consent-group rows repeat the variable as phvNNN.vN.pN.cN.
        if ".c" in var_id:
            continue
        base_phv = var_id.split(".")[0]
        if not base_phv.startswith("phv"):
            continue
        stats = var.find("total/stats")
        if stats is None:
            continue
        enums = stats.findall("enum")
        stat = stats.find("stat")
        if not enums:
            if stat is None:
                continue
            try:
                records[base_phv] = {"n": int(stat.get("n", ""))}
            except ValueError:
                pass
            continue
        n: int | None = None
        if stat is not None:
            try:
                n = int(stat.get("n", ""))
            except ValueError:
                n = None
        counts: dict[str, int] = {}
        for e in enums:
            key = e.get("code")
            if key is None:
                key = (e.text or "").strip()
            try:
                counts[key] = counts.get(key, 0) + int(e.get("count", "0"))
            except ValueError:
                continue
        # No <stat>: the n is unknown, so the entry has none (never 0, which 3.19 reads as
        # empty), exactly as an uncoded variable with no <stat> has no entry.
        records[base_phv] = {"c": counts} if n is None else {"n": n, "c": counts}
    return records


def build_stats_index(
    cohort_key: str,
    source_dir: Path,
    output_dir: Path,
    *,
    study_prefix: str | None = None,
) -> int:
    """Build ``<cohort_key>_stats.json.gz`` from ``source_dir``. Returns PHV count.

    ``study_prefix`` (e.g. ``"phs000287.v7."``) restricts the build to files
    from the pinned study version, so a directory that also holds another
    study's or version's reports cannot leak into the index.
    """
    files = sorted(source_dir.glob("*.var_report.xml"))
    if study_prefix:
        files = [f for f in files if f.name.startswith(study_prefix)]
    if not files:
        print(f"  [stats] No var_report.xml files for {cohort_key} in {source_dir} -- skipping")
        return 0

    index: dict[str, dict] = {}
    for f in files:
        index.update(parse_var_report(f))

    # Checked BEFORE writing: an index the manifest then refuses to record cannot be read.
    _cohorts.read_manifest_for_update(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    gz_path = output_dir / f"{cohort_key}_stats.json.gz"
    json_bytes = json.dumps(
        dict(sorted(index.items())), separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    # mtime=0 keeps the gzip header stable, so a rebuild from the same
    # files produces a byte-identical index and no spurious git diff.
    with gz_path.open("wb") as raw, gzip.GzipFile(
        fileobj=raw, mode="wb", mtime=0
    ) as gz:
        gz.write(json_bytes)
    _record_artifact(output_dir, cohort_key, gz_path)

    coded = sum(1 for rec in index.values() if "c" in rec)
    print(
        f"  [stats] {cohort_key:12s}: {len(index):>7,} PHVs ({coded:,} coded), "
        f"{len(files):>4} files -> {gz_path.stat().st_size:>9,} bytes"
    )
    return len(index)


_RELEASE_KEY_RE = re.compile(r"^phs\d{6}\.v\d+$")
_DATA_DICT_NAME_RE = re.compile(r"^phs\d{6}\.v\d+\.(pht\d{6})\.v\d+\.(.+)\.data_dict\.xml$")


def _table_description(path: Path) -> str:
    """The ``<data_table>``'s own ``<description>`` (the first one, before any variable).

    Raises :class:`_cohorts.DataDictUnreadable` when the file cannot be parsed up to that
    point: an empty description would be published as the table's real one. A file that is
    damaged only after its description still yields the correct entry, so it is not refused.
    """
    try:
        for _event, elem in ET.iterparse(path, events=("end",)):
            if elem.tag == "description":
                return " ".join((elem.text or "").split())
            if elem.tag == "variable":
                return ""
    except (ET.ParseError, OSError) as exc:
        raise _cohorts.DataDictUnreadable(f"{path}: XML parse error: {exc}") from exc
    return ""


def build_tables_index(
    cohort_key: str,
    source_dir: Path,
    output_dir: Path,
    *,
    study_prefix: str | None = None,
) -> int:
    """Write ``<cohort_key>_tables.json.gz``: ``{pht: {"name", "description"}}``. Returns count.

    The short name is the segment dbGaP puts in every data-dictionary filename
    (``phs000007.v35.pht000009.v2.ex0_7s.data_dict.xml`` -> ``ex0_7s``) and the table's own
    ``<description>`` ("Clinic Exam, Original Cohort Exams 1 - 7"). FHS encodes the cohort and
    exam in the name, which is what rule 1.8 checks a single-label block's visit against; MESA
    names the exam ("MESA_Exam4Main"), which is what rule 1.14 checks.
    """
    files = sorted(source_dir.glob("*.data_dict.xml"))
    if study_prefix:
        files = [f for f in files if f.name.startswith(study_prefix)]
    names: dict[str, dict[str, str]] = {}
    for f in files:
        m = _DATA_DICT_NAME_RE.match(f.name)
        if m:
            names[m.group(1)] = {"name": m.group(2), "description": _table_description(f)}
    if not names:
        print(f"  [tables] No data_dict.xml files for {cohort_key} in {source_dir} -- skipping")
        return 0
    _cohorts.read_manifest_for_update(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    gz_path = output_dir / f"{cohort_key}_tables.json.gz"
    payload = json.dumps(dict(sorted(names.items())), separators=(",", ":")).encode("utf-8")
    with gz_path.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        gz.write(payload)
    _record_artifact(output_dir, cohort_key, gz_path)
    print(f"  [tables] {cohort_key:12s}: {len(names):>5,} tables -> {gz_path.name}")
    return len(names)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Build PHV value-count indexes from dbGaP var_report files"
    )
    p.add_argument("--cohort", required=True,
                   help="Cache key of the matching detail index (the stem before "
                        "_detail.json.gz) -- names the output file")
    p.add_argument("--source-dir", default=None,
                   help="Directory of *.var_report.xml (default: "
                        "hv-lint/dbgap-cache/<cohort>/pheno_variable_summaries)")
    p.add_argument("--study-prefix", default=None,
                   help="Only read files whose name starts with this, e.g. phs000287.v7. "
                        "Defaults to '<cohort>.'; any other value is refused.")
    p.add_argument("--output-dir", default=str(CACHE_DIR),
                   help="Output directory (default: hv-lint/dbgap-cache)")
    p.add_argument("--tables", action="store_true",
                   help="Write <key>_tables.json.gz (pht -> table short name, from the "
                        "data_dict filenames) instead of the value-count index")
    args = p.parse_args()

    # The key must name ONE release, and only files stamped with it are read. A cohort name
    # (`fhs`) wrote `fhs_stats.json.gz` under a manifest entry with no release, which the
    # release check can never verify -- the same unprovenanced artifact the PHV builders no
    # longer write. There is no fallback name.
    if not _RELEASE_KEY_RE.match(args.cohort):
        print(f"ERROR: --cohort {args.cohort!r} is not a release key (phs######.v#). Publishing "
              f"nothing: an index keyed by anything else has no release to verify.",
              file=sys.stderr)
        return 1
    prefix = f"{args.cohort}."
    if args.study_prefix not in (None, prefix):
        print(f"ERROR: --study-prefix {args.study_prefix!r} does not match --cohort "
              f"{args.cohort!r}. Publishing nothing: the index would be keyed by one release "
              f"and built from another.", file=sys.stderr)
        return 1
    source = (Path(args.source_dir) if args.source_dir
              else CACHE_DIR / args.cohort / "pheno_variable_summaries")
    if not source.is_dir():
        print(f"ERROR: source directory not found: {source}", file=sys.stderr)
        return 1
    builder = build_tables_index if args.tables else build_stats_index
    try:
        n = builder(args.cohort, source, Path(args.output_dir), study_prefix=prefix)
    except _cohorts.ManifestUnreadable as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except _cohorts.DataDictUnreadable as exc:
        print(f"ERROR: {exc}\nPublishing nothing: no index or {_cohorts.MANIFEST_NAME} "
              f"entry was written.", file=sys.stderr)
        return 1
    return 0 if n else 1


if __name__ == "__main__":
    raise SystemExit(main())
