"""Known-issues suppression for the compare pipeline.

Loads a per-cohort known_issues YAML from
``hv_dataqc/compare/config/known_issues/<COHORT>.yaml`` and applies it to a
list of CheckResult objects, replacing matching FAIL (or WARN) results with
SKIP.

YAML schema (one document per cohort):

    cohort: CARDIA
    known_issues:
      - checks: [C2]            # one or more check IDs this entry suppresses
        variable_key: "a12cbron"  # one source-side variable name token
        yaml_file: chr_bronchitis.yaml
        status: false_positive
        summary: >
          ...explanation...
        related_issues: [651]
        confirmed_date: "2026-06-28"

Matching rules
--------------
An entry in known_issues suppresses a CheckResult when ALL of:

1. ``entry["checks"]`` contains the result's ``check_id``.
2. The token set of ``entry["variable_key"]`` is a subset of the source
   variable name tokens in the result's ``variable`` field.  The variable
   field has the form::

       display_name [phv... / pht...]

   Only the ``display_name`` part (before the first ``[``) is tokenised, on
   ``+``.  ``variable_key`` may be either a single token (e.g. ``a11mstrk``,
   ``_total``) or a ``+``-joined pool that mirrors how the report renders a
   pooled variable (e.g. ``crp+crp_1+crp_7+crp_8``).  It matches when every
   token it names is present in the result's variable tokens — so a single
   token matches when it appears, and a pooled key matches the pooled variable
   it describes.  (A pooled key is NOT matched by set membership of the whole
   ``+``-joined string, which never appears as a single token.)

Suppressed results keep their original ``check_id`` and ``variable`` but have
their ``status`` changed to ``"SKIP"`` and their ``message`` prepended with a
citation of the matching known_issue entry.  The original message and the full
known_issue entry are preserved in ``detail``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from hv_dataqc.compare._common import CheckResult

_CONFIG_DIR = Path(__file__).resolve().parent / "config" / "known_issues"

# Statuses that known_issues suppression can downgrade to SKIP.
_SUPPRESSIBLE = {"FAIL", "WARN"}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_known_issues(cohort: str) -> list[dict]:
    """Load the known_issues list for *cohort* (case-insensitive).

    Returns an empty list when no file exists for the cohort.
    """
    path = _CONFIG_DIR / f"{cohort.upper()}.yaml"
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except yaml.YAMLError as exc:
        # A malformed known_issues config is human-edited documentation metadata
        # and must not abort the whole compare run. Warn and proceed with no
        # suppression applied, so the full report is still produced.
        print(
            f"WARNING: could not parse known_issues config {path.name}: {exc}\n"
            "  Proceeding with NO known-issue suppression for this cohort.",
            file=sys.stderr,
        )
        return []
    entries = data.get("known_issues") or []
    if not isinstance(entries, list):
        return []
    return entries


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------

def _variable_tokens(variable: str) -> set[str]:
    """Extract source-variable name tokens from a CheckResult.variable string.

    The variable field has the form::

        display_name [phv... / pht...]

    or just a plain name like ``_total`` or ``entity_file_coverage``.
    We tokenise the *display_name* part only, splitting on ``+``.
    """
    # Strip the " [phv... / pht...]" suffix
    bracket_pos = variable.find("[")
    display = variable[:bracket_pos].strip() if bracket_pos != -1 else variable.strip()
    # Split on '+' and strip whitespace from each token
    return {t.strip() for t in display.split("+") if t.strip()}


def _key_tokens(variable_key: str) -> set[str]:
    """Split a ``variable_key`` into its component tokens on ``+``.

    A single-token key yields a one-element set; a ``+``-joined pooled key
    yields the set of pooled source names.  Tokenising the key the same way as
    the report's variable field lets a pooled key match the pooled variable it
    describes (subset match), instead of never matching because the whole
    ``+``-joined string is not itself a single token.
    """
    return {t.strip() for t in variable_key.split("+") if t.strip()}


def _entry_matches(entry: dict, check_id: str, variable: str) -> bool:
    """Return True when *entry* matches the given check_id and variable."""
    entry_checks = entry.get("checks") or []
    if check_id not in entry_checks:
        return False
    variable_key = str(entry.get("variable_key", "")).strip()
    if not variable_key:
        return False
    key_tokens = _key_tokens(variable_key)
    if not key_tokens:
        return False
    # Match when every token the entry names is present in the result's
    # variable tokens.  For a single-token key this is exact membership (the
    # prior behaviour); for a pooled key it requires the pooled variable to
    # contain all the named source vars — precise, and not satisfied by an
    # unrelated variable that happens to share one common token.
    return key_tokens <= _variable_tokens(variable)


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

def apply_known_issues(
    results: list[CheckResult],
    known_issues: list[dict],
) -> tuple[list[CheckResult], int]:
    """Suppress matching FAIL/WARN results using *known_issues* entries.

    Returns a new list with suppressed results converted to SKIP, and the
    count of results that were suppressed.

    The original message and matching known_issue entry are preserved in
    ``result.detail`` under keys ``"original_message"`` and
    ``"known_issue"``.
    """
    if not known_issues:
        return results, 0

    suppressed = 0
    out: list[CheckResult] = []
    for r in results:
        if r.status not in _SUPPRESSIBLE:
            out.append(r)
            continue

        match: dict | None = None
        for entry in known_issues:
            if _entry_matches(entry, r.check_id, r.variable):
                match = entry
                break

        if match is None:
            out.append(r)
            continue

        # Build citation
        summary = str(match.get("summary", "")).strip().replace("\n", " ")
        issues = match.get("related_issues") or []
        issue_ref = (" (issue #" + ", #".join(str(i) for i in issues) + ")") if issues else ""
        new_msg = (
            f"[known_issue{issue_ref}] {summary} "
            f"— original: {r.message}"
        )
        new_detail = {
            **r.detail,
            "original_message": r.message,
            "known_issue": dict(match),
        }
        # Rebuild result with SKIP status
        from hv_dataqc.compare._common import CheckResult as CR
        out.append(CR(r.check_id, r.variable, "SKIP", new_msg, new_detail))
        suppressed += 1

    return out, suppressed
