# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native entry-point admissions deny before any side-effectful handler runs."""
import types
import ast
from pathlib import Path

import pytest

from lampway_server.engine import hermes_features as F


@pytest.mark.parametrize("method,params", [
    ("prompt.background", {"text": "work"}), ("prompt.btw", {"text": "question"}),
    ("cron.manage", {"action": "add"}),
    ("command.dispatch", {"name": "/bg", "arg": "work"}),
    ("command.dispatch", {"name": "hermes", "arg": "cron run"}),
    ("slash.exec", {"command": "/review work"}),
    ("slash.exec", {"command": "/refine"}),
    ("slash.exec", {"command": "/cron create"}),
    ("cli.exec", {"argv": ["cron", "run"]}),
])
def test_default_off_refuses_registered_rpc_before_action(tmp_path, method, params):
    module = types.ModuleType("tui_gateway.server")
    actions = []
    module._methods = {method: lambda rid, args: actions.append(args) or {"result": "spawned"}}
    module._spawn_side_agent = lambda *args: actions.append("side agent")
    module.register_method = lambda name, fn: module._methods.__setitem__(name, fn)
    F.install_module(module, F.Policy(tmp_path))
    response = module._methods[method](17, params)
    assert actions == [], "native handler admission must precede every action"
    assert response["error"]["code"] == -32070


@pytest.mark.parametrize("body", ["", "[]", "lampway_features: true", "lampway_features: {background: 'true'}",
                                "lampway_features: {background: true, unknown: false}", "[:"])
def test_missing_or_malformed_policy_is_off(tmp_path, body):
    (tmp_path / "config.yaml").write_text(body)
    policy = F.Policy(tmp_path)
    assert not any(policy.enabled(name) for name in ("subagents", "schedule", "background"))


def test_registered_ordinary_calls_and_future_admissions(tmp_path):
    module = types.ModuleType("tui_gateway.server")
    calls = []
    original = lambda rid, args: calls.append(args) or {"result": "native"}
    module._methods = {"prompt.send": original, "approval.resolve": original, "session.history": original}
    module._spawn_side_agent = lambda *args: calls.append("spawn")
    module.register_method = lambda name, fn: module._methods.__setitem__(name, fn)
    F.install_module(module, F.Policy(tmp_path))
    for name in module._methods:
        assert module._methods[name](1, {}) == {"result": "native"}
    module.register_method("prompt.background", original)
    assert "error" in module._methods["prompt.background"](2, {"text": "work"})
    assert len(calls) == 3
    (tmp_path / "config.yaml").write_text("lampway_features: {background: true}")
    assert module._methods["prompt.background"](3, {}) == {"result": "native"}
    (tmp_path / "config.yaml").write_text("lampway_features: {background: 'true'}")
    assert "error" in module._methods["prompt.background"](4, {})
    assert len(calls) == 4


@pytest.mark.parametrize("module_name,path,kind", [
    (name, path, kind) for name, entries in F.ENTRIES.items() for path, kind in entries.items()
])
def test_lower_entry_denies_before_any_action(tmp_path, module_name, path, kind):
    module = types.ModuleType(module_name)
    module._methods = {}
    module.register_method = lambda name, fn: None
    calls = []
    def native(*args, action=None, background=False, cmd="/bg work", command="/bg work", argv=None):
        calls.append("native action")
        return "started"
    for entry in F.ENTRIES[module_name]:
        owner = module
        parts = entry.split(".")
        for part in parts[:-1]:
            if not hasattr(owner, part):
                setattr(owner, part, types.SimpleNamespace())
            owner = getattr(owner, part)
        setattr(owner, parts[-1], native)
    F.install_module(module, F.Policy(tmp_path))
    value = module
    for part in path.split("."):
        value = getattr(value, part)
    try:
        value(argv=["curator", "run"], cmd="/bg work")
    except PermissionError:
        pass
    assert calls == [], (module_name, path, kind)


def test_entry_names_match_the_pinned_native_source():
    root = Path(__file__).resolve().parents[2] / "third_party/hermes-agent"
    for module, entries in F.ENTRIES.items():
        source = root / (module.replace(".", "/") + ".py")
        tree = ast.parse(source.read_text())
        definitions = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        if module == "tui_gateway.server":
            definitions |= {node.name for node in ast.walk(ast.parse((root / "tui_gateway/methods_prompt.py").read_text()))
                            if isinstance(node, ast.FunctionDef)}
        assert all(path.split(".")[-1] in definitions for path in entries), module


@pytest.mark.parametrize("argv", [["chat", "-q", "cron"], ["--tui", "--resume", "background"]])
def test_ordinary_native_arguments_are_not_feature_commands(argv):
    assert F.cli_features(argv) == ()


@pytest.mark.parametrize("entry", ["AIAgent._spawn_background_review", "AIAgent._spawn_background_review_now"])
def test_manual_focused_review_cannot_bypass_auxiliary_config(tmp_path, entry):
    (tmp_path / "config.yaml").write_text("lampway_features: {background: true}\nauxiliary: {background_review: {enabled: false}}")
    module = types.ModuleType("run_agent")
    calls = []
    module.AIAgent = types.SimpleNamespace(_spawn_background_review=lambda **kw: calls.append(kw),
                                         _spawn_background_review_now=lambda **kw: calls.append(kw))
    F.install_module(module, F.Policy(tmp_path))
    assert getattr(module.AIAgent, entry.split(".")[-1])(focus="manual", explicit=True) is None
    assert calls == []


