# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Runtime environment variables: ``LAMPWAY_X`` first, ``MIXAR_X`` as a deprecated fallback for one release (rebrand M5).

Build-time knobs (MIXAR_ENV, MIXAR_CUDA, MIXAR_BACKEND_URL ... read by scripts/*.sh and generate_config.py) keep their names for builders; this is about
what the running client and native code read.
"""

import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src/scripts"))
from mixar.config import brand  # noqa: E402


def test_lampway_wins_then_the_old_name_then_the_default(capsys):
    brand._warned.clear()
    assert brand.env("AGENT_HISTORY_DIR", "d", environ={}) == "d"
    assert brand.env("AGENT_HISTORY_DIR", "d", environ={"MIXAR_AGENT_HISTORY_DIR": "old"}) == "old"
    assert brand.env("AGENT_HISTORY_DIR", "d", environ={"MIXAR_AGENT_HISTORY_DIR": "old", "LAMPWAY_AGENT_HISTORY_DIR": "new"}) == "new"
    assert brand.env("QA", None, environ={"LAMPWAY_QA": ""}) == ""        # set-but-empty is still set


def test_the_old_name_logs_one_deprecation_line_per_process(capsys):
    brand._warned.clear()
    for _ in range(3):
        brand.env("SCENES_DOSSIER_DIR", environ={"MIXAR_SCENES_DOSSIER_DIR": "x"})
    err = capsys.readouterr().err
    assert err.count("MIXAR_SCENES_DOSSIER_DIR is deprecated; use LAMPWAY_SCENES_DOSSIER_DIR") == 1


RUNTIME = ("src/scripts/mixar", "src/scripts/startup")
BUILD_TIME_OK = {"MIXAR_ENV", "MIXAR_CUDA", "MIXAR_BACKEND_URL", "MIXAR_FRONTEND_URL", "MIXAR_VERSION"}


def _is_environ(node):
    """``os.environ``, ``environ`` or ``env`` used as a mapping."""
    return (isinstance(node, ast.Attribute) and node.attr == "environ") or (isinstance(node, ast.Name) and node.id in ("environ", "env"))


def _python_direct_reads():
    """Every place a runtime ``MIXAR_*`` variable is read or named as an environment constant: environ.get/[]/getenv with that literal, or a *ENV*
    constant (``ENV_BASE_DIR = "MIXAR_..."``). The ``MIXAR_UV``/``MIXAR_ICON`` strings are Blender space/icon identifiers, not variables."""
    out = []
    for r in RUNTIME:
        for f in (ROOT / r).rglob("*.py"):
            if {"tests", "testing", "__pycache__"} & set(f.relative_to(ROOT).parts) or f.name == "brand.py":
                continue
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for n in ast.walk(tree):
                lit = None
                if isinstance(n, ast.Call) and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                    fn = n.func
                    if (isinstance(fn, ast.Attribute) and ((fn.attr == "get" and _is_environ(fn.value)) or fn.attr == "getenv")) or (isinstance(fn, ast.Name) and fn.id == "getenv"):
                        lit = n.args[0]
                elif isinstance(n, ast.Subscript) and _is_environ(n.value) and isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str):
                    lit = n.slice
                elif isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str) and any(
                        isinstance(t, ast.Name) and ("ENV" in t.id) for t in n.targets):
                    lit = n.value
                if lit is not None and re.fullmatch(r"MIXAR_[A-Z0-9_]+", lit.value) and lit.value not in BUILD_TIME_OK:
                    out.append(f"{f.relative_to(ROOT)}:{lit.lineno}: {lit.value}")
    return out


def test_no_python_module_reads_a_mixar_variable_directly():
    allowed = {"MIXAR_MCP_DISCOVERY_DIR"}      # read beside LAMPWAY_MCP_DISCOVERY_DIR in discovery.py (the model this follows)
    assert [h for h in _python_direct_reads() if h.rsplit(": ", 1)[1] not in allowed] == []


def test_every_native_getenv_of_a_mixar_variable_tries_the_lampway_one_first():
    bad = []
    for r in ("src/source", "src/intern"):
        for f in (ROOT / r).rglob("*"):
            if f.suffix not in (".cc", ".hh", ".h"):
                continue
            for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                m = re.search(r'getenv\("MIXAR_([A-Z0-9_]+)"\)', line)
                if m and f'getenv("LAMPWAY_{m.group(1)}")' not in line:
                    bad.append(f"{f.relative_to(ROOT)}:{n}")
    assert bad == []


def test_the_scan_sees_a_planted_direct_read_and_ignores_identifiers(tmp_path, monkeypatch):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "x.py").write_text('import os\nA = os.environ.get("MIXAR_FOO")\nB = os.environ["MIXAR_BAR"]\nENV_BAZ = "MIXAR_BAZ"\nC = "MIXAR_UV"\nD = os.getenv("LAMPWAY_OK")\nE = os.environ.get("MIXAR_ENV")\n')
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    monkeypatch.setattr(sys.modules[__name__], "RUNTIME", ("pkg",))
    assert sorted(h.rsplit(": ", 1)[1] for h in _python_direct_reads()) == ["MIXAR_BAR", "MIXAR_BAZ", "MIXAR_FOO"]
