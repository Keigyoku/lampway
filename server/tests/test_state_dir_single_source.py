"""ONE state directory for every Lampway process: a route switched on through the server is the route the compute CLI reads (and the other way round).
The site truth-check found compute/cli.py defaulting to <XDG_STATE_HOME>/lampway while the server used <XDG_STATE_HOME>/lampway-server."""
from starlette.testclient import TestClient

from lampway_server import config as C
from lampway_server import egress as E
from lampway_server.app import create_app
from lampway_server.compute import cli as CLI

from .fake_client import FakeMixarClient


def test_every_module_reads_the_state_directory_from_one_function(monkeypatch, tmp_path):
    monkeypatch.delenv("LAMPWAY_STATE_DIR", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
    want = C.state_dir()
    assert want == tmp_path / "xdg" / "lampway-server"
    assert C.Settings.from_env().state_dir == want
    assert CLI.default_context().state == want
    from lampway_server import imagegen
    from lampway_server.agent import files_tools
    assert imagegen._state_dir() == want and files_tools._state_dir() == want
    monkeypatch.setenv("LAMPWAY_STATE_DIR", str(tmp_path / "explicit"))
    assert C.state_dir() == CLI.default_context().state == C.Settings.from_env().state_dir == tmp_path / "explicit"


def test_a_route_switched_on_through_the_server_is_on_for_the_compute_cli(monkeypatch, tmp_path, settings, provider):
    """No explicit state dir anywhere: the server's default and the CLI's default must be the same directory."""
    monkeypatch.delenv("LAMPWAY_STATE_DIR", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path / "proj"))
    server_settings = C.Settings.from_env()
    server_settings.user_password, server_settings.jwt_secret = settings.user_password, settings.jwt_secret
    prev = E.ACTIVE
    E.set_active(None)                                                       # production path: create_app opens the manager on its own state directory
    try:
        app = create_app(server_settings, provider=provider)
        with TestClient(app, base_url="http://127.0.0.1:8787") as http:
            fake = FakeMixarClient(http, password=server_settings.user_password)
            fake.login()
            r = http.post("/app/egress/route", headers=fake.rest_headers(), json={"route": "compute:boat", "enabled": True})
            assert r.status_code == 200 and r.json()["enabled"] is True
        CLI.build(CLI.default_context())                                     # the CLI opens its own manager, exactly as `compute` does
        assert E.ACTIVE.enabled("compute:boat") is True
    finally:
        E.set_active(prev)
