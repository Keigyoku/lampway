# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""BYOA B2 (docs/reports/agent-modes-spec.md): a harness pane's own MCP config starts the launcher with LAMPWAY_BOUND_SESSION, and
the launcher starts pinned to that scene tab, so every tool call carries the tab's session. An explicit --session still wins."""

import asyncio
import contextlib

from mixar.modules.mcp_bridge.core import stdio_server


class RecordingConnector:
    made = []

    def __init__(self, instance, session):
        self.tasks = set()
        RecordingConnector.made.append((instance, session))

    def cancel(self, call_id=None):
        pass


class StoppedServer:
    async def run(self, read, write, options):
        return None

    def create_initialization_options(self):
        return None


@contextlib.asynccontextmanager
async def no_stdio():
    yield None, None


def _started_with(monkeypatch, env_value, session=None):
    RecordingConnector.made.clear()
    monkeypatch.setattr(stdio_server, "Connector", RecordingConnector)
    monkeypatch.setattr(stdio_server, "create_server", lambda connector: StoppedServer())
    monkeypatch.setattr(stdio_server, "stdio_server", no_stdio)
    if env_value is None:
        monkeypatch.delenv("LAMPWAY_BOUND_SESSION", raising=False)
    else:
        monkeypatch.setenv("LAMPWAY_BOUND_SESSION", env_value)
    asyncio.run(stdio_server.run(None, session))
    return RecordingConnector.made[-1]


def test_the_launcher_starts_pinned_to_the_panes_bound_scene_tab(monkeypatch):
    assert _started_with(monkeypatch, "scene-7") == (None, "scene-7")


def test_an_explicit_session_wins_and_an_empty_binding_is_unpinned(monkeypatch):
    assert _started_with(monkeypatch, "scene-7", session="scene-1") == (None, "scene-1")
    assert _started_with(monkeypatch, "") == (None, None)
    assert _started_with(monkeypatch, None) == (None, None)
