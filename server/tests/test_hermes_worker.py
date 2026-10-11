# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent worker MCP admission without changing native settings or built-in toolsets."""
import asyncio
from dataclasses import replace
import importlib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import types

import pytest

from lampway_server import hermes_worker as W
from lampway_server.herdr.harnesses.base import DirectServer, PaneSpec
from lampway_server.herdr.harnesses.hermes import Hermes


@pytest.fixture
def entry(tmp_path):
    root = tmp_path / "lampway"
    return W.canonical_entry(str(tmp_path / "bin/lampway-pane-mcp"),
                             str(root / "panes/worker/mcp.json"), str(root))


@pytest.fixture
def native_version(monkeypatch):
    version = types.ModuleType("hermes_cli")
    version.__version__, version.__release_date__ = W.SUPPORTED_NATIVE
    monkeypatch.setitem(sys.modules, "hermes_cli", version)
    return version


@pytest.fixture
def native(monkeypatch, native_version):
    calls = []
    config = types.ModuleType("tools.mcp_tool_config")

    def load():
        calls.append("native-config")
        return {"terminal": {"command": "foreign"}, "lampway_pane": {"command": "impostor"}}

    config._load_mcp_config = load
    lifecycle = types.ModuleType("tools.mcp_tool_server_run")

    class MCPServerRunMixin:
        async def start(self, config):
            calls.append(("start", self.name, config))

        async def run(self, config):
            calls.append(("run", self.name, config))

    lifecycle.MCPServerRunMixin = MCPServerRunMixin
    transport = types.ModuleType("tools.mcp_tool_transport")

    class MCPServerTransportMixin:
        async def _run_stdio(self, config):
            calls.append(("_run_stdio", self.name, config))

        async def _run_http(self, config):
            calls.append(("_run_http", self.name, config))

    transport.MCPServerTransportMixin = MCPServerTransportMixin
    lifecycle.Transport = MCPServerTransportMixin
    monkeypatch.setitem(sys.modules, config.__name__, config)
    monkeypatch.setitem(sys.modules, lifecycle.__name__, lifecycle)
    monkeypatch.setitem(sys.modules, transport.__name__, transport)
    monkeypatch.setattr(sys, "meta_path", list(sys.meta_path))
    monkeypatch.setattr(sys, W._STATE, None, raising=False)
    return config, lifecycle, calls


def test_scope_replaces_only_mcp_map_and_keeps_native_loader(entry, native):
    config, lifecycle, calls = native
    klass = lifecycle.MCPServerRunMixin
    W.install(entry)
    assert lifecycle.MCPServerRunMixin is klass
    assert config._load_mcp_config() == {W.SERVER_NAME: entry}
    assert calls == ["native-config"]
    # A caller cannot mutate the next discovery/reconnect map.
    config._load_mcp_config()[W.SERVER_NAME]["env"][W.CONFIG_ENV] = "foreign"
    assert config._load_mcp_config() == {W.SERVER_NAME: entry}


@pytest.mark.parametrize("method", ["start", "run", "_run_stdio", "_run_http"])
@pytest.mark.parametrize("foreign", ["terminal", "foreign_user", "foreign_project", "same-name"])
def test_lower_admission_refuses_before_scheduling_or_transport(entry, native, method, foreign):
    _, lifecycle, calls = native
    W.install(entry)
    instance = lifecycle.Transport() if method.startswith("_") else lifecycle.MCPServerRunMixin()
    instance.name = W.SERVER_NAME if foreign == "same-name" else foreign
    config = {"command": "foreign", "args": [], "env": {}} if foreign == "same-name" else entry
    with pytest.raises(PermissionError, match="owned Lampway connector"):
        asyncio.run(getattr(instance, method)(config))
    assert calls == []


@pytest.mark.parametrize("method", ["start", "run"])
def test_exact_connector_uses_native_lifecycle_unchanged(entry, native, method):
    _, lifecycle, calls = native
    W.install(entry)
    instance = lifecycle.MCPServerRunMixin()
    instance.name = W.SERVER_NAME
    asyncio.run(getattr(instance, method)(entry))
    assert calls == [(method, W.SERVER_NAME, entry)]


