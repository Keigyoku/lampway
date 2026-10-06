# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""ue_material, the Blender half (specs/ue_parity/contracts/ue_material.md §6, §10) in the REAL binary, EEVEE only, headless:
the "UE Default Lit" node group shades as UE's legacy Default Lit does (Lambert ADDED to single-scatter GGX, F0 =
lerp(0.08 Specular, BaseColor, Metallic), F90 = saturate(50 F0.g), a DirectX normal with Z rebuilt, masked at 0.3333), and
each render has a control that shows the check can fail (Principled, or the stock decode)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

SCENE = r'''
from mixar.modules.lampway_tools.ue import material_group as MG
S = bpy.context.scene
S.render.engine = "BLENDER_EEVEE"
S.render.resolution_x = S.render.resolution_y = 64
S.render.film_transparent = True
S.render.dither_intensity = 0.0
S.view_settings.view_transform = "Standard"
S.eevee.taa_render_samples = 16
S.eevee.use_fast_gi = False
S.eevee.use_raytracing = False
def world(v):
    w = bpy.data.worlds.new("W"); w.use_nodes = True; S.world = w
    bg = w.node_tree.nodes["Background"]; bg.inputs["Color"].default_value = (v, v, v, 1); bg.inputs["Strength"].default_value = 1.0
def camera(loc=(0, -5, 0), rot=(math.pi / 2, 0, 0), scale=2.4):
    cd = bpy.data.cameras.new("C"); cd.type = "ORTHO"; cd.ortho_scale = scale
    cam = link(bpy.data.objects.new("C", cd)); cam.location = loc; cam.rotation_euler = rot; S.camera = cam
def principled(name, **inputs):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    for k, v in inputs.items():
        b.inputs[k.replace("_", " ")].default_value = v
    return m
def ball(mat):
    ob = sphere("Ball", radius=1.0, subdiv=6)
    for p in ob.data.polygons: p.use_smooth = True
    ob.data.materials.append(mat)
    return ob
def render(path):
    S.render.image_settings.file_format = "OPEN_EXR"; S.render.image_settings.color_depth = "32"; S.render.filepath = path
    bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(path)
    w, h = im.size
    px = np.array(im.pixels[:], dtype=np.float64).reshape(h, w, 4)[::-1]
    bpy.data.images.remove(im)
    return px
yy, xx = np.mgrid[0:64, 0:64] + 0.5
R_PX = 64 / 2.4
rr = np.hypot(xx - 32, yy - 32) / R_PX
def disc(px, lo, hi):
    m = (rr >= lo) & (rr < hi) & (px[..., 3] > 0.99)
    return px[m][:, :3].mean(axis=0).tolist()
def preview(mat):
    res = MG.preview(mat.name, profile=None)
    assert res["ok"], res
    return bpy.data.materials[res["preview_material"]]
'''


def go(tmp_path, body):
    r = run(tmp_path, SCENE + body, timeout=600)
    assert r.rc == 0, r.out[-3000:]
    return r.results[0]


def test_shd01_white_furnace_matches_single_scatter_and_principled_does_not(tmp_path):
    """T-SHD-01: metallic 1, BaseColor white, roughness 0.5 / 0.75 / 1.0 under a uniform world of 1: the group's centre (N.V ~ 1)
    is the single-scatter albedo 0.895 / 0.604 / 0.307 (SCR/ggx_energy.json), Principled (multiscatter) stays ~1."""
    d = go(tmp_path, '''
world(1.0); camera()
out = {}
for r in (0.5, 0.75, 1.0):
    for o in list(bpy.data.objects):
        if o.type == "MESH": bpy.data.objects.remove(o)
    m = principled(f"Metal{r}", Base_Color=(1, 1, 1, 1), Metallic=1.0, Roughness=r)
    ob = ball(m)
    p = render(os.path.join(root, f"p{r}.exr"))
    ob.data.materials[0] = preview(m)
    g = render(os.path.join(root, f"g{r}.exr"))
    out[str(r)] = {"principled": disc(p, 0, 0.3), "group": disc(g, 0, 0.3)}
print("RESULT", json.dumps(out))
''')
    for r, want in (("0.5", 0.895), ("0.75", 0.604), ("1.0", 0.307)):
        g, p = d[r]["group"], d[r]["principled"]
        assert all(abs(c - want) <= 0.05 for c in g), (r, g, want)
        assert all(abs(c - 1.0) <= 0.05 for c in p), (r, p)


