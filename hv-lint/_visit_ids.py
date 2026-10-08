"""Symbolic enumeration of the ids an ``id`` / ``associated_visit`` / ``associated_participant``
expression can emit -- one parser for rules 1.8, 5.1, 5.2 and 5.11.

An expression is parsed with :mod:`ast` (each ``{phv}`` / ``{pht.phv}`` becomes a name) and every
value it can produce is enumerated: ``case()`` yields each arm's value, ``+`` concatenates,
``uuid5(ns, seed)`` records the namespace and the seed. A seed is a sequence of literal text and
``str({phv})`` placeholders, so::

    uuid5(".../Visit", str({phv00177926}) + ":" + case((x == 0, 'FHS ORIGINAL'), ...) + ' EXAM 2')

enumerates to one :class:`IdValue` per arm, each with ``seed_phvs == ("phv00177926",)`` and a
label such as ``FHS ORIGINAL EXAM 2``. Comparison operands (``'P2'`` in ``phase_study == 'P2'``,
CARDIA's ``'HBP'``) are conditions, never values, so they can never be read as labels -- the
defect a regex over quoted strings cannot avoid.

A ``(True, ...)`` arm of a case() that has other non-None arms is a FALLBACK (``FHS UNKNOWN
VISIT``): it fires only on a code no arm covers, so rules that compare labels (1.8, 5.1) drop it.
:func:`fallback_reach` evaluates the expression per observed code, so 5.2 can report a fallback
that real rows reach when no Visit block defines it.
"""

from __future__ import annotations

import ast
import itertools
import re
from dataclasses import dataclass

# {phv}, {pht.phv}, or a bare column name such as {dbGaP_Subject_ID}
_REF_RE = re.compile(r"\{(?:(pht\d{6})\.)?(phv\d{8}|[A-Za-z_][A-Za-z0-9_]*)\}")


class Unparsed(Exception):
    """The expression uses a construct the enumerator does not model."""


@dataclass(frozen=True)
class Seed:
    """A ``str({phv})`` placeholder inside a uuid5 seed; ``table`` is set for ``{pht.phv}``.

    ``phv`` holds the column name as written, which is not always an accession
    (``{dbGaP_Subject_ID}``)."""
    phv: str
    table: str | None = None


@dataclass(frozen=True)
class IdValue:
    """One value an id expression can emit."""
    namespace: str | None        # uuid5 namespace URL; None for a plain string value
    parts: tuple                 # literal strings and Seed placeholders, adjacent strings merged
    fallback: bool = False       # produced only by a (True, ...) fallback arm

    @property
    def seeds(self) -> tuple[Seed, ...]:
        return tuple(p for p in self.parts if isinstance(p, Seed))

    @property
    def label(self) -> str:
        """The literal text of the seed with its leading ``:`` separator removed."""
        return "".join(p for p in self.parts if isinstance(p, str)).lstrip(":").strip()


def _encode(expr: str) -> tuple[str, dict[str, Seed]]:
    names: dict[str, Seed] = {}

    def sub(m: re.Match) -> str:
        name = f"__ref_{m.group(1) or 'x'}_{m.group(2)}"
        names[name] = Seed(m.group(2), m.group(1))
        return name

    return _REF_RE.sub(sub, str(expr)), names


def _merge(parts) -> tuple:
    out: list = []
    for p in parts:
        if isinstance(p, str):
            if not p:
                continue
            if out and isinstance(out[-1], str):
                out[-1] += p
                continue
        out.append(p)
    return tuple(out)


