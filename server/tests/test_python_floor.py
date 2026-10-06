"""The server declares requires-python >= 3.11 (pyproject.toml): nothing in it may need a newer Python.
Two checks: every module byte-compiles under a real 3.11 interpreter when one is on the machine (syntax, PEP 701 f-strings included), and no module calls a
standard-library API that was added after 3.11 (a named list: an interpreter-free check, so it runs everywhere; it cannot see an API it does not name)."""
import ast
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "lampway_server"
FLOOR = (3, 11)
NEWER = {("uuid", "uuid7"): "3.14", ("uuid", "uuid6"): "3.14", ("uuid", "uuid8"): "3.14", ("itertools", "batched"): "3.12", ("math", "sumprod"): "3.12",
         ("typing", "override"): "3.12", ("os", "process_cpu_count"): "3.13", ("copy", "replace"): "3.13", ("warnings", "deprecated"): "3.13",
         ("asyncio", "Runner"): "3.11", ("pathlib", "Path.walk"): "3.12", ("shutil", "rmtree.onexc"): "3.12", ("base64", "z85encode"): "3.13"}


def _modules():
    return sorted(ROOT.rglob("*.py"))


def test_no_module_calls_a_stdlib_api_newer_than_the_floor():
    bad = []
    for p in _modules():
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                v = NEWER.get((node.value.id, node.attr))
                if v and tuple(map(int, v.split("."))) > FLOOR:
                    bad.append(f"{p.relative_to(ROOT)}:{node.lineno}: {node.value.id}.{node.attr} needs Python {v}")
            if isinstance(node, ast.ImportFrom) and node.module:
                for a in node.names:
                    v = NEWER.get((node.module, a.name))
                    if v and tuple(map(int, v.split("."))) > FLOOR:
                        bad.append(f"{p.relative_to(ROOT)}:{node.lineno}: from {node.module} import {a.name} needs Python {v}")
            if (hasattr(ast, "TypeAlias") and isinstance(node, ast.TypeAlias)) or (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and getattr(node, "type_params", None)):
                bad.append(f"{p.relative_to(ROOT)}:{node.lineno}: PEP 695 syntax needs Python 3.12")
    assert not bad, "\n".join(bad)


def _floor_python():
    for name in (f"python{FLOOR[0]}.{FLOOR[1]}",):
        import pwd
        exe = shutil.which(name) or str(Path(pwd.getpwuid(os.getuid()).pw_dir) / ".local/bin" / name)        # the real home: the tests' HOME is isolated
        if Path(exe).exists():
            return exe
    return None


@pytest.mark.skipif(_floor_python() is None, reason="no python3.11 interpreter on this machine: the syntax check needs one")
def test_every_module_compiles_under_the_floor_interpreter(tmp_path):
    exe = _floor_python()
    code = ("import sys\nbad = []\nfor f in sys.argv[1:]:\n    try:\n        compile(open(f, encoding='utf-8').read(), f, 'exec')\n"
            "    except SyntaxError as e:\n        bad.append(f'{e.filename}:{e.lineno}: {e.msg}')\nprint('\\n'.join(bad)); sys.exit(1 if bad else 0)\n")
    r = subprocess.run([exe, "-c", code, *map(str, _modules())], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-1000:]


def test_the_local_uuid7_is_a_version_7_rfc_uuid_with_the_time_in_front():
    from lampway_server.library.ids import uuid7
    before = time.time_ns() // 1_000_000
    ids = [uuid7() for _ in range(5000)]
    after = time.time_ns() // 1_000_000
    u = uuid.UUID(ids[0])
    assert u.version == 7 and u.variant == uuid.RFC_4122 and len(set(ids)) == 5000
    assert before <= (u.int >> 80) <= after
