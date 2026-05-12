"""Common types and small helpers shared across compare/* modules.

Kept minimal: just the types and a couple of widely-used utilities that
don't belong specifically to crosswalk-building, check-running, or
rendering.
"""

from __future__ import annotations

from typing import Any


class CheckResult:
    """One check result for one variable."""

    def __init__(
        self,
        check_id: str,
        variable: str,
        status: str,          # PASS | WARN | FAIL | SKIP | INFO
        message: str,
        detail: dict | None = None,
    ) -> None:
        self.check_id = check_id
        self.variable = variable
        self.status = status
        self.message = message
        self.detail = detail or {}

    def to_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "variable": self.variable,
            "status": self.status,
            "message": self.message,
            "detail": self.detail,
        }


class CrosswalkBuildError(RuntimeError):
    """Raised when a YAML-driven variable crosswalk cannot be built safely."""


def md_escape(value: Any) -> str:
    """Escape values embedded in Markdown prose/tables."""
    text = str(value).replace("\r", " ").replace("\n", " ")
    return (
        text.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("`", "\\`")
        .replace("*", "\\*")
        .replace("_", "\\_")
    )


# ---------------------------------------------------------------------------
# Message-formatting helpers used by check functions
#
# These format numbers and src→dst comparisons that currently get baked
# into CheckResult.message strings at check time. That entanglement of
# formatting with check logic is a known issue (see REFACTOR_PLAN Phase
# C-prereq) — the long-term fix is for checks to emit structured detail
# and let the renderer format. Until then, these helpers live here as a
# peer-of-checks/peer-of-render utility module.
# ---------------------------------------------------------------------------


def fmt_n(val: int | float) -> str:
    """Format a number with commas for integers, leave floats as-is."""
    if isinstance(val, int):
        return f"{val:,}"
    if isinstance(val, float) and val == int(val) and abs(val) >= 1000:
        return f"{int(val):,}"
    return str(val)


def fmt_cmp(src, dst, unit: str = "") -> str:
    """Format a comparison. If src == dst, show once; otherwise 'src -> dst'."""
    s, d = fmt_n(src), fmt_n(dst)
    u = unit
    if s == d:
        return f"{s}{u}"
    return f"{s}{u} -> {d}{u}"


def fmt_cmp_stat(label: str, src, dst, rel_diff: float) -> str:
    """Format 'Label: value (d=X)' or 'Label: src -> dst (d=X)'.

    Omits the delta when values are identical.
    """
    s, d = fmt_n(src), fmt_n(dst)
    if s == d:
        return f"{label}: {s}"
    return f"{label}: {s} -> {d} (d={rel_diff:.4f})"