# A value during evaluation: None, ("STR", parts), ("UUID", ns, parts). Each is paired with a
# fallback flag.
def _ev(node, names):
    if isinstance(node, ast.Constant):
        if node.value is None:
            return [(None, False)]
        return [(("STR", (str(node.value),)), False)]
    if isinstance(node, ast.Name):
        if node.id in names:
            return [(("STR", (names[node.id],)), False)]
        if node.id == "None":
            return [(None, False)]
        raise Unparsed(f"name {node.id}")
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        out = []
        for (lv, lf), (rv, rf) in itertools.product(_ev(node.left, names), _ev(node.right, names)):
            if lv is None or rv is None:
                out.append((None, lf or rf))
            elif lv[0] != "STR" or rv[0] != "STR":
                raise Unparsed("concatenation with a uuid5 value")
            else:
                out.append((("STR", _merge(lv[1] + rv[1])), lf or rf))
        return out
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        fn = node.func.id
        if fn == "str" and len(node.args) == 1:
            return _ev(node.args[0], names)
        if fn == "uuid5" and len(node.args) == 2:
            try:
                ns = ast.literal_eval(node.args[0])
            except ValueError as exc:
                raise Unparsed("uuid5 namespace") from exc
            out = []
            for v, f in _ev(node.args[1], names):
                out.append((None if v is None else ("UUID", ns, v[1] if v[0] == "STR" else ()), f))
            return out
        if fn == "case":
            arms = []
            for t in node.args:
                if not isinstance(t, ast.Tuple) or len(t.elts) != 2:
                    raise Unparsed("case() arm")
                cond, val = t.elts
                is_true = isinstance(cond, ast.Constant) and cond.value is True
                arms.append((is_true, _ev(val, names)))
            has_other = any(not is_true and any(v is not None for v, _ in vals)
                            for is_true, vals in arms)
            out = []
            for is_true, vals in arms:
                for v, f in vals:
                    out.append((v, f or (is_true and has_other)))
            if not any(is_true for is_true, _ in arms):
                out.append((None, False))
            return out
    raise Unparsed(ast.dump(node)[:80])


def enumerate_ids(expr: str) -> list[IdValue]:
    """Every non-None value ``expr`` can emit. Raises :class:`Unparsed` on an unmodelled form."""
    src, names = _encode(expr)
    try:
        tree = ast.parse(src.strip(), mode="eval")
    except SyntaxError as exc:
        raise Unparsed(f"syntax: {exc.msg}") from exc
    out: list[IdValue] = []
    seen: set = set()
    for v, fb in _ev(tree.body, names):
        if v is None:
            continue
        iv = IdValue(v[1], v[2], fb) if v[0] == "UUID" else IdValue(None, v[1], fb)
        if iv not in seen:
            seen.add(iv)
            out.append(iv)
    return out


def slot_ids(slot_def) -> list[IdValue]:
    """The values a slot derivation emits: ``expr`` enumerated, a static ``value`` as one label,
    a bare ``populated_from`` as one seed with no label. Unparsed expressions yield ``[]``."""
    if not isinstance(slot_def, dict):
        return []
    if slot_def.get("expr") not in (None, ""):
        try:
            return enumerate_ids(str(slot_def["expr"]))
        except Unparsed:
            return []
    if isinstance(slot_def.get("value"), str) and slot_def["value"].strip():
        return [IdValue(None, (slot_def["value"].strip(),))]
    pf = slot_def.get("populated_from")
    if isinstance(pf, str) and re.fullmatch(r"phv\d{8}", pf):
        return [IdValue(None, (Seed(pf),))]
    return []


def labels(values, include_fallback: bool = False) -> set[str]:
    """The visit labels of ``values``; fallback arms are dropped unless asked for."""
    return {v.label for v in values if v.label and (include_fallback or not v.fallback)}


# -- Which observed codes reach a fallback arm ------------------------------------------------

def _switch_names(tree, names) -> set[str]:
    """The ``{phv}`` names compared inside case() conditions."""
    out: set[str] = set()
    for call in ast.walk(tree):
        if isinstance(call, ast.Call) and getattr(call.func, "id", None) == "case":
            for arm in call.args:
                if isinstance(arm, ast.Tuple) and len(arm.elts) == 2:
                    for n in ast.walk(arm.elts[0]):
                        if isinstance(n, ast.Name) and n.id in names:
                            out.add(n.id)
    return out


