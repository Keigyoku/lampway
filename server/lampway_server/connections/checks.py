# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The free status checks (CATALOGUE.md table C). Each is a READ: one documented request through httpx (so the egress hook gates and
logs it), an MCP ``initialize`` + ``tools/list`` + one named free tool, or a CLI status command. A check never follows a redirect, has a
15 s budget, quotes no provider body, and keeps only the registry's ``show`` fields.

A result is ``(state, evidence, http_status)`` with state in connected | expired | error."""

import json
import os
import subprocess
from urllib.parse import urlsplit

import httpx

from .. import logredact

BUDGET_S = 15.0


def _shown(data, show) -> dict:
    if not isinstance(data, dict):
        return {}
    return {k: data[k] for k in show if k in data and isinstance(data[k], (str, int, float, bool, type(None), dict))}


def _verdict(status: int):
    if status in (401, 403):
        return "expired"
    if status >= 400:
        return "error"
    return "connected"


def _evidence_for(spec, body) -> dict:
    """What the hub may show, reduced by the registry's ``show`` list and turned into identity/plan/balance."""
    if spec.id == "openrouter":
        data = (body or {}).get("data") if isinstance(body, dict) else None
        shown = _shown(data or {}, spec.check.show)
        ev = {"masked": shown.get("label"), "tier": "free" if shown.get("is_free_tier") else None, "shown": shown}
        if shown.get("limit_remaining") is not None:
            ev["balance"] = {"amount": shown["limit_remaining"], "unit": "USD"}
        return ev
    if spec.group == "Studios" and spec.check.show == ("balance",):
        from ..studios.rest import shapes as SH
        name = {"studio:meshy": "meshy", "studio:hyper3d": "hyper3d", "studio:hi3d": "hi3d", "studio:tripo_api": "tripo"}[spec.id]
        try:
            amount = float(SH.STUDIOS[name].balance[2](body))
        except (KeyError, TypeError, ValueError):
            return {}
        return {"balance": {"amount": amount, "unit": "credits"}}
    return {}


def run_http(spec, cred, transport=None, base: str = "") -> tuple:
    url = spec.check.url.replace("{base}", base.rstrip("/"))
    with httpx.Client(transport=transport, timeout=BUDGET_S, follow_redirects=False) as client:
        try:
            headers = cred.headers()
            if spec.id == "anthropic":
                headers = {**headers, "anthropic-version": "2023-06-01"}
            if spec.scheme == "basic":                                    # Hi3D: the pair is read by exchanging it for a bearer
                tok = client.post(spec.check.reads[0][1], headers=headers)
                if tok.status_code >= 400:
                    return _verdict(tok.status_code), {}, tok.status_code
                try:
                    bearer = ((tok.json().get("data") or {}).get("accessToken")) or ""
                except ValueError:
                    bearer = ""
                if not bearer:
                    return "error", {"reason": "the provider issued no access token"}, tok.status_code
                logredact.register_secret(bearer)
                headers = {"Authorization": f"Bearer {bearer}"}
            resp = client.request(spec.check.method, url, headers=headers)
        except httpx.RequestError as exc:
            return "error", {"reason": f"could not reach {urlsplit(url).hostname} ({type(exc).__name__})"}, 0
        except PermissionError as exc:                                      # the egress hook refused (route off): nothing was sent
            return "error", {"reason": logredact.redact_text(str(exc))[:200]}, 0
    state = _verdict(resp.status_code)
    if state != "connected":
        return state, {"reason": f"{urlsplit(url).hostname} answered HTTP {resp.status_code}"}, resp.status_code
    try:
        body = resp.json()
    except ValueError:
        body = {}
    return "connected", _evidence_for(spec, body), resp.status_code


def run_mcp(spec, client) -> tuple:
    """``client`` speaks MCP with the connection's own sign-in: ``tools()`` (initialize + tools/list) and ``call(name)``."""
    try:
        tools = client.tools()
        ev = {"tools": len(tools)}
        if spec.check.tool:
            data = client.call(spec.check.tool, {})
            ev.update(_shown(data if isinstance(data, dict) else {}, spec.check.show))
            if spec.id == "higgsfield":
                from ..higgsfield import find_credits
                credits = find_credits(data) if isinstance(data, dict) else None
                plan = (data or {}).get("subscription_plan_type") or (data or {}).get("plan") if isinstance(data, dict) else None
                ev = {"tools": len(tools), "plan": plan}
                if credits is not None:
                    ev["balance"] = {"amount": credits, "unit": "credits"}
        return "connected", ev, 200
    except Exception as exc:  # noqa: BLE001 - the reason is a class name and a fixed phrase, never a provider body
        name = type(exc).__name__
        if name == "NotSignedIn":
            return "signed_out", {"reason": "the sign-in was refused: sign in again"}, 401
        return "error", {"reason": f"the MCP check failed ({name})"}, 0


def run_cli(spec, binary: str, env: dict, runner=subprocess.run) -> tuple:
    """A CLI status command with a 10 s timeout and a scrubbed environment; stdout parsed in memory, reduced to ``show``, dropped."""
    try:
        p = runner([binary, *spec.check.argv], capture_output=True, text=True, timeout=10, env=env)
    except FileNotFoundError:
        return "error", {"reason": f"{os.path.basename(binary)} is not installed"}, 0
    except subprocess.TimeoutExpired:
        return "error", {"reason": f"{os.path.basename(binary)} did not answer in 10 s"}, 0
    if p.returncode != 0:
        return "signed_out" if "login" in (p.stderr or "").lower() else "error", {"reason": f"{os.path.basename(binary)} exited {p.returncode}"}, 0
    try:
        data = json.loads(p.stdout or "{}")
    except ValueError:
        return "error", {"reason": f"{os.path.basename(binary)} printed something that is not JSON"}, 0
    return "connected", {"shown": _shown(data, spec.check.show)}, 0


def run_local_cdp(spec, transport=None) -> tuple:
    """The Tripo tool browser: is it up (a loopback read of CDP's version; nothing reaches Tripo)."""
    url = os.environ.get("LAMPWAY_STUDIO_CDP") or spec.check.url
    try:
        with httpx.Client(transport=transport, timeout=3.0, follow_redirects=False) as client:
            r = client.get(url if url.endswith("/json/version") else url.rstrip("/") + "/json/version")
    except httpx.RequestError:
        return "error", {"reason": "the tool browser is not running: open it from Studios"}, 0
    return ("connected", {"browser": "up"}, r.status_code) if r.status_code == 200 else ("error", {"reason": "the tool browser did not answer"}, r.status_code)

