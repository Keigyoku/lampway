# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Every registered adapter keeps the direct endpoint's bearer out of command lines."""
import json

import pytest
from starlette.testclient import TestClient

from lampway_server.app import create_app
from lampway_server.herdr import harnesses as HN
from lampway_server.mcp import McpServer


@pytest.mark.parametrize("harness", [*HN.ADAPTERS, *HN.LAMPWAY_ADAPTERS])
def test_direct_bearer_never_appears_on_an_adapters_command_line(harness, tmp_path):
    adapter = HN.get(harness)
    secret = "fixture-worker-bearer-value"
    # Hermes/Grok expose the supported scene-bound main route; their worker
    # refusals are covered independently. Every original secrecy assertion runs.
    main = harness in {"hermes", "grok"}
    direct = HN.DirectServer("lampway", "http://127.0.0.1:8787/api/v1/mcp/pane",
                             {} if main else {HN.SESSION_HEADER: "swarm:sw1:worker-1"}, "LAMPWAY_WORKER_TOKEN", secret)
    pane = HN.PaneSpec(cwd=str(tmp_path), home=str(tmp_path / "home"), session_id="fixture-session",
                       mcp_config_path=str(tmp_path / adapter.config_name), desktop=main,
                       scene_session_id="scene-bound-main" if main else None, direct=(direct,))
    wiring = adapter.lampway_tools(pane)
    assert secret not in json.dumps(adapter.launch(pane))
    assert secret not in json.dumps(adapter.resume("fixture-session", pane))
    assert secret not in json.dumps(wiring.argv)
    if adapter.direct_ok and not HN.is_lampway(harness):
        assert secret in json.dumps(wiring.env) or secret in json.dumps(wiring.files)
    elif not adapter.direct_ok:
        assert wiring.kind == "unavailable", "unsupported adapters must disclose that they cannot wire a worker endpoint"
        assert secret not in json.dumps(wiring.files)


@pytest.mark.parametrize("harness", [*HN.ADAPTERS, *HN.LAMPWAY_ADAPTERS])
def test_the_check_rejects_a_planted_bearer_on_the_command_line(harness, tmp_path, monkeypatch):
    adapter = HN.get(harness)
    monkeypatch.setattr(adapter, "launch", lambda pane: [adapter.binary, pane.direct[0].token])
    with pytest.raises(AssertionError):
        test_direct_bearer_never_appears_on_an_adapters_command_line(harness, tmp_path)


@pytest.mark.parametrize("peer", ["203.0.113.5", "2001:db8::5"])
def test_pane_endpoint_refuses_non_loopback_before_resolving_a_bearer(settings, peer, monkeypatch):
    app = create_app(settings)

    def unexpected_lookup(*args):
        pytest.fail("a non-loopback peer reached bearer resolution")
    monkeypatch.setattr(McpServer, "pane_caller", unexpected_lookup)
    with TestClient(app, base_url="http://127.0.0.1:8787", client=(peer, 12345)) as client:
        response = client.post("/api/v1/mcp/pane", headers={"Authorization": "Bearer " + "fixture-worker-bearer-value"},
                               json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert response.status_code == 403 and response.json() == {"detail": "loopback only"}