def test_repeated_install_is_idempotent_and_changed_policy_refuses(entry, native):
    config, _, calls = native
    W.install(entry)
    original_wrapper = config._load_mcp_config
    W.install(entry)
    assert config._load_mcp_config is original_wrapper
    changed = {**entry, "command": "/other/lampway-pane-mcp"}
    with pytest.raises(ValueError, match="different Hermes worker MCP policy"):
        W.install(changed)
    assert calls == []


def test_unknown_native_lifecycle_fails_closed(entry, native):
    _, lifecycle, calls = native

    async def incompatible(self, config, unknown_required):
        calls.append("unsafe")

    lifecycle.MCPServerRunMixin.start = incompatible
    with pytest.raises(RuntimeError, match="unsupported Hermes MCP lifecycle API"):
        W.install(entry)
    assert calls == []


@pytest.mark.parametrize("case", ["valid", "missing-startup", "foreign-root", "foreign-python", "attached", "root-shadow"])
def test_native_tui_handoff_preserves_defaults_or_refuses_unguarded_backend(entry, native, native_version,
                                                                          tmp_path, monkeypatch, case):
    root = tmp_path / "native-source"
    root.mkdir()
    native_version.__file__ = str(root / "hermes_cli/__init__.py")
    module = types.ModuleType(W._TUI)
    calls = []

    def apply(env):
        calls.append("native-handoff")
        env.setdefault("HERMES_PYTHON", sys.executable)
        env.setdefault("HERMES_PYTHON_SRC_ROOT", str(root))
        return "native-result"

    module._apply_tui_python_env = apply
    monkeypatch.setitem(sys.modules, W._TUI, module)
    boot = str(tmp_path / "owned-startup")
    W.install(entry, owned_startup=boot)
    env = {"PYTHONPATH": boot + os.pathsep + "original-pythonpath", "HERMES_TUI_TOOLSETS": "terminal,web",
           "HERMES_TUI_PROVIDER": "synthetic-own-provider", "SYNTHETIC_PROVIDER_TOKEN": "unchanged"}
    if case == "missing-startup":
        env["PYTHONPATH"] = "foreign"
    elif case == "foreign-root":
        env["HERMES_PYTHON_SRC_ROOT"] = str(tmp_path / "foreign")
    elif case == "foreign-python":
        env["HERMES_PYTHON"] = str(tmp_path / "foreign-python")
    elif case == "attached":
        env["HERMES_TUI_GATEWAY_URL"] = "ws://127.0.0.1:9/foreign"
    elif case == "root-shadow":
        (root / "sitecustomize.py").write_text("raise AssertionError('foreign hook must not execute')\n")
    if case == "valid":
        assert module._apply_tui_python_env(env) == "native-result"
        assert env["PYTHONPATH"] == boot + os.pathsep + "original-pythonpath"
        assert env["HERMES_TUI_TOOLSETS"] == "terminal,web"
        assert env["HERMES_TUI_PROVIDER"] == "synthetic-own-provider"
        assert env["SYNTHETIC_PROVIDER_TOKEN"] == "unchanged"
    else:
        with pytest.raises(RuntimeError):
            module._apply_tui_python_env(env)
    assert calls == ["native-handoff"]


def test_admission_plant_native_without_guard_accepts_foreign(native):
    _, lifecycle, calls = native
    instance = lifecycle.MCPServerRunMixin()
    instance.name = "terminal"
    asyncio.run(instance.start({"command": "foreign"}))
    assert calls == [("start", "terminal", {"command": "foreign"})]


def test_reloaded_native_loader_stays_scoped(entry, tmp_path, monkeypatch, native_version):
    tools = types.ModuleType("tools")
    tools.__path__ = [str(tmp_path)]
    monkeypatch.setitem(sys.modules, "tools", tools)
    for name in W._TARGETS:
        monkeypatch.setitem(sys.modules, name, None)
        del sys.modules[name]
    monkeypatch.setattr(sys, "meta_path", list(sys.meta_path))
    monkeypatch.setattr(sys, W._STATE, None, raising=False)
    source = tmp_path / "mcp_tool_config.py"
    source.write_text("def _load_mcp_config(): return {'terminal': {'command': 'foreign'}}\n")
    W.install(entry)
    module = importlib.import_module("tools.mcp_tool_config")
    assert module._load_mcp_config() == {W.SERVER_NAME: entry}
    module = importlib.reload(module)
    assert module._load_mcp_config() == {W.SERVER_NAME: entry}


