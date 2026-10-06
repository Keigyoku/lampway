# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the Asset Vault window says, as pure functions (specs/client_facelift/09-asset-vault.md section 10, DESIGN v2 sections 13-14): the similar strip names where it runs,
every provenance line is dated and the timeline collapses to one glance line, the selected tile sits on the lamplit bed, stats are a kind's own rows."""

from mixar.modules.asset_library.core import present as P

PALETTE = {"viewport_hi": (0.10, 0.11, 0.15, 1.0), "viewport_lo": (0.04, 0.05, 0.07, 1.0), "accent_bed": (0.23, 0.18, 0.09, 1.0), "accent_bed_hi": (0.35, 0.28, 0.13, 1.0),
           "accent": (0.93, 0.73, 0.27, 1.0)}

REC = {"id": "a1", "kind": "mesh", "name": "Bronze greaves", "created_at": 1759672920.0, "license_id": None, "attribution": None,
       "stats": {"tris": 12000, "verts": 6100, "dim_x": 0.31, "dim_y": 0.28, "dim_z": 0.92, "materials": 2, "uv_sets": 1, "watertight": 0, "version_id": "v"},
       "generation": [{"studio": "tripo", "model": "h3.1", "action": "mesh", "started_at": 1759672800.0, "finished_at": 1759672920.0, "job_id": "j1"}],
       "relations": [{"src": "a1", "dst": "p1", "type": "generated_from", "role": "", "by": "rule"}, {"src": "a1", "dst": "p2", "type": "derived_from", "role": "", "by": "rule"},
                     {"src": "c9", "dst": "a1", "type": "variant_of", "role": "", "by": "rule"}],
       "files": [{"role": "main", "sha256": "s", "bytes": 1, "locations": [{"path": "/x/greaves.glb", "storage": "external", "missing": 0}]}]}


def test_similar_strip_names_where_it_runs():
    local = P.similar_chip({"location": "local"})
    assert local["glyph"] == "lamp" and local["text"] == "local embeddings, no egress" and local["colour"] == "go"
    remote = P.similar_chip({"location": "remote", "host": "openrouter.ai"})
    assert remote["glyph"] == "wire" and "openrouter.ai" in remote["text"] and remote["colour"] == "wire"
    assert P.similar_chip({}) == local, "no backend reported means the bundled local model"


def test_a_remote_backend_is_never_labelled_local():
    for backend in ({"location": "remote", "host": "x"}, {"location": "remote"}):
        chip = P.similar_chip(backend)
        assert chip["glyph"] != "lamp" and "local" not in chip["text"]


def test_provenance_lines_are_dated_and_collapse_to_one_glance_line():
    lines = P.provenance_lines(REC, tz=0)
    assert lines and all(P.DATED.match(ln) for ln in lines), lines
    assert any("tripo" in ln and "h3.1" in ln for ln in lines)
    assert P.provenance_glance(REC, tz=0) == "14:02, 2 parents"
    assert P.provenance_glance({"created_at": 1759672920.0, "generation": [], "relations": []}, tz=0) == "14:02, no parents"


def test_the_selected_tile_uses_the_lamplit_bed_and_the_others_the_viewport_light():
    plain = P.tile_bed((0, 0, 128, 128), selected=False, palette=PALETTE)
    lit = P.tile_bed((0, 0, 128, 128), selected=True, palette=PALETTE)
    assert plain == [("radial", (0, 0, 128, 128), PALETTE["viewport_hi"], PALETTE["viewport_lo"])]
    assert lit[0] == ("radial", (0, 0, 128, 128), PALETTE["accent_bed_hi"], PALETTE["accent_bed"])
    assert ("edge", (0, 0, 128, 128), PALETTE["accent"]) in lit


def test_stats_are_the_kinds_own_rows_and_empty_values_are_left_out():
    rows = dict(P.stats_rows(REC))
    assert rows["Triangles"] == "12 000" and rows["Size"] == "0.31 x 0.28 x 0.92 m" and rows["Watertight"] == "no"
    assert "version_id" not in rows and "Bones" not in rows
    video = dict(P.stats_rows({"kind": "video", "stats": {"motion_fps": 12.0, "container_fps": 24.0, "duration_s": 4.5, "width": 1280, "height": 720}}))
    assert video["Motion fps"] == "12 (container 24)" and video["Frame"] == "1280 x 720" and video["Duration"] == "4.5 s"
