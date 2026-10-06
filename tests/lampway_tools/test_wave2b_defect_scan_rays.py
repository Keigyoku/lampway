# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""mesh_defect_scan amendment (specs/mrmak/BUILD_ORDER_ADDENDUM section 2): report the ray coverage of the thin scan and state its epsilon as a fraction of the bounding-box diagonal."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

BODY = '''
def sphere_half(name, scale=1.0, open_=False):
    bm = bmesh.new(); bmesh.ops.create_icosphere(bm, subdivisions=3, radius=0.5 * scale)
    if open_:
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_center_median().z > 0], context="FACES")
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    return link(bpy.data.objects.new(name, me))
'''


def test_the_thin_scan_reports_its_ray_coverage_and_epsilon_as_a_fraction_of_the_diagonal(tmp_path):
    r = run(tmp_path, BODY + '''
sphere_half("closed"); sphere_half("open", open_=True); sphere_half("big", scale=100.0)
out = {n: call("mesh_defect_scan", object=n, kinds=["thin"]) for n in ("closed", "open", "big")}
print("RESULT", json.dumps(out))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    c, op, big = (o[k]["rays"] for k in ("closed", "open", "big"))
    assert c["faces_cast"] > 100 and c["hit_fraction"] > 0.95 and c["miss"] < c["faces_cast"] * 0.05
    assert op["hit_fraction"] < 0.6 and "open mesh" in op["note"]                         # half the sphere is gone: the inward rays escape through the opening
    assert abs(c["epsilon_m"] - c["epsilon_frac_of_diagonal"] * c["bbox_diagonal_m"]) < 1e-9 and 0 < c["epsilon_frac_of_diagonal"] < 1e-2
    assert abs(big["epsilon_m"] / c["epsilon_m"] - 100.0) < 1e-6 and big["epsilon_frac_of_diagonal"] == c["epsilon_frac_of_diagonal"]      # the epsilon scales with the model


def test_a_scan_without_the_thin_kind_has_no_ray_block(tmp_path):
    r = run(tmp_path, BODY + '''
sphere_half("closed")
print("RESULT", json.dumps(call("mesh_defect_scan", object="closed", kinds=["degenerate"])))
''')
    assert r.rc == 0 and "rays" not in r.results[0]
