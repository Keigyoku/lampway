# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Deterministic chroma matting of generated plates (STATUS O34), ported from the astra-1 shelf's image-matte tool v1.2.0 (key_rgba, sheet_cells,
center_rgba, the atomic batch publish and its manifest) with two changes the spike's findings asked for:

* the KEY is read from the image's own border ring (a generated "magenta" is never exactly #FF00FF): its colour is the ring's median, used to
  unmix the edge pixels (C = coverage * F + (1 - coverage) * key), and the clear threshold drops to the ring's own score when the background is
  duller than the shelf's fixed 220, so the background is cleared whatever magenta the generator painted;
* the arithmetic is the shelf's integer arithmetic vectorised in numpy (same floor divisions), so the shelf's golden holds bit for bit.

A threshold key cannot tell genuine magenta foreground from background (an enclosed magenta region is keyed too). PNG input must be 8-bit RGB or
RGBA, non-interlaced, at most 16 million pixels: anything else is refused, never converted. Output PNGs are written by one encoder (filter 0,
zlib level 9), so a repeat run is byte-identical on the same zlib. Integer shifts only; nothing is ever resampled."""

import hashlib
import io
import json
import os
import shutil
import struct
import tempfile
import zlib
from pathlib import Path

import numpy as np

VERSION = "lampway-1.0 (shelf 1.2.0)"
LAYOUTS = {"3x2": (3, 2, ["Front", "Right", "Back", "Left", "Top", "Bottom"]),
           "2x2": (2, 2, ["Front", "Left", "Back", "Right"])}
SIGNATURE = b"\x89PNG\r\n\x1a\n"
COLOR_CHUNKS = {b"cHRM", b"gAMA", b"iCCP", b"sRGB", b"pHYs"}
IDEAL = {"magenta": (255, 0, 255), "white": (255, 255, 255)}
DEFAULTS = {"magenta": (20, 220), "white": (200, 245)}       # (opaque, clear) on the key score
RING_PX = 4                    # the border ring the key is read from
RING_CANDIDATE = {"magenta": 96, "white": 180}               # a ring pixel scoring at least this is background
RING_MIN_FRACTION = 0.25       # under this share of key in the ring, the background is not this key: refused
CLEAR_MIN_GAP = 40             # the ring-derived clear stays this far above opaque, or the image is refused
LIGHT, DARK = 235, 25          # the verification contact sheet's two backgrounds


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _chunks(raw):
    """Walk and validate every chunk (CRC, order, no animation, no trailing bytes); returns (IHDR fields, colour chunks)."""
    if not raw.startswith(SIGNATURE):
        raise ValueError("input is not PNG")
    pos, header, metadata, ended, idat, trns = 8, None, [], False, False, None
    while pos < len(raw):
        if pos + 12 > len(raw):
            raise ValueError("truncated PNG chunk")
        size = struct.unpack_from(">I", raw, pos)[0]
        kind = raw[pos + 4:pos + 8]
        end = pos + 12 + size
        if end > len(raw):
            raise ValueError("truncated PNG data")
        data = raw[pos + 8:pos + 8 + size]
        if zlib.crc32(kind + data) & 0xffffffff != struct.unpack_from(">I", raw, pos + 8 + size)[0]:
            raise ValueError("PNG CRC mismatch")
        if kind == b"IHDR":
            if header is not None or pos != 8 or size != 13:
                raise ValueError("invalid PNG header")
            header = struct.unpack(">IIBBBBB", data)
        elif kind == b"IDAT":
            if header is None:
                raise ValueError("IDAT before header")
            idat = True
        elif kind == b"IEND":
            if size:
                raise ValueError("invalid IEND")
            ended, pos = True, end
            break
        elif kind == b"tRNS":
            trns = data
        elif kind in COLOR_CHUNKS:
            metadata.append((kind, data))
        elif kind in (b"acTL", b"fcTL", b"fdAT"):
            raise ValueError("animated PNG unsupported")
        elif not kind[0] & 32 and kind != b"PLTE":
            raise ValueError("unsupported PNG critical chunk")
        pos = end
    if not ended or header is None or not idat or pos != len(raw):
        raise ValueError("incomplete PNG or trailing data")
    w, h, depth, color, compression, filtering, interlace = header
    if not 0 < w <= 16384 or not 0 < h <= 16384 or w * h > 16_000_000:
        raise ValueError("PNG exceeds 16 million pixel limit")
    if depth != 8 or color not in (2, 6) or compression or filtering or interlace:
        raise ValueError("requires non-interlaced RGB/RGBA 8-bit PNG")
    if trns is not None and (color != 2 or len(trns) != 6):
        raise ValueError("invalid RGB transparency")
    return (w, h, color, trns), metadata


def decode_png(raw):
    """(width, height, straight RGBA8 bytes, colour chunks); the chunk walk validates, PIL decodes the validated stream."""
    from PIL import Image
    (w, h, color, trns), metadata = _chunks(raw)
    im = Image.open(io.BytesIO(raw))
    im.load()
    a = np.asarray(im.convert("RGBA") if color == 6 else im.convert("RGB"), dtype=np.uint8)
    if color == 2:
        alpha = np.full((h, w, 1), 255, np.uint8)
        if trns is not None:
            key = struct.unpack(">HHH", trns)
            alpha[np.all(a == np.array(key, np.uint16).astype(np.uint8), axis=2)] = 0
        a = np.concatenate([a, alpha], axis=2)
    if a.shape != (h, w, 4):
        raise ValueError("decoded size does not match the header")
    return w, h, a.tobytes(), metadata


def _chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)


def encode_png(w, h, rgba, metadata=()):
    if w <= 0 or h <= 0 or len(rgba) != w * h * 4:
        raise ValueError("invalid RGBA dimensions")
    rows = b"".join(b"\0" + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))
    return (SIGNATURE + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) +
            b"".join(_chunk(k, d) for k, d in metadata if k in COLOR_CHUNKS) +
            _chunk(b"IDAT", zlib.compress(rows, 9)) + _chunk(b"IEND", b""))


def _score(px, background):
    r, g, b = px[:, 0], px[:, 1], px[:, 2]
    return np.minimum(r, b) - g if background == "magenta" else np.minimum(np.minimum(r, g), b)


def border_key(w, h, rgba, background="magenta", opaque=None):
    """The key read from the border ring: colour = median of the ring's background pixels, clear = the shelf's default or, when the ring is duller,
    its 5th-percentile score. Refused when the ring is not mostly this background."""
    a = np.frombuffer(rgba, np.uint8).reshape(h, w, 4).astype(np.int64)
    k = min(RING_PX, w // 2 or 1, h // 2 or 1)
    ring = np.zeros((h, w), bool)
    ring[:k], ring[-k:], ring[:, :k], ring[:, -k:] = True, True, True, True
    px = a[ring]
    px = px[px[:, 3] > 0]
    s = _score(px, background)
    cand = s >= RING_CANDIDATE[background]
    frac = float(cand.mean()) if len(s) else 0.0
    if frac < RING_MIN_FRACTION:
        raise ValueError(f"no clear {background} on the border ({frac:.0%} of the ring): wrong background or settings")
    key = [int(v) for v in np.median(px[cand][:, :3], axis=0).round()]
    op = DEFAULTS[background][0] if opaque is None else opaque
    clear = min(DEFAULTS[background][1], int(np.percentile(s[cand], 5)))
    if clear - op < CLEAR_MIN_GAP:
        raise ValueError(f"the ring's {background} scores {clear}, too close to opaque {op}: the key cannot separate foreground from background")
    return {"key_rgb": key, "clear": clear, "ring_fraction": round(frac, 4), "ring_px": k}


def key_rgba(w, h, rgba, opaque=20, clear=220, despill=True, *, background="magenta", key_rgb=None):
    """The shelf's key: score min(R,B)-G (white: min(R,G,B)); integer soft alpha; optional unmix of the key colour (key_rgb, default the
    ideal) with the complementary-green clamp. Pixels outside the transition keep their colour; transparent ones become 0000; alpha never rises."""
    if background not in IDEAL:
        raise ValueError("background must be magenta or white")
    if not isinstance(opaque, int) or not isinstance(clear, int) or not 0 <= opaque < clear <= 255:
        raise ValueError("require 0 <= opaque < clear <= 255")
    if w <= 0 or h <= 0 or len(rgba) != w * h * 4:
        raise ValueError("invalid RGBA dimensions")
    kr, kg, kb = key_rgb or IDEAL[background]
    px = np.frombuffer(rgba, np.uint8).reshape(-1, 4).astype(np.int64)
    r, g, b, a = px[:, 0], px[:, 1], px[:, 2], px[:, 3]
    span = clear - opaque
    score = _score(px, background)
    weight = np.clip(clear - score, 0, span)
    alpha = (a * weight + span // 2) // span
    out = px.copy()
    out[:, 3] = alpha
    part = (alpha > 0) & (weight < span)
    if despill and part.any():
        wt = weight[part]
        inv = span - wt
        un = lambda c, k: np.clip((c[part] * span - k * inv + wt // 2) // wt, 0, 255)
        nr, ng, nb = un(r, kr), un(g, kg), un(b, kb)
        if background == "magenta":
            ng = np.minimum(ng, np.maximum(nr, nb))
        out[part, 0], out[part, 1], out[part, 2] = nr, ng, nb
    out[alpha == 0] = 0
    o8 = out.astype(np.uint8)
    idx = np.arange(len(px))
    y, x = idx // w, idx % w
    border = (x == 0) | (y == 0) | (x == w - 1) | (y == h - 1)
    counts = {"transparent": int((alpha == 0).sum()), "partial": int(((alpha > 0) & (alpha < 255)).sum()), "opaque": int((alpha == 255).sum()),
              "changed_pixels": int(np.any(o8 != px.astype(np.uint8), axis=1).sum()),
              "border_key_pixels": int((border & (score >= clear) & (a > 0)).sum())}
    return o8.tobytes(), counts


def _rect(rect, w, h):
    if (not isinstance(rect, list) or len(rect) != 4 or any(type(v) is not int for v in rect)
            or not 0 <= rect[0] < rect[2] <= w or not 0 <= rect[1] < rect[3] <= h):
        raise ValueError("rectangle must be [x0,y0,x1,y1], integer half-open bounds inside source")
    return rect


def sheet_cells(w, h, split=None, x_cuts=None, y_cuts=None, row_x_cuts=None):
    """Partition the source exactly once (shelf); never scale or invent a view."""
    if split is None:
        if x_cuts is not None or y_cuts is not None or row_x_cuts is not None:
            raise ValueError("cuts require split layout")
        return [(None, [0, 0, w, h])]
    if not isinstance(split, str) or split not in LAYOUTS:
        raise ValueError("split must be 3x2 or 2x2")
    cols, rows, names = LAYOUTS[split]

    def cuts(values, size, count):
        if values is None:
            values = [size * i // count for i in range(1, count)]
        if not isinstance(values, list) or len(values) != count - 1 or any(type(v) is not int for v in values):
            raise ValueError("cut count/type does not match layout")
        bounds = [0, *values, size]
        if any(p >= q for p, q in zip(bounds, bounds[1:])):
            raise ValueError("cuts must increase strictly inside source")
        return bounds
    ys = cuts(y_cuts, h, rows)
    if row_x_cuts is not None:
        if x_cuts is not None or not isinstance(row_x_cuts, list) or len(row_x_cuts) != rows:
            raise ValueError("row_x_cuts requires one cut list per row and no x_cuts")
        xs = [cuts(row, w, cols) for row in row_x_cuts]
    else:
        xs = [cuts(x_cuts, w, cols)] * rows
    return [(names[y * cols + x], [xs[y][x], ys[y], xs[y][x + 1], ys[y + 1]]) for y in range(rows) for x in range(cols)]


def crop_rgba(w, rgba, rect):
    x0, y0, x1, y1 = rect
    return b"".join(rgba[(y * w + x0) * 4:(y * w + x1) * 4] for y in range(y0, y1))


def _batch_paths(source, destination):
    """Separate, non-nested, symlink-free paths; the PNG inventory (shelf)."""
    source, destination = Path(source).absolute(), Path(destination).absolute()
    for p in (source, destination):
        if any(q.is_symlink() for q in (p, *p.parents)):
            raise ValueError("symlink paths are not supported")
    source, destination = source.resolve(), destination.resolve()
    if not source.exists():
        raise ValueError("input does not exist")
    if destination.exists():
        raise ValueError("output already exists; choose a new versioned directory")
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("input/output must be separate, non-nested paths")
    base = source if source.is_dir() else source.parent
    if source.is_dir():
        entries = sorted(source.rglob("*"))
        if any(p.is_symlink() for p in entries):
            raise ValueError("input tree contains symlink")
        files = [p for p in entries if p.is_file() and p.suffix.lower() == ".png"]
    else:
        files = [source] if source.suffix.lower() == ".png" else []
    if not files:
        raise ValueError("no PNG input files")
    return base, files, destination


def _publish(destination, write):
    """Stage beside the destination, then one rename: a failed batch leaves nothing behind."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".image-matte-", dir=destination.parent))
    try:
        write(stage)
        if destination.exists():
            raise ValueError("output appeared during processing")
        os.rename(stage, destination)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _write_manifest(stage, manifest):
    (stage / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")


def remove(source, destination, opaque=None, clear=None, despill=True, *, background="magenta", key="border", split=None, sheet_recipe=None):
    """Key every PNG under source into a NEW directory with a manifest of settings and hashes. key=border reads the key colour and clear threshold
    from each image's ring; key=ideal is the shelf's literal key. A sheet recipe ({schema: 1, images: {name: {sha256?, size?, split, x_cuts,
    y_cuts, row_x_cuts, erase, background, opaque, clear}}}) must name exactly the input inventory."""
    if key not in ("border", "ideal"):
        raise ValueError("key is border (read from the image's ring) or ideal (the literal key colour)")
    base, files, destination = _batch_paths(source, destination)
    profiles, recipe_hash = {}, None
    if sheet_recipe:
        recipe_raw = Path(sheet_recipe).read_bytes()
        recipe_hash, recipe = _sha(recipe_raw), json.loads(recipe_raw)
        if not isinstance(recipe, dict) or set(recipe) != {"schema", "images"} or recipe["schema"] != 1 or not isinstance(recipe["images"], dict):
            raise ValueError("sheet recipe requires schema:1 and images mapping")
        profiles = recipe["images"]
        if set(profiles) != {p.relative_to(base).as_posix() for p in files}:
            raise ValueError("recipe image names must exactly match input PNG inventory")
    records = []

    def write(stage):
        for path in files:
            raw = path.read_bytes()
            w, h, rgba, metadata = decode_png(raw)
            relative = path.relative_to(base)
            profile = profiles.get(relative.as_posix(), {})
            if not isinstance(profile, dict) or set(profile) - {"sha256", "size", "split", "background", "opaque", "clear", "x_cuts", "y_cuts", "row_x_cuts", "erase"}:
                raise ValueError("unknown sheet recipe field or invalid profile")
            if "sha256" in profile and profile["sha256"] != _sha(raw):
                raise ValueError(f"{relative}: recipe source hash mismatch")
            if "size" in profile and profile["size"] != [w, h]:
                raise ValueError(f"{relative}: recipe dimensions mismatch")
            bg = profile.get("background", background)
            if bg not in IDEAL:
                raise ValueError("background must be magenta or white")
            op = profile.get("opaque", opaque)
            op = DEFAULTS[bg][0] if op is None else op
            cl = profile.get("clear", clear)
            ring = border_key(w, h, rgba, bg, op) if key == "border" else None
            if cl is None:
                cl = ring["clear"] if ring else DEFAULTS[bg][1]
            krgb = tuple(ring["key_rgb"]) if ring else IDEAL[bg]
            cells = sheet_cells(w, h, profile.get("split", split), profile.get("x_cuts"), profile.get("y_cuts"), profile.get("row_x_cuts"))
            erase = profile.get("erase", [])
            if not isinstance(erase, list):
                raise ValueError("erase must be a list of rectangles")
            for rect in erase:
                _rect(rect, w, h)
            result, stats = key_rgba(w, h, rgba, op, cl, despill, background=bg, key_rgb=krgb)
            if stats["border_key_pixels"] == 0:
                raise ValueError(f"{relative}: no clear {bg} on the border; wrong background or settings")
            if stats["transparent"] == w * h:
                raise ValueError(f"{relative}: key removed entire image")
            result = bytearray(result)
            for x0, y0, x1, y1 in erase:
                for y in range(y0, y1):
                    result[(y * w + x0) * 4:(y * w + x1) * 4] = bytes((x1 - x0) * 4)
            result = bytes(result)
            for view, rect in cells:
                cw, ch = rect[2] - rect[0], rect[3] - rect[1]
                pixels = crop_rgba(w, result, rect)
                if not any(pixels[3::4]):
                    raise ValueError(f"{relative}: empty view after key/erase: {view}")
                output = encode_png(cw, ch, pixels, metadata)
                out_rel = relative if view is None else relative.with_suffix("") / (view + ".png")
                target = stage / out_rel
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    raise ValueError(f"output filename collision: {out_rel}")
                target.write_bytes(output)
                al = pixels[3::4]
                records.append({"file": out_rel.as_posix(), "source": relative.as_posix(), "width": cw, "height": ch, "source_rect": rect, "erase": erase,
                                "view": view, "settings": {"background": bg, "opaque": op, "clear": cl, "despill": despill, "key": key, "key_rgb": list(krgb),
                                                           "ring": ring},
                                "source_sha256": _sha(raw), "output_sha256": _sha(output), "rgba_sha256": _sha(pixels),
                                "transparent": al.count(0), "opaque": al.count(255), "partial": cw * ch - al.count(0) - al.count(255), "source_key_stats": stats})
        _write_manifest(stage, {"schema": 2, "tool": "image-matte", "operation": "remove", "version": VERSION, "recipe_sha256": recipe_hash,
                                "settings": {"background": background, "opaque": opaque, "clear": clear, "despill": despill, "key": key, "split": split},
                                "scope": "deterministic chroma key, not semantic segmentation", "images": records})
    _publish(destination, write)
    return {"output": str(destination), "images": len(records), "manifest": str(destination / "manifest.json"), "verdict": "PASS",
            "scope": "files converted; edge acceptance needs the light/dark review (verify)"}


def alpha_bounds(w, h, rgba):
    """Half-open bounds of EVERY nonzero alpha, the one-level fringe included."""
    al = np.frombuffer(rgba, np.uint8)[3::4].reshape(h, w)
    ys, xs = np.nonzero(al)
    if not len(xs):
        raise ValueError("cannot center an empty alpha image")
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def center_rgba(w, h, rgba, canvas_size=None):
    """Integer translation onto a transparent canvas; no filtering or resampling (shelf)."""
    if canvas_size is not None and (type(canvas_size) is not int or not 0 < canvas_size <= 4000):
        raise ValueError("canvas size must be an integer from 1 to 4000")
    ow, oh = (w, h) if canvas_size is None else (canvas_size, canvas_size)
    box = alpha_bounds(w, h, rgba)
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    if bw > ow or bh > oh:
        raise ValueError("canvas is too small for foreground; resizing is never applied")
    left, top = (ow - bw) // 2, (oh - bh) // 2
    out = bytearray(ow * oh * 4)
    for y in range(bh):
        out[((top + y) * ow + left) * 4:((top + y) * ow + left + bw) * 4] = rgba[((y0 + y) * w + x0) * 4:((y0 + y) * w + x1) * 4]
    return ow, oh, bytes(out), {"source_bbox": box, "output_bbox": [left, top, left + bw, top + bh], "translation": [left - x0, top - y0],
                                "resampled": False, "content_sha256": _sha(crop_rgba(w, rgba, box))}


def center(source, destination, canvas_size=None):
    """Centre transparent PNGs without keying them again. canvas_size: None (each keeps its size), an integer square, or "common": the smallest
    square that holds every plate's foreground, so a set lands on matching canvases."""
    base, files, destination = _batch_paths(source, destination)
    decoded = [(p, p.read_bytes()) for p in files]
    decoded = [(p, raw, *decode_png(raw)) for p, raw in decoded]
    if canvas_size == "common":
        boxes = [alpha_bounds(w, h, rgba) for _, _, w, h, rgba, _ in decoded]
        canvas_size = max(max(b[2] - b[0], b[3] - b[1]) for b in boxes)
    records = []

    def write(stage):
        for path, raw, w, h, rgba, metadata in decoded:
            ow, oh, pixels, geometry = center_rgba(w, h, rgba, canvas_size)
            encoded = encode_png(ow, oh, pixels, metadata)
            relative = path.relative_to(base)
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(encoded)
            records.append({"file": relative.as_posix(), "source": relative.as_posix(), "source_size": [w, h], "width": ow, "height": oh,
                            "source_sha256": _sha(raw), "output_sha256": _sha(encoded), "rgba_sha256": _sha(pixels), **geometry})
        _write_manifest(stage, {"schema": 1, "tool": "image-matte", "version": VERSION, "operation": "center",
                                "settings": {"canvas_size": canvas_size, "bounds": "alpha > 0", "resampled": False}, "images": records})
    _publish(destination, write)
    return {"output": str(destination), "images": len(records), "manifest": str(destination / "manifest.json"), "verdict": "PASS",
            "canvas_size": canvas_size, "scope": "alpha bounds centred; original foreground pixels preserved"}


def _thumb(w, h, rgba, side, bg):
    a = np.frombuffer(rgba, np.uint8).reshape(h, w, 4).astype(np.int64)
    s = max(w, h) / side
    ys = np.minimum((np.arange(side) * s).astype(int), h - 1)
    xs = np.minimum((np.arange(side) * s).astype(int), w - 1)
    t = a[ys][:, xs]
    inside = (np.arange(side)[:, None] * s < h) & (np.arange(side)[None, :] * s < w)
    al = np.where(inside, t[:, :, 3], 0)[:, :, None]
    rgb = (t[:, :, :3] * al + bg * (255 - al) + 127) // 255
    return np.concatenate([rgb, np.full((side, side, 1), 255)], axis=2).astype(np.uint8)


def verify(output, source, verify_out, thumb=160):
    """The verification pass over a published directory: every PNG decodes with valid CRCs; its file and pixel hashes equal the manifest's; every
    source still hashes as recorded; a keyed image kept every non-key source pixel exactly; a centred one kept its foreground bytes; files whose
    border is not fully transparent are NAMED (a foreground touching the frame), and a light/dark contact sheet is written for the edge review."""
    output, verify_out = Path(output), Path(verify_out)
    if verify_out.exists():
        raise ValueError("verify output already exists; choose a new directory")
    manifest = json.loads((output / "manifest.json").read_text())
    src_base = Path(source) if Path(source).is_dir() else Path(source).parent
    failures, border, rows, unchanged, hashes = [], [], [], True, True
    on_disk = sorted(p.relative_to(output).as_posix() for p in output.rglob("*.png"))
    listed = sorted(r["file"] for r in manifest["images"])
    if on_disk != listed:
        failures.append({"file": "*", "error": f"PNG set differs from the manifest: extra {sorted(set(on_disk) - set(listed))}, missing {sorted(set(listed) - set(on_disk))}"})
    for r in manifest["images"]:
        try:
            raw = (output / r["file"]).read_bytes()
            w, h, rgba, _ = decode_png(raw)
            if _sha(raw) != r["output_sha256"] or _sha(rgba) != r["rgba_sha256"]:
                hashes = False
                failures.append({"file": r["file"], "error": "file or pixel hash differs from the manifest"})
                continue
            sraw = (src_base / r["source"]).read_bytes()
            if _sha(sraw) != r["source_sha256"]:
                unchanged = False
                failures.append({"file": r["file"], "error": "the source changed since the run"})
                continue
            sw, sh, srgba, _ = decode_png(sraw)
            if manifest.get("operation") == "center":
                if crop_rgba(w, rgba, r["output_bbox"]) != crop_rgba(sw, srgba, r["source_bbox"]):
                    failures.append({"file": r["file"], "error": "the centred foreground differs from the source"})
            else:
                st = r["settings"]
                src = np.frombuffer(crop_rgba(sw, srgba, r["source_rect"]), np.uint8).reshape(-1, 4)
                out = np.frombuffer(rgba, np.uint8).reshape(-1, 4)
                er = np.zeros((h, w), bool)
                for x0, y0, x1, y1 in r.get("erase") or []:
                    rx0, ry0 = r["source_rect"][0], r["source_rect"][1]
                    er[max(0, y0 - ry0):max(0, y1 - ry0), max(0, x0 - rx0):max(0, x1 - rx0)] = True
                keep = (_score(src.astype(np.int64), st["background"]) <= st["opaque"]) & (src[:, 3] > 0) & ~er.ravel()
                if not np.array_equal(out[keep], src[keep]):
                    failures.append({"file": r["file"], "error": "a non-key source pixel changed"})
            al = np.frombuffer(rgba, np.uint8)[3::4].reshape(h, w)
            if al[0].any() or al[-1].any() or al[:, 0].any() or al[:, -1].any():
                border.append(r["file"])
            rows.append(np.concatenate([_thumb(w, h, rgba, thumb, LIGHT), _thumb(w, h, rgba, thumb, DARK)], axis=1))
        except (OSError, ValueError) as exc:
            failures.append({"file": r["file"], "error": str(exc)})
    verify_out.mkdir(parents=True)
    sheet_path = None
    if rows:
        sheet = np.concatenate(rows, axis=0)
        sheet_path = verify_out / "contact_sheet.png"
        sheet_path.write_bytes(encode_png(sheet.shape[1], sheet.shape[0], sheet.tobytes()))
    report = {"verdict": "FAIL" if failures else "PASS", "images": len(manifest["images"]), "failures": failures, "hashes_match": hashes,
              "sources_unchanged": unchanged, "nonzero_alpha_border": border, "contact_sheet": str(sheet_path) if sheet_path else None,
              "contact_sheet_rows": [r["file"] for r in manifest["images"]], "backgrounds": [LIGHT, DARK],
              "note": "the contact sheet is the edge review: a fringe shows on one of the two backgrounds; a border listed here is a foreground touching the frame"}
    (verify_out / "checks.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    return report
