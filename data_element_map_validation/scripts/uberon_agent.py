#!/usr/bin/env python3
"""Look up the best-matching UBERON term for an anatomical site description via the EBI OLS4 API.

Endpoint: GET https://www.ebi.ac.uk/ols4/api/search?ontology=uberon&q={query}

Use for anatomical structures, body parts, organs, and drug administration routes.
Matching strategy mirrors mondo_agent: single pass + client-side re-ranking:
  - Exact label match      → 1.00
  - Exact synonym match    → 0.95
  - Otherwise              → difflib ratio * length_factor^0.4

Usage examples:
    python uberon_agent.py "respiratory tract"
    python uberon_agent.py "oral cavity" --id-only
    python uberon_agent.py "lung" --all
"""

import json
import sys
from difflib import SequenceMatcher
from urllib.parse import quote

import click
import requests

OLS4_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"


def _extract_uberon_id(doc: dict) -> str | None:
    """Return the UBERON:XXXXXXX string from a doc, or None if not a UBERON term."""
    obo_id = doc.get("obo_id", "")
    if obo_id.startswith("UBERON:"):
        return obo_id
    short_form = doc.get("short_form", "")
    if short_form.startswith("UBERON_"):
        return short_form.replace("UBERON_", "UBERON:", 1)
    return None


def _similarity(query: str, concept: dict) -> float:
    """Composite similarity score between *query* and a concept dict."""
    q = query.lower()
    label = concept["label"].lower()
    synonyms = [s.lower() for s in concept["exact_synonyms"]]

    if q == label:
        return 1.0
    if q in synonyms:
        return 0.95

    candidates = [label] + synonyms
    raw = max(SequenceMatcher(None, q, c).ratio() for c in candidates if c)
    length_factor = len(q) / max(len(q), len(label))
    return raw * (length_factor ** 0.4)


def _fetch_docs(query: str, *, rows: int) -> list[dict]:
    """Call OLS4 and return raw docs for UBERON concepts only."""
    url = f"{OLS4_SEARCH_URL}?ontology=uberon&q={quote(query)}&rows={rows}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json().get("response", {}).get("docs", [])


def _docs_to_concepts(docs: list[dict]) -> list[dict]:
    """Convert raw API docs to cleaned concept dicts, dropping non-UBERON entries."""
    concepts = []
    for doc in docs:
        uberon_id = _extract_uberon_id(doc)
        if uberon_id is None:
            continue
        concepts.append(
            {
                "uberon_id": uberon_id,
                "label": doc.get("label", ""),
                "description": (doc.get("description") or [""])[0],
                "exact_synonyms": doc.get("exact_synonyms", []),
            }
        )
    return concepts


def search_uberon_terms(description: str, *, rows: int = 100) -> list[dict]:
    """Return UBERON concepts for *description*, best match first.

    Args:
        description: Free-text anatomical site or route description.
        rows: Max candidates to fetch from OLS4.

    Returns:
        List of concept dicts (uberon_id, label, description, exact_synonyms),
        best match first.
    """
    concepts = _docs_to_concepts(_fetch_docs(description, rows=rows))
    concepts.sort(key=lambda c: _similarity(description, c), reverse=True)
    return concepts


def get_uberon_id(description: str, **kwargs) -> str | None:
    """Return only the top UBERON ID string for an anatomical description.

    Example:
        >>> get_uberon_id("respiratory tract")
        'UBERON:0000065'
        >>> get_uberon_id("oral cavity")
        'UBERON:0000167'
    """
    results = search_uberon_terms(description, **kwargs)
    return results[0]["uberon_id"] if results else None


@click.command()
@click.argument("description")
@click.option(
    "--id-only",
    is_flag=True,
    default=False,
    help="Print only the top UBERON ID (e.g. UBERON:0000065). Handy for scripting.",
)
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    default=False,
    help="Return all matching UBERON terms (scored, best first).",
)
@click.option(
    "--rows",
    default=100,
    show_default=True,
    help="Max candidates to fetch from the API.",
)
def main(description: str, id_only: bool, show_all: bool, rows: int) -> None:
    """Find the best-matching UBERON term for an anatomical DESCRIPTION.

    \b
    Examples:
        python uberon_agent.py "respiratory tract"
        python uberon_agent.py "oral cavity" --id-only
        python uberon_agent.py "lung" --all
    """
    try:
        results = search_uberon_terms(description, rows=rows)
    except requests.HTTPError as exc:
        click.echo(f"HTTP error from OLS4 API: {exc}", err=True)
        sys.exit(1)
    except requests.ConnectionError:
        click.echo("Could not connect to https://www.ebi.ac.uk. Check your network.", err=True)
        sys.exit(1)

    if not results:
        click.echo(f"No UBERON terms found for '{description}'.", err=True)
        sys.exit(1)

    if id_only:
        click.echo(results[0]["uberon_id"])
        return

    output = results if show_all else results[:1]
    click.echo(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
