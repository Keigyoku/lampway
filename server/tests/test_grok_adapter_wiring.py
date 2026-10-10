# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Candidate Grok wiring must preserve literal tasks and refuse missing authority."""
import json
from pathlib import Path
import sys

import pytest

from lampway_server import native_worker_readiness as N
from lampway_server.herdr import launcher as L
from lampway_server.herdr.harnesses.base import DirectServer, PaneSpec
from lampway_server.herdr.harnesses.grok import Grok


def worker(tmp_path, **changes):
    values = dict(cwd=str(tmp_path), desktop=False,
        mcp_config_path=str(tmp_path / "root/panes/worker/mcp.json"),
        direct=(DirectServer("lampway", "http://127.0.0.1:9/api/v1/mcp/pane",
            {"X-Mixar-Session-Id": "swarm:one:worker"}, "WORKER_TOKEN", "synthetic-secret"),))
    return PaneSpec(**{**values, **changes})


def test_candidate_native_wrap_uses_production_wiring_and_one_literal_task(tmp_path, monkeypatch):
    adapter = Grok()
    pane = worker(tmp_path)
    with pytest.raises(ValueError, match="unproved"):
        adapter.launch(pane, task="synthetic task")
    adapter.worker_ok = True  # Candidate fixture; no production readiness grant.
    description = dict(native="/synthetic/grok", native_sha256="a" * 64,
        bwrap="/synthetic/bwrap", bwrap_sha256="b" * 64,
        connector=dict(command="/synthetic/lampway-pane-mcp", args=[], sha256="c" * 64))
    monkeypatch.setattr(N, "grok_worker_description", lambda binary, *, cwd: dict(description))
    task = "--leading-option literal 'quotes' $NOT_AN_ENV; $(no-shell)\nsecond line"
    wiring = adapter.lampway_tools(pane)
    metadata_path = str(Path(pane.mcp_config_path).with_name("grok-worker.json"))
    metadata = json.loads(wiring.files[metadata_path])
    assert metadata["root"] == str(tmp_path / "root")
    assert metadata["cwd"] == pane.cwd and "task" not in metadata
    assert metadata["inner_socket"] != metadata["outer_socket"]
    assert metadata["connector"] == description["connector"]
    assert adapter.launch(pane, task=task) == ["grok", "--leader-socket", metadata["outer_socket"],
        "wrap", "--", sys.executable, "-m", "lampway_server.grok_worker", "--config", metadata_path,
        "--task=" + task]
    assert "synthetic-secret" not in str(wiring.argv) and "synthetic-secret" not in str(metadata)
    binding = json.loads(wiring.files[pane.mcp_config_path])
    assert binding["binding"] == "swarm:one:worker" and binding["desktop"] is None
    assert binding["direct"][0]["headers"]["Authorization"] == "Bearer synthetic-secret"
    assert not wiring.verified
    main = PaneSpec(cwd=str(tmp_path))
    assert adapter.launch(main, task="native task") == ["grok", "native task"]
    assert adapter.lampway_tools(main).argv == ()


@pytest.mark.parametrize("changes", [dict(direct=()), dict(launcher=("unwanted-desktop",)),
    dict(mcp_config_path=None), dict(scene_session_id="wrong-binding")])
def test_malformed_candidate_binding_refuses_before_probe(tmp_path, monkeypatch, changes):
    adapter = Grok(); adapter.worker_ok = True
    def unexpected(*args, **kwargs):
        raise AssertionError("malformed binding reached native probe")
    monkeypatch.setattr(N, "grok_worker_description", unexpected)
    with pytest.raises(ValueError, match="direct-only swarm"):
        adapter.launch(worker(tmp_path, **changes), task="synthetic task")


def test_readiness_queries_native_identity_at_project_and_requires_namespace_success(tmp_path, monkeypatch):
    from lampway_server import grok_worker as G
    calls = []
    monkeypatch.setattr(G, "candidate_paths", lambda binary: ("/native/grok", "/native/bwrap", "/native/helper"))
    monkeypatch.setattr(G, "preflight", lambda *args: {"native": args[0], "namespace_probe": ["/native/bwrap", "--", "/bin/true"]})
    def probe(argv, env, **kwargs):
        calls.append((argv, env, kwargs))
        return (0, "[]") if "mcp" in argv else (1, "")
    monkeypatch.setattr(L, "worker_probe", probe)
    with pytest.raises(ValueError, match="unprivileged namespaces"):
        N.grok_worker_description("/native/grok", cwd=str(tmp_path))
    assert calls == [(["/native/grok", "mcp", "list", "--json"], {}, {"cwd": str(tmp_path)}),
        (["/native/bwrap", "--", "/bin/true"], {}, {})]
