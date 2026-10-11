# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native worker qualification requires the current complete guard receipt, not a version string."""
import hashlib
import json
import os
from pathlib import Path

import pytest

from lampway_server import hermes_worker as H
from lampway_server import native_worker_readiness as R


def receipt(entry):
    return {"schema": 1, "guard": "installed", "entry": entry,
        "native_version": list(H.SUPPORTED_NATIVE),
        "guard_sha256": hashlib.sha256(Path(H.__file__).read_bytes()).hexdigest(),
        "loader": "tools.mcp_tool_config._load_mcp_config",
        "admissions": [f"{name}.{klass}.{method}" for name, (klass, methods) in H._LIFECYCLES.items() for method in methods],
        "gateway_handoff": "hermes_cli.main_tui_launch._apply_tui_python_env",
        "native_package": "/synthetic/native/hermes_cli/__init__.py",
        "gateway_source_root": "/synthetic/native", "python": "/synthetic/python",
        "gateway_python": "/synthetic/python", "source_root_hook_shadow": False}


@pytest.mark.parametrize("field,value", [("schema", True), ("guard", "absent"),
    ("native_version", ["0.21.4", "2026.9.24"]), ("guard_sha256", "old"),
    ("entry", {}), ("admissions", []), ("gateway_handoff", "absent"),
    ("source_root_hook_shadow", True), ("gateway_source_root", "/foreign/native"),
    ("gateway_python", "/foreign/python")])
def test_partial_stale_or_foreign_receipts_refuse(field, value):
    entry = H.canonical_entry("/installed/lampway-pane-mcp", "/owned/panes/probe/mcp.json", "/owned")
    valid = receipt(entry)
    assert R._valid_receipt(valid, entry)
    valid[field] = value
    assert not R._valid_receipt(valid, entry)


def test_startup_probe_preserves_native_environment_and_removes_its_owned_hook(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("PYTHONPATH", "/native/original")
    monkeypatch.setattr(R, "pane_helper", lambda: "/installed/lampway-pane-mcp")
    monkeypatch.setattr(R, "console_interpreter", lambda binary: "/synthetic/python", raising=False)
    hooks = []
    def probe(argv, env):
        assert argv == ["/installed/hermes", "--version"]
        assert set(env) == {"PYTHONPATH", H.POLICY_ENV, H.PROBE_ENV}
        hook, original = env["PYTHONPATH"].split(os.pathsep)
        assert original == "/native/original" and env[H.PROBE_ENV] == "1"
        hooks.append(Path(hook))
        assert (Path(hook) / "sitecustomize.py").read_text() == H.startup_source()
        assert (Path(hook) / "sitecustomize.py").stat().st_mode & 0o777 == 0o600
        entry = json.loads(env[H.POLICY_ENV])
        assert not Path(entry["env"][H.CONFIG_ENV]).exists()
        return 0, json.dumps(receipt(entry))
    monkeypatch.setattr(R.L, "worker_probe", probe)
    assert R.hermes_worker_note("/installed/hermes") == ""
    assert hooks and all(not path.exists() for path in hooks)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("code,output", [(0, "Hermes 0.21.5"), (78, ""), (None, ""), (0, "{}")])
def test_version_or_missing_startup_receipt_is_not_readiness(tmp_path, monkeypatch, code, output):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr(R, "pane_helper", lambda: "/installed/lampway-pane-mcp")
    monkeypatch.setattr(R, "console_interpreter", lambda binary: "/synthetic/python", raising=False)
    monkeypatch.setattr(R.L, "worker_probe", lambda argv, env: (code, output))
    assert R.hermes_worker_note("/installed/hermes") == R.HERMES_REFUSAL
    assert list(tmp_path.iterdir()) == []


def test_outer_python_or_shell_wrapper_is_not_a_native_entry_receipt(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    wrapper = tmp_path / "hermes"
    wrapper.write_text("#!/bin/sh\npython -c 'print(0)'\n")
    wrapper.chmod(0o755)
    monkeypatch.setattr(R, "pane_helper", lambda: "/installed/lampway-pane-mcp")
    calls = []
    def intercepted(argv, env):
        calls.append(argv)
        return 0, json.dumps(receipt(json.loads(env[H.POLICY_ENV])))
    monkeypatch.setattr(R.L, "worker_probe", intercepted)
    assert R.hermes_worker_note(str(wrapper)) == R.HERMES_REFUSAL
    assert calls == []
    assert list(tmp_path.iterdir()) == [wrapper]


def test_missing_installed_helper_refuses_before_native_process(monkeypatch):
    def missing():
        raise FileNotFoundError("helper absent")
    monkeypatch.setattr(R, "pane_helper", missing)
    def forbidden(*args):
        raise AssertionError("native process before helper qualification")
    monkeypatch.setattr(R.L, "worker_probe", forbidden)
    assert R.hermes_worker_note("/installed/hermes") == R.HERMES_REFUSAL
