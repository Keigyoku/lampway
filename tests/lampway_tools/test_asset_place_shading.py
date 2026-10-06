# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""asset_place, the shading kinds (real binary): a material appended onto a slot (never silently over a Mixar Paint material), a PBR set wired
by role with the DX green flip honoured, a node group dropped into a material's tree, an HDRI set as the world."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from asset_place_support import go, one  # noqa: E402


def test_place_blend_material_assigns_to_slot_and_keeps_existing_layer_material_unless_replace(tmp_path):
    d = one(go(tmp_path, f'''
lib = {str(tmp_path / "bronze.blend")!r}
write_blend(lib, [material("Bronze"), material("Other", (0.1, 0.1, 0.1))])
bpy.ops.mesh.primitive_cube_add(); cube = bpy.context.active_object
r = place(asset=rec("material", lib, role="blend", subtype="procedural", name="Bronze"), mode="auto", target={{"where": "slot:" + cube.name + ":0"}})
m = cube.material_slots[0].material
plain = {{"r": r, "mat": m.name, "props": {{k: str(m[k]) for k in m.keys() if k.startswith("lw_")}}, "others": sorted(x.name for x in bpy.data.materials)}}
# a Mixar Paint material on the second cube's slot: a group node whose tree is flagged as the MPaint node
bpy.ops.mesh.primitive_cube_add(location=(3, 0, 0)); c2 = bpy.context.active_object
paint = bpy.data.materials.new("Layers"); paint.use_nodes = True
g = bpy.data.node_groups.new("MPaint", "ShaderNodeTree"); g.mp.is_mpaint_node = True
paint.node_tree.nodes.new("ShaderNodeGroup").node_tree = g
c2.data.materials.append(paint)
kept = place(asset=rec("material", lib, role="blend", subtype="procedural", name="Bronze"), mode="assign_material", target={{"where": "slot:" + c2.name + ":0"}})
still = c2.material_slots[0].material.name
rep = place(asset=rec("material", lib, role="blend", subtype="procedural", name="Bronze"), mode="assign_material", target={{"where": "slot:" + c2.name + ":0"}}, options={{"replace": True}})
lamp = bpy.data.lights.new("L", "POINT"); lob = bpy.data.objects.new("Lamp", lamp); bpy.context.scene.collection.objects.link(lob)
no_mesh = place(asset=rec("material", lib, role="blend", subtype="procedural", name="Bronze"), mode="assign_material", target={{"where": "slot:Lamp:0"}})
print("RESULT", json.dumps({{**plain, "kept": kept, "still": still, "rep": rep, "after_rep": c2.material_slots[0].material.name, "no_mesh": no_mesh}}))
'''))
    assert d["r"]["ok"] and d["r"]["mode_used"] == "assign_material", d["r"]
    assert d["mat"] == "Bronze" and "Other" not in d["others"], d
    assert d["props"]["lw_asset_id"] == "asset-1" and d["props"]["lw_asset_sha256"] == "ab" * 32
    assert d["kept"]["ok"] is False and "object already has a Mixar Paint material: pass replace:true" in d["kept"]["error"]
    assert d["still"] == "Layers"
    assert d["rep"]["ok"] and d["after_rep"].startswith("Bronze"), d
    assert d["no_mesh"]["ok"] is False and "pick a mesh object with a material slot" in d["no_mesh"]["error"]


PBR = '''
d = {tmp!r}
png(d + "/bc.png", rgba=(0.8, 0.6, 0.4, 1.0))
png(d + "/orm.png", rgba=(1.0, 0.35, 0.9, 1.0), noncolor=True)
png(d + "/n_gl.png", rgba=(0.5, 0.85, 0.6, 1.0), noncolor=True)       # tilted toward +Y in OpenGL's convention
png(d + "/n_dx.png", rgba=(0.5, 0.15, 0.6, 1.0), noncolor=True)       # the same surface in DirectX's (green inverted)
def pbr(normal_sub, normal_file, name):
    r = rec("material", d + "/bc.png", subtype="pbr_set", name=name, aid="set-" + name)
    r["files"] = []
    r["members"] = [map_rec("basecolor", d + "/bc.png"), map_rec("orm", d + "/orm.png"), map_rec(normal_sub, d + "/" + normal_file)]
    return r
'''


