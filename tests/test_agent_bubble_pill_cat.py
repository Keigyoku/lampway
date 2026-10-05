# SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Mixie the cat on the minimised Agent pill.

Pose is the shipped `mixie_cat_eval_pose` (header-only, compiled into a
tiny harness — not reimplemented here). Idle is a close–hold–open blink
and a gaze that leaves centre then returns; working keeps the eyes open
and rolls the pupils in a paused circle, not a squint or bounce clip.
The Mixar mark is gone from the elongated pill; the compact pill clears
the cat QA target.
"""

from __future__ import annotations

import functools
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/source/blender/editors/space_agent_bubble"
HARNESS_SRC = ROOT / "tests/pill_cat_pose_harness.cc"

DRAW_CC = (CPP / "agent_ui_draw.cc").read_text(encoding="utf-8")
CAT_CC = (CPP / "agent_ui_pill_cat.cc").read_text(encoding="utf-8")
CAT_HH = (CPP / "agent_ui_pill_cat.hh").read_text(encoding="utf-8")
POSE_HH = (CPP / "agent_ui_pill_cat_pose.hh").read_text(encoding="utf-8")
BUBBLE_CC = (CPP / "space_agent_bubble.cc").read_text(encoding="utf-8")
CMAKE = (CPP / "CMakeLists.txt").read_text(encoding="utf-8")


def _pill_draw() -> str:
    start = DRAW_CC.index("void agent_ui_draw_status_pill")
    end = DRAW_CC.index("void agent_ui_draw_island", start)
    return DRAW_CC[start:end]


def _elongated() -> str:
    body = _pill_draw()
    return body[body.index("if (w > h * 4.0f)") :]


def _parse_pose_line(line: str) -> dict[str, float]:
    out: dict[str, float] = {}
    parts = line.split()
    out["label"] = parts[0]
    for token in parts[1:]:
        key, _, val = token.partition("=")
        out[key] = float(val)
    return out


@functools.lru_cache(maxsize=1)
def pose_harness_output() -> str:
    """Compile and run the shipped pose header. Same function the painter calls."""
    cxx = shutil.which("c++") or shutil.which("clang++")
    assert cxx, "need c++ or clang++ to sample mixie_cat_eval_pose"
    with tempfile.TemporaryDirectory(prefix="mixie-pose-") as td:
        binary = Path(td) / "pose_harness"
        subprocess.check_call(
            [
                cxx,
                "-std=c++17",
                "-O0",
                f"-I{CPP}",
                str(HARNESS_SRC),
                "-o",
                str(binary),
            ],
            cwd=str(ROOT),
        )
        return subprocess.check_output([str(binary)], text=True)


def pose_samples() -> dict[str, dict[str, float]]:
    rows = {}
    for line in pose_harness_output().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parsed = _parse_pose_line(line)
        rows[parsed["label"]] = parsed
    return rows


def test_painter_draws_the_lampway_spark_not_the_upstream_mascot():
    """The pill and the Parallel Agents cards draw a flame in a ring (docs/brand/logo_agent_spark.svg); the upstream black cat is gone from the painter."""
    assert "static void draw_spark(" in CAT_CC and "flame(" in CAT_CC and "ring(" in CAT_CC
    assert "0.929f, 0.725f, 0.267f" in CAT_CC          # Flame #EDB944
    for cat_part in ("draw_eyes", "void ear(", "catchlight", "pose.look_x", "mixie_cat_eval_pose"):
        assert cat_part not in CAT_CC, cat_part


def test_the_working_state_alternates_two_flame_frames_and_offline_shows_the_flame_out():
    body = CAT_CC[CAT_CC.index("static void draw_spark("):]
    assert "BLI_time_now_seconds() / 0.8" in body          # 1.6 s per full cycle
    assert "second_frame" in body and "wisp(" in body and "offline" in body


def test_worker_colours_are_the_brand_pack_in_order():
    style = (ROOT / "src/source/blender/editors/space_agent_bubble/agent_ui_cat_style.hh").read_text()
    for name in ("Flame", "Dusk", "Mint", "Coral", "Sky", "Orchid"):
        assert f'"{name}"' in style
    for old in ("Emerald", "Amber", "Lagoon", "Lilac", "Lime"):
        assert old not in style
    for hexcode in ("#EDB944", "#9EA0F7", "#5BC48F", "#F0766B", "#6FC3E8", "#D58FE0"):
        assert hexcode in style

def test_qa_target_reads_the_painted_chip():
    assert 't.surface = "pill_cat"' in CAT_CC
    assert "agent_ui_pill_cat_last_rect" in CAT_CC
    assert "agent_ui_pill_cat_qa_register();" in BUBBLE_CC
    assert "Mixar_qa_register_target_provider(SPACE_AGENT_BUBBLE, pill_cat_qa_targets)" in CAT_CC


def test_cmake_compiles_the_cat():
    assert "agent_ui_pill_cat.cc" in CMAKE
    assert "agent_ui_pill_cat.hh" in CMAKE
    assert "agent_ui_pill_cat_pose.hh" in CMAKE
    assert "agent_ui_cat_catch.hh" in CMAKE
    catch_hh = (CPP / "agent_ui_cat_catch.hh").read_text(encoding="utf-8")
    assert "ATTACHMENT_FLIGHT_SECONDS" in catch_hh
    assert "mixie_cat_catch_pose" in catch_hh
    assert "mixie_cat_catch_pick" in catch_hh


def test_header_documents_the_clip_contract():
    assert "Every vertex stays inside that rect" in CAT_HH
    assert "test_agent_bubble_pill_paint.py" in CAT_HH
    assert "mixie_cat_eval_pose" in POSE_HH
