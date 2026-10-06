# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The one-click "UE Look" mode (specs/ue_parity/contracts/ue_look.md §4-§10) in the REAL binary: apply a profile (exposure
from EV100 and k, GI and reflections as the profile says, lights mapped by k, materials swapped to the UE Default Lit group,
backface culling = not Two Sided) and revert it EXACTLY: an RNA dump of every touched datablock is byte-identical after
apply + revert (T-LOOK-04). Refusals change nothing."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

DUMP = r'''
SKIP = {"rna_type", "session_uid", "is_evaluated", "original", "is_runtime_data", "tag", "is_editmode", "bound_box", "mode"}
def tolist(v):
    try:
        return [tolist(x) for x in v] if not isinstance(v, str) else v
    except TypeError:
        return v
def props(o, depth):
    d = {}
    for p in o.bl_rna.properties:
        pid = p.identifier
        if pid in SKIP:
            continue
        try:
            v = getattr(o, pid)
        except Exception:
            continue
        if p.type in ("BOOLEAN", "INT", "FLOAT", "STRING"):
            d[pid] = tolist(v) if getattr(p, "array_length", 0) else v
        elif p.type == "ENUM":
            d[pid] = sorted(v) if p.is_enum_flag else v
        elif p.type == "POINTER":
            if v is None:
                d[pid] = None
            elif isinstance(v, bpy.types.ID):
                d[pid] = "ID:" + v.name
            elif depth > 0:
                d[pid] = props(v, depth - 1)
    return d
def tree(nt):
    if nt is None:
        return None
    nodes = {n.name: {"type": n.bl_idname, "props": props(n, 0), "inputs": [tolist(i.default_value) if hasattr(i, "default_value") else None for i in n.inputs]} for n in nt.nodes}
    return {"nodes": nodes, "links": sorted([l.from_node.name, l.from_socket.identifier, l.to_node.name, l.to_socket.identifier] for l in nt.links)}
def dump():
    S = bpy.context.scene
    out = {"scene": {k: props(getattr(S, k), 2) for k in ("view_settings", "display_settings", "render", "eevee")},
           "scene_keys": sorted(S.keys()), "world": props(S.world, 1) if S.world else None,
           "objects": {o.name: {"slots": [[s.link, s.material.name if s.material else None] for s in o.material_slots],
                                "data_mats": [m.name if m else None for m in getattr(o.data, "materials", [])]} for o in bpy.data.objects},
           "materials": {m.name: {"props": props(m, 1), "tree": tree(m.node_tree)} for m in bpy.data.materials},
           "lights": {l.name: props(l, 1) for l in bpy.data.lights},
           "ids": {k: sorted(x.name for x in getattr(bpy.data, k)) for k in ("materials", "node_groups", "images", "lights", "objects", "worlds", "meshes")}}
    return json.dumps(out, sort_keys=True, default=str)
'''

SCENE = r'''
S = bpy.context.scene
S.render.engine = "BLENDER_EEVEE"
def mat(name, **kw):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    for k, v in kw.items(): b.inputs[k.replace("_", " ")].default_value = v
    return m
def lamp(name, kind, **kw):
    ld = bpy.data.lights.new(name, kind)
    for k, v in kw.items(): setattr(ld, k, v)
    return link(bpy.data.objects.new(name, ld))
def three_lights():
    lamp("Key", "SUN", energy=3.0); lamp("Fill", "POINT", energy=500.0, shadow_soft_size=0.25)
    lamp("Rim", "SPOT", energy=800.0, spot_size=math.radians(45.0), spot_blend=0.15)
def four_materials():
    a = sphere("A", loc=(-2, 0, 0)); a.data.materials.append(mat("Steel", Metallic=1.0, Roughness=0.3))
    b = sphere("B", loc=(0, 0, 0)); b.data.materials.append(mat("Leather", Roughness=0.8, Sheen_Weight=0.2))
    b.data.materials.append(mat("Gold", Base_Color=(1.0, 0.7, 0.2, 1.0), Metallic=1.0))
    c = sphere("C", loc=(2, 0, 0)); c.data.materials.append(bpy.data.materials["Steel"])              # shared
    c.material_slots[0].link = "OBJECT"; c.material_slots[0].material = mat("Cloth", Roughness=1.0)    # object-linked slot
def live_profile(**edits):
    from mixar.modules.lampway_tools.ue import profile as PR
    p = json.loads(open(PR.DEFAULT_PROFILE).read()); p["source"] = "live-dump"
    for path, v in edits.items():
        node = p; keys = path.split("__")
        for k in keys[:-1]: node = node[k]
        node[keys[-1]] = v
    q = os.path.join(root, f"profile_{len(os.listdir(root))}.json"); open(q, "w").write(json.dumps(p)); return q
'''


