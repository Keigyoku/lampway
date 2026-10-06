# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lampway's own sign-in to a studio's MCP server: the standard MCP authorization, one module, a studio is CONFIGURATION.

The flow: discover the protected-resource metadata (RFC 9728: a fixed URL when the studio documents one, else the
``resource_metadata`` of the MCP server's own 401) -> the authorization server's metadata (RFC 8414) -> register a client named
"Lampway" once per redirect URI (RFC 7591) -> authorization code + S256 PKCE in the system browser, the loopback redirect on THIS
server's port -> tokens kept by a ``Session`` (a 0600 file in the state dir for Higgsfield, whose format predates Connections; the
Connections store for every studio after it).

Refresh tokens rotate, so a refresh is single-flight across processes (an fcntl lock, the session re-read after it), the start of a
refresh is written before the request, and a refresh a crash interrupted is named, never retried in a loop. Nothing here logs or
returns a code, state, verifier or token, and nothing reads another client's token (Claude Code's included)."""

import base64
import hashlib
import json
import logging
import secrets
import threading
import time
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlencode, urlsplit

import httpx

from . import logredact
from .connections import files as CF

log = logging.getLogger("lampway.mcp_oauth")

REFRESH_MARGIN_S = 120
INTERRUPTED = "the session was interrupted during a refresh: sign in again"
_UNUSABLE = {"invalid_grant", "invalid_token", "invalid_refresh_token", "refresh_token_reused", "expired_token"}


class LoginError(Exception):
    pass


class LoginDeclined(LoginError):
    pass


class NotSignedIn(Exception):
    pass


class TemporaryAuthError(Exception):
    pass


@dataclass(frozen=True)
class McpOAuthConfig:
    id: str                         # the Connections row
    label: str
    mcp_url: str
    scope: str
    callback_path: str
    page: str                       # where the person signs in again ("Connections", or a legacy page path)
    metadata_url: str = ""          # a documented protected-resource metadata URL; "" = from the MCP server's 401 (RFC 9728 5.1)
    issuer_hint: str = ""           # when the metadata names several authorization servers, the one whose URL contains this


HIGGSFIELD = McpOAuthConfig("higgsfield", "Higgsfield", "https://mcp.higgsfield.ai/mcp", "openid email offline_access", "/auth/higgsfield/callback",
                            "/app/higgsfield", metadata_url="https://mcp.higgsfield.ai/.well-known/oauth-protected-resource/mcp", issuer_hint="clerk")
HYPER3D = McpOAuthConfig("mcp:hyper3d", "Hyper3D", "https://api.hyper3d.com/api/mcp", "rodin:generate rodin:read", "/auth/hyper3d/callback",
                         "Connections")
CONFIGS = {c.id: c for c in (HIGGSFIELD, HYPER3D)}


@dataclass
class Attempt:
    url: str
    state: str
    verifier: str
    redirect_uri: str
    client_id: str


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


# ------------------------------------------------------------------------------------------------------------------ sessions
class FileSession:
    """One JSON file, 0600 in a 0700 directory (Higgsfield's ``higgsfield_auth.json``, its format unchanged)."""

    def __init__(self, path):
        self.path = Path(path)

    def read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def write(self, data: dict) -> None:
        CF.atomic_write_json(self.path, data)

    def lock(self):
        return CF.locked(self.path.with_name(f".{self.path.name}.lock"))


class StoreSession:
    """The session as one field of the Connections store (the keyring, or a 0600 file outside the Lampway home)."""

    def __init__(self, store: Callable, cid: str, lock_dir):
        self.store, self.cid, self.lock_dir = store, cid, Path(lock_dir)

    def read(self) -> dict:
        raw = self.store().get(self.cid, "session")
        try:
            data = json.loads(raw) if raw else {}
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def write(self, data: dict) -> None:
        self.store().put(self.cid, {"session": json.dumps(data)})

    def lock(self):
        return CF.locked(self.lock_dir / f"{self.cid.replace(':', '_')}.session.lock")    # not the store's own write lock: that one nests inside


# ------------------------------------------------------------------------------------------------------------------ the flow
class McpOAuth:
    MAX_PENDING = 16

    def __init__(self, config: McpOAuthConfig, session, *, http: Optional[httpx.Client] = None, redirect_port: int = 8787, clock=time.time):
        self.config, self.session = config, session
        self.http = http or httpx.Client(timeout=30.0)
        self.redirect_uri = f"http://127.0.0.1:{redirect_port}{config.callback_path}"
        self._clock = clock
        self._pending: dict[str, Attempt] = {}
        self._lock = threading.Lock()
        self._meta: Optional[dict] = None
        self._resource: Optional[str] = None

    def _read(self) -> dict:
        return self.session.read()

    def _write(self, data: dict) -> None:
        self.session.write(data)

    # ------------------------------------------------------------------------ discovery
    def _resource_metadata_url(self) -> str:
        if self.config.metadata_url:
            return self.config.metadata_url
        init = {"jsonrpc": "2.0", "id": 0, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "Lampway", "version": "1"}}}
        resp = self.http.post(self.config.mcp_url, json=init, headers={"Accept": "application/json, text/event-stream"})
        header = resp.headers.get("www-authenticate", "")
        if resp.status_code == 401 and 'resource_metadata="' in header:
            return header.split('resource_metadata="', 1)[1].split('"', 1)[0]
        u = urlsplit(self.config.mcp_url)                                     # RFC 9728 section 3: the well-known path, inserted
        return f"{u.scheme}://{u.netloc}/.well-known/oauth-protected-resource{u.path}"

    def metadata(self) -> dict:
        """The authorization server's endpoints (cached)."""
        if self._meta is None:
            try:
                prm = self.http.get(self._resource_metadata_url()).json()
                servers = prm.get("authorization_servers") or []
                issuer = next((s for s in servers if self.config.issuer_hint and self.config.issuer_hint in s), servers[0] if servers else None)
                if not issuer:
                    raise LoginError(f"{self.config.label}'s metadata names no authorization server")
                self._resource = prm.get("resource") or self.config.mcp_url
                self._meta = self._as_metadata(issuer.rstrip("/"))
            except httpx.RequestError as exc:
                raise TemporaryAuthError(f"could not reach {self.config.label} to discover its sign-in ({type(exc).__name__})") from exc
        return self._meta

    def _as_metadata(self, issuer: str) -> dict:
        u = urlsplit(issuer)
        tries = [issuer + "/.well-known/oauth-authorization-server",                               # measured on Hyper3D and Higgsfield
                 f"{u.scheme}://{u.netloc}/.well-known/oauth-authorization-server{u.path}",       # RFC 8414 section 3
                 issuer + "/.well-known/openid-configuration"]
        for url in dict.fromkeys(tries):
            r = self.http.get(url)
            if r.status_code == 200:
                try:
                    meta = r.json()
                except ValueError:
                    continue
                if meta.get("authorization_endpoint") and meta.get("token_endpoint"):
                    return meta
        raise LoginError(f"{self.config.label}'s authorization server publishes no metadata Lampway can read")

    @property
    def resource(self) -> str:
        if self._resource is None:
            self.metadata()
        return self._resource or self.config.mcp_url

    def _client_id(self) -> str:
        data = self._read()
        reg = data.get("registration") or {}
        if reg.get("redirect_uri") == self.redirect_uri and reg.get("client_id"):
            return reg["client_id"]
        meta = self.metadata()
        if not meta.get("registration_endpoint"):
            raise LoginError(f"{self.config.label} offers no dynamic client registration")
        body = {"client_name": "Lampway", "redirect_uris": [self.redirect_uri], "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"], "token_endpoint_auth_method": "none", "scope": self.config.scope}
        try:
            resp = self.http.post(meta["registration_endpoint"], json=body)
        except httpx.RequestError as exc:
            raise TemporaryAuthError(f"could not register with {self.config.label} ({type(exc).__name__})") from exc
        if resp.status_code not in (200, 201) or not resp.json().get("client_id"):
            raise LoginError(f"{self.config.label} refused the client registration (HTTP {resp.status_code})")
        data["registration"] = {"client_id": resp.json()["client_id"], "redirect_uri": self.redirect_uri}
        self._write(data)
        return data["registration"]["client_id"]

    # --------------------------------------------------------------------------- sign-in
    def start_login(self) -> Attempt:
        client_id = self._client_id()
        state, verifier = _b64(secrets.token_bytes(24)), _b64(secrets.token_bytes(48))
        params = {"response_type": "code", "client_id": client_id, "redirect_uri": self.redirect_uri, "scope": self.config.scope,
                  "resource": self.resource, "state": state, "code_challenge_method": "S256",
                  "code_challenge": _b64(hashlib.sha256(verifier.encode("ascii")).digest())}
        attempt = Attempt(f"{self.metadata()['authorization_endpoint']}?{urlencode(params)}", state, verifier, self.redirect_uri, client_id)
        self._pending[state] = attempt
        while len(self._pending) > self.MAX_PENDING:
            self._pending.pop(next(iter(self._pending)))
        return attempt

    def complete_login(self, query: dict) -> dict:
        attempt = self._pending.pop(query.get("state") or "", None)
        if attempt is None:
            raise LoginError("the callback's state does not match a sign-in attempt of ours (a stale or forged callback)")
        if query.get("error"):
            if query["error"] == "access_denied":
                raise LoginDeclined(f"{self.config.label} access was not authorized (access_denied); no code was exchanged")
            shown = "".join(ch for ch in str(query["error"])[:40] if ch.isalnum() or ch in "_-. ")
            raise LoginError(f"the sign-in returned an error: {shown}")
        if not query.get("code"):
            raise LoginError("the callback carried no authorization code")
        body = {"grant_type": "authorization_code", "client_id": attempt.client_id, "code": query["code"], "code_verifier": attempt.verifier,
                "redirect_uri": attempt.redirect_uri, "resource": self.resource}
        try:
            resp = self.http.post(self.metadata()["token_endpoint"], data=body)
        except httpx.RequestError as exc:
            raise TemporaryAuthError(f"could not reach the token endpoint: {type(exc).__name__}") from exc
        if resp.status_code != 200:
            raise LoginError(f"the code exchange failed (HTTP {resp.status_code}: {self._error_code(resp)}); start a fresh sign-in")
        with self._lock, self.session.lock():
            data = self._read()
            data.pop("interrupted", None)
            self._store(data, resp.json())
        log.info("signed in to %s", self.config.label)
        return self.status()

    def _store(self, data: dict, tok: dict, previous_refresh: Optional[str] = None) -> None:
        for v in (tok.get("access_token"), tok.get("refresh_token")):
            logredact.register_secret(v)
        data.update(access_token=tok["access_token"], refresh_token=tok.get("refresh_token") or previous_refresh,
                    expires_at=self._clock() + int(tok.get("expires_in", 3600)), scope=tok.get("scope", self.config.scope), saved_at=self._clock())
        self._write(data)

    @staticmethod
    def _error_code(resp) -> str:
        try:
            return str(resp.json().get("error") or "")
        except ValueError:
            return ""

    # --------------------------------------------------------------------- access token
    async def access_token(self) -> str:
        return await asyncio.to_thread(self._access_token_sync)

    def _access_token_sync(self, force: bool = False) -> str:
        with self._lock, self.session.lock():                        # one refresh at a time ACROSS processes: the refresh token rotates
            data = self._read()                                       # re-read after the lock: another process may have just refreshed
            if not data.get("access_token"):
                raise NotSignedIn(INTERRUPTED if data.get("interrupted") else self._not_signed_in())
            if not force and data["expires_at"] - self._clock() > REFRESH_MARGIN_S:
                logredact.register_secret(data["access_token"])
                return data["access_token"]
            return self._refresh(data)

    def _not_signed_in(self) -> str:
        if self.config.page == "Connections":
            return f"{self.config.label} is not signed in: sign in from Connections"
        return f"not signed in to {self.config.label}: open {self.config.page} on this server and choose Continue with {self.config.label}"

    def invalidate_access_token(self) -> None:
        """The server answered 401 to a token we thought valid: the next call refreshes."""
        with self._lock, self.session.lock():
            data = self._read()
            if data.get("access_token"):
                data["expires_at"] = 0
                self._write(data)

    def _refresh(self, data: dict) -> str:
        if not data.get("refresh_token"):
            raise NotSignedIn(f"the {self.config.label} session expired: sign in again")
        interrupted = (data.get("refresh_started_at") or 0) > (data.get("saved_at") or 0)
        data["refresh_started_at"] = self._clock()
        self._write(data)                                             # on disk BEFORE the request: a crash after it is named
        body = {"grant_type": "refresh_token", "client_id": (data.get("registration") or {}).get("client_id"),
                "refresh_token": data["refresh_token"], "resource": self.resource}
        try:
            resp = self.http.post(self.metadata()["token_endpoint"], data=body)
        except httpx.RequestError as exc:
            raise TemporaryAuthError(f"could not reach {self.config.label} to refresh the session ({type(exc).__name__}); credentials kept") from exc
        if resp.status_code >= 500:
            raise TemporaryAuthError(f"{self.config.label} answered HTTP {resp.status_code} to the refresh; credentials kept")
        if resp.status_code != 200:
            code = self._error_code(resp)
            if code in _UNUSABLE or resp.status_code in (400, 401):
                for k in ("access_token", "refresh_token"):
                    data.pop(k, None)
                if interrupted:
                    data["interrupted"] = True
                self._write(data)
                if interrupted:
                    raise NotSignedIn(INTERRUPTED)
                raise NotSignedIn(f"the {self.config.label} session can no longer be refreshed ({code or resp.status_code}): sign in again")
            raise TemporaryAuthError(f"the refresh failed (HTTP {resp.status_code}); credentials kept")
        data.pop("interrupted", None)
        self._store(data, resp.json(), previous_refresh=data["refresh_token"])
        return data["access_token"]

    # --------------------------------------------------------------------------- state
    def status(self) -> dict:
        data = self._read()
        return {"signed_in": bool(data.get("access_token")), "expires_at": data.get("expires_at"), "client_id": (data.get("registration") or {}).get("client_id")}

    def connection_state(self) -> dict:
        data = self._read()
        if data.get("interrupted") and not data.get("access_token"):
            return {"state": "signed_out", "next_step": INTERRUPTED}
        return {}

    def sign_out(self) -> None:
        with self._lock, self.session.lock():
            data = self._read()
            for k in ("access_token", "refresh_token", "expires_at"):
                data.pop(k, None)
            self._write(data)


def for_store(config: McpOAuthConfig, store: Callable, secrets_dir, **kw) -> McpOAuth:
    """A studio after Higgsfield: its session in the Connections store."""
    return McpOAuth(config, StoreSession(store, config.id, secrets_dir), **kw)

