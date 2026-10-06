# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Client's door to the server's MCP inventory routes (/app/mcp/...). No bpy. Transport only: a check starts a probe, so it is the user's click (ui/operators/mcp_ops.py)."""

from .studio_client import StudioClient


class McpClient(StudioClient):
    def inventory(self, client: str = "all", scope: str = "all") -> dict:
        return self._call("GET", f"/app/mcp/inventory?client={client}&scope={scope}")

    def check(self, server_id: str) -> dict:
        return self._call("POST", "/app/mcp/check", {"id": server_id}, timeout=60)
