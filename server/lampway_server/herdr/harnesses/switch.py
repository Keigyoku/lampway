# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The switch for the user's own agents in Lampway's panes (Bring Your Own Agent), moved here from ``agent/cli_adapters.py``
(agent-modes spec B1, captain's Q6). The cockpit's create route and the agent's open path both check it (B6).

In BYOA Lampway starts the vendor's own, unmodified binary for the user, on the user's own login, in a pane on Lampway's herdr
server. It never reads, copies, stores or forwards that login, and never sends a model request through it (spec B0).
Off by default: switch on with ``LAMPWAY_LOCAL_CLI=1`` or ``{"enabled": true}`` in ``<state>/local_cli.json`` (Lampway's own
state file; this module reads nothing else).
"""
import json
import os
from pathlib import Path

TERMS_NOTE = (
    "Your own agent runs as you, on its own login, in a pane on Lampway's herdr server; Lampway never reads that login and never "
    "sends a model request through it."
)


def enabled(state_dir) -> bool:
    """Off unless exactly LAMPWAY_LOCAL_CLI=1 or <state>/local_cli.json says {"enabled": true}."""
    env = os.environ.get("LAMPWAY_LOCAL_CLI")
    if env is not None:
        return env == "1"
    if state_dir is None:                               # no state directory known: only the environment switch counts
        return False
    try:
        return json.loads((Path(state_dir) / "local_cli.json").read_text(encoding="utf-8")).get("enabled") is True
    except (OSError, ValueError):
        return False


def require_enabled(state_dir) -> None:
    if not enabled(state_dir):
        raise ValueError("your own agents in Lampway's panes are off. Switch them on with LAMPWAY_LOCAL_CLI=1 (or write "
                         "{\"enabled\": true} to " + str(Path(state_dir or "<state>") / "local_cli.json") + "). " + TERMS_NOTE)
