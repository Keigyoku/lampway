"""Sign in with ChatGPT, ChatGPT plan usage: OAuth for an open-source local app, from OpenAI's DOCUMENTED flow only
(developers.openai.com/siwc/token-sharing-open-source: sign-in, profiles-and-sessions, token-reference, errors-and-recovery).
Nothing here is taken from OpenAI's DevKit (a noncommercial licence that is not GPL-compatible) and nothing reads Codex's own
tokens: the terms require OpenAI's supported sign-in flow, so this is that flow, with this app's own registered identity.

The flow: authorization code + PKCE (S256) + OIDC in the system browser with a loopback redirect
``http://127.0.0.1:<port>/auth/callback`` (our server's own port); the first registration is ``client_id=dynamic_agent_client``
with ``agent_name_hint=Lampway`` and a persistent ``ext_agent_host_id``; the callback returns the issued ``client_id``, which is
saved and used from then on; the ID token is verified against OpenAI's JWKS (signature, issuer, audience = the issued client id,
expiry, nonce); the granted scope must contain ``chatgpt.tokens.use.direct``. Access tokens last an hour; refresh tokens rotate
and refreshes are serialized.

Terms constraints held by design (openai.com/policies/sign-in-with-chatgpt-terms): tokens are stored only in this machine's state
directory (0600); requests come only from this local runtime; there is no endpoint that lets another tool use the plan; the
user can disconnect the app in ChatGPT settings; there is no silent fallback to another billing path.
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
import uuid
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlencode

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm

log = logging.getLogger("lampway.chatgpt")

ISSUER = "https://auth.openai.com"
AUTHORIZE_URL = f"{ISSUER}/api/accounts/authorize"
TOKEN_URL = f"{ISSUER}/api/accounts/oauth/token"
REVOKE_URL = f"{ISSUER}/api/accounts/oauth/revoke"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"
RESOURCE = "https://api.openai.com/v1"
DYNAMIC_CLIENT = "dynamic_agent_client"
DIRECT_SCOPE = "chatgpt.tokens.use.direct"
SCOPES = "openid profile email offline_access resource.invoke " + DIRECT_SCOPE
USAGE_URL = "https://chatgpt.com/settings/usage"
REFRESH_MARGIN_S = 120
_UNUSABLE_REFRESH = {"invalid_grant", "invalid_refresh_token", "token_expired", "refresh_token_expired",
                     "refresh_token_invalidated", "refresh_token_reused"}


class LoginError(Exception):
    pass


class LoginDeclined(LoginError):
    pass


class NotSignedIn(Exception):
    pass


class PlanUsageDisabled(Exception):
    pass


class TemporaryAuthError(Exception):
    pass


class AuthConfigError(Exception):
    pass


@dataclass
class Attempt:
    url: str
    state: str
    nonce: str
    verifier: str
    redirect_uri: str
    client_id: str
    registering: bool
    subject: Optional[str] = None


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class ChatGPTAuth:
    MAX_PENDING = 16                     # sign-in attempts kept in memory; the oldest is dropped past it

    def __init__(self, state_dir, *, http: Optional[httpx.Client] = None, app_name: str = "Lampway", redirect_port: int = 8787,
                 jwks: Optional[Callable[[], dict]] = None, clock: Callable[[], float] = time.time):
        self.dir = Path(state_dir)
        self.http = http or httpx.Client(timeout=30.0)
        self.app_name = app_name
        self.redirect_uri = f"http://127.0.0.1:{redirect_port}/auth/callback"
        self._jwks = jwks
        self._clock = clock
        self._pending: dict[str, Attempt] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------- the credential file
    @property
    def path(self) -> Path:
        return self.dir / "chatgpt_auth.json"

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
        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix=".chatgpt")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def host_id(self) -> str:
        """The stable id of this host (the documented ext_agent_host_id), chosen once and kept."""
        data = self._read()
        if not data.get("host_id"):
            data["host_id"] = f"urn:uuid:{uuid.uuid4()}"
            self._write(data)
        return data["host_id"]

    def _account(self, data=None):
        data = data if data is not None else self._read()
        cid = data.get("selected")
        return data, cid, (data.get("accounts") or {}).get(cid) if cid else None

    # ------------------------------------------------------------- sign-in
    def start_login(self) -> Attempt:
        """Build the authorization request. The caller opens ``attempt.url`` in the system browser; the callback is
        ``redirect_uri`` on this server (complete_login)."""
        host = self.host_id()
        data, cid, acct = self._account()
        state, nonce, verifier = _b64(secrets.token_bytes(24)), _b64(secrets.token_bytes(24)), _b64(secrets.token_bytes(48))
        params = {"response_type": "code", "redirect_uri": self.redirect_uri, "scope": SCOPES, "resource": RESOURCE,
                  "state": state, "nonce": nonce, "code_challenge_method": "S256",
                  "code_challenge": _b64(hashlib.sha256(verifier.encode("ascii")).digest()), "ext_agent_host_id": host}
        registering = not acct
        if registering:
            params.update(client_id=DYNAMIC_CLIENT, agent_name_hint=self.app_name)
        else:
            params["client_id"] = cid
            if acct.get("id_token"):
                params["id_token_hint"] = acct["id_token"]
            if acct.get("email"):
                params["login_hint"] = acct["email"]
        attempt = Attempt(f"{AUTHORIZE_URL}?{urlencode(params)}", state, nonce, verifier, self.redirect_uri,
                          params["client_id"], registering, acct.get("subject") if acct else None)
        self._pending[state] = attempt
        while len(self._pending) > self.MAX_PENDING:
            self._pending.pop(next(iter(self._pending)))
        return attempt

    def complete_login(self, query: dict) -> dict:
        """Handle the callback's query parameters; returns the status."""
        attempt = self._pending.pop(query.get("state") or "", None)
        if attempt is None:
            raise LoginError("the callback's state does not match a sign-in attempt of ours (a stale or forged callback)")
        if query.get("error"):
            if query["error"] == "access_denied":
                raise LoginDeclined("ChatGPT plan use was not authorized (access_denied); no code was exchanged")
            shown = "".join(ch for ch in str(query["error"])[:40] if ch.isalnum() or ch in "_-. ")
            raise LoginError(f"the sign-in returned an error: {shown}")
        code = query.get("code")
        if not code:
            raise LoginError("the callback carried no authorization code")
        client_id = query.get("client_id")
        if attempt.registering:
            if not client_id or client_id == DYNAMIC_CLIENT:
                raise LoginError("registration is incomplete: the callback did not return an issued client_id")
        else:
            if client_id and client_id != attempt.client_id:
                raise LoginError("the callback names a different client than the account being signed in; rejected")
            client_id = attempt.client_id
        body = {"grant_type": "authorization_code", "client_id": client_id, "code": code, "code_verifier": attempt.verifier,
                "redirect_uri": attempt.redirect_uri, "resource": RESOURCE}
        try:
            resp = self.http.post(TOKEN_URL, data=body)
        except httpx.RequestError as exc:
            raise TemporaryAuthError(f"could not reach the token endpoint: {type(exc).__name__}") from exc
        if resp.status_code != 200:
            raise LoginError(f"the code exchange failed (HTTP {resp.status_code}: {self._error_code(resp)}); start a fresh sign-in")
        tok = resp.json()
        claims = self._validate_id_token(tok.get("id_token", ""), client_id, attempt.nonce)
        if attempt.subject and claims.get("sub") != attempt.subject:
            raise LoginError("the signed-in ChatGPT account is not the one selected; nothing was replaced")
        scopes = sorted((tok.get("scope") or "").split())
        data = self._read()
        data.setdefault("accounts", {})[client_id] = {
            "email": claims.get("email"), "issuer": ISSUER, "subject": claims["sub"], "client_id": client_id,
            "ext_agent_host_id": self.host_id(), "id_token": tok["id_token"], "access_token": tok["access_token"],
            "refresh_token": tok.get("refresh_token"), "token_type": tok.get("token_type", "Bearer"),
            "expires_in": tok.get("expires_in", 3600), "expires_at": self._clock() + int(tok.get("expires_in", 3600)),
            "scopes": scopes, "saved_at": int(self._clock())}
        data["selected"] = client_id
        self._write(data)
        log.info("signed in with ChatGPT (client %s, plan usage %s)", client_id, "enabled" if DIRECT_SCOPE in scopes else "NOT granted")
        return self.status()

    def _validate_id_token(self, token: str, client_id: str, nonce: str) -> dict:
        try:
            header = jwt.get_unverified_header(token)
            keys = {k.get("kid"): k for k in self._get_jwks().get("keys", [])}
            key = RSAAlgorithm.from_jwk(json.dumps(keys[header.get("kid")]))
            claims = jwt.decode(token, key, algorithms=["RS256"], audience=client_id, issuer=ISSUER,
                                options={"require": ["exp", "iss", "aud", "sub"]})
        except (jwt.PyJWTError, KeyError, ValueError, TypeError) as exc:
            raise LoginError(f"the ID token failed validation ({type(exc).__name__}); nothing was stored") from exc
        if claims.get("nonce") != nonce:
            raise LoginError("the ID token's nonce does not match this attempt; nothing was stored")
        return claims

    def _get_jwks(self) -> dict:
        if self._jwks is not None:
            return self._jwks()
        return self.http.get(JWKS_URL).json()

    @staticmethod
    def _error_code(resp) -> str:
        try:
            return str(resp.json().get("error") or resp.json().get("detail") or "")
        except ValueError:
            return ""

    # ------------------------------------------------------------- the access token
    async def access_token(self) -> str:
        """A valid access token for inference: the saved one while it has time, else a refresh (serialized). Raises
        NotSignedIn / PlanUsageDisabled / TemporaryAuthError; never falls back to another billing path."""
        return await asyncio.to_thread(self._access_token_sync)

    def _access_token_sync(self) -> str:
        with self._lock:                                          # one refresh at a time: the refresh token rotates
            data, cid, acct = self._account()
            if not acct or not acct.get("access_token"):
                raise NotSignedIn("not signed in with ChatGPT: open /app/chatgpt on this server and choose Continue with ChatGPT")
            if DIRECT_SCOPE not in acct.get("scopes", []):
                raise PlanUsageDisabled(f"ChatGPT plan usage is not enabled for this sign-in (the grant lacks {DIRECT_SCOPE}); "
                                        "enable it from /app/chatgpt or use an API key")
            if acct["expires_at"] - self._clock() > REFRESH_MARGIN_S:
                return acct["access_token"]
            return self._refresh(data, cid, acct)

    def _refresh(self, data, cid, acct) -> str:
        if not acct.get("refresh_token"):
            raise NotSignedIn("the ChatGPT session expired: sign in again")
        body = {"grant_type": "refresh_token", "client_id": cid, "refresh_token": acct["refresh_token"], "resource": RESOURCE}
        try:
            resp = self.http.post(TOKEN_URL, data=body)
        except httpx.RequestError as exc:
            raise TemporaryAuthError(f"could not reach OpenAI to refresh the session ({type(exc).__name__}); credentials kept") from exc
        if resp.status_code >= 500:
            raise TemporaryAuthError(f"OpenAI answered HTTP {resp.status_code} to the refresh; credentials kept")
        if resp.status_code != 200:
            code = self._error_code(resp)
            if code == "invalid_client":
                raise AuthConfigError("OpenAI rejected the saved client id (invalid_client)")
            if code in _UNUSABLE_REFRESH or resp.status_code in (400, 401):
                for k in ("access_token", "refresh_token", "id_token"):
                    acct.pop(k, None)
                self._write(data)                                 # the client id and identity stay; the tokens are unusable
                raise NotSignedIn(f"the ChatGPT session can no longer be refreshed ({code or resp.status_code}): sign in again")
            raise TemporaryAuthError(f"the refresh failed (HTTP {resp.status_code}); credentials kept")
        tok = resp.json()
        acct["access_token"] = tok["access_token"]
        acct["refresh_token"] = tok.get("refresh_token", acct["refresh_token"])
        acct["expires_in"] = tok.get("expires_in", 3600)
        acct["expires_at"] = self._clock() + int(acct["expires_in"])
        if tok.get("scope"):
            acct["scopes"] = sorted(tok["scope"].split())
        acct["saved_at"] = int(self._clock())
        self._write(data)                                         # access, expiry, scopes and the rotated refresh token together
        return acct["access_token"]

    # ------------------------------------------------------------- state and sign-out
    def status(self) -> dict:
        data, cid, acct = self._account()
        if not acct or not acct.get("access_token"):
            return {"signed_in": False, "plan_usage_enabled": False, "email": (acct or {}).get("email"), "client_id": cid,
                    "scopes": [], "manage_usage_url": USAGE_URL}
        return {"signed_in": True, "plan_usage_enabled": DIRECT_SCOPE in acct.get("scopes", []), "email": acct.get("email"),
                "client_id": cid, "scopes": acct.get("scopes", []), "expires_at": acct.get("expires_at"),
                "manage_usage_url": USAGE_URL}

    def sign_out(self) -> None:
        """Revoke (best effort) and remove the tokens. The registered client and host id stay: signing out does not delete them."""
        with self._lock:
            data, cid, acct = self._account()
            if not acct:
                return
            for token, hint in ((acct.get("refresh_token"), "refresh_token"), (acct.get("access_token"), "access_token")):
                if token:
                    try:
                        self.http.post(REVOKE_URL, data={"token": token, "token_type_hint": hint, "client_id": cid})
                    except httpx.RequestError:
                        log.info("could not reach OpenAI to revoke; the tokens are removed locally")
                        break
            for k in ("access_token", "refresh_token", "id_token"):
                acct.pop(k, None)
            self._write(data)
