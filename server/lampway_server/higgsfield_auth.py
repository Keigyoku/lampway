"""Sign in to Higgsfield's MCP server: the standard MCP authorization flow through Clerk.

Measured facts (scratch/subs/higgsfield/SPEC.md): the MCP endpoint is https://mcp.higgsfield.ai/mcp; an unauthenticated call answers 401
with a ``resource_metadata`` URL; the protected-resource metadata names Clerk (https://clerk.higgsfield.ai) as authorization server, which
offers dynamic client registration and S256 PKCE. The flow here: discover -> register a client named "Lampway" once per redirect URI ->
authorization code + PKCE in the system browser with the loopback redirect on THIS server's port -> tokens 0600 in the state dir.
Refresh tokens rotate, so one instance per server serialises every refresh. Nothing here logs a code, state, verifier or token.
"""

import base64
import hashlib
import json
import logging
import os
import secrets
import tempfile
import threading
import time
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import httpx

log = logging.getLogger("lampway.higgsfield")

MCP_URL = "https://mcp.higgsfield.ai/mcp"
METADATA_URL = "https://mcp.higgsfield.ai/.well-known/oauth-protected-resource/mcp"
SCOPE = "openid email offline_access"
CALLBACK_PATH = "/auth/higgsfield/callback"
REFRESH_MARGIN_S = 120
_UNUSABLE = {"invalid_grant", "invalid_token", "invalid_refresh_token", "refresh_token_reused", "expired_token"}


class LoginError(Exception):
    pass


class LoginDeclined(LoginError):
    pass


class NotSignedIn(Exception):
    pass


class TemporaryAuthError(Exception):
    pass


