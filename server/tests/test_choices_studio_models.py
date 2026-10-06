# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""choices_migration.md 5.3, 5.9 and 5.13 (HC8, HC13, HC16): the model inside a Studio action, Tripo Studio's image model and plate_pick's
template come from the purpose's params - defaulting to today's values, and an explicit argument still wins."""

import pytest

from lampway_server import choices as CH
from lampway_server.choices import store as CS
from lampway_server.studios.actions import ACTIONS


@pytest.fixture
def live(tmp_path):
    CH.set_active(CS.FileStore(tmp_path / "state"), tmp_path / "state")
    img = tmp_path / "front.png"
    img.write_bytes(b"\x89PNG")
    yield img
    CH.set_active(None, None)


def _v(aid, args):
    return ACTIONS[aid].validate(args, lambda p: str(p))


def test_studio_models_default_to_todays_values(live):
    assert _v("meshy.image_to_3d", {"image": str(live)})["ai_model"] == "meshy-7.1"
    assert _v("tripo.rest.image_to_model", {"image": str(live)})["model_version"] == "v3.1-20260211"


def test_studio_models_come_from_the_purposes_params(live):
    CH.active_store().set("3d.image_to_3d", "global", None, {"preferred": "local:visual_hull",
                                                             "params": {"meshy.ai_model": "meshy-6", "tripo.model_version": "v3.0-20250812"}}, by="user")
    assert _v("meshy.image_to_3d", {"image": str(live)})["ai_model"] == "meshy-6"
    assert _v("tripo.rest.image_to_model", {"image": str(live)})["model_version"] == "v3.0-20250812"
    assert _v("meshy.image_to_3d", {"image": str(live), "ai_model": "meshy-6-lite"})["ai_model"] == "meshy-6-lite", "an explicit argument wins"


def test_tripo_studios_image_model_comes_from_plates(live):
    import os
    pf = __import__("pathlib").Path(os.environ["LAMPWAY_PROJECT_ROOT"]) / "p.txt"
    pf.parent.mkdir(parents=True, exist_ok=True)
    pf.write_text("x")
    assert _v("tripo.image", {"prompt_file": str(pf)})["model"] == "GPT Image 2.5"
    CH.active_store().set("image.plates", "global", None, {"preferred": "studio:tripo.image", "params": {"tripo_model": "GPT Image 2.0"}}, by="user")
    assert _v("tripo.image", {"prompt_file": str(pf)})["model"] == "GPT Image 2.0"
    from lampway_server.agent import server_tools as ST
    cmd = ST.command("studio_tripo_image", {"prompt_file": str(pf), "out_dir": "runs/x"})
    assert cmd[cmd.index("--model") + 1] == "GPT Image 2.0"


def test_plate_pick_uses_the_plates_template(live):
    from lampway_server.agent import lampway_tools as LT
    assert LT.plate_template() == "plate-4k-crisper"
    CH.active_store().set("image.plates", "global", None, {"preferred": "openrouter:openai/gpt-image-2.5-flare", "params": {"template": "texture-plate-delit"}},
                          by="user")
    assert LT.plate_template() == "texture-plate-delit"
    script = LT.build_script(LT.BY_NAME["lampway_plate_pick"], {"stage": "prompt", "piece": "Boots1"})
    assert "texture-plate-delit" in script
    assert "mine" in LT.build_script(LT.BY_NAME["lampway_plate_pick"], {"stage": "prompt", "piece": "Boots1", "template": "mine"})
