#!/usr/bin/env python3
"""Look up the best-matching MONDO term for a condition description via the EBI OLS4 API.

Endpoint: GET https://www.ebi.ac.uk/ols4/api/search?ontology=mondo&q={query}

Matching strategy (single pass + client-side re-ranking):
  OLS4's own exact=true does substring matching, not true exact matching, so
  all ranking is done client-side after fetching up to 100 candidates:
    - Exact label match      → 1.00
    - Exact synonym match    → 0.95
    - Otherwise              → difflib ratio * length_factor^0.4
  where length_factor = len(query) / max(len(query), len(label))
  This penalises overly specific labels (e.g. "renal hypertension" over
  "essential hypertension" for the query "hypertension").

Note: MONDO has no concept labelled simply "hypertension"; the closest general
clinical term is MONDO:0001134 (essential hypertension). For highly ambiguous
short queries, passing a fuller variable description (e.g. "history of
hypertension") will improve accuracy.

Usage examples:
    python mondo_agent.py "type 2 diabetes"
    python mondo_agent.py "hypertension" --id-only
    python mondo_agent.py "myocardial infarction" --all
"""

import json
import os
import re
import sys
import threading
import time
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote

import click
import requests

OLS4_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"

# ---------------------------------------------------------------------------
# Local response cache (2026-08-27) — OLS4 is a live, occasionally flaky
# endpoint, and this fleet re-asks the same handful of clinical terms
# ("hypertension", "diabetes", "asthma", ...) across many cohorts. Cache raw
# API responses locally, keyed by the exact query actually sent, so a repeat
# query never touches the network again. Kept out of git (see .gitignore) —
# same treatment as the loinc2omop.* files: local-only, not redistributed.
# ---------------------------------------------------------------------------
_CACHE_PATH = Path(__file__).parent.parent / "bdc_study_input" / "terminology-cache" / "mondo-index.json"
_cache: dict[str, list[dict]] | None = None
# generate_curie_mapreview.py drives this agent through a ThreadPoolExecutor
# (10 workers by default) -- guards the read-modify-write-replace cycle below
# against two races reported 2026-08-28: json.dumps() iterating the shared
# _cache dict while another thread mutates it, and every thread writing the
# same fixed tmp path before os.replace, so one thread's rename could pull
# the file out from under another's (reproduced as FileNotFoundError in
# ~48% of concurrent calls). Reads elsewhere (the `key in cache` check in
# _fetch_docs) stay unlocked -- a plain dict lookup can't corrupt state, and
# a stale miss just costs a redundant fetch, never wrong data. RLock (not
# Lock) because _save_cache_entry holds the lock while calling _load_cache(),
# which also acquires it -- same thread re-entering, which a plain Lock
# would deadlock on.
_cache_lock = threading.RLock()


def _cache_key(query: str, rows: int) -> str:
    return f"{rows}|{query.strip().lower()}"


def _load_cache() -> dict[str, list[dict]]:
    global _cache
    if _cache is not None:
        return _cache
    # Only the first call per process actually touches disk (subsequent
    # calls short-circuit above) -- but on Windows, os.replace() in
    # _save_cache_entry can raise PermissionError if another thread has the
    # destination file open for reading at that exact moment (unlike POSIX,
    # which allows atomic replace of an open file). With 10 concurrent
    # workers, several can race to do that first disk read simultaneously,
    # so it shares the same lock as the write path.
    with _cache_lock:
        if _cache is None:
            if _CACHE_PATH.exists():
                try:
                    _cache = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    _cache = {}
            else:
                _cache = {}
    return _cache


def _save_cache_entry(key: str, docs: list[dict]) -> None:
    with _cache_lock:
        cache = _load_cache()
        cache[key] = docs
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = _CACHE_PATH.with_suffix(f".tmp.{threading.get_ident()}.json")
        tmp_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
        # os.replace() can still transiently raise PermissionError on Windows
        # even with zero contention from our own threads (the lock above
        # already serializes those) -- something external (AV real-time
        # scanning, a search indexer, a backup/sync agent) can briefly hold
        # its own open handle on a just-written file. A short retry is the
        # standard, pragmatic mitigation for this well-known Windows quirk.
        for attempt in range(5):
            try:
                os.replace(tmp_path, _CACHE_PATH)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05 * (attempt + 1))

