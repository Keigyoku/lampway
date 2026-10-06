# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Client's door to the server's Studio service (/app/studio/...): plan, confirm, reject, read a job, download its files.

No bpy here. The server URL and the bearer come from the stored login (the same as the MatGen and image-slot clients), or are given
(tests). The confirm is only ever called by ``ui/operators/studio_ops.py`` after the human-click gate (human_gate.py): this module is
the transport, the gate is the policy."""

import json
import urllib.error
import urllib.request


class StudioError(RuntimeError):
    pass


def _default_url() -> str:
    from mixar.config.config import get_server_url
    return get_server_url().rstrip("/")


def _default_token() -> str:
    from mixar.modules.auth.core.auth import get_access_token
    return get_access_token()


class StudioClient:
    def __init__(self, base_url=None, token_getter=None):
        self._base = base_url
        self._token = token_getter or _default_token

    def _call(self, method, path, body=None, raw=False, timeout=60):
        token = self._token()
        if not token:
            raise StudioError("not signed in: log in to the Lampway server first")
        base = (self._base or _default_url()).rstrip("/")
        req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode("utf-8") if body is not None else None,
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("detail") or ""
            except Exception:  # noqa: BLE001
                detail = ""
            raise StudioError(detail or f"the server answered HTTP {exc.code}") from None
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise StudioError(f"the server could not be reached: {exc}") from None
        return data if raw else json.loads(data.decode("utf-8"))

    def home(self) -> dict:
        return self._call("GET", "/app/studio")

    def plan(self, action: str, args: dict) -> dict:
        return self._call("POST", "/app/studio/plan", {"action": action, "args": args or {}})

    def base(self) -> str:
        return (self._base or _default_url()).rstrip("/")

    def confirm(self, approval_id: str, price, answer=None) -> dict:
        """The user's confirm. ``price`` is the exact number shown (credits are fractional); ``answer`` only for a question."""
        body = {"price": price}
        if answer is not None:
            body["answer"] = answer
        return self._call("POST", f"/app/studio/approvals/{approval_id}/confirm", body)

    def reject(self, approval_id: str) -> dict:
        return self._call("POST", f"/app/studio/approvals/{approval_id}/reject", {})

    def job(self, job_id: str) -> dict:
        return self._call("GET", f"/app/studio/jobs/{job_id}")

    def acknowledge_hung(self, job_id: str) -> dict:
        return self._call("POST", f"/app/studio/jobs/{job_id}/acknowledge-hung", {})

    def download(self, job_id: str, name: str) -> bytes:
        return self._call("GET", f"/app/studio/jobs/{job_id}/files/{name}", raw=True, timeout=300)

    # ---- receipts: the user's two ways out of submission_unknown (docs/reports/integration.md; never an agent)
    def receipts(self, state="submission_unknown") -> list:
        return self._call("GET", f"/app/receipts?state={state}")["receipts"]

    def acknowledge_receipt(self, key: str) -> dict:
        return self._call("POST", f"/app/receipts/{key}/acknowledge", {"by": "user"})

    def link_receipt(self, key: str, provider_job_id: str) -> dict:
        return self._call("POST", f"/app/receipts/{key}/link", {"by": "user", "provider_job_id": provider_job_id})

    # ---- provider setup (the same server door)
    def provider_settings(self) -> dict:
        return self._call("GET", "/app/provider-settings")

    def save_provider_settings(self, values: dict) -> dict:
        return self._call("PUT", "/app/provider-settings", {"values": values})

    # ---- the prompt library (the same server door)
    def prompts(self, media=None) -> dict:
        return self._call("GET", "/app/prompts" + (f"?media={media}" if media else ""))

    def prompt(self, template_id: str, version=None) -> dict:
        return self._call("GET", f"/app/prompts/{template_id}" + (f"?version={version}" if version else ""))

    def render_prompt(self, template_id: str, variables: dict, model=None) -> dict:
        body = {"id": template_id, "variables": variables}
        if model:
            body["model"] = model
        return self._call("POST", "/app/prompts/render", body)

    def save_prompt(self, template: dict) -> dict:
        return self._call("PUT", "/app/prompts", {"template": template})

    def rate_prompt(self, job_id: str, rating: int, note: str = "") -> dict:
        return self._call("POST", "/app/prompts/rate", {"job_id": job_id, "rating": int(rating), "note": note})
