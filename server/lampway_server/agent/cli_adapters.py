"""The switch for the user's own agent CLIs in Lampway's panes (Bring Your Own Agent).

The CLI-as-model-endpoint code that lived here is gone (docs/reports/agent-modes-spec.md R0, captain's Q6, 2026-10-06): the
``claude_cli`` / ``codex_cli`` providers that flattened a transcript into ``claude -p`` / ``codex exec``, their ``TOOL_CALL`` text
protocol, and ``codex_image``. What is left is the switch the cockpit's pane spawn checks; it moves into the harness adapter
interface (spec B1) with the binary detection and the pane environment.

In BYOA Lampway starts the vendor's own, unmodified binary for the user, on the user's own login, in a pane on Lampway's herdr
server. It never reads, copies, stores or forwards that login, and never sends a model request through it (spec B0).
Off by default: switch on with ``LAMPWAY_LOCAL_CLI=1`` or ``{"enabled": true}`` in ``<state>/local_cli.json``.
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
    try:
        return json.loads((Path(state_dir) / "local_cli.json").read_text(encoding="utf-8")).get("enabled") is True
    except (OSError, ValueError):
        return False


def require_enabled(state_dir) -> None:
    if not enabled(state_dir):
        raise ValueError("your own agents in Lampway's panes are off. Switch them on with LAMPWAY_LOCAL_CLI=1 (or write "
                         "{\"enabled\": true} to " + str(Path(state_dir) / "local_cli.json") + "). " + TERMS_NOTE)
