# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""choices_migration.md 5.12, client half (HC17, HC18): the retry ladder names the models it would use (the server passes the Choices
resolution as `models`), and the vision-judge refusal points to the agent.vision_judge choice, not a Providers field that does not exist."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))


def test_the_ladder_names_the_resolved_models():
    from mixar.modules.lampway_tools.pipeline import view_verify_io as VVI
    hist = [{"verdict": "hard_fail", "reason": "turned", "model": "x"}, {"verdict": "hard_fail", "reason": "arms", "model": "x"}]
    d = VVI.run("ladder", "/tmp", attempts=hist[:1], original_prompt="p", models={"primary": "openai/gpt-image-2.5-sunburst", "fallback": "sourceful/riverflow-v2.5-pro"})
    assert d["model"] == "openai/gpt-image-2.5-sunburst"
    d = VVI.run("ladder", "/tmp", attempts=hist, original_prompt="p", models={"primary": "openai/gpt-image-2.5-sunburst", "fallback": "sourceful/riverflow-v2.5-pro"})
    assert d["model"] == "sourceful/riverflow-v2.5-pro"
    assert VVI.run("ladder", "/tmp", attempts=hist, original_prompt="p")["model"] == "fallback"


def test_the_judge_refusal_points_to_choices(tmp_path):
    from mixar.modules.lampway_tools.pipeline import view_verify_io as VVI
    import numpy as np
    from PIL import Image
    img = np.zeros((64, 64, 4), np.uint8)
    img[16:48, 24:40] = 255
    Image.fromarray(img).save(tmp_path / "f.png")
    with pytest.raises(VVI.ViewVerifyError) as exc:
        VVI.run("verify", str(tmp_path), image=str(tmp_path / "f.png"), judge="vision")
    assert "agent.vision_judge" in str(exc.value) and "Providers" not in str(exc.value)
