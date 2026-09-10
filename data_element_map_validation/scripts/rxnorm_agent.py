#!/usr/bin/env python3
"""Look up OMOP concept IDs for drug names via the publicly accessible OHDSI Atlas WebAPI.

Endpoint used: GET https://atlas-demo.ohdsi.org/WebAPI/vocabulary/search/{drug_name}

Usage examples:
    python scripts/rxnorm_agent.py Metformin
    python scripts/rxnorm_agent.py Metformin --id-only
    python scripts/rxnorm_agent.py Metformin --all-classes
    python scripts/rxnorm_agent.py Metformin --concept-class "Clinical Drug"
"""

import json
import re
import sys

import click
import requests

ATLAS_BASE_URL = "https://atlas-demo.ohdsi.org/WebAPI"
DEFAULT_CONCEPT_CLASS = "Ingredient"

# ---------------------------------------------------------------------------
# Curated drug-name -> full CURIE overrides.
#
# Free-text medication-name fields (e.g. "name of chol lowering medication")
# sometimes get case()-matched against specific drug names and assigned an
# RxCUI by hand during curation. When the correct classification is really
# an ATC therapeutic class (not an RxNorm ingredient concept), the live
# Atlas WebAPI lookup can't produce that — it only returns OMOP concept IDs,
# which generate_curie_mapreview.py wraps as "OMOP:<id>". These overrides
# return the full CURIE directly, bypassing that wrapping, so future
# pipeline re-runs land on the correct classification instead of drifting
# back to a bare RxCUI/OMOP concept.
#
# Match is case-insensitive, whole-word (so "niacin 500mg tablets" still
# matches "niacin"). Add entries here as new mismapped free-text drugs turn up.
# ---------------------------------------------------------------------------
DRUG_CURIE_OVERRIDES: dict[str, str] = {
    "gemfibrozil":          "ATC:C10AB",         # fibrate
    "metoprolol":           "RxCUI:6918",        # beta blocker, ingredient-level
    "niacin 500mg tablets": "RxCUI:198024",      # niacin 500 MG Oral Tablet (immediate-release,
                                                  # matches the source text exactly — live search
                                                  # ranking for this exact concept was found to be
                                                  # unreliable across phrasings, so it's pinned
                                                  # here rather than left to search ranking)
    "insulin":              "ATC:A10A",          # Insulins and analogues (class-level). RxNorm has
                                                  # no single generic "insulin" Ingredient concept —
                                                  # only specific formulations (insulin glargine,
                                                  # insulin isophane, etc.) — and a bare "are you
                                                  # taking insulin" survey question can't resolve to
                                                  # any one of those. Confirmed via two independent
                                                  # cases this session: CARDIA tak_insulin.yaml
                                                  # (fix #33) and CHS tak_insulin.yaml, 16 PHVs
                                                  # (fix #38), both landed on this exact class code.
    "insulins":             "ATC:A10A",          # Plural form — CHS's real dbGaP variable
                                                  # description text is literally "Insulins" for
                                                  # several of the 16 PHVs in fix #38, so this must
                                                  # match on its own, not just singular "insulin".
}
# All values confirmed against dbGaP-verified real cases this session. Plain
# "niacin" (no dose) is deliberately NOT overridden — it stays on the live
# Ingredient-only search path, which already resolves it correctly on its own.

# "insulin"/"insulins" are class-level fallbacks for a bare yes/no insulin
# question — but RxNorm DOES have specific formulation concepts (insulin
# glargine, insulin isophane, etc., confirmed present in the local
# rxnorm2omop_standard.csv reference table). A query naming one of those
# specific types is more specific than the class-level fallback and should
# fall through to the RxNorm lookup instead, where it can resolve to its own
# concept — but the distinguishing signal is NOT "more than one word": real
# dbGaP text for a still-generic insulin question is routinely multi-word
# ("TAKE INSULIN", CHS; "CURRENTLY TAKING INSULIN OR ORAL DRUGS? Q 14",
# CARDIA fix #33) and must still hit the override. What actually
# distinguishes a specific mention is a recognized insulin-type modifier
# word alongside "insulin" — so those are excluded by name instead of by
# word count.
_INSULIN_TYPE_MODIFIERS = {
    "glargine", "aspart", "lispro", "isophane", "detemir", "degludec",
    "regular", "nph", "human", "beef", "pork", "zinc", "lente", "ultralente",
    "protamine",
}

_OVERRIDE_PATTERNS = {
    name: re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)", re.IGNORECASE)
    for name in DRUG_CURIE_OVERRIDES
}


def get_drug_curie_override(drug_name: str) -> str | None:
    """Return a curated full CURIE for *drug_name* if it matches a known
    override, else None. Checked before the live API call in
    generate_curie_mapreview.py's drug_concept branch.

    "insulin"/"insulins" match as a bounded word anywhere in the query (same
    rule as every other entry) UNLESS the query also names a specific
    insulin type (see _INSULIN_TYPE_MODIFIERS) — in that case the override
    is skipped so the more specific RxNorm lookup can run instead.
    """
    words = set(re.findall(r"[a-z]+", drug_name.lower()))
    is_specific_insulin = ("insulin" in words or "insulins" in words) and bool(words & _INSULIN_TYPE_MODIFIERS)
    for name, pattern in _OVERRIDE_PATTERNS.items():
        if name in ("insulin", "insulins") and is_specific_insulin:
            continue
        if pattern.search(drug_name):
            return DRUG_CURIE_OVERRIDES[name]
    return None


