"""Build the observation_type -> variable-label lookup from Table S1.

Table S1 (``config/TableS1.tsv``) is the authoritative label source. It
superseded ``harmonized_vars.tsv``, which has been removed.

BDCHM emits one of three forms in the ``observation_type`` column of
``MeasurementObservation.tsv``:

- ``"OMOP:<n>"`` — matches the ``OMOP Concept ID`` column, which already
  carries the ``OMOP:`` prefix in S1.
- ``"OBA:<id>"`` — matches the ``Ontology CURIE`` column, which holds
  ``OBA:``-prefixed CURIEs (and may hold other vocabularies' CURIEs too).
- bare ``UPPERCASE`` name (e.g. ``CESD_SCORE``) — matches ``var_name.upper()``,
  with a small ``BARE_NAME_ALIASES`` map for the exceptions where BDCHM's
  uppercase form doesn't match ``var_name.upper()``.

A single label (e.g. ``"Albumin in blood"``) may have multiple contributing
codes (an OMOP code in some cohorts, an OBA code in others, sometimes a bare
name). The returned dict collapses all of them onto the same label.

S1 also carries a ``Deprecated Codes`` column: superseded codes that still
appear in some transform specs. These resolve to the same label as their
row's current code, so a spec that hasn't been updated still lands on the
right row rather than falling back to its filename.

Used by the harmonized extractor to populate the ``bdc_label`` field on
measurement entries (so cross-cohort grouping by conceptual variable is
possible without re-loading row data), and by the S5 report aggregator
when grouping per-``observation_type`` summaries into per-``bdc_label``
rows for Table S5.
"""

from __future__ import annotations

import csv
from pathlib import Path

# Bare uppercase observation_type forms emitted by BDCHM that don't match
# var_name.upper(). Keys are the BDCHM-emitted form; values are the
# var_name to look up in Table S1 to find the label.
BARE_NAME_ALIASES: dict[str, str] = {
    "LYMPHOCYTES_COUNT": "lympho_ct",
    "NEUTROPHILS_COUNT": "neutro_ct",
}

# Default location relative to this file.
DEFAULT_PATH = Path(__file__).resolve().parent / "config" / "TableS1.tsv"

# S1 column names.
_LABEL_COL = "Variable Label"
_OMOP_COL = "OMOP Concept ID"
_CURIE_COL = "Ontology CURIE"
_DEPRECATED_COL = "Deprecated Codes"
_STATUS_COL = "status"
_VAR_NAME_COL = "var_name"


def _split_codes(raw: str) -> list[str]:
    """Split a delimited code cell into individual codes."""
    return [c.strip() for c in raw.replace(";", ",").split(",") if c.strip()]


def _is_ignored(row: dict) -> bool:
    """True for S1 rows that annotate rather than define a variable.

    Such a row records a code that is metadata (the spirometry codes) or
    superseded, and its label must never enter the label map — otherwise real
    data gets routed into a row named after the annotation. ``OBA:VT0000217``
    is white blood cell count in ten cohorts' specs and briefly resolved to a
    stray-code note this way.

    ``status=ignore`` is the intended marker. A parenthetical label is also
    honoured because S1 has carried annotation rows with an empty ``status``;
    once those are marked or removed, the label check becomes redundant.
    """
    if (row.get(_STATUS_COL) or "").strip().lower() == "ignore":
        return True
    label = (row.get(_LABEL_COL) or "").strip()
    return label.startswith("(") and label.endswith(")")


def load_label_map(path: Path | str | None = None) -> dict[str, str]:
    """Return a dict mapping observation_type code -> variable label.

    The dict's keys cover all three encoding forms BDCHM emits for the
    ``observation_type`` column: ``OMOP:<n>``, ``OBA:<id>``, and bare
    uppercase ``var_name``, plus any superseded codes listed in S1's
    ``Deprecated Codes`` column. Rows with no usable code contribute zero
    keys.

    Current codes take precedence: a deprecated code never overwrites a
    label already registered by a row's current code.

    Args:
        path: Path to ``TableS1.tsv``. Defaults to the canonical location
            at ``hv_dataqc/extract_harmonized/config/``.

    Returns:
        Dict mapping observation_type code (as it appears in BDCHM output)
        to the human-readable label.
    """
    src = Path(path) if path is not None else DEFAULT_PATH
    with src.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    lookup: dict[str, str] = {}
    deprecated: dict[str, str] = {}
    for r in rows:
        label = (r.get(_LABEL_COL) or "").strip()
        if not label or _is_ignored(r):
            continue
        omop = (r.get(_OMOP_COL) or "").strip()
        curie = (r.get(_CURIE_COL) or "").strip()
        var_name = (r.get(_VAR_NAME_COL) or "").strip()

        # S1 stores OMOP codes already prefixed; tolerate a bare id.
        if omop:
            lookup[omop if ":" in omop else f"OMOP:{omop}"] = label
        if curie:
            lookup[curie] = label
        if var_name:
            lookup[var_name.upper()] = label
        for code in _split_codes(r.get(_DEPRECATED_COL) or ""):
            deprecated.setdefault(code, label)

    # Deprecated codes fill gaps only — a current code always wins.
    for code, label in deprecated.items():
        lookup.setdefault(code, label)

    # Resolve the bare-name exception map: each alias key points to the
    # label of the row whose var_name matches the alias's target.
    for bare, var_name in BARE_NAME_ALIASES.items():
        match = next(
            (
                r
                for r in rows
                if (r.get(_VAR_NAME_COL) or "").strip() == var_name
                and not _is_ignored(r)
            ),
            None,
        )
        if match:
            label = (match.get(_LABEL_COL) or "").strip()
            if label:
                lookup[bare] = label

    return lookup


def load_ignored_codes(path: Path | str | None = None) -> set[str]:
    """Return observation_type codes S1 marks ``status=ignore``.

    These carry a MeasurementObservation that is metadata rather than a
    reportable variable (e.g. the spirometry metadata codes). Callers drop
    the concept entirely so it neither forms a row nor inflates a real
    variable's phv count.
    """
    src = Path(path) if path is not None else DEFAULT_PATH
    with src.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    ignored: set[str] = set()
    for r in rows:
        if (r.get(_STATUS_COL) or "").strip().lower() != "ignore":
            continue
        omop = (r.get(_OMOP_COL) or "").strip()
        curie = (r.get(_CURIE_COL) or "").strip()
        if omop:
            ignored.add(omop if ":" in omop else f"OMOP:{omop}")
        if curie:
            ignored.add(curie)
        ignored.update(_split_codes(r.get(_DEPRECATED_COL) or ""))
    return ignored


def load_var_labels(path: Path | str | None = None) -> dict[str, str]:
    """Return a dict mapping ``var_name`` -> variable label from Table S1."""
    src = Path(path) if path is not None else DEFAULT_PATH
    with src.open(encoding="utf-8") as f:
        return {
            name: label
            for r in csv.DictReader(f, delimiter="\t")
            if (name := (r.get(_VAR_NAME_COL) or "").strip())
            and (label := (r.get(_LABEL_COL) or "").strip())
            and not _is_ignored(r)
        }
