"""Asset Vault video (specs/asset_library/asset_video.md): a clip's facts, its TRUE motion rate, its held and blended frames, its panels.

ffprobe for the container; ffmpeg decodes to small greyscale frames and numpy does the rest. A hold is a frame that barely differs from the one before (the threshold
adapts to the clip: ``max(EPS_ABS, K x median of the moving steps)``); the motion rate is the container rate over the median gap between frames that move; a clip whose
in-between frames are the average of their neighbours is flagged ``blend_suspect`` and gets NO motion rate rather than a wrong one. Every number is reproducible for the
same file. ffmpeg runs niced; the clip is only read. Derived artefacts, attachments and comparison live in ``video_derive`` (re-exported here)."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import numpy as np

from . import derived as D
from .store import AssetLibrary, LibraryError

NICE = 19
EPS_ABS = 0.5                     # grey levels (0..255) of mean absolute difference below which a step is a hold whatever the clip [calibrated on the synthetic fixtures]
SEPARATION = 4.0                  # holds are a separate cluster only when the moving steps are at least 4x the held ones (grain makes a hold differ a little)
BLEND_LOW, BLEND_HIGH = 0.15, 0.3  # an in-between that is the average of its neighbours leaves a residual near 0; a real frame leaves about 0.5
SILENT_DB = -60.0
MAX_ANALYZE_S = 300.0
ANALYZE_WIDTH = 128
PANEL_WIDTH = 640
_VERSION = "lampway.video@" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12]


def _need(tool: str):
    if not shutil.which(tool):
        raise LibraryError("ffmpeg not found on PATH: install it (the server needs ffmpeg + ffprobe)")


def _run(argv, timeout=600, text=False):
    return subprocess.run(["nice", "-n", str(NICE), *map(str, argv)], capture_output=True, text=text, timeout=timeout)


def _rate(s) -> Optional[float]:
    try:
        n, d = str(s).split("/")
        return float(n) / float(d) if float(d) else None
    except (ValueError, AttributeError):
        return None


def probe(path) -> dict:
    """The container facts, ffprobe's own numbers; ``frame_count`` is counted by decoding when the container does not say (it did not, for every clip probed)."""
    _need("ffprobe")
    p = _run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path], 120, text=True)
    doc = json.loads(p.stdout or "{}") if p.returncode == 0 else {}
    v = next((s for s in doc.get("streams", []) if s.get("codec_type") == "video"), None)
    if not v:
        raise LibraryError(f"cannot decode {path}: {(p.stderr or 'no video stream').strip()[-300:]}")
    a = next((s for s in doc.get("streams", []) if s.get("codec_type") == "audio"), None)
    fmt = doc.get("format", {})
    count = int(v["nb_frames"]) if str(v.get("nb_frames", "")).isdigit() else None
    if count is None:
        c = _run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "json", path], 300, text=True)
        count = int(((json.loads(c.stdout or "{}").get("streams") or [{}])[0]).get("nb_read_frames") or 0)
    rot = next((int(sd.get("rotation", 0)) for sd in v.get("side_data_list", []) if "rotation" in sd), int((v.get("tags") or {}).get("rotate", 0) or 0))
    return {"container": fmt.get("format_name"), "codec": v.get("codec_name"), "profile": v.get("profile"), "pix_fmt": v.get("pix_fmt"), "width": v.get("width"),
            "height": v.get("height"), "sar": v.get("sample_aspect_ratio"), "rotation": rot, "container_fps": _rate(v.get("r_frame_rate")), "avg_fps": _rate(v.get("avg_frame_rate")),
            "frame_count": count, "duration_s": float(fmt["duration"]) if fmt.get("duration") else None,
            "bitrate": int(fmt["bit_rate"]) if str(fmt.get("bit_rate", "")).isdigit() else None, "has_audio": 1 if a else 0, "audio_codec": a.get("codec_name") if a else None}


