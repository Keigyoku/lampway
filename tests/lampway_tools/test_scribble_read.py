# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""scribble_read (specs/mixar_docs/scribble_marks.md): the read side of the Scribble marks for an external driver. The marks are the Client's own records
(scene.mixar_marks, written by scribble_mark/core/marks.add_mark); the tool re-reads them through marks.get_marks and says, per mark, its kind, the object it
resolved to, its region (the payload's own bottom-up 0..1 frame bbox, no y flip) and its anchor in NDC (-1..1, y up), plus the Client's own prose summary. include_image writes the mark's frozen annotated frame under the project root."""

from features_support import run

MARKS = '''
from mixar.modules.scribble_mark.core import marks as M, freeze as F
if not hasattr(bpy.types.Scene, "mixar_marks"):          # the UI modules register on deferred timers, which never fire in a -b -P run
    from mixar.modules.scribble_mark.ui.properties import mark_props
    mark_props.register()
boxes("alpha_cube", [((0, 0, 0), (1, 1, 1))]); boxes("beta_cube", [((3, 0, 0), (1, 1, 1))])
scene = bpy.context.scene
def mark(gesture, resolved, poly):
    serial = M.next_serial(scene)
    return M.add_mark(scene, serial, "mixar_mark_view_0001", {"size": [200, 100]}, {"gesture": gesture, "polygon": poly, "anchor": poly[0]}, 200, 100,
                      resolved=resolved, strokes=[poly])
mark("circle", {"hit": True, "objects": [{"name": "alpha_cube", "partial": False}, {"name": "beta_cube"}], "point": [0.0, -1.0, 0.5]}, [[20, 20], [60, 20], [60, 60], [20, 60]])
mark("point", {"hit": False, "plane": True, "point": [5.0, 1.0, 0.0]}, [[150, 50]])
'''


def test_the_marks_come_back_with_the_object_each_resolved_to(tmp_path):
    r = run(tmp_path, MARKS + '''
res = call("scribble_read")
print("RESULT", json.dumps(res))
''')
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    assert o["ok"] is True and o["mode"] == "point" and len(o["marks"]) == 2, o
    assert o["marks"][0]["object"] == "alpha_cube" and o["marks"][0]["kind"] == "circle" and o["marks"][0]["region"] == [0.1, 0.2, 0.3, 0.6] and o["marks"][0]["ndc"] == [-0.8, -0.6], o["marks"][0]
    assert o["marks"][1]["object"] is None and o["marks"][1]["kind"] == "point" and o["marks"][1]["ndc"] == [0.5, 0.0], o["marks"][1]
    assert "`alpha_cube`" in o["summary"] and "(5, 1, 0)" in o["summary"] and "image_path" not in o, o


def test_include_image_writes_the_annotated_frame_and_refuses_without_one(tmp_path):
    r = run(tmp_path, MARKS + '''
none = call("scribble_read", include_image=True)
img = bpy.data.images.new(F.annotated_name(2), 32, 16)
img.pixels = [0.5] * (32 * 16 * 4)
res = call("scribble_read", include_image=True)
print("RESULT", json.dumps({"none": none, "res": res}))
''')
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    assert o["none"]["ok"] is False and "no frozen frame" in o["none"]["error"], o["none"]
    p = o["res"]["image_path"]
    assert o["res"]["ok"] and p.endswith(".png") and p.startswith(str(tmp_path)), o["res"]
    from PIL import Image
    assert Image.open(p).size == (32, 16)


def test_no_marks_is_an_empty_answer_not_an_error(tmp_path):
    r = run(tmp_path, '''
res = call("scribble_read")
print("RESULT", json.dumps(res))
''')
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    assert o["ok"] is True and o["marks"] == [] and o["mode"] is None and o["summary"] == "", o
