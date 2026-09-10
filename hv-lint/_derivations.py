"""Shared parsing of nested class_derivations for HV-Lint phases.

A nested class derivation list item can take three shapes:

    - name: Quantity        ->  ("Quantity", {"name": "Quantity", ...})
    - Quantity: {...}       ->  ("Quantity", {...})
    - Quantity:             ->  ("Quantity", {})     # null body

The last one is legal YAML that parses as ``{"Quantity": None}``; callers
expect a mapping, so it is coerced to ``{}``.

Anything else -- a non-dict item, or a mapping with several keys and no
``name`` -- is *unrecognized*. ``classify_derivation_item`` reports those as
a ``None`` class name so callers can emit a structural finding instead of
skipping in silence.
"""

from __future__ import annotations


def classify_derivation_item(cd) -> tuple[str | None, dict]:
    """Return ``(class_name, spec)`` for one class_derivations list item.

    ``class_name`` is ``None`` when the item matches none of the known forms.
    ``spec`` is always a dict so callers can index it unconditionally.
    """
    if not isinstance(cd, dict):
        return None, {}
    if "name" in cd:
        return cd.get("name"), cd
    if len(cd) == 1:
        cls_name, spec = next(iter(cd.items()))
        return cls_name, spec if isinstance(spec, dict) else {}
    return None, cd


def iter_nested_class_derivs(slot_def):
    """Yield ``(class_name, class_spec)`` for a slot's nested class derivations.

    Handles list-based class_derivations in both ``- name: X`` and dict-keyed
    ``- X: {...}`` form, plus legacy object_derivations. Unrecognized items are
    skipped -- use ``classify_derivation_item`` directly to report them.
    """
    slot_def = slot_def or {}
    for cd in slot_def.get("class_derivations") or []:
        cls_name, spec = classify_derivation_item(cd)
        if cls_name is not None:
            yield cls_name, spec
    for od in slot_def.get("object_derivations") or []:
        for name, spec in ((od or {}).get("class_derivations") or {}).items():
            yield name, spec