# Survey-language phrases that precede or follow a clinical term.
# Pattern: "<ClinicalTerm>: <SurveyPhrase>" or "<SurveyPhrase> <ClinicalTerm>"
_SURVEY_PHRASES_RE = re.compile(
    r":\s*(have you ever had|have you ever been|at about what age did|"
    r"do you currently|do you have|did you have|has a doctor ever told you|"
    r"at what age did|when did|how long have you had|please indicate).*",
    re.IGNORECASE,
)
# Strip trailing parenthetical clarifiers  e.g. "(in legs or lungs)", "(MI)"
_PAREN_SUFFIX_RE = re.compile(r"\s*\([^)]{4,}\)\s*$")


def _extract_clinical_term(description: str) -> str:
    """Return the core clinical term from a survey-style variable description.

    Examples:
        "Emphysema: Have you ever had emphysema"  -> "Emphysema"
        "Asthma: At about what age did asthma start" -> "Asthma"
        "Heart attack (MI)"                          -> "Heart attack (MI)"
        "Blood clots (in legs or lungs)"             -> "Blood clots"
    """
    # Remove survey phrases that follow a colon
    cleaned = _SURVEY_PHRASES_RE.sub("", description).strip().rstrip(":")
    # Remove long parenthetical suffixes (keep short ones like "(MI)")
    cleaned = _PAREN_SUFFIX_RE.sub("", cleaned).strip()
    return cleaned if cleaned else description


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_mondo_id(doc: dict) -> str | None:
    """Return the MONDO:XXXXXXX string from a doc, or None if not a MONDO term."""
    obo_id = doc.get("obo_id", "")
    if obo_id.startswith("MONDO:"):
        return obo_id
    short_form = doc.get("short_form", "")
    if short_form.startswith("MONDO_"):
        return short_form.replace("MONDO_", "MONDO:", 1)
    return None


def _similarity(query: str, concept: dict) -> float:
    """Composite similarity score between *query* and a concept dict.

    Priority:
      1.00  exact label match
      0.95  exact synonym match
      else  difflib ratio normalised by label length (penalises over-specific labels)
    """
    q = query.lower()
    label = concept["label"].lower()
    synonyms = [s.lower() for s in concept["exact_synonyms"]]

    if q == label:
        return 1.0
    if q in synonyms:
        return 0.95

    candidates = [label] + synonyms
    raw = max(SequenceMatcher(None, q, c).ratio() for c in candidates if c)
    # Normalise: penalise labels that are much longer than the query
    length_factor = len(q) / max(len(q), len(label))
    return raw * (length_factor ** 0.4)


def _fetch_docs(query: str, *, rows: int) -> list[dict]:
    """Call OLS4 and return raw docs for MONDO concepts only.

    Checks the local response cache first (see _CACHE_PATH) — a repeat query
    never touches the network. Only successful responses are cached; a
    network/HTTP error is never written, so a transient failure doesn't
    poison future lookups.
    """
    key = _cache_key(query, rows)
    cache = _load_cache()
    if key in cache:
        return cache[key]

    url = f"{OLS4_SEARCH_URL}?ontology=mondo&q={quote(query)}&rows={rows}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    docs = resp.json().get("response", {}).get("docs", [])
    _save_cache_entry(key, docs)
    return docs


