# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Gaussian splats (Mixar docs: "a splat is not an ordinary polygon mesh ... treat splats as a separate environment workflow";
Stefan's engine-gaussian-splat-environments). Proven code: the 3D Gaussian Splatting PLY layout (x y z, f_dc_0..2 spherical
harmonic DC colour, opacity logit, log scales, rotation quaternion) decoded exactly as the format defines it, into a coloured
point object with a geometry-nodes view; the splat stays a separate object, never converted to a mesh. Generating a splat from an
image or text needs a world model (World Labs): that is the slot, and it is not wired (no driver exists)."""

import struct

import numpy as np

from features_support import run

C0 = 0.28209479177387814


def write_ply(path, n=100, seed=1, extra_float=("nx",)):
    rng = np.random.default_rng(seed)
    props = ["x", "y", "z", "f_dc_0", "f_dc_1", "f_dc_2", "opacity", "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3"]
    data = np.zeros((n, len(props)), dtype="<f4")
    data[:, 0:3] = rng.uniform(-1, 1, (n, 3))
    data[:, 3:6] = rng.uniform(-1, 1, (n, 3))
    data[:, 6] = rng.uniform(-3, 3, n)
    data[:, 7:10] = np.log(rng.uniform(0.01, 0.05, (n, 3)))
    data[:, 10] = 1.0
    header = "ply\nformat binary_little_endian 1.0\nelement vertex %d\n" % n + "".join(f"property float {p}\n" for p in props) + "end_header\n"
    with open(path, "wb") as fh:
        fh.write(header.encode("ascii"))
        fh.write(data.tobytes())
    return data


def test_a_3dgs_ply_is_decoded_into_a_coloured_point_object_with_a_geometry_nodes_view(tmp_path):
    data = write_ply(tmp_path / "scene.ply", n=100)
    r = run(tmp_path, '''
res = call("splat_import", path="scene.ply", name="lw_splat")
ob = bpy.data.objects[res["object"]]
me = ob.data
col = np.empty(len(me.vertices) * 4, dtype=np.float32); me.attributes["splat_color"].data.foreach_get("color", col)
op = np.empty(len(me.vertices), dtype=np.float32); me.attributes["splat_opacity"].data.foreach_get("value", op)
rad = np.empty(len(me.vertices), dtype=np.float32); me.attributes["splat_radius"].data.foreach_get("value", rad)
co = np.empty(len(me.vertices) * 3, dtype=np.float32); me.vertices.foreach_get("co", co)
print("RESULT", json.dumps({"res": res, "n": len(me.vertices), "polys": len(me.polygons), "col": col.reshape(-1, 4)[:3].tolist(), "op": op[:3].tolist(),
                            "rad": rad[:3].tolist(), "co": co.reshape(-1, 3)[:3].tolist(), "mods": [m.type for m in ob.modifiers]}))
''')
    assert r.rc == 0, r.out[-2500:]
    out = r.results[0]
    assert out["res"]["ok"] is True and out["res"]["splats"] == 100 and out["n"] == 100 and out["polys"] == 0
    assert "NODES" in out["mods"]
    for i in range(3):
        want_rgb = np.clip(0.5 + C0 * data[i, 3:6], 0, 1)
        assert np.allclose(out["col"][i][:3], want_rgb, atol=1e-5), (out["col"][i], want_rgb)
        assert abs(out["op"][i] - 1 / (1 + np.exp(-data[i, 6]))) < 1e-5
        assert abs(out["rad"][i] - float(np.exp(data[i, 7:10]).mean())) < 1e-5
        assert np.allclose(out["co"][i], data[i, 0:3], atol=1e-6)


def test_max_points_subsamples_deterministically_and_a_bad_file_is_refused(tmp_path):
    write_ply(tmp_path / "scene.ply", n=500)
    (tmp_path / "bad.ply").write_bytes(b"ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nend_header\n1\n")
    (tmp_path / "plain.ply").write_bytes(b"ply\nformat binary_little_endian 1.0\nelement vertex 1\nproperty float x\nend_header\n" + struct.pack("<f", 1.0))
    r = run(tmp_path, '''
a = call("splat_import", path="scene.ply", max_points=120, name="a")
b = call("splat_import", path="scene.ply", max_points=120, name="b")
fa = bpy.data.objects[a["object"]].data; fb = bpy.data.objects[b["object"]].data
ca = np.empty(len(fa.vertices) * 3, dtype=np.float32); fa.vertices.foreach_get("co", ca)
cb = np.empty(len(fb.vertices) * 3, dtype=np.float32); fb.vertices.foreach_get("co", cb)
print("RESULT", json.dumps({"a": a, "same": bool(np.array_equal(ca, cb)), "n": len(fa.vertices),
                            "ascii": call("splat_import", path="bad.ply"), "plain": call("splat_import", path="plain.ply"),
                            "outside": call("splat_import", path="/etc/hostname")}))
''')
    out = r.results[0]
    assert out["a"]["ok"] is True and out["n"] == 120 and out["same"] is True and out["a"]["source_splats"] == 500
    assert out["ascii"]["ok"] is False and "binary_little_endian" in out["ascii"]["error"]
    assert out["plain"]["ok"] is False and "f_dc_0" in out["plain"]["error"]
    assert out["outside"]["ok"] is False and "outside the project root" in out["outside"]["error"]
