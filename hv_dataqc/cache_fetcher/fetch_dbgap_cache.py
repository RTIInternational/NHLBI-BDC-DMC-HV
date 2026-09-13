#!/usr/bin/env python3
"""
fetch_dbgap_cache.py
--------------------
Self-contained downloader for dbGaP per-dataset data dictionaries
(``*.data_dict.xml``) and optional auxiliary files (``var_report.xml``,
``GapExchange_*.xml``).

The output layout matches what ``compare_source_harmonized.py`` expects
when its ``--cache-dir`` argument is supplied:

    <output-dir>/<cohort>/pheno_variable_summaries/*.data_dict.xml
    <output-dir>/<cohort>/GapExchange_<study>.xml      (optional)

Dependencies (Python 3.10+):
    pip install requests pyyaml

Usage:
    python fetch_dbgap_cache.py --list
    python fetch_dbgap_cache.py --cohort aric
    python fetch_dbgap_cache.py                          # all cohorts
    python fetch_dbgap_cache.py --cohort fhs --include-var-reports
    python fetch_dbgap_cache.py --cohort chs --include-gap-exchange
    python fetch_dbgap_cache.py --cohort aric --output-dir ./my-cache
    python fetch_dbgap_cache.py --dry-run --cohort mesa
    python fetch_dbgap_cache.py --summary

The version pinned for each cohort comes from ``manifests/_manifest-<key>.yaml``
sitting next to this script. Edit those files (or pass --force) if you need
to upgrade to a newer dbGaP release.
"""

from __future__ import annotations

import argparse
import sys
import time
from html.parser import HTMLParser
from pathlib import Path

import requests
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
MANIFEST_DIR = SCRIPT_DIR / "manifests"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "dbgap-cache"
FTP_BASE = "https://ftp.ncbi.nlm.nih.gov/dbgap/studies"
NCBI_DELAY_SECONDS = 0.5  # polite delay between real network requests
USER_AGENT = "BDC-DMC-HV-DataQC-Fetcher/1.0 (cache-fetcher; contact: bdc-dmc-hv@rti.org)"

# When True (set by --quiet), suppress progress chatter. Errors/warnings and
# the final summary always print. Used by the runners to keep the cache fetch
# from burying their own output.
_QUIET = False


def _say(msg: str) -> None:
    """Print progress chatter unless --quiet is in effect."""
    if not _QUIET:
        print(msg)


# ----------------------------------------------------------------------
# HTTP session

def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


_SESSION: requests.Session | None = None


def get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = make_session()
    return _SESSION


# ----------------------------------------------------------------------
# FTP directory listing parser

