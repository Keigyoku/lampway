# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lampway's Hermes pane (`lampway_hermes`): Mode 1's adapter, for a scene's main agent and every Mode 1 swarm worker
(docs/reports/agent-modes-spec.md A0, A1). NOT BUILT YET: a stub that refuses to launch.

Lampway's own wrapper, never the user's `hermes` (that one is a Mode 2 harness, ``hermes.py``; E1.10): its own home under the
Lampway state directory, Lampway's model gateway, Lampway's tools. Choosing it is decided (the unit's mode picks the adapter:
``worker_adapter``); what it starts (``hermes serve`` plus Hermes's own TUI, A1) is another lane's work. Until that lands, every
path that would start it is refused with the help below, so a Mode 1 swarm never runs another way and never runs without a pane.
It is not in the user's "Your agent" list (``harnesses.ids()``/``listing()``) and needs no BYOA switch.
"""
from .base import Adapter

NOT_BUILT = "Lampway's Hermes pane (agent-modes spec A1) is not built yet"
HELP = ("every Lampway agent runs in a pane on Lampway's herdr server, and Lampway Agent's pane is not there yet, so nothing was "
        "started. To run a swarm now, switch this scene tab to Your agent in the island's agent menu and ask your own agent to start it: "
        "its workers then run in your harness's panes")


class LampwayHermes(Adapter):
    id = "lampway_hermes"
    label = "Lampway Agent (Hermes)"
    binary = "hermes"
    #: False until A1's wrapper exists: ``require_launchable`` and every argv method refuse with ``refusal()``.
    built = False

    @staticmethod
    def refusal() -> str:
        return f"{NOT_BUILT}: {HELP}"

    def detect(self):
        return None                              # never the user's PATH: Lampway's pinned engine, found by A1's wrapper

    def launch(self, pane, task=None):
        raise ValueError(self.refusal())

    def resume(self, native_id, pane):
        raise ValueError(self.refusal())

    def lampway_tools(self, pane):
        raise ValueError(self.refusal())

    def observe(self, record):
        return None