def audio_facts(path) -> dict:
    """Is there audio, and is it silence (ffmpeg's volumedetect: a peak at or under -60 dB)? ``audio_silent`` is None when there is no audio to judge."""
    p = probe(path)
    if not p["has_audio"]:
        return {"has_audio": 0, "audio_codec": None, "audio_silent": None}
    r = _run(["ffmpeg", "-v", "info", "-nostdin", "-i", path, "-map", "0:a:0", "-af", "volumedetect", "-f", "null", "-"], 300, text=True)
    m = re.search(r"max_volume:\s*(-?inf|-?[\d.]+) dB", r.stderr or "")
    peak = float("-inf") if not m or "inf" in m.group(1) else float(m.group(1))
    return {"has_audio": 1, "audio_codec": p["audio_codec"], "audio_silent": 1 if peak <= SILENT_DB else 0}


def decode_gray(path, width: int, height: int, start_s=None, end_s=None, fps=None) -> np.ndarray:
    """(N, height, width) uint8 luminance frames, decoded niced; ``fps`` resamples (for the panel scan), ``start_s``/``end_s`` cut a range."""
    _need("ffmpeg")
    vf = (f"fps={fps}," if fps else "") + f"scale={width}:{height},format=gray"
    argv = ["ffmpeg", "-v", "error", "-nostdin"] + (["-ss", start_s] if start_s is not None else []) + ["-i", path]
    argv += (["-t", float(end_s) - float(start_s or 0)] if end_s is not None else []) + ["-map", "0:v:0", "-vf", vf, "-f", "rawvideo", "-"]
    p = _run(argv, 900)
    n = len(p.stdout) // (width * height)
    if p.returncode != 0 or n == 0:
        raise LibraryError(f"cannot decode {path}: {p.stderr.decode(errors='replace').strip()[-300:]}")
    return np.frombuffer(p.stdout, np.uint8, n * width * height).reshape(n, height, width)


def _small(info) -> tuple:
    w, h = info["width"] or ANALYZE_WIDTH, info["height"] or ANALYZE_WIDTH
    return ANALYZE_WIDTH, max(2, int(round(ANALYZE_WIDTH * h / w / 2)) * 2)


def analyze_motion(path, fps: float, start_s=None, end_s=None, dup_threshold=None) -> dict:
    info = probe(path)
    frames = decode_gray(path, *_small(info), start_s=start_s, end_s=end_s).astype(np.float32)
    return motion_of(frames, fps, dup_threshold)


def hold_threshold(d: np.ndarray) -> float:
    """Split the steps into held and moving by the best two-cluster cut of log(step) (Otsu); the cut counts only when the clusters sit SEPARATION apart, and then the
    threshold is their geometric midpoint. Otherwise only steps under EPS_ABS are holds. (The contract's ``K x median`` rule failed on grain: with half the steps held,
    the median sits between the clusters.)"""
    x = np.sort(np.log(np.asarray(d, "float64") + 0.1))
    if len(x) < 4:
        return EPS_ABS
    n, c = len(x), np.cumsum(x)
    i = np.arange(1, n)
    between = i * (n - i) * (c[:-1] / i - (c[-1] - c[:-1]) / (n - i)) ** 2
    cut = int(np.argmax(between)) + 1
    lo, hi = np.exp(x[:cut]) - 0.1, np.exp(x[cut:]) - 0.1
    if hi.mean() / max(lo.mean(), 0.1) < SEPARATION:
        return EPS_ABS
    return max(EPS_ABS, float(np.sqrt(max(lo.max(), 0.01) * hi.min())))


