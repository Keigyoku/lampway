# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bring Your Own Agent: one adapter per first-party harness (docs/reports/agent-modes-spec.md B1; captain's Q5 and Q6, 2026-10-06).

The starting adapters, in the order the island lists them: Claude Code, Codex CLI, Hermes Agent (the user's own, never Lampway's
engine), OpenCode, Pi, Grok and Cursor. Adding a harness is one module here and its fixture tests, never a change to herdr or the
island. The cockpit host (``herdr/host.py``) starts every harness pane through these adapters; ``switch`` is the BYOA switch.

Beside the user's harnesses (``ADAPTERS``, Mode 2) the registry holds Lampway's own adapters (``LAMPWAY_ADAPTERS``, Mode 1, spec A0):
``lampway_hermes``, Lampway's Hermes pane (A1). They are never in the user's list, need no BYOA switch and have no byoa route. A
Lampway adapter's pane starts only on a server whose engine is wired (the cockpit's ``mode1`` hook, ``engine/units.py``); the
cockpit refuses it with help otherwise. Saved worker Choices selects a swarm worker's mode and adapter in
``SwarmManager.worker_brain``, independently of the parent unit.
"""
import os
from pathlib import Path

from .base import BOUND_ENV, SERVER_NAME, SESSION_HEADER, Adapter, Argv, DirectServer, HarnessAdapter, Installed, LoginState, Observer, PaneSpec, ToolWiring, mcp_entry
from .claude import Claude
from .codex import Codex
from .cursor import Cursor
from .grok import Grok
from .hermes import Hermes
from .lampway_hermes import LampwayHermes
from .opencode import OpenCode
from .pi import Pi
from .switch import TERMS_NOTE, enabled, require_enabled

__all__ = ["ADAPTERS", "LAMPWAY_ADAPTERS", "MODE1_ADAPTER", "MODE1_UNAVAILABLE", "Adapter", "Argv", "BOUND_ENV", "DirectServer", "HarnessAdapter", "Installed", "LoginState", "Observer", "PaneSpec", "SERVER_NAME", "SESSION_HEADER", "TERMS_NOTE",
           "ToolWiring", "enabled", "get", "ids", "is_lampway", "listing", "mcp_entry", "mcp_launcher", "require_enabled", "worker_adapter"]

#: The user's own harnesses (Mode 2, spec B1), in the order the island lists them.
ADAPTERS = {a.id: a for a in (Claude(), Codex(), Hermes(), OpenCode(), Pi(), Grok(), Cursor())}
#: Lampway's own adapters (Mode 1, spec A0, A1): never in the user's list.
LAMPWAY_ADAPTERS = {a.id: a for a in (LampwayHermes(),)}
#: Mode 1's adapter, for a scene's main agent and every Mode 1 swarm worker (spec A1).
MODE1_ADAPTER = LampwayHermes.id


def ids() -> tuple:
    """The user's harnesses (the island's "Your agent" list, the cockpit's harness kinds): never Lampway's own adapters."""
    return tuple(ADAPTERS)


def get(hid: str) -> Adapter:
    """Any registered adapter: a user's harness or one of Lampway's own."""
    try:
        return ADAPTERS[hid] if hid in ADAPTERS else LAMPWAY_ADAPTERS[hid]
    except KeyError:
        raise KeyError(f"no harness {hid!r}: the harnesses are {', '.join(ADAPTERS)}") from None


def worker_adapter(mode: str, parent_harness=None) -> str:
    """Legacy mode-to-adapter mapping retained for compatibility.

    Swarm runtime does not call this helper: it resolves saved worker Choices independently of the parent unit.
    """
    if mode == "byoa":
        if not parent_harness:
            raise ValueError("a swarm in Your agent mode runs on its parent pane's harness, and this tab has no pane bound: "
                             "pick Your agent in the island's agent menu first")
        return str(parent_harness)
    return MODE1_ADAPTER


#: Why a Lampway adapter's pane cannot start on this server, with what to do (the cockpit has no ``mode1`` hook).
MODE1_UNAVAILABLE = ("Lampway Agent runs on Lampway's pinned Hermes engine (agent-modes spec A1), and this server is not running it, "
                     "so nothing was started: build the engine with scripts/lampway/engine_env.py and restart Lampway (it runs the "
                     "engine whenever it is built); or switch this scene tab to Your agent in the island's agent menu and ask your "
                     "own agent")


def is_lampway(hid) -> bool:
    """One of Lampway's own adapters (Mode 1), never a user's harness."""
    return hid in LAMPWAY_ADAPTERS


def listing() -> list:
    """The island's "Your agent" list: every adapter, installed or not, with how to install a missing one. Runs only each found
    binary's version flag (local); never a login check (that is the user's action, inside the harness's route)."""
    rows = []
    for a in ADAPTERS.values():
        found = a.detect()
        rows.append({"id": a.id, "label": a.label, "binary": a.binary, "route": a.route, "installed": found is not None,
                     "status": "installed" if found else "not installed", "path": found.path if found else None,
                     "version": found.version if found else None, "install": None if found else a.install_hint,
                     # what a pane of it can do from the island, so the user knows before they pick it
                     "tools": a.tools_reachable, "tools_note": "" if a.tools_reachable else a.tools_note,
                     "images": a.takes_image_paths, "images_note": "" if a.takes_image_paths else a.images_note,
                     "stop": bool(a.interrupt_keys)})
    return rows


def mcp_launcher() -> tuple:
    """Lampway's MCP launcher, as the Client provisions it (mcp_bridge installation.directory(): the parent of the discovery
    directory, then connector/lampway-mcp). LAMPWAY_MCP_LAUNCHER overrides it."""
    explicit = os.environ.get("LAMPWAY_MCP_LAUNCHER")
    if explicit:
        return (explicit,)
    disc = os.environ.get("LAMPWAY_MCP_DISCOVERY_DIR") or os.environ.get("MIXAR_MCP_DISCOVERY_DIR")
    base = Path(disc).expanduser() if disc else Path.home() / ".lampway" / "mcp"
    return (str(base.parent / "connector" / "lampway-mcp"),)
