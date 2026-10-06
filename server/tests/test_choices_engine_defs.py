# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""choices_migration.md 5.8 and test 9 (HC14): each Blender-side Def with an `engine` takes every option of its purpose; with none named the
purpose's choice decides; a local option becomes the Def's own method; an agent's Studio option is a job override under the purpose's
policy (any_local: local always, a Studio option only from the user's chain)."""

import json

import pytest

from lampway_server import choices as CH
from lampway_server import egress as E
from lampway_server.agent import lampway_tools as LT
from lampway_server.choices import registry as REG
from lampway_server.choices import store as CS
from lampway_server.choices.snapshot import World
from lampway_server.connections import registry as CREG


@pytest.fixture
def live(tmp_path, monkeypatch):
    CH.set_active(CS.FileStore(tmp_path / "state"), tmp_path / "state")
    monkeypatch.setattr(CH, "WORLD_FACTORY", lambda: World(connections={c: "connected" for c in CREG.SPECS}, routes={r: True for r in E.ROUTES}))
    yield
    CH.set_active(None, None)


def payload(script: str) -> dict:
    raw = script.split("api.call(", 1)[1].split(", ", 1)[1].rsplit(")", 1)[0]
    return json.loads(json.loads(raw))


def test_engine_defs_accept_every_option(live):
    for name, pid in LT.ENGINE_PURPOSES.items():
        desc = next(p.desc for p in LT.BY_NAME[name].params if p.name == "engine")
        for oid in REG.listed(REG.get(pid)):
            assert oid in desc, (name, oid)


def test_no_engine_means_the_purposes_choice(live):
    args = payload(LT.build_script(LT.BY_NAME["lampway_retopo"], {"object": "dense"}))
    assert args["engine"] == "algorithmic" and args["method"] == "quadriflow"
    CH.active_store().set("3d.retopo", "global", None, {"preferred": "local:voxel"}, by="user")
    args = payload(LT.build_script(LT.BY_NAME["lampway_retopo"], {"object": "dense"}))
    assert args["engine"] == "algorithmic" and args["method"] == "voxel"


def test_a_local_option_is_always_allowed_and_a_studio_one_only_from_the_chain(live):
    args = payload(LT.build_script(LT.BY_NAME["lampway_retopo"], {"object": "dense", "engine": "local:autoremesher"}))
    assert args["method"] == "autoremesher"
    with pytest.raises(LT.BadArguments, match="propose it with lampway_choices"):
        LT.build_script(LT.BY_NAME["lampway_retopo"], {"object": "dense", "engine": "studio:meshy.remesh"})
    CH.active_store().set("3d.retopo", "global", None, {"preferred": "local:quadriflow", "fallbacks": ["studio:meshy.remesh"]}, by="user")
    args = payload(LT.build_script(LT.BY_NAME["lampway_retopo"], {"object": "dense", "engine": "studio:meshy.remesh"}))
    assert args["engine"] == "studio:meshy.remesh"


def test_the_legacy_engine_values_still_work(live):
    assert payload(LT.build_script(LT.BY_NAME["lampway_uv_unwrap"], {"object": "o", "engine": "algorithmic"}))["engine"] == "algorithmic"
    assert payload(LT.build_script(LT.BY_NAME["lampway_uv_unwrap"], {"object": "o", "engine": "studio:tripo"}))["engine"] == "studio:tripo"
