"""Model providers behind one interface (see base.py)."""

import os


def make_provider(settings):
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
    raise ValueError(f"unknown LAMPWAY_PROVIDER {settings.provider!r}")