def go(tmp_path, body):
    r = run(tmp_path, DUMP + SCENE + body, timeout=600)
    assert r.rc == 0, r.out[-3000:]
    return r.results[0]


def test_look04_apply_then_revert_is_byte_identical(tmp_path):
    d = go(tmp_path, '''
three_lights(); four_materials()
before = dump()
a = call("ue_look", action="apply")
during = dump()
st = call("ue_look", action="status")
r = call("ue_look", action="revert", receipt=a["receipt_path"])
after = dump()
print("RESULT", json.dumps({"a": a, "st": st, "r": r, "same": before == after, "changed": before != during, "receipt_exists": os.path.isfile(a["receipt_path"]),
                            "after_status": call("ue_look", action="status"), "first_diff": next((i for i, (x, y) in enumerate(zip(before, after)) if x != y), None),
                            "ctx": before[max(0, (next((i for i, (x, y) in enumerate(zip(before, after)) if x != y), 0) or 0) - 200):][:400]}))
''')
    a = d["a"]
    assert a["ok"], a
    assert d["changed"] and d["receipt_exists"]
    assert d["same"], (d["first_diff"], d["ctx"])
    assert d["r"]["ok"] and d["st"]["active"] is True and d["after_status"]["active"] is False
    assert {m["name"] for m in a["materials"]} == {"Steel", "Leather", "Gold", "Cloth"}
    assert {l["name"] for l in a["lights"]} == {"Key", "Fill", "Rim"}


def test_apply_sets_exposure_eevee_flags_lights_and_classes_from_the_profile(tmp_path):
    d = go(tmp_path, '''
three_lights(); four_materials()
a = call("ue_look", action="apply")
S = bpy.context.scene
got = {"exposure": S.view_settings.exposure, "fast_gi": S.eevee.use_fast_gi, "rt": S.eevee.use_raytracing, "rt_method": S.eevee.ray_tracing_method,
       "aniso": S.render.anisotropic_filter, "soft": [bpy.data.lights[n].use_soft_falloff for n in ("Fill", "Rim")],
       "culling": {m: bpy.data.materials[m + " [UE]"].use_backface_culling for m in ("Steel", "Cloth")},
       "slot_c": bpy.data.objects["C"].material_slots[0].material.name, "slot_a": bpy.data.objects["A"].material_slots[0].material.name}
call("ue_look", action="revert", receipt=a["receipt_path"])
p = call("ue_look", action="apply", profile=live_profile(), parity=True)
got["parity"] = {"fast_gi": S.eevee.use_fast_gi, "rt": S.eevee.use_raytracing, "dither": S.render.dither_intensity}
print("RESULT", json.dumps({"a": a, "got": got, "p": p}))
''')
    a, g = d["a"], d["got"]
    assert round(a["exposure_stops"], 3) == 0.509 and round(g["exposure"], 3) == 0.509
    assert g["fast_gi"] is False and g["rt"] is True and g["rt_method"] == "SCREEN" and g["aniso"] == "FILTER_8"       # GI none; SSR -> screen tracing
    assert g["soft"] == [False, False] and g["culling"] == {"Steel": False, "Cloth": False}                             # Default Lit is one-sided only when marked so
    assert g["slot_c"] == "Cloth [UE]" and g["slot_a"] == "Steel [UE]"
    lights = {l["name"]: l for l in a["lights"]}
    assert lights["Key"]["to"]["intensity"] == 2049.0 and lights["Rim"]["to"]["outer_cone_deg"] == 22.5
    assert a["classes"]["COL"] == "needs_decision" and a["classes"]["SHD"] == "unmeasured" and a["view"]["state"] == "needs_decision"
    leather = next(m for m in a["materials"] if m["name"] == "Leather")
    assert [x["input"] for x in leather["dropped"]] == ["Sheen Weight"]
    assert d["p"]["ok"] and d["got"]["parity"] == {"fast_gi": False, "rt": False, "dither": 0.0}


