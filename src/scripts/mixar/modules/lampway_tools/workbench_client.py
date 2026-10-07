# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Client's door to the server's cockpit routes (/app/workbench/...). No bpy. The transport is the Studio client's (the same stored login); this class only names the routes.
Starting and stopping the herdr server, closing a session and enabling agent sends are the USER's clicks (ui/operators/workbench_ops.py): this module is transport, not policy."""

from .studio_client import StudioClient


class WorkbenchClient(StudioClient):
    def home(self) -> dict:
        return self._call("GET", "/app/workbench")

    def start_server(self) -> dict:
        return self._call("POST", "/app/workbench/server/start", {})

    def stop_server(self, confirm: bool) -> dict:
        return self._call("POST", "/app/workbench/server/stop", {"confirm": bool(confirm)})

    def reconcile(self) -> dict:
        return self._call("POST", "/app/workbench/reconcile", {})

    def create(self, agent, name, cwd="", task="", command=None) -> dict:
        return self._call("POST", "/app/workbench/sessions", {"agent": agent, "name": name, "cwd": cwd, "task": task, "command": command})

    def screen(self, sid: str, lines: int = 70) -> str:
        return self._call("GET", f"/app/workbench/sessions/{sid}/screen?lines={int(lines)}")["screen"]

    def send(self, sid: str, text: str, submit: bool = True) -> dict:
        return self._call("POST", f"/app/workbench/sessions/{sid}/input", {"text": text, "submit": submit, "by": "user"})

    # one agent mode per scene tab (agent-modes spec M0): the island's switch
    def harnesses(self) -> dict:
        """``{"harnesses": [row...], "enabled": bool}``: every harness adapter, installed or not (version probes only)."""
        return self._call("GET", "/app/workbench/harnesses", timeout=20)

    def set_mode(self, scene_session_id: str, mode: str, harness=None, pane=None, previous=None, name=None) -> dict:
        """Bind the tab's pane (``byoa``: the picked harness, started if need be, or ``pane``) or unbind it (``runtime``)."""
        body = {"scene_session_id": scene_session_id, "mode": mode, "harness": harness, "pane": pane,
                "previous_session_id": previous, "name": name}
        return self._call("POST", "/app/workbench/mode", {k: v for k, v in body.items() if v is not None}, timeout=150)

    def close(self, sid: str, confirm: bool) -> dict:
        return self._call("POST", f"/app/workbench/sessions/{sid}/close", {"confirm": bool(confirm)})

    # the Lampway terminal (facelift contract 16)
    def terminal(self) -> dict:
        return self._call("GET", "/app/terminal")

    def terminal_get(self) -> dict:
        return self._call("POST", "/app/terminal/get", {}, timeout=900)

    def terminal_open(self, position=None) -> dict:
        return self._call("POST", "/app/terminal/open", {"position": position})

    def terminal_remove(self) -> dict:
        return self._call("POST", "/app/terminal/remove", {})
