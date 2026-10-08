"""Read linkml-map ``expr`` strings with :mod:`ast` instead of regexes.

A regex over ``, 'X')`` cannot tell a ``case()`` result from a membership tuple
(``{phv} in ('1', '2')``) or a comparison operand; the parse tree can.
"""

from __future__ import annotations

import ast
import re

_REF_RE = re.compile(r"\{(?:pht\d{6}\.)?([A-Za-z_][A-Za-z0-9_]*)\}")


def parse(expr: str) -> ast.expr | None:
    """The expression's AST with each ``{ref}`` replaced by a name, or None if it does not parse."""
    try:
        return ast.parse(_REF_RE.sub(r"\1", str(expr)).strip(), mode="eval").body
    except SyntaxError:
        return None


def _case_calls(node: ast.AST):
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "case":
            yield n


def case_result_literals(expr: str) -> list[str] | None:
    """The string literals a ``case()`` arm returns directly (element ``[1]`` of each arm).

    None when the expression does not parse. Results that are not plain string constants
    (``None``, a nested call, a concatenation) are not literals and are not returned.
    """
    tree = parse(expr)
    if tree is None:
        return None
    out: list[str] = []
    for call in _case_calls(tree):
        for arm in call.args:
            if isinstance(arm, ast.Tuple) and len(arm.elts) == 2:
                val = arm.elts[1]
                if isinstance(val, ast.Constant) and isinstance(val.value, str):
                    out.append(val.value)
    return out


def outer_case_lacks_default(expr: str) -> bool:
    """True when the expression IS a ``case()`` with no ``(True, ...)`` arm.

    Such a slot is null on every row no arm matches, so a required slot written this way passes
    a presence check while emitting nothing on those rows.
    """
    tree = parse(expr)
    if not (isinstance(tree, ast.Call) and isinstance(tree.func, ast.Name)
            and tree.func.id == "case"):
        return False
    for arm in tree.args:
        if (isinstance(arm, ast.Tuple) and len(arm.elts) == 2
                and isinstance(arm.elts[0], ast.Constant) and arm.elts[0].value is True):
            return False
    return True


def guarded_by(expr: str, phv: str) -> bool:
    """True when ``expr`` is ``None if <test reading phv> else ...`` (or a case() on phv).

    The test must read ``phv`` itself, so an age gated on the block's own status variable counts
    as guarded and one gated on a different question does not.
    """
    tree = parse(expr)
    if tree is None:
        return False
    if isinstance(tree, ast.IfExp):
        names = {n.id for n in ast.walk(tree.test) if isinstance(n, ast.Name)}
        is_none = lambda n: isinstance(n, ast.Constant) and n.value is None  # noqa: E731
        return phv in names and (is_none(tree.body) or is_none(tree.orelse))
    return False