@dataclass
class Attempt:
    url: str
    state: str
    verifier: str
    redirect_uri: str
    client_id: str


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class HiggsfieldAuth:
    MAX_PENDING = 16

    def __init__(self, state_dir, *, http: Optional[httpx.Client] = None, redirect_port: int = 8787, clock=time.time):
        self.dir = Path(state_dir)
        self.http = http or httpx.Client(timeout=30.0)
        self.redirect_uri = f"http://127.0.0.1:{redirect_port}{CALLBACK_PATH}"
        self._clock = clock
        self._pending: dict[str, Attempt] = {}
        self._lock = threading.Lock()
        self._meta: Optional[dict] = None

    # ----------------------------------------------------------------- the credential file
    @property
    def path(self) -> Path:
        return self.dir / "higgsfield_auth.json"

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, data: dict) -> None:
        created = not self.dir.exists()
        self.dir.mkdir(parents=True, exist_ok=True)
        if created:
            os.chmod(self.dir, 0o700)
        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix=".higgsfield")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    # ------------------------------------------------------------------------ discovery
    def metadata(self) -> dict:
        """The authorization server's endpoints, discovered from the MCP server's protected-resource metadata (cached)."""
        if self._meta is None:
            try:
                prm = self.http.get(METADATA_URL).json()
                servers = prm.get("authorization_servers") or []
                issuer = next((s for s in servers if "clerk" in s), servers[0] if servers else None)
                if not issuer:
                    raise LoginError("Higgsfield's metadata names no authorization server")
                self._meta = self.http.get(issuer.rstrip("/") + "/.well-known/oauth-authorization-server").json()
            except httpx.RequestError as exc:
                raise TemporaryAuthError(f"could not reach Higgsfield to discover its sign-in ({type(exc).__name__})") from exc
        return self._meta

    def _client_id(self) -> str:
        data = self._read()
        reg = data.get("registration") or {}
        if reg.get("redirect_uri") == self.redirect_uri and reg.get("client_id"):
            return reg["client_id"]
        meta = self.metadata()
        body = {"client_name": "Lampway", "redirect_uris": [self.redirect_uri], "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"], "token_endpoint_auth_method": "none", "scope": SCOPE}
        try:
            resp = self.http.post(meta["registration_endpoint"], json=body)
        except httpx.RequestError as exc:
            raise TemporaryAuthError(f"could not register with Higgsfield ({type(exc).__name__})") from exc
        if resp.status_code not in (200, 201) or not resp.json().get("client_id"):
            raise LoginError(f"Higgsfield refused the client registration (HTTP {resp.status_code})")
        data["registration"] = {"client_id": resp.json()["client_id"], "redirect_uri": self.redirect_uri}
        self._write(data)
        return data["registration"]["client_id"]

    # --------------------------------------------------------------------------- sign-in
    def start_login(self) -> Attempt:
        client_id = self._client_id()
        state, verifier = _b64(secrets.token_bytes(24)), _b64(secrets.token_bytes(48))
        params = {"response_type": "code", "client_id": client_id, "redirect_uri": self.redirect_uri, "scope": SCOPE, "resource": MCP_URL,
                  "state": state, "code_challenge_method": "S256", "code_challenge": _b64(hashlib.sha256(verifier.encode("ascii")).digest())}
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
                raise LoginDeclined("Higgsfield access was not authorized (access_denied); no code was exchanged")
            shown = "".join(ch for ch in str(query["error"])[:40] if ch.isalnum() or ch in "_-. ")
            raise LoginError(f"the sign-in returned an error: {shown}")
        if not query.get("code"):
            raise LoginError("the callback carried no authorization code")
        body = {"grant_type": "authorization_code", "client_id": attempt.client_id, "code": query["code"], "code_verifier": attempt.verifier,
                "redirect_uri": attempt.redirect_uri, "resource": MCP_URL}
        try:
            resp = self.http.post(self.metadata()["token_endpoint"], data=body)
        except httpx.RequestError as exc:
            raise TemporaryAuthError(f"could not reach the token endpoint: {type(exc).__name__}") from exc
        if resp.status_code != 200:
            raise LoginError(f"the code exchange failed (HTTP {resp.status_code}: {self._error_code(resp)}); start a fresh sign-in")
        self._store(resp.json())
        log.info("signed in to Higgsfield")
        return self.status()

    def _store(self, tok: dict, previous_refresh: Optional[str] = None) -> None:
        data = self._read()
        data.update(access_token=tok["access_token"], refresh_token=tok.get("refresh_token") or previous_refresh,
                    expires_at=self._clock() + int(tok.get("expires_in", 3600)), scope=tok.get("scope", SCOPE), saved_at=int(self._clock()))
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
        with self._lock:                                           # one refresh at a time: the refresh token rotates
            data = self._read()
            if not data.get("access_token"):
                raise NotSignedIn("not signed in to Higgsfield: open /app/higgsfield on this server and choose Continue with Higgsfield")
            if not force and data["expires_at"] - self._clock() > REFRESH_MARGIN_S:
                return data["access_token"]
            return self._refresh(data)

    def invalidate_access_token(self) -> None:
        """The server answered 401 to a token we thought valid: the next call refreshes."""
        with self._lock:
            data = self._read()
            if data.get("access_token"):
                data["expires_at"] = 0
                self._write(data)

    def _refresh(self, data: dict) -> str:
        if not data.get("refresh_token"):
            raise NotSignedIn("the Higgsfield session expired: sign in again")
        body = {"grant_type": "refresh_token", "client_id": (data.get("registration") or {}).get("client_id"),
                "refresh_token": data["refresh_token"], "resource": MCP_URL}
        try:
            resp = self.http.post(self.metadata()["token_endpoint"], data=body)
        except httpx.RequestError as exc:
            raise TemporaryAuthError(f"could not reach Higgsfield to refresh the session ({type(exc).__name__}); credentials kept") from exc
        if resp.status_code >= 500:
            raise TemporaryAuthError(f"Higgsfield answered HTTP {resp.status_code} to the refresh; credentials kept")
        if resp.status_code != 200:
            code = self._error_code(resp)
            if code in _UNUSABLE or resp.status_code in (400, 401):
                for k in ("access_token", "refresh_token"):
                    data.pop(k, None)
                self._write(data)
                raise NotSignedIn(f"the Higgsfield session can no longer be refreshed ({code or resp.status_code}): sign in again")
            raise TemporaryAuthError(f"the refresh failed (HTTP {resp.status_code}); credentials kept")
        self._store(resp.json(), previous_refresh=data["refresh_token"])
        return self._read()["access_token"]

    # --------------------------------------------------------------------------- state
    def status(self) -> dict:
        data = self._read()
        return {"signed_in": bool(data.get("access_token")), "expires_at": data.get("expires_at"), "client_id": (data.get("registration") or {}).get("client_id")}

    def sign_out(self) -> None:
        with self._lock:
            data = self._read()
            for k in ("access_token", "refresh_token", "expires_at"):
                data.pop(k, None)
            self._write(data)
