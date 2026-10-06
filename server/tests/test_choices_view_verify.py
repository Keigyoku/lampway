# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""choices_migration.md 5.12, server half (HC17): the view_verify ladder gets its models from Choices - the purpose's resolution, and the
fallback is resolve(..., avoid=[the first model])."""

import json

import pytest

from lampway_server import choices as CH
from lampway_server import egress as E
from lampway_server.agent import lampway_tools as LT
from lampway_server.choices import store as CS
from lampway_server.choices.snapshot import World
from lampway_server.connections import registry as CREG


@pytest.fixture
def live(tmp_path, monkeypatch):
    CH.set_active(CS.FileStore(tmp_path / "state"), tmp_path / "state")
    monkeypatch.setattr(CH, "WORLD_FACTORY", lambda: World(connections={c: "connected" for c in CREG.SPECS}, routes={r: True for r in E.ROUTES}))
    yield
    CH.set_active(None, None)


def test_the_ladder_models_come_from_choices(live):
    CH.active_store().set("image.reference_sheet", "global", None, {"preferred": "openrouter:openai/gpt-image-2.5-sunburst",
                                                                    "fallbacks": ["openrouter:sourceful/riverflow-v2.5-pro"]}, by="user")
    script = LT.build_script(LT.BY_NAME["lampway_view_verify"], {"action": "ladder", "category": "sheet", "attempts": []})
    args = json.loads(json.loads(script.split("api.call(", 1)[1].split(", ", 1)[1].rsplit(")", 1)[0]))
    assert args["models"] == {"primary": "openai/gpt-image-2.5-sunburst", "fallback": "sourceful/riverflow-v2.5-pro"}