def test_assign_maps_wires_orm_channels_and_flips_dx_normal(tmp_path):
    d = one(go(tmp_path, PBR.format(tmp=str(tmp_path)) + '''
bpy.ops.mesh.primitive_plane_add(size=2.0); plane = bpy.context.active_object
r = place(asset=pbr("normal_dx", "n_dx.png", "SetDX"), mode="auto", target={"where": "slot:" + plane.name + ":0"})
m = plane.material_slots[0].material
nt = m.node_tree
bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
def src(sock):
    l = sock.links[0] if sock.is_linked else None
    return (l.from_node.type, l.from_socket.name) if l else None
def upstream_images(node, seen=None):
    seen = seen or set()
    out = []
    for i in node.inputs:
        for l in i.links:
            n = l.from_node
            if n.name in seen:
                continue
            seen.add(n.name)
            if n.type == "TEX_IMAGE":
                out.append((os.path.basename(n.image.filepath), n.image.colorspace_settings.name))
            out += upstream_images(n, seen)
    return out
print("RESULT", json.dumps({"r": r, "mode": r.get("mode_used"), "base": src(bsdf.inputs["Base Color"]),
    "rough": src(bsdf.inputs["Roughness"]), "metal": src(bsdf.inputs["Metallic"]), "normal": src(bsdf.inputs["Normal"]),
    "images": sorted(set(upstream_images(bsdf))), "img_props": sorted({str(n.image.get("lw_asset_id")) for n in nt.nodes if n.type == "TEX_IMAGE"})}))
''', timeout=300))
    assert d["r"]["ok"] and d["mode"] == "assign_maps", d["r"]
    assert d["base"] == ["TEX_IMAGE", "Color"]
    assert d["rough"] == ["SEPARATE_COLOR", "Green"] and d["metal"] == ["SEPARATE_COLOR", "Blue"], d
    assert d["normal"] == ["NORMAL_MAP", "Normal"]
    assert ["bc.png", "sRGB"] in d["images"] and ["orm.png", "Non-Color"] in d["images"] and ["n_dx.png", "Non-Color"] in d["images"], d["images"]
    assert d["img_props"] == ["map-basecolor", "map-normal_dx", "map-orm"]


def test_dx_normal_renders_like_its_gl_twin_and_unflipped_it_would_not(tmp_path):
    """The falsifier: the DX set and the GL set describe one surface, so lit renders agree; the DX map read as GL (no flip) does not."""
    d = one(go(tmp_path, PBR.format(tmp=str(tmp_path)) + '''
sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.samples = 4; sc.cycles.seed = 1; sc.cycles.device = "CPU"
sc.render.resolution_x = sc.render.resolution_y = 16; sc.render.resolution_percentage = 100
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam")); sc.collection.objects.link(cam); cam.location = (0, 0, 3); sc.camera = cam
sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN")); sc.collection.objects.link(sun)
sun.rotation_euler = (-1.0, 0, 0); sun.data.energy = 3.0
bpy.ops.mesh.primitive_plane_add(size=4.0); plane = bpy.context.active_object
def shot(asset, tag):
    plane.data.materials.clear()
    r = place(asset=asset, mode="assign_maps", target={"where": "slot:" + plane.name + ":0"})
    assert r["ok"], r
    sc.render.filepath = d + "/" + tag + ".png"
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(sc.render.filepath)
    px = list(img.pixels)
    return sum(px[0::4]) / (len(px) / 4)
gl = shot(pbr("normal_gl", "n_gl.png", "GL"), "gl")
dx = shot(pbr("normal_dx", "n_dx.png", "DX"), "dx")
wrong = shot(pbr("normal_gl", "n_dx.png", "WRONG"), "wrong")
print("RESULT", json.dumps({"gl": gl, "dx": dx, "wrong": wrong}))
''', timeout=400))
    assert abs(d["gl"] - d["dx"]) < 0.01 * max(d["gl"], 1e-3), d
    assert abs(d["gl"] - d["wrong"]) > 0.05 * max(d["gl"], 1e-3), d


