"""Build the observation_type -> var_label lookup from harmonized_vars.tsv.

BDCHM emits one of three forms in the ``observation_type`` column of
``MeasurementObservation.tsv``:

- ``"OMOP:<n>"`` — matches the ``OMOP Standard Concept ID`` column in
  ``harmonized_vars.tsv`` (the TSV stores the bare numeric id; we prefix
  ``OMOP:`` on lookup).
- ``"OBA:<id>"`` — matches the ``OBA CURIE`` column directly (already
  includes the ``OBA:`` prefix in the TSV).
- bare ``UPPERCASE`` name (e.g. ``CESD_SCORE``) — matches ``var_name.upper()``,
  with a small ``BARE_NAME_ALIASES`` map for the exceptions where BDCHM's
  uppercase form doesn't match ``var_name.upper()``.

A single ``var_label`` (e.g. ``"Albumin in blood"``) may have multiple
contributing codes (an OMOP code in some cohorts, an OBA code in others,
sometimes a bare name). The returned dict collapses all of them onto the
same label.

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
# var_name to look up in harmonized_vars.tsv to find the var_label.
BARE_NAME_ALIASES: dict[str, str] = {
    "LYMPHOCYTES_COUNT": "lympho_ct",
    "NEUTROPHILS_COUNT": "neutro_ct",
}

# Default location relative to this file.
DEFAULT_PATH = Path(__file__).resolve().parent / "config" / "harmonized_vars.tsv"


def load_label_map(path: Path | str | None = None) -> dict[str, str]:
    """Return a dict mapping observation_type code -> var_label.

    The dict's keys cover all three encoding forms BDCHM emits for the
    ``observation_type`` column: ``OMOP:<n>``, ``OBA:<id>``, and bare
    uppercase ``var_name``. Entries with no usable code in their TSV row
    (e.g. variables that haven't been assigned an OMOP or OBA mapping yet)
    contribute zero keys.

    Args:
        path: Path to ``harmonized_vars.tsv``. Defaults to the canonical
            location at ``hv_dataqc/extract_harmonized/config/``.

    Returns:
        Dict mapping observation_type code (as it appears in BDCHM output)
        to the human-readable ``var_label``.
    """
    src = Path(path) if path is not None else DEFAULT_PATH
    with src.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    lookup: dict[str, str] = {}
    for r in rows:
        label = r.get("var_label", "").strip()
        if not label:
            continue
        omop_id = r.get("OMOP Standard Concept ID", "").strip()
        oba = r.get("OBA CURIE", "").strip()
        var_name = r.get("var_name", "").strip()

        if omop_id:
            lookup[f"OMOP:{omop_id}"] = label
        if oba.startswith("OBA:"):
            lookup[oba] = label
        if var_name:
            lookup[var_name.upper()] = label

    # Resolve the bare-name exception map: each alias key points to the
    # var_label of the row whose var_name matches the alias's target.
    for bare, var_name in BARE_NAME_ALIASES.items():
        match = next(
            (r for r in rows if r.get("var_name", "").strip() == var_name),
            None,
        )
        if match:
            label = match.get("var_label", "").strip()
            if label:
                lookup[bare] = label

    return lookup
