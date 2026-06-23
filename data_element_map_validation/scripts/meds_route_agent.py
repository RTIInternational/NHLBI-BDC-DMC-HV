#!/usr/bin/env python3
"""Look up OMOP route concept IDs from a curated reference table.

Unlike omop_agent.py (which hits the OHDSI Atlas WebAPI), this agent resolves
route terms offline from a CSV table at:
    data_element_map_validation/bdc_study_input/omop_route_concepts.csv

To add or update route entries, edit that CSV — no code changes needed.

Matching strategy (in order):
  1. Alias expansion  — maps common synonyms to a canonical table name
                        (e.g. "respiratory tract" → "inhalation")
  2. Exact match      — case-insensitive, punctuation-normalised
  3. Substring match  — one string fully contained in the other (score 0.95)
  4. Fuzzy match      — SequenceMatcher ratio; only returned if ≥ threshold

Usage:
    python scripts/meds_route_agent.py "Oral"
    python scripts/meds_route_agent.py "RESPIRATORY TRACT" --id-only
    python scripts/meds_route_agent.py "inhalation" --all
    python scripts/meds_route_agent.py "subcutaneous" --top 3
"""

import csv
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

import click

# ---------------------------------------------------------------------------
# Reference data location
# ---------------------------------------------------------------------------

_DEFAULT_CSV = (
    Path(__file__).parent.parent / "bdc_study_input" / "omop_route_concepts.csv"
)

_FUZZY_THRESHOLD = 0.70

# Common synonyms not present verbatim in the OMOP table.
# Keys are normalised (lowercase, single-space); values match a table entry name.
#
# NOTE — intentionally NOT aliased (curator must decide):
#   "inhaled", "inhalation", "inhalation route"
#   These are ambiguous: could be ENDOTRACHEOPULMONARY (MDI/DPI/nebulizer → lungs)
#   or NASAL (nasal spray). An empty omop_maps_to in the mapreview CSV is the
#   signal for the curator to assign the correct route for that specific medication.
_ALIASES: dict[str, str] = {
    "respiratory tract":  "endotracheopulmonary",
    "oral route":         "oral",
    "by mouth":           "oral",
    "po":                 "oral",
    "iv":                 "intravenous",
    "intravenous route":  "intravenous",
    "im":                 "intramuscular",
    "sq":                 "subcutaneous",
    "subq":               "subcutaneous",
    "sc":                 "subcutaneous",
    "sl":                 "sublingual",
    "transdermal patch":  "transdermal",
    "ophthalmic":         "ocular",
    "eye":                "ocular",
    "ear":                "otic",
    "rectal route":       "rectal",
    "nasal route":        "nasal",
    "topical route":      "topical",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalise(text: str) -> str:
    """Lowercase and collapse non-alphanumeric runs to a single space."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _load_route_table(csv_path: Path) -> list[dict]:
    rows = []
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            cid = row["route_concept_id"].strip()
            name = row["route_concept_name"].strip()
            rows.append({
                "omop_id":      f"OMOP:{cid}",
                "concept_id":   int(cid),
                "concept_name": name,
                "_norm":        _normalise(name),
            })
    return rows


_ROUTE_TABLE: list[dict] | None = None


def _get_table(csv_path: Path = _DEFAULT_CSV) -> list[dict]:
    global _ROUTE_TABLE
    if _ROUTE_TABLE is None:
        _ROUTE_TABLE = _load_route_table(csv_path)
    return _ROUTE_TABLE


def _similarity(query_norm: str, row_norm: str) -> float:
    if query_norm == row_norm:
        return 1.0
    if query_norm in row_norm or row_norm in query_norm:
        return 0.95
    return SequenceMatcher(None, query_norm, row_norm).ratio()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def search_route_concepts(
    text: str,
    *,
    csv_path: Path = _DEFAULT_CSV,
    threshold: float = _FUZZY_THRESHOLD,
) -> list[dict]:
    """Return route concept rows ranked by similarity to *text*, best first.

    Each result dict has: omop_id, concept_id, concept_name, score.
    Only results with score >= *threshold* are returned.
    """
    table = _get_table(csv_path)
    q = _normalise(text)

    # Alias expansion before fuzzy matching
    q = _ALIASES.get(q, q)

    scored = []
    for row in table:
        score = _similarity(q, row["_norm"])
        if score >= threshold:
            scored.append({**row, "score": round(score, 4)})

    scored.sort(key=lambda r: r["score"], reverse=True)
    return [{k: v for k, v in r.items() if k != "_norm"} for r in scored]


def get_omop_route_id(text: str, **kwargs) -> str | None:
    """Return the best-match OMOP route concept as 'OMOP:<id>', or None."""
    results = search_route_concepts(text, **kwargs)
    return results[0]["omop_id"] if results else None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.argument("route_text")
@click.option(
    "--csv-path",
    default=str(_DEFAULT_CSV),
    show_default=True,
    help="Path to the route concepts reference CSV.",
)
@click.option(
    "--threshold",
    default=_FUZZY_THRESHOLD,
    show_default=True,
    help="Minimum fuzzy similarity score (0.0–1.0) to include a result.",
)
@click.option(
    "--id-only",
    is_flag=True,
    default=False,
    help="Print only OMOP:<concept_id>. Handy for scripting.",
)
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    default=False,
    help="Return all matches above the threshold (best first).",
)
@click.option(
    "--top",
    default=1,
    show_default=True,
    help="Number of top results to return (ignored when --all is set).",
)
def main(
    route_text: str,
    csv_path: str,
    threshold: float,
    id_only: bool,
    show_all: bool,
    top: int,
) -> None:
    """Find the OMOP route concept for ROUTE_TEXT using the reference table.

    \b
    Examples:
        python scripts/meds_route_agent.py "Oral"
        python scripts/meds_route_agent.py "RESPIRATORY TRACT" --id-only
        python scripts/meds_route_agent.py "inhalation" --all
        python scripts/meds_route_agent.py "subcutaneous" --top 3
    """
    try:
        results = search_route_concepts(
            route_text, csv_path=Path(csv_path), threshold=threshold
        )
    except FileNotFoundError:
        click.echo(f"Route concepts CSV not found: {csv_path}", err=True)
        sys.exit(1)

    if not results:
        click.echo(
            f"No route concept found for '{route_text}' (threshold={threshold}).",
            err=True,
        )
        sys.exit(1)

    if id_only:
        click.echo(results[0]["omop_id"])
        return

    output = results if show_all else results[:top]
    click.echo(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