def _const_values(node) -> list[str]:
    if isinstance(node, ast.Constant):
        return [str(node.value)]
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)) and all(
            isinstance(e, ast.Constant) for e in node.elts):
        return [str(e.value) for e in node.elts]
    raise Unparsed("comparison with a non-literal")


def _cond(node, var: str, code: str) -> bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BoolOp):
        vals = [_cond(v, var, code) for v in node.values]
        return all(vals) if isinstance(node.op, ast.And) else any(vals)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _cond(node.operand, var, code)
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.left, ast.Name) \
            and node.left.id == var:
        op, vals = node.ops[0], _const_values(node.comparators[0])
        if isinstance(op, (ast.Eq, ast.In)):
            return code in vals
        if isinstance(op, (ast.NotEq, ast.NotIn)):
            return code not in vals
    raise Unparsed("condition " + ast.dump(node)[:60])


def _at(node, names, var: str, code: str):
    """The one value ``node`` emits when ``var`` holds ``code``, as ``(value, fallback)``."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "case":
        arms = [(t.elts[0], t.elts[1]) for t in node.args
                if isinstance(t, ast.Tuple) and len(t.elts) == 2]
        if len(arms) != len(node.args):
            raise Unparsed("case() arm")
        has_other = any(not (isinstance(c, ast.Constant) and c.value is True)
                        and any(v is not None for v, _ in _ev(val, names)) for c, val in arms)
        for c, val in arms:
            if _cond(c, var, code):
                v, f = _at(val, names, var, code)
                return v, f or (isinstance(c, ast.Constant) and c.value is True and has_other)
        return None, False
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        (lv, lf), (rv, rf) = _at(node.left, names, var, code), _at(node.right, names, var, code)
        if lv is None or rv is None:
            return None, lf or rf
        if lv[0] != "STR" or rv[0] != "STR":
            raise Unparsed("concatenation with a uuid5 value")
        return ("STR", _merge(lv[1] + rv[1])), lf or rf
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in (
            "str", "uuid5"):
        if node.func.id == "str" and len(node.args) == 1:
            return _at(node.args[0], names, var, code)
        if node.func.id == "uuid5" and len(node.args) == 2:
            v, f = _at(node.args[1], names, var, code)
            if v is None:
                return None, f
            return ("UUID", ast.literal_eval(node.args[0]), v[1] if v[0] == "STR" else ()), f
    ((v, f),) = _ev(node, names)  # a leaf: a constant, a {phv}, None
    return v, f


def fallback_reach(expr: str, counts_for) -> tuple[str | None, dict[str, dict[str, int]]]:
    """The observed codes that reach each fallback label of ``expr``.

    ``counts_for(phv)`` returns ``{code: rows}`` from the var_report value counts, or None.
    Returns ``(switch phv, {fallback label: {code: rows}})``; an expression with no fallback arm
    gives ``(None, {})``. Raises :class:`Unparsed` when the reach cannot be evaluated: the
    conditions test more than one variable, use a form other than ``==`` / ``!=`` / ``in`` /
    ``not in`` against literals (with ``and`` / ``or`` / ``not``), or the switch variable has no
    counts. Codes compare as text, as the var_report records them.
    """
    if not any(v.fallback for v in enumerate_ids(expr)):
        return None, {}
    src, names = _encode(expr)
    tree = ast.parse(src.strip(), mode="eval")
    switch = _switch_names(tree, names)
    if len(switch) != 1:
        raise Unparsed(f"conditions test {len(switch)} variables")
    (var,) = switch
    phv = names[var].phv
    counts = counts_for(phv)
    if not counts:
        raise Unparsed(f"no value counts for {phv}")
    out: dict[str, dict[str, int]] = {}
    for code, n in sorted(counts.items()):
        if not int(n):
            continue
        v, fb = _at(tree.body, names, var, str(code))
        if v is None or not fb:
            continue
        iv = IdValue(v[1], v[2]) if v[0] == "UUID" else IdValue(None, v[1])
        if iv.label:
            out.setdefault(iv.label, {})[str(code)] = int(n)
    return phv, out
