# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Execute the real two-worker fixture's cleanup after failure before its first status publication."""
import ast
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
from types import SimpleNamespace


def test_early_worker_fixture_failure_still_stops_its_own_herdr_without_status(tmp_path, monkeypatch):
    source = Path(__file__).parent / "lampway_tools" / "test_agent_modes_workers_live.py"
    tree = ast.parse(source.read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "test_two_real_mode1_workers_collect_into_real_parent_blender")
    guarded = next(node for node in function.body if isinstance(node, ast.Try))
    # Run the fixture's actual finally body, without launching any app, provider or process.
    cleanup = ast.Module(body=guarded.finalbody, type_ignores=[])
    fixture_root = tmp_path / "fixture-herdr"
    fixture_root.mkdir()
    unrelated = tmp_path / "another-herdr"
    unrelated.mkdir()
    client_root = tmp_path / "client"
    client_root.mkdir()
    stopped = []
    monkeypatch.delenv("LAMPWAY_WORKER_ARTIFACTS", raising=False)

    def stop(root, confirmed=False):
        stopped.append((root, confirmed))

    scope = dict(json=json, os=os, Path=Path, shutil=shutil, signal=signal, subprocess=subprocess,
                 proof={}, gateway=[], factories=[], main=SimpleNamespace(requests=[]),
                 client_root=client_root, process=None, client=object(), root=fixture_root,
                 L=SimpleNamespace(stop_server=stop))
    exec(compile(cleanup, str(source), "exec"), scope)
    assert stopped == [(fixture_root, True)]
    assert not fixture_root.exists() and unrelated.is_dir()
    assert not (client_root / "status.json").exists()
