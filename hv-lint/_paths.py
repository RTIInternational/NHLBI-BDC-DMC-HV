"""Shared path resolution for HV-Lint scripts.

Works in both deployment locations:
  1. Control center:  QC/hv-lint/phase-{1,2,3}/  (develop & test)
  2. HV repo:         hv-lint/phase-{1,2,3}/     (CI & production)

Detection logic: walk up from the calling script until we find
``priority_variables_transform/``.  Two levels up from ``hv-lint/``
in the HV repo; four levels up then into the sibling ``NHLBI-BDC-DMC-HV``
for the control center.
"""

from __future__ import annotations

from pathlib import Path

# Root of the hv-lint directory tree (one level above phase-1/2/3)
HVLINT_ROOT = Path(__file__).resolve().parent

# .yamllint config lives alongside this module
YAMLLINT_CONFIG = HVLINT_ROOT / ".yamllint"


def find_hv_root(script_path: str | Path | None = None) -> Path:
    """Return the HV repo root that contains ``priority_variables_transform/``.

    Parameters
    ----------
    script_path : optional
        The ``__file__`` of the calling script.  Not needed if the caller
        is inside the ``hv-lint/`` tree (the default resolution is from
        this module's own ``__file__``).

    Raises
    ------
    RuntimeError
        If neither the HV-repo layout nor the control-center layout can
        be detected.
    """
    anchor = Path(script_path).resolve().parent if script_path else HVLINT_ROOT

    # Case 1 — running inside the HV repo:
    #   hv-lint/_paths.py  →  parent = hv-lint/  →  parent.parent = HV root
    candidate = HVLINT_ROOT.parent
    if (candidate / "priority_variables_transform").is_dir():
        return candidate

    # Case 2 — running from the control center repo:
    #   QC/hv-lint/_paths.py  →  ...parent...parent = control-center root
    #   sibling NHLBI-BDC-DMC-HV should be next to the control-center dir
    control_center = HVLINT_ROOT.parent.parent  # QC → control-center
    sibling = control_center.parent / "NHLBI-BDC-DMC-HV"
    if (sibling / "priority_variables_transform").is_dir():
        return sibling

    raise RuntimeError(
        f"Cannot locate HV repo root (priority_variables_transform/) "
        f"from {anchor}.  Pass --hv-root explicitly."
    )


def find_transform_dir() -> Path:
    """Return the ``priority_variables_transform/`` directory in the HV repo."""
    return find_hv_root() / "priority_variables_transform"


def find_transform_dir(script_path: str | Path | None = None) -> Path:
    """Shortcut: ``find_hv_root() / 'priority_variables_transform'``."""
    return find_hv_root(script_path) / "priority_variables_transform"
