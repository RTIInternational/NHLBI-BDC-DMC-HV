#!/usr/bin/env python3
"""
update_data.py -- Fetch dbGaP source data and rebuild lint indexes.

Single entry point for all dbGaP data maintenance in hv-lint. Performs:
  1. Fetch CGI variable index (variables.xml) from NCBI
  2. Fetch FTP data dictionaries (*.data_dict.xml) from NCBI FTP
  3. Build the PHV-to-PHT index, via build_phv_index.build_one
  4. Build the PHV detail index, via build_phv_detail_index.build_one

Steps 3 and 4 DELEGATE to those two builders rather than repeating them, so this
path and a direct builder invocation produce the same artifact: keyed by study
release (`phs000280.v8.json.gz`) and carrying the provenance the mandatory
release check requires. This script held its own pair until 2026-09-23; they read
only variables.xml and wrote `<cohort>.json.gz` with no provenance, so the
onboarding command below produced exactly the cache that check rejects.

There is no step 5. It extracted a visit cache by regex-guessing visit metadata;
Phase 5 checks 5.5 and 5.7 were its only readers and both were removed.

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
# Cohort version pins are sourced from the hv_dataqc cache-fetcher manifests,
# the single source of truth for dbGaP study versions across both tools.
MANIFESTS_DIR = HVLINT_DIR.parent / "hv_dataqc" / "cache_fetcher" / "manifests"
CACHE_DIR = HVLINT_DIR / "dbgap-cache"

# dbGaP stamps every FTP data dictionary `phs######.v#.pht######.v#.<name>.data_dict.xml`.
# Anchored, so a name merely containing an accession cannot match.
_DATA_DICT_PREFIX = re.compile(r"^phs\d{6}\.v\d+\.pht\d+\.v\d+\.")

FTP_BASE = "https://ftp.ncbi.nlm.nih.gov/dbgap/studies"
CGI_BASE = "https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin"
NCBI_DELAY_SECONDS = 0.5  # polite delay between real network requests


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------
def load_cohorts(manifests_dir: Path | None = None) -> dict[str, dict]:
    """Load cohort version pins from the hv_dataqc cache-fetcher manifests.

    Each ``_manifest-<key>.yaml`` carries a ``current_version`` block; that block
    is the single source of truth for the cohort's dbGaP study version, shared
    with the hv_dataqc compare pipeline so the two tools never drift.

    Returns dict mapping cohort key -> {study_id, data_version, display_name}.
    """
    import yaml  # deferred so --help works without pyyaml

    directory = manifests_dir or MANIFESTS_DIR
    if not directory.is_dir():
        print(f"ERROR: manifests dir not found at {directory}", file=sys.stderr)
        sys.exit(1)

    cohorts: dict[str, dict] = {}
    for path in sorted(directory.glob("_manifest-*.yaml")):
        key = path.stem[len("_manifest-"):]
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        current = (data or {}).get("current_version")
        if not isinstance(current, dict):
            print(f"ERROR: {path.name} missing 'current_version:' mapping", file=sys.stderr)
            sys.exit(1)
        study_id = current.get("study_id")
        data_version = current.get("data_version")
        if not study_id or not data_version:
            print(f"ERROR: {path.name} 'current_version' missing study_id/data_version",
                  file=sys.stderr)
            sys.exit(1)
        cohorts[key] = {
            "study_id": study_id,
            "data_version": data_version,
            "display_name": current.get("study_name", key.upper()),
        }

    if not cohorts:
        print(f"ERROR: no _manifest-*.yaml files found in {directory}", file=sys.stderr)
        sys.exit(1)
    return cohorts


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

    # `variables.xml` carries no release in its name, so a cached copy from the PREVIOUS
    # release looks identical to a current one. It is not inert: the PHV index merges it as a
    # supplement, which would fold a superseded release's PHVs into an artifact whose manifest
    # names the new one -- rebuilding, inside one file, the union cache this branch exists to
    # eliminate. The data dictionaries already on disk are what say which release this
    # directory currently holds, so they decide whether the cached copy is stale.
    if dest.exists() and not force and staged_release_differs(
        CACHE_DIR / cohort_key, study_id, data_version
    ):
        print("  [variables.xml] Cached copy is from a superseded release -- re-fetching")
        force = True

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
def staged_release_differs(cohort_dir: Path, study_id: str, data_version: str) -> bool:
    """True when the data dictionaries already staged name a release other than this one.

    False when the directory is empty, holds no parseable data dictionary, or already holds
    this release -- absence is never read as disagreement, so a first fetch is not treated as
    a version bump.
    """
    want = f"{study_id}.{data_version.split('.')[0]}."
    names = [
        p.name for p in (cohort_dir / "pheno_variable_summaries").glob("*.data_dict.xml")
        if _DATA_DICT_PREFIX.match(p.name)
    ]
    return bool(names) and any(not n.startswith(want) for n in names)


def retire_superseded_data_dicts(dest_dir: Path, study_id: str, data_version: str) -> int:
    """Remove data dictionaries from a release other than the one being fetched. Returns count.

    One staging directory per cohort is reused across version bumps, and the FTP fetch ADDS
    filenames rather than replacing them -- dbGaP stamps the release into each name, so a v9
    fetch over a v8 tree leaves both. `study_from_data_dicts` then sees two releases and
    refuses to choose (correctly: the directory genuinely has no single answer), so the
    documented update command cannot build the new cache at all. The bump this branch exists
    to support was the one operation that did not work.

    Only files whose `phs######.v#.` prefix names a DIFFERENT release are removed, so a
    re-fetch of the same release removes nothing, and a file that does not match the prefix
    pattern at all is left alone rather than guessed about.
    """
    want = f"{study_id}.{data_version.split('.')[0]}."
    stale = [
        p for p in sorted(dest_dir.glob("*.data_dict.xml"))
        if _DATA_DICT_PREFIX.match(p.name) and not p.name.startswith(want)
    ]
    for path in stale:
        path.unlink()
    if stale:
        print(f"  [FTP] Retired {len(stale)} data dictionaries from a superseded release "
              f"(keeping {want[:-1]})")
    return len(stale)


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
    retire_superseded_data_dicts(dest_dir, study_id, data_version)

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
        # Steps 3 and 4 delegate to the release-keyed builders rather than repeating them.
        # This script used to hold its own pair, reading only `variables.xml` and writing
        # `<cohort>.json.gz` with no provenance -- so the onboarding command MAINTENANCE.md
        # documents produced exactly the cache the mandatory release check rejects. The
        # builders read the data dictionaries fetched in step 2, which is where the
        # `phs######.v#` provenance comes from; `variables.xml` stays as their supplement.
        #
        # Step 5 built `<cohort>_visit.json` by regex-guessing visit metadata. Checks 5.5 and
        # 5.7 were its only readers and both were removed, so it is not built any more.
        # Deferred, matching this file's convention for its other cross-module imports:
        # --help must work without the builders' dependencies present.
        import _cohorts
        import build_phv_detail_index
        import build_phv_index

        cohort_dir = CACHE_DIR / cohort_key
        if not cohort_dir.is_dir():
            print(f"  ERROR: no staged source at {cohort_dir} -- fetch before building",
                  file=sys.stderr)
            return False
        entries: dict[str, dict] = {}
        for builder in (build_phv_index, build_phv_detail_index):
            entry = builder.build_one(cohort_dir, CACHE_DIR, CACHE_DIR)
            if entry and entry.get("study"):
                entries[f"{entry['study']}.{entry['study_version']}"] = entry
        if entries:
            _cohorts.write_manifest_entries(CACHE_DIR, entries)
        else:
            # Not a warning to bury: an index carrying no release fails the mandatory check at
            # lint time, far from here, and reads there as a cache problem rather than a build
            # one.
            print(f"  ERROR: {cohort_key}: built no release-keyed index -- the data "
                  f"dictionaries in {cohort_dir} name no single phs######.v#", file=sys.stderr)
            ok = False

    return ok


def print_summary() -> None:
    """Print summary of all cached data."""
    print(f"\n{'=' * 65}")
    print("  Cache Summary")
    print(f"{'=' * 65}")

    if not CACHE_DIR.is_dir():
        print(f"  Cache directory not found: {CACHE_DIR}")
        return

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
