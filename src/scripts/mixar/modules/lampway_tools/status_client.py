# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The status bar's door to the server (facelift contract 03): three reads, nothing written. No bpy."""

from .studio_client import StudioClient


class StatusClient(StudioClient):
    def egress(self) -> dict:
        return self._call("GET", "/app/egress", timeout=2)

    def spend(self) -> dict:
        return self._call("GET", "/app/spend", timeout=2)

    def studio(self) -> dict:
        return self._call("GET", "/app/studio", timeout=2)

    def provider_settings(self) -> dict:
        return self._call("GET", "/app/provider-settings", timeout=2)
