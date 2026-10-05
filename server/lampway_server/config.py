"""Runtime configuration. Everything comes from the environment; nothing here logs a secret."""

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path


def _default_state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "lampway-server"


@dataclass
class Settings:
    host: str = "127.0.0.1"
    port: int = 8787
    jwt_secret: str = ""
    access_token_ttl_s: int = 3600
    user_email: str = "owner@lampway.local"
    user_name: str = "Owner"
    user_password: str = ""
    fake_credits: int = 100_000
    state_dir: Path = field(default_factory=_default_state_dir)
    provider: str = "mock"
    anthropic_model: str = "claude-sonnet-5-5"
    openai_base_url: str = "http://127.0.0.1:11434/v1"
    openai_model: str = ""
    chatgpt_model: str = "gpt-6.1-sol"                 # the documented example model; the account's own list is at /app/chatgpt/status

    @classmethod
    def from_env(cls, env=None) -> "Settings":
        env = os.environ if env is None else env
        state_dir = Path(env.get("LAMPWAY_STATE_DIR") or _default_state_dir())
        return cls(
            host=env.get("LAMPWAY_HOST", "127.0.0.1"),
            port=int(env.get("LAMPWAY_PORT", "8787")),
            jwt_secret=env.get("LAMPWAY_JWT_SECRET", ""),
            access_token_ttl_s=int(env.get("LAMPWAY_ACCESS_TTL_S", "3600")),
            user_email=env.get("LAMPWAY_USER_EMAIL", "owner@lampway.local"),
            user_name=env.get("LAMPWAY_USER_NAME", "Owner"),
            user_password=env.get("LAMPWAY_USER_PASSWORD", ""),
            fake_credits=int(env.get("LAMPWAY_FAKE_CREDITS", "100000")),
            state_dir=state_dir,
            provider=env.get("LAMPWAY_PROVIDER", "mock"),
            anthropic_model=env.get("LAMPWAY_ANTHROPIC_MODEL", "claude-sonnet-5-5"),
            openai_base_url=env.get("OPENAI_BASE_URL", "http://127.0.0.1:11434/v1"),
            openai_model=env.get("LAMPWAY_OPENAI_MODEL", ""),
            chatgpt_model=env.get("LAMPWAY_CHATGPT_MODEL", "gpt-6.1-sol"),
        )

    def resolve_jwt_secret(self) -> str:
        """The configured secret, else one generated once and kept in the state dir
        (0600) so access tokens survive a server restart."""
        if self.jwt_secret:
            return self.jwt_secret
        path = self.state_dir / "jwt_secret"
        if path.exists():
            self.jwt_secret = path.read_text().strip()
            return self.jwt_secret
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.jwt_secret = secrets.token_urlsafe(48)
        path.touch(mode=0o600)
        path.write_text(self.jwt_secret)
        return self.jwt_secret
