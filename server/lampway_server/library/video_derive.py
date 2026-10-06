"""asset_video's second half: the artefacts derived FROM a clip (frame strip, panel crops, the 8 fps proxy, keyframe descriptors), the artefacts other tools attach
TO it (keypoints, fit results, gate receipts, the start frame, the retargeted animation), and the side-by-side alignment of two clips.

A derived artefact that is a thing of its own (a strip, a panel) is an asset with a relation to the clip; a cache (the proxy frames) is a derived file of the clip's
version. Nothing here models or guesses: keypoints and fits come from their own tools and are attached, never computed."""
from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

import numpy as np

from . import derived as D
from . import video as V
from .store import AssetLibrary, LibraryError

PROXY_FPS, PROXY_H = 8, 256
KF_EVERY_S, KF_MAX = 0.5, 24
LAYOUTS = ("split_front_side", "grid_2x2", "single")
PANEL_ROLES = {"split_front_side": ["panel:front", "panel:side"], "grid_2x2": ["panel:tl", "panel:tr", "panel:bl", "panel:br"]}
# role -> (kind, subtype, relation, direction): "from" = artefact -> clip, "to" = clip -> artefact
ATTACH = {"keypoints_2d": ("receipt", "track", "derived_from", "from"), "fit_result": ("receipt", "fit", "derived_from", "from"),
          "anim_check": ("receipt", "gate", "derived_from", "from"), "overlay": ("image", None, "derived_from", "from"),
          "retargeted": ("animation", "retargeted", "drives", "to"), "start_frame": ("image", None, "generated_from", "to"),
          "end_frame": ("image", None, "generated_from", "to"), "reference": ("image", None, "generated_from", "to"), "variant": ("video", None, "variant_of", "from")}


def _frames_png(path, indices, height) -> list:
    """The frames at ``indices`` as PIL images (one ffmpeg pass with a select filter)."""
    from PIL import Image
    sel = "+".join(f"eq(n\\,{i})" for i in indices)
    p = V._run(["ffmpeg", "-v", "error", "-nostdin", "-i", path, "-map", "0:v:0", "-vf", f"select='{sel}',scale=-2:{height}", "-fps_mode", "passthrough",
                "-f", "image2pipe", "-vcodec", "png", "-"], 600)
    data, out, sig = p.stdout, [], b"\x89PNG\r\n\x1a\n"
    starts = [i for i in range(len(data)) if data.startswith(sig, i)] if data else []
    for a, b in zip(starts, starts[1:] + [len(data)]):
        with Image.open(io.BytesIO(data[a:b])) as im:
            out.append(im.convert("RGB"))
    if not out:
        raise LibraryError(f"cannot decode {path}: {p.stderr.decode(errors='replace').strip()[-300:]}")
    return out


