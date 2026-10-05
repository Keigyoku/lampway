"""Deterministic video measures: no model, no network. ffmpeg decodes, probes and builds the closure files; every gate is numpy on frames.

Thresholds are PROPOSED (the specs mark them UNVERIFIED) and live in one place so a recorded clip can replace them. A gate that could not be measured is
reported ``unverified``, never as a pass."""
import json
import subprocess

import numpy as np

CLOSURE_DIFF_MAX = 6.0          # mean abs pixel difference first vs last frame, 0..255 [proposed]
WRAP_JUMP_MAX = 2.0             # inter-frame change across the wrap / the median inter-frame change [proposed]
HELD_EPS = 0.5                  # a frame is held when its mean abs difference to the previous is <= 0.5/255 * 255 grey levels
CLIP_SIZE = (720, 1280)
CLIP_DURATION = 5.0
CLIP_DURATION_TOL = 0.1
FIGURE_MIN_PX = 1000
CAMERA_DRIFT_MAX = 0.03         # feet (bbox bottom) may move 3 % of the frame height [proposed]
CAMERA_CUT_MAX = 40.0           # no frame-to-frame full-frame change above 40/255 [proposed]
MIN_STRIDES = 4
UPSCALE_SSIM_MIN = 0.95         # [proposed]
EDIT_PSNR_MIN = 35.0            # outside the mask [proposed]
PSNR_CAP = 99.0


class VideoGateError(ValueError):
    pass


# ----------------------------------------------------------------------------------------------------------------- ffmpeg
def probe(path: str) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate,nb_read_frames:format=duration", "-of", "json", path], capture_output=True, text=True, timeout=120)
    data = json.loads(out.stdout or "{}")
    st = (data.get("streams") or [{}])[0]
    num, _, den = str(st.get("r_frame_rate") or "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    if not st:
        raise VideoGateError(f"not a readable video: {path}")
    return {"width": int(st["width"]), "height": int(st["height"]), "fps": fps, "frames": int(st.get("nb_read_frames") or 0),
            "duration": float((data.get("format") or {}).get("duration") or 0)}


def decode(path: str, max_frames: int = 1000, gray: bool = False) -> list:
    """Every frame as an (h, w, 3) uint8 array, or (h, w) with gray=True (a third of the memory: the clip gates only need luminance)."""
    info = probe(path)
    w, h = info["width"], info["height"]
    ch = 1 if gray else 3
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-frames:v", str(max_frames), "-f", "rawvideo", "-pix_fmt", "gray" if gray else "rgb24", "-"], capture_output=True, timeout=300).stdout
    n = len(raw) // (w * h * ch)
    shape = (h, w) if gray else (h, w, 3)
    return [np.frombuffer(raw, np.uint8, w * h * ch, i * w * h * ch).reshape(shape) for i in range(n)]


def pingpong_file(src: str, dst: str) -> str:
    """Forward then reversed (without repeating the end frames): perfect closure by construction. Writes a new file; the source is untouched."""
    if src == dst:
        raise VideoGateError("the closure fix writes a second file, never over the model output")
    graph = "[0:v]split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1:a=0[o]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-filter_complex", graph, "-map", "[o]", "-pix_fmt", "yuv420p", dst], check=True, timeout=300)
    return dst


# --------------------------------------------------------------------------------------------------------------- measures
def _f(a):
    return np.asarray(a, np.float32)


def _mad(a, b):
    return float(np.abs(_f(a) - _f(b)).mean())


def closure(frames) -> dict:
    """closure_diff: mean abs difference between the first and last frame (0..255). wrap_jump: the change across the wrap over the median change inside the clip."""
    if len(frames) < 3:
        raise VideoGateError("a loop measure needs at least 3 frames")
    steps = [_mad(a, b) for a, b in zip(frames, frames[1:])]
    wrap = _mad(frames[-1], frames[0])
    med = float(np.median(steps))
    jump = 0.0 if wrap == 0 else wrap / max(med, 1e-6)
    return {"closure_diff": round(_mad(frames[0], frames[-1]), 4), "wrap_jump": round(jump, 4), "frames": len(frames)}


def loop_gate(c: dict) -> dict:
    ok = c["closure_diff"] <= CLOSURE_DIFF_MAX and c["wrap_jump"] <= WRAP_JUMP_MAX
    msg = "closed" if ok else (f"wrap jump {c['wrap_jump']} > {WRAP_JUMP_MAX}: the model's end pose differs from the first frame; use the crossfade closure or re-run (a re-run is a new charge)"
                               if c["wrap_jump"] > WRAP_JUMP_MAX else f"closure diff {c['closure_diff']} > {CLOSURE_DIFF_MAX}: the last frame differs from the first; use the crossfade closure")
    return {"passed": ok, "message": msg, **c}


