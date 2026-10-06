# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract 11, the compare face: a missing map is drawn as a finding, the blind overlay never carries a label until the
reveal, and an interior difference above 0.05 is lit."""

from mixar.modules.lampway_tools import compare_face as F

STATS = {"triangles": 11904, "vertices": 6002, "ngon_encoding": False, "largest_texture_px": 2048,
         "channels": {"base": True, "normal": False, "orm_packed": True, "occlusion": False, "emissive": False}}


def test_missing_channel_is_drawn_as_a_finding():
    strip = F.strip(STATS)
    assert strip["tris"] == "11,904 tris"
    normal = next(c for c in strip["channels"] if c["key"] == "normal")
    assert normal["text"] == "no normal map baked" and normal["tone"] == "stop" and normal["glyph"] == "cross"
    base = next(c for c in strip["channels"] if c["key"] == "base")
    assert base["text"] == "base" and base["tone"] == "go"
    assert "6,002 verts" in strip["hover"] and "quads unknown: triangles only" in strip["hover"] and "largest texture 2K" in strip["hover"]
    assert "quads (ngon-encoded)" in F.strip(dict(STATS, ngon_encoding=True))["hover"]


def test_blind_overlay_never_holds_the_label():
    view = {"alias": "C", "label": "Tripo v3 smart mesh"}
    blind = F.overlay_texts(view, blind=True, revealed=False)
    assert blind == ["C", "name hidden"] and not any("Tripo" in t for t in blind)
    assert F.overlay_texts(view, blind=True, revealed=True) == ["C", "Tripo v3 smart mesh"]
    assert F.overlay_texts(view, blind=False, revealed=False) == ["C", "Tripo v3 smart mesh"]


def test_interior_highlight_threshold():
    pairs = {"pairs": [{"a": 0, "b": 1, "worst_iou": 0.991, "worst_interior": 0.05, "views": [{"cells_compared": 18240}]},
                       {"a": 0, "b": 2, "worst_iou": 0.962, "worst_interior": 0.071, "views": [{"cells_compared": 18240}]}]}
    rows = F.pair_rows(pairs, aliases="ABCD")
    assert [r["pair"] for r in rows] == ["A vs B", "A vs C"]
    assert rows[0]["interior_tone"] == "text" and rows[1]["interior_tone"] == "accent", "above 0.05 only"
    assert rows[1]["iou"] == "0.962" and rows[1]["interior"] == "0.071"
    assert rows[1]["tip"] == "measured on 192 x 192, 10 bands, 18,240 cells"


def test_the_mode_bar_carries_its_keys():
    assert F.MODES == (("1", "Wire"), ("2", "Clay"), ("3", "Normals"), ("4", "Textured"), ("5", "Base colour"), ("6", "Normal map"), ("7", "ORM"))


def test_the_drawn_overlay_never_holds_the_label_while_blind(monkeypatch):
    """Contract 11 test 2 on the drawn text: every blf.draw argument of a compare area's overlay, before and after the reveal."""
    import sys
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    for name in ("Panel", "Operator"):
        monkeypatch.setattr(sys.modules["bpy.types"], name, object, raising=False)
    monkeypatch.delitem(sys.modules, "mixar.modules.lampway_tools.ui.compare", raising=False)
    import importlib
    ui = importlib.import_module("mixar.modules.lampway_tools.ui.compare")
    drawn = []
    fake_blf = MagicMock()
    fake_blf.draw.side_effect = lambda font, text: drawn.append(text)
    monkeypatch.setitem(sys.modules, "blf", fake_blf)
    area = SimpleNamespace(as_pointer=lambda: 77, height=600)
    monkeypatch.setattr(sys.modules["bpy"], "context", SimpleNamespace(area=area), raising=False)
    ui.STATE.update(manifest={"blind": True, "models": [{"index": 0, "alias": "C", "object": "LWC_x_0"}]}, areas={77: 0},
                    labels={0: "Tripo v3 smart mesh"}, revealed=False)
    ui._draw_overlay()
    assert drawn == ["C", "name hidden"]
    drawn.clear()
    ui.STATE.update(revealed=True)
    ui._draw_overlay()
    assert drawn == ["C", "Tripo v3 smart mesh"]
    drawn.clear()
    ui.STATE.update(areas={})
    ui._draw_overlay()
    assert drawn == [], "an area that is not a compare view draws nothing"
