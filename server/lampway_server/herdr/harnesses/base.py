# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The harness adapter interface (docs/reports/agent-modes-spec.md B1) and the shared behaviour of the seven starting adapters.

An adapter DESCRIBES a harness: where its binary is, which argv starts or resumes it, how a pane reaches Lampway's tools and where
its session can be observed. It never reads or writes a file and never starts a process itself: the cockpit host writes the pane's
own files and herdr's launcher runs every command (the version probe and the login check included). It never opens a harness's
credential store (spec B0): ``login_state`` asks the harness's own status command, inside the harness's egress route.

Flags and paths the spec marks ``[UNVERIFIED]`` came from vendor documentation, not an installed copy; they stay marked here until
each adapter's first task, a fixture recorded from a real installed version, confirms them.
"""
import json
import os
import shutil
from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

from .. import launcher as L

Argv = list

#: The name a pane's MCP entry is listed under (the same name the Client's own connector uses: mcp_bridge constants.SERVER_NAME).
SERVER_NAME = "lampway"
#: The variable the pane's MCP launcher reads to pin its scene tab (spec B2).
BOUND_ENV = "LAMPWAY_BOUND_SESSION"


@dataclass(frozen=True)
class Installed:
    id: str
    binary: str
    path: str
    version: Optional[str]


@dataclass(frozen=True)
class LoginState:
    state: str                         # signed_in | signed_out | unknown
    detail: str = ""


@dataclass(frozen=True)
class PaneSpec:
    cwd: str
    project_root: Optional[str] = None
    effort: Optional[str] = None
    bypass: bool = False               # the user's own tick for this pane in the cockpit; never an agent's
    session_id: Optional[str] = None   # a native id Lampway picks for a new session (Claude Code's --session-id)
    scene_session_id: Optional[str] = None   # the scene tab the pane is bound to (B2); None = unbound
    mcp_config_path: Optional[str] = None    # where this pane's own MCP config lives (written by the host, under the Lampway root)
    launcher: tuple = ()               # Lampway's MCP launcher command (argv), resolved by the host


@dataclass(frozen=True)
class ToolWiring:
    kind: str                          # mcp_config_file | mcp_override | extension
    argv: tuple = ()                   # flags added to the harness's own command line
    env: dict = field(default_factory=dict)      # variables added to the pane's environment
    files: dict = field(default_factory=dict)    # path -> text: the pane's own config, written 0600 by the host before the start
    launcher: tuple = ()
    bound_session: Optional[str] = None
    verified: bool = False             # True only once a recorded fixture from an installed version showed the harness reads it
    note: str = ""


@dataclass(frozen=True)
class Observer:
    kind: str                          # session_file | rollout | store | screen
    path: Optional[str] = None
    verified: bool = False
    note: str = ""


@runtime_checkable
class HarnessAdapter(Protocol):
    id: str                                   # "claude" | "codex" | "hermes" | "opencode" | "pi" | "grok" | "cursor"
    label: str                                # shown in the island's "Your agent" list

    def detect(self) -> Optional[Installed]: ...                    # binary on PATH, version; None = not installed (install_hint says how)
    def login_state(self) -> LoginState: ...                         # from the harness's own status command; never reads its files
    def launch(self, pane: PaneSpec) -> Argv: ...                    # a new session in the project root, bound to a scene tab (B2)
    def resume(self, native_id: str, pane: PaneSpec) -> Argv: ...
    def lampway_tools(self, pane: PaneSpec) -> ToolWiring: ...       # a per-pane MCP config file and flag, or an extension for a harness without MCP
    def observe(self, record) -> Optional[Observer]: ...             # how the island reads the session (B4)
    def bypass_flag(self) -> list: ...                               # emitted only when the user ticked bypass for this pane


def _first_line(text: str) -> str:
    return next((ln.strip() for ln in (text or "").splitlines() if ln.strip()), "")[:200]


def mcp_entry(pane: PaneSpec) -> dict:
    """The one server entry every MCP-speaking harness gets: Lampway's launcher, pinned to the pane's scene tab."""
    cmd = list(pane.launcher) or ["lampway-mcp"]
    return {"command": cmd[0], "args": cmd[1:], "env": {BOUND_ENV: pane.scene_session_id or ""}}


class Adapter:
    """The behaviour every adapter shares. A subclass names its binary, its flags and its wiring."""
    id = ""
    label = ""
    binary = ""
    herdr_kind: Optional[str] = None          # herdr's own `agent start --kind` (claude, codex, opencode); the others run with `pane run`
    install_hint = ""
    version_args: tuple = ("--version",)
    status_argv: Optional[tuple] = None       # the harness's own login status command; None = none recorded, nothing runs
    api_key_connections: tuple = ()           # the Connections entries a pane receives only with the user's per-pane opt-in (B5)
    picks_session_id = False                  # Lampway chooses the native id of a new session (Claude Code's --session-id)
    config_name = "mcp.json"                  # the pane's own config file name, under <herdr root>/panes/<session id>/ (B2)
    BYPASS: tuple = ()

    def __init__(self, which=None):
        self._which = which

    @property
    def route(self) -> str:
        return f"byoa:{self.id}"

    # ------------------------------------------------------------------------------------------------- detect and login
    def _search_path(self) -> str:
        return os.environ.get("PATH", "")

    def locate(self) -> Optional[str]:
        return (self._which or shutil.which)(self.binary, path=self._search_path())

    def detect(self) -> Optional[Installed]:
        path = self.locate()
        if not path:
            return None
        code, out = L.probe([path, *self.version_args])
        return Installed(self.id, self.binary, path, _first_line(out) if code == 0 else None)

    def login_state(self) -> LoginState:
        if not self.status_argv:
            return LoginState("unknown", f"no status command is recorded for {self.label}: its own pane shows whether it is signed in")
        path = self.locate()
        if not path:
            return LoginState("unknown", f"{self.label} is not installed")
        from ... import egress as EG
        try:
            code, out = L.login_probe(self.route, [path, *self.status_argv])
        except EG.EgressRefused as exc:
            return LoginState("unknown", str(exc))
        if code is None:
            return LoginState("unknown", f"{self.label}'s status command did not answer")
        return LoginState("signed_in" if code == 0 else "signed_out", _first_line(out))       # exit status as the signal [UNVERIFIED per harness]

    # ------------------------------------------------------------------------------------------------- argv
    def _args(self, pane: PaneSpec, resume_id: Optional[str]) -> list:
        return list(self._resume_args(resume_id)) if resume_id else []

    def _resume_args(self, native_id: str) -> list:
        return ["--resume", native_id]

    def _wired(self, pane: PaneSpec) -> list:
        return list(self.lampway_tools(pane).argv) if pane.scene_session_id and pane.mcp_config_path else []

    def launch(self, pane: PaneSpec) -> Argv:
        return [self.binary, *self._args(pane, None), *self._wired(pane)]

    def resume(self, native_id: str, pane: PaneSpec) -> Argv:
        return [self.binary, *self._args(pane, native_id), *self._wired(pane)]

    def bypass_flag(self) -> list:
        return list(self.BYPASS)

    def _bypass(self, pane: PaneSpec) -> list:
        return self.bypass_flag() if pane.bypass else []

    # ------------------------------------------------------------------------------------------------- tools and observation
    def lampway_tools(self, pane: PaneSpec) -> ToolWiring:
        """Default: the pane's own mcpServers file, written for the record; no flag points the harness at it yet [UNVERIFIED]."""
        path = pane.mcp_config_path
        return ToolWiring("mcp_config_file", (), {}, {path: json.dumps({"mcpServers": {SERVER_NAME: mcp_entry(pane)}}, indent=2)} if path else {},
                          tuple(pane.launcher), pane.scene_session_id, False,
                          f"[UNVERIFIED] no per-pane MCP flag is recorded for {self.label}: the file is written beside the pane, and nothing points "
                          f"{self.binary} at it until a fixture from an installed version names the flag (the user's own config is never changed)")

    def observe(self, record) -> Optional[Observer]:
        return Observer("screen", None, True, "the pane's screen text (herdr pane read)")
