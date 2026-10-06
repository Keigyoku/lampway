"""Facelift contract 16: the Lampway terminal, an optional WezTerm add-on. The download goes only through the github route,
SHA-256 pinned in source and cross-checked against the published .sha256; the launch is Lampway's own (its config file,
a new process, its own class and socket) and never reads or writes the user's WezTerm config; cockpit actions refuse any
pane Lampway did not create; Remove signals only the process Lampway started; reconcile re-adopts without spawning."""
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

import httpx
import pytest

from lampway_server import egress as E
from lampway_server.addons import wezterm as W

PAYLOAD = b"\x7fELF fake wezterm appimage " * 64
PIN = {"version": "20240203-110809-5046fc22", "asset": "WezTerm-test.AppImage", "bytes": len(PAYLOAD),
       "sha256": hashlib.sha256(PAYLOAD).hexdigest(), "url": "https://github.com/wezterm/wezterm/releases/download/v/WezTerm-test.AppImage",
       "kind": "appimage", "license_url": "https://github.com/wezterm/wezterm/raw/v/LICENSE.md"}
LICENSE = b"MIT License\n\nCopyright (c) 2018-Present Wez Furlong\n"


class Fake:
    def __init__(self, payload=PAYLOAD, published=None):
        self.requests = []
        self.payload, self.published = payload, published if published is not None else hashlib.sha256(payload).hexdigest()

    def handle(self, request):
        self.requests.append(str(request.url))
        path = request.url.path
        if path.endswith(".sha256"):
            return httpx.Response(200, content=f"{self.published}  WezTerm-test.AppImage\n".encode())
        if path.endswith("LICENSE.md"):
            return httpx.Response(200, content=LICENSE)
        return httpx.Response(200, content=self.payload)


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "lampway_home"
    h.mkdir()
    monkeypatch.setenv("LAMPWAY_HOME", str(h))
    return h


@pytest.fixture
def egress(tmp_path):
    m = E.Egress(tmp_path / "state")
    E.set_active(m)
    E.install()
    yield m
    E.set_active(None)


def test_unopted_download_refuses(home, egress):
    fake = Fake()
    with pytest.raises(W.TerminalRefused, match="github.com is off: open it in Privacy to download the Lampway terminal"):
        W.get(home, PIN, transport=httpx.MockTransport(fake.handle))
    assert fake.requests == [] and not (home / "addons").exists()


def test_checksum_mismatch_refuses(home, egress):
    egress.set_route("github", True)
    fake = Fake(payload=PAYLOAD + b"tampered", published=hashlib.sha256(PAYLOAD + b"tampered").hexdigest())
    with pytest.raises(W.TerminalRefused, match="does not match the pinned value: it was deleted; nothing was installed"):
        W.get(home, PIN, transport=httpx.MockTransport(fake.handle))
    root = home / "addons" / "wezterm"
    assert not list(root.rglob("*.part")) and not (root / PIN["version"]).exists()


def test_published_sha256_must_agree(home, egress):
    egress.set_route("github", True)
    fake = Fake(published="0" * 64)
    with pytest.raises(W.TerminalRefused, match="published SHA-256"):
        W.get(home, PIN, transport=httpx.MockTransport(fake.handle))
    assert not (home / "addons" / "wezterm" / PIN["version"]).exists()


def test_a_good_download_installs_with_its_licence_and_provenance(home, egress):
    egress.set_route("github", True)
    fake = Fake()
    out = W.get(home, PIN, transport=httpx.MockTransport(fake.handle))
    vdir = home / "addons" / "wezterm" / PIN["version"]
    binary = Path(out["binary"])
    assert binary.read_bytes() == PAYLOAD and binary.stat().st_mode & stat.S_IXUSR
    assert (vdir / "LICENSE.md").read_bytes() == LICENSE
    prov = json.loads((vdir / "PROVENANCE.json").read_text())
    assert prov["sha256"] == PIN["sha256"] and prov["verified"] is True and prov["bytes"] == len(PAYLOAD)
    assert (home / "wezterm" / "lampway.wezterm.lua").exists(), "the generated config is copied at install"
    rows = [r for r in egress.log() if r.get("route") == "github"]
    assert rows and all(r["event"] == "send" for r in rows)


