"""Facelift contract 02, test 4: a first run on a fresh state dir starts with every outbound route off, and after a walk with the defaults the only
route on is the one the user switched on by a recorded click. The walk is the Client's own (``lampway_tools/onboarding.py``, no bpy), talking to
this server over its two doors: ``POST /app/egress/route`` and ``PUT /app/provider-settings``."""

import importlib.util
import json
from pathlib import Path

from starlette.testclient import TestClient

from lampway_server import egress as E
from lampway_server.app import create_app

from .fake_client import FakeMixarClient

ONBOARDING = Path(__file__).resolve().parents[2] / "src/scripts/mixar/modules/lampway_tools/onboarding.py"


def onboarding():
    spec = importlib.util.spec_from_file_location("lampway_onboarding", ONBOARDING)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Door:
    """The Client's server door, over the test server."""

    def __init__(self, http, headers):
        self.http, self.h = http, headers

    def egress(self):
        return self.http.get("/app/egress", headers=self.h).json()

    def provider_settings(self):
        return self.http.get("/app/provider-settings", headers=self.h).json()

    def set_route(self, route, enabled):
        r = self.http.post("/app/egress/route", headers=self.h, json={"route": route, "enabled": bool(enabled)})
        assert r.status_code == 200, r.text
        return r.json()

    def save_provider_settings(self, values):
        r = self.http.put("/app/provider-settings", headers=self.h, json={"values": values})
        assert r.status_code == 200, r.text
        return r.json()


def test_onboarding_starts_with_every_route_off(settings, provider, tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path))
    m = E.Egress(tmp_path / "egstate")
    app = create_app(settings, provider=provider, egress=m)
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        door = Door(http, fake.rest_headers())
        ob = onboarding()
        walk = ob.Walk.read(door)
        assert walk.online and walk.routes_on() == [], "a fresh install starts with every route off"
        assert walk.next() is None and walk.step == 2      # language and keys
        assert walk.next() is None and walk.step == 3      # the provider as it is (a local one)
        walk.click_route("openrouter", True)               # the one recorded click
        assert walk.next() is None and walk.step == 4
        assert walk.continue_label() == "Continue with 1 route on"
        saved = walk.finish(door)
        assert saved == ["preferences", "routes", "caps"]
    on = {r for r, v in json.loads((m.state_dir / "egress.json").read_text())["routes"].items() if v.get("enabled")}
    assert on == {"openrouter"}
    assert walk.clicks == [("openrouter", True)]
    policy = settings.spend_policy["openrouter"]
    assert (policy["job_cap"], policy["session_cap"], policy["click"], policy["above"]) == (1.0, 5.0, "above", 0.25)
