"""Shared path resolution for HV-Lint scripts.

Works in both deployment locations:
  1. Control center:  hv-lint/phase-{1,2,3}/  (develop & test)
  2. HV repo:         hv-lint/phase-{1,2,3}/     (CI & production)

Override the auto-detected HV repo root in two ways (checked in order):
  - ``set_hv_root(path)`` -- programmatic override (same process)
  - ``HV_ROOT`` environment variable -- for CLI / subprocess use

Detection logic (fallback): check two fixed candidate locations:
  - Two levels up from ``hv-lint/`` (HV repo layout)
  - Sibling ``NHLBI-BDC-DMC-HV`` directory (control center layout)
Does NOT walk up the directory tree.
"""

from __future__ import annotations

import os
from pathlib import Path

# Root of the hv-lint directory tree (one level above phase-1/2/3)
HVLINT_ROOT = Path(__file__).resolve().parent

# .yamllint config lives alongside this module
YAMLLINT_CONFIG = HVLINT_ROOT / ".yamllint"

# Programmatic override -- set via set_hv_root()
_hv_root_override: Path | None = None


def set_hv_root(path: str | Path) -> None:
    """Programmatically override the HV repo root for this process.

    The path must contain a ``priority_variables_transform/`` directory.
    """
    global _hv_root_override
    p = Path(path).resolve()
    if not (p / "priority_variables_transform").is_dir():
        raise ValueError(
            f"Not a valid HV repo root (no priority_variables_transform/): {p}"
        )
    _hv_root_override = p


def find_hv_root(script_path: str | Path | None = None) -> Path:
    """Return the HV repo root that contains ``priority_variables_transform/``.

    Resolution order:
      1. ``set_hv_root()`` programmatic override
      2. ``HV_ROOT`` environment variable
      3. Auto-detection from file-system layout

    Parameters
    ----------
    script_path : optional
        The ``__file__`` of the calling script.  Not needed if the caller
        is inside the ``hv-lint/`` tree (the default resolution is from
        this module's own ``__file__``).

    Raises
    ------
    RuntimeError
        If no valid HV repo root can be found.
    """
    # 1. Programmatic override
    if _hv_root_override is not None:
        return _hv_root_override

    # 2. HV_ROOT environment variable
    env_root = os.environ.get("HV_ROOT")
    if env_root:
        p = Path(env_root).resolve()
        if (p / "priority_variables_transform").is_dir():
            return p
        raise RuntimeError(
            f"HV_ROOT environment variable points to {p} "
            f"but it has no priority_variables_transform/ directory."
        )

    # 3. Auto-detection
    anchor = Path(script_path).resolve().parent if script_path else HVLINT_ROOT

    # Case A -- running inside the HV repo:
    #   hv-lint/_paths.py  ->  parent = hv-lint/  ->  parent.parent = HV root
    candidate = HVLINT_ROOT.parent
    if (candidate / "priority_variables_transform").is_dir():
        return candidate

    # Case B -- running from the control center repo:
    #   hv-lint/_paths.py  ->  ...parent...parent = control-center root
    #   sibling NHLBI-BDC-DMC-HV should be next to the control-center dir
    control_center = HVLINT_ROOT.parent.parent  # QC -> control-center
    sibling = control_center.parent / "NHLBI-BDC-DMC-HV"
    if (sibling / "priority_variables_transform").is_dir():
        return sibling

    raise RuntimeError(
        f"Cannot locate HV repo root (priority_variables_transform/) "
        f"from {anchor}.  Set HV_ROOT env var or pass --hv-root to the "
        f"phase runner."
    )


def find_transform_dir(script_path: str | Path | None = None) -> Path:
    """Return the ``priority_variables_transform/`` directory in the HV repo."""
    return find_hv_root(script_path) / "priority_variables_transform"