def test_shd02_specular_shadowing_darkens_the_edge_of_a_low_green_metal(tmp_path):
    """T-SHD-02: metal BaseColor (0.9, 0.01, 0.01): UE's F90 = saturate(50 * 0.01) = 0.5, so the grazing (rim) reflectance in
    green is about half of Principled's F90 = 1."""
    d = go(tmp_path, '''
world(1.0); camera()
m = principled("Red", Base_Color=(0.9, 0.01, 0.01, 1), Metallic=1.0, Roughness=0.1)
ob = ball(m)
p = render(os.path.join(root, "p.exr"))
ob.data.materials[0] = preview(m)
g = render(os.path.join(root, "g.exr"))
print("RESULT", json.dumps({"p_rim": disc(p, 0.93, 1.0), "g_rim": disc(g, 0.93, 1.0), "p_mid": disc(p, 0, 0.3), "g_mid": disc(g, 0, 0.3)}))
''')
    ratio = d["g_rim"][1] / d["p_rim"][1]
    assert abs(ratio - 0.5) <= 0.1, d
    assert abs(d["g_mid"][0] - d["p_mid"][0]) <= 0.05, d                      # face-on red is F0 in both: only the edge differs


PLANE = r'''
def plane(mat, size=2.0):
    bpy.ops.mesh.primitive_plane_add(size=size); ob = bpy.context.active_object
    ob.data.materials.append(mat); return ob
def image(name, arr):
    h, w = arr.shape[:2]
    im = bpy.data.images.new(name, w, h, float_buffer=True)
    im.colorspace_settings.name = "Non-Color"                       # before the pixels: changing it regenerates a generated image
    rgba = np.dstack([arr, np.ones((h, w, 1))]) if arr.shape[2] == 3 else arr
    im.pixels.foreach_set(rgba.astype(np.float32).ravel())          # row 0 = v 0 (Blender's bottom row)
    im.pack()
    return im
def normal_material(name, img, convention):
    m = principled(name, Base_Color=(1, 1, 1, 1), Roughness=1.0, Specular_IOR_Level=0.0)
    nt = m.node_tree; b = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = img; tex.interpolation = "Closest"
    nm = nt.nodes.new("ShaderNodeNormalMap"); nm.convention = convention
    nt.links.new(tex.outputs["Color"], nm.inputs["Color"]); nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    return m
def sun(direction, strength=1.0):
    ld = bpy.data.lights.new("Sun", "SUN"); ld.energy = strength; ld.angle = 0.0
    ob = link(bpy.data.objects.new("Sun", ld))
    ob.rotation_euler = Vector(direction).to_track_quat("-Z", "Y").to_euler()
    return ob
world(0.0); camera(loc=(0, 0, 5), rot=(0, 0, 0), scale=2.0)
'''


def test_nrm01_directx_bump_lit_from_plus_y_is_bright_on_its_top_edge(tmp_path):
    """T-NRM-01: a dome bump stored DirectX (green = -y), lit from +Y at a grazing angle: with the group (which reads the DX file
    as UE does) the +V half is brighter; the control reads the same file as OpenGL and lights the wrong half."""
    d = go(tmp_path, PLANE + '''
n = 64; v, u = (np.mgrid[0:n, 0:n] + 0.5) / n
x, y = (u - 0.5) * 2.2, (v - 0.5) * 2.2
inside = x * x + y * y < 1
z = np.sqrt(np.clip(1 - x * x - y * y, 0, 1))
nx, ny, nz = np.where(inside, x * 0.7, 0), np.where(inside, y * 0.7, 0), 1.0
ln = np.sqrt(nx * nx + ny * ny + nz * nz); nx, ny, nz = nx / ln, ny / ln, nz / ln
dx = np.dstack([nx * 0.5 + 0.5, -ny * 0.5 + 0.5, nz * 0.5 + 0.5])           # DirectX: green holds -y
img = image("BumpDX", dx)
sun((0, -1, -0.35), strength=3.0)                                      # travels toward -Y: lit FROM +Y
ob = plane(normal_material("Wrong", img, "OPENGL"))
ctl = render(os.path.join(root, "ctl.exr"))
grp = plane(normal_material("Src", img, "DIRECTX")); bpy.data.objects.remove(ob)
grp.data.materials[0] = preview(bpy.data.materials["Src"])
g = render(os.path.join(root, "g.exr"))
def halves(px):
    top = px[16:30, 20:44, :3].mean(); bottom = px[34:48, 20:44, :3].mean(); return [float(top), float(bottom)]
print("RESULT", json.dumps({"group": halves(g), "control": halves(ctl)}))
''')
    assert d["group"][0] > d["group"][1] * 1.2, d                     # top (+V, toward the light) brighter
    assert d["control"][0] < d["control"][1], d                       # the OpenGL reading of the DX file lights the other half