def search_omop_concepts(
    drug_name: str,
    *,
    base_url: str = ATLAS_BASE_URL,
    vocabularies: list[str] | None = None,
    concept_class: str | None = DEFAULT_CONCEPT_CLASS,
    standard_only: bool = True,
) -> list[dict]:
    """Return OMOP concept records matching *drug_name* from the OHDSI Atlas WebAPI.

    Args:
        drug_name: Drug name to search for (e.g. "Metformin").
        base_url: WebAPI root URL for the Atlas instance.
        vocabularies: Restrict to these vocabularies (default: RxNorm + RxNorm Extension).
        concept_class: Restrict to this concept class (default: "Ingredient").
                       Pass None to return all concept classes.
        standard_only: When True, keep only standard concepts (STANDARD_CONCEPT == 'S').

    Returns:
        List of concept dicts with keys concept_id, concept_name, concept_code,
        vocabulary_id, domain_id, concept_class_id, standard_concept.
    """
    if vocabularies is None:
        vocabularies = ["RxNorm", "RxNorm Extension"]

    url = f"{base_url}/vocabulary/search/{requests.utils.quote(drug_name)}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    raw = resp.json()

    vocab_set = set(vocabularies)
    concepts = []
    for item in raw:
        if item.get("VOCABULARY_ID") not in vocab_set:
            continue
        if standard_only and item.get("STANDARD_CONCEPT") != "S":
            continue
        if concept_class and item.get("CONCEPT_CLASS_ID") != concept_class:
            continue
        concepts.append(
            {
                "concept_id": item["CONCEPT_ID"],
                "concept_name": item["CONCEPT_NAME"],
                "concept_code": item["CONCEPT_CODE"],
                "vocabulary_id": item["VOCABULARY_ID"],
                "domain_id": item["DOMAIN_ID"],
                "concept_class_id": item["CONCEPT_CLASS_ID"],
                "standard_concept": item["STANDARD_CONCEPT"],
            }
        )

    return concepts


def get_omop_concept_id(drug_name: str, **kwargs) -> int | None:
    """Return only the first matching concept ID (convenience wrapper)."""
    concepts = search_omop_concepts(drug_name, **kwargs)
    return concepts[0]["concept_id"] if concepts else None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.argument("drug_name")
@click.option(
    "--base-url",
    default=ATLAS_BASE_URL,
    show_default=True,
    help="OHDSI Atlas WebAPI base URL.",
)
@click.option(
    "--concept-class",
    default=DEFAULT_CONCEPT_CLASS,
    show_default=True,
    help='Filter by concept class (e.g. "Ingredient", "Clinical Drug"). Pass empty string for all.',
)
@click.option(
    "--all-classes",
    is_flag=True,
    default=False,
    help="Return all concept classes (overrides --concept-class).",
)
@click.option(
    "--all-concepts",
    is_flag=True,
    default=False,
    help="Include non-standard concepts in addition to standard ones.",
)
@click.option(
    "--id-only",
    is_flag=True,
    default=False,
    help="Print only the first matching concept ID (handy for scripting).",
)
def main(
    drug_name: str,
    base_url: str,
    concept_class: str,
    all_classes: bool,
    all_concepts: bool,
    id_only: bool,
) -> None:
    """Look up the OMOP concept ID for DRUG_NAME via the OHDSI Atlas WebAPI.

    By default returns only standard RxNorm Ingredient-level concepts,
    which gives you the canonical drug concept (e.g. concept_id 1503297 for Metformin).

    \b
    Examples:
        python scripts/rxnorm_agent.py Metformin
        python scripts/rxnorm_agent.py Metformin --id-only
        python scripts/rxnorm_agent.py Metformin --all-classes
        python scripts/rxnorm_agent.py Lisinopril --concept-class "Clinical Drug"
    """
    try:
        concepts = search_omop_concepts(
            drug_name,
            base_url=base_url,
            concept_class=None if all_classes else (concept_class or None),
            standard_only=not all_concepts,
        )
    except requests.HTTPError as exc:
        click.echo(f"HTTP error from Atlas API: {exc}", err=True)
        sys.exit(1)
    except requests.ConnectionError:
        click.echo(f"Could not connect to Atlas at {base_url}. Check the URL or your network.", err=True)
        sys.exit(1)

    if not concepts:
        label = "standard Ingredient-level" if not all_classes else "matching"
        click.echo(f"No {label} concepts found for '{drug_name}'.", err=True)
        sys.exit(1)

    if id_only:
        click.echo(concepts[0]["concept_id"])
        return

    click.echo(json.dumps(concepts, indent=2))


if __name__ == "__main__":
    main()
