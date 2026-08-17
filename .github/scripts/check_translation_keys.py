#!/usr/bin/env python3
"""Assert every Repair translation_key used in Python exists in strings.json.

A missing entry does not raise at runtime -- Home Assistant just renders the
raw key in the Repairs UI -- so this class of bug ships silently. Hence the
CI gate.

Scope: only `translation_key=` arguments passed to `async_create_issue()`
calls are checked, and only against the top-level `issues` object.
`translation_key` is also a valid entity attribute in HA, and those resolve
against `entity.<platform>.<key>` instead; blanket-checking every literal
would produce false failures the moment an entity platform is added.
"""

from __future__ import annotations

import ast
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
COMPONENT = ROOT / "custom_components" / "plex_dashboard"
STRINGS = COMPONENT / "strings.json"


def issue_translation_keys(path: pathlib.Path) -> set[str]:
    """Return translation_key literals passed to async_create_issue in path."""
    keys: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name != "async_create_issue":
            continue
        for kw in node.keywords:
            if kw.arg == "translation_key" and isinstance(kw.value, ast.Constant):
                if isinstance(kw.value.value, str):
                    keys.add(kw.value.value)
    return keys


def main() -> int:
    declared = set(json.loads(STRINGS.read_text(encoding="utf-8")).get("issues", {}))

    used: set[str] = set()
    for py in sorted(COMPONENT.rglob("*.py")):
        used |= issue_translation_keys(py)

    missing = sorted(used - declared)
    unused = sorted(declared - used)

    for key in sorted(used):
        print(f"  ok       {key}")
    for key in unused:
        print(f"  unused   {key}  (declared in strings.json, never raised)")

    if missing:
        print(
            f"\nERROR: {len(missing)} translation_key(s) used in Python but "
            f"absent from the 'issues' object of {STRINGS.relative_to(ROOT)}:",
            file=sys.stderr,
        )
        for key in missing:
            print(f"  - {key}", file=sys.stderr)
        return 1

    print(f"\nAll {len(used)} issue translation key(s) are declared.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