class FTPDirectoryParser(HTMLParser):
    """Extract href links from an FTP HTTPS directory listing page."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        for name, value in attrs:
            if name == "href" and value and not value.startswith("?") and not value.startswith("/"):
                self.links.append(value)


def list_ftp_directory(url: str) -> list[str]:
    resp = get_session().get(url, timeout=60)
    resp.raise_for_status()
    parser = FTPDirectoryParser()
    parser.feed(resp.text)
    return parser.links


# ----------------------------------------------------------------------
# Manifest helpers

def load_manifest(cohort_key: str) -> dict:
    path = MANIFEST_DIR / f"_manifest-{cohort_key}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No manifest found at {path}")
    with open(path) as f:
        return yaml.safe_load(f)


def discover_cohorts() -> list[str]:
    return sorted(
        p.stem.replace("_manifest-", "")
        for p in MANIFEST_DIR.glob("_manifest-*.yaml")
        if "template" not in p.stem
    )


def get_ftp_study_path(manifest: dict) -> str:
    cv = manifest.get("current_version", {})
    study_id = cv.get("study_id", "")
    data_version = cv.get("data_version", "")
    if not study_id or not data_version:
        raise ValueError("Manifest missing study_id or data_version")
    qualified = f"{study_id}.{data_version}"
    return f"{study_id}/{qualified}"


# ----------------------------------------------------------------------
# Download

def download_file(url: str, dest: Path, force: bool = False) -> tuple[bool, str]:
    if dest.exists() and not force:
        size_kb = dest.stat().st_size / 1024
        return True, f"already cached ({size_kb:,.1f} KB)"

    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        resp = get_session().get(url, timeout=120)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        size_kb = len(resp.content) / 1024
        return True, f"downloaded ({size_kb:,.1f} KB)"
    except Exception as exc:
        return False, f"FAILED: {exc}"


def fetch_pheno_variable_summaries(
    cohort_key: str,
    ftp_study_path: str,
    output_dir: Path,
    *,
    include_var_reports: bool = False,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    dir_url = f"{FTP_BASE}/{ftp_study_path}/pheno_variable_summaries/"
    _say(f"  Listing {dir_url}")

    try:
        entries = list_ftp_directory(dir_url)
    except Exception as exc:
        print(f"  ERROR listing directory: {exc}")
        return 0, 0, 1

    targets = [e for e in entries if e.endswith(".data_dict.xml")]
    if include_var_reports:
        targets += [e for e in entries if e.endswith(".var_report.xml")]
    targets = sorted(set(targets))

    if not targets:
        print(f"  No matching XML files found in directory ({len(entries)} total entries)")
        return 0, 0, 0

    dd_count = sum(1 for t in targets if t.endswith(".data_dict.xml"))
    vr_count = sum(1 for t in targets if t.endswith(".var_report.xml"))
    _say(f"  Found {dd_count} data_dict + {vr_count} var_report files")

    if dry_run:
        for fname in targets[:10]:
            print(f"    [dry-run] would fetch: {fname}")
        if len(targets) > 10:
            print(f"    ... and {len(targets) - 10} more")
        return 0, len(targets), 0

    dest_dir = output_dir / cohort_key / "pheno_variable_summaries"
    downloaded = skipped = failed = 0

    for i, fname in enumerate(targets, 1):
        url = f"{FTP_BASE}/{ftp_study_path}/pheno_variable_summaries/{fname}"
        dest = dest_dir / fname
        ok, msg = download_file(url, dest, force=force)
        if ok:
            if "already cached" in msg:
                skipped += 1
            else:
                downloaded += 1
                time.sleep(NCBI_DELAY_SECONDS)
        else:
            failed += 1
            print(f"    !! {fname}: {msg}")

        if i % 25 == 0 or i == len(targets):
            _say(f"    [{i}/{len(targets)}] {downloaded} new, {skipped} cached, {failed} failed")

    return downloaded, skipped, failed


def fetch_gap_exchange(
    cohort_key: str,
    ftp_study_path: str,
    output_dir: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    dir_url = f"{FTP_BASE}/{ftp_study_path}/"
    try:
        entries = list_ftp_directory(dir_url)
    except Exception as exc:
        print(f"  ERROR listing study root: {exc}")
        return 0, 0, 1

    gap_files = [e for e in entries if e.startswith("GapExchange_") and e.endswith(".xml")]
    if not gap_files:
        print("  No GapExchange XML found in study root")
        return 0, 0, 0

    fname = gap_files[0]
    print(f"  GapExchange: {fname}")

    if dry_run:
        print(f"    [dry-run] would fetch: {fname}")
        return 0, 1, 0

    url = f"{FTP_BASE}/{ftp_study_path}/{fname}"
    dest = output_dir / cohort_key / fname
    ok, msg = download_file(url, dest, force=force)
    if ok:
        print(f"    OK  {msg}")
        cached = "already cached" in msg
        return (0 if cached else 1, 1 if cached else 0, 0)
    print(f"    !! {msg}")
    return 0, 0, 1


# ----------------------------------------------------------------------
# Top-level orchestration

def fetch_cohort(
    cohort_key: str,
    output_dir: Path,
    *,
    include_var_reports: bool = False,
    include_gap_exchange: bool = False,
    force: bool = False,
    dry_run: bool = False,
) -> bool:
    _say(f"\n{'=' * 60}")
    _say(f"  Cohort: {cohort_key.upper()}")
    _say(f"{'=' * 60}")

    try:
        manifest = load_manifest(cohort_key)
        ftp_path = get_ftp_study_path(manifest)
    except (FileNotFoundError, ValueError) as e:
        print(f"  ERROR: {e}")
        return False

    _say(f"  FTP path: {FTP_BASE}/{ftp_path}/")

    dl, sk, fl = fetch_pheno_variable_summaries(
        cohort_key, ftp_path, output_dir,
        include_var_reports=include_var_reports,
        force=force,
        dry_run=dry_run,
    )
    _say(f"  Pheno summaries: {dl} downloaded, {sk} cached, {fl} failed")

    if include_gap_exchange:
        gdl, gsk, gfl = fetch_gap_exchange(
            cohort_key, ftp_path, output_dir, force=force, dry_run=dry_run,
        )
        _say(f"  GapExchange:    {gdl} downloaded, {gsk} cached, {gfl} failed")
        fl += gfl

    return fl == 0


def print_cache_summary(output_dir: Path) -> None:
    print(f"\n{'=' * 60}")
    print(f"  Cache Summary: {output_dir}")
    print(f"{'=' * 60}")
    if not output_dir.exists():
        print("  (output directory does not exist yet)")
        return

    total_files = 0
    total_bytes = 0
    for cohort_dir in sorted(output_dir.iterdir()):
        if not cohort_dir.is_dir():
            continue
        pvs_dir = cohort_dir / "pheno_variable_summaries"
        if not pvs_dir.exists():
            print(f"  {cohort_dir.name:<15}  (no pheno_variable_summaries)")
            continue
        dd = list(pvs_dir.glob("*.data_dict.xml"))
        vr = list(pvs_dir.glob("*.var_report.xml"))
        dd_b = sum(f.stat().st_size for f in dd)
        vr_b = sum(f.stat().st_size for f in vr)
        total_files += len(dd) + len(vr)
        total_bytes += dd_b + vr_b
        print(
            f"  {cohort_dir.name:<15}  "
            f"{len(dd):>4} data_dict ({dd_b // 1024:>6,} KB)  "
            f"{len(vr):>4} var_report ({vr_b // 1024:>6,} KB)"
        )

    print(f"  {'-' * 50}")
    print(f"  Total: {total_files} XML files, {total_bytes // 1024:,} KB")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--cohort", metavar="KEY", help="Fetch a single cohort.")
    parser.add_argument("--output-dir", metavar="DIR", default=str(DEFAULT_OUTPUT_DIR),
                        help=f"Where to write the cache (default: {DEFAULT_OUTPUT_DIR}).")
    parser.add_argument("--include-var-reports", action="store_true",
                        help="Also download var_report.xml (larger, has summary stats).")
    parser.add_argument("--include-gap-exchange", action="store_true",
                        help="Also download GapExchange study-level XML.")
    parser.add_argument("--force", action="store_true",
                        help="Re-download even if local file exists.")
    parser.add_argument("--dry-run", action="store_true",
                        help="List what would be downloaded without fetching.")
    parser.add_argument("--list", action="store_true",
                        help="List available cohort keys and exit.")
    parser.add_argument("--summary", action="store_true",
                        help="Print cache summary and exit.")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress per-file/per-cohort progress; keep warnings and the "
                             "final summary. Used by the report runners.")
    args = parser.parse_args()

    global _QUIET
    _QUIET = args.quiet

    output_dir = Path(args.output_dir).resolve()
    cohorts = discover_cohorts()

    if args.list:
        print("Available cohorts:", ", ".join(cohorts))
        return 0

    if args.summary:
        print_cache_summary(output_dir)
        return 0

    if args.cohort:
        cohort_key = args.cohort.lower()
        if cohort_key not in cohorts:
            print(f"ERROR: Unknown cohort '{args.cohort}'. Known: {', '.join(cohorts)}",
                  file=sys.stderr)
            return 1
        targets = [cohort_key]
    else:
        targets = cohorts

    mode = "DRY RUN" if args.dry_run else "LIVE"
    extras = []
    if args.include_var_reports:
        extras.append("var_reports")
    if args.include_gap_exchange:
        extras.append("gap_exchange")
    extra_str = f" (+{', '.join(extras)})" if extras else ""
    print(f"[{mode}] Output: {output_dir}")
    print(f"[{mode}] Fetching dbGaP cache{extra_str} for: {', '.join(targets)}")

    all_ok = True
    for cohort in targets:
        ok = fetch_cohort(
            cohort, output_dir,
            include_var_reports=args.include_var_reports,
            include_gap_exchange=args.include_gap_exchange,
            force=args.force,
            dry_run=args.dry_run,
        )
        if not ok:
            all_ok = False

    if not args.dry_run:
        print_cache_summary(output_dir)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
