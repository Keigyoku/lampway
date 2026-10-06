"""The Vault's inspection views, server side (specs/asset_library/asset_ui_views.md section 6): pure functions the editor presents.

- ``lineage_layout``: the assets within ``depth`` relation hops of one asset, layered so every parent sits left of its children (a parent is a relation's ``dst``), ordered
  inside a layer by creation then id, so the same library always gives the same picture; more than ``max_nodes`` (or a hop past ``depth``) is counted as ``collapsed``.
- ``render_lineage`` / ``hit_test``: the layout drawn to a PNG and a click on it mapped back to the asset (the node rects are the same numbers).
- ``image_diff``: |a - b| amplified to a PNG, the mean absolute difference and the mean SSIM over 8 px windows.
- ``view_products``: the derived files an asset has for each view (turntable frames, ball, UV overlay, maps sheet, video proxy frames), by role."""
from __future__ import annotations

from collections import deque
from contextlib import closing
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

NODE_W, NODE_H, GAP_X, GAP_Y, MARGIN = 168, 44, 56, 16, 16
EDGE_COLOURS = {"derived_from": "#8A8A8A", "variant_of": "#5B8DEF", "textured_by": "#4CAF50", "fits_body": "#F29B38", "rigged_to": "#A066D3", "generated_from": "#2BB5A8",
                "drives": "#E0524F", "part_of": "#B0A27A", "uses": "#9AA0A6", "frame_of": "#C7B05A", "supersedes": "#6D6F6C"}
BG, NODE, NODE_LINE, TEXT, FOCUS = (14, 16, 22), (30, 34, 45), (59, 66, 82), (236, 232, 223), (237, 185, 68)


def _neighbours(db, aid):
    return db.execute("SELECT src,dst,type FROM relation WHERE src=? OR dst=? ORDER BY id", (aid, aid)).fetchall()


def lineage_layout(lib, asset_id: str, depth: int = 6, max_nodes: int = 80) -> dict:
    with closing(lib._reader()) as db:
        if not db.execute("SELECT 1 FROM asset WHERE id=?", (asset_id,)).fetchone():
            from .store import LibraryError
            raise LibraryError(f"no asset {asset_id}")
        hops, order, edges, seen_beyond = {asset_id: 0}, [asset_id], set(), set()
        todo = deque([asset_id])
        while todo:
            cur = todo.popleft()
            for src, dst, rtype in _neighbours(db, cur):
                other = dst if src == cur else src
                edges.add((src, dst, rtype))
                if other in hops:
                    continue
                if hops[cur] + 1 > depth or len(order) >= max_nodes:
                    seen_beyond.add(other)
                    continue
                hops[other] = hops[cur] + 1
                order.append(other)
                todo.append(other)
        keep = set(order)
        meta = {r[0]: (r[1], r[2], r[3]) for r in db.execute(f"SELECT id,name,kind,created_at FROM asset WHERE id IN ({','.join('?' * len(keep))})", sorted(keep))}
    edges = sorted(e for e in edges if e[0] in keep and e[1] in keep)
    layer = {a: 0 for a in keep}
    for _ in range(len(keep)):                         # longest path from the roots; bounded, so a cycle in non-derivation edges cannot loop
        changed = False
        for src, dst, _t in edges:
            if layer[src] < layer[dst] + 1:
                layer[src] = layer[dst] + 1
                changed = True
        if not changed:
            break
    nodes, by_layer = [], {}
    for a in sorted(keep, key=lambda a: (layer[a], meta[a][2], a)):
        by_layer.setdefault(layer[a], []).append(a)
    for lv, ids in sorted(by_layer.items()):
        for i, a in enumerate(ids):
            nodes.append({"id": a, "name": meta[a][0], "kind": meta[a][1], "layer": lv, "focus": a == asset_id,
                          "x": MARGIN + lv * (NODE_W + GAP_X), "y": MARGIN + i * (NODE_H + GAP_Y), "w": NODE_W, "h": NODE_H})
    width = MARGIN * 2 + (max(by_layer) + 1) * (NODE_W + GAP_X) - GAP_X
    height = MARGIN * 2 + max(len(v) for v in by_layer.values()) * (NODE_H + GAP_Y) - GAP_Y
    return {"root": asset_id, "nodes": nodes, "edges": [{"src": s, "dst": d, "type": t, "colour": EDGE_COLOURS.get(t, "#9AA0A6")} for s, d, t in edges],
            "collapsed": len(seen_beyond - keep), "width": width, "height": height}


