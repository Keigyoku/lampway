# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The canon's runtime dependencies are DECLARED where they run (the coordinator, 2026-10-06: jsonschema was missing from the tools
venv and only an inline CI pip line named it):
* the server imports canon_asset (library/canon.py, every canonical Vault version) - each third-party module canon_asset and the
  schema validator import is a core server dependency in server/pyproject.toml, not an optional extra;
* docs/canon/check_canon.py's self-tests need numpy (goldens) and jsonschema (the asset schema) - declared in
  docs/canon/requirements.txt, which the canon workflow installs from."""

import ast
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LT = ROOT / "src/scripts/mixar/modules/lampway_tools"
STDLIB = set(sys.stdlib_module_names)
BLENDER = {"bpy", "bmesh", "mathutils"}                                  # Blender's own modules: scripts run inside it need no pip install


def _third_party(path):
    out = set()
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Import):
            out |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            out.add(n.module.split(".")[0])
    local = {p.stem for p in path.parent.glob("*.py")}                    # sibling modules (meshgen, reference, ...)
    return {m for m in out if m not in STDLIB and m not in BLENDER and m not in local}


def _names(reqs):
    return {re.split(r"[<>=!~;\[ ]", r.strip(), maxsplit=1)[0].lower() for r in reqs if r.strip() and not r.strip().startswith("#")}


def test_what_canon_asset_imports_is_a_core_server_dependency():
    needed = _third_party(LT / "canon_asset.py") | _third_party(LT / "canon" / "minischema.py")
    core = _names(tomllib.loads((ROOT / "server/pyproject.toml").read_text())["project"]["dependencies"])
    assert needed and needed <= core, f"canon_asset imports {sorted(needed)}; server/pyproject.toml's core dependencies lack {sorted(needed - core)}"


def test_check_canon_declares_numpy_and_jsonschema_and_ci_installs_from_the_file():
    req = ROOT / "docs/canon/requirements.txt"
    assert req.exists(), "docs/canon/requirements.txt: check_canon.py's dependencies are declared nowhere but an inline CI line"
    needed = set()
    for script in (ROOT / "docs/canon").rglob("*.py"):
        needed |= _third_party(script)
    assert {"numpy", "jsonschema"} <= needed, needed                       # the self-tests import them
    assert needed <= _names(req.read_text().splitlines()), sorted(needed - _names(req.read_text().splitlines()))
    assert "-r docs/canon/requirements.txt" in (ROOT / ".github/workflows/canon.yml").read_text()
