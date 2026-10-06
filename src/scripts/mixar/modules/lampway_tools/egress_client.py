# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Client's door to the server's egress routes (/app/egress...). No bpy. Transport only: opting a route in is the user's click (ui/operators/egress_ops.py)."""

from .studio_client import StudioClient


class EgressClient(StudioClient):
    def state(self) -> dict:
        return self._call("GET", "/app/egress")

    def set_route(self, route: str, enabled: bool) -> dict:
        return self._call("POST", "/app/egress/route", {"route": route, "enabled": bool(enabled)})

    def log(self, limit: int = 20) -> list:
        return self._call("GET", f"/app/egress/log?limit={int(limit)}")["rows"]

    def export(self) -> str:
        return self._call("GET", "/app/egress/export", raw=True).decode("utf-8")
