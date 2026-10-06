"""The facelift lane's Connections and Choices windows were built against the contracts while lp/connections was not yet
integrated (fake clients). Now the hub is here: its real answers go through the windows' own words (connections_face,
choices_face, loaded by file: they import nothing of Blender) and every state, glyph and row must be one the faces know."""
import importlib.util
from pathlib import Path

import httpx
import pytest

from lampway_server.app import create_app

ROOT = Path(__file__).resolve().parents[2]


def _face(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"src/scripts/mixar/modules/lampway_tools/{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def app(settings, provider):
    return create_app(settings, provider=provider, connections_transport=httpx.MockTransport(lambda r: httpx.Response(401, json={})))


def test_the_connections_window_reads_the_real_hub(http, fake):
    C = _face("connections_face")
    fake.login()
    h = fake.rest_headers()
    listing = http.get("/app/connections", headers=h).json()
    views = listing["connections"]
    assert views, listing
    for v in views:
        cue = C.cue(v)
        assert not cue["word"].startswith("unknown state"), v["state"]
        assert C.detail(v)["action"]["op"].startswith("lampway.connections_")
    groups = [g for g, _rows in C.groups(views)]
    assert [g for g in C.GROUP_ORDER if g in groups] == [g for g in groups if g in C.GROUP_ORDER]
    one = http.get("/app/connections/openrouter", headers=h).json()
    assert C.detail(one)["name"] == one["label"]


def test_the_choices_window_reads_the_real_choices(http, fake):
    F = _face("choices_face")
    fake.login()
    h = fake.rest_headers()
    listing = http.get("/app/choices", headers=h).json()
    purposes = [p for g in listing["groups"] for p in g["purposes"]]
    assert purposes
    for p in purposes:
        assert not F.cue(p, set())["word"].startswith("unknown state"), p.get("cue")
    view = http.get(f"/app/choices/{purposes[0]['id']}", headers=h).json()
    for o in view["chain"] + view["other_options"]:
        row = F.option_row(o)
        assert row["name"] and row["retention"], o
    assert "proposals" in http.get("/app/choices/proposals?state=open", headers=h).json()


def test_a_real_proposal_reads_in_the_window(http, fake):
    F = _face("choices_face")
    from lampway_server import choices as CH
    fake.login()
    h = fake.rest_headers()
    pid = http.get("/app/choices", headers=h).json()["groups"][0]["purposes"][0]["id"]
    view = http.get(f"/app/choices/{pid}", headers=h).json()
    option = (view["chain"] + view["other_options"])[0]["id"]
    CH.active_store().propose("agent", pid, {"preferred": option}, "it measured better", [])
    rows = http.get("/app/choices/proposals?state=open", headers=h).json()["proposals"]
    assert F.proposal_line(rows[0]) == f"The agent proposes {option}: it measured better"