def test_the_pins_are_in_source_and_complete():
    pins = W.load_pins()
    linux = pins["linux-x86_64"]
    assert linux["version"] == "20240203-110809-5046fc22" and linux["bytes"] == 49505472
    assert linux["sha256"] == "34010a07076d2272c4d4f94b5e0dae608a679599e8d729446323f88f956c60f0"
    assert linux["url"].startswith("https://github.com/wezterm/wezterm/releases/download/20240203-110809-5046fc22/")
    with pytest.raises(W.TerminalRefused, match="no pinned WezTerm build for linux-arm64: use the browser cockpit"):
        W.pin_for("linux-arm64", pins)


FAKE_WEZTERM = """#!/usr/bin/env python3
import json, os, sys
log = os.environ["FAKE_WEZTERM_LOG"]
with open(log, "a") as fh:
    fh.write(json.dumps({"argv": sys.argv[1:], "socket": os.environ.get("WEZTERM_UNIX_SOCKET"),
                         "dirs": {k: os.environ.get(k) for k in ("HOME", "XDG_RUNTIME_DIR", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME")},
                         "herdr": {k: v for k, v in os.environ.items() if k.startswith("HERDR_")}}) + "\\n")
if "cli" in sys.argv and "list" in sys.argv:
    print(json.dumps([{"pane_id": 3}, {"pane_id": 12}]))
"""


@pytest.fixture
def fake_wezterm(tmp_path, monkeypatch):
    exe = tmp_path / "wezterm"
    exe.write_text(FAKE_WEZTERM.replace("/usr/bin/env python3", sys.executable))
    exe.chmod(0o755)
    log = tmp_path / "wezterm.log"
    monkeypatch.setenv("FAKE_WEZTERM_LOG", str(log))
    return exe, log


def test_user_config_untouched(home, tmp_path, fake_wezterm, monkeypatch):
    user = tmp_path / "user_home"
    (user / ".config" / "wezterm").mkdir(parents=True)
    (user / ".wezterm.lua").write_text("return {font_size = 99}\n")
    (user / ".config" / "wezterm" / "wezterm.lua").write_text("return {}\n")
    monkeypatch.setenv("HOME", str(user))
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in user.rglob("*") if p.is_file()}
    exe, log = fake_wezterm
    W.write_config(home)
    W.launch(home, str(exe), herdr_root=home / "herdr", detached=False)
    after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in user.rglob("*") if p.is_file()}
    assert before == after
    call = json.loads(log.read_text().splitlines()[0])
    argv = call["argv"]
    assert argv[:2] == ["--config-file", str(home / "wezterm" / "lampway.wezterm.lua")]
    assert "--always-new-process" in argv and "--class" in argv and argv[argv.index("--class") + 1] == "dev.lampway.terminal"
    assert call["socket"] == str(W.socket_path(home)), "Lampway's own WEZTERM_UNIX_SOCKET, never the user's"
    assert call["herdr"]["HERDR_SOCKET_PATH"].startswith(str(home / "herdr")) or call["herdr"]["HERDR_SOCKET_PATH"].startswith("/run/user/")
    # Lampway's WezTerm never sees the person's WezTerm state: a CLI call that found no window once auto-started a mux server that
    # took ~/.local/share/wezterm/pid (the lane's live run, 2026-10-06). Every WezTerm process runs on Lampway's own dirs.
    for key, value in call["dirs"].items():
        assert value and value.startswith(str(home)), (key, value)
    W.save_instance(home, {"gui_pid": None, "socket": str(W.socket_path(home)), "panes": {"3": {}}})
    W.send_text(home, str(exe), 3, "x")
    cli_call = json.loads(log.read_text().splitlines()[-1])
    assert "--no-auto-start" in cli_call["argv"], "a CLI call never starts a mux server"
    assert all(v.startswith(str(home)) for v in cli_call["dirs"].values())


def test_send_text_refuses_foreign_panes(home, fake_wezterm):
    exe, log = fake_wezterm
    W.save_instance(home, {"gui_pid": None, "socket": str(W.socket_path(home)), "panes": {"3": {"herdr_agent_id": "a1"}}})
    with pytest.raises(W.TerminalRefused, match="pane 12 is not a Lampway pane: nothing was sent"):
        W.send_text(home, str(exe), 12, "hello")
    assert not log.exists() or "send-text" not in log.read_text()
    W.send_text(home, str(exe), 3, "hello")
    assert "send-text" in log.read_text()