def _strip(lib, clip, a, path, count=12, size=256, every_s=None) -> dict:
    from PIL import Image, ImageDraw, ImageFont
    if not 8 <= int(count) <= 64:
        raise LibraryError("strip count 8..64")
    if not 128 <= int(size) <= 512:
        raise LibraryError("strip size 128..512")
    info = V.probe(path)
    n = info["frame_count"] or 1
    idx = sorted({min(n - 1, int(round(t * (info["container_fps"] or 24)))) for t in np.arange(0, info["duration_s"] or 0, float(every_s))})[:int(count)] if every_s \
        else sorted({int(i) for i in np.linspace(0, n - 1, int(count))})
    ims = _frames_png(path, idx, int(size))
    cols = min(len(ims), 8)
    w, h = ims[0].size
    sheet = Image.new("RGB", (cols * w, -(-len(ims) // cols) * h), (40, 40, 40))
    draw, font = ImageDraw.Draw(sheet), ImageFont.load_default(size=12)
    for k, (i, im) in enumerate(zip(idx, ims)):
        x, y = (k % cols) * w, (k // cols) * h
        sheet.paste(im, (x, y))
        draw.text((x + 4, y + 3), f"#{i}", fill=(255, 255, 0), font=font)
    b = io.BytesIO()
    sheet.save(b, "JPEG", quality=88)
    res = lib.put({"kind": "image", "subtype": "strip", "name": f"{a['name']} strip", "source": {"kind": "derived", "key": f"{clip}:strip:{len(idx)}:{size}:{every_s}"},
                   "files": [{"role": "main", "bytes": b.getvalue(), "storage": "cas", "name": "strip.jpg"}], "attrs": {"frames": idx, "of": clip},
                   "relations": [{"type": "derived_from", "to": clip, "role": "frame_strip"}]})
    return {"asset_id": res["id"], "frames": idx}


def _proxy(lib, clip, path) -> dict:
    with tempfile.TemporaryDirectory(dir=lib.root) as tmp:
        p = V._run(["ffmpeg", "-v", "error", "-nostdin", "-i", path, "-map", "0:v:0", "-vf", f"fps={PROXY_FPS},scale=-2:{PROXY_H}", "-q:v", "4", str(Path(tmp) / "%05d.jpg")], 900)
        files = sorted(Path(tmp).glob("*.jpg"))
        if p.returncode != 0 or not files:
            raise LibraryError(f"cannot decode {path}: {p.stderr.decode(errors='replace').strip()[-300:]}")
        items = [(f"proxy_{i:05d}.jpg", f.read_bytes()) for i, f in enumerate(files)]
    D.replace(lib, lib.version_of(clip), "proxy", items)
    return {"frames": len(items), "fps": PROXY_FPS}


def _keyframes(lib, clip, path) -> dict:
    """One 4x4x4 colour histogram per keyframe (every 0.5 s, at most 24), stored as ``video_kf_hist`` with ``sub_key = kf:<frame>``: deterministic, local."""
    info = V.probe(path)
    fps = info["container_fps"] or 24.0
    n = info["frame_count"] or 1
    idx = [int(round(t * fps)) for t in np.arange(0, (info["duration_s"] or 0), KF_EVERY_S)][:KF_MAX] or [0]
    idx = sorted({min(i, n - 1) for i in idx})
    vid = lib.version_of(clip)
    for i, im in zip(idx, _frames_png(path, idx, 64)):
        a = np.asarray(im.resize((32, 32)), dtype=np.int64) // 64
        h = np.bincount((a[:, :, 0] * 16 + a[:, :, 1] * 4 + a[:, :, 2]).reshape(-1), minlength=64).astype("float64")
        lib.put_embedding(vid, "video_kf_hist", h / np.linalg.norm(h), model="deterministic", sub_key=f"kf:{i}")
    return {"keyframes": len(idx), "frames": idx}


def _panels(lib, clip, a, path, layout=None) -> dict:
    stats = a.get("stats") or {}
    layout = layout or stats.get("panel_layout")
    if layout not in PANEL_ROLES:
        raise LibraryError("tell me the layout (split_front_side | grid_2x2 | single) or let analyze detect the divider")
    rects = json.loads(stats["panels_json"]) if stats.get("panels_json") and stats.get("panel_layout") == layout else V.detect_panels(path)["panels"]
    if len(rects) != len(PANEL_ROLES[layout]):
        raise LibraryError(f"the clip shows {len(rects)} panel(s), not a {layout}: run analyze, or name the layout it has")
    ids = []
    with tempfile.TemporaryDirectory(dir=lib.root) as tmp:
        for r, role in zip(rects, PANEL_ROLES[layout]):
            out = Path(tmp) / f"{role.split(':')[1]}.mp4"
            p = V._run(["ffmpeg", "-v", "error", "-nostdin", "-i", path, "-map", "0:v:0", "-map", "0:a?", "-vf", f"crop={r['w']}:{r['h']}:{r['x']}:{r['y']}",
                        "-c:a", "copy", "-pix_fmt", "yuv420p", str(out)], 1800)
            if p.returncode != 0 or not out.exists():
                raise LibraryError(f"cannot crop {path}: {p.stderr.decode(errors='replace').strip()[-300:]}")
            res = lib.put({"kind": "video", "subtype": "split", "name": f"{a['name']} {role.split(':')[1]}", "source": {"kind": "derived", "key": f"{clip}:{role}"},
                           "files": [{"role": "main", "path": str(out), "storage": "cas"}], "attrs": {"rect": r, "of": clip},
                           "relations": [{"type": "part_of", "to": clip, "role": role}, {"type": "derived_from", "to": clip, "role": "panel"}]})
            ids.append(res["id"])
    return {"asset_ids": ids, "layout": layout}


def derive(lib: AssetLibrary, clip: str, what, strip=None, panel_layout=None) -> dict:
    a, path = V.video_asset(lib, clip)
    out = {}
    for w in what:
        if w == "frame_strip":
            out[w] = _strip(lib, clip, a, path, **(strip or {}))
        elif w == "proxy":
            out[w] = _proxy(lib, clip, path)
        elif w == "keyframes":
            out[w] = _keyframes(lib, clip, path)
        elif w == "split_panels":
            out[w] = _panels(lib, clip, a, path, panel_layout)
        elif w == "keypoints_2d":
            raise LibraryError("2D keypoints come from anim_track (its own tool): attach its JSON with attach(role='keypoints_2d')")
        else:
            raise LibraryError(f"unknown derive {w!r}: frame_strip|split_panels|proxy|keyframes (keypoints are attached)")
    return out


def attach(lib: AssetLibrary, clip: str, path, role: str, attrs=None) -> str:
    """Record an artefact another tool made (it stays where that tool wrote it) and link it to the clip the way the contract's table says."""
    V.video_asset(lib, clip)
    if role not in ATTACH:
        raise LibraryError(f"unknown role {role!r}: {sorted(ATTACH)}")
    kind, subtype, rel, direction = ATTACH[role]
    p = Path(path)
    spec = {"kind": kind, "subtype": subtype, "name": p.stem, "source": {"kind": "attached", "key": f"{clip}:{role}:{p}"},
            "files": [{"role": "main", "path": str(p), "storage": "external"}], "attrs": dict(attrs or {})}
    rrole = {"start_frame": "start_frame", "end_frame": "end_frame", "reference": "reference"}.get(role, role if rel == "derived_from" else "")
    if direction == "from":
        spec["relations"] = [{"type": rel, "to": clip, "role": rrole}]
        return lib.put(spec)["id"]
    aid = lib.put(spec)["id"]
    lib.relate(clip, rel, aid, "rule", rrole, {"frame": {"start_frame": "first", "end_frame": "last", "reference": "ref"}[role]} if rel == "generated_from" else None)
    return aid


def _energy(path) -> np.ndarray:
    info = V.probe(path)
    w, h = V._small(info)
    f = V.decode_gray(path, w, h, fps=PROXY_FPS).astype(np.float32)
    return np.concatenate([[0.0], np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))])


def _dtw(x: np.ndarray, y: np.ndarray):
    """Monotone index pairs aligning two motion-energy series (dynamic time warping, absolute difference; O(n m), bounded by the caller's caps)."""
    n, m = len(x), len(y)
    cost = np.full((n + 1, m + 1), np.inf)
    cost[0, 0] = 0.0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost[i, j] = abs(x[i - 1] - y[j - 1]) + min(cost[i - 1, j], cost[i, j - 1], cost[i - 1, j - 1])
    i, j, path = n, m, []
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        step = int(np.argmin([cost[i - 1, j - 1], cost[i - 1, j], cost[i, j - 1]]))
        i, j = (i - 1, j - 1) if step == 0 else (i - 1, j) if step == 1 else (i, j - 1)
    return path[::-1]


def compare(lib: AssetLibrary, a: str, b: str, align: str = "start", max_frames: int = 600) -> dict:
    """Two equally long, monotone lists of proxy frame indices (8 fps) for the UI's side-by-side: ``start`` frame 0 both, ``time`` the same seconds, ``motion`` DTW."""
    pa, pb = V.video_asset(lib, a)[1], V.video_asset(lib, b)[1]
    if align == "motion":
        ea, eb = _energy(pa)[:max_frames], _energy(pb)[:max_frames]
        path = _dtw(ea, eb)
        return {"align": align, "a": [p[0] for p in path], "b": [p[1] for p in path]}
    if align not in ("start", "time"):
        raise LibraryError("align: start|time|motion")
    na, nb = (max(1, int((V.probe(p)["duration_s"] or 0) * PROXY_FPS)) for p in (pa, pb))
    n = min(na, nb, max_frames)
    return {"align": align, "a": list(range(n)), "b": list(range(n))}


def handle(lib: AssetLibrary, req: dict) -> dict:
    """The tool surface (``lampway_asset_video``): probe|analyze|derive|strip|compare -> ``{ok, ...}`` or ``{ok: false, error, help}``."""
    action = req.get("action") or "probe"
    try:
        if action == "probe":
            return {"ok": True, **V.probe(V.video_asset(lib, req["asset_id"])[1] if req.get("asset_id") else req["path"])}
        if action == "analyze":
            return V.analyze(lib, req["asset_id"], req.get("start_s"), req.get("end_s"), req.get("dup_threshold"))
        if action == "derive":
            return {"ok": True, **derive(lib, req["asset_id"], req.get("derive") or [], strip=req.get("strip"), panel_layout=req.get("panel_layout"))}
        if action == "strip":
            return {"ok": True, **derive(lib, req["asset_id"], ["frame_strip"], strip=req.get("strip"))}
        if action == "compare":
            c = req.get("compare") or {}
            return {"ok": True, **compare(lib, c.get("a"), c.get("b"), c.get("align", "start"))}
        raise LibraryError(f"unknown action {action!r}: probe|analyze|derive|strip|compare")
    except (LibraryError, KeyError, TypeError) as e:
        msg = str(e) if isinstance(e, LibraryError) else f"missing or bad field: {e}"
        return {"ok": False, "error": msg, "help": ["analyze {asset_id} first: it records container vs motion fps, holds, blends, panels and audio",
                                                    "derive: frame_strip|split_panels|proxy|keyframes; strip: {count 8..64, size 128..512}"]}
