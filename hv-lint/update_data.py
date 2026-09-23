#!/usr/bin/env python3
"""
update_data.py -- Fetch dbGaP source data and rebuild lint indexes.

Single entry point for all dbGaP data maintenance in hv-lint. Performs:
  1. Fetch FTP data dictionaries (*.data_dict.xml) from NCBI FTP
  2. Build the PHV-to-PHT index, via build_phv_index.build_one
  3. Build the PHV detail index, via build_phv_detail_index.build_one

Steps 2 and 3 DELEGATE to those two builders rather than repeating them, so this
path and a direct builder invocation produce the same artifact: keyed by study
release (`phs000280.v8.json.gz`) and carrying the provenance the mandatory
release check requires. This script held its own pair until 2026-09-23; they read
only variables.xml and wrote `<cohort>.json.gz` with no provenance, so the
onboarding command below produced exactly the cache that check rejects.

Two steps were removed. A visit cache was extracted by regex-guessing visit
metadata, and Phase 5 checks 5.5/5.7 were its only readers. The CGI
`variables.xml` bulk index was fetched as a supplement for the PHV index, and
carries no release -- so a copy left from an earlier one made the artifact a
union of releases, which is what keying by release exists to prevent.

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

    requests-cache is only needed for --fetch operations (step 1).
    --build-only requires only pyyaml and stdlib.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import shutil
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
# Step 1: Fetch FTP data dictionaries
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
        # Benign only for a study that genuinely has none. If a SUPERSEDED release is staged,
        # returning success here leaves it in place for the builders to index and
        # provenance-stamp as the release we asked for -- the update command reports success
        # and the contradiction surfaces at lint time, which is the wrong place for it.
        if staged_release_differs(CACHE_DIR / cohort_key, study_id, data_version):
            print(f"  [FTP] ...but a superseded release is staged for {cohort_key}. Refusing: "
                  f"the listing for {study_id}.{data_version} has no dictionaries to replace "
                  f"it with.", file=sys.stderr)
            return False
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
    if failed:
        # Retire NOTHING on a partial fetch. The new release's filenames differ from the old
        # one's, so both sets coexist harmlessly until the fetch completes -- whereas retiring
        # first and then failing destroys the only complete staging tree the cohort has, and
        # leaves a half-fetched release in its place. `study_from_data_dicts` refuses a
        # two-release directory, and `process_cohort` refuses to build after a failed fetch,
        # so the mixed state is reported rather than indexed.
        print("  [FTP] Fetch incomplete -- keeping the superseded release's data dictionaries",
              file=sys.stderr)
        return False
    retire_superseded_data_dicts(dest_dir, study_id, data_version)
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
        # The FTP data dictionaries are the only source fetched. The CGI `variables.xml` bulk
        # index was fetched alongside them until 2026-09-23 and is not any more: it fed one
        # consumer, the PHV index's supplement, and that was removed because a file carrying no
        # release cannot be allowed to contribute to a release-keyed artifact. Fetching it now
        # would write a file nothing reads -- which is exactly what made a stale copy hazardous
        # in the first place.
        if not fetch_ftp_data_dicts(cohort_key, study_id, data_version,
                                    force=force, dry_run=dry_run):
            ok = False

    if build and not dry_run and not ok:
        # A failed fetch must not be indexed. The builders read whatever is on disk and stamp
        # the release they find into the manifest, so building over a half-fetched tree
        # produces an index that CLAIMS a release it does not completely hold -- provenance it
        # has not earned, and indistinguishable at lint time from a complete one.
        print(f"  ERROR: {cohort_key}: fetch failed -- not building, because an index over a "
              f"partial tree would record a release it does not hold", file=sys.stderr)
        return False

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
        # BOTH builders must succeed, and NOTHING is published until both have. They are not
        # independent outputs: Phase 3's 3.9-3.16 and Phase 5's 5.8 read the detail index, and
        # a missing one is an ERROR at lint time by the guard in 69769543. Accepting either
        # builder's entry let a valid PHV mapping mask a wholly corrupt data-dictionary set,
        # because `variables.xml` alone can carry the PHV->PHT mapping.
        #
        # They build into a scratch directory and are moved into place together. Writing
        # straight into CACHE_DIR meant a failure of the SECOND builder still left the first's
        # freshly-written artifact behind -- and against an existing manifest entry from an
        # earlier successful build, that thinner index reads as a valid release-keyed cache.
        # `Path.replace` is atomic within a filesystem, and the scratch directory is a child of
        # the destination so that holds.
        entries: dict[str, dict] = {}
        missing: list[str] = []
        scratch = CACHE_DIR / f".build-{cohort_key}"
        shutil.rmtree(scratch, ignore_errors=True)
        scratch.mkdir(parents=True, exist_ok=True)
        try:
            for label, builder in (("PHV index", build_phv_index),
                                   ("detail index", build_phv_detail_index)):
                entry = builder.build_one(cohort_dir, scratch, CACHE_DIR)
                if entry and entry.get("study"):
                    entries[f"{entry['study']}.{entry['study_version']}"] = entry
                else:
                    missing.append(label)
            if missing:
                print(f"  ERROR: {cohort_key}: built no {' and no '.join(missing)} -- the data "
                      f"dictionaries in {cohort_dir} name no single phs######.v#, or parsed to "
                      f"zero records. Publishing nothing.", file=sys.stderr)
                ok = False
            else:
                for produced in sorted(scratch.glob("*.json.gz")):
                    produced.replace(CACHE_DIR / produced.name)
                _cohorts.write_manifest_entries(CACHE_DIR, entries)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

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