def motion_of(frames: np.ndarray, fps: float, dup_threshold=None) -> dict:
    n = len(frames)
    d = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2)) if n > 1 else np.zeros(0)
    thr = float(dup_threshold) if dup_threshold is not None else hold_threshold(d)
    holds = d < thr
    runs, cur = [], 0
    for h in holds:
        cur = cur + 1 if h else 0
        runs.append(cur)
    out = {"frames": n, "dup_frames": int(holds.sum()), "dup_ratio": round(float(holds.mean()), 6) if d.size else 0.0, "longest_hold": int(max(runs, default=0)),
           "motion_energy": round(float(d.mean()), 6) if d.size else 0.0, "hold_threshold": round(thr, 6), "blend_suspect": 0}
    starts = np.concatenate([[0], np.nonzero(~holds)[0] + 1])     # the frames whose picture is new
    gaps = np.diff(starts)
    if not gaps.size:
        return {**out, "motion_fps": 0.0, "motion_fps_confidence": 1.0}
    if out["dup_ratio"] < 0.1 and n >= 8:
        mid = frames[1:-1] - (frames[:-2] + frames[2:]) / 2
        span = np.abs(frames[2:] - frames[:-2]).mean(axis=(1, 2))
        ok = span > EPS_ABS
        r = np.abs(mid).mean(axis=(1, 2))[ok] / span[ok]
        parity = np.arange(len(span))[ok] % 2
        if r.size >= 6 and (parity == 0).any() and (parity == 1).any():
            lo, hi = sorted((float(np.median(r[parity == 0])), float(np.median(r[parity == 1]))))
            if lo < BLEND_LOW and hi > BLEND_HIGH:
                return {**out, "blend_suspect": 1, "motion_fps": None, "motion_fps_confidence": None}
    g = float(np.median(gaps))
    cv = float(gaps.std() / gaps.mean()) if gaps.mean() else 0.0
    return {**out, "motion_fps": round(fps / g, 3), "motion_fps_confidence": round(max(0.0, 1.0 - cv), 4)}


def _band(var: np.ndarray):
    """The longest run of near-constant lines in the middle half (a divider), as (start, stop) in that axis, else None."""
    n = len(var)
    low = var < 0.1 * float(np.median(var)) if np.median(var) > 0 else np.zeros(n, bool)
    best, run_start = None, None
    for i in range(n + 1):
        if i < n and low[i]:
            run_start = i if run_start is None else run_start
            continue
        if run_start is not None and i - run_start >= 2 and run_start >= n * 0.25 and i <= n * 0.75 and (best is None or i - run_start > best[1] - best[0]):
            best = (run_start, i)
        run_start = None
    return best


def detect_panels(path) -> dict:
    """A split-screen clip's divider: a band of columns (side by side) or rows (stacked) that never changes and has no detail, in the middle half of the frame."""
    info = probe(path)
    W, H = info["width"], info["height"]
    w = min(W, PANEL_WIDTH)
    h = max(2, int(round(w * H / W / 2)) * 2)
    f = decode_gray(path, w, h, fps=4).astype(np.float32)[:48]
    cols, rows = _band(f.std(axis=(0, 1))), _band(f.std(axis=(0, 2)))
    sx, sy = W / w, H / h
    if cols and not rows:
        x0, x1 = int(round(cols[0] * sx)), int(round(cols[1] * sx))
        return {"panel_layout": "split_front_side", "divider": {"axis": "x", "x": x0, "w": x1 - x0},
                "panels": [{"x": 0, "y": 0, "w": x0, "h": H}, {"x": x1, "y": 0, "w": W - x1, "h": H}]}
    if rows and not cols:
        y0, y1 = int(round(rows[0] * sy)), int(round(rows[1] * sy))
        return {"panel_layout": "split_front_side", "divider": {"axis": "y", "y": y0, "w": y1 - y0},
                "panels": [{"x": 0, "y": 0, "w": W, "h": y0}, {"x": 0, "y": y1, "w": W, "h": H - y1}]}
    if rows and cols:
        x0, x1, y0, y1 = (int(round(v)) for v in (cols[0] * sx, cols[1] * sx, rows[0] * sy, rows[1] * sy))
        return {"panel_layout": "grid_2x2", "divider": {"axis": "xy", "x": x0, "w": x1 - x0, "y": y0, "h": y1 - y0},
                "panels": [{"x": 0, "y": 0, "w": x0, "h": y0}, {"x": x1, "y": 0, "w": W - x1, "h": y0}, {"x": 0, "y": y1, "w": x0, "h": H - y1}, {"x": x1, "y": y1, "w": W - x1, "h": H - y1}]}
    return {"panel_layout": "single", "divider": None, "panels": [{"x": 0, "y": 0, "w": W, "h": H}]}


