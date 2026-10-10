# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pi's worker replacement uses the public native MCP factory, keeping MAIN additive."""
import json

from lampway_server.herdr.harnesses.base import DirectServer, Installed, PaneSpec
from lampway_server.herdr.harnesses.pi import MCP_ENV, Pi


def test_pi_worker_uses_exclusive_native_mcp_replacement_only_for_workers(tmp_path, monkeypatch):
    adapter = Pi()
    monkeypatch.setattr(adapter, "detect", lambda: Installed("pi", "pi", "/synthetic/pi", "1.0.4"))
    path = str(tmp_path / "mcp.json")
    direct = DirectServer("lampway", "http://127.0.0.1:8787/api/v1/mcp/pane",
                          {"X-Mixar-Session-Id": "swarm:test:worker"}, "TOKEN", "synthetic-token")
    worker = PaneSpec(cwd=str(tmp_path), desktop=False, mcp_config_path=path, direct=(direct,))
    wiring = adapter.lampway_tools(worker)
    assert "--no-mcp" in wiring.argv
    assert wiring.env == {MCP_ENV: path, "LAMPWAY_PI_WORKER_MCP": "1"}
    assert set(json.loads(wiring.files[path])["mcpServers"]) == {"lampway"}
    assert adapter.worker_ok
    assert not adapter.worker_compatibility_note()
    main = PaneSpec(cwd=str(tmp_path), mcp_config_path=path, launcher=("synthetic-launcher",))
    main_wiring = adapter.lampway_tools(main)
    assert "--no-mcp" not in main_wiring.argv
    assert main_wiring.env == {MCP_ENV: path}
    monkeypatch.setattr(adapter, "detect", lambda: Installed("pi", "pi", "/synthetic/pi", "0.99.0"))
    assert "1.0.4" in adapter.worker_compatibility_note()
    assert not adapter.compatibility_note()


def test_pi_worker_refuses_launch_without_its_owned_mcp_config(tmp_path, monkeypatch):
    import pytest
    adapter = Pi()
    monkeypatch.setattr(adapter, "detect", lambda: Installed("pi", "pi", "/synthetic/pi", "1.0.4"))
    with pytest.raises(ValueError, match="worker.*MCP"):
        adapter.launch(PaneSpec(cwd=str(tmp_path), desktop=False), task="synthetic task")
