# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Test support for Mode 1's panes (docs/reports/agent-modes-spec.md A1): a stand-in engine build (no Hermes runs), the real
``Mode1Units`` on it, and a reader for the MCP server a pane's rendered config names."""

import json
import os
import re
import stat
import sys
from pathlib import Path

from lampway_server import capabilities as CAP
from lampway_server.engine import hermes_config as HC
from lampway_server.engine.units import Mode1Units


def fake_engine(root: Path) -> dict:
    """A finished-looking build: an executable ``env/bin/hermes`` that does nothing and a prebuilt TUI bundle."""
    build = Path(root) / "hermes" / "v0-test"
    (build / "env" / "bin").mkdir(parents=True, exist_ok=True)
    exe = build / "env" / "bin" / "hermes"
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    (build / "src" / "ui-tui" / "dist").mkdir(parents=True, exist_ok=True)
    (build / "src" / "ui-tui" / "dist" / "entry.js").write_text("// prebuilt\n")
    record = {"engine": "hermes", "tag": "v0-test", "entry": "env/bin/hermes", "hermes": "env/bin/hermes", "tui": "src/ui-tui",
              "source": "src"}
    (build / "engine.json").write_text(json.dumps(record))
    return {**record, "dir": str(build), "entry_path": str(exe)}


def units_for(cockpit, state_dir, registry, *, engine: dict, base="http://127.0.0.1:8787", start_sessions=False) -> Mode1Units:
    """The real Mode 1 hook on a stand-in engine; ``start_sessions`` False: nothing connects to a serve (none runs)."""
    def write_config(home, gateway_url, token, model_id, worker=False, mcp_url=None, mcp_headers=None, rendered=None):
        board = CAP.ACTIVE
        return HC.write(home, board, CAP.project(), gateway_url, token, model_id, mcp_url=mcp_url, mcp_headers=mcp_headers, rendered=rendered,
                        asks_user=not worker)
    units = Mode1Units(cockpit=cockpit, engine=engine, state_dir=state_dir, server_base=base, registry=registry,
                       write_config=write_config, model_id="lampway", proxy_vars={"NO_PROXY": "127.0.0.1"},
                       pane_mcp_url=getattr(cockpit, "pane_mcp_url", None),
                       environ={**{k: v for k, v in os.environ.items() if k != "LAMPWAY_HERMES_TUI_DIR"}, "LAMPWAY_NODE": sys.executable})
    if not start_sessions:
        units.opened_records = []
        units.opened = units.opened_records.append
    return units


_ENTRY = re.compile(r'^mcp_servers:\n  lampway:\n    url: "([^"]+)"\n    headers:\n((?:      .+\n)+)', re.M)
_HEADER = re.compile(r'^      ([A-Za-z0-9_-]+|"[^"]+"): "([^"]*)"$', re.M)


def mcp_entry(home) -> tuple:
    """(url, headers) of the one MCP server a Mode 1 pane's config.yaml declares (the renderer's own deterministic shape)."""
    text = (Path(home) / "config.yaml").read_text()
    m = _ENTRY.search(text)
    assert m, text
    return m.group(1), {k.strip('"'): v for k, v in _HEADER.findall(m.group(2))}
