# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""CHOICES.md 8.4 and choices_store.md 4.1: quality records - append-only, imported from the 2026-10-05 bake-off (cost and seconds per
model), shown on each option, never used to reorder a chain (CH7: a measured winner is a proposal card only). Only the user imports."""

import json
import os

import pytest

from lampway_server import choices as CH
from lampway_server import egress as E
from lampway_server.choices import store as CS
from lampway_server.choices.snapshot import World
from lampway_server.connections import registry as CREG

BAKEOFF = {"openai/gpt-image-2.5-flare": {"model": "openai/gpt-image-2.5-flare", "status": 200, "file": "x.png", "size": [2048, 2048], "cost": 0.139, "s": 30},
           "sourceful/riverflow-v2.5-pro": {"model": "sourceful/riverflow-v2.5-pro", "status": 200, "file": "y.png", "size": [2048, 2048], "cost": 0.56, "s": 143},
           "broken/model": {"model": "broken/model", "status": 500}}


@pytest.fixture
def live(tmp_path, monkeypatch):
    CH.set_active(CS.FileStore(tmp_path / "state"), tmp_path / "state")
    monkeypatch.setattr(CH, "WORLD_FACTORY", lambda: World(connections={c: "connected" for c in CREG.SPECS}, routes={r: True for r in E.ROUTES}))
    root = __import__("pathlib").Path(os.environ["LAMPWAY_PROJECT_ROOT"])
    root.mkdir(parents=True, exist_ok=True)
    (root / "bakeoff.json").write_text(json.dumps(BAKEOFF))
    yield root
    CH.set_active(None, None)


def test_import_the_bakeoff_and_show_it_on_the_option_without_reordering(live):
    n = CH.import_quality("bakeoff", str(live / "bakeoff.json"), by="user")
    assert n == 4                                                          # cost and seconds for the two that answered 200
    recs = CH.active_store().quality(purpose="image.plates")
    assert {(r["option"], r["metric"]) for r in recs} == {("openrouter:openai/gpt-image-2.5-flare", "cost_usd"), ("openrouter:openai/gpt-image-2.5-flare", "seconds"),
                                                          ("openrouter:sourceful/riverflow-v2.5-pro", "cost_usd"), ("openrouter:sourceful/riverflow-v2.5-pro", "seconds")}
    CH.active_store().set("image.plates", "global", None, {"preferred": "openrouter:sourceful/riverflow-v2.5-pro", "fallbacks": ["openrouter:openai/gpt-image-2.5-flare"]},
                          by="user")
    v = CH.purpose_view("image.plates", CH.Job(content_class="public"))
    river = v["chain"][0]
    assert river["id"] == "openrouter:sourceful/riverflow-v2.5-pro" and {q["metric"] for q in river["quality"]} == {"cost_usd", "seconds"}
    assert [o["id"] for o in v["chain"]][0] == "openrouter:sourceful/riverflow-v2.5-pro", "quality never reorders the user's chain"


def test_only_the_user_imports_and_only_from_the_project_root(live, tmp_path):
    with pytest.raises(CS.Refused):
        CH.import_quality("bakeoff", str(live / "bakeoff.json"), by="agent")
    outside = tmp_path / "elsewhere.json"
    outside.write_text(json.dumps(BAKEOFF))
    with pytest.raises(CS.Refused, match="inside the project root"):
        CH.import_quality("bakeoff", str(outside), by="user")


def test_the_routes(http, fake, live):
    fake.login()
    h = fake.rest_headers()
    r = http.post("/app/choices/quality/import", json={"source": "bakeoff", "path": str(live / "bakeoff.json")}, headers=h)
    assert r.status_code == 200 and r.json()["imported"] == 4
    assert http.post("/app/choices/quality/import", json={"source": "bakeoff", "path": "bakeoff.json"}, headers={**h, "x-lampway-origin": "agent"}).status_code == 403
    recs = http.get("/app/choices/quality", params={"option": "openrouter:openai/gpt-image-2.5-flare"}, headers=h).json()["records"]
    assert {r["metric"] for r in recs} == {"cost_usd", "seconds"}
