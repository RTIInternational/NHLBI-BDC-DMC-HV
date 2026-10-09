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


def _norm(value) -> str:
    try:
        return repr(float(value))
    except (TypeError, ValueError):
        return str(value)


def _test_holds(node, phv: str, code: str) -> bool | None:
    """Whether a condition on ``phv`` holds when it carries ``code``; None if it cannot be read.

    Reads ``{phv} == 1``, ``str({phv}) != '2'``, ``int({phv}) in (1, 2)`` and ``and`` / ``or`` /
    ``not`` of them. Codes compare as numbers when both sides are numeric, else as text.
    """
    if isinstance(node, ast.BoolOp):
        vals = [_test_holds(v, phv, code) for v in node.values]
        if None in vals:
            return None
        return all(vals) if isinstance(node.op, ast.And) else any(vals)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        v = _test_holds(node.operand, phv, code)
        return None if v is None else not v
    if not (isinstance(node, ast.Compare) and len(node.ops) == 1):
        return None
    left = node.left
    if (isinstance(left, ast.Call) and isinstance(left.func, ast.Name)
            and left.func.id in ("str", "int", "float") and len(left.args) == 1):
        left = left.args[0]
    if not (isinstance(left, ast.Name) and left.id == phv):
        return None
    right = node.comparators[0]
    if isinstance(right, ast.Constant):
        vals = [right.value]
    elif isinstance(right, (ast.Tuple, ast.List, ast.Set)) and all(
            isinstance(e, ast.Constant) for e in right.elts):
        vals = [e.value for e in right.elts]
    else:
        return None
    hit = _norm(code) in {_norm(v) for v in vals}
    op = node.ops[0]
    if isinstance(op, (ast.Eq, ast.In)):
        return hit
    if isinstance(op, (ast.NotEq, ast.NotIn)):
        return not hit
    return None


def guarded_by(expr: str, phv: str, absent_codes=(), present_codes=()) -> bool:
    """True when ``expr`` is ``None if <test reading phv> else ...`` and the guard points the
    right way.

    The test must read ``phv`` itself, so an age gated on the block's own status variable counts
    as guarded and one gated on a different question does not. Given the status codes that map
    to ABSENT and to PRESENT, the guard must give None on every ABSENT code and a value on at
    least one PRESENT code: ``None if {status} == 1 else {age}`` with 1 -> PRESENT is reversed,
    not guarded. A test that cannot be evaluated on the codes falls back to the structural form.
    """
    tree = parse(expr)
    if tree is None or not isinstance(tree, ast.IfExp):
        return False
    names = {n.id for n in ast.walk(tree.test) if isinstance(n, ast.Name)}
    is_none = lambda n: isinstance(n, ast.Constant) and n.value is None  # noqa: E731
    if phv not in names or not (is_none(tree.body) or is_none(tree.orelse)):
        return False
    none_when = is_none(tree.body)   # None is the branch taken when the test holds

    def gives_none(code: str) -> bool | None:
        holds = _test_holds(tree.test, phv, code)
        return None if holds is None else holds == none_when

    absent = [gives_none(str(c)) for c in absent_codes]
    present = [gives_none(str(c)) for c in present_codes]
    if None in absent or None in present:
        return True
    return all(absent) and (not present or not all(present))