def test_reconcile_readopts_and_spawns_nothing(home, fake_wezterm):
    exe, log = fake_wezterm
    W.save_instance(home, {"gui_pid": os.getpid(), "socket": str(W.socket_path(home)), "panes": {"3": {"herdr_agent_id": "a1"}}})
    first = W.reconcile(home, str(exe))
    second = W.reconcile(home, str(exe))
    assert first == second == {"window": "re-adopted", "panes": ["3"], "foreign_panes": ["12"]}
    assert all("spawn" not in json.loads(line)["argv"] for line in log.read_text().splitlines())
    W.save_instance(home, {"gui_pid": 2 ** 22 + 7, "socket": str(W.socket_path(home)), "panes": {}})
    assert W.reconcile(home, str(exe))["window"] == "gone"


def test_remove_only_removes_lampway(home, monkeypatch):
    killed = []
    monkeypatch.setattr(W, "_signal", lambda pid: killed.append(pid))
    vdir = home / "addons" / "wezterm" / "v1"
    vdir.mkdir(parents=True)
    W.save_instance(home, {"gui_pid": 4242, "socket": str(W.socket_path(home)), "panes": {}})
    W.remove(home, alive=lambda pid: pid in (4242, 999))
    assert killed == [4242], "only the window Lampway started; a WezTerm of another class (pid 999) is never signalled"
    assert not (home / "addons" / "wezterm").exists()


def test_the_routes_need_the_user(settings, provider, tmp_path, monkeypatch):
    """The routes are the Blender panel's: behind the bearer, an agent's declared origin refused, Get refused with the route off."""
    from starlette.testclient import TestClient

    from lampway_server.app import create_app

    from .fake_client import FakeMixarClient
    monkeypatch.setenv("LAMPWAY_HOME", str(tmp_path / "home"))
    eg = E.Egress(tmp_path / "eg")
    app = create_app(settings, provider=provider, egress=eg)
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        h = fake.rest_headers()
        assert http.get("/app/terminal").status_code == 401
        st = http.get("/app/terminal", headers=h).json()
        assert st["installed"] is False and st["window"] == "gone" and st["pin"]["version"] == "20240203-110809-5046fc22"
        assert http.post("/app/terminal/get", headers={**h, "X-Lampway-Origin": "agent"}).status_code == 403
        r = http.post("/app/terminal/get", headers=h)
        assert r.status_code == 409 and r.json()["detail"].startswith("github.com is off")
        assert http.post("/app/terminal/open", headers=h).json()["detail"].startswith("the Lampway terminal is not installed")
    E.set_active(None)


def test_every_redirect_hop_is_logged_under_its_own_host(home, egress):
    """GitHub answers a release download with a redirect to its asset host: each hop goes through the gate and the log names it."""
    egress.set_route("github", True)
    fake = Fake()

    def handle(request):
        if request.url.host == "github.com" and not request.url.path.endswith("LICENSE.md"):
            fake.requests.append(str(request.url))
            return httpx.Response(302, headers={"location": "https://release-assets.githubusercontent.com/x" + request.url.path})
        return fake.handle(request)
    W.get(home, PIN, transport=httpx.MockTransport(handle))
    hosts = {r["provider"] for r in egress.log() if r.get("route") == "github"}
    assert {"github.com", "release-assets.githubusercontent.com"} <= hosts, hosts


def test_the_terminal_gets_plex_mono_as_truetype(home):
    """WezTerm 20240203 cannot read woff2 (measured live 2026-10-06: a Configuration Error pane): the add-on installs TTF."""
    W.write_config(home)
    fonts = home / "addons" / "wezterm" / "fonts"
    ttfs = sorted(fonts.glob("*.ttf"))
    assert ttfs and not list(fonts.glob("*.woff2")), sorted(p.name for p in fonts.iterdir())
    for f in ttfs:
        assert f.read_bytes()[:4] == b"\x00\x01\x00\x00", f.name     # an sfnt with TrueType outlines
    assert (fonts / "OFL-IBM-Plex-Mono.txt").exists()
