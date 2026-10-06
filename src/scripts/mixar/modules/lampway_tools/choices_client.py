# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Client's door to the server's Choices (/app/choices..., specs/choices/choices_store.md 4.1). No bpy. Transport only:
every write is the user's click (ui/choices.py gates it). No answer carries an identity, a balance or a credential."""

from urllib.parse import quote, urlencode

from .studio_client import StudioClient


def _q(**kw) -> str:
    kw = {k: v for k, v in kw.items() if v}
    return ("?" + urlencode(kw)) if kw else ""


class ChoicesClient(StudioClient):
    def list(self, project=None) -> dict:
        return self._call("GET", "/app/choices" + _q(project=project), timeout=5)

    def one(self, pid: str, project=None) -> dict:
        return self._call("GET", f"/app/choices/{quote(pid, safe='')}" + _q(project=project), timeout=5)

    def proposals(self, state="open") -> dict:
        return self._call("GET", "/app/choices/proposals" + _q(state=state), timeout=5)

    def put(self, pid: str, body: dict) -> dict:
        return self._call("PUT", f"/app/choices/{quote(pid, safe='')}", body)

    def clear(self, pid: str, project=None) -> dict:
        return self._call("DELETE", f"/app/choices/{quote(pid, safe='')}" + _q(project=project))

    def accept(self, proposal_id: str, scope: str, project=None) -> dict:
        return self._call("POST", f"/app/choices/proposals/{quote(proposal_id, safe='')}/accept", {"scope": scope, "project": project})

    def decline(self, proposal_id: str) -> dict:
        return self._call("POST", f"/app/choices/proposals/{quote(proposal_id, safe='')}/decline", {})

    def acknowledge(self, option: str, private: bool) -> dict:
        return self._call("POST", "/app/choices/acknowledge", {"option": option, "private": bool(private)})