def pingpong_frames(frames) -> list:
    return list(frames) + list(frames[-2::-1])


def crossfade_frames(frames, fade: int = 8) -> list:
    """The last ``fade`` frames fade into the clip's first ``fade`` frames and the loop restarts after them: the output is ``fade`` frames shorter and its
    last frame is the frame just before its first."""
    n = len(frames)
    if not 1 <= fade < n // 2:
        raise VideoGateError(f"fade {fade} does not fit a clip of {n} frames")
    body = [np.asarray(f) for f in frames[fade:n - fade]]
    tail = []
    for i in range(fade):
        a = (i + 1) / fade
        tail.append(((1 - a) * _f(frames[n - fade + i]) + a * _f(frames[i])).round().astype(np.uint8))
    return body + tail


def duplicate_frames(frames, fps: float = 24.0) -> dict:
    held = sum(1 for a, b in zip(frames, frames[1:]) if _mad(a, b) <= HELD_EPS)
    unique = len(frames) - held
    return {"held": held, "unique": unique, "frames": len(frames), "true_fps": fps * unique / len(frames) if frames else 0.0}


def _gray(f):
    f = _f(f)
    return f.mean(axis=2) if f.ndim == 3 else f


def _resize(f, size):
    from PIL import Image
    return np.asarray(Image.fromarray(np.asarray(f, np.uint8)).resize(size, Image.LANCZOS))


