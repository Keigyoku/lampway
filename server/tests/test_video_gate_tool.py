"""lampway_video_gate: the deterministic gates behind the video presets, through the agent tool, on real ffmpeg clips inside the project jail."""
import asyncio
import json
import shutil
import subprocess

import numpy as np
import pytest
from PIL import Image

from lampway_server.agent import video_tools as VT

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")


class System:
    def __init__(self, root):
        self.root = root
        self.settings = type("S", (), {"video_purposes": {}, "video_max_job_usd": 2.0})()


def _mp4(path, frames, fps=24):
    d = path.parent / (path.stem + "_png")
    d.mkdir()
    for i, f in enumerate(frames):
        Image.fromarray(f).save(d / f"{i:03d}.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(fps), "-i", str(d / "%03d.png"), "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def _square(n=24, w=64, h=48, speed=1.5):
    out = []
    for t in range(n):
        f = np.full((h, w, 3), 30, np.uint8)
        x = int(2 + speed * t)
        f[16:32, x:x + 12] = 220
        out.append(f)
    return out


def call(tmp_path, **args):
    out, err = asyncio.run(VT.call(System(tmp_path), "lampway_video_gate", args))
    return json.loads(out) if not err else out, err


def test_the_tool_is_listed_and_dispatched_by_name():
    assert "lampway_video_gate" in VT.NAMES and "lampway_video_gate" in {s.name for s in VT.specs()}


def test_a_straight_clip_fails_the_loop_gate_and_the_ping_pong_file_it_writes_passes_without_touching_the_source(tmp_path):
    src = _mp4(tmp_path / "clip.mp4", _square())
    before = src.read_bytes()
    out, err = call(tmp_path, kind="loop", video="clip.mp4")
    assert not err and out["passed"] is False and "wrap jump" in out["message"]
    fixed, err = call(tmp_path, kind="loop", video="clip.mp4", fix="pingpong")
    assert not err and fixed["fixed"]["passed"] is True and fixed["fixed_file"].endswith("clip_loop.mp4") and src.read_bytes() == before


def test_duplicate_frames_are_counted_from_the_file(tmp_path):
    frames = [f for f in _square(12) for _ in range(2)]
    _mp4(tmp_path / "held.mp4", frames)
    out, err = call(tmp_path, kind="duplicates", video="held.mp4")
    assert not err and out["held"] == 12 and out["true_fps"] == pytest.approx(12.0, abs=0.5)


def test_the_upscale_gate_compares_the_output_with_its_source_file(tmp_path):
    src = _square(12, 64, 48)
    _mp4(tmp_path / "src.mp4", src)
    up = [np.asarray(Image.fromarray(f).resize((128, 96), Image.LANCZOS)) for f in src]
    _mp4(tmp_path / "up.mp4", up)
    out, err = call(tmp_path, kind="upscale", video="up.mp4", source="src.mp4", factor=2.0)
    assert not err and out["passed"] is True and out["ssim"] >= 0.95
    bad, err = call(tmp_path, kind="upscale", video="up.mp4", source="src.mp4", factor=3.0)
    assert bad["passed"] is False


def test_the_edit_gate_needs_a_mask_and_keeps_the_outside_of_it(tmp_path):
    src = _square(12)
    edited = [f.copy() for f in src]
    for f in edited:
        f[16:32, :] = np.where(f[16:32, :] > 100, 90, f[16:32, :])
    _mp4(tmp_path / "src.mp4", src)
    _mp4(tmp_path / "edit.mp4", edited)
    mask = np.zeros((48, 64), np.uint8); mask[16:32, :] = 255
    Image.fromarray(mask).save(tmp_path / "mask.png")
    out, err = call(tmp_path, kind="edit", video="edit.mp4", source="src.mp4", mask="mask.png")
    assert not err and out["outside_mask_psnr"] > 30
    none, err = call(tmp_path, kind="edit", video="edit.mp4", source="src.mp4")
    assert err and "needs the region mask" in none


def test_the_clip_gate_names_each_failing_gate_and_a_path_outside_the_project_is_refused(tmp_path):
    _mp4(tmp_path / "tiny.mp4", _square(24, 64, 48))
    out, err = call(tmp_path, kind="clip", video="tiny.mp4")
    assert not err and out["passed"] is False and out["gates"]["G-CLIP-size"]["passed"] is False and out["unverified"] == ["G-CLIP-strides"]
    bad, err = call(tmp_path, kind="loop", video="/etc/hostname")
    assert err and "outside the project root" in bad
    unknown, err = call(tmp_path, kind="spin", video="tiny.mp4")
    assert err and "kind is" in unknown
