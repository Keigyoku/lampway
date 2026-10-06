# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""image_matte (STATUS O34; ported from the astra-1 shelf's image-matte tool v1.2.0, behaviour pinned by its tests): a deterministic chroma key
to transparent RGBA (integer soft coverage, despill by unmixing the KEY colour, enclosed holes keyed), the key colour and the clear threshold
read from the image's own border ring (a generated "magenta" is never exactly #FF00FF), batch publishing with a manifest of settings and
hashes, sheet splitting (2x2, 3x2, cuts, erase rectangles), centring on a common canvas by integer shifts, and the verification pass."""

import hashlib
import io
import json
import struct
import sys
import zlib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.pipeline import image_matte as M  # noqa: E402

IDEAL = (255, 0, 255)


def png(arr):
    b = io.BytesIO(); Image.fromarray(np.asarray(arr, dtype=np.uint8)).save(b, "PNG"); return b.getvalue()


def plate(w=40, h=30, bg=(247, 3, 251), fg=(150, 80, 30), box=(10, 8, 30, 22), hole=None):
    a = np.zeros((h, w, 3), np.uint8); a[:] = bg
    x0, y0, x1, y1 = box; a[y0:y1, x0:x1] = fg
    if hole:
        hx0, hy0, hx1, hy1 = hole; a[hy0:hy1, hx0:hx1] = bg
    return a


def test_the_shelf_golden_holds_with_the_ideal_key():
    pixels = bytes([247, 3, 251, 255, 150, 90, 40, 255, 130, 10, 15, 255, 128, 0, 128, 255])
    out, stats = M.key_rgba(4, 1, pixels, key_rgb=IDEAL)
    assert out.hex() == "00000000965a28ff820a0fff00000075"
    assert (stats["transparent"], stats["partial"], stats["opaque"]) == (1, 1, 2)


def test_existing_alpha_never_increases_and_enclosed_holes_are_keyed():
    out, _ = M.key_rgba(3, 1, bytes([150, 90, 40, 64, 128, 0, 128, 128, 9, 9, 9, 0]), key_rgb=IDEAL)
    assert out[:4] == bytes([150, 90, 40, 64]) and out[7] < 128 and out[-4:] == bytes(4)
    px = bytes([150, 80, 30, 255] * 9); px = px[:16] + bytes([245, 2, 250, 255]) + px[20:]
    out, _ = M.key_rgba(3, 3, px, key_rgb=IDEAL)
    assert out[16:20] == bytes(4) and out[:16] == px[:16] and out[20:] == px[20:]


def test_the_key_is_read_from_the_border_ring_not_assumed():
    a = plate(bg=(214, 28, 205))                                  # a generated magenta: its key score 177 is under the shelf's fixed clear 220
    k = M.border_key(a.shape[1], a.shape[0], np.dstack([a, np.full(a.shape[:2], 255, np.uint8)]).tobytes())
    assert k["key_rgb"] == [214, 28, 205] and k["clear"] <= 177 and k["ring_fraction"] > 0.9, k
    fixed, _ = M.key_rgba(a.shape[1], a.shape[0], np.dstack([a, np.full(a.shape[:2], 255, np.uint8)]).tobytes(), 20, 220, key_rgb=IDEAL)
    assert np.frombuffer(fixed, np.uint8)[3::4].min() > 0, "with the literal key and threshold this background is never fully cleared"


def test_despill_unmixes_the_measured_key_without_a_green_fringe():
    # the key score is linear in coverage between the foreground's score (20 = opaque) and the background's (177 = clear), so the unmix is exact
    # up to rounding when the key colour is the one the generator painted
    bg, fg = np.array([214, 28, 205]), np.array([150, 60, 80])
    mix = (0.5 * fg + 0.5 * bg).round().astype(np.uint8)          # a half-covered edge pixel over the real background
    px = bytes([*mix, 255])
    measured, _ = M.key_rgba(1, 1, px, 20, 177, key_rgb=tuple(bg))
    ideal, _ = M.key_rgba(1, 1, px, 20, 177, key_rgb=IDEAL)
    err = lambda o: np.abs(np.array(list(o[:3]), int) - fg).max()
    assert err(measured) <= 3 < err(ideal), (list(measured), list(ideal))
    assert measured[1] <= max(measured[0], measured[2])


def _tree(tmp_path, **imgs):
    src = tmp_path / "src"; src.mkdir(parents=True)
    for name, arr in imgs.items():
        (src / f"{name}.png").write_bytes(png(arr))
    return src


def test_remove_publishes_a_manifest_and_is_byte_deterministic_and_sources_are_untouched(tmp_path):
    src = _tree(tmp_path, Helmet=plate(), Sandal=plate(fg=(20, 20, 20), hole=(14, 12, 18, 16)))
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in src.iterdir()}
    r1 = M.remove(src, tmp_path / "a"); r2 = M.remove(src, tmp_path / "b")
    assert r1["images"] == 2 and r1["verdict"] == "PASS"
    for name in ("Helmet.png", "Sandal.png", "manifest.json"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes(), name
    assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in src.iterdir()}
    man = json.loads((tmp_path / "a" / "manifest.json").read_text())
    rec = {r["file"]: r for r in man["images"]}
    assert rec["Helmet.png"]["settings"]["key_rgb"] == [247, 3, 251] and rec["Helmet.png"]["source_sha256"] == before["Helmet.png"]
    out = np.asarray(Image.open(tmp_path / "a" / "Sandal.png"))
    assert out.shape == (30, 40, 4) and out[13, 15, 3] == 0 and out[9, 11, 3] == 255 and out[0, 0, 3] == 0, "the enclosed hole is keyed"
    with pytest.raises(ValueError, match="already exists"):
        M.remove(src, tmp_path / "a")
    with pytest.raises(ValueError, match="non-nested"):
        M.remove(src, src / "out")


def test_wrong_background_or_an_all_key_image_is_refused(tmp_path):
    grey = np.full((20, 20, 3), 128, np.uint8)
    with pytest.raises(ValueError, match="border"):
        M.remove(_tree(tmp_path, Grey=grey), tmp_path / "o")
    with pytest.raises(ValueError, match="entire image"):
        M.remove(_tree(tmp_path / "x", Key=np.dstack([np.full((20, 20), 247), np.full((20, 20), 3), np.full((20, 20), 251)]).astype(np.uint8)), tmp_path / "o2")


def test_an_unsupported_png_is_refused_not_converted(tmp_path):
    b = io.BytesIO(); Image.fromarray(np.full((8, 8), 7, np.uint8), "L").save(b, "PNG")
    with pytest.raises(ValueError, match="RGB/RGBA 8-bit"):
        M.decode_png(b.getvalue())
    good = png(plate())
    bad = bytearray(good); bad[40] ^= 1
    with pytest.raises(ValueError, match="CRC"):
        M.decode_png(bytes(bad))


def test_a_sheet_splits_into_named_views_with_cuts_and_erase(tmp_path):
    sheet = np.zeros((60, 80, 3), np.uint8); sheet[:] = (247, 3, 251)
    for i, (cx, cy) in enumerate(((20, 15), (60, 15), (20, 45), (60, 45))):
        sheet[cy - 6:cy + 6, cx - 6:cx + 6] = (40 + 40 * i, 60, 30)
    sheet[59, 0] = (10, 10, 10)                                   # an isolated corner remnant, pinned by an erase rectangle
    src = _tree(tmp_path, Armour=sheet)
    recipe = tmp_path / "recipe.json"
    recipe.write_text(json.dumps({"schema": 1, "images": {"Armour.png": {"split": "2x2", "y_cuts": [30], "erase": [[0, 59, 1, 60]]}}}))
    r = M.remove(src, tmp_path / "o", sheet_recipe=recipe)
    files = sorted(p.relative_to(tmp_path / "o").as_posix() for p in (tmp_path / "o").rglob("*.png"))
    assert files == ["Armour/Back.png", "Armour/Front.png", "Armour/Left.png", "Armour/Right.png"] and r["images"] == 4
    left = np.asarray(Image.open(tmp_path / "o" / "Armour/Back.png"))
    assert left.shape == (30, 40, 4) and left[29, 0, 3] == 0, "the erased remnant is gone"


def test_center_puts_every_plate_on_one_common_canvas_by_integer_shift(tmp_path):
    a = np.zeros((30, 40, 4), np.uint8); a[2:10, 3:9] = (200, 10, 10, 255); a[5, 5, 3] = 1
    b = np.zeros((50, 20, 4), np.uint8); b[30:48, 2:18] = (10, 200, 10, 128)
    src = _tree(tmp_path, A=a, B=b)
    r = M.center(src, tmp_path / "c", canvas_size="common")
    man = json.loads((tmp_path / "c" / "manifest.json").read_text())
    sizes = {(x["width"], x["height"]) for x in man["images"]}
    assert sizes == {(18, 18)} and man["settings"]["canvas_size"] == 18, man["settings"]
    for x in man["images"]:
        out = np.asarray(Image.open(tmp_path / "c" / x["file"]))
        x0, y0, x1, y1 = x["output_bbox"]
        assert hashlib.sha256(out[y0:y1, x0:x1].tobytes()).hexdigest() == x["content_sha256"] and x["resampled"] is False


def test_verify_decodes_checks_hashes_and_borders_and_writes_light_dark_sheets(tmp_path):
    src = _tree(tmp_path, Helmet=plate(), Edge=plate(box=(0, 8, 30, 22)))
    M.remove(src, tmp_path / "o")
    v = M.verify(tmp_path / "o", src, tmp_path / "v")
    assert v["verdict"] == "PASS" and v["images"] == 2 and v["sources_unchanged"] and v["hashes_match"], v
    assert v["nonzero_alpha_border"] == ["Edge.png"], "a foreground touching the frame is named, not failed"
    sheet = np.asarray(Image.open(v["contact_sheet"]))
    assert sheet.shape[2] in (3, 4) and sheet.shape[1] >= 2 * 2 * 8
    (tmp_path / "o" / "Helmet.png").write_bytes(png(plate()))
    bad = M.verify(tmp_path / "o", src, tmp_path / "v2")
    assert bad["verdict"] == "FAIL" and "Helmet.png" in json.dumps(bad["failures"]), bad


def test_the_tool_answers_through_api_in_the_app(tmp_path):
    from features_support import run
    _tree(tmp_path, Helmet=plate(), Sandal=plate(fg=(20, 20, 20)))
    r = run(tmp_path, '''
a = call("image_matte", action="remove", src="src", out="matte")
c = call("image_matte", action="center", src="matte", out="centred", canvas_size="common")
v = call("image_matte", action="verify", src="src", out="matte")
bad = call("image_matte", action="remove", src="src", out="matte")
print("RESULT", json.dumps({"a": a, "c": c, "v": v, "bad": bad}))
''')
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    assert o["a"]["ok"] and o["a"]["images"] == 2 and o["c"]["ok"] and o["c"]["canvas_size"] == 20, o
    assert o["v"]["ok"] and o["v"]["verdict"] == "PASS" and Path(o["v"]["contact_sheet"]).exists(), o["v"]
    assert o["bad"]["ok"] is False and "already exists" in o["bad"]["error"], o["bad"]
