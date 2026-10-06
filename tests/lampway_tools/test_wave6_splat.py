# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""splat_world (the import half: SPZ through the Client's own decoder, PLY as is) and splat_collision_proxy (specs/mixar_docs/splat_world.md,
specs/wiki/splat_collision_proxy.md) in the real binary. A splat is a point object: mesh tools refuse it. The collision proxy is a separate, named, closed
mesh from the opacity-weighted voxel occupancy, because visually dense splats do not imply physics surfaces."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from wave6_support import go, one  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

PLY = '''
def write_ply(path, pts, opacity=0.9):
    n = len(pts)
    dt = np.dtype([(k, "<f4") for k in ("x", "y", "z", "f_dc_0", "f_dc_1", "f_dc_2", "opacity", "scale_0", "scale_1", "scale_2")])
    a = np.zeros(n, dtype=dt)
    a["x"], a["y"], a["z"] = pts[:, 0], pts[:, 1], pts[:, 2]
    op = np.full(n, opacity) if np.isscalar(opacity) else opacity
    a["opacity"] = np.log(op / (1 - op))
    a["scale_0"] = a["scale_1"] = a["scale_2"] = np.log(0.01)
    head = "ply\\nformat binary_little_endian 1.0\\nelement vertex %d\\n" % n + "".join("property float %s\\n" % k for k in dt.names) + "end_header\\n"
    with open(path, "wb") as fh:
        fh.write(head.encode("ascii")); fh.write(a.tobytes())
rng = np.random.default_rng(1)
def ball(n=20000, r=1.0):
    v = rng.normal(size=(n, 3)); v /= np.linalg.norm(v, axis=1, keepdims=True)
    return v * r * rng.uniform(0.0, 1.0, size=(n, 1)) ** (1 / 3)
'''


def test_spz_imports_through_the_clients_decoder_and_mesh_tools_refuse_the_splat(tmp_path):
    import numpy as np
    sys.path.insert(0, str(ROOT / "tests"))
    import test_world_labs_spz as SPZ                                          # the Client's own SPZ test encoder (it needs pytest: outside Blender)
    n = 50
    pos = np.random.default_rng(0).uniform(-1, 1, size=(n, 3)).astype(np.float32)
    (tmp_path / "world.spz").write_bytes(SPZ._make_spz_v2(pos, np.full((n, 3), -3.0, np.float32), np.zeros((n, 3), np.float32), np.full(n, 0.8, np.float32),
                                                          np.zeros((n, 3), np.float32)))
    d = one(go(tmp_path, f'''
res = call("splat_world", action="import", path="world.spz", name="env")
ob = bpy.data.objects.get("env")
lod = call("lod_chain", object="env", ratios=[0.5])
print("RESULT", json.dumps({{"res": res, "faces": len(ob.data.polygons) if ob else None, "attrs": sorted(a.name for a in ob.data.attributes if a.name.startswith("splat_")) if ob else [],
                            "lod": lod, "files": sorted(os.listdir(root))}}))
'''))
    res = d["res"]
    assert res["ok"], res
    assert res["splats"] == 50 and d["faces"] == 0 and d["attrs"] == ["splat_color", "splat_opacity", "splat_radius", "splat_scale"]
    assert res["converted_from"] == "world.spz" and "world.ply" in d["files"]
    assert d["lod"]["ok"] is False and "a splat has no faces: mesh tools refuse it" in d["lod"]["error"]


def test_generation_is_not_a_blender_action(tmp_path):
    d = one(go(tmp_path, '''
res = call("splat_world", action="generate", mode="text", prompt="a temple")
print("RESULT", json.dumps(res))
'''))
    assert d["ok"] is False and "lampway_splat_world" in d["error"] and "server" in d["error"]


def test_a_sphere_of_points_gives_a_closed_surface_near_the_radius(tmp_path):
    d = one(go(tmp_path, PLY + '''
write_ply(os.path.join(root, "ball.ply"), ball())
call("splat_import", path="ball.ply", name="scan", max_points=0)
res = call("splat_collision_proxy", object="scan", voxel_m=0.1, min_opacity=0.5, min_density=2)
ob = bpy.data.objects[res["object"]]
r = [ (ob.matrix_world @ v.co).length for v in ob.data.vertices]
print("RESULT", json.dumps({"res": res, "rmin": min(r), "rmax": max(r), "coll": [c.name for c in ob.users_collection]}))
'''))
    res = d["res"]
    assert res["ok"] and res["manifold"] is True and res["object"] == "scan_collision"
    assert 0.75 < d["rmin"] and d["rmax"] < 1.0 + 0.1 * 1.8 and d["coll"] == ["scan_collision"]
    assert res["coverage_of_splat_mass"] > 0.9


def test_low_opacity_points_are_ignored_and_ue_naming(tmp_path):
    d = one(go(tmp_path, PLY + '''
a = ball(5000, 0.5); b = ball(5000, 0.5) + np.array([3.0, 0, 0])
dust = np.stack([np.linspace(-3, -1.2, 10), np.zeros(10), np.zeros(10)], axis=1)          # ten bright specks, one per voxel: under min_density
write_ply(os.path.join(root, "two.ply"), np.vstack([a, b, dust]), opacity=np.concatenate([np.full(5000, 0.9), np.full(5000, 0.1), np.full(10, 0.9)]))
call("splat_import", path="two.ply", name="scan", max_points=0)
res = call("splat_collision_proxy", object="scan", voxel_m=0.1, min_opacity=0.5, min_density=2, export_for_ue=True)
ob = bpy.data.objects[res["object"]]
xs = [(ob.matrix_world @ v.co).x for v in ob.data.vertices]
xmin = min(xs)
bad = call("splat_collision_proxy", object="scan", min_opacity=1.1)
print("RESULT", json.dumps({"res": res, "xmax": max(xs), "xmin": xmin, "bad": bad}))
'''))
    assert d["res"]["object"] == "UCX_scan" and d["xmax"] < 1.0 and d["xmin"] > -1.0     # the faint cluster at x = 3 and the lone specks have no collision
    assert d["bad"]["ok"] is False and "0..1" in d["bad"]["error"]


def test_thin_floor_slab_stays_a_slab_at_fine_voxel_and_refusals(tmp_path):
    d = one(go(tmp_path, PLY + '''
xy = rng.uniform(-2, 2, size=(40000, 2)); z = rng.uniform(-0.005, 0.005, size=(40000, 1))
write_ply(os.path.join(root, "floor.ply"), np.hstack([xy, z]))
call("splat_import", path="floor.ply", name="floor", max_points=0)
res = call("splat_collision_proxy", object="floor", voxel_m=0.05, min_opacity=0.5, min_density=2)
ob = bpy.data.objects[res["object"]]
co = np.array([(ob.matrix_world @ v.co)[:] for v in ob.data.vertices])
sphere("plain", 0.5)
notsplat = call("splat_collision_proxy", object="plain")
huge = call("splat_collision_proxy", object="floor", voxel_m=0.02, min_density=1, max_voxels=1000)
print("RESULT", json.dumps({"res": res, "z": float(co[:, 2].max() - co[:, 2].min()), "x": float(co[:, 0].max() - co[:, 0].min()), "notsplat": notsplat, "huge": huge}))
'''))
    assert d["res"]["ok"] and d["z"] <= 0.1 + 1e-6 and d["x"] > 3.8
    assert d["notsplat"]["ok"] is False and "splat_opacity" in d["notsplat"]["error"]
    assert d["huge"]["ok"] is False and "raise voxel_m" in d["huge"]["error"]
