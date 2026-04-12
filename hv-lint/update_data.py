#!/usr/bin/env python3
"""
update_data.py -- Fetch dbGaP source data and rebuild lint indexes.

Single entry point for all dbGaP data maintenance in hv-lint. Performs:
  1. Fetch CGI variable index (variables.xml) from NCBI
  2. Fetch FTP data dictionaries (*.data_dict.xml) from NCBI FTP
  3. Build compressed PHV-to-PHT index (.json.gz)
  4. Build compressed PHV detail index (.json.gz)
  5. Extract visit cache (visit-relevant metadata per table)

Fetched source XML files and intermediate data are written to
hv-lint/dbgap-cache/ and are git-ignored. The compressed indexes
(*.json.gz) built by the index steps ARE committed so that Phases 3
and 5 can run offline in CI and local environments.

Usage:
    # Full refresh -- fetch from NCBI + rebuild all indexes:
    python hv-lint/update_data.py

    # Single cohort:
    python hv-lint/update_data.py --cohort aric

    # Just rebuild indexes (source XMLs already present):
    python hv-lint/update_data.py --build-only

    # Just fetch (skip index building):
    python hv-lint/update_data.py --fetch-only

    # Preview what would be downloaded:
    python hv-lint/update_data.py --dry-run

    # List configured cohorts:
    python hv-lint/update_data.py --list

Requirements:
    pip install pyyaml requests-cache

    requests-cache is only needed for --fetch operations (steps 1-2).
    --build-only requires only pyyaml and stdlib.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HVLINT_DIR = Path(__file__).resolve().parent

# Ensure hv-lint dir is importable (for `from _http import get_session`)
if str(HVLINT_DIR) not in sys.path:
    sys.path.insert(0, str(HVLINT_DIR))
COHORTS_YAML = HVLINT_DIR / "cohorts.yaml"
CACHE_DIR = HVLINT_DIR / "dbgap-cache"

FTP_BASE = "https://ftp.ncbi.nlm.nih.gov/dbgap/studies"
CGI_BASE = "https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin"
NCBI_DELAY_SECONDS = 0.5  # polite delay between real network requests


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------
def load_cohorts(cohorts_yaml: Path | None = None) -> dict[str, dict]:
    """Load cohort config from cohorts.yaml.

    Returns dict mapping cohort key -> {study_id, data_version, ...}.
    """
    import yaml  # deferred so --help works without pyyaml

    path = cohorts_yaml or COHORTS_YAML
    if not path.exists():
        print(f"ERROR: cohorts.yaml not found at {path}", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        print(f"ERROR: cohorts.yaml is empty or malformed at {path}", file=sys.stderr)
        sys.exit(1)
    return data.get("cohorts", {})


# ---------------------------------------------------------------------------
# HTML parser for FTP directory listings
# ---------------------------------------------------------------------------
class FTPDirectoryParser(HTMLParser):
    """Extract href links from an NCBI FTP HTTPS directory listing."""

    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value and not value.startswith("?") and not value.startswith("/"):
                    self.links.append(value)


# ---------------------------------------------------------------------------
# HTML parser for CGI variable index
# ---------------------------------------------------------------------------
class VariableTableParser(HTMLParser):
    """Parse the dbGaP variable list HTML table.

    Each row: [phv_accession, var_name, var_desc, pht_accession, dataset_name]
    """

    def __init__(self):
        super().__init__()
        self.in_td = False
        self.current_row: list[str] = []
        self.rows: list[list[str]] = []
        self.current_text = ""

    def handle_starttag(self, tag, attrs):
        if tag == "td":
            self.in_td = True
            self.current_text = ""
        elif tag == "tr":
            self.current_row = []

    def handle_endtag(self, tag):
        if tag == "td":
            self.in_td = False
            self.current_row.append(self.current_text.strip())
        elif tag == "tr" and self.current_row:
            self.rows.append(self.current_row)

    def handle_data(self, data):
        if self.in_td:
            self.current_text += data


# ---------------------------------------------------------------------------
# Step 1: Fetch CGI variable index (variables.xml)
# ---------------------------------------------------------------------------
def fetch_cgi_index(cohort_key: str, study_id: str, data_version: str,
                    *, force: bool = False, dry_run: bool = False) -> bool:
    """Fetch variables.xml from the CGI endpoint."""
    url = (
        f"{CGI_BASE}/GetListOfAllObjects.cgi"
        f"?study_id={study_id}.{data_version}&object_type=variable"
    )
    dest = CACHE_DIR / cohort_key / "variables.xml"

    if dry_run:
        print(f"  [dry-run] Would fetch: {url}")
        print(f"             -> {dest}")
        return True

    if dest.exists() and not force:
        size_kb = dest.stat().st_size // 1024
        print(f"  [variables.xml] Already cached ({size_kb:,} KB) -- use --force to re-download")
        return True

    from _http import get_session

    dest.parent.mkdir(parents=True, exist_ok=True)
    session = get_session()
    try:
        if force:
            session.cache.delete(urls=[url])
        resp = session.get(url, timeout=120)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        size_kb = len(resp.content) // 1024
        from_cache = getattr(resp, "from_cache", False)
        source = "http-cache" if from_cache else "downloaded"
        print(f"  [variables.xml] OK ({source}, {size_kb:,} KB)")
        if not from_cache:
            time.sleep(NCBI_DELAY_SECONDS)
        return True
    except Exception as exc:
        print(f"  [variables.xml] FAILED: {exc}")
        return False


# ---------------------------------------------------------------------------
# Step 2: Fetch FTP data dictionaries
# ---------------------------------------------------------------------------
def fetch_ftp_data_dicts(cohort_key: str, study_id: str, data_version: str,
                         *, force: bool = False, dry_run: bool = False) -> bool:
    """Fetch all *.data_dict.xml from NCBI FTP pheno_variable_summaries/."""
    qualified = f"{study_id}.{data_version}"
    dir_url = f"{FTP_BASE}/{study_id}/{qualified}/pheno_variable_summaries/"
    print(f"  [FTP] Listing {dir_url}")

    if dry_run:
        print(f"  [dry-run] Would list and download data_dict.xml files")
        return True

    from _http import get_session

    session = get_session()
    try:
        resp = session.get(dir_url, timeout=60)
        resp.raise_for_status()
    except Exception as exc:
        print(f"  [FTP] ERROR listing directory: {exc}")
        return False

    parser = FTPDirectoryParser()
    parser.feed(resp.text)
    targets = sorted(set(e for e in parser.links if e.endswith(".data_dict.xml")))

    if not targets:
        print(f"  [FTP] No data_dict.xml files found ({len(parser.links)} entries)")
        return True  # Not an error -- some studies have none

    print(f"  [FTP] Found {len(targets)} data_dict files")
    dest_dir = CACHE_DIR / cohort_key / "pheno_variable_summaries"
    dest_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    skipped = 0
    failed = 0

    for i, fname in enumerate(targets, 1):
        file_url = f"{FTP_BASE}/{study_id}/{qualified}/pheno_variable_summaries/{fname}"
        dest = dest_dir / fname

        if dest.exists() and not force:
            skipped += 1
            continue

        try:
            r = session.get(file_url, timeout=120)
            r.raise_for_status()
            dest.write_bytes(r.content)
            from_cache = getattr(r, "from_cache", False)
            if not from_cache:
                downloaded += 1
                time.sleep(NCBI_DELAY_SECONDS)
            else:
                skipped += 1
        except Exception as exc:
            print(f"    !! {fname}: {exc}")
            failed += 1

        if i % 50 == 0 or i == len(targets):
            print(f"    [{i}/{len(targets)}] {downloaded} new, {skipped} cached, {failed} failed")

    print(f"  [FTP] Done: {downloaded} downloaded, {skipped} cached, {failed} failed")
    return failed == 0


# ---------------------------------------------------------------------------
# Step 3: Build PHV-to-PHT index
# ---------------------------------------------------------------------------
def build_phv_index(cohort_key: str) -> int:
    """Build compressed PHV-to-PHT index from variables.xml. Returns PHV count."""
    vf = CACHE_DIR / cohort_key / "variables.xml"
    if not vf.exists():
        print(f"  [index] No variables.xml for {cohort_key} -- skipping basic index")
        return 0

    parser = VariableTableParser()
    parser.feed(vf.read_text(encoding="utf-8", errors="replace"))
    parser.close()

    mapping: dict[str, str] = {}
    for row in parser.rows:
        if len(row) < 4:
            continue
        phv_base = row[0].split(".")[0]
        pht_base = row[3].split(".")[0]
        if phv_base.startswith("phv") and pht_base.startswith("pht"):
            mapping[phv_base] = pht_base

    json_bytes = json.dumps(mapping, separators=(",", ":")).encode("utf-8")
    gz_path = CACHE_DIR / f"{cohort_key}.json.gz"
    with gzip.open(gz_path, "wb") as f:
        f.write(json_bytes)

    phts = len(set(mapping.values()))
    gz_size = gz_path.stat().st_size
    print(
        f"  [index] {cohort_key:12s}: {len(mapping):>7,} PHVs, "
        f"{phts:>4} PHTs -> {gz_size:>8,} bytes"
    )
    return len(mapping)


# ---------------------------------------------------------------------------
# Step 4: Build PHV detail index
# ---------------------------------------------------------------------------
def parse_data_dict(path: Path) -> dict[str, dict]:
    """Parse one data_dict.xml and return per-PHV detail records."""
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        print(f"  WARN: XML parse error in {path.name}: {exc}", file=sys.stderr)
        return {}

    root = tree.getroot()
    base_pht = root.get("id", "").split(".")[0]

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
        vtype = (type_el.text.strip().lower() if type_el is not None and type_el.text else "")
        unit = unit_el.text.strip() if unit_el is not None and unit_el.text else None
        coll_interval = ci_el.text.strip() if ci_el is not None and ci_el.text else None

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


def build_phv_detail_index(cohort_key: str) -> int:
    """Build extended PHV detail index from FTP data dicts. Returns PHV count."""
    ftp_dir = CACHE_DIR / cohort_key / "pheno_variable_summaries"
    if not ftp_dir.is_dir():
        print(f"  [detail] No pheno_variable_summaries for {cohort_key} -- skipping")
        return 0

    data_dict_files = sorted(ftp_dir.glob("*.data_dict.xml"))
    if not data_dict_files:
        print(f"  [detail] No data_dict.xml files for {cohort_key} -- skipping")
        return 0

    cohort_index: dict[str, dict] = {}
    for dd_file in data_dict_files:
        records = parse_data_dict(dd_file)
        cohort_index.update(records)

    json_bytes = json.dumps(
        cohort_index, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    gz_path = CACHE_DIR / f"{cohort_key}_detail.json.gz"
    with gzip.open(gz_path, "wb") as f:
        f.write(json_bytes)

    gz_size = gz_path.stat().st_size
    n_coded = sum(1 for r in cohort_index.values() if r.get("codes"))
    print(
        f"  [detail] {cohort_key:12s}: {len(cohort_index):>7,} PHVs "
        f"({n_coded:>5,} coded), {len(data_dict_files):>4} files -> "
        f"{gz_size:>9,} bytes"
    )
    return len(cohort_index)


# ---------------------------------------------------------------------------
# Step 5: Extract visit cache
# ---------------------------------------------------------------------------

# Regex patterns for visit-relevant variable detection
_VISIT_DISCRIMINATOR_RE = [
    re.compile(r"^VISIT$", re.IGNORECASE),
    re.compile(r"^IDTYPE$", re.IGNORECASE),
    re.compile(r"VTYP$", re.IGNORECASE),
    re.compile(r"^visitnum$", re.IGNORECASE),
    re.compile(r"^phase_study$", re.IGNORECASE),
    re.compile(r"^visit_type$", re.IGNORECASE),
]

_AGE_RE = [
    re.compile(r"\bage\b", re.IGNORECASE),
    re.compile(r"^AGE", re.IGNORECASE),
    re.compile(r"AGE\d*$", re.IGNORECASE),
]

_DATE_DAYS_RE = [
    re.compile(r"\bDAYS?\b", re.IGNORECASE),
    re.compile(r"\bDATE\b", re.IGNORECASE),
    re.compile(r"^F\d+DAYS$", re.IGNORECASE),  # WHI: F80DAYS, etc.
]

_VISIT_DESC_RE = re.compile(
    r"visit\s*\d|exam\s*\d|baseline|follow.?up|phase\s*\d|year\s*\d",
    re.IGNORECASE,
)


def extract_visit_metadata(cohort_key: str) -> dict | None:
    """Extract visit-relevant metadata from FTP data dicts for one cohort.

    Returns a dict suitable for JSON serialization, or None if no data.
    """
    ftp_dir = CACHE_DIR / cohort_key / "pheno_variable_summaries"
    if not ftp_dir.is_dir():
        return None

    data_dict_files = sorted(ftp_dir.glob("*.data_dict.xml"))
    if not data_dict_files:
        return None

    tables: dict[str, dict] = {}

    for dd_file in data_dict_files:
        try:
            tree = ET.parse(dd_file)
        except ET.ParseError:
            continue

        root = tree.getroot()
        table_id_raw = root.get("id", "")
        base_pht = table_id_raw.split(".")[0]
        if not base_pht.startswith("pht"):
            continue

        # Table description
        desc_el = root.find(".//description")
        table_desc = desc_el.text.strip() if desc_el is not None and desc_el.text else ""

        discriminators = []
        age_vars = []
        date_days_vars = []
        participant_ids = []
        all_var_names = []

        for var_elem in root.iter("variable"):
            name_el = var_elem.find("name")
            if name_el is None or not name_el.text:
                continue
            vname = name_el.text.strip()
            all_var_names.append(vname)

            # Visit discriminators
            for pat in _VISIT_DISCRIMINATOR_RE:
                if pat.search(vname):
                    # Get coded values if any
                    codes = {}
                    for ve in var_elem.findall("value"):
                        code = ve.get("code", "")
                        label = (ve.text or "").strip()
                        if code:
                            codes[code] = label
                    phv_raw = var_elem.get("id", "")
                    base_phv = phv_raw.split(".")[0]
                    entry = {"name": vname, "phv": base_phv}
                    if codes:
                        entry["codes"] = codes
                    discriminators.append(entry)
                    break

            # Age variables
            for pat in _AGE_RE:
                if pat.search(vname):
                    phv_raw = var_elem.get("id", "")
                    age_vars.append({"name": vname, "phv": phv_raw.split(".")[0]})
                    break

            # Date/days variables
            for pat in _DATE_DAYS_RE:
                if pat.search(vname):
                    phv_raw = var_elem.get("id", "")
                    date_days_vars.append({"name": vname, "phv": phv_raw.split(".")[0]})
                    break

            # Participant IDs
            if vname.upper() in ("SUBJECT_ID", "SHAREID", "SUBJID", "PID", "ID",
                                  "RANID", "SID", "DBGAP_SUBJECT_ID"):
                phv_raw = var_elem.get("id", "")
                participant_ids.append({"name": vname, "phv": phv_raw.split(".")[0]})

        table_entry: dict = {
            "pht": base_pht,
            "n_variables": len(all_var_names),
        }
        if table_desc:
            table_entry["description"] = table_desc
        if discriminators:
            table_entry["visit_discriminators"] = discriminators
            table_entry["is_multi_visit"] = True
        if age_vars:
            table_entry["age_variables"] = age_vars
        if date_days_vars:
            table_entry["date_days_variables"] = date_days_vars
        if participant_ids:
            table_entry["participant_id_variables"] = participant_ids

        # Visit context clues
        table_entry["visit_context_in_name"] = bool(
            re.search(r"visit|exam|base|yr\d|phase|annual", base_pht, re.IGNORECASE)
            or re.search(r"visit|exam|base|yr\d|phase|annual", dd_file.stem, re.IGNORECASE)
        )
        table_entry["visit_context_in_desc"] = bool(
            _VISIT_DESC_RE.search(table_desc)
        ) if table_desc else False

        tables[base_pht] = table_entry

    if not tables:
        return None

    return {
        "cohort": cohort_key,
        "n_tables": len(tables),
        "n_multi_visit": sum(1 for t in tables.values() if t.get("is_multi_visit")),
        "tables": tables,
    }


def build_visit_cache(cohort_key: str) -> bool:
    """Extract visit metadata and write to dbgap-cache/<cohort>_visit.json."""
    metadata = extract_visit_metadata(cohort_key)
    if metadata is None:
        print(f"  [visit] No data for {cohort_key} -- skipping")
        return True

    dest = CACHE_DIR / f"{cohort_key}_visit.json"
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    n_multi = metadata["n_multi_visit"]
    print(
        f"  [visit] {cohort_key:12s}: {metadata['n_tables']} tables "
        f"({n_multi} multi-visit) -> {dest.name}"
    )
    return True


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def process_cohort(
    cohort_key: str,
    config: dict,
    *,
    fetch: bool = True,
    build: bool = True,
    force: bool = False,
    dry_run: bool = False,
) -> bool:
    """Process one cohort: fetch + build as requested."""
    study_id = config["study_id"]
    data_version = config["data_version"]
    display = config.get("display_name", cohort_key.upper())

    print(f"\n{'=' * 65}")
    print(f"  {display}")
    print(f"  {study_id}.{data_version}")
    print(f"{'=' * 65}")

    ok = True

    if fetch:
        # Step 1: CGI variable index
        if not fetch_cgi_index(cohort_key, study_id, data_version,
                               force=force, dry_run=dry_run):
            ok = False

        # Step 2: FTP data dictionaries
        if not fetch_ftp_data_dicts(cohort_key, study_id, data_version,
                                    force=force, dry_run=dry_run):
            ok = False

    if build and not dry_run:
        # Step 3: Basic PHV index
        build_phv_index(cohort_key)

        # Step 4: Detail PHV index
        build_phv_detail_index(cohort_key)

        # Step 5: Visit cache
        build_visit_cache(cohort_key)

    return ok


def print_summary() -> None:
    """Print summary of all cached data."""
    print(f"\n{'=' * 65}")
    print("  Cache Summary")
    print(f"{'=' * 65}")

    total_gz = 0
    total_xml = 0
    total_gz_bytes = 0
    total_xml_bytes = 0

    for item in sorted(CACHE_DIR.iterdir()):
        if item.is_file() and item.suffix == ".gz":
            total_gz += 1
            total_gz_bytes += item.stat().st_size
        elif item.is_dir():
            xmls = list(item.rglob("*.xml"))
            xml_bytes = sum(f.stat().st_size for f in xmls)
            total_xml += len(xmls)
            total_xml_bytes += xml_bytes
            print(f"  {item.name:15s}  {len(xmls):>5} XML files  ({xml_bytes // 1024:>8,} KB)")

    print(f"  {'-' * 50}")
    print(f"  Source XML:        {total_xml:>5} files  ({total_xml_bytes // 1024:>8,} KB)")
    print(f"  Compressed indexes:{total_gz:>5} files  ({total_gz_bytes // 1024:>8,} KB)")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch dbGaP source data and rebuild hv-lint indexes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full refresh (all cohorts):
  python hv-lint/update_data.py

  # Single cohort:
  python hv-lint/update_data.py --cohort aric

  # Just rebuild indexes from existing XML (no network):
  python hv-lint/update_data.py --build-only

  # Preview what would be downloaded:
  python hv-lint/update_data.py --dry-run --cohort mesa
""",
    )
    parser.add_argument("--cohort", metavar="KEY",
                        help="Process a single cohort (e.g. aric, mesa). Default: all.")
    parser.add_argument("--fetch-only", action="store_true",
                        help="Only fetch from NCBI, skip index building.")
    parser.add_argument("--build-only", action="store_true",
                        help="Only rebuild indexes from existing XML (no network).")
    parser.add_argument("--force", action="store_true",
                        help="Re-download even if cached locally.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without doing it.")
    parser.add_argument("--list", action="store_true",
                        help="List configured cohorts and exit.")
    parser.add_argument("--summary", action="store_true",
                        help="Print cache summary and exit.")
    args = parser.parse_args()

    if args.fetch_only and args.build_only:
        print("ERROR: --fetch-only and --build-only are mutually exclusive", file=sys.stderr)
        return 1

    cohorts = load_cohorts()

    if args.list:
        print("Configured cohorts:")
        for key, cfg in sorted(cohorts.items()):
            print(f"  {key:15s}  {cfg['study_id']}.{cfg['data_version']}  "
                  f"{cfg.get('display_name', '')}")
        return 0

    if args.summary:
        print_summary()
        return 0

    # Determine targets
    if args.cohort:
        if args.cohort not in cohorts:
            print(f"ERROR: Unknown cohort '{args.cohort}'. "
                  f"Known: {', '.join(sorted(cohorts))}", file=sys.stderr)
            return 1
        targets = {args.cohort: cohorts[args.cohort]}
    else:
        targets = cohorts

    do_fetch = not args.build_only
    do_build = not args.fetch_only

    mode_parts = []
    if do_fetch:
        mode_parts.append("FETCH")
    if do_build:
        mode_parts.append("BUILD")
    if args.dry_run:
        mode_parts.append("DRY-RUN")
    mode_str = " + ".join(mode_parts)

    print(f"[{mode_str}] Processing {len(targets)} cohort(s)")
    print(f"Cache directory: {CACHE_DIR}")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    results: dict[str, bool] = {}
    for key, config in sorted(targets.items()):
        results[key] = process_cohort(
            key, config,
            fetch=do_fetch,
            build=do_build,
            force=args.force,
            dry_run=args.dry_run,
        )

    print_summary()

    failures = [k for k, ok in results.items() if not ok]
    if failures:
        print(f"\nWARNING: {len(failures)} cohort(s) had errors: {', '.join(failures)}")
        return 1

    print(f"\nDone. {len(targets)} cohort(s) processed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
