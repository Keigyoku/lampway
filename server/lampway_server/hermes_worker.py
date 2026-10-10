# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Worker-only MCP admission around the user's native Hermes Python runtime.

The native CLI, its gateway, settings, provider and built-in toolsets remain native. The native
MCP loader still reads its own settings; only its returned MCP map is scoped to the worker's
owned connector. No user configuration or credentials are read here. This is an admission
wrapper for supported native APIs, not a sandbox against arbitrary Python/plugin code.
"""
from __future__ import annotations

import copy
import functools
import hashlib
import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import inspect
import json
import os
from pathlib import Path
import shutil
import sys

POLICY_ENV = "LAMPWAY_HERMES_WORKER_MCP"
PROBE_ENV = "LAMPWAY_HERMES_WORKER_PROBE"
SUPPORTED_NATIVE = ("0.21.5", "2026.9.24")
CONFIG_ENV = "LAMPWAY_HERMES_CONNECTOR_CONFIG"
ROOT_ENV = "LAMPWAY_HERMES_CONNECTOR_ROOT"
SERVER_NAME = "lampway_pane"
_LIFECYCLES = {
    "tools.mcp_tool_server_run": ("MCPServerRunMixin", ("start", "run")),
    "tools.mcp_tool_transport": ("MCPServerTransportMixin", ("_run_stdio", "_run_http")),
}
_TUI = "hermes_cli.main_tui_launch"
_TARGETS = {"tools.mcp_tool_config", _TUI, *_LIFECYCLES}
_STATE = "_lampway_hermes_worker_mcp"
_MARKER = "_lampway_worker_admission"


def canonical_entry(command: str, config: str, root: str) -> dict:
    """Describe the host's trusted helper and pane-owned file; never open either here."""
    command_path, config_path, root_path = map(Path, (command, config, root))
    if not all(path.is_absolute() for path in (command_path, config_path, root_path)):
        raise ValueError("Hermes worker connector paths must be absolute")
    if command_path.name != "lampway-pane-mcp":
        raise ValueError("Hermes workers require the installed lampway-pane-mcp helper")
    if (config_path.name != "mcp.json" or config_path.parent.parent != root_path / "panes"
            or ".." in config_path.parts or ".." in root_path.parts):
        raise ValueError("Hermes worker binding must be a pane-owned mcp.json under the Lampway root")
    return {"command": str(command_path), "args": [],
            "env": {CONFIG_ENV: str(config_path), ROOT_ENV: str(root_path)}}


def _validate(entry: object) -> dict:
    if not isinstance(entry, dict) or set(entry) != {"command", "args", "env"} or entry["args"] != []:
        raise ValueError("invalid Hermes worker MCP entry")
    env = entry["env"]
    if not isinstance(env, dict) or set(env) != {CONFIG_ENV, ROOT_ENV}:
        raise ValueError("invalid Hermes worker MCP binding environment")
    if not all(isinstance(value, str) for value in (entry["command"], env[CONFIG_ENV], env[ROOT_ENV])):
        raise ValueError("invalid Hermes worker MCP path")
    return canonical_entry(entry["command"], env[CONFIG_ENV], env[ROOT_ENV])


def _refuse_startup() -> None:
    # Python deliberately ignores exceptions from sitecustomize. Unsafe startup must not continue.
    os.write(2, b"Hermes worker MCP guard could not be installed; refusing unsafe startup.\n")
    os._exit(78)


def _native_version() -> tuple:
    native = importlib.import_module("hermes_cli")
    version = (native.__version__, native.__release_date__)
    if version != SUPPORTED_NATIVE:
        raise RuntimeError("unsupported native Hermes worker version")
    return version


def _gateway_identity(env: dict) -> dict:
    """Inspect native code/startup metadata, never native settings or credential files."""
    _native_version()
    native = sys.modules["hermes_cli"]
    package = Path(native.__file__).resolve()
    root = package.parent.parent
    if importlib.machinery.PathFinder.find_spec("sitecustomize", [str(root)]) is not None:
        raise RuntimeError("native source-root sitecustomize would shadow the Hermes worker guard")
    configured = str(env.get("HERMES_PYTHON_SRC_ROOT") or "").strip()
    if configured and os.path.realpath(configured) != str(root):
        raise RuntimeError("custom Hermes gateway source root is not qualified for worker MCP isolation")
    python = str(env.get("HERMES_PYTHON") or "").strip()
    if python:
        chosen = python if os.path.isabs(python) else shutil.which(python, path=env.get("PATH"))
        if not chosen or os.path.abspath(chosen) != os.path.abspath(sys.executable):
            raise RuntimeError("custom Hermes gateway interpreter is not qualified for worker MCP isolation")
    if str(env.get("HERMES_TUI_GATEWAY_URL") or "").strip():
        raise RuntimeError("an attached Hermes gateway does not carry this worker's MCP guard")
    return {"native_package": str(package), "gateway_source_root": str(root),
            "gateway_python": sys.executable, "source_root_hook_shadow": False}


