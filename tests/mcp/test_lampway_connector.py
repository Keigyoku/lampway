# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Connect AI Apps (MCP) connector speaks Lampway: the MCP server is named `lampway`, the launcher is ~/.lampway/connector/lampway-mcp, the setup guide is OUR docs; an
existing install's old ~/.mixar/connector/installation.json is migrated once, the old launcher path stays a shim for one release, and an old `mixar` entry in Codex's
config.toml or Claude Code is replaced rather than left beside the new one."""

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tomllib

import pytest

from mixar.config import brand
from mixar.modules.mcp_bridge import constants
from mixar.modules.mcp_bridge.core import app_configs, discovery, installation, setup

NEW = "/Users/me/.lampway/connector/lampway-mcp"


def test_every_rendered_setup_names_the_server_lampway_and_never_mixar(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    out = {key: setup.render(key, NEW, []) for key, _n, _h in app_configs.APPS}
    assert shlex.split(out["CLAUDE_CODE"]) == ["claude", "mcp", "add", "--scope", "user", "lampway", "--", NEW]
    assert tomllib.loads(out["CODEX"])["mcp_servers"]["lampway"]["command"] == NEW
    assert set(json.loads(out["JSON"])["mcpServers"]) == {"lampway"} and set(json.loads(out["CURSOR"])["mcpServers"]) == {"lampway"}
    assert set(json.loads(out["VSCODE"])["servers"]) == {"lampway"} and set(json.loads(out["OPENCODE"])["mcp"]) == {"lampway"}
    assert not [k for k, v in out.items() if "mixar" in v.lower()], "the printed config the user copies carries no Mixar"


def test_the_launcher_lives_under_dot_lampway_and_the_discovery_override_is_lampways(tmp_path, monkeypatch):
    monkeypatch.delenv("MIXAR_MCP_DISCOVERY_DIR", raising=False)
    monkeypatch.delenv("LAMPWAY_MCP_DISCOVERY_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert discovery.discovery_directory() == tmp_path / ".lampway" / "mcp" and installation.directory() == tmp_path / ".lampway" / "connector"
    monkeypatch.setenv("MIXAR_MCP_DISCOVERY_DIR", str(tmp_path / "old"))
    assert discovery.discovery_directory() == tmp_path / "old", "the old variable still works for one release"
    monkeypatch.setenv("LAMPWAY_MCP_DISCOVERY_DIR", str(tmp_path / "new"))
    assert discovery.discovery_directory() == tmp_path / "new", "the new variable wins"


@pytest.mark.skipif(os.name == "nt", reason="Unix launcher")
def test_provision_writes_lampway_mcp_and_an_old_install_gets_a_shim_at_the_old_path(tmp_path, monkeypatch):
    monkeypatch.delenv("MIXAR_MCP_DISCOVERY_DIR", raising=False)
    monkeypatch.delenv("LAMPWAY_MCP_DISCOVERY_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    script = tmp_path / "mcp.py"
    script.write_text("import json,sys; print(json.dumps(['ran', *sys.argv[1:]]))")
    launcher = installation.provision(sys.executable, script, sys.executable)
    assert launcher == tmp_path / ".lampway" / "connector" / "lampway-mcp" and not (tmp_path / ".mixar").exists(), "a fresh install never creates the old folder"
    old = tmp_path / ".mixar" / "connector"
    old.mkdir(parents=True)
    (old / "mixar-mcp").write_text("#!/bin/sh\necho stale\n")
    installation.provision(sys.executable, script, sys.executable)
    assert json.loads(subprocess.check_output([str(old / "mixar-mcp"), "x"], text=True)) == ["ran", "x"], "the old path forwards to the new launcher"


def test_an_old_installation_json_is_read_once_and_written_to_the_new_location(tmp_path, monkeypatch):
    monkeypatch.delenv("MIXAR_MCP_DISCOVERY_DIR", raising=False)
    monkeypatch.delenv("LAMPWAY_MCP_DISCOVERY_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    old = tmp_path / ".mixar" / "connector"
    old.mkdir(parents=True)
    manifest = {"version": 1, "python": sys.executable, "script": str(tmp_path / "mcp.py"), "executable": sys.executable, "enabled": True}
    (old / "installation.json").write_text(json.dumps(manifest))
    assert installation.migrate() is True
    new = json.loads((tmp_path / ".lampway" / "connector" / "installation.json").read_text())
    assert new == manifest and (tmp_path / ".lampway" / "connector" / "lampway-mcp").exists() and (old / "installation.json").exists(), "the old file is left alone"
    changed = dict(new, enabled=False)
    (tmp_path / ".lampway" / "connector" / "installation.json").write_text(json.dumps(changed))
    assert installation.migrate() is False and json.loads((tmp_path / ".lampway" / "connector" / "installation.json").read_text()) == changed, "once"


def test_the_setup_guide_is_our_docs_not_mixars_website():
    assert "mixar" not in constants.SETUP_GUIDE_URL.lower() and constants.SETUP_GUIDE_URL.startswith(brand.WEBSITE_URL)
    assert constants.SETUP_GUIDE_URL.endswith("/docs/#connect-ai-apps")
    routes = (Path(__file__).resolve().parents[2] / "src/scripts/mixar/config/site_routes.txt").read_text().split()
    assert "/docs/" in routes, "the page the dialog opens is on the site's route list"


CODEX_OLD = '''model = "gpt-6"

[mcp_servers.mixar]
command = "/Users/me/.mixar/connector/mixar-mcp"
args = []
tool_timeout_sec = 610

[mcp_servers.other]
command = "other-server"
'''


def test_adding_to_codex_replaces_an_old_mixar_table_and_keeps_everything_else(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(CODEX_OLD)
    status, detail = app_configs.add_to_codex(NEW, [], cfg)
    assert status == "updated", (status, detail)
    got = tomllib.loads(cfg.read_text())
    assert set(got["mcp_servers"]) == {"lampway", "other"} and got["mcp_servers"]["lampway"]["command"] == NEW and got["model"] == "gpt-6"
    assert (tmp_path / "config.toml.lampway-backup").read_text() == CODEX_OLD, "the previous file is kept as config.toml.lampway-backup"
    assert app_configs.add_to_codex(NEW, [], cfg)[0] == "already"


def test_adding_to_claude_code_uses_the_lampway_name_and_retires_an_old_mixar_entry(monkeypatch):
    calls = []

    def fake_run(args):
        calls.append(args[1:])
        if args[1:3] == ["mcp", "get"] and args[3] == "mixar":
            return 0, "mixar: /old/path"
        return 0, ""
    monkeypatch.setattr(app_configs, "_run", fake_run)
    assert app_configs.add_to_claude_code(NEW, [], cli="/bin/claude")[0] == "added"
    assert ["mcp", "add", "--scope", "user", "lampway", "--", NEW] in calls
    assert ["mcp", "remove", "--scope", "user", "mixar"] in calls, "the old entry is removed after the new one is in"
    assert not any("mixar" in " ".join(c) and c[1] == "add" for c in calls)
