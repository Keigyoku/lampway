# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""N1 (specs/canon/normalization DOOR.md section 1): canon_io, the ONLY module that calls Blender's importers.

import_raw stamps every datablock an import made `lw_raw` (the raw bytes' sha256, the container, the importer and its settings);
load_image binds the colour space to the role; facts measures what a door re-checks; the npz carries its canonical header."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from test_wave3_weights import PRE  # noqa: E402


def run(body):
    r = run_script(PRE + body, timeout=300)
    assert r.rc == 0, r.out[-1500:]
    return r.results[-1]


def test_import_raw_stamps_every_new_datablock_with_the_raw_sha_container_and_settings():
    d = run('''
from mixar.modules.lampway_tools import canon_io
bpy.ops.mesh.primitive_cube_add(size=1.0); cube = bpy.context.active_object
path = os.path.join(root, "box.glb")
bpy.ops.export_scene.gltf(filepath=path, use_selection=True)
bpy.data.objects.remove(cube)
r = canon_io.import_raw(path, guess_original_bind_pose=False)
ob = bpy.data.objects[r["objects"][0]]
res({"r": {k: r[k] for k in ("sha256", "container", "importer", "settings", "objects")}, "stamp": json.loads(ob["lw_raw"]),
     "mesh_stamp": json.loads(ob.data["lw_raw"]) if "lw_raw" in ob.data else None, "path": path})
''')
    raw = Path(d["path"]).read_bytes() if Path(d["path"]).exists() else None
    assert d["r"]["container"] == "glb" and d["r"]["importer"] == "import_scene.gltf" and d["r"]["settings"] == {"guess_original_bind_pose": False}
    assert d["stamp"]["sha256"] == d["r"]["sha256"] and len(d["r"]["sha256"]) == 64 and d["mesh_stamp"] == d["stamp"]
    assert raw is None or d["r"]["sha256"] == hashlib.sha256(raw).hexdigest()


def test_import_raw_refuses_an_unknown_container():
    d = run('''
from mixar.modules.lampway_tools import canon_io
p = os.path.join(root, "x.xyz"); open(p, "w").write("x")
try:
    canon_io.import_raw(p); res({"err": None})
except ValueError as e:
    res({"err": str(e)})
''')
    assert d["err"] and ".xyz" in d["err"]


def test_load_image_binds_the_colour_space_to_the_role_and_stamps_it():
    d = run('''
from mixar.modules.lampway_tools import canon_io
im = bpy.data.images.new("t", 4, 4); p = os.path.join(root, "t.png"); im.filepath_raw = p; im.file_format = "PNG"; im.save()
a = canon_io.load_image(p, role="normal"); b = canon_io.load_image(p, role="basecolor")
res({"normal": a.colorspace_settings.name, "base": b.colorspace_settings.name, "stamp": json.loads(a["lw_raw"])})
''')
    assert d["normal"] == "Non-Color" and d["base"] == "sRGB" and d["stamp"]["role"] == "normal" and len(d["stamp"]["sha256"]) == 64


def test_facts_measure_the_matrix_the_unit_the_bounds_and_the_geometry_hash():
    d = run('''
from mixar.modules.lampway_tools import canon_io
bpy.ops.mesh.primitive_cube_add(size=2.0); ob = bpy.context.active_object
f0 = canon_io.facts(ob)
ob.data.vertices[0].co.x += 0.25; ob.data.update()
f1 = canon_io.facts(ob)
ob.location = (1, 0, 0); bpy.context.view_layer.update()
f2 = canon_io.facts(ob)
res({"f0": f0, "h1": f1["geometry_sha256"], "m2": f2["object_matrix"]})
''')
    f0 = d["f0"]
    assert np.allclose(f0["object_matrix"], np.eye(4)) and f0["scene_scale_length"] == 1.0
    assert np.allclose(f0["bbox_min_m"], [-1, -1, -1]) and np.allclose(f0["bbox_max_m"], [1, 1, 1])
    assert len(f0["geometry_sha256"]) == 64 and d["h1"] != f0["geometry_sha256"] and d["m2"][0][3] == 1.0


def test_npz_carries_its_canonical_header(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
    from mixar.modules.lampway_tools import canon_io
    doc = {"schema": "lampway.canonical-asset", "kind": "mesh"}
    p = tmp_path / "x.npz"
    canon_io.write_npz(p, np.zeros((3, 3)), np.array([[0, 1, 2]]), doc)
    V, T, canon = canon_io.read_npz(p)
    assert canon == doc and V.shape == (3, 3) and T.tolist() == [[0, 1, 2]]
    np.savez(tmp_path / "raw.npz", V=np.zeros((3, 3)), T=np.array([[0, 1, 2]]))
    assert canon_io.read_npz(tmp_path / "raw.npz")[2] is None
