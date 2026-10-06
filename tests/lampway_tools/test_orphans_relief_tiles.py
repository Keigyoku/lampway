# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""relief_tiles (specs/shelf/relief_map.md, second stage; the shelf's texlib/relief_tiles.py ported): tile each plate view so the relief generator sees
ornament at full scale (make), then stitch the tile reliefs' FINE band into one frame per view with a raised-cosine window (stitch). Pure numpy + PIL."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.pipeline import relief_tiles as RT  # noqa: E402


def _plate(d, view="Front", box=(150, 120, 560, 600)):
    a = np.zeros((RT.PLATE, RT.PLATE, 4), np.uint8)
    x0, y0, x1, y1 = box
    a[y0:y1, x0:x1] = (180, 140, 60, 255)
    Image.fromarray(a, "RGBA").save(d / f"{view}.png")


def test_make_tiles_the_alpha_box_and_records_each_tiles_plate_box(tmp_path):
    v3 = tmp_path / "v3"; v3.mkdir(); _plate(v3)
    rec = RT.make(str(v3), str(tmp_path / "tiles"), ["Front"])
    names = [t["name"] for t in rec["tiles"]]
    assert names and all((tmp_path / "tiles" / f"{n}.png").exists() for n in names)
    assert Image.open(tmp_path / "tiles" / f"{names[0]}.png").size == (RT.UP, RT.UP)
    xs = sorted({t["box_plate"][0] for t in rec["tiles"]}); ys = sorted({t["box_plate"][1] for t in rec["tiles"]})
    assert xs[0] == 150 and xs[-1] == 560 - RT.TILE and ys[0] == 120 and ys[-1] == 600 - RT.TILE, (xs, ys)
    assert json.loads((tmp_path / "tiles" / "tiles.json").read_text())["tiles"] == rec["tiles"]


def test_stitch_puts_a_fine_detail_back_at_its_plate_position(tmp_path):
    v3 = tmp_path / "v3"; v3.mkdir(); _plate(v3)
    tdir = tmp_path / "tiles"
    rec = RT.make(str(v3), str(tdir), ["Front"])
    # the fake relief: one bright dot at plate (300, 300) in every tile that covers it, flat elsewhere
    for t in rec["tiles"]:
        bx, by, bw, _ = t["box_plate"]
        r = np.full((RT.UP, RT.UP), 128, np.uint8)
        if bx <= 300 < bx + bw and by <= 300 < by + bw:
            k = RT.UP / RT.TILE
            cx, cy = int((300 - bx + 0.5) * k), int((300 - by + 0.5) * k)
            r[cy - 3:cy + 4, cx - 3:cx + 4] = 255
        Image.fromarray(r, "L").save(tdir / f"{t['name']}.relief.png")
    rep = RT.stitch(str(v3), str(tdir), str(tmp_path / "fine"), 1408)
    fd = np.load(tmp_path / "fine" / "Front.fine.npy")
    s = 1408 / RT.PLATE
    peak = np.unravel_index(np.argmax(fd), fd.shape)
    assert abs(peak[0] - 300.5 * s) <= 3 and abs(peak[1] - 300.5 * s) <= 3, (peak, 300.5 * s)
    assert rep["views"]["Front"]["tiles_used"] == len(rec["tiles"])


def test_a_missing_relief_is_reported_and_a_wrong_plate_size_refused(tmp_path):
    v3 = tmp_path / "v3"; v3.mkdir(); _plate(v3)
    rec = RT.make(str(v3), str(tmp_path / "tiles"), ["Front"])
    rep = RT.stitch(str(v3), str(tmp_path / "tiles"), str(tmp_path / "fine"))
    assert rep["views"]["Front"]["tiles_used"] == 0 and len(rep["missing"]) == len(rec["tiles"])
    Image.new("RGBA", (500, 500)).save(v3 / "Back.png")
    with pytest.raises(RT.ReliefTileError, match="704"):
        RT.make(str(v3), str(tmp_path / "t2"), ["Back"])


def test_the_tool_answers_through_api(tmp_path):
    from features_support import run
    v3 = tmp_path / "v3"; v3.mkdir(); _plate(v3)
    r = run(tmp_path, '''
print("RESULT", json.dumps({"make": call("relief_tiles", stage="make", v3_dir="v3", tile_dir="tiles", views=["Front"]),
                            "bad": call("relief_tiles", stage="melt", v3_dir="v3", tile_dir="tiles"),
                            "jail": call("relief_tiles", stage="make", v3_dir="/etc", tile_dir="tiles")}))
''')
    assert r.rc == 0, r.out[-2000:]
    o = r.results[0]
    assert o["make"]["ok"] is True and o["make"]["counts"] == {"Front": len(o["make"]["tiles"])} and "tripo.relief" in o["make"]["next"], o["make"]
    assert o["bad"]["ok"] is False and "make | stitch" in o["bad"]["error"] and o["jail"]["ok"] is False, o