def test_serve_marker_identifies_owned_bootstrap_without_secrets(tmp_path):
    import hashlib
    import json
    import os
    F.record_serve_bootstrap(F.Policy(tmp_path))
    marker = tmp_path / "serve.features.json"
    record = json.loads(marker.read_text())
    assert record["pid"] == os.getpid() and record["schema"] == 1
    assert record["bootstrap_sha256"] == hashlib.sha256(Path(F.__file__).read_bytes()).hexdigest()
    assert marker.stat().st_mode & 0o777 == 0o600
    assert set(record) == {"schema", "pid", "start_ticks", "bootstrap_sha256"}


@pytest.mark.parametrize("feature,method,params", [
    ("background", "prompt.btw", {}), ("schedule", "cron.manage", {"action": "add"}),
    ("subagents", "ordinary", {}),
])
def test_independent_boolean_opt_in(tmp_path, feature, method, params):
    (tmp_path / "config.yaml").write_text(f"lampway_features: {{{feature}: true}}")
    policy = F.Policy(tmp_path)
    assert policy.enabled(feature)
    assert all(not policy.enabled(other) for other in F.FEATURES - {feature})
    calls = []
    if feature == "subagents":
        module = types.ModuleType("tools.delegate_tool")
        module.delegate_task = lambda goal=None, background=False: calls.append(goal) or "native"
        F.install_module(module, policy)
        assert module.delegate_task(goal="synthetic") == "native"
        assert "disabled" in module.delegate_task(goal="synthetic", background=True)
    else:
        handler = F._rpc_guard(method, lambda rid, args: calls.append(args) or "native", policy)
        assert handler(1, params) == "native"
    assert len(calls) == 1


def test_only_known_native_child_modules_are_redirected(tmp_path, monkeypatch):
    import subprocess
    import sys
    calls = []
    original_class = subprocess.Popen
    monkeypatch.setattr(subprocess, "Popen", original_class)  # restore symbol if a broken hook replaces it
    monkeypatch.setattr(original_class, "__init__", lambda self, argv, *a, **kw: calls.append(argv))
    monkeypatch.setattr(sys, "meta_path", list(sys.meta_path))
    # Existing module stubs belong to other tests; this test exercises the
    # subprocess seam without re-installing hooks into loaded native modules.
    monkeypatch.setattr(F, "ENTRIES", {})
    F.install(F.Policy(tmp_path))
    assert subprocess.Popen is original_class
    # Native serve evaluates this union at import time (web_server_messaging).
    namespace = {"subprocess": subprocess}
    exec("class NativePending:\n    proc: subprocess.Popen | None", namespace)
    assert namespace["NativePending"].__annotations__["proc"] == original_class | None
    assert subprocess.Popen[str].__origin__ is original_class
    for name in ("hermes_cli.main", "tui_gateway.slash_worker", "cron.scheduler"):
        subprocess.Popen([sys.executable, "-m", name, "synthetic"])
        assert calls[-1] == [sys.executable, str(Path(F.__file__).resolve()), "--native-module", name, "synthetic"]
    # A native module that imported Popen before installation keeps the same
    # constructor admission; class identity and aliases cannot bypass it.
    original_class([sys.executable, "-m", "cron.scheduler", "synthetic"])
    assert calls[-1][1:4] == [str(Path(F.__file__).resolve()), "--native-module", "cron.scheduler"]
    ordinary = [sys.executable, "-m", "http.server"]
    subprocess.Popen(ordinary)
    assert calls[-1] == ordinary


def test_off_external_worker_refused_before_import_or_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(F, "install", lambda policy: pytest.fail("worker admission came after import hooks"))
    with pytest.raises(SystemExit, match="schedule is disabled"):
        F.main(["--native-module", "cron.scheduler", "--external-worker-file", "missing", "--ack-file", "missing"])


@pytest.mark.parametrize("flag", ["-q", "--query", "--query-file", "-z", "--oneshot", "-m"])
def test_top_level_value_flags_do_not_turn_query_text_into_features(flag):
    assert F.cli_features([flag, "cron"]) == ()
    assert F.cli_features([flag, "background"]) == ()
    assert F.cli_features([flag, "synthetic", "cron", "run"]) == ("schedule",)


def test_native_scope_builder_wraps_owned_worker_before_systemd(tmp_path):
    import sys
    module = types.ModuleType("tools.process_registry")
    calls = []
    def native(command, **kwargs):
        calls.append((command, kwargs))
        return types.SimpleNamespace(mode="scoped", argv=["systemd-run", "--scope", *command])
    module.restart_safe_gateway_child_argv = native
    F.install_module(module, F.Policy(tmp_path))
    command = [sys.executable, "-m", "cron.scheduler", "--external-worker-file", "payload", "--ack-file", "ack"]
    options = {"unit_suffix": "synthetic", "require_restart_safe_scope": True}
    dispatch = module.restart_safe_gateway_child_argv(command, **options)
    owned = [sys.executable, str(Path(F.__file__).resolve()), "--native-module", "cron.scheduler", *command[3:]]
    assert calls == [(owned, options)]
    assert dispatch.mode == "scoped" and dispatch.argv == ["systemd-run", "--scope", *owned]
    assert command[1:3] == ["-m", "cron.scheduler"]  # caller's input is unchanged
    ordinary = [sys.executable, "-m", "http.server"]
    module.restart_safe_gateway_child_argv(ordinary, **options)
    assert calls[-1] == (ordinary, options)
