"""videogate: deterministic video measures (video_loop, video_edit, video_upscale, anim_clip specs): closure, ping-pong and crossfade loops,
held frames, the upscale gate, the edit gate. Frames are numpy arrays; ffmpeg is used only to decode, probe and build the loop files."""
import shutil
import subprocess

import numpy as np
import pytest

from lampway_server import videogate as VGT


def _clip(n=48, w=64, h=48, speed=1.0):
    """A bright square moving left to right over a dark static background: a straight, non-looping motion."""
    out = []
    for t in range(n):
        f = np.full((h, w, 3), 30, np.uint8)
        x = int(2 + speed * t)
        f[16:32, x:x + 12] = 220
        out.append(f)
    return out


def test_a_straight_clip_does_not_close_and_its_ping_pong_closes_by_construction():
    clip = _clip()
    straight = VGT.closure(clip)
    assert straight["wrap_jump"] > 5 and straight["closure_diff"] > 6
    loop = VGT.pingpong_frames(clip)
    c = VGT.closure(loop)
    assert c["closure_diff"] == 0 and c["wrap_jump"] <= 1.2, c
    assert len(loop) == 2 * len(clip) - 1 and (loop[len(clip)] == clip[-2]).all()            # the turning frame is not shown twice


def test_a_crossfade_tail_brings_the_last_frame_back_to_the_first_and_never_touches_the_source():
    clip = _clip()
    before = [f.copy() for f in clip]
    loop = VGT.crossfade_frames(clip, fade=8)
    assert VGT.closure(loop)["closure_diff"] < VGT.closure(clip)["closure_diff"] / 3
    assert all((a == b).all() for a, b in zip(clip, before)) and len(loop) == len(clip) - 8


def test_the_loop_gate_reads_the_thresholds_and_names_the_failure():
    ok = VGT.loop_gate({"closure_diff": 3.0, "wrap_jump": 1.2})
    bad = VGT.loop_gate({"closure_diff": 3.0, "wrap_jump": 4.1})
    assert ok["passed"] and not bad["passed"] and "wrap jump 4.1 > 2.0" in bad["message"] and "crossfade" in bad["message"]


def test_held_frames_are_counted_and_the_true_rate_follows():
    base = _clip(12)
    held = [f for f in base for _ in range(2)]
    d = VGT.duplicate_frames(held, fps=24)
    assert d["held"] == 12 and d["unique"] == 12 and d["true_fps"] == pytest.approx(12.0)
    assert VGT.duplicate_frames(base, 24)["held"] == 0


def test_the_clip_gates_pass_a_good_clip_and_each_has_a_failing_fixture():
    def figure_clip(n, w, h, fig_h, margin=40, shift=0, vary=True):
        out = []
        for t in range(n):
            f = np.full((h, w), 128, np.uint8)
            top = h - margin - fig_h
            f[top:top + fig_h, w // 2 - 40 + (t % 7 if vary else 0):w // 2 + 40 + (t % 7 if vary else 0)] = 40 + 15 * (t % 4)
            out.append(f)
        return out
    good = figure_clip(24 * 5, 720, 1280, 1100)
    g = VGT.clip_gates(good, fps=24, duration=5.0, size=(720, 1280))
    assert g["passed"], g
    assert g["unverified"] == ["G-CLIP-strides"] and not g["complete"]                    # no foot contacts supplied: the stride count is UNVERIFIED, never a pass
    strides = VGT.clip_gates(good, fps=24, duration=5.0, size=(720, 1280), foot_contacts=[3, 33, 63, 93, 123])
    assert strides["complete"] and strides["gates"]["G-CLIP-strides"]["value"] == 4
    assert not VGT.clip_gates(good, fps=24, duration=5.0, size=(720, 1280), foot_contacts=[3, 63, 123])["gates"]["G-CLIP-strides"]["passed"]
    small = VGT.clip_gates(figure_clip(24 * 5, 720, 1280, 800), fps=24, duration=5.0, size=(720, 1280))
    assert not small["gates"]["G-CLIP-figure"]["passed"] and not small["passed"]
    cut = VGT.clip_gates(figure_clip(24 * 5, 720, 1280, 1100, margin=0), fps=24, duration=5.0, size=(720, 1280))
    assert not cut["gates"]["G-CLIP-figure"]["passed"]                                   # the feet touch the border
    dup = VGT.clip_gates([f for f in figure_clip(60, 720, 1280, 1100) for _ in range(2)], fps=24, duration=5.0, size=(720, 1280))
    assert not dup["gates"]["G-CLIP-fps"]["passed"] and "duplicate frames" in dup["gates"]["G-CLIP-fps"]["message"]
    wrong = VGT.clip_gates(figure_clip(24 * 5, 1280, 720, 600), fps=24, duration=5.0, size=(1280, 720))
    assert not wrong["gates"]["G-CLIP-size"]["passed"]
    short = VGT.clip_gates(good[:60], fps=24, duration=2.5, size=(720, 1280))
    assert not short["gates"]["G-CLIP-duration"]["passed"]


def test_the_upscale_gate_wants_size_duration_fps_and_a_downscale_that_matches_the_source():
    src = _clip(24, 64, 48)
    lanczos = [np.asarray(__import__("PIL.Image", fromlist=["x"]).fromarray(f).resize((128, 96), 1)) for f in src]
    g = VGT.upscale_gate(src, lanczos, factor=2.0, src_fps=24, out_fps=24)
    assert g["passed"] and g["ssim"] >= 0.95
    assert not VGT.upscale_gate(src, lanczos[:-3], 2.0, 24, 24)["passed"]                  # duration differs by more than a frame
    assert not VGT.upscale_gate(src, lanczos, 3.0, 24, 24)["passed"]                       # size is not source x factor
    noise = [np.random.default_rng(i).integers(0, 255, (96, 128, 3), dtype=np.uint8) for i in range(24)]
    assert not VGT.upscale_gate(src, noise, 2.0, 24, 24)["passed"]                         # a repaint does not match the source
    assert "no gain over Lanczos" in VGT.upscale_gate(src, lanczos, 2.0, 24, 24)["flags"]


def test_the_edit_gate_keeps_the_outside_of_the_mask_and_the_length_within_a_frame():
    src = _clip(24)
    edited = [f.copy() for f in src]
    mask = np.zeros((48, 64), bool); mask[16:32, :] = True
    for f in edited:
        f[mask] = 90                                                                        # only the masked band changes
    g = VGT.edit_gate(src, edited, mask)
    assert g["passed"] and g["outside_mask_psnr"] > 60 and g["duration_delta_frames"] == 0
    repaint = [np.full_like(f, 200) for f in src]
    assert not VGT.edit_gate(src, repaint, mask)["passed"]
    assert not VGT.edit_gate(src, edited[:-3], mask)["passed"]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_ffmpeg_decodes_probes_and_builds_a_ping_pong_file(tmp_path):
    from PIL import Image
    d = tmp_path / "f"; d.mkdir()
    for i, f in enumerate(_clip(24)):
        Image.fromarray(f).save(d / f"{i:03d}.png")
    src = tmp_path / "src.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-framerate", "24", "-i", str(d / "%03d.png"), "-pix_fmt", "yuv420p", str(src)], check=True)
    info = VGT.probe(str(src))
    assert info["width"] == 64 and info["height"] == 48 and info["fps"] == pytest.approx(24.0) and info["frames"] == 24
    out = tmp_path / "loop.mp4"
    VGT.pingpong_file(str(src), str(out))
    frames = VGT.decode(str(out))
    assert VGT.closure(frames)["wrap_jump"] <= 1.5 and len(frames) >= 46
