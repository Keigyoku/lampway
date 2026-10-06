# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The canonical-asset schema module, read from the Lampway tools tree beside the server (specs/canon/normalization).

``canon_asset`` (and the JSON Schema shipped beside it) is pure python with one source of truth in the client tree; the server loads
that file by path rather than keeping a second copy. A server installed without the tree beside it cannot validate a canonical
document and says so (a canonical put is refused, a raw one still works)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[3] / "src" / "scripts" / "mixar" / "modules" / "lampway_tools"
_mod = None


class CanonUnavailable(RuntimeError):
    pass


def module():
    """The client's canon_asset module, loaded by path (with its `canon` package for the schema and the vendored validator)."""
    global _mod
    if _mod is None:
        src = _TOOLS / "canon_asset.py"
        if not src.exists():
            raise CanonUnavailable(f"the Lampway tools tree is not beside this server ({_TOOLS} missing): canonical documents cannot be validated")
        pkg = "_lampway_canon_tools"
        if pkg not in sys.modules:                                     # a stand-in package so canon_asset's relative import finds canon/
            spec = importlib.util.spec_from_file_location(pkg, _TOOLS / "canon" / "__init__.py", submodule_search_locations=[])
            p = importlib.util.module_from_spec(spec)
            p.__path__ = [str(_TOOLS)]
            sys.modules[pkg] = p
        spec = importlib.util.spec_from_file_location(f"{pkg}.canon_asset", src)
        m = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = m
        spec.loader.exec_module(m)
        _mod = m
    return _mod


def validate(doc) -> list:
    return module().validate(doc)
