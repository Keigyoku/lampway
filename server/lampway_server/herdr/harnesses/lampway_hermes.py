# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lampway's Hermes pane (`lampway_hermes`): Mode 1's adapter, for a scene's main agent and every Mode 1 swarm worker
(docs/reports/agent-modes-spec.md A0, A1).

Lampway's own wrapper, never the user's `hermes` (that one is a Mode 2 harness, ``hermes.py``; E1.10). The pane runs Lampway's
pane wrapper (``engine/hermes_pane.py``) with the server's own interpreter, by path; the wrapper starts ``hermes serve`` from the
pinned engine and Hermes's own TUI on it. Everything the wrapper needs lives in the unit's own home under the Lampway state
directory (``<state>/agent/hermes/<unit>``; a worker's under ``<unit>/workers/``), written by the server before the pane starts
(``engine/units.py``): the rendered config with Lampway's gateway and its one MCP server, the serve token in a 0600 file, and a
``pane.json`` with no secret in it. So the argv names only the wrapper and the home: no token, no task, no key.

* **No egress route of its own.** Mode 1 is Lampway's own engine: its model traffic goes only to Lampway's gateway on loopback
  and everything else through Lampway's egress proxy, which decides and logs each host under the user's own routes (E1.4, E1.5).
  So, unlike a user's harness (``byoa:<harness>``, B5), starting it is not an egress (``route = None``); the launch is declared
  ``local`` with its reason in ``egress.LAUNCHES``.
* **A worker's task** is not on its command line: the server submits it as the session's first prompt once the pane's serve is up
  (spec S2, S3), and the worker's one MCP server is the pane endpoint with its own bearer, in its own 0600 config.
* It is never in the user's "Your agent" list (``harnesses.ids()``/``listing()``) and needs no BYOA switch. The island is a live
  client of the pane's serve (A2), not an observer of a file: ``observe`` is None.
"""
import sys
from pathlib import Path

from .base import Adapter, ToolWiring, direct_binding

#: The wrapper the pane runs, by path: stdlib only, so the server's interpreter runs it whatever its working directory.
WRAPPER = Path(__file__).resolve().parents[2] / "engine" / "hermes_pane.py"


class LampwayHermes(Adapter):
    id = "lampway_hermes"
    label = "Lampway Agent (Hermes)"
    binary = "hermes"
    route = None                                  # Lampway's own engine: no byoa route (see the module docstring)
    built = True
    direct_ok = True                              # a worker's one MCP server is the pane endpoint, in its own config.yaml (S3)
    process_match = WRAPPER.name                  # what reconcile looks for among the pane's foreground processes
    interpreter = sys.executable                  # the server's own interpreter runs the wrapper

    def detect(self):
        return None                               # never the user's PATH: Lampway's pinned engine, found by the server

    def launch(self, pane, task=None):
        """The wrapper and the unit's home. ``task`` never reaches the command line: the server submits it (S2, S3)."""
        if not pane.home:
            raise ValueError("Lampway's Hermes pane needs its unit's home, which the server prepares before the pane starts")
        return [self.interpreter, str(WRAPPER), "--home", str(pane.home)]

    def resume(self, native_id, pane):
        return self.launch(pane)                  # the wrapper resumes the session its home records

    def lampway_tools(self, pane):
        return ToolWiring("hermes_config", (), {}, {}, (), pane.scene_session_id or direct_binding(pane), True,
                          "Lampway's tools are the one MCP server in the unit's own config.yaml (written by engine/units.py)")

    def observe(self, record):
        return None
