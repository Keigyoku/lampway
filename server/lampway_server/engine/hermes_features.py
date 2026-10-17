# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Admission hooks around Lampway's pinned native Hermes CLI, not an agent host.

Executed by path in Hermes's interpreter. Native handlers, persistence, tools,
approval handling and transports remain native. This module installs feature
admission and the owned prompt/display compatibility hooks before native entry.
"""
import functools
import hashlib
import argparse
import importlib
import importlib.abc
import importlib.machinery
import inspect
import json
import os
from pathlib import Path
import runpy
import shlex
import sys

if __package__:
    from . import hermes_prompt, hermes_history
else:  # This bootstrap is executed by path in the pinned interpreter.
    import hermes_prompt
    import hermes_history

FEATURES = frozenset({"subagents", "schedule", "background"})
READ_CRON = frozenset({"list", "pause", "remove", "delete"})
COMMANDS = {"bg": ("background",), "background": ("background",), "btw": ("background",),
            "review": ("background", "subagents"), "refine": ("background",),
            "curator": ("background",), "cron": ("schedule",), "loop": ("schedule",),
            "heartbeat": ("schedule",)}


class Policy:
    def __init__(self, home):
        self.home = Path(home)

    def config(self):
        try:
            import yaml
            value = yaml.safe_load((self.home / "config.yaml").read_text())
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}  # missing, malformed or unreadable policy is never an opt-in

    def enabled(self, feature):
        flags = self.config().get("lampway_features")
        return (isinstance(flags, dict) and not (flags.keys() - FEATURES)
                and all(type(value) is bool for value in flags.values()) and flags.get(feature) is True)

    def auxiliary(self, curator=False):
        config = self.config()
        try:
            allowed = config["curator"]["enabled"] if curator else config["auxiliary"]["background_review"]["enabled"]
        except (KeyError, TypeError):
            return False
        return self.enabled("background") and allowed is True

    def refusal(self, features):
        denied = next((feature for feature in features if not self.enabled(feature)), None)
        return f"Native Hermes {denied} is disabled in Lampway Agent preferences (untested layering)." if denied else None


def command_features(command):
    parts = str(command or "").strip().lstrip("/").lower().split(maxsplit=1)
    if not parts:
        return ()
    name = parts[0]
    if name == "hermes" and len(parts) > 1:
        return cli_features(shlex.split(parts[1]))
    return COMMANDS.get(name, ())


def cli_features(argv):
    # Never treat an ordinary chat prompt's words as CLI subcommands.
    values = {"-p", "--profile", "--cwd", "--config", "--resume", "-m", "--model", "--provider",
              "-q", "--query", "--query-file", "-z", "--oneshot"}
    skip = False
    for word in argv:
        if skip:
            skip = False
        elif word in values:
            skip = True
        elif not word.startswith("-"):
            return COMMANDS.get(word, ())
    return ()


def rpc_features(name, params):
    if name in {"prompt.background", "prompt.btw", "preview.restart"}:
        return ("background",)
    if name == "cron.manage":
        return () if params.get("action", "list") in READ_CRON else ("schedule",)
    if name == "command.dispatch":
        return command_features(f"{params.get('name', '')} {params.get('arg', '')}")
    if name == "slash.exec":
        return command_features(params.get("command"))
    if name == "cli.exec":
        return cli_features(params.get("argv") or [])
    if name == "session.control" and params.get("action") in {"loop.resume", "heartbeat.resume"}:
        return ("schedule",)
    return ()


def _rpc_guard(name, function, policy):
    if getattr(function, "_lampway_features_guarded", False):
        return function
    @functools.wraps(function)
    def guarded(rid, params):
        message = policy.refusal(rpc_features(name, params))
        if message:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32070, "message": message}}
        return function(rid, params)
    guarded._lampway_features_guarded = True
    return guarded


# Concrete pinned lower admissions. None/0/False preserve idle/no-work paths;
# side-effectful direct calls raise before any record, thread or child is made.
ENTRIES = {
    "tui_gateway.server": {"_spawn_side_agent": "background"},
    "tools.delegate_tool": {"delegate_task": "delegate"},
    "tools.cronjob_tools": {"cronjob": "cron_action", "execute_job_for_event": "schedule"},
    "cron.jobs": {"create_job": "schedule", "update_job": "cron_update", "resume_job": "schedule"},
    "cron.scheduler": {"run_job": "cron_run", "run_one_job": "cron_one",
                       "_run_external_worker_payload": "cron_one",
                       "create_job_with_scheduler_registration": "schedule"},
    "cron.scheduler_tick": {"tick": "tick", "_tick_admitted": "tick"},
    "hermes_cli.loops": {"LoopManager.set": "schedule", "LoopManager.resume": "schedule",
                         "LoopManager.fire_tick": "schedule_idle"},
    "hermes_cli.heartbeat": {"HeartbeatManager.set": "schedule", "HeartbeatManager.resume": "schedule",
                             "HeartbeatManager.due_prompt": "schedule_idle"},
    "agent.side_question": {"answer_side_question": "background"},
    "agent.review_engine": {"start_review": "review"},
    "agent.curator": {"run_curator_review": "curator", "maybe_run_curator": "curator_idle"},
    "run_agent": {"AIAgent._spawn_background_review": "auxiliary",
                  "AIAgent._spawn_background_review_now": "auxiliary"},
    "cli": {"HermesCLI.process_command": "command"},
    "hermes_cli.cli_commands_mixin": {
        "CLICommandsMixin._handle_background_command": "background",
        "CLICommandsMixin._handle_btw_command": "background",
        "CLICommandsMixin._handle_refine_command": "auxiliary",
        "CLICommandsMixin._handle_review_command": "review",
        "CLICommandsMixin._handle_cron_command": "schedule"},
    "hermes_cli.web_routers.status": {"_spawn_action": "spawn_action"},
}


def _entry_guard(function, kind, policy):
    if getattr(function, "_lampway_features_guarded", False):
        return function
    signature = inspect.signature(function)
    @functools.wraps(function)
    def guarded(*args, **kwargs):
        bound = signature.bind_partial(*args, **kwargs)
        values = bound.arguments
        if kind == "command":
            features = command_features(values.get("cmd", values.get("command", "")))
        elif kind == "spawn_action":
            features = cli_features(values.get("argv", []))
        elif kind == "delegate":
            if str(values.get("action") or "").strip().lower() in {"list", "steer", "stop"}:
                return function(*args, **kwargs)
            features = ("subagents", "background") if values.get("background") else ("subagents",)
        elif kind == "cron_action":
            features = () if str(values.get("action") or "").strip().lower() in READ_CRON else ("schedule",)
        elif kind == "cron_update":
            updates = values.get("updates")
            pausing = (isinstance(updates, dict) and updates.get("enabled") is False
                       and updates.get("state") == "paused"
                       and not (updates.keys() - {"enabled", "state", "paused_at", "paused_reason"}))
            features = () if pausing else ("schedule",)
        else:
            features = (("background", "subagents") if kind == "review" else
                        ("background",) if kind in {"background", "auxiliary", "curator", "curator_idle"} else
                        ("schedule",))
        message = policy.refusal(features)
        if kind in {"auxiliary", "curator", "curator_idle"} and not policy.auxiliary(kind.startswith("curator")):
            message = "Native auxiliary background work is disabled by Lampway's capability settings."
        if message:
            if kind in {"auxiliary", "curator_idle", "schedule_idle"}:
                return None
            if kind == "tick":
                return 0
            if kind == "cron_one":
                return False
            if kind == "cron_run":
                return False, "", "", message
            if kind in {"delegate", "cron_action"}:
                return json.dumps({"success": False, "error": message})
            if kind == "command":
                print(message)
                return True  # handled; never reinterpret a denied slash as a prompt
            raise PermissionError(message)
        return function(*args, **kwargs)
    guarded._lampway_features_guarded = True
    return guarded


NATIVE_CHILD_MODULES = {"hermes_cli.main", "tui_gateway.slash_worker", "cron.scheduler"}


def native_child_argv(argv):
    if (isinstance(argv, (list, tuple)) and len(argv) >= 3 and argv[1] == "-m"
            and argv[2] in NATIVE_CHILD_MODULES):
        return [argv[0], str(Path(__file__).resolve()), "--native-module", argv[2], *argv[3:]]
    return argv


def install_module(module, policy):
    hermes_prompt.install_module(module, policy)
    hermes_history.install_module(module)
    if module.__name__ == "tools.process_registry":
        original = module.restart_safe_gateway_child_argv
        if not getattr(original, "_lampway_features_guarded", False):
            @functools.wraps(original)
            def dispatch(command, *args, **kwargs):
                # Rewrite before native systemd wrapping; retain native scope,
                # lifetime and handoff decisions without parsing wrapper argv.
                return original(native_child_argv(command), *args, **kwargs)
            dispatch._lampway_features_guarded = True
            module.restart_safe_gateway_child_argv = dispatch
    if module.__name__ == "tui_gateway.server":
        for name, function in list(module._methods.items()):
            module._methods[name] = _rpc_guard(name, function, policy)
        if not getattr(module.register_method, "_lampway_features_guarded", False):
            original = module.register_method
            def register(name, function):
                result = original(name, _rpc_guard(name, function, policy))
                if name in {"session.history", "session.undo"}:
                    hermes_history.install_module(module)
                return result
            register._lampway_features_guarded = True
            module.register_method = register
    for path, kind in ENTRIES.get(module.__name__, {}).items():
        owner = module
        parts = path.split(".")
        for part in parts[:-1]:
            owner = getattr(owner, part)
        setattr(owner, parts[-1], _entry_guard(getattr(owner, parts[-1]), kind, policy))
    return module


class _Loader(importlib.abc.Loader):
    def __init__(self, original, policy):
        self.original, self.policy = original, policy
    def create_module(self, spec):
        return self.original.create_module(spec) if hasattr(self.original, "create_module") else None
    def exec_module(self, module):
        self.original.exec_module(module)
        install_module(module, self.policy)


class _Finder(importlib.abc.MetaPathFinder):
    def __init__(self, policy):
        self.policy = policy
    def find_spec(self, fullname, path=None, target=None):
        targets = set(ENTRIES) | hermes_prompt.MODULES | hermes_history.MODULES | {"tools.process_registry"}
        if fullname not in targets:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec and spec.loader:
            spec.loader = _Loader(spec.loader, self.policy)
        return spec


def install(policy):
    sys.meta_path.insert(0, _Finder(policy))
    for name in set(ENTRIES) | hermes_prompt.MODULES | {"tui_gateway.server", "tools.process_registry"}:
        if name in sys.modules:
            install_module(sys.modules[name], policy)
    # Exact native child module launches only: ordinary terminal/process
    # background remains native. Workers run this bootstrap before CLI imports.
    import subprocess
    original = subprocess.Popen.__init__
    if getattr(original, "_lampway_features_guarded", False):
        return
    @functools.wraps(original)
    def owned_native_child(process, args, *positional, **kwargs):
        return original(process, native_child_argv(args), *positional, **kwargs)
    owned_native_child._lampway_features_guarded = True
    # Keep the class itself: native annotations use Popen | None and Popen[T],
    # and pre-imported aliases must share this constructor admission.
    subprocess.Popen.__init__ = owned_native_child


def record_serve_bootstrap(policy):
    """Owned process identity only; this is not a retroactive old-pane fence."""
    pid = os.getpid()
    try:
        ticks = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        ticks = None
    record = {"schema": 1, "pid": pid, "start_ticks": ticks,
              "bootstrap_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    target = policy.home / "serve.features.json"
    temporary = policy.home / f".serve.features.{pid}.tmp"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(record, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 2 or args[0] not in {"--console-script", "--native-module"}:
        raise SystemExit("Lampway native bootstrap requires a pinned console script or native module.")
    mode, target, *native_args = args
    policy = Policy(os.environ.get("HERMES_HOME", "/nonexistent"))
    message = policy.refusal(("schedule",) if mode == "--native-module" and target == "cron.scheduler"
                             else cli_features(native_args))
    if message:
        raise SystemExit(message)
    install(policy)
    if native_args[:1] == ["serve"]:
        record_serve_bootstrap(policy)
    sys.argv = [target, *native_args]
    if mode == "--console-script":
        runpy.run_path(target, run_name="__main__")
    else:
        if target not in NATIVE_CHILD_MODULES:
            raise SystemExit("Unsupported native child module.")
        if target == "cron.scheduler":
            # The pinned scheduler has no main(): its two-flag __main__ block
            # calls these native functions. Import under its real name so the
            # native admissions remain installed in the external worker too.
            scheduler = importlib.import_module(target)
            if "--external-worker-file" in native_args:
                parser = argparse.ArgumentParser(add_help=False)
                parser.add_argument("--external-worker-file", type=Path, required=True)
                parser.add_argument("--ack-file", type=Path, required=True)
                arguments = parser.parse_args(native_args)
                try:
                    from hermes_logging import setup_logging
                    setup_logging(hermes_home=scheduler._get_hermes_home(), mode="cron")
                except Exception:
                    pass  # preserve the pinned worker entry's best-effort logging
                raise SystemExit(0 if scheduler._run_external_worker_payload(
                    arguments.external_worker_file, arguments.ack_file) else 1)
            scheduler.tick(verbose=True)
        else:
            runpy.run_module(target, run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
