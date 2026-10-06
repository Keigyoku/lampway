# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""connections_store.md tests 11 and 15: the host scan opens no credential file and holds no value; every registry check is a read
(only its declared requests, only GET or the named free tool), and every documented answer a check is built on is free."""

import builtins
import io
import json
import os

import httpx
import pytest

from lampway_server.connections import hub as H
from lampway_server.connections import registry as R
from lampway_server.connections import store as CS

HOST_SENTINEL = "HOST-FAKE-SENTINEL-do-not-read-5555"


def _plant(home):
    planted = []
    for spec in R.SPECS.values():
        for p in spec.paths:
            full = home / p[2:]
            if p.endswith("profile"):
                full.mkdir(parents=True, exist_ok=True)
                continue
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(json.dumps({"token": HOST_SENTINEL, "access_token": HOST_SENTINEL}))
            os.chmod(full, 0o600)
            planted.append(full)
    return planted


def test_host_scan_reads_no_values(tmp_path, monkeypatch):
    home = tmp_path / "home"
    planted = _plant(home)
    assert len(planted) >= 6
    bins = {"claude", "codex", "opencode", "gh"}
    boat = home / ".ascii" / "bin" / "boat"
    boat.parent.mkdir(parents=True)
    boat.write_text("#!/bin/sh\n")
    os.chmod(boat, 0o700)
    opened = []
    real_open, real_io_open, real_os_open = builtins.open, io.open, os.open

    def rec_open(path, *a, **kw):
        opened.append(str(path))
        return real_open(path, *a, **kw)

    def rec_os_open(path, *a, **kw):
        opened.append(str(path))
        return real_os_open(path, *a, **kw)
    hub = H.Hub(tmp_path / "state", secrets_dir=tmp_path / "secrets", env={"PATH": "/usr/bin"}, store=CS.MemoryStore(),
                which=lambda b: f"/usr/bin/{b}" if b in bins else None, home=home, route_on=lambda r: True,
                transport=httpx.MockTransport(lambda r: pytest.fail(f"the scan contacted {r.url}")))
    monkeypatch.setattr(builtins, "open", rec_open)
    monkeypatch.setattr(io, "open", rec_open)
    monkeypatch.setattr(os, "open", rec_os_open)
    result = hub.scan(by="user")
    views = hub.view()
    ones = [hub.one(cid) for cid in R.SPECS]
    monkeypatch.undo()
    for p in planted:
        assert str(p) not in opened, f"the scan opened {p}"
    blob = json.dumps([result, views, ones])
    assert HOST_SENTINEL not in blob
    for f in (tmp_path / "state").rglob("*"):
        if f.is_file():
            assert HOST_SENTINEL not in f.read_text()
    claude = next(v for v in ones if v["id"] == "claude_cli")
    assert claude["state"] == "not_checked" and claude["next_step"] == "installed; status not read"
    assert claude["host_files"] == [{"path": "~/.claude/.credentials.json", "exists": True, "owner_only": True}]
    assert next(v for v in ones if v["id"] == "compute:boat")["active_source"]["mode"] == "host"


# --------------------------------------------------------------------------------------------- test 15: every check is a read
DOCUMENTED = {                                       # the answer each check is built on (CATALOGUE.md table C), as documented
    "openrouter": {"data": {"label": "sk-" "or-v1-abc...xyz", "limit": 100, "limit_remaining": 74.5, "usage": 25.5, "is_free_tier": False}},
    "anthropic": {"data": [{"id": "claude-sonnet-5-5"}]},
    "custom_llm": {"data": [{"id": "llama"}]},
    "studio:hyper3d": {"balance": 120},
    "studio:meshy": {"balance": 1240},
    "studio:hi3d": {"data": {"balance": 33, "accessToken": "hi3d-bearer-FAKE-000000"}},
    "studio:tripo_api": {"data": {"balance": 50}},
    "fal": {"prices": [{"endpoint_id": "fal-ai/flux/dev", "unit_price": 0.025}]},
    "huggingface": {"name": "someone", "auth": {"accessToken": {"role": "read"}}},
}
FAKE_ENV = {"OPENROUTER_API_KEY": "sk-" "or-v1-FAKE", "ANTHROPIC_API_KEY": "sk-" "ant-FAKE", "OPENAI_API_KEY": "ollama-FAKE", "HYPER3D_API_KEY": "h3d-FAKE",
            "MESHY_API_KEY": "msy-FAKE", "HITEM3D_CLIENT_ID": "cid-FAKE", "HITEM3D_CLIENT_SECRET": "csec-FAKE", "TRIPO_API_KEY": "tsk-FAKE",
            "FAL_KEY": "fal-FAKE", "HF_TOKEN": "hf_FAKE"}


def test_every_documented_answer_is_free():
    for cid, body in DOCUMENTED.items():
        assert not any(w in json.dumps(body).lower() for w in ("charged", "consumed")), cid


@pytest.mark.parametrize("cid", sorted(c for c, s in R.SPECS.items() if s.check.kind == "http"))
def test_every_check_is_a_read(cid, tmp_path):
    spec = R.SPECS[cid]
    assert cid in DOCUMENTED, f"{cid} has an http check with no documented answer in this test"
    seen = []

    def answer(request):
        seen.append((request.method, str(request.url)))
        return httpx.Response(200, json=DOCUMENTED[cid])
    hub = H.Hub(tmp_path / "state", secrets_dir=tmp_path / "secrets", env=dict(FAKE_ENV), store=CS.MemoryStore(), which=lambda b: None,
                home=tmp_path / "home", route_on=lambda r: True, transport=httpx.MockTransport(answer), endpoint=lambda: "http://10.0.0.5:11434/v1")
    view = hub.test(cid, by="user")
    assert view["state"] == "connected", view
    declared = {(m, u.replace("{base}", "http://10.0.0.5:11434/v1")) for m, u in spec.check.reads}
    assert seen and set(seen) <= declared, (seen, declared)
    assert all(m == "GET" for m, u in seen if not u.endswith("/auth/token")), seen


def test_the_mcp_checks_call_only_initialize_tools_list_and_the_named_free_tool(tmp_path):
    calls = []

    class FakeMcp:
        def tools(self):
            calls.append("tools/list")
            return [{"name": "balance"}, {"name": "generate_video"}]

        def call(self, name, args):
            calls.append(name)
            return {"subscription_plan_type": "plus", "credits": 623.86}

    class SignedIn:
        def status(self):
            return {"signed_in": True, "client_id": "c"}
    hub = H.Hub(tmp_path / "state", secrets_dir=tmp_path / "secrets", env={}, store=CS.MemoryStore(), which=lambda b: None, home=tmp_path / "home",
                route_on=lambda r: True, oauth={"higgsfield": SignedIn()}, mcp_clients={"higgsfield": FakeMcp})
    v = hub.test("higgsfield", by="user")
    assert calls == ["tools/list", "balance"] and v["identity"]["plan"] == "plus" and v["identity"]["balance"]["amount"] == 623.86
    assert {s.check.tool for s in R.SPECS.values() if s.check.kind == "mcp"} <= {"", "balance"}


def test_the_cli_check_runs_only_the_status_command_with_a_scrubbed_environment(tmp_path):
    runs = []

    def runner(argv, **kw):
        runs.append((argv, kw["env"]))

        class P:
            returncode, stdout, stderr = 0, json.dumps({"plan": "free", "health": "ok", "email": "x@example.com"}), ""
        return P()
    boat = tmp_path / "home" / ".ascii" / "bin" / "boat"
    boat.parent.mkdir(parents=True)
    boat.write_text("#!/bin/sh\n")
    os.chmod(boat, 0o700)
    hub = H.Hub(tmp_path / "state", secrets_dir=tmp_path / "secrets", env={"PATH": "/usr/bin", "OPENROUTER_API_KEY": "sk-" "or-v1-FAKE"}, store=CS.MemoryStore(),
                which=lambda b: None, home=tmp_path / "home", route_on=lambda r: True, cli_runner=runner)
    v = hub.test("compute:boat", by="user")
    assert v["state"] == "connected"
    assert runs[0][0] == [str(boat), "status", "--json"] and "OPENROUTER_API_KEY" not in runs[0][1]
    assert "x@example.com" not in (tmp_path / "state" / "connections.json").read_text()
