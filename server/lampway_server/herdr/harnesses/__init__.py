# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bring Your Own Agent: one adapter per first-party harness (docs/reports/agent-modes-spec.md B1; captain's Q5 and Q6, 2026-10-06).

The starting adapters, in the order the island lists them: Claude Code, Codex CLI, Hermes Agent (the user's own, never Lampway's
engine), OpenCode, Pi, Grok and Cursor. Adding a harness is one module here and its fixture tests, never a change to herdr or the
island. The cockpit host (``herdr/host.py``) starts every harness pane through these adapters; ``switch`` is the BYOA switch.
"""
import os
from pathlib import Path

from .base import BOUND_ENV, SERVER_NAME, SESSION_HEADER, Adapter, Argv, DirectServer, HarnessAdapter, Installed, LoginState, Observer, PaneSpec, ToolWiring, mcp_entry
from .claude import Claude
from .codex import Codex
from .cursor import Cursor
from .grok import Grok
from .hermes import Hermes
from .opencode import OpenCode
from .pi import Pi
from .switch import TERMS_NOTE, enabled, require_enabled

__all__ = ["ADAPTERS", "Adapter", "Argv", "BOUND_ENV", "DirectServer", "HarnessAdapter", "Installed", "LoginState", "Observer", "PaneSpec", "SERVER_NAME", "SESSION_HEADER", "TERMS_NOTE",
           "ToolWiring", "enabled", "get", "ids", "listing", "mcp_entry", "mcp_launcher", "require_enabled"]

ADAPTERS = {a.id: a for a in (Claude(), Codex(), Hermes(), OpenCode(), Pi(), Grok(), Cursor())}


def ids() -> tuple:
    return tuple(ADAPTERS)


def get(hid: str) -> Adapter:
    try:
        return ADAPTERS[hid]
    except KeyError:
        raise KeyError(f"no harness {hid!r}: the harnesses are {', '.join(ADAPTERS)}") from None


def listing() -> list:
    """The island's "Your agent" list: every adapter, installed or not, with how to install a missing one. Runs only each found
    binary's version flag (local); never a login check (that is the user's action, inside the harness's route)."""
    rows = []
    for a in ADAPTERS.values():
        found = a.detect()
        rows.append({"id": a.id, "label": a.label, "binary": a.binary, "route": a.route, "installed": found is not None,
                     "status": "installed" if found else "not installed", "path": found.path if found else None,
                     "version": found.version if found else None, "install": None if found else a.install_hint})
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