def _ssim(a, b, block=8):
    a, b = _gray(a), _gray(b)
    h, w = (min(a.shape[0], b.shape[0]) // block) * block, (min(a.shape[1], b.shape[1]) // block) * block
    a, b = a[:h, :w].reshape(h // block, block, w // block, block), b[:h, :w].reshape(h // block, block, w // block, block)
    ma, mb = a.mean((1, 3)), b.mean((1, 3))
    va, vb = a.var((1, 3)), b.var((1, 3))
    cov = ((a - ma[:, None, :, None]) * (b - mb[:, None, :, None])).mean((1, 3))
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    return float((((2 * ma * mb + c1) * (2 * cov + c2)) / ((ma ** 2 + mb ** 2 + c1) * (va + vb + c2))).mean())


def _lap_var(f):
    g = _gray(f)
    return float((g[1:-1, 1:-1] * 4 - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]).var())


def upscale_gate(src, out, factor: float, src_fps: float, out_fps: float) -> dict:
    """Duration equal within one frame, size = source x factor within 2 px, fps equal, and the output downscaled back matches the source (SSIM). A result that is no sharper
    than a free Lanczos resize is flagged."""
    sh, sw = np.asarray(src[0]).shape[:2]
    oh, ow = np.asarray(out[0]).shape[:2]
    checks = {"duration": abs(len(out) - len(src)) <= 1, "size": abs(ow - sw * factor) <= 2 and abs(oh - sh * factor) <= 2, "fps": abs(out_fps - src_fps) < 1e-6}
    ssim = 0.0
    flags = []
    if checks["duration"] and checks["size"]:
        picks = np.linspace(0, min(len(src), len(out)) - 1, num=min(8, len(src))).astype(int)
        ssim = float(np.mean([_ssim(src[i], _resize(out[i], (sw, sh))) for i in picks]))
        base = np.mean([_lap_var(_resize(src[i], (ow, oh))) for i in picks])
        if np.mean([_lap_var(out[i]) for i in picks]) <= base * 1.0 + 1e-9:
            flags.append("no gain over Lanczos")
    checks["ssim"] = ssim >= UPSCALE_SSIM_MIN
    return {"passed": all(checks.values()), "checks": checks, "ssim": round(ssim, 4), "flags": flags}


def edit_gate(src, edited, mask) -> dict:
    """The length within one frame of the source, and the pixels OUTSIDE the edit mask unchanged (PSNR)."""
    delta = len(edited) - len(src)
    n = min(len(src), len(edited))
    keep = ~np.asarray(mask, bool)
    mse = float(np.mean([((_f(src[i]) - _f(edited[i]))[keep] ** 2).mean() for i in range(n)])) if n and keep.any() else 0.0
    psnr = PSNR_CAP if mse <= 1e-9 else min(PSNR_CAP, float(10 * np.log10(255.0 ** 2 / mse)))
    return {"passed": abs(delta) <= 1 and psnr >= EDIT_PSNR_MIN, "duration_delta_frames": delta, "outside_mask_psnr": round(psnr, 2)}


# ------------------------------------------------------------------------------------------------------------------ clips
def _figure(f, thr=25.0):
    g = _gray(f)
    m = np.abs(g - np.median(g)) > thr
    rows = np.flatnonzero(m.any(axis=1))
    return m, (int(rows.min()), int(rows.max())) if len(rows) else None


def clip_gates(frames, fps: float, duration: float, size: tuple, foot_contacts=None) -> dict:
    """The character-clip gates of anim_clip: 24 fps all distinct, 720x1280, 5.0 s, a figure of at least 1000 px that never touches the border, a locked camera,
    and at least 4 strides (needs the foot contacts: without them that gate is UNVERIFIED)."""
    gates = {}
    dup = duplicate_frames(frames, fps)
    want = round(duration * 24)
    gates["G-CLIP-fps"] = {"passed": len(frames) == want and dup["held"] == 0, "value": dup["unique"],
                           "message": f"duplicate frames {dup['held']} of {len(frames)}" + (" (the clip is upsampled)" if dup["held"] else "") + f"; {len(frames)} frames, {want} expected"}
    gates["G-CLIP-size"] = {"passed": tuple(size) == CLIP_SIZE, "value": list(size), "message": f"{size[0]}x{size[1]}, expected {CLIP_SIZE[0]}x{CLIP_SIZE[1]}"}
    gates["G-CLIP-duration"] = {"passed": abs(duration - CLIP_DURATION) <= CLIP_DURATION_TOL, "value": duration, "message": f"{duration} s, expected {CLIP_DURATION} +/- {CLIP_DURATION_TOL}"}
    heights, touches, bottoms, jumps = [], 0, [], []
    for i, f in enumerate(frames):
        m, span = _figure(f)
        heights.append(0 if span is None else span[1] - span[0] + 1)
        touches += int(span is not None and (m[0].any() or m[-1].any() or m[:, 0].any() or m[:, -1].any()))
        bottoms.append(span[1] if span else 0)
        if i:
            jumps.append(_mad(frames[i - 1], f))
    H = np.asarray(frames[0]).shape[0]
    gates["G-CLIP-figure"] = {"passed": min(heights) >= FIGURE_MIN_PX and touches == 0, "value": min(heights),
                              "message": f"figure {min(heights)} px (>= {FIGURE_MIN_PX}), touches the border in {touches} frames"}
    drift = (max(bottoms) - min(bottoms)) / H
    cut = max(jumps) if jumps else 0.0
    gates["G-CLIP-camera"] = {"passed": drift <= CAMERA_DRIFT_MAX and cut <= CAMERA_CUT_MAX, "value": {"feet_drift": round(drift, 4), "max_frame_change": round(cut, 2)},
                              "message": f"feet drift {drift:.3f} of the height (<= {CAMERA_DRIFT_MAX}); largest frame change {cut:.1f}/255 (<= {CAMERA_CUT_MAX})"}
    unverified = []
    if foot_contacts is None:
        gates["G-CLIP-strides"] = {"passed": None, "value": None, "message": "UNVERIFIED: no foot contacts supplied (the tracker measures them)"}
        unverified.append("G-CLIP-strides")
    else:
        strides = max(0, len(foot_contacts) - 1)
        gates["G-CLIP-strides"] = {"passed": strides >= MIN_STRIDES, "value": strides, "message": f"{strides} strides (>= {MIN_STRIDES})"}
    return {"gates": gates, "passed": all(g["passed"] is not False for g in gates.values()), "complete": not unverified, "unverified": unverified}


# ------------------------------------------------------------------------------------------------------------ the tool's entry
def run_gate(kind, video, source=None, mask=None, factor=None, fix=None, foot_contacts=None, loader=None) -> dict:
    """Decode the file(s) and run one gate. Paths arrive already resolved inside the project. ``loader`` reads a mask PNG to a 2-D array (default: PIL)."""
    if kind == "loop":
        frames = decode(video)
        c = closure(frames)
        out = loop_gate(c)
        if fix == "pingpong":
            dst = video.rsplit(".", 1)[0] + "_loop.mp4"
            pingpong_file(video, dst)
            out["fixed_file"] = dst
            out["fixed"] = loop_gate(closure(decode(dst)))
        elif fix:
            raise VideoGateError("fix is pingpong")
        return out
    if kind == "duplicates":
        info = probe(video)
        return duplicate_frames(decode(video), info["fps"] or 24.0)
    if kind == "clip":
        info = probe(video)
        return clip_gates(decode(video, gray=True), info["fps"], info["duration"], (info["width"], info["height"]), foot_contacts)
    if kind == "upscale":
        if not source or not factor:
            raise VideoGateError("an upscale gate needs the source video and the factor")
        si, oi = probe(source), probe(video)
        return upscale_gate(decode(source), decode(video), float(factor), si["fps"], oi["fps"])
    if kind == "edit":
        if not source or not mask:
            raise VideoGateError("an edit gate needs the region mask (a PNG, white where the edit is allowed) and the source video")
        if loader is None:
            from PIL import Image
            loader = lambda p: np.asarray(Image.open(p).convert("L"))
        return edit_gate(decode(source), decode(video), loader(mask) > 127)
    raise VideoGateError("kind is loop | clip | duplicates | upscale | edit")
