"""lampway_compute (agent tool): plan, status, list and reconcile_report ONLY. An agent can never submit, approve or cancel."""
import asyncio
import json

import pytest

from lampway_server.agent import compute_tools as CT
from lampway_server.agent import tools as AT


def test_the_tool_exposes_only_the_read_and_plan_actions(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path))
    spec = next(t for t in AT.TOOLS if t.name == "lampway_compute")
    assert "lampway_compute" in CT.NAMES and "submit" not in json.dumps(spec.parameters.get("properties", {}).get("action", {}).get("enum", [])) and spec.parameters["properties"]["action"]["enum"] == ["plan", "status", "list", "reconcile_report"]
    out, err = asyncio.run(CT.call(settings.state_dir, tmp_path, "lampway_compute", {"action": "submit"}))
    assert err is True and "plan, status, list or reconcile_report" in out
    out, err = asyncio.run(CT.call(settings.state_dir, tmp_path, "lampway_compute", {"action": "list"}))
    assert err is False and json.loads(out)["count"] == 0
    out, err = asyncio.run(CT.call(settings.state_dir, tmp_path, "lampway_compute", {"action": "plan", "job": {"recipe": "probe", "inputs": [], "backend": "boat"}}))
    assert err is True and "not enabled" in out                                              # a provider is the user's choice: none is enabled on a fresh install
