"""Model providers behind one interface (see base.py)."""

import os


def make_provider(settings, chatgpt_auth=None):
    """The provider LAMPWAY_PROVIDER names. Keys are read from the environment
    here or by the SDK and never pass through logs or responses."""
    if settings.provider == "mock":
        from .mock import MockProvider
        return MockProvider()
    if settings.provider == "anthropic":
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider(model=settings.anthropic_model)
    if settings.provider == "openai":
        from .openai_compat import OpenAICompatProvider
        if not settings.openai_model:
            raise ValueError("LAMPWAY_OPENAI_MODEL is required with LAMPWAY_PROVIDER=openai")
        return OpenAICompatProvider(settings.openai_base_url, settings.openai_model,
                                    os.environ.get("OPENAI_API_KEY", ""))
    if settings.provider == "chatgpt_plan":
        # ChatGPT plan usage (Sign in with ChatGPT): OAuth tokens from /app/chatgpt, never an API key, never Codex's tokens.
        from ...chatgpt_auth import ChatGPTAuth
        from .chatgpt_plan import ChatGPTPlanProvider
        auth = chatgpt_auth or ChatGPTAuth(settings.state_dir, redirect_port=settings.port)
        return ChatGPTPlanProvider(auth, settings.chatgpt_model)
    if settings.provider in ("codex_cli", "claude_cli"):
        # The owner's own official CLIs, for personal use. Off unless enabled; the refusal carries the terms caveat.
        from .. import cli_adapters
        cli_adapters.require_enabled(settings.state_dir)
        if settings.provider == "codex_cli":
            return cli_adapters.CodexCLIProvider(model=os.environ.get("LAMPWAY_CODEX_MODEL", ""))
        return cli_adapters.ClaudeCLIProvider(model=os.environ.get("LAMPWAY_CLAUDE_MODEL", ""))
    raise ValueError(f"unknown LAMPWAY_PROVIDER {settings.provider!r}")