def install(entry: dict, *, owned_startup: str | None = None) -> None:
    """Install before native imports, preserving class identity and future reloads."""
    expected = _validate(entry)
    existing = getattr(sys, _STATE, None)
    if existing is not None:
        if existing != expected:
            raise ValueError("a different Hermes worker MCP policy is already installed")
        return

    def admit(name: str, config: dict) -> None:
        if name != SERVER_NAME or config != expected:
            raise PermissionError("Hermes worker MCP is restricted to its owned Lampway connector")

    def patch(module) -> None:
        _native_version()  # Recheck at native import/reload, not just the earlier readiness probe.
        if module.__name__ == "tools.mcp_tool_config":
            original = module._load_mcp_config
            if not callable(original) or inspect.signature(original).parameters:
                raise RuntimeError("unsupported Hermes MCP config API")

            @functools.wraps(original)
            def scoped():
                original()  # Hermes alone reads its normal settings, home and portable plugins.
                return {SERVER_NAME: copy.deepcopy(expected)}

            setattr(scoped, _MARKER, expected)
            module._load_mcp_config = scoped
        elif module.__name__ == _TUI:
            original = module._apply_tui_python_env
            if tuple(inspect.signature(original).parameters) != ("env",):
                raise RuntimeError("unsupported Hermes TUI Python handoff API")

            @functools.wraps(original)
            def handoff(env):
                result = original(env)
                _gateway_identity(env)
                paths = [os.path.realpath(path or os.getcwd()) for path in env.get("PYTHONPATH", "").split(os.pathsep)]
                if not owned_startup or os.path.realpath(owned_startup) not in paths:
                    raise RuntimeError("Hermes gateway environment lost its worker startup guard")
                return result

            setattr(handoff, _MARKER, expected)
            module._apply_tui_python_env = handoff
        else:
            class_name, methods = _LIFECYCLES[module.__name__]
            klass = getattr(module, class_name)
            for name in methods:
                original = getattr(klass, name)
                if (not inspect.iscoroutinefunction(original)
                        or tuple(inspect.signature(original).parameters) != ("self", "config")):
                    raise RuntimeError("unsupported Hermes MCP lifecycle API")

                def wrap(fn):
                    @functools.wraps(fn)
                    async def guarded(self, config):
                        admit(self.name, config)  # Before scheduling, transport construction or reconnect.
                        return await fn(self, config)
                    setattr(guarded, _MARKER, expected)
                    return guarded

                setattr(klass, name, wrap(original))

    class Loader(importlib.abc.Loader):
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def create_module(self, spec):
            method = getattr(self.wrapped, "create_module", None)
            return method(spec) if method else None

        def exec_module(self, module):
            self.wrapped.exec_module(module)
            try:
                patch(module)
            except BaseException:
                _refuse_startup()

    class Finder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname not in _TARGETS:
                return None
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
            if spec is None or spec.loader is None:
                _refuse_startup()
            spec.loader = Loader(spec.loader)
            return spec

    for name in _TARGETS:
        if name in sys.modules:
            patch(sys.modules[name])
    sys.meta_path.insert(0, Finder())
    setattr(sys, _STATE, expected)


def startup(owned_startup: str) -> None:
    """Install the policy, then preserve any native/user sitecustomize on the remaining path."""
    try:
        install(json.loads(os.environ[POLICY_ENV]), owned_startup=owned_startup)
        own = os.path.realpath(owned_startup)
        paths = [path for path in sys.path if os.path.realpath(path or os.getcwd()) != own]
        spec = importlib.machinery.PathFinder.find_spec("sitecustomize", paths)
        if spec is not None and spec.loader is not None:
            module = importlib.util.module_from_spec(spec)
            sys.modules["sitecustomize"] = module
            spec.loader.exec_module(module)
        if os.environ.get(PROBE_ENV) == "1":
            version = _native_version()
            identity = _gateway_identity(os.environ)
            for name in sorted(_TARGETS):
                importlib.import_module(name)
            expected = getattr(sys, _STATE)
            admissions = []
            config = sys.modules["tools.mcp_tool_config"]
            if getattr(config._load_mcp_config, _MARKER, None) != expected:
                raise RuntimeError("missing Hermes MCP config admission")
            for name, (klass, methods) in _LIFECYCLES.items():
                for method in methods:
                    fn = getattr(getattr(sys.modules[name], klass), method)
                    if getattr(fn, _MARKER, None) != expected:
                        raise RuntimeError("missing Hermes MCP transport admission")
                    admissions.append(f"{name}.{klass}.{method}")
            handoff = sys.modules[_TUI]._apply_tui_python_env
            if getattr(handoff, _MARKER, None) != expected:
                raise RuntimeError("missing Hermes gateway environment admission")
            receipt = {"schema": 1, "guard": "installed", "native_version": list(version),
                       "python": sys.executable, "entry": expected,
                       "guard_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       "loader": "tools.mcp_tool_config._load_mcp_config", "admissions": admissions,
                       "gateway_handoff": f"{_TUI}._apply_tui_python_env", **identity}
            os.write(1, (json.dumps(receipt, separators=(",", ":")) + "\n").encode())
            os._exit(0)  # Probe ends before native main, providers, login or a frontend can run.
    except BaseException:
        _refuse_startup()


def startup_source() -> str:
    """The host writes this only into its owned pane directory, with normal 0600 permissions."""
    # REUSE-IgnoreStart
    return ("# SPDX-FileCopyrightText: 2026 Lampway contributors\n"
            "# SPDX-License-Identifier: GPL-3.0-or-later\n"
            "import importlib.util, os, sys\n"
            "try:\n"
            f"    spec = importlib.util.spec_from_file_location('lampway_hermes_worker_guard', {str(Path(__file__).resolve())!r})\n"
            "    module = importlib.util.module_from_spec(spec)\n"
            "    sys.modules[spec.name] = module\n"
            "    spec.loader.exec_module(module)\n"
            "    module.startup(os.path.dirname(__file__))\n"
            "except BaseException:\n"
            "    os.write(2, b'Hermes worker startup guard failed; refusing unsafe startup.\\n')\n"
            "    os._exit(78)\n")
    # REUSE-IgnoreEnd