def test_refusals_change_nothing_and_name_their_fix(tmp_path):
    d = go(tmp_path, '''
three_lights(); four_materials()
before = dump()
out = {"parity_defaults": call("ue_look", action="apply", parity=True),
       "auto": call("ue_look", action="apply", profile=live_profile(exposure__method="auto"), parity=True),
       "aces": call("ue_look", action="apply", profile=live_profile(tonemap__method="StandardACES")),
       "space": call("ue_look", action="apply", profile=live_profile(project__working_color_space="ACEScg"))}
lamp("Panel", "AREA", energy=50.0)
out["area"] = call("ue_look", action="apply")
bpy.data.objects.remove(bpy.data.objects["Panel"]); bpy.data.lights.remove(bpy.data.lights["Panel"])
out["unchanged"] = dump() == before
a = call("ue_look", action="apply")
out["twice"] = call("ue_look", action="apply", profile=live_profile(light_units__k=1))
out["generate"] = call("ue_look", action="generate")
print("RESULT", json.dumps(out))
''')
    assert "engine defaults are not the Titan project: run the UE editor leg's profile dump" in d["parity_defaults"]["error"]
    assert "auto exposure adapts per frame: set the volume to Manual for a parity render" in d["auto"]["error"]
    assert "Standard ACES is not replicated yet: judge in UE, or set the volume to Filmic" in d["aces"]["error"]
    assert "regenerate the profile after M-CFG-01 adds this space" in d["space"]["error"]
    assert "area lights are not mapped (LGT-03): convert to spot/point or exclude" in d["area"]["error"]
    assert d["unchanged"] is True
    assert "revert receipt" in d["twice"]["error"] and "first" in d["twice"]["error"]
    assert d["generate"]["ok"] is False and d["generate"]["state"] == "needs_decision"


def test_shd03_backfaces_follow_two_sided_after_apply(tmp_path):
    """T-SHD-03 (SHD-18): after apply every material is culled exactly when its translation says one-sided (two_sided = not the
    original's culling): a one-sided plane seen from behind renders empty, a two-sided one renders. Both through the [UE] copy."""
    d = go(tmp_path, '''
S.render.resolution_x = S.render.resolution_y = 32; S.render.film_transparent = True; S.eevee.taa_render_samples = 4
bpy.ops.mesh.primitive_plane_add(size=2.0); pl = bpy.context.active_object
m = mat("Strip"); pl.data.materials.append(m)
cd = bpy.data.cameras.new("C"); cam = link(bpy.data.objects.new("C", cd)); cam.location = (0, 0, -3); cam.rotation_euler = (math.pi, 0, 0); S.camera = cam
lamp("Key", "SUN", energy=3.0)
def alpha():
    p = os.path.join(root, f"r{len(os.listdir(root))}.exr"); S.render.image_settings.file_format = "OPEN_EXR"; S.render.filepath = p
    bpy.ops.render.render(write_still=True); im = bpy.data.images.load(p)
    a = float(np.array(im.pixels[:]).reshape(-1, 4)[:, 3].mean()); bpy.data.images.remove(im); return a
m.use_backface_culling = False
out = {"base": alpha()}                                                # the original, two-sided, seen from behind
for culling in (True, False):
    m.use_backface_culling = culling
    a = call("ue_look", action="apply")
    out[str(culling)] = {"alpha": alpha(), "two_sided": a["materials"][0]["two_sided"], "slot": pl.material_slots[0].material.name}
    call("ue_look", action="revert", receipt=a["receipt_path"])
print("RESULT", json.dumps(out))
''')
    assert d["True"]["two_sided"] is False and d["True"]["slot"] == "Strip [UE]" and d["True"]["alpha"] < 0.01, d
    assert d["base"] > 0.5 and d["False"]["two_sided"] is True and abs(d["False"]["alpha"] - d["base"]) <= 0.02, d


def test_a_failure_part_way_through_apply_rolls_everything_back(tmp_path):
    d = go(tmp_path, '''
three_lights(); four_materials()
before = dump()
from mixar.modules.lampway_tools.ue import material_group as MG
real = MG.build_preview
calls = []
def flaky(m, tr):
    calls.append(m.name)
    if len(calls) == 3: raise RuntimeError("disk full")
    return real(m, tr)
MG.build_preview = flaky
a = call("ue_look", action="apply")
MG.build_preview = real
print("RESULT", json.dumps({"a": a, "same": dump() == before, "calls": calls, "active": call("ue_look", action="status")["active"]}))
''')
    assert not d["a"]["ok"] and "disk full" in d["a"]["error"] and len(d["calls"]) == 3
    assert d["same"] and d["active"] is False
