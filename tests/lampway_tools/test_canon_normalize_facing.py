# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Canon D6: cardinal plate registration preserves aspect and refuses ambiguous facing."""
import json

from blender_run import run_script
from test_wave3_weights import PRE

FACING = r'''
import numpy as np
from mathutils import Matrix
from mixar.modules.lampway_tools.features import normalize as N, silhouette as S
from mixar.modules.lampway_tools import canon_asset as CA
from PIL import Image
def shape(name):
    outline = [(0,0),(1,0),(1,.3),(.3,.3),(.3,1),(0,1)]
    v = [(x*.2,y,z*.2) for y in (-.04,.04) for x,z in outline]
    f = [tuple(range(5,-1,-1)),tuple(range(6,12))]+[(i,(i+1)%6,(i+1)%6+6,i+6) for i in range(6)]
    me = bpy.data.meshes.new(name); me.from_pydata(v,[],f); me.update()
    ob = bpy.data.objects.new(name,me); bpy.context.scene.collection.objects.link(ob); return ob
source = shape("approved")
plate = os.path.join(root,"Front.png")
mask = S._render_mask(source,source,"Front",128,plate)
rgba = np.dstack([np.full((*mask.shape,3),255,np.uint8),(mask*255).astype(np.uint8)])
canvas = np.zeros((128,256,4),np.uint8); canvas[:,64:192] = rgba
Image.fromarray(canvas,"RGBA").save(plate)
raw = shape("raw")
raw.data.transform(Matrix.Rotation(math.radians(90),4,"Z")); raw.data.update()
bpy.context.view_layer.update()
'''

def test_approved_plate_picks_actual_minus90_rotation_and_records_best_second_margin(tmp_path):
    r = run_script(PRE+FACING+r'''
CA.SETTINGS["facing_margin"]["value"] = None
before = N._ids(); old_mesh_pointer = raw.data.as_pointer()
result = api.normalize_mesh(input="raw",plate=plate,generator="captain_authored",weld="never",facing_margin=.1)
assert result.get("ok"),result
doc = json.loads(raw["lw_canon"])
receipt = json.load(open(os.path.join(root,result["receipt_path"])))
assert receipt["steps"][1]["evidence"] == doc["conventions"]["frame_decision"]["evidence"]
assert N._ids()-{("meshes",raw.data.as_pointer())} == before-{("meshes",old_mesh_pointer)}, "registration left renderer IDs"
res({"raw_front":doc["conventions"]["source_frame"]["front"],"generator":doc["raw"]["generator"]["source"],"turn":doc["conventions"]["turn_deg"],"decision":doc["conventions"]["frame_decision"],"vertices":[v.co[:] for v in raw.data.vertices]})
''',env={"LW_KEEP_ROOT":str(tmp_path)},timeout=300)
    assert r.rc == 0,r.out[-2500:]
    d = r.results[-1]
    (tmp_path / "facing-proof.json").write_text(json.dumps(d, indent=2)+"\n")
    assert d["turn"] == -90.0 and d["raw_front"] == "+X" and d["generator"] == "captain_authored"
    assert d["decision"]["kind"] == "measured"
    e = d["decision"]["evidence"]
    assert e["method"] == "plate_silhouette_registration" and e["value"] > .99 and e["value"]-e["second_best"] >= .1
    assert e["margin"] == .1
    # The winner is applied to the mesh, not just reported.
    assert max(abs(d["vertices"][i][0]-d["vertices"][i+6][0]) for i in range(6)) < 1e-6

def test_symmetric_plate_refuses_best_second_tie_and_preserves_geometry(tmp_path):
    r = run_script(PRE+FACING+r'''
CA.SETTINGS["facing_margin"]["value"] = .1
bpy.ops.mesh.primitive_cube_add(size=.2); cube = bpy.context.object
plate = os.path.join(root,"Cube.png")
m = S._render_mask(cube,cube,"Front",128,plate)
Image.fromarray(np.dstack([np.full((*m.shape,3),255,np.uint8),(m*255).astype(np.uint8)]),"RGBA").save(plate)
before = [v.co[:] for v in cube.data.vertices]; ids = N._ids()
try:
    N.normalize_object(cube,plate=plate,generator="captain_authored",root=root)
except Exception as error:
    message = str(error)
else:
    raise AssertionError("symmetric facing was accepted")
res({"message":message,"unchanged":[v.co[:] for v in cube.data.vertices] == before,"ids":N._ids() == ids})
''',env={"LW_KEEP_ROOT":str(tmp_path)},timeout=300)
    assert r.rc == 0,r.out[-2500:]
    d = r.results[-1]
    (tmp_path / "tie-proof.json").write_text(json.dumps(d, indent=2)+"\n")
    assert "facing ambiguous" in d["message"] and "IoU" in d["message"] and "turn_deg" in d["message"]
    assert d["unchanged"] and d["ids"]


def test_border_ring_key_and_native_aspect_share_the_existing_loader(tmp_path):
    r = run_script(PRE+FACING+r'''
# Nonliteral border colour and a fringe supported by the canon's own p99 key.
px = np.full((64,128,3),(249,3,251),np.uint8)
px[0,0] = (237,11,240)
px[20:40,35:75] = (40,80,100)
path = os.path.join(root,"border.png"); Image.fromarray(px).save(path)
mask = S._image_mask(path)
res({"shape":list(mask.shape),"count":int(mask.sum()),"corner":bool(mask[0,0]),"subject":bool(mask[30,50]),"square":list(S._image_mask(path,128).shape)})
''',env={"LW_KEEP_ROOT":str(tmp_path)},timeout=300)
    assert r.rc == 0,r.out[-2000:]
    d = r.results[-1]
    assert d["shape"] == [64,128] and d["square"] == [128,128] and d["subject"]
    assert 800 <= d["count"] <= 801

def test_unset_or_invalid_margin_refuses_without_changing_the_raw_mesh(tmp_path):
    r = run_script(PRE+FACING+r'''
CA.SETTINGS["facing_margin"]["value"] = None
before = [v.co[:] for v in raw.data.vertices]
missing = api.normalize_mesh(input="raw",plate=plate,generator="captain_authored")
bad = [api.normalize_mesh(input="raw",plate=plate,facing_margin=value) for value in (-.1,1.1,True)]
res({"missing":missing,"bad":bad,"unchanged":before == [v.co[:] for v in raw.data.vertices]})
''',env={"LW_KEEP_ROOT":str(tmp_path)},timeout=300)
    assert r.rc == 0,r.out[-2200:]
    d = r.results[-1]
    assert not d["missing"]["ok"] and "facing_margin" in d["missing"]["error"]
    assert all(not x["ok"] and "0..1" in x["error"] for x in d["bad"]) and d["unchanged"]
