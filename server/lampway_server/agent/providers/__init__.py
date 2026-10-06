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
        return AnthropicProvider(model=settings.anthropic_model, api_key=_held_key("anthropic"))
    if settings.provider == "openai":
        from .openai_compat import OpenAICompatProvider
        if not settings.openai_model:
            raise ValueError("LAMPWAY_OPENAI_MODEL is required with LAMPWAY_PROVIDER=openai")
        return OpenAICompatProvider(settings.openai_base_url, settings.openai_model, _held_key("custom_llm") or "")
    if settings.provider == "chatgpt_plan":
        # ChatGPT plan usage (Sign in with ChatGPT): OAuth tokens from /app/chatgpt, never an API key, never Codex's tokens.
        from ...chatgpt_auth import ChatGPTAuth
        from .chatgpt_plan import ChatGPTPlanProvider
        auth = chatgpt_auth or ChatGPTAuth(settings.state_dir, redirect_port=settings.port)
        return ChatGPTPlanProvider(auth, settings.chatgpt_model, effort=settings.chatgpt_effort)
    if settings.provider == "codex_app_server":
        from .. import cli_adapters
        from .codex_app_server import CodexAppServerProvider
        cli_adapters.require_enabled(settings.state_dir)
        return CodexAppServerProvider(binary=os.environ.get("LAMPWAY_CODEX_BINARY", "codex"), model=os.environ.get("LAMPWAY_CODEX_MODEL", ""), effort=os.environ.get("LAMPWAY_CODEX_EFFORT", "medium"),
                                      turn_timeout_s=float(os.environ.get("LAMPWAY_CODEX_TURN_TIMEOUT_S", "180")))
    if settings.provider in ("codex_cli", "claude_cli"):
        # The owner's own official CLIs, for personal use. Off unless enabled; the refusal carries the terms caveat.
        from .. import cli_adapters
        cli_adapters.require_enabled(settings.state_dir)
        if settings.provider == "codex_cli":
            return cli_adapters.CodexCLIProvider(model=os.environ.get("LAMPWAY_CODEX_MODEL", ""))
        return cli_adapters.ClaudeCLIProvider(model=os.environ.get("LAMPWAY_CLAUDE_MODEL", ""), workdir=settings.state_dir)
    if settings.provider == "openrouter":
        return _openrouter(settings, settings.openrouter_model, "main")
    raise ValueError(f"unknown LAMPWAY_PROVIDER {settings.provider!r}")


def _held_key(cid: str):
    """The key Connections resolves (the environment first, C3), or None: then the SDK resolves its own (an ``ant auth login`` profile)."""
    from ... import connections as C
    try:
        return C.secret_of(C.credential(cid)) or None
    except C.Refused:
        return None


_LEDGERS: dict = {}


def spend_ledger(settings):
    """The one session ledger every OpenRouter caller of this server shares (main agent, swarm workers, image backend)."""
    from .openrouter import SpendLedger
    key = (str(settings.state_dir), float(settings.openrouter_budget_usd))
    if key not in _LEDGERS:
        log = os.environ.get("LAMPWAY_SPEND_LOG") or settings.state_dir / "openrouter_spend.jsonl"
        _LEDGERS[key] = SpendLedger(settings.openrouter_budget_usd, log_path=log)
    return _LEDGERS[key]


def _openrouter(settings, model, label):
    from .openrouter import OpenRouterProvider, resolve_api_key
    return OpenRouterProvider(model=model, api_key=resolve_api_key(), ledger=spend_ledger(settings),
                              max_tokens=settings.openrouter_max_tokens, label=label)


def make_swarm_provider(settings, label: str, chatgpt_auth=None):
    """A provider for one swarm worker: the cheap swarm model, the shared ledger. The mock/scripted providers serve themselves.
    ``settings.swarm_provider`` puts the workers on a different provider from the main agent."""
    kind = settings.swarm_provider or settings.provider
    if kind == "claude_cli":
        from .. import cli_adapters
        cli_adapters.require_enabled(settings.state_dir)              # the owner's own login, personal use, terms note on refusal
        return cli_adapters.ClaudeCLIProvider(model=settings.claude_swarm_model, workdir=settings.state_dir)
    if kind == "openrouter" and settings.provider != "openrouter":
        return _openrouter(settings, settings.openrouter_swarm_model, label)
    if kind != settings.provider:
        raise ValueError(f"LAMPWAY_SWARM_PROVIDER {kind!r} is not supported (claude_cli, openrouter, or the main provider)")
    if settings.provider == "openrouter":
        return _openrouter(settings, settings.openrouter_swarm_model, label)
    if settings.provider == "chatgpt_plan":
        # workers on the owner's own ChatGPT plan: the swarm model and effort, one shared sign-in (refreshes serialise in ChatGPTAuth)
        from ...chatgpt_auth import ChatGPTAuth
        from .chatgpt_plan import ChatGPTPlanProvider
        # ONE ChatGPTAuth per server: refresh tokens rotate, so a second instance refreshing on its own would reuse a rotated
        # token and the sign-in would be revoked (refresh_token_reused). The app passes its own instance.
        auth = chatgpt_auth or ChatGPTAuth(settings.state_dir, redirect_port=settings.port)
        return ChatGPTPlanProvider(auth, settings.chatgpt_swarm_model, effort=settings.chatgpt_swarm_effort)
    return make_provider(settings)
