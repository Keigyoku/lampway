# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""BYOA B1 (docs/reports/agent-modes-spec.md): one adapter interface for every first-party harness, and the seven starting adapters
(captain's Q5): Claude Code, Codex CLI, Hermes Agent, OpenCode, Pi, Grok and Cursor.

Every binary here is a fake shell script on a PATH made for the test: no real harness is started, no login is read and nothing
leaves the machine. login_state runs only the fake's status command, inside the harness's egress route. The argv, wiring, status
and key facts pinned here were checked against installed copies (each adapter's FACTS names the version and the command); the
fakes print what those copies printed."""
import importlib.util
import json
import os
import shlex
import stat
from pathlib import Path

import pytest

from lampway_server import egress as EG
from lampway_server.herdr import harnesses as HN
from lampway_server.herdr import host as H
from lampway_server.herdr import launcher as L

from .test_byoa_egress import FakeHerdr

IDS = ("claude", "codex", "hermes", "opencode", "pi", "grok", "cursor")
BINARIES = {"claude": "claude", "codex": "codex", "hermes": "hermes", "opencode": "opencode", "pi": "pi", "grok": "grok", "cursor": "cursor-agent"}
BYPASS_TOKENS = ("--dangerously-skip-permissions", "--dangerously-bypass-approvals-and-sandbox", "--auto", "--force", "--yolo", "--always-approve")
#: The harnesses whose per-pane wiring an installed copy was seen to read (each adapter's FACTS); the others have no per-pane way in.
VERIFIED_WIRING = ("claude", "codex", "opencode", "pi")
SUPPORTED_WIRING = (*VERIFIED_WIRING, "cursor", "hermes", "grok")  # Native symbolic connectors require explicit user installation; account calls remain owed
#: herdr 0.9.3's kind for each harness (src/detect/mod.rs interactive_agent_executable): herdr starts every one of them itself.
HERDR_KINDS = {"claude": "claude", "codex": "codex", "hermes": "hermes", "opencode": "opencode", "pi": "pi", "grok": "grok", "cursor": "cursor"}


def fake_bin(d: Path, name: str, body: str) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text("#!/bin/sh\n" + body + "\n")
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


@pytest.fixture
def only_path(monkeypatch, tmp_path):
    """PATH holds only the test's own fake binaries (never the machine's real harnesses)."""
    d = tmp_path / "bin"
    d.mkdir()
    monkeypatch.setenv("PATH", str(d))
    return d


@pytest.fixture
def strict(tmp_path):
    m = EG.Egress(tmp_path / "egress-state")
    prev = EG.ACTIVE
    EG.set_active(m)
    yield m
    EG.set_active(prev)


# ------------------------------------------------------------------------------------------------------------- the interface
def test_the_seven_starting_adapters_in_order_each_implementing_the_interface():
    assert tuple(HN.ids()) == IDS
    for hid in IDS:
        a = HN.get(hid)
        assert isinstance(a, HN.HarnessAdapter), hid
        assert a.id == hid and a.label and a.binary == BINARIES[hid] and a.route == f"byoa:{hid}" and a.route in EG.ROUTES


def test_the_protocol_names_exactly_the_specs_members():
    members = {n for n in vars(HN.HarnessAdapter) if not n.startswith("_")} | set(getattr(HN.HarnessAdapter, "__annotations__", {}))
    assert members == {"id", "label", "detect", "login_state", "launch", "resume", "lampway_tools", "observe", "bypass_flag"}


ARGV = [
    # id, resume id (None = new), bypass, effort, expected argv (binary first)
    ("claude", None, False, None, ["claude", "--session-id", "s-1"]),
    ("claude", "c-9", True, "high", ["claude", "--resume", "c-9", "--dangerously-skip-permissions", "--effort", "high"]),
    ("codex", None, False, "max", ["codex", "--no-alt-screen", "-c", 'model_reasoning_effort="max"']),
    ("codex", "r-1", False, None, ["codex", "resume", "r-1", "--no-alt-screen"]),
    ("opencode", "ses_2", False, None, ["opencode", "--session", "ses_2"]),
    ("hermes", None, False, None, ["hermes"]),
    ("hermes", "h-1", True, None, ["hermes", "--resume", "h-1", "--yolo"]),                 # Hermes v0.21.5 --help
    ("pi", None, False, None, ["pi", "--session-id", "s-1"]),                               # Pi 1.0.4 --help: Lampway picks the id
    ("pi", "p-1", False, None, ["pi", "--session", "p-1"]),
    ("grok", None, False, None, ["grok", "--session-id", "s-1"]),                           # Grok 1.0.46 --help: a new conversation's UUID
    ("grok", "g-1", True, None, ["grok", "--resume", "g-1", "--always-approve"]),
    ("cursor", None, False, None, ["cursor-agent"]),
    ("cursor", "chat-1", True, None, ["cursor-agent", "--resume", "chat-1", "--force"]),
]


@pytest.mark.parametrize("hid,resume_id,bypass,effort,want", ARGV)
def test_each_adapter_builds_the_recorded_argv(hid, resume_id, bypass, effort, want, tmp_path):
    a = HN.get(hid)
    pane = HN.PaneSpec(cwd=str(tmp_path), effort=effort, bypass=bypass, session_id="s-1" if HN.get(hid).picks_session_id and not resume_id else None)
    assert (a.resume(resume_id, pane) if resume_id else a.launch(pane)) == want


@pytest.mark.parametrize("hid", IDS)
def test_no_adapter_emits_a_bypass_flag_unless_the_user_ticked_it(hid, tmp_path):
    a = HN.get(hid)
    for argv in (a.launch(HN.PaneSpec(cwd=str(tmp_path))), a.resume("x-1", HN.PaneSpec(cwd=str(tmp_path)))):
        assert not [t for t in argv if t in BYPASS_TOKENS or t in a.bypass_flag()], (hid, argv)
    ticked = a.launch(HN.PaneSpec(cwd=str(tmp_path), bypass=True))
    assert all(f in ticked for f in a.bypass_flag())


@pytest.mark.parametrize("hid", IDS)
def test_the_tool_wiring_names_the_launcher_and_the_bound_session(hid, tmp_path):
    a = HN.get(hid)
    pane = HN.PaneSpec(cwd=str(tmp_path), scene_session_id="scene-7", mcp_config_path=str(tmp_path / "pane" / "mcp.cfg"), launcher=("/opt/lw/lampway-mcp",))
    w = a.lampway_tools(pane)
    assert w.launcher == ("/opt/lw/lampway-mcp",) and w.bound_session == "scene-7"
    text = json.dumps({"argv": list(w.argv), "env": w.env, "files": w.files})
    assert "/opt/lw/lampway-mcp" in text and "LAMPWAY_BOUND_SESSION" in text and "scene-7" in text, hid
    assert all(Path(p).is_relative_to(Path(pane.mcp_config_path).parent) for p in w.files), hid
    assert w.verified is (hid in VERIFIED_WIRING), hid                    # only what an installed copy was seen to read claims verified
    assert (w.kind == "unavailable") is (hid not in SUPPORTED_WIRING) is (not HN.get(hid).tools_reachable), hid


def test_claude_code_reaches_lampway_through_a_per_pane_mcp_config_file(tmp_path):
    a = HN.get("claude")
    cfg = tmp_path / "pane" / "mcp.json"
    pane = HN.PaneSpec(cwd=str(tmp_path), session_id="s-1", scene_session_id="scene-7", mcp_config_path=str(cfg), launcher=("/opt/lw/lampway-mcp",))
    assert a.launch(pane) == ["claude", "--session-id", "s-1", "--mcp-config", str(cfg)]
    entry = json.loads(a.lampway_tools(pane).files[str(cfg)])["mcpServers"]["lampway"]
    assert entry == {"command": "/opt/lw/lampway-mcp", "args": [], "env": {"LAMPWAY_BOUND_SESSION": "scene-7"}}


def test_codex_reaches_lampway_through_config_overrides_on_its_own_command_line(tmp_path):
    a = HN.get("codex")
    pane = HN.PaneSpec(cwd=str(tmp_path), scene_session_id="scene-7", mcp_config_path=str(tmp_path / "p" / "mcp.toml"), launcher=("/opt/lw/lampway-mcp",))
    argv = a.launch(pane)
    assert argv[:2] == ["codex", "--no-alt-screen"]
    assert ["-c", 'mcp_servers.lampway.command="/opt/lw/lampway-mcp"'] == argv[2:4]
    assert "mcp_servers.lampway.env.LAMPWAY_BOUND_SESSION=\"scene-7\"" in argv


def test_pi_reaches_lampway_through_lampways_own_extension_and_its_own_mcp_client(tmp_path):
    """Pi 1.0.4 has MCP built in but reads only the user's and the project's mcp.json: Lampway's extension (-e) hands it this pane's
    own entries (pi.registerMcpServer). Checked live in test_byoa_pi_live.py where Pi is installed."""
    from lampway_server.herdr.harnesses import pi as PI
    cfg = tmp_path / "pane" / "mcp.json"
    d = HN.DirectServer("lampway_swarm", "http://127.0.0.1:8787/api/v1/mcp/pane", {}, "LAMPWAY_PANE_KEY", "k-1")
    pane = HN.PaneSpec(cwd=str(tmp_path), session_id="s-1", scene_session_id="scene-7", mcp_config_path=str(cfg), launcher=("/opt/lw/lampway-mcp",),
                       direct=(d,))
    w = HN.get("pi").lampway_tools(pane)
    assert w.kind == "extension" and w.verified is True and w.argv == ("-e", str(PI.EXTENSION)) and w.env == {"LAMPWAY_PI_MCP": str(cfg)}
    assert PI.EXTENSION.is_file() and PI.EXTENSION.parent == Path(HN.__file__).parent       # shipped beside the adapters (package data)
    servers = json.loads(w.files[str(cfg)])["mcpServers"]
    assert servers["lampway"] == {"command": "/opt/lw/lampway-mcp", "args": [], "env": {"LAMPWAY_BOUND_SESSION": "scene-7"}}
    assert servers["lampway_swarm"] == {"url": "http://127.0.0.1:8787/api/v1/mcp/pane", "headers": {"Authorization": "Bearer k-1"}}
    assert HN.get("pi").launch(pane) == ["pi", "--session-id", "s-1", "-e", str(PI.EXTENSION)]
    assert "k-1" not in " ".join(HN.get("pi").launch(pane)) and "k-1" not in json.dumps(w.env)    # the bearer only in the 0600 file


def test_the_pi_extension_is_a_wrapper_only():
    """The extension reads one file (the pane's own config, named by LAMPWAY_PI_MCP) and registers its entries with Pi's own MCP
    client: no process, no network, no other file, nothing written."""
    from lampway_server.herdr.harnesses import pi as PI
    src = PI.EXTENSION.read_text(encoding="utf-8")
    assert ("SPDX-" + "License-Identifier: GPL-3.0-or-later") in src and "export default function" in src
    assert src.count("readFileSync(") == 1 and "process.env.LAMPWAY_PI_MCP" in src and "pi.registerMcpServer(" in src
    for banned in ("child_process", "spawn(", "exec(", "fetch(", "http", "writeFile", "mcp.json\"", "~/.pi"):
        assert banned not in src.replace("~/.pi/agent/mcp.json or the project's .pi/mcp.json", ""), banned


@pytest.mark.parametrize("hid", ("hermes", "grok"))
def test_symbolic_connector_harnesses_keep_explicit_setup_and_proof_limits_in_listing(hid, only_path):
    a = HN.get(hid)
    assert a.tools_reachable is True and "install" in a.tools_note.lower() and "unverified" in a.tools_note.lower(), hid
    row = next(r for r in HN.listing() if r["id"] == hid)
    assert row["tools"] is True and row["tools_note"] == a.tools_note, row
    assert all(r["tools"] is True and r["tools_note"] == "" for r in HN.listing() if r["id"] in VERIFIED_WIRING)


def test_an_unbound_pane_carries_no_wiring_flag(tmp_path):
    for hid in IDS:
        argv = HN.get(hid).launch(HN.PaneSpec(cwd=str(tmp_path), session_id="s-1"))
        assert "--mcp-config" not in argv and not any("mcp_servers" in t for t in argv), hid


# ---------------------------------------------------------------------------------------------------------- detect and login
def test_a_harness_not_on_path_is_listed_not_installed_with_how_to_install_it(only_path):
    rows = {r["id"]: r for r in HN.listing()}
    assert set(rows) == set(IDS)
    for hid, r in rows.items():
        assert r["installed"] is False and r["status"] == "not installed" and r["install"] and r["path"] is None, r
        assert HN.get(hid).detect() is None


def test_detect_finds_the_binary_and_its_version_and_never_runs_a_status_command(only_path, tmp_path):
    log = tmp_path / "ran.txt"
    fake_bin(only_path, "codex", f'echo "$@" >> {log}\necho "codex-cli 0.99.0"')
    got = HN.get("codex").detect()
    assert got.path == str(only_path / "codex") and got.version == "codex-cli 0.99.0"
    assert log.read_text().split() == ["--version"]
    row = next(r for r in HN.listing() if r["id"] == "codex")
    assert row["installed"] is True and row["version"] == "codex-cli 0.99.0" and row["status"] == "installed"


def test_the_users_own_hermes_never_lampways_engine(only_path, tmp_path, monkeypatch):
    engine = fake_bin(tmp_path / "install" / "engines" / "hermes" / "v1" / "bin", "hermes", 'echo "engine"')
    monkeypatch.setenv("PATH", f"{engine.parent}{os.pathsep}{only_path}")
    assert HN.get("hermes").detect() is None                                     # only the engine is there: not the user's Hermes
    fake_bin(only_path, "hermes", 'echo "hermes 1.2.3"')
    got = HN.get("hermes").detect()
    assert got.path == str(only_path / "hermes") and got.version == "hermes 1.2.3"


def test_login_state_runs_only_the_harness_status_command_inside_its_route(only_path, tmp_path, strict):
    log = tmp_path / "ran.txt"
    fake_bin(only_path, "codex", f'echo "$@" >> {log}\necho "Logged in using ChatGPT"')
    off = HN.get("codex").login_state()
    assert off.state == "unknown" and "byoa:codex is off" in off.detail and not log.exists()
    strict.set_route("byoa:codex", True)
    on = HN.get("codex").login_state()
    assert on.state == "signed_in" and on.detail == "Logged in using ChatGPT"
    assert log.read_text().splitlines() == ["login status"]
    assert [r["route"] for r in strict.log() if r.get("event") == "send"] == ["byoa:codex"]


def test_a_failed_status_command_reads_as_signed_out_and_no_command_reads_as_unknown(only_path, strict):
    fake_bin(only_path, "claude", 'echo "Not logged in" ; exit 1')
    strict.set_route("byoa:claude", True)
    assert HN.get("claude").login_state().state == "signed_out"
    fake_bin(only_path, "grok", 'echo should-not-run; exit 3')
    assert HN.get("grok").login_state().state == "unknown"                       # Grok 1.0.46 has no status command: nothing runs


STATUS = [
    # harness, what the installed copy printed (its status argv), exit code, the state it means
    ("claude", '{"loggedIn": false, "authMethod": "none"}', 0, "signed_out"),         # `claude auth status`, 2.1.293
    ("claude", '{"loggedIn": true, "authMethod": "oauth_token"}', 0, "signed_in"),
    ("codex", "Not logged in", 1, "signed_out"),                                       # `codex login status`, 0.161.0 (exit 1)
    ("opencode", "Credentials ~/.local/share/opencode/auth.json\n0 credentials", 0, "signed_out"),   # `opencode auth list`, 1.18.35: exit 0
    ("opencode", "Credentials\n2 credentials", 0, "signed_in"),
    ("cursor", '{"status": "unauthenticated", "isAuthenticated": false, "message": "Not logged in"}', 0, "signed_out"),   # 2026.10.01
]


@pytest.mark.parametrize("hid,printed,code,want", STATUS)
def test_each_status_command_is_read_the_way_its_installed_copy_answers(hid, printed, code, want, only_path, strict, tmp_path):
    log = tmp_path / "ran.txt"
    fake_bin(only_path, BINARIES[hid], f'echo "$@" >> {log}\nprintf "%s\\n" {shlex.quote(printed)}\nexit {code}')   # builtins only: PATH holds the fakes
    strict.set_route(f"byoa:{hid}", True)
    assert HN.get(hid).login_state().state == want, (hid, printed)
    assert log.read_text().split() == list(HN.get(hid).status_argv)


def test_every_harness_names_its_interrupt_keys_in_herdrs_own_spelling():
    from .herdr_support import valid_key
    want = {"claude": ("esc",), "codex": ("esc",), "opencode": ("esc", "esc"), "pi": ("esc",), "hermes": ("ctrl+c",), "grok": ("ctrl+c",),
            "cursor": ("ctrl+c",)}
    assert {hid: HN.get(hid).interrupt_keys for hid in IDS} == want
    assert all(valid_key(k) for keys in want.values() for k in keys) and not valid_key("ctrl-c")


def test_every_harness_says_whether_it_takes_an_image_and_why_not(tmp_path):
    for hid in IDS:
        a = HN.get(hid)
        if a.takes_image_paths:
            assert a.with_images("what is this", ["/p/a.png", "/p/b.png"]) == "/p/a.png /p/b.png what is this", hid
        else:
            assert a.images_note, hid
            with pytest.raises(ValueError, match="no way to take an image"):
                a.with_images("what is this", ["/p/a.png"])
    assert [h for h in IDS if not HN.get(h).takes_image_paths] == ["cursor"]


def test_every_adapter_names_the_evidence_for_its_facts():
    for hid in IDS:
        facts = HN.get(hid).FACTS
        assert {"version", "argv", "status", "interrupt", "images"} <= set(facts), hid
        assert all(isinstance(v, str) and v for v in facts.values()), hid


# ---------------------------------------------------------------------------------------------------------- gates
PKG = Path(HN.__file__).parent
CREDENTIAL_NAMES = ("auth.json", ".credentials", "oauth_creds")
FILE_OR_PROCESS = ("open(", "read_text", "read_bytes", "write_text", "sqlite3", "subprocess", "os.system")


def gate_hits(root: Path) -> list:
    """What the B0/B1 source gate refuses in a harness package: a credential file's name anywhere; a file read or write or a process
    anywhere but Lampway's own switch module (adapters describe; the host writes the pane's files and the launcher runs)."""
    hits = []
    for f in sorted(root.rglob("*.py")):
        text = f.read_text()
        hits += [(f.name, n) for n in CREDENTIAL_NAMES if n in text]
        if f.name != "switch.py":
            hits += [(f.name, n) for n in FILE_OR_PROCESS if n in text]
    return hits


def test_no_harness_module_names_a_credential_file_reads_a_file_or_starts_a_process():
    assert gate_hits(PKG) == []


def test_the_source_gate_sees_a_planted_credential_read_and_a_planted_process(tmp_path):
    (tmp_path / "bad.py").write_text('TOKEN = open("~/.codex/auth.json").read()\n')
    (tmp_path / "worse.py").write_text("import subprocess\n")
    assert set(gate_hits(tmp_path)) == {("bad.py", "auth.json"), ("bad.py", "open("), ("worse.py", "subprocess")}


# ---------------------------------------------------------------------------------------------------------- the pane switch moved
def test_the_pane_switch_lives_with_the_adapters_and_the_old_module_is_gone(tmp_path, monkeypatch):
    assert importlib.util.find_spec("lampway_server.agent.cli_adapters") is None
    monkeypatch.delenv("LAMPWAY_LOCAL_CLI", raising=False)
    assert HN.enabled(tmp_path) is False
    with pytest.raises(ValueError, match="your own agents in Lampway's panes are off"):
        HN.require_enabled(tmp_path)
    (tmp_path / "local_cli.json").write_text('{"enabled": true}')
    assert HN.enabled(tmp_path) is True


# ---------------------------------------------------------------------------------------------------------- the host goes through them
@pytest.fixture
def herdr(monkeypatch):
    fake = FakeHerdr()
    monkeypatch.setattr(L, "run", fake)
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    return fake


@pytest.mark.parametrize("hid", IDS)
def test_the_cockpit_offers_every_adapter_and_herdr_starts_each_by_its_own_kind(hid, herdr, tmp_path):
    """herdr 0.9.3 knows every starting harness's kind (its CLI reference; src/detect/mod.rs), so none is typed into a shell."""
    assert set(IDS) <= set(H.AGENTS) and {"shell", "command"} <= set(H.AGENTS)
    assert HN.get(hid).herdr_kind == HERDR_KINDS[hid]
    c = H.Cockpit(tmp_path / "herdr")
    rec = c.create_session(hid, "Chest fit audit", str(tmp_path), by="user")
    start = next(x["args"] for x in herdr.calls if x["args"][:2] == ["agent", "start"])
    assert start[:7] == ["agent", "start", f"lw-{rec['id']}", "--kind", HERDR_KINDS[hid], "--pane", "p1"], start
    assert rec["match"] == [BINARIES[hid]] and rec["agent"] == hid
    assert not [x for x in herdr.calls if x["args"][:2] == ["pane", "run"]]


def test_an_adapter_herdr_has_no_kind_for_is_typed_into_its_pane_as_one_quoted_command(herdr, tmp_path, monkeypatch):
    """The path a kind-less adapter takes (Lampway's own Hermes pane is one): one shell-quoted string for ``pane run``."""
    class Bare(HN.Adapter):
        id, label, binary = "bare", "Bare", "bare-agent"
    monkeypatch.setitem(HN.ADAPTERS, "bare", Bare())
    monkeypatch.setattr(H, "AGENTS", (*H.AGENTS, "bare"))
    c = H.Cockpit(tmp_path / "herdr")
    rec = c.create_session("bare", "Chest fit audit", str(tmp_path), by="user", resume_id="r 1")
    run = next(x["args"] for x in herdr.calls if x["args"][:2] == ["pane", "run"])
    assert run == ["pane", "run", "p1", "bare-agent --resume 'r 1'"] and rec["match"] == ["bare-agent"]
    assert not [x for x in herdr.calls if x["args"][:2] == ["agent", "start"]]


def test_every_harness_start_is_gated_by_its_own_route(herdr, tmp_path, strict):
    strict.set_route("byoa:grok", True)
    c = H.Cockpit(tmp_path / "herdr")
    with pytest.raises(EG.EgressRefused, match="byoa:hermes is off"):
        c.create_session("hermes", "Chest fit audit", str(tmp_path), by="user")
    c.create_session("grok", "Chest fit audit", str(tmp_path), by="user")
    assert [r["route"] for r in strict.log() if r.get("event") == "send"] == ["byoa:grok"]


def test_the_create_route_checks_the_switch_for_every_harness(settings, provider, tmp_path, monkeypatch):
    from starlette.testclient import TestClient
    from lampway_server.app import create_app
    monkeypatch.delenv("LAMPWAY_LOCAL_CLI", raising=False)
    app = create_app(settings, provider=provider, cockpit=H.Cockpit(tmp_path / "herdr", project_root=str(tmp_path)))
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        from .fake_client import FakeMixarClient
        client = FakeMixarClient(http, password=settings.user_password)
        client.login()
        for hid in ("hermes", "pi", "grok", "cursor"):
            r = http.post("/app/workbench/sessions", headers=client.rest_headers(), json={"agent": hid, "name": "Chest fit audit", "cwd": str(tmp_path)})
            assert r.status_code == 403 and "local CLI" in r.json()["detail"], hid
