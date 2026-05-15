"""I/O helpers for the compare pipeline.

Atomic file writes and config-file loaders. Pure I/O — no business logic,
no compare-specific data shapes.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

from hv_dataqc.hv_dataqc_common import write_json_atomic

THRESHOLDS_PATH = Path(__file__).resolve().parent / "config" / "thresholds.yaml"


def write_json_atomic_strict(path: Path, data: Any) -> None:
    """Write strict JSON via temp file then atomic replace."""
    write_json_atomic(path, data, ensure_ascii=False, default=str)


def write_text_atomic(path: Path, text: str) -> None:
    """Write text via temp file then atomic replace. Creates parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as fh:
            fh.write(text)
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def load_thresholds(path: Path | None = None) -> dict:
    """Load statistical comparison thresholds from YAML, falling back to {}.

    The compare module supplies built-in default values for any key that
    isn't overridden; this loader returns whatever the YAML file specifies
    (or an empty dict if no file is present).
    """
    effective_path = path or THRESHOLDS_PATH
    if effective_path.exists():
        try:
            with effective_path.open("r", encoding="utf-8") as fh:
                cfg = yaml.safe_load(fh) or {}
            if not isinstance(cfg, dict):
                print(
                    f"WARNING: Thresholds YAML {effective_path.name}: expected a mapping, "
                    "using built-in defaults",
                    file=sys.stderr,
                )
                return {}
            print(f"Loaded thresholds from {effective_path.name}")
            return cfg
        except yaml.YAMLError as exc:
            print(
                f"WARNING: Malformed thresholds YAML {effective_path.name}: {exc} -- using built-in defaults",
                file=sys.stderr,
            )
            return {}
    if path is not None:
        print(f"WARNING: Thresholds file not found: {effective_path} -- using built-in defaults")
    return {}
