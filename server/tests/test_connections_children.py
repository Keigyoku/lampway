# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""connections_store.md test 12 and connections_migration.md test 4 (finding F4): a child process gets a scrubbed environment plus
exactly the connections it needs, under the variable names it already reads. A Meshy driver sees MESHY_API_KEY (from wherever
Connections resolved it) and no other key; a claude or codex CLI, a Tripo browser driver and a server tool's driver see no key at all."""

import asyncio
import os

import pytest

from lampway_server import connections as C
from lampway_server.connections import hub as H
from lampway_server.connections import store as CS

MESHY = "msy-FAKE-CHILD-SENTINEL-444444444444"
SERVER_ENV = {"PATH": "/usr/bin:/bin", "HOME": "/home/user", "LAMPWAY_STUDIO_POLL_S": "0", "OPENROUTER_API_KEY": "sk-" "or-v1-FAKE-CHILD",
              "ANTHROPIC_API_KEY": "sk-" "ant-FAKE-CHILD", "GH_TOKEN": "gh-FAKE-CHILD", "LAMPWAY_JWT_SECRET": "jwt-FAKE-CHILD", "FAL_KEY": "fal-FAKE-CHILD",
              "TRIPO_API_KEY": "tsk-FAKE-CHILD", "LAMPWAY_USER_PASSWORD": "pw-FAKE-CHILD"}
KEYS = ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "GH_TOKEN", "LAMPWAY_JWT_SECRET", "FAL_KEY", "TRIPO_API_KEY", "LAMPWAY_USER_PASSWORD",
        "MESHY_API_KEY_FILE")


@pytest.fixture
def server_env(tmp_path, monkeypatch):
    key_file = tmp_path / "keys" / "meshy.txt"
    key_file.parent.mkdir()
    key_file.write_text(MESHY + "\n")
    os.chmod(key_file, 0o600)
    env = dict(SERVER_ENV, MESHY_API_KEY_FILE=str(key_file))
    for k in list(os.environ):
        if any(t in k for t in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
            monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    C.set_active(H.Hub(tmp_path / "state", secrets_dir=tmp_path / "secrets", store=CS.MemoryStore(), route_on=lambda r: True))
    return env


def _clean(env):
    return [k for k in KEYS if k in env]


def test_children_get_only_their_connection_a_meshy_driver(server_env, tmp_path):
    from lampway_server.studios.service import StudioService
    seen = []

    def execute(argv, env, timeout):
        seen.append(env)
        return 0, "dry_run: verified\nprice_effective_credits: 20\nbalance_credits: 100\n"
    model = tmp_path / "project" / "piece.glb"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"glb")
    svc = StudioService(tmp_path / "project", execute)
    out = asyncio.run(svc.plan("meshy.uv_unwrap", {"model": str(model)}, by="agent"))
    assert out["state"] in ("needs_approval", "refused") and seen
    env = seen[0]
    assert env["MESHY_API_KEY"] == MESHY, "the key reaches the driver under the name it reads, from the pointer file"
    assert _clean(env) == [] and env["PATH"] == "/usr/bin:/bin" and env["LAMPWAY_STUDIO_POLL_S"] == "0"


def test_a_tripo_browser_driver_gets_no_key(server_env, tmp_path):
    from lampway_server.studios.service import StudioService
    seen = []
    svc = StudioService(tmp_path / "project", lambda argv, env, t: (seen.append(env), (0, "state: ok\n"))[1])

    async def go():
        out = await svc.plan("tripo.state", {}, by="agent")
        await svc.wait(out["job"]["id"])
    asyncio.run(go())
    assert seen and _clean(seen[0]) == [] and "MESHY_API_KEY" not in seen[0]


def test_a_claude_cli_run_sees_no_key(server_env, monkeypatch):
    from lampway_server.agent import cli_adapters as CA
    captured = {}

    async def fake_exec(*cmd, **kw):
        captured.update(kw)
        raise FileNotFoundError(cmd[0])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    with pytest.raises(CA.CLIError):
        asyncio.run(CA._run(["claude", "-p"], "hello", 5))
    env = captured["env"]
    assert env is not None, "the child must not inherit the whole server environment"
    assert _clean(env) == [] and "MESHY_API_KEY" not in env and env["HOME"] == "/home/user"


def test_codex_image_sees_no_key(server_env, monkeypatch, tmp_path):
    from lampway_server.agent import cli_adapters as CA
    import subprocess
    captured = {}

    def fake_run(cmd, **kw):
        captured.update(kw)
        raise FileNotFoundError(cmd[0])
    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(CA.CLIError):
        CA.codex_image("codex", "a helmet", [], tmp_path / "out", "x")
    assert captured.get("env") is not None and _clean(captured["env"]) == []


def test_a_server_tool_driver_sees_no_key_and_keeps_the_owners_arming(server_env, monkeypatch):
    from lampway_server.agent import server_tools as ST
    monkeypatch.setenv("LAMPWAY_STUDIO_ARMED", "1")
    env = ST.environment()
    assert _clean(env) == [] and env["LAMPWAY_STUDIO_ARMED"] == "1" and ST.PKG_ROOT in env["PYTHONPATH"]