def _startup_run(tmp_path, entry, *, policy=None, probe=None, native_version="0.21.5"):
    boot = tmp_path / "owned-startup"
    previous = tmp_path / "native-startup"
    boot.mkdir()
    previous.mkdir()
    (boot / "sitecustomize.py").write_text(W.startup_source())
    (previous / "sitecustomize.py").write_text("import sys\nsys.native_startup_preserved = True\nNATIVE_MARKER = 'preserved'\n")
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path),
           "PYTHONPATH": os.pathsep.join((str(boot), str(previous))),
           W.POLICY_ENV: json.dumps(entry) if policy is None else policy}
    if probe is not None:
        env[W.PROBE_ENV] = probe
        source = tmp_path / "native-source"
        source.mkdir()
        env["PYTHONPATH"] += os.pathsep + str(source)
        native = source / "hermes_cli"
        native.mkdir()
        (native / "__init__.py").write_text(f"__version__={native_version!r}\n__release_date__='2026.9.24'\n")
        (native / "main_tui_launch.py").write_text("def _apply_tui_python_env(env): pass\n")
        tools = source / "tools"
        tools.mkdir()
        (tools / "__init__.py").write_text("")
        (tools / "mcp_tool_config.py").write_text("def _load_mcp_config(): return {}\n")
        for module, (klass, methods) in W._LIFECYCLES.items():
            text = f"class {klass}:\n" + "".join(f"    async def {name}(self, config): pass\n" for name in methods)
            (tools / (module.rsplit(".", 1)[1] + ".py")).write_text(text)
    return subprocess.run([sys.executable, "-c",
                           "import sys,json,sitecustomize; print(json.dumps([sys.native_startup_preserved,"
                           f" getattr(sys,{W._STATE!r}),sitecustomize.NATIVE_MARKER]))"],
                          env=env, cwd=tmp_path, text=True, capture_output=True, timeout=10)


def test_startup_chains_native_sitecustomize_without_importing_hermes(tmp_path, entry):
    result = _startup_run(tmp_path, entry)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [True, entry, "preserved"]


def test_invalid_startup_is_fatal_instead_of_pythons_fail_open(tmp_path, entry):
    result = _startup_run(tmp_path, entry, policy="malformed")
    assert result.returncode == 78
    assert result.stdout == ""
    assert "refusing unsafe startup" in result.stderr


def test_startup_probe_checks_native_seams_and_exits_before_main(tmp_path, entry):
    result = _startup_run(tmp_path, entry, probe="1")
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt == {"schema": 1, "guard": "installed", "native_version": list(W.SUPPORTED_NATIVE),
                       "python": sys.executable, "entry": entry,
                       "guard_sha256": hashlib.sha256(Path(W.__file__).read_bytes()).hexdigest(),
                       "loader": "tools.mcp_tool_config._load_mcp_config",
                       "admissions": [f"{name}.{klass}.{method}" for name, (klass, methods) in W._LIFECYCLES.items()
                                      for method in methods],
                       "gateway_handoff": "hermes_cli.main_tui_launch._apply_tui_python_env",
                       "native_package": str(tmp_path / "native-source/hermes_cli/__init__.py"),
                       "gateway_source_root": str(tmp_path / "native-source"),
                       "gateway_python": sys.executable, "source_root_hook_shadow": False}


def test_startup_probe_refuses_unknown_native_version(tmp_path, entry):
    result = _startup_run(tmp_path, entry, probe="1", native_version="future-unknown")
    assert result.returncode == 78
    assert result.stdout == ""


@pytest.mark.parametrize("mutation", ["args", "foreign-env", "relative-command", "wrong-helper", "outside-pane"])
def test_invalid_canonical_policy_fails_closed(entry, mutation):
    if mutation == "args":
        entry["args"] = ["--agent", "foreign"]
    elif mutation == "foreign-env":
        entry["env"]["AUTH_TOKEN"] = "synthetic"
    elif mutation == "relative-command":
        entry["command"] = "lampway-pane-mcp"
    elif mutation == "wrong-helper":
        entry["command"] = "/synthetic/foreign"
    else:
        entry["env"][W.CONFIG_ENV] = str(Path(entry["env"][W.ROOT_ENV]) / "settings.json")
    with pytest.raises(ValueError):
        W._validate(entry)