def main_path(lib: AssetLibrary, a: dict) -> Path:
    for f in a["files"]:
        if f["role"] == "main" and f["locations"]:
            return Path(f["locations"][0]["path"])
    raise LibraryError(f"asset {a['id']} has no main file")


def video_asset(lib: AssetLibrary, asset_id: str):
    a = lib.get(asset_id)
    if a["kind"] != "video":
        raise LibraryError(f"not a video: kind is {a['kind']}")
    return a, main_path(lib, a)


def analyze(lib: AssetLibrary, asset_id: str, start_s=None, end_s=None, dup_threshold=None, audio_expected: Optional[bool] = None) -> dict:
    a, path = video_asset(lib, asset_id)
    try:
        info = probe(path)
    except LibraryError:
        D.add_tag(lib, asset_id, "defect:undecodable")             # kept, active, flagged: never deleted for failing to decode
        raise
    if start_s is None and end_s is None and (info["duration_s"] or 0) > MAX_ANALYZE_S:
        raise LibraryError(f"clip longer than {MAX_ANALYZE_S:g} s: analyse a range: pass start_s/end_s")
    motion = analyze_motion(path, info["container_fps"] or 24.0, start_s, end_s, dup_threshold)
    panels = detect_panels(path)
    stats = {**info, **audio_facts(path), **{k: motion[k] for k in ("motion_fps", "motion_fps_confidence", "dup_frames", "dup_ratio", "longest_hold", "blend_suspect")},
             "panel_layout": panels["panel_layout"], "panels_json": json.dumps(panels["panels"]), "analyzed_with": _VERSION}
    gates = [{"gate": "dup_frames", "value": motion["dup_frames"], "threshold": 0, "passed": motion["dup_frames"] == 0},
             {"gate": "motion_fps_ge_24", "value": motion["motion_fps"], "threshold": 24.0, "passed": motion["motion_fps"] is not None and motion["motion_fps"] >= 23.5},
             {"gate": "duration_s", "value": info["duration_s"], "threshold": None, "passed": bool(info["duration_s"])}]
    if audio_expected is not None:
        gates.append({"gate": "audio_expected", "value": stats["has_audio"], "threshold": 1 if audio_expected else 0, "passed": bool(stats["has_audio"]) == bool(audio_expected)})
    vid = lib.version_of(asset_id)
    with lib.tx() as db:
        cols = list(stats)
        db.execute(f"INSERT OR REPLACE INTO video_stats(version_id,{','.join(cols)}) VALUES(?{',?' * len(cols)})", (vid, *stats.values()))
        db.execute("DELETE FROM gate_result WHERE version_id=? AND run_id='asset_video'", (vid,))
        for g in gates:
            db.execute("INSERT INTO gate_result(version_id,gate,value,threshold,passed,detail_json,run_id,ts) VALUES(?,?,?,?,?,?,?,?)",
                       (vid, g["gate"], g["value"], g["threshold"], 1 if g["passed"] else 0, json.dumps({"tool": _VERSION}), "asset_video", lib._now()))
        lib._event("analyze", asset_id, {"tool": _VERSION})
    return {"ok": True, "asset_id": asset_id, "stats": stats, "gates": gates, "range": [start_s, end_s] if start_s is not None or end_s is not None else None}


from .video_derive import attach, compare, derive, handle  # noqa: E402,F401  (the derive/attach/compare half, re-exported)