def test_add_node_group_into_a_material_tree_wires_only_an_empty_tree(tmp_path):
    d = one(go(tmp_path, f'''
lib = {str(tmp_path / "groups.blend")!r}
write_blend(lib, [node_group("Rust")])
empty = bpy.data.materials.new("Empty"); empty.use_nodes = True
for n in list(empty.node_tree.nodes):
    if n.type != "OUTPUT_MATERIAL":
        empty.node_tree.nodes.remove(n)
full = material("Full")
r1 = place(asset=rec("material", lib, role="blend", subtype="procedural", name="Rust"), mode="add_node_group", target={{"where": "node_tree:Empty"}}, options={{"location": [-300, 40]}})
r2 = place(asset=rec("material", lib, role="blend", subtype="procedural", name="Rust"), mode="add_node_group", target={{"where": "node_tree:Full"}})
r3 = place(asset=rec("material", lib, role="blend", subtype="procedural", name="Rust"), mode="add_node_group", target={{"where": "node_tree:Nope"}})
def info(m):
    g = [n for n in m.node_tree.nodes if n.type == "GROUP"]
    out = next(n for n in m.node_tree.nodes if n.type == "OUTPUT_MATERIAL")
    l = out.inputs["Surface"].links
    return {{"groups": [(n.node_tree.name, list(n.location)) for n in g], "surface_from": l[0].from_node.type if l else None,
            "lw": [str(n.node_tree.get("lw_asset_id")) for n in g]}}
print("RESULT", json.dumps({{"r1": r1, "r2": r2, "r3": r3, "empty": info(empty), "full": info(full), "groups": sorted(g.name for g in bpy.data.node_groups if g.name.startswith("Rust"))}}))
'''))
    assert d["r1"]["ok"] and d["r1"]["mode_used"] == "add_node_group", d["r1"]
    assert d["empty"]["groups"][0][0] == "Rust" and d["empty"]["groups"][0][1] == [-300.0, 40.0]
    assert d["empty"]["surface_from"] == "GROUP" and d["empty"]["lw"] == ["asset-1"]
    assert d["r2"]["ok"] and d["full"]["surface_from"] == "BSDF_PRINCIPLED" and len(d["full"]["groups"]) == 1
    assert d["groups"] == ["Rust"], "the second drop reuses the appended group"
    assert d["r3"]["ok"] is False and "no material named 'Nope'" in d["r3"]["error"]


def test_place_hdri_sets_the_world_environment(tmp_path):
    d = one(go(tmp_path, f'''
p = {str(tmp_path / "sky.png")!r}
png(p, rgba=(0.2, 0.4, 0.9, 1.0))
r = place(asset=rec("hdri", p, subtype="sky", name="Sky"), mode="auto")
w = bpy.context.scene.world
nt = w.node_tree
bg = next(n for n in nt.nodes if n.type == "BACKGROUND")
l = bg.inputs["Color"].links
env = l[0].from_node if l else None
print("RESULT", json.dumps({{"r": r, "env": env.type if env else None, "img": os.path.basename(env.image.filepath) if env else None,
                            "world_lw": str(w.get("lw_asset_id")), "img_lw": str(env.image.get("lw_asset_id")) if env else None}}))
'''))
    assert d["r"]["ok"] and d["r"]["mode_used"] == "set_world", d["r"]
    assert d["env"] == "TEX_ENVIRONMENT" and d["img"] == "sky.png"
    assert d["world_lw"] == "asset-1" and d["img_lw"] == "asset-1"
