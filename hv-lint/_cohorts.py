"""Cohort identity and dbGaP cache resolution for HV-Lint -- one resolver for all phases.

Resolves a ``--cohort`` token to three things:

* **cache key** -- the ``dbgap-cache/<key>.json.gz`` stem, normally the cohort's DECLARED
  release (``phs000280.v8``), so several releases of one study coexist. Legacy cohort-named keys
  and the lower-cased token follow as fallbacks, which is what lets a cohort nobody registered
  still resolve, so onboarding a study needs no edit here.
* **canonical casing** -- the casing its ``<COHORT>-ingest`` directory uses. Not cosmetic: the
  token is joined onto a path, so ``COPDGENE-ingest`` resolves on a case-insensitive filesystem
  and not on CI's ubuntu runner.
* **study provenance** -- the ``phs######`` accession and ``v#`` version recorded in
  ``dbgap-cache/manifest.json`` by the two builders, which read it from the
  ``phs######.v#.pht######.v#.`` prefix dbGaP stamps on every ``*.data_dict.xml``.

Provenance matters because a cache payload is a bare ``{phv: pht}`` mapping with no metadata, and
Phase 3 validates spec PHVs against it: a cache built from a superseded release reports PHVs that
exist only in the newer release as absent, which is indistinguishable from a real mapping error.
:func:`study_label` reports it; ``--expect-study`` enforces it.

**Absence is reported, never inferred.** Entries are written only by a builder that read the
source, so nothing here guesses a version from a filename; a cache with no entry reports
``PROVENANCE UNKNOWN`` and fails any pin.

``all`` is derived from ``*-ingest/`` directories (:func:`ingest_cohorts`) -- the same way the CI
workflow derives it from a PR's changed paths. A cohort with a cache but no ingest directory is
NOT in ``all``: it has no specs to check, so it can only contribute a failure.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path

MANIFEST_NAME = "manifest.json"
MANIFEST_VERSION = 1

#: Alternative spellings of one cohort. **This is the fetch-manifest filename bridge, not a
#: cache-key bridge** -- it bridged cohort to cache key before artifacts were named by release
#: (``hchs_sol.json.gz``), and that job is gone.
#:
#: What still needs it: HCHS/SOL's ingest directory and its version declaration disagree, and
#: both are outside this module --
#:
#:     priority_variables_transform/HCHS-ingest          -> --cohort HCHS
#:     hv_dataqc/.../manifests/_manifest-hchs_sol.yaml   -> the declared release
#:
#: so :func:`declared_study` cannot find ``HCHS``'s declaration without this. Renaming that
#: manifest would remove the need, but ``update_data.py`` derives its cohort key FROM that
#: filename, and `fetch_dbgap_cache.py` and `validate_ingest_yamls.py` use the same key.
#:
#: Secondary use: :func:`candidate_keys` still offers the alias as a legacy cache key, for a
#: cache built before the release rename.
ALIASES: dict[str, str] = {
    "HCHS": "hchs_sol",
    "HCHS-SOL": "hchs_sol",
    "HCHS_SOL": "hchs_sol",
}

#: dbGaP stamps every FTP data dictionary ``phs######.v#.pht######.v#.<name>.data_dict.xml``.
#: Anchored, so a name merely containing an accession cannot match.
_DATA_DICT_RE = re.compile(r"^(phs\d{6})\.(v\d+)\.(pht\d+)\.(v\d+)\.")


def _squash(text: str) -> str:
    """Fold a token for comparison: lower-case, separators removed (``HCHS-SOL`` -> ``hchssol``).

    Needed because the cache key comes from a source DIRECTORY name and staging trees disagree
    on the separator (``hchs_sol`` vs ``hchs-sol``) for the same study.
    """
    return "".join(ch for ch in (text or "").lower() if ch.isalnum())


#: A staging directory may carry the release in its NAME (``aric-v8``, ``fhs-v33``) so several
#: releases can be staged at once. That suffix is not part of the cohort's identity.
_DIR_VERSION_SUFFIX = re.compile(r"[-_]v\d+(?:\.p\d+)?$", re.IGNORECASE)


def _staging_pipeline_cohort(source_cache: Path | str, dir_name: str) -> str | None:
    """The cohort slug the AI-harmonization pipeline recorded for ``dir_name``, or ``None``.

    That pipeline stages dbGaP metadata under ``data/dbgap/<accession>/`` (its `RunOutputs`
    counterpart for the source cache) and writes a SIBLING ``manifest.json`` --
    ``{"entries": {"<accession>": {"cohort": "<slug>", "fetched": ...}}}`` -- recording which
    cohort slug each accession-named directory holds. That is the only place this answer lives:
    a bare accession (``phs000284.v2.p1``) carries no cohort token a regex can recover, unlike
    the legacy ``<cohort>[-_]v#`` staging convention :func:`cohort_from_source_dir` was written
    against.

    Distinct from THIS module's own ``dbgap-cache/manifest.json`` (:func:`read_manifest` /
    :func:`write_manifest_entries`), which lives in the HV clone, is keyed by STUDY RELEASE, and
    is only ever correct here because THIS function fixed what gets written into its ``cohort``
    field in the first place. Returns ``None`` -- never a guess -- when the file is absent,
    unreadable, or silent on this exact directory name, so callers fall back to the name-derived
    rule unchanged.
    """
    path = Path(source_cache) / "manifest.json"
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    entries = data.get("entries")
    entry = entries.get(dir_name) if isinstance(entries, dict) else None
    cohort = entry.get("cohort") if isinstance(entry, dict) else None
    return str(cohort) if cohort else None


def cohort_from_source_dir(name: str, source_cache: Path | str | None = None) -> str:
    """``aric-v8`` -> ``ARIC``; ``hchs-sol`` -> ``HCHS``; ``ltrc`` -> ``LTRC``.

    The cohort a staging directory holds, independent of which release it holds. Recorded in the
    manifest so a lookup by cohort works regardless of how the directory was named -- without it,
    a cache built from ``aric-v8`` records the cohort as ``ARIC-V8`` and no ARIC lookup finds it.

    ``source_cache``, when given, is checked FIRST via :func:`_staging_pipeline_cohort` --
    measured 2026-09-16 against a real ``data/dbgap/phs000284.v2.p1/`` directory: the name-derived
    rule below has no ``-v#``/``_v#`` suffix to strip there (the separator right before the
    version token is ``.``, not ``-``/``_``), so it returned the accession itself, upper-cased,
    as the "cohort" -- silently correct-shaped and wrong, and on a rebuild of an ALREADY-staged
    cohort (COPDGene, staged as ``phs000179.v7.p2/`` the same day) it overwrites a previously
    correct manifest entry rather than merely failing to add one. Falls back to the name-derived
    guess when ``source_cache`` is omitted, the sidecar is absent, or it is silent on this
    directory -- every existing caller and cache stay exactly as before.
    """
    if source_cache is not None:
        mapped = _staging_pipeline_cohort(source_cache, (name or "").strip())
        if mapped:
            return mapped.upper()
    stem = _DIR_VERSION_SUFFIX.sub("", (name or "").strip())
    # Fold the HCHS/SOL spellings onto the ingest stem the HV repo uses.
    if _squash(stem) == _squash("hchs_sol"):
        return "HCHS"
    return stem.upper()


def candidate_keys(
    cohort: str, cache_dir: Path | str | None = None, hv_root: Path | str | None = None
) -> list[str]:
    """Cache keys to try for ``cohort``, best first, without checking existence.

    The DECLARED release comes first: artifacts are named ``<phs######>.<v#>``, so several
    releases of one study coexist and the cohort's declaration is what picks between them.
    Legacy cohort-named keys follow, so caches built before the rename still resolve.
    """
    token = (cohort or "").strip()
    cands: list[str] = []
    # `cache_dir` is passed through because the declaration lives in the real HV clone, which a
    # caller linting a STAGED tree can only reach via the cache path.
    declared = declared_study(token, hv_root, cache_dir)
    if declared:
        cands.append(declared)
    if cache_dir:
        # A manifest entry naming this cohort, but ONLY when it is unambiguous. Artifacts are
        # keyed by release, so a study with two staged releases has two entries carrying the
        # same cohort -- appending both silently picked whichever sorted first, which resolved
        # LTRC to phs001662.v2 against a declared v4. Ambiguity must fail loudly instead.
        matches = [key for key, entry in read_manifest(cache_dir).items()
                   if _squash(entry.get("cohort", "")) == _squash(token)]
        if len(matches) == 1:
            cands.append(matches[0])
    alias = ALIASES.get(token.upper())
    if alias:
        cands.append(alias)
    low = token.lower()
    cands += [low, low.replace("-", "_"), low.replace("_", "-")]
    seen: set[str] = set()
    return [c for c in cands if c and not (c in seen or seen.add(c))]


#: Where each cohort declares the dbGaP release it is harmonized against. This is the
#: authority for "which version should we be linting", and it is the file a version bump edits.
_FETCH_MANIFESTS = ("hv_dataqc", "cache_fetcher", "manifests")

_STUDY_ID_RE = re.compile(r'^\s*study_id:\s*"?(phs\d{6})"?', re.MULTILINE)
_DATA_VERSION_RE = re.compile(r'^\s*data_version:\s*"?(v\d+)', re.MULTILINE)


def _hv_root() -> Path | None:
    try:
        from _paths import find_transform_dir
        return Path(find_transform_dir()).parent
    except Exception:  # noqa: BLE001 -- no checkout to consult
        return None


def declared_study(
    cohort: str, hv_root: Path | str | None = None, cache_dir: Path | str | None = None
) -> str | None:
    """The release ``cohort`` is DECLARED to be harmonized against, e.g. ``phs000280.v8``.

    Read from ``hv_dataqc/cache_fetcher/manifests/_manifest-<cohort>.yaml`` (`current_version`),
    which is the file a version bump already edits. ``data_version`` there carries the participant
    set too (``v8.p2``); only the study version is returned, because that is what the cache
    artifacts are keyed by.

    ``None`` means the cohort declares nothing -- which callers must treat as a hard failure
    rather than a default, since "lint against whatever cache happens to be present" is how a
    superseded release goes unnoticed.
    """
    # Candidate roots, in order. The CACHE directory matters as much as the transform tree:
    # a caller that lints STAGED output points --hv-root at a temporary tree holding only
    # `<COHORT>-ingest`, which has no `hv_dataqc/` manifests -- so resolving the root from the
    # transform dir alone made the mandatory release check fail for every staged run, which is
    # how the AI-harmonization pipeline always invokes HV-Lint. The cache directory is in the
    # real clone (`<hv>/hv-lint/dbgap-cache`), so its grandparent gets there.
    roots: list[Path] = []
    for cand in (Path(hv_root) if hv_root else _hv_root(), ):
        if cand is not None:
            roots.append(Path(cand))
    if cache_dir:
        cd = Path(cache_dir).resolve()
        roots.extend(parent for parent in cd.parents if (parent / _FETCH_MANIFESTS[0]).is_dir())
    base = next(
        (r.joinpath(*_FETCH_MANIFESTS) for r in roots if r.joinpath(*_FETCH_MANIFESTS).is_dir()),
        None,
    )
    if base is None:
        return None
    want = _squash(cohort)
    for path in sorted(base.glob("_manifest-*.yaml")):
        name = path.name[len("_manifest-"):-len(".yaml")]
        if _squash(name) != want and _squash(ALIASES.get(cohort.upper(), "")) != _squash(name):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        sid = _STUDY_ID_RE.search(text)
        ver = _DATA_VERSION_RE.search(text)
        if sid and ver:
            return f"{sid.group(1)}.{ver.group(1)}"
        return None
    return None


def cache_key_for(
    cohort: str, cache_dir: Path | str | None = None, hv_root: Path | str | None = None
) -> str:
    """A cohort token -> its cache key (the ``<key>.json.gz`` stem).

    When ``cache_dir`` is given, the first candidate that actually has a cache file wins;
    otherwise the first candidate is returned. See the module docstring for the order.
    """
    cands = candidate_keys(cohort, cache_dir, hv_root)
    if cache_dir:
        base = Path(cache_dir)
        for cand in cands:
            if (base / f"{cand}.json.gz").is_file() or (base / f"{cand}_detail.json.gz").is_file():
                return cand
    return cands[0] if cands else (cohort or "").strip().lower()


def canonical_cohort(cohort: str, transform_dir: Path | str | None = None) -> str:
    """``copdgene`` / ``COPDGENE`` -> ``COPDGene`` -- the casing the ingest DIRECTORY uses.

    Falls back to the token unchanged when no directory matches, so an as-yet-unstaged cohort is
    passed through rather than rejected.
    """
    if transform_dir is None:
        try:
            from _paths import find_transform_dir
            transform_dir = find_transform_dir()
        except Exception:  # noqa: BLE001 -- no tree to consult; the token is the best answer
            return cohort
    want = _squash(cohort)
    for name in ingest_cohorts(transform_dir):
        if _squash(name) == want:
            return name
    return cohort


def cohorts_to_load(
    cohort: str, cache_dir: Path | str, transform_dir: Path | str | None = None
) -> list[tuple[str, str]]:
    """``[(cohort_name, cache_key)]`` for a ``--cohort`` argument. **Never silently empty.**

    A named cohort always yields exactly one pair, so a caller that cannot load it can name the
    cohort and the file it looked for instead of reporting a generic "no indexes found".

    ``all`` means **every cohort with an ``<COHORT>-ingest`` directory** -- the specs are what a
    lint run checks, so a cohort with none contributes no files and can only contribute a
    failure. The manifest is consulted only when the tree holds no ingest directory at all,
    which keeps a caller that points at something other than a spec tree from resolving to
    nothing. Adding manifest cohorts to a tree that HAS ingest directories is what let one cache
    artifact for an unregistered study (``phs000284.v2``, staged ahead of its ingest directory)
    abort the whole enforced Phase 3 gate on the mandatory release check, before a single spec
    file was read.
    """
    token = (cohort or "").strip()
    if token.lower() != "all":
        return [(token, cache_key_for(token, cache_dir))]
    names: list[str] = list(ingest_cohorts(transform_dir)) if transform_dir else []
    if not names:
        for entry in read_manifest(cache_dir).values():
            name = str(entry.get("cohort") or "")
            if name and not any(_squash(name) == _squash(n) for n in names):
                names.append(name)
    return [(n, cache_key_for(n, cache_dir)) for n in sorted(names)]


def study_from_data_dicts(cohort_dir: Path) -> tuple[str | None, str | None, int]:
    """``(accession, version, files_seen)`` read from a source directory's data dictionaries.

    Returns ``(None, None, n)`` when no data dictionary parses, and **refuses to choose** when
    more than one accession/version pair is present: a directory holding ``phs001662.v2.*`` and
    ``phs001662.v4.*`` together has no single answer, and picking the higher number would invent
    a provenance the directory does not have.
    """
    ftp_dir = cohort_dir / "pheno_variable_summaries"
    if not ftp_dir.is_dir():
        return None, None, 0
    pairs: set[tuple[str, str]] = set()
    seen = 0
    for dd in sorted(ftp_dir.glob("*.data_dict.xml")):
        m = _DATA_DICT_RE.match(dd.name)
        if m:
            seen += 1
            pairs.add((m.group(1), m.group(2)))
    if len(pairs) != 1:
        return None, None, seen
    accession, version = next(iter(pairs))
    return accession, version, seen


def manifest_path(cache_dir: Path | str) -> Path:
    return Path(cache_dir) / MANIFEST_NAME


def read_manifest(cache_dir: Path | str) -> dict[str, dict]:
    """The manifest's ``entries`` map, or ``{}`` when absent or unreadable.

    Unreadable is deliberately the same as absent: a corrupt manifest must degrade to "provenance
    unknown" (which callers report loudly) rather than abort a lint run that can still check
    everything else.
    """
    path = manifest_path(cache_dir)
    if not path.is_file():
        return {}
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    entries = data.get("entries")
    if not isinstance(entries, dict):
        return {}
    # Each VALUE must be a mapping too, not just the container. Callers do `entry.get(...)`,
    # so a hand-edited manifest holding a null or a bare string raises AttributeError and
    # aborts the lint run -- the opposite of the degradation this function promises above.
    return {key: entry for key, entry in entries.items() if isinstance(entry, dict)}


def write_manifest_entries(cache_dir: Path | str, entries: dict[str, dict]) -> Path:
    """Merge ``entries`` into the manifest and write it, returning the path.

    Merges rather than replaces so building one cohort's index does not erase the provenance of
    the others -- the builders are routinely run over a source cache holding a subset.
    """
    path = manifest_path(cache_dir)
    merged = read_manifest(cache_dir)
    # Field-wise, not entry-wise: `build_phv_index.py`, `build_phv_detail_index.py` and
    # `build_visit_index.py` each contribute different fields for the SAME key, and a whole-entry
    # replace would make whichever ran last erase the others' counts.
    for key, entry in entries.items():
        combined = dict(merged.get(key) or {})
        combined.update(entry)
        merged[key] = combined
    payload = {
        "manifest_version": MANIFEST_VERSION,
        "updated": _dt.datetime.now(tz=_dt.UTC).date().isoformat(),
        "entries": dict(sorted(merged.items())),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=False)
        f.write("\n")
    return path


def manifest_entry(cache_dir: Path | str, cache_key: str) -> dict | None:
    """One cache key's provenance entry, or ``None`` when it has none."""
    return read_manifest(cache_dir).get(cache_key)


