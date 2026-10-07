# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Client's door to the server's Capabilities (/app/capabilities..., docs/reports/agent-modes-spec.md E2). No bpy. Transport only:
a write is the user's click (ui/capabilities.py and the first-run walk gate it), and the server refuses an agent-origin caller as well.
Both calls give up after 5 seconds, so a server that hangs never holds Blender."""

from urllib.parse import quote, urlencode

from .studio_client import StudioClient

TIMEOUT_S = 5


class CapabilitiesClient(StudioClient):
    def capabilities(self, project=None) -> dict:
        """``{"capabilities": [row...], "proposals": [card...]}``; ``project`` makes the rows the project's effective values."""
        query = "?" + urlencode({"project": project}) if project else ""
        return self._call("GET", "/app/capabilities" + query, timeout=TIMEOUT_S)

    def set_capability(self, cid: str, enabled=None, approval=None, options=None, project=None) -> dict:
        """PUT one capability. Only what is given is sent (``enabled=False`` is given); the answer is the row as the server now has it."""
        given = {"enabled": enabled, "approval": approval, "options": options, "project": project}
        body = {k: (bool(v) if k == "enabled" else v) for k, v in given.items() if v is not None}
        return self._call("PUT", f"/app/capabilities/{quote(cid, safe='')}", body, timeout=TIMEOUT_S)
