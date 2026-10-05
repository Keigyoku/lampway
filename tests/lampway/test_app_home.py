# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Per-user data lives in ONE place, under Lampway's home (rebrand finding 5), and a stock Mixar install's data is never touched.

The launcher claims "everything lives under $LAMPWAY_HOME"; about 20 modules wrote ``~/.mixar`` directly. ``mixar.config.paths.app_home()`` is the one
resolver (LAMPWAY_APP_HOME, else $LAMPWAY_HOME/app, else ~/.lampway) and ``migrate_from_mixar()`` copies, once, what a person would want to keep.
"""

import ast
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src/scripts"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import brandgate  # noqa: E402
from mixar.config import paths  # noqa: E402

CLIENT = ROOT / "src/scripts/mixar"


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for k in ("LAMPWAY_APP_HOME", "LAMPWAY_HOME"):
        monkeypatch.delenv(k, raising=False)
    return home


def test_the_resolver_order(env, monkeypatch, tmp_path):
    assert paths.app_home() == env / ".lampway"
    monkeypatch.setenv("LAMPWAY_HOME", str(tmp_path / "lh"))
    assert paths.app_home() == tmp_path / "lh" / "app"
    monkeypatch.setenv("LAMPWAY_APP_HOME", str(tmp_path / "explicit"))
    assert paths.app_home() == tmp_path / "explicit"


def _legacy(env):
    old = env / ".mixar"
    for rel, body in {"chat_history/s1.json": "{}", "chat_media/a/b.png": "png", "checkpoints/s/c.mixar": "x", "operation_history/ops.jsonl": "{}\n",
                      "scenes-dossier/d.txt": "d", "agent_history/h.json": "{}", "onboarding_seen.json": "{}",
                      "mcp/3062426.json": '{"token": "loopback-secret"}', "connector/installation.json": "{}", "auth_token.json": "bearer"}.items():
        f = old / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body)
    return old


def test_migration_copies_what_is_worth_keeping_and_nothing_secret(env, monkeypatch):
    old = _legacy(env)
    monkeypatch.setenv("LAMPWAY_HOME", str(env / "lh"))
    report = paths.migrate_from_mixar()
    new = paths.app_home()
    for kept in ("chat_history/s1.json", "chat_media/a/b.png", "checkpoints/s/c.mixar", "operation_history/ops.jsonl", "scenes-dossier/d.txt", "agent_history/h.json"):
        assert (new / kept).read_text() == (old / kept).read_text(), kept
    assert not (new / "mcp").exists() and not (new / "connector").exists() and not (new / "auth_token.json").exists()
    marker = json.loads((new / "MIGRATED-FROM-MIXAR.json").read_text())
    assert "chat_history" in marker["copied"] and "mcp" in marker["skipped"] and report["copied"] == marker["copied"]
    assert (old / "mcp/3062426.json").exists() and (old / "chat_history/s1.json").exists(), "the old install is left alone"


def test_migration_is_idempotent_and_never_overwrites(env, monkeypatch):
    _legacy(env)
    monkeypatch.setenv("LAMPWAY_HOME", str(env / "lh"))
    paths.migrate_from_mixar()
    (paths.app_home() / "chat_history/s1.json").write_text('{"mine": 1}')
    again = paths.migrate_from_mixar()
    assert again["copied"] == [] and again["already"] is True
    assert (paths.app_home() / "chat_history/s1.json").read_text() == '{"mine": 1}'


def test_only_a_lampway_launched_session_copies_silently(env, monkeypatch):
    _legacy(env)
    assert paths.migrate_if_launched_by_lampway()["copied"] == [] and not paths.app_home().exists()
    monkeypatch.setenv("LAMPWAY_HOME", str(env / "lh"))
    assert "chat_history" in paths.migrate_if_launched_by_lampway()["copied"]


def test_no_legacy_install_is_not_an_error(env):
    assert paths.migrate_from_mixar()["copied"] == []


def _dot_mixar_directory_uses(path):
    """String constants naming the ``.mixar`` DATA DIRECTORY (a join/division operand, a ``~/.mixar`` path, a *_DIR constant), not the file suffix."""
    src = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    parents = {id(c): p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
    out = []
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Constant) and isinstance(n.value, str)):
            continue
        v = n.value
        par = parents.get(id(n))
        hit = False
        if "~/.mixar" in v or "/.mixar/" in v or v.startswith(".mixar/"):
            hit = not (isinstance(par, ast.Expr))        # a docstring is prose
        elif v == ".mixar":
            if isinstance(par, ast.BinOp) and isinstance(par.op, ast.Div):
                hit = True
            elif isinstance(par, ast.Call) and any(getattr(par.func, a, "") in ("join", "joinpath", "Path") for a in ("attr", "id")):
                hit = True
            elif isinstance(par, ast.Assign) and any(isinstance(t, ast.Name) and ("DIR" in t.id or "ROOT" in t.id) for t in par.targets):
                hit = True
        if hit:
            out.append((n.lineno, src.splitlines()[n.lineno - 1].strip()))
    return out


def test_no_module_writes_to_a_dot_mixar_directory():
    allow = brandgate.load()
    offenders = []
    for f in CLIENT.rglob("*.py"):
        if {"tests", "testing", "__pycache__"} & set(f.relative_to(CLIENT).parts):
            continue
        rel = f.relative_to(ROOT).as_posix()
        offenders += [f"{rel}:{n}: {line[:90]}" for n, line in _dot_mixar_directory_uses(f) if not brandgate.is_allowed(allow, rel, line)]
    assert offenders == [], offenders


def test_the_scanner_sees_a_planted_dot_mixar_and_ignores_a_suffix(tmp_path):
    f = tmp_path / "x.py"
    f.write_text('import os\nfrom pathlib import Path\nA = os.path.join(os.path.expanduser("~"), ".mixar", "x")\nB = Path.home() / ".mixar"\nSUFFIXES = (".mixar", ".blend")\n'
                 'if p.endswith(".mixar"):\n    pass\n"""docs say ~/.mixar"""\nDATA_DIR = ".mixar"\nC = "~/.mixar/cache"\n')
    lines = sorted(n for n, _ in _dot_mixar_directory_uses(f))
    assert lines == [3, 4, 9, 10], lines
