# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Client's door to the server's Connections hub (/app/connections..., specs/connections/connections_store.md 4.1).
No bpy. Transport only: every write is the user's click (ui/connections.py gates it). A secret is sent and never kept
here; no answer of the server carries one back."""

from urllib.parse import quote

from .studio_client import StudioClient


def _id(cid: str) -> str:
    return quote(cid, safe="")


class ConnectionsClient(StudioClient):
    def list(self) -> dict:
        return self._call("GET", "/app/connections", timeout=5)

    def one(self, cid: str) -> dict:
        return self._call("GET", f"/app/connections/{_id(cid)}", timeout=5)

    def set_source(self, cid: str, mode: str, ref=None) -> dict:
        return self._call("POST", f"/app/connections/{_id(cid)}/source", {"mode": mode, **({"ref": ref} if ref else {})})

    def put_secret(self, cid: str, fields: dict) -> dict:
        return self._call("PUT", f"/app/connections/{_id(cid)}/secret", {"fields": fields})

    def test(self, cid: str) -> dict:
        return self._call("POST", f"/app/connections/{_id(cid)}/test", {})

    def signin(self, cid: str) -> dict:
        return self._call("POST", f"/app/connections/{_id(cid)}/signin", {})

    def signout(self, cid: str) -> dict:
        return self._call("POST", f"/app/connections/{_id(cid)}/signout", {})

    def forget(self, cid: str, mode: str) -> dict:
        return self._call("DELETE", f"/app/connections/{_id(cid)}/source/{quote(mode, safe='')}")

    def move_to_keyring(self, cid: str) -> dict:
        return self._call("POST", f"/app/connections/{_id(cid)}/move-to-keyring", {})