def test_nrm02_z_is_rebuilt_from_rg_as_ue_does(tmp_path):
    """T-NRM-02: a constant texel (0.75, 0.75, 0.5) is not unit length. UE reads x = y = 0.5 and rebuilds z = sqrt(1 - 0.5) = 0.707;
    a sun along the plane normal then lights it at N.L = 0.707 of a flat texel. Blender's stock decode (normalised (0.5, -0.5, 0))
    puts the normal IN the plane: N.L ~ 0."""
    d = go(tmp_path, PLANE + '''
n = 8
odd = image("Odd", np.full((n, n, 3), (0.75, 0.75, 0.5)))
flat = image("Flat", np.full((n, n, 3), (0.5, 0.5, 1.0)))
sun((0, 0, -1), strength=3.0)
a = plane(normal_material("OddSrc", odd, "DIRECTX")); a.data.materials[0] = preview(bpy.data.materials["OddSrc"])
odd_px = render(os.path.join(root, "odd.exr"))[24:40, 24:40, :3].mean()
bpy.data.objects.remove(a)
b = plane(normal_material("FlatSrc", flat, "DIRECTX")); b.data.materials[0] = preview(bpy.data.materials["FlatSrc"])
flat_px = render(os.path.join(root, "flat.exr"))[24:40, 24:40, :3].mean()
b.data.materials[0] = bpy.data.materials["OddSrc"]
stock_px = render(os.path.join(root, "stock.exr"))[24:40, 24:40, :3].mean()
print("RESULT", json.dumps({"ratio": float(odd_px / flat_px), "stock_ratio": float(stock_px / flat_px)}))
''')
    assert abs(d["ratio"] - 0.7071) <= 0.02, d
    assert d["stock_ratio"] < 0.2, d


def test_mat05_masked_alpha_cuts_at_one_third_and_dithered_principled_does_not(tmp_path):
    """T-MAT-05: alpha = U across a plane; the material is Masked (alpha linked, dithered): the group cuts at 0.3333 with no partial
    alpha away from the edge; the Principled control renders the gradient."""
    d = go(tmp_path, PLANE + '''
S.render.filter_size = 0.0
m = principled("Grad", Base_Color=(1, 1, 1, 1))
nt = m.node_tree; tc = nt.nodes.new("ShaderNodeTexCoord"); sx = nt.nodes.new("ShaderNodeSeparateXYZ")
nt.links.new(tc.outputs["UV"], sx.inputs[0]); nt.links.new(sx.outputs["X"], nt.nodes["Principled BSDF"].inputs["Alpha"])
world(1.0)
ob = plane(m, size=2.0)
ctl = render(os.path.join(root, "ctl.exr"))[32, :, 3]
ob.data.materials[0] = preview(m)
g = render(os.path.join(root, "g.exr"))[32, :, 3]
print("RESULT", json.dumps({"group": g.tolist(), "control": ctl.tolist()}))
''')
    g, c = d["group"], d["control"]
    edge = next(i for i, a in enumerate(g) if a >= 0.5)
    assert abs(edge - 64 / 3) <= 1.5, edge
    assert all(a <= 0.01 for a in g[:edge - 2]) and all(a >= 0.99 for a in g[edge + 2:]), g
    assert sum(1 for a in c if 0.1 < a < 0.9) > 20, c                  # the control really is a gradient


def test_ue_material_tool_report_and_preview_through_the_api(tmp_path):
    d = go(tmp_path, '''
m = principled("Chest", Base_Color=(1.2, 0.4, 0.1, 1), Metallic=1.0, Roughness=0.35, Sheen_Weight=0.2)
rep = call("ue_material", material="Chest", mode="report")
rep2 = call("ue_material", material="Chest", mode="report")
pre = call("ue_material", material="Chest", mode="preview")
bad = call("ue_material", material="Nope", mode="report")
print("RESULT", json.dumps({"rep": rep, "same": rep["translation_sha256"] == rep2["translation_sha256"], "pre": pre, "bad": bad,
                            "mats": sorted(bpy.data.materials.keys()), "groups": sorted(g.name for g in bpy.data.node_groups),
                            "orig_untouched": bpy.data.materials["Chest"].node_tree.nodes["Material Output"].inputs["Surface"].links[0].from_node.type}))
''')
    rep, pre = d["rep"], d["pre"]
    assert rep["ok"] and d["same"] and rep["ue"]["vectors"]["BaseColor"][:3] == [1.0, 0.4, 0.1] and rep["dropped"][0]["input"] == "Sheen Weight"
    assert pre["ok"] and pre["preview_material"] == "Chest [UE]" and "Chest [UE]" in d["mats"] and "LW_UE_DefaultLit_v1" in d["groups"]
    assert d["orig_untouched"] == "BSDF_PRINCIPLED"                   # the original keeps its Principled output
    assert not d["bad"]["ok"] and "no material named 'Nope'" in d["bad"]["error"]
