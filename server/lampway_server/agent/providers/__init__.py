"""Model providers behind one interface (see base.py)."""

import os

#: The agent CLIs that used to be wrapped as Lampway's model (agent-modes spec R0, captain's Q6, 2026-10-06). They run as the user's
#: own agent now (Bring Your Own Agent), on their own login, never behind Lampway's loop.
RETIRED = {"claude_cli": "Claude Code", "codex_cli": "Codex", "codex_app_server": "Codex"}


def retired(kind: str) -> ValueError:
    return ValueError(f"{kind} is retired: Lampway's agent thinks through an API key, an endpoint you run, or Sign in with ChatGPT. "
                      f"To use {RETIRED[kind]} on its own login, run it as your own agent (Bring Your Own Agent) in a pane on "
                      "Lampway's herdr server.")


def make_provider(settings, chatgpt_auth=None, resolution=None):
    """The main agent's provider. With ``resolution`` (Choices' agent.main, 5.6) it is built from the resolved option - the user's
    fallback when the preferred option cannot serve; without one, from the settings (which Choices also decides). Keys come from Connections."""
    if resolution is not None and not str(resolution.option).startswith("follow:"):
        from ...choices.bridge import settings_for_option
        p = _make_provider(settings_for_option(settings, resolution.option, resolution.params), chatgpt_auth)
        try:
            p.choice = {"option": resolution.option, "reason": resolution.reason, "why": resolution.why}
        except AttributeError:
            pass
        return p
    try:
        from ...choices import shadow as SH
        from ...choices.bridge import chains
        from ... import choices as CH
        SH.record("agent.main", chains(settings)["agent.main"]["preferred"], CH.Job())       # the shadow row: resolved vs ran
    except Exception:  # noqa: BLE001
        pass
    return _make_provider(settings, chatgpt_auth)


def _make_provider(settings, chatgpt_auth=None):
    if settings.provider in RETIRED:
        raise retired(settings.provider)
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
    """A provider for one swarm worker. When the configured one cannot be built (a CLI switch off, a missing key), the next option of the
    agent.worker chain in Choices is built instead, at spawn - never mid-turn - and the provider says so in ``choice`` (HC23)."""
    try:
        return _make_swarm_provider(settings, label, chatgpt_auth)
    except (ValueError, RuntimeError) as exc:
        first_error = exc
    from ... import choices as CH
    from ...logredact import redact_text
    tried = []
    for oid in CH.chain("agent.worker")[1:]:
        try:
            p = _build_worker_option(settings, oid, label, chatgpt_auth)
        except (ValueError, RuntimeError) as exc:
            tried.append(f"{oid}: {redact_text(str(exc))[:120]}")
            continue
        why = f"fallback: {settings.swarm_provider or settings.provider} could not be built (" + redact_text(str(first_error))[:160] + ")"
        try:
            p.choice = {"option": oid, "reason": "fallback", "why": "; ".join([why] + tried)}
        except AttributeError:
            pass
        return p
    raise first_error


def _build_worker_option(settings, oid: str, label: str, chatgpt_auth=None):
    prov, _, model = oid.partition(":")
    if prov == "openrouter":
        return _openrouter(settings, model, label)
    if prov == "chatgpt_plan":
        from ...chatgpt_auth import ChatGPTAuth
        from .chatgpt_plan import ChatGPTPlanProvider
        auth = chatgpt_auth or ChatGPTAuth(settings.state_dir, redirect_port=settings.port)
        return ChatGPTPlanProvider(auth, model or settings.chatgpt_swarm_model, effort=settings.chatgpt_swarm_effort)
    if prov in RETIRED:
        raise retired(prov)
    if oid == "follow:agent.main":
        return make_provider(settings, chatgpt_auth=chatgpt_auth)
    raise ValueError(f"{oid} cannot serve a swarm worker")


def _make_swarm_provider(settings, label: str, chatgpt_auth=None):
    """The configured worker provider: the cheap swarm model, the shared ledger. The mock/scripted providers serve themselves.
    ``settings.swarm_provider`` puts the workers on a different provider from the main agent."""
    kind = settings.swarm_provider or settings.provider
    if kind in RETIRED:
        raise retired(kind)
    if kind == "openrouter" and settings.provider != "openrouter":
        return _openrouter(settings, settings.openrouter_swarm_model, label)
    if kind != settings.provider:
        raise ValueError(f"LAMPWAY_SWARM_PROVIDER {kind!r} is not supported (openrouter, or the main provider)")
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