def study_label(cache_dir: Path | str, cache_key: str) -> str:
    """A short provenance string for a log line -- the accession+version, or a loud UNKNOWN.

    Callers print this next to the PHV count so a reader can tell what the counts were validated
    against. ``PROVENANCE UNKNOWN`` is not padding: it means the cache predates the manifest and
    nothing records its study version, so a version-specific finding from it cannot be trusted.
    """
    entry = manifest_entry(cache_dir, cache_key)
    if not entry:
        return "PROVENANCE UNKNOWN -- rebuild with build_phv_index.py to record phs#+version"
    study = entry.get("study") or "phs?"
    version = entry.get("study_version") or "v?"
    built = entry.get("built")
    return f"{study}.{version}" + (f", built {built}" if built else "")


def study_mismatch(cache_dir: Path | str, cache_key: str, expect: str) -> str | None:
    """A message when the cache's recorded study does not match ``expect``, else ``None``.

    ``expect`` accepts ``phs001662`` or ``phs001662.v4``; a bare accession ignores the version.
    An UNRECORDED provenance is a mismatch, not a pass -- pinning a version against a cache that
    cannot say which version it holds is exactly the case the pin exists to catch.
    """
    want = (expect or "").strip()
    if not want:
        return None
    entry = manifest_entry(cache_dir, cache_key)
    if not entry:
        return (f"cache '{cache_key}' has no recorded study provenance, so --expect-study "
                f"{want} cannot be verified; rebuild it with build_phv_index.py")
    got_study = str(entry.get("study") or "")
    got_full = f"{got_study}.{entry.get('study_version') or ''}".rstrip(".")
    got = got_study if "." not in want else got_full
    if got != want:
        return f"cache '{cache_key}' was built from {got_full or 'an unrecorded study'}, not {want}"
    return None


def discover_cache_keys(cache_dir: Path | str) -> list[str]:
    """Every cache key present in ``cache_dir``, from the ``*.json.gz`` files themselves.

    Detail indexes (``<key>_detail.json.gz``) are folded onto their base key, so a cohort with
    both files appears once.
    """
    keys: set[str] = set()
    for path in Path(cache_dir).glob("*.json.gz"):
        stem = path.name[: -len(".json.gz")]
        keys.add(stem[: -len("_detail")] if stem.endswith("_detail") else stem)
    return sorted(keys)


def ingest_cohorts(transform_dir: Path | str) -> list[str]:
    """Every cohort with an ``<COHORT>-ingest`` directory, from the directories themselves.

    This is the set CI already derives by ``sed`` from a PR's changed paths, computed the same way
    from the tree instead of from a diff, so ``--cohort all`` can cover a cohort nobody has added
    to a list.
    """
    base = Path(transform_dir)
    if not base.is_dir():
        return []
    return sorted(
        d.name[: -len("-ingest")] for d in base.iterdir()
        if d.is_dir() and d.name.endswith("-ingest")
    )