def _docs_to_concepts(docs: list[dict]) -> list[dict]:
    """Convert raw API docs to cleaned concept dicts, dropping non-MONDO entries."""
    concepts = []
    for doc in docs:
        mondo_id = _extract_mondo_id(doc)
        if mondo_id is None:
            continue
        concepts.append(
            {
                "mondo_id": mondo_id,
                "label": doc.get("label", ""),
                "description": (doc.get("description") or [""])[0],
                "exact_synonyms": doc.get("exact_synonyms", []),
            }
        )
    return concepts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def search_mondo_terms(
    description: str,
    *,
    rows: int = 100,
) -> list[dict]:
    """Return MONDO concepts for *description*, best match first.

    Single search pass — fetches up to *rows* candidates from OLS4, then
    re-ranks client-side by composite similarity score:

      1.00  exact label match (case-insensitive)
      0.95  exact synonym match (case-insensitive)
      else  difflib ratio * length_factor^0.4  (penalises over-specific labels)

    Note: OLS4's own ``exact=true`` parameter does substring matching, not true
    exact matching, so exact-match detection is performed client-side here.

    Args:
        description: Free-text condition label from a study file.
        rows: Max candidates to fetch from OLS4.

    Returns:
        List of concept dicts (mondo_id, label, description, exact_synonyms),
        best match first.
    """
    concepts = _docs_to_concepts(_fetch_docs(description, rows=rows))
    concepts.sort(key=lambda c: _similarity(description, c), reverse=True)
    return concepts


def get_mondo_id(description: str, **kwargs) -> str | None:
    """Return only the top MONDO ID string, with multi-pass query cleaning.

    Pass 1: search with full description as-is.
    Pass 2: if no results, search with the extracted clinical term
            (strips survey-style preamble like "Have you ever had…").

    Example:
        >>> get_mondo_id("type 2 diabetes")
        'MONDO:0005148'
        >>> get_mondo_id("Emphysema: Have you ever had emphysema")
        'MONDO:0004849'
    """
    mondo_id, _score = get_mondo_id_with_score(description, **kwargs)
    return mondo_id


def get_mondo_id_with_score(description: str, **kwargs) -> tuple[str | None, float]:
    """Like get_mondo_id, but also returns the top match's similarity score.

    The score is the same composite label/synonym similarity used to rank
    candidates in search_mondo_terms — a text-match confidence, not a
    guarantee of ontological correctness. Callers can bucket it into
    curator-facing confidence tiers or compare it against another vocabulary's
    score to pick a priority_curie (see generate_curie_mapreview.py).
    """
    results = search_mondo_terms(description, **kwargs)
    if results:
        return results[0]["mondo_id"], _similarity(description, results[0])

    cleaned = _extract_clinical_term(description)
    if cleaned.lower() != description.lower():
        results2 = search_mondo_terms(cleaned, **kwargs)
        if results2:
            return results2[0]["mondo_id"], _similarity(cleaned, results2[0])

    return None, 0.0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.argument("description")
@click.option(
    "--id-only",
    is_flag=True,
    default=False,
    help="Print only the top MONDO ID (e.g. MONDO:0005148). Handy for scripting.",
)
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    default=False,
    help="Return all matching MONDO terms (scored, best first) instead of just the top result.",
)
@click.option(
    "--rows",
    default=100,
    show_default=True,
    help="Max candidates to fetch from the API in the fuzzy search pass.",
)
def main(description: str, id_only: bool, show_all: bool, rows: int) -> None:
    """Find the best-matching MONDO term for a condition DESCRIPTION.

    DESCRIPTION is the free-text condition label from your study file,
    e.g. \"type 2 diabetes mellitus\" or \"history of hypertension\".

    \b
    Examples:
        python mondo_agent.py "type 2 diabetes"
        python mondo_agent.py "type 2 diabetes" --id-only
        python mondo_agent.py "hypertension" --id-only
        python mondo_agent.py "myocardial infarction" --all
    """
    try:
        results = search_mondo_terms(description, rows=rows)
    except requests.HTTPError as exc:
        click.echo(f"HTTP error from OLS4 API: {exc}", err=True)
        sys.exit(1)
    except requests.ConnectionError:
        click.echo("Could not connect to https://www.ebi.ac.uk. Check your network.", err=True)
        sys.exit(1)

    if not results:
        click.echo(f"No MONDO terms found for '{description}'.", err=True)
        sys.exit(1)

    if id_only:
        click.echo(results[0]["mondo_id"])
        return

    output = results if show_all else results[:1]
    click.echo(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
