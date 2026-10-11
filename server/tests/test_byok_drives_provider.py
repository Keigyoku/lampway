# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The client's API-key dialog drives the main agent (docs/reports/agent-modes-spec.md R0).

``PUT /api/v1/agent/byok`` stored the user's provider, model and base_url, but nothing read them: the factory kept building from
the settings, so a key or a local endpoint saved in the dialog never reached the agent, and ``provider="local"`` (what the
client's local-models form sends) had nowhere to go. Mode 1 thinks through a key the user owns or an endpoint the user runs.
"""

import json

from lampway_server import egress
from lampway_server.agent.providers.anthropic_provider import AnthropicProvider
from lampway_server.agent.providers.openai_compat import OpenAICompatProvider


def _main_choice(settings):
    return json.loads((settings.state_dir / "choices.json").read_text())["purposes"]["agent.main"]


def test_a_local_endpoint_saved_in_the_dialog_is_the_agents_provider(fake, settings, http):
    fake.login()
    saved = fake.put("/api/v1/agent/byok", json={"provider": "local", "model": "qwen3-coder-30b",
                                                  "base_url": "http://127.0.0.1:8080/v1", "supports_vision": False})
    assert saved.status_code == 200, saved.text
    chosen = _main_choice(settings)
    assert chosen["preferred"] == "openai:local" and chosen["set_by"] == "user"
    assert chosen["params"] == {"model": "qwen3-coder-30b", "base_url": "http://127.0.0.1:8080/v1"}
    main = http.app.state.agent.provider
    assert isinstance(main, OpenAICompatProvider)
    assert (main.base_url, main.model) == ("http://127.0.0.1:8080/v1", "qwen3-coder-30b")


def test_an_anthropic_key_saved_in_the_dialog_is_the_agents_provider(fake, settings, http):
    fake.login()
    saved = fake.put("/api/v1/agent/byok", json={"provider": "anthropic", "model": "claude-sonnet-5-5",
                                                  "api_key": "sk-" "ant-secret-FAKE-0000000000005678"})
    assert saved.status_code == 200, saved.text
    assert _main_choice(settings)["preferred"] == "anthropic:claude-sonnet-5-5"
    assert isinstance(http.app.state.agent.provider, AnthropicProvider)


def test_a_remote_endpoint_is_an_egress_route_the_user_switches_on(fake, settings, http):
    fake.login()
    saved = fake.put("/api/v1/agent/byok", json={"provider": "openai", "model": "big-model",
                                                  "base_url": "https://llm.example.net/v1"})
    assert saved.status_code == 200, saved.text
    assert http.app.state.agent.provider.base_url == "https://llm.example.net/v1"
    # Law 2: the host is the custom_llm route's, which is off until the user opts in; loopback stays local.
    assert egress.ACTIVE.route_for_host("llm.example.net") == "custom_llm"


def test_an_agent_cannot_change_where_the_agent_thinks(fake, settings, http):
    fake.login()
    refused = fake.put("/api/v1/agent/byok", headers={"X-Lampway-Origin": "agent"},
                       json={"provider": "local", "model": "m", "base_url": "http://127.0.0.1:9/v1"})
    assert refused.status_code == 403
    assert not (settings.state_dir / "choices.json").exists() or "agent.main" not in json.loads(
        (settings.state_dir / "choices.json").read_text()).get("purposes", {})