def test_worker_candidate_keeps_canonical_herdr_argv_and_main_unchanged(tmp_path, monkeypatch):
    adapter = Hermes()
    pane = PaneSpec(cwd=str(tmp_path), desktop=False,
                    mcp_config_path=str(tmp_path / "lampway/panes/worker/mcp.json"),
                    direct=(DirectServer("lampway", "http://127.0.0.1:9/api/v1/mcp/pane",
                                      {"X-Mixar-Session-Id": "swarm:one:worker"}, "WORKER_TOKEN", "synthetic"),))
    monkeypatch.setattr(adapter, "worker_compatibility_note", lambda: "unsupported connector-only worker startup")
    with pytest.raises(ValueError, match="connector-only worker"):
        adapter.launch(pane, task="synthetic task")
    with pytest.raises(ValueError, match="connector-only worker"):
        adapter.lampway_tools(pane)
    # Description fixtures explicitly supply a qualified preflight; no native process is launched.
    monkeypatch.setattr(adapter, "worker_compatibility_note", lambda: "")
    monkeypatch.setenv("PYTHONPATH", "synthetic-original-pythonpath")
    assert adapter.launch(pane, task="synthetic task") == ["hermes", "chat", "-q", "synthetic task"]
    wiring = adapter.lampway_tools(pane)
    assert wiring.argv == ()
    assert wiring.env["PYTHONPATH"].endswith(os.pathsep + "synthetic-original-pythonpath")
    assert "HERMES_HOME" not in wiring.env and "HERMES_PYTHON" not in wiring.env
    entry = json.loads(wiring.env[W.POLICY_ENV])
    assert set(entry["env"]) == {W.CONFIG_ENV, W.ROOT_ENV}
    assert entry["args"] == []
    body = json.loads(wiring.files[pane.mcp_config_path])
    assert body["desktop"] is None and body["binding"] == "swarm:one:worker"
    assert body["direct"][0]["headers"]["X-Mixar-Session-Id"] == "swarm:one:worker"
    main = PaneSpec(cwd=str(tmp_path), mcp_config_path=pane.mcp_config_path)
    main_wiring = adapter.lampway_tools(main)
    assert W.POLICY_ENV not in main_wiring.env
    assert "PYTHONPATH" not in main_wiring.env
    assert set(main_wiring.files) == {main.mcp_config_path}


@pytest.mark.parametrize("mutation", ["missing-config", "missing-direct", "multiple-direct", "foreign-name",
                                     "desktop-launcher", "non-swarm", "conflicting-scene"])
def test_malformed_worker_binding_refuses_before_native_probe(tmp_path, monkeypatch, mutation):
    adapter = Hermes()
    direct = DirectServer("lampway", "http://127.0.0.1:9/api/v1/mcp/pane",
                          {"X-Mixar-Session-Id": "swarm:one:worker"}, "WORKER_TOKEN", "synthetic")
    pane = PaneSpec(cwd=str(tmp_path), desktop=False,
                    mcp_config_path=str(tmp_path / "lampway/panes/worker/mcp.json"), direct=(direct,))
    changes = {
        "missing-config": {"mcp_config_path": None},
        "missing-direct": {"direct": ()},
        "multiple-direct": {"direct": (direct, direct)},
        "foreign-name": {"direct": (replace(direct, name="foreign"),)},
        "desktop-launcher": {"launcher": ("lampway-mcp",)},
        "non-swarm": {"direct": (replace(direct, headers={"X-Mixar-Session-Id": "scene:one"}),)},
        "conflicting-scene": {"scene_session_id": "scene:other"},
    }
    pane = replace(pane, **changes[mutation])
    calls = []
    monkeypatch.setattr(adapter, "worker_compatibility_note", lambda: calls.append("probe") or "")
    for action in (lambda: adapter.launch(pane, task="synthetic task"), lambda: adapter.lampway_tools(pane)):
        with pytest.raises(ValueError, match="owned direct-only swarm MCP binding"):
            action()
    assert calls == []
