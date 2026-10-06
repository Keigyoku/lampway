# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Nothing a test run or a Lampway tool makes may outlive it in the shared /tmp (a 16 GB tmpfs with a user quota: leaked Lampway homes of ~105 MB each filled it twice).

Static, by AST, over the tests and the Lampway Python: a ``tempfile.mkdtemp`` / ``mkstemp`` (never removed by itself) must say ``dir=``, and so must a
``NamedTemporaryFile(delete=False)`` (a TemporaryDirectory object, or a NamedTemporaryFile that deletes, removes itself: at close, at exit or when collected). Scripts sent INTO the binary are strings, which this
cannot read: ``tests/lampway_tools/blender_run.run_script`` points the binary's TMPDIR into the run's own temp dir, which is removed after the run
(``tests/lampway_tools/test_tmp_hygiene_live.py`` proves it in the real binary)."""
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCAN = [ROOT / "tests" / "lampway_tools", ROOT / "tests" / "lampway", ROOT / "server" / "tests", ROOT / "server" / "lampway_server",
        ROOT / "src" / "scripts" / "mixar" / "modules" / "lampway_tools"]
NEVER_CLEANED = {"mkdtemp", "mkstemp"}


def _offenders(files):
    bad = []
    for p in files:
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id == "tempfile"):
                continue
            has_dir = any(k.arg == "dir" for k in n.keywords)
            if n.func.attr in NEVER_CLEANED and not has_dir:
                bad.append(f"{p.relative_to(ROOT)}:{n.lineno}: tempfile.{n.func.attr} without dir= lands in the shared /tmp and is never removed")
            keeps = any(k.arg == "delete" and isinstance(k.value, ast.Constant) and k.value.value is False for k in n.keywords)
            if n.func.attr == "NamedTemporaryFile" and keeps and not has_dir:
                bad.append(f"{p.relative_to(ROOT)}:{n.lineno}: tempfile.NamedTemporaryFile(delete=False) without dir= is never removed")
    return bad


def test_no_temp_file_or_dir_can_leak_into_the_shared_tmp():
    files = [p for d in SCAN for p in d.rglob("*.py") if "__pycache__" not in p.parts]
    bad = _offenders(files)
    assert not bad, "\n".join(bad)


def test_the_scan_sees_a_planted_leak(tmp_path):
    (tmp_path / "x.py").write_text("import tempfile\nA = tempfile.mkdtemp(prefix='lw_home_')\nB = tempfile.NamedTemporaryFile(delete=False)\nD = tempfile.NamedTemporaryFile()\nwith tempfile.TemporaryDirectory() as d:\n    pass\nC = tempfile.mkdtemp(dir='/x')\n")
    global ROOT
    saved, ROOT = ROOT, tmp_path
    try:
        bad = _offenders([tmp_path / "x.py"])
    finally:
        ROOT = saved
    assert [b.split(":")[1] for b in bad] == ["2", "3"]


def test_both_suites_remove_a_passed_tests_tmp_path():
    import configparser
    ini = configparser.ConfigParser()
    ini.read(ROOT / "pytest.ini")
    assert ini["pytest"]["tmp_path_retention_policy"] == "failed"
    assert 'tmp_path_retention_policy = "failed"' in (ROOT / "server" / "pyproject.toml").read_text()