def render_lineage(layout: dict, out_png) -> str:
    im = Image.new("RGB", (layout["width"], layout["height"]), BG)
    draw = ImageDraw.Draw(im)
    rect = {n["id"]: n for n in layout["nodes"]}
    for e in layout["edges"]:
        a, b = rect[e["src"]], rect[e["dst"]]                     # parent (dst) on the left, child (src) on the right
        draw.line([(b["x"] + b["w"], b["y"] + b["h"] // 2), (a["x"], a["y"] + a["h"] // 2)], fill=e["colour"], width=2)
    for n in layout["nodes"]:
        draw.rectangle([n["x"], n["y"], n["x"] + n["w"] - 1, n["y"] + n["h"] - 1], fill=NODE, outline=FOCUS if n["focus"] else NODE_LINE, width=2)
        draw.text((n["x"] + 8, n["y"] + 6), str(n["name"])[:24], fill=TEXT)
        draw.text((n["x"] + 8, n["y"] + 24), str(n["kind"]), fill=NODE_LINE if not n["focus"] else FOCUS)
    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    im.save(out_png)
    return str(out_png)


def hit_test(layout: dict, x: float, y: float):
    for n in layout["nodes"]:
        if n["x"] <= x < n["x"] + n["w"] and n["y"] <= y < n["y"] + n["h"]:
            return n["id"]
    return None


def _ssim(a: np.ndarray, b: np.ndarray, win: int = 8) -> float:
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    h, w = (a.shape[0] // win) * win, (a.shape[1] // win) * win
    if not h or not w:
        return 1.0 if np.array_equal(a, b) else 0.0
    def blocks(x):
        return x[:h, :w].reshape(h // win, win, w // win, win).transpose(0, 2, 1, 3).reshape(-1, win * win)
    pa, pb = blocks(a), blocks(b)
    ma, mb = pa.mean(1), pb.mean(1)
    va, vb = pa.var(1), pb.var(1)
    cov = ((pa - ma[:, None]) * (pb - mb[:, None])).mean(1)
    return float(np.mean(((2 * ma * mb + c1) * (2 * cov + c2)) / ((ma ** 2 + mb ** 2 + c1) * (va + vb + c2))))


def image_diff(a_path, b_path, out_png, gain: float = 4.0) -> dict:
    a = np.asarray(Image.open(a_path).convert("RGB"), dtype=np.float64)
    b = np.asarray(Image.open(b_path).convert("RGB").resize((a.shape[1], a.shape[0])), dtype=np.float64)
    d = np.abs(a - b)
    Image.fromarray(np.clip(d * gain, 0, 255).astype(np.uint8)).save(out_png)
    lum = lambda x: x @ np.array([0.2126, 0.7152, 0.0722])  # noqa: E731
    return {"ssim": round(_ssim(lum(a), lum(b)), 6), "mean_abs": round(float(d.mean()), 6), "diff": str(out_png)}


def view_products(lib, asset_id: str, version=None) -> dict:
    rec = lib.get(asset_id, version)
    def present(f):
        return next((loc["path"] for loc in f["locations"] if not loc["missing"] and Path(loc["path"]).is_file()), None)
    by_role = {f["role"]: present(f) for f in rec["files"]}
    turns = sorted(((int(r.split(":", 1)[1]), p) for r, p in by_role.items() if r.startswith("turntable:") and p and r.split(":", 1)[1].isdigit()))
    vid = lib.version_of(asset_id, rec["version"])
    proxy = sorted(str(p) for p in (lib.root / "derived" / vid / "proxy").glob("*.jpg"))
    return {"turntable": [p for _, p in turns], "ball": by_role.get("ball"), "overlay": by_role.get("overlay"), "sheet": by_role.get("sheet"),
            "thumb": by_role.get("thumb"), "proxy": proxy, "strip": by_role.get("strip")}


MOTION_THRESHOLD = 8.0        # mean absolute grey-level change between two proxy frames that counts as motion [UNVERIFIED: chosen, not calibrated]


def _onset(frames: list) -> int:
    """The last still frame before the first change above MOTION_THRESHOLD (0 when the clip moves from the start or never moves)."""
    prev = None
    for i, p in enumerate(frames):
        cur = np.asarray(Image.open(p).convert("L").resize((32, 32)), dtype=np.float64)
        if prev is not None and np.abs(cur - prev).mean() > MOTION_THRESHOLD:
            return i - 1
        prev = cur
    return 0


def clip_align(frames_a: list, frames_b: list, mode: str = "start", fps_a: float = 8.0, fps_b: float = 8.0) -> dict:
    """Two clips' proxy frames as equal-length lists for one scrub bar (asset_ui_views 5, compare): ``start`` pairs frame 0 with frame 0; ``time`` pairs by timestamp at the
    faster rate (the slower clip's frames repeat); ``motion`` starts each clip at its last still frame before it first moves."""
    if mode not in ("start", "time", "motion"):
        raise ValueError("mode is start, time or motion")
    oa = ob = 0
    if mode == "time":
        rate = max(fps_a, fps_b)
        n = int(min(len(frames_a) / fps_a, len(frames_b) / fps_b) * rate)
        a = [frames_a[min(len(frames_a) - 1, int(k * fps_a / rate))] for k in range(n)]
        b = [frames_b[min(len(frames_b) - 1, int(k * fps_b / rate))] for k in range(n)]
        return {"mode": mode, "a": a, "b": b, "offset": {"a": 0, "b": 0}, "fps": rate}
    if mode == "motion":
        oa, ob = _onset(frames_a), _onset(frames_b)
    a, b = frames_a[oa:], frames_b[ob:]
    n = min(len(a), len(b))
    return {"mode": mode, "a": a[:n], "b": b[:n], "offset": {"a": oa, "b": ob}, "fps": fps_a}
