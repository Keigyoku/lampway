# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Worker MCP boundary reproduced offline on native Claude Code 2.1.293.

The causal receipt in scratch/pr4-claude-worker-isolation/causal/corrected shows
foreign global/project/plugin servers connecting without strict configuration,
and only the supplied worker connecting with strict configuration.
"""
import json

from lampway_server.herdr.harnesses.base import DirectServer, PaneSpec
from lampway_server.herdr.harnesses.claude import Claude


def test_claude_worker_excludes_inherited_mcp_without_changing_main(tmp_path):
    adapter = Claude()
    assert adapter.worker_ok
    path = str(tmp_path / "mcp.json")
    direct = DirectServer("lampway", "http://127.0.0.1:8787/api/v1/mcp/pane",
                          {"X-Mixar-Session-Id": "swarm:test:worker"}, "WORKER_TOKEN", "synthetic-test-token")
    worker = PaneSpec(cwd=str(tmp_path), desktop=False, mcp_config_path=path, direct=(direct,))
    wiring = adapter.lampway_tools(worker)
    assert wiring.argv == ("--strict-mcp-config", "--mcp-config", path)
    assert set(json.loads(wiring.files[path])["mcpServers"]) == {"lampway"}
    assert wiring.env == {}
    assert wiring.launcher == ()
    launch = adapter.launch(worker, task="synthetic worker task")
    assert launch.index("synthetic worker task") < launch.index("--mcp-config")
    assert "--strict-mcp-config" in launch
    main = PaneSpec(cwd=str(tmp_path), mcp_config_path=path, launcher=("synthetic-desktop-launcher",))
    assert adapter.lampway_tools(main).argv == ("--mcp-config", path)
    assert "--strict-mcp-config" not in adapter.launch(main)


def test_claude_worker_refuses_launch_without_its_owned_mcp_config(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="worker.*MCP"):
        Claude().launch(PaneSpec(cwd=str(tmp_path), desktop=False), task="synthetic task")
