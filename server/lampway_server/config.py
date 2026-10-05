"""Runtime configuration. Everything comes from the environment; nothing here logs a secret."""

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path


def _default_state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "lampway-server"


# One image model per PURPOSE (the bake-off of 2026-10-05, scratch/subs/bakeoff): plates / mesh-paint, material-ID masks, concepts, seamless tiles.
# size = WIDTHxHEIGHT for models that take `size` (GPT Image 2.5: at most 3840 per edge within ~8.3 MP); resolution = 1K/2K/4K for the models
# that take `resolution` + `aspect_ratio` instead (FLUX 3, Seedream, Gemini, Riverflow). An empty value is not sent.
DEFAULT_IMAGE_PURPOSES = {
    "plates": {"model": "openai/gpt-image-2.5-flare", "size": "2880x2880", "resolution": "", "quality": ""},
    "mask": {"model": "google/gemini-3.1-flash-image", "size": "", "resolution": "", "quality": ""},
    "concept": {"model": "black-forest-labs/flux-3-image", "size": "", "resolution": "2K", "quality": ""},
    "tile": {"model": "openai/gpt-image-2.5-flare", "size": "2048x2048", "resolution": "", "quality": ""},
}


# One video model per PURPOSE: bulk clips, loops (first = last frame) and motion transfer (a reference video). The OpenRouter video catalogue
# is the source of the model ids; ``duration`` is seconds, ``image_mode`` first_frame | first_last_frame | reference.
DEFAULT_VIDEO_PURPOSES = {
    "bulk": {"model": "heygen/heygen-video-1", "resolution": "768p", "duration": 10, "aspect_ratio": "16:9", "image_mode": "first_frame"},
    "loop": {"model": "bytedance/seedance-1-5-pro", "resolution": "720p", "duration": 5, "aspect_ratio": "1:1", "image_mode": "first_last_frame"},
    "motion": {"model": "bytedance/seedance-2.0-mini", "resolution": "480p", "duration": 5, "aspect_ratio": "9:16", "image_mode": "reference"},
}


from .spendpolicy import DEFAULT_SPEND_POLICY


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
    chatgpt_effort: str = ""                           # reasoning.effort for the main agent ('' = model default)
    chatgpt_swarm_model: str = "gpt-6.1-sol"           # swarm workers on the same ChatGPT plan
    chatgpt_swarm_effort: str = "low"
    swarm_provider: str = ""                           # '' = the main provider's own swarm path; or claude_cli / chatgpt_plan / openrouter
    claude_swarm_model: str = "claude-sonnet-5-5"      # swarm workers on the owner's own `claude` CLI (local CLI switch required)
    openrouter_model: str = "anthropic/claude-sonnet-5.5"       # the main agent
    # swarm workers. stealth/space-bunny-alpha is free but answered "502 Provider returned an empty response" to 6 of 6
    # concurrent worker requests (2026-10-05, probe in reports/tools.md), which a swarm is; deepseek-v4.1-flash served 6 of 6.
    openrouter_swarm_model: str = "deepseek/deepseek-v4.1-flash"
    image_backend: str = "tripo"                       # tripo | codex_cli | openrouter (mesh-paint and the image slot)
    openrouter_image_model: str = "google/gemini-3.1-flash-image"
    openrouter_image_size: str = ""                    # e.g. 2880x2880 (GPT Image 2.5's pixel budget refuses 3840x3840); '' = provider default
    openrouter_image_quality: str = ""                 # auto/low/medium/high/xhigh/max; '' = provider default
    image_purposes: dict = field(default_factory=lambda: {k: dict(v) for k, v in DEFAULT_IMAGE_PURPOSES.items()})
    video_purposes: dict = field(default_factory=lambda: {k: dict(v) for k, v in DEFAULT_VIDEO_PURPOSES.items()})
    video_max_job_usd: float = 2.0                     # one video job above this estimate is refused before it is sent
    openrouter_stt_model: str = "google/gemini-3.8-flash"      # dictation: an audio-input model
    openrouter_max_tokens: int = 4096                  # per request, always sent
    openrouter_budget_usd: float = 3.0                 # session spend ceiling: past it every OpenRouter call is refused
    spend_policy: dict = field(default_factory=lambda: {k: dict(v) for k, v in DEFAULT_SPEND_POLICY.items()})      # per provider: click, above, job_cap, session_cap
    sources: dict = field(default_factory=dict, compare=False)      # field -> env | saved | default (provider_prefs.apply_saved fills it)

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
            chatgpt_effort=env.get("LAMPWAY_CHATGPT_EFFORT", ""),
            chatgpt_swarm_model=env.get("LAMPWAY_CHATGPT_SWARM_MODEL", env.get("LAMPWAY_CHATGPT_MODEL", "gpt-6.1-sol")),
            chatgpt_swarm_effort=env.get("LAMPWAY_CHATGPT_SWARM_EFFORT", "low"),
            swarm_provider=env.get("LAMPWAY_SWARM_PROVIDER", ""),
            claude_swarm_model=env.get("LAMPWAY_CLAUDE_SWARM_MODEL", "claude-sonnet-5-5"),
            openrouter_model=env.get("LAMPWAY_OPENROUTER_MODEL", "anthropic/claude-sonnet-5.5"),
            openrouter_swarm_model=env.get("LAMPWAY_OPENROUTER_SWARM_MODEL", "deepseek/deepseek-v4.1-flash"),
            image_backend=env.get("LAMPWAY_IMAGE_BACKEND", "tripo"),
            openrouter_image_model=env.get("LAMPWAY_OPENROUTER_IMAGE_MODEL", "google/gemini-3.1-flash-image"),
            openrouter_image_size=env.get("LAMPWAY_OPENROUTER_IMAGE_SIZE", ""),
            openrouter_image_quality=env.get("LAMPWAY_OPENROUTER_IMAGE_QUALITY", ""),
            openrouter_stt_model=env.get("LAMPWAY_OPENROUTER_STT_MODEL", "google/gemini-3.8-flash"),
            openrouter_max_tokens=int(env.get("LAMPWAY_OPENROUTER_MAX_TOKENS", "4096")),
            openrouter_budget_usd=float(env.get("LAMPWAY_OPENROUTER_BUDGET_USD", "3.0")),
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
