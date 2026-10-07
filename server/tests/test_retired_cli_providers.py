# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mode 1 thinks through a key the user owns or an endpoint the user runs, never through an agent CLI wrapped as a model endpoint
(docs/reports/agent-modes-spec.md R0; captain's Q6, 2026-10-06).

Retired: ``claude_cli`` and ``codex_cli`` (a transcript flattened into ``claude -p`` / ``codex exec``), ``codex_app_server`` (Codex's
app-server as Lampway's model) and the ``codex_cli`` image backend (``codex exec '$imagegen'``). A user who wants Claude Code or
Codex runs it as their own agent (Bring Your Own Agent), on its own login, in a pane on Lampway's herdr server.
"""

import importlib.util

import pytest

from lampway_server import imagegen, provider_prefs
from lampway_server.agent import cli_adapters
from lampway_server.agent.providers import make_provider
from lampway_server.choices import registry as REG
from lampway_server.config import Settings

RETIRED = ("claude_cli", "codex_cli", "codex_app_server")


def test_no_purpose_offers_a_cli_wrapped_as_a_model():
    offers = [(p.id, o) for p in REG.PURPOSES.values() for o in p.options + p.default if o.split(":", 1)[0] in RETIRED]
    assert offers == []


@pytest.mark.parametrize("kind", RETIRED)
def test_the_factory_refuses_a_retired_provider_and_names_the_way_to_run_it(kind, tmp_path):
    with pytest.raises(ValueError) as refused:
        make_provider(Settings(provider=kind, state_dir=tmp_path))
    assert "your own agent" in str(refused.value).lower()


def test_the_providers_dialog_no_longer_lists_them():
    assert not set(RETIRED) & set(provider_prefs.MAIN_PROVIDERS + provider_prefs.SWARM_PROVIDERS + provider_prefs.IMAGE_BACKENDS)
    assert "codex_cli" not in imagegen.BACKENDS


def test_an_older_saved_choice_is_set_aside_not_applied(tmp_path):
    """A provider_prefs.json written before the retirement must not stop the server from starting: the retired value is skipped
    and the default stays in force."""
    settings = Settings(state_dir=tmp_path)
    provider_prefs.apply_saved(settings, {"provider": "claude_cli", "swarm_provider": "claude_cli", "image_backend": "codex_cli"},
                               env={})
    assert (settings.provider, settings.swarm_provider, settings.image_backend) == ("mock", "", "tripo")
    assert settings.sources["provider"] == "default"


def test_the_cli_as_endpoint_code_is_gone():
    assert importlib.util.find_spec("lampway_server.agent.providers.codex_app_server") is None
    for name in ("build_prompt", "parse_answer", "CodexCLIProvider", "ClaudeCLIProvider", "codex_image"):
        assert not hasattr(cli_adapters, name), name
