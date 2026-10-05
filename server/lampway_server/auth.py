"""Single-user authentication: HS256 JWT access tokens, rotating refresh tokens,
and the PKCE desktop SSO exchange.

The client never verifies the JWT signature; it only reads ``exp`` to schedule
refreshes (socket_reauth.py:11-18). We verify it on every request.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def mint_jwt(secret: str, claims: dict) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url(json.dumps(claims, separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url(signature)}"


def verify_jwt(secret: str, token: str, now: Optional[float] = None) -> Optional[dict]:
    """The claims when the signature is ours and ``exp`` is in the future; else None."""
    try:
        header, payload, signature = token.split(".")
    except (ValueError, AttributeError):
        return None
    signing_input = f"{header}.{payload}".encode("ascii")
    expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(expected, _b64url_decode(signature)):
            return None
        claims = json.loads(_b64url_decode(payload))
    except (ValueError, TypeError):
        return None
    if not isinstance(claims, dict):
        return None
    if float(claims.get("exp", 0)) <= (time.time() if now is None else now):
        return None
    return claims


class Auth:
    """One account; token pairs; PKCE codes; idempotent refresh."""

    PKCE_CODE_TTL_S = 300

    def __init__(self, *, secret: str, email: str, name: str, password: str,
                 access_ttl_s: int, credits: int):
        self._secret = secret
        self.email = email
        self.name = name
        self._password = password
        self._access_ttl_s = access_ttl_s
        self.credits = credits
        self._refresh_tokens: set[str] = set()
        self._pkce_codes: dict[str, tuple[str, float]] = {}
        # Idempotency-Key -> (refresh token it was used with, pair it produced)
        self._refresh_replays: dict[str, tuple[str, dict]] = {}

    # ----------------------------------------------------------- credentials
    def check_password(self, username: str, password: str) -> bool:
        if not self._password:
            return False
        return hmac.compare_digest(username or "", self.email) and hmac.compare_digest(
            password or "", self._password)

    def password_required(self) -> bool:
        return bool(self._password)

    # ------------------------------------------------------------- the pair
    def issue_pair(self) -> dict:
        now = time.time()
        access = mint_jwt(self._secret, {
            "sub": self.email, "iat": int(now), "exp": int(now) + self._access_ttl_s,
        })
        refresh = secrets.token_urlsafe(48)
        self._refresh_tokens.add(refresh)
        return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}

    def verify_access(self, token: str) -> Optional[dict]:
        return verify_jwt(self._secret, token)

    def profile(self) -> dict:
        return {"email": self.email, "name": self.name, "credits": self.credits}

    # ------------------------------------------------------------- refresh
    def refresh(self, refresh_token: str, idempotency_key: Optional[str]) -> Optional[dict]:
        """Rotate the pair. A repeated Idempotency-Key with the same refresh token
        returns the pair the first attempt produced (auth.py:401-409)."""
        if idempotency_key and idempotency_key in self._refresh_replays:
            used_with, pair = self._refresh_replays[idempotency_key]
            if hmac.compare_digest(used_with, refresh_token or ""):
                return pair
            return None
        if not refresh_token or refresh_token not in self._refresh_tokens:
            return None
        self._refresh_tokens.discard(refresh_token)
        pair = self.issue_pair()
        if idempotency_key:
            self._refresh_replays[idempotency_key] = (refresh_token, pair)
        return pair

    # ---------------------------------------------------------------- PKCE
    def begin_pkce(self, code_challenge: str, method: str) -> Optional[str]:
        if method != "S256" or not code_challenge:
            return None
        code = secrets.token_urlsafe(32)
        self._pkce_codes[code] = (code_challenge, time.time() + self.PKCE_CODE_TTL_S)
        return code

    def exchange_code(self, code: str, verifier: str) -> Optional[dict]:
        entry = self._pkce_codes.pop(code or "", None)
        if entry is None:
            return None
        challenge, expires_at = entry
        if time.time() > expires_at or not verifier:
            return None
        computed = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        if not hmac.compare_digest(computed, challenge):
            return None
        return self.issue_pair()
