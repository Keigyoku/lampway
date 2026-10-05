# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/texlib/render_textured.py, sha256 1697a22c1f35) on 2026-10-05. The header below, with the
# measured rules behind the code, is the original's; paths and interpreters now come from Lampway's configuration.
# SPIKE (2026-10-04): first textured look of a parts set on its shared atlas - masks (material_masks.py) choose per texel
# between five materials; tiling textures are box-projected in object space (no pattern break at UV seams); the relief
# detail (relief_project.py, exact 16-bit carrier) drives a bump; ambient occlusion darkens recesses and pointiness
# lifts worn edges on the dark plate. Renders fixed views at one exposure.
# blender -b <blend> -P render_textured.py -- <projection_dir> <out_dir> [object]
# --- AXI prelude (tools/AXI.md): no args shows what this is; too few args or an unknown flag refuses on stdout (script runs only, never on import) ---
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
_A = (_sys.argv[_sys.argv.index('--') + 1:] if '--' in _sys.argv else [])
_bad = [] if __name__ != '__main__' else [x for x in _A if x.startswith('--') and x.split('=')[0] not in []]
if _bad: print(f'error: unknown flag(s) {_bad}'); _ax.helps(['blender -b <blend> -P scripts/texlib/render_textured.py -- <projection_dir> <out_dir> [object]']); _sys.stdout.flush(); raise SystemExit(2)
if __name__ == '__main__' and len(_A) < 2:
    if not _A: _ax.home(__file__, 'Textured look of a parts set on its shared atlas (masks choose the material per texel)')
    else: print(f'error: {len(_A)} argument(s); at least 2 needed')
    _ax.helps(['blender -b <blend> -P scripts/texlib/render_textured.py -- <projection_dir> <out_dir> [object]']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
# --- end AXI prelude ---
import bpy, sys, os, json, math
a = sys.argv[sys.argv.index('--') + 1:]; P, OUT = a[0], a[1]; OBJ = a[2] if len(a) > 2 else 'chest_smartmesh_r6'
os.makedirs(OUT, exist_ok=True)
def _need(env, what):                                    # a library path is configuration, never a baked-in shelf path
    v = os.environ.get(env)
    return v if v else _ax.refuse(f'{env} is not set: {what}', [f'export {env}=<path>  (Lampway settings: texture libraries)'])
TEX = _need('LAMPWAY_TILES_DIR', 'the folder holding the <Name>_BaseColor_Tile1024 colour tiles')
ACG = _need('LAMPWAY_AMBIENTCG_DIR', 'the folder holding the ambientCG material folders (Metal009, Metal048C)')
M = {  # material: (colour map, colour multiplier (linear), metallic, roughness map or value, box scale per metre)
    'plate': (f'{ACG}/Metal009/Metal009_2K-PNG_Color.png', (0.42, 0.27, 0.17), 0.9, f'{ACG}/Metal009/Metal009_2K-PNG_Roughness.png', 5.0),   # blackened bronze: metallic, dark brown base, so reflections come back brown, not white
    'gold': (f'{ACG}/Metal048C/Metal048C_2K-PNG_Color.png', (0.92, 0.58, 0.40), 1.0, f'{ACG}/Metal048C/Metal048C_2K-PNG_Roughness.png', 5.0),   # -> ~(0.87, 0.43, 0.13): V3's orange antique gold (H 24-26, S 0.56-0.75)
    'red': (f'{TEX}/Titan_Crimson_Cape_Diamond_Lattice_BaseColor_Tile1024_v0004.png', (1, 1, 1), 0.0, 0.85, 4.0),
    'linen': (f'{TEX}/Titan_Black_Linen_BaseColor_Tile1024_v0004.png', (1, 1, 1), 0.0, 0.9, 8.0),
    'embroidery': (None, (0.85, 0.58, 0.24), 0.85, 0.45, 1.0),
    'leather': (f'{TEX}/Titan_Oxblood_Belt_Leather_BaseColor_Tile1024_v0004.png', (1, 1, 1), 0.0, 0.6, 6.0)}
HDRI = _need('LAMPWAY_HDRI', 'the studio HDRI (.hdr) the render is lit with')
# Opt-in overrides (env RT_OVERRIDES as JSON, recorded in render.json) from the r7 critique: {"plate": {"mul": [r,g,b], "metal": x},
# "gold": {"mul": [...], "metal": x, "rough_floor": x}, "embroidery": {"mul": [...], "rough": x}, "proj_blend": x, "hdri_strength": x}
OV = json.loads(os.environ.get('RT_OVERRIDES', '{}'))
for _k, _o in OV.items():
    if _k in M:
        cm_, mu_, me_, ro_, bx_ = M[_k]; M[_k] = (cm_, tuple(_o.get('mul', mu_)), _o.get('metal', me_), _o.get('rough', ro_), _o.get('box', bx_))
PROJ_BLEND = float(OV.get('proj_blend', 0.25)); ROUGH_FLOOR = {k: o['rough_floor'] for k, o in OV.items() if isinstance(o, dict) and 'rough_floor' in o}
sc = bpy.context.scene
for o in list(sc.objects): o.hide_render = o.name != OBJ
ob = bpy.data.objects[OBJ]
mat = bpy.data.materials.new('textured_atlas'); mat.use_nodes = True; nt = mat.node_tree; nt.nodes.clear(); N, L = nt.nodes, nt.links
out = N.new('ShaderNodeOutputMaterial'); bs = N.new('ShaderNodeBsdfPrincipled'); L.new(bs.outputs['BSDF'], out.inputs['Surface'])
uv = N.new('ShaderNodeTexCoord')
def img(path, noncolor=False, box=None):
    t = N.new('ShaderNodeTexImage'); t.image = bpy.data.images.load(path, check_existing=True)
    if noncolor: t.image.colorspace_settings.name = 'Non-Color'
    if box:
        mp = N.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (box, box, box)
        L.new(uv.outputs['Object'], mp.inputs['Vector']); L.new(mp.outputs['Vector'], t.inputs['Vector']); t.projection = 'BOX'; t.projection_blend = PROJ_BLEND
    else: L.new(uv.outputs['UV'], t.inputs['Vector'])
    return t
def const(v):
    n = N.new('ShaderNodeRGB'); n.outputs[0].default_value = (v[0], v[1], v[2], 1); return n.outputs[0]
def mul_col(sock, f):
    m = N.new('ShaderNodeMix'); m.data_type = 'RGBA'; m.blend_type = 'MULTIPLY'; m.inputs['Factor'].default_value = 1
    L.new(sock, m.inputs[6]); m.inputs[7].default_value = (f[0], f[1], f[2], 1); return m.outputs[2]
def mix(fac, s_a, s_b, kind='RGBA'):
    m = N.new('ShaderNodeMix'); m.data_type = kind; L.new(fac, m.inputs['Factor'])
    ia, ib, o = (6, 7, 2) if kind == 'RGBA' else (2, 3, 0)
    for sock, i in ((s_a, ia), (s_b, ib)):
        if isinstance(sock, (int, float)): m.inputs[i].default_value = sock
        else: L.new(sock, m.inputs[i])
    return m.outputs[o]
masks = {k: img(os.path.join(P, f'mask_{k}.png'), True).outputs['Color'] for k in M}
col = rough = met = None
for k, (cmap, mulf, metal, r, box) in M.items():
    c = mul_col(img(cmap, False, box).outputs['Color'], mulf) if cmap else const(mulf)
    rr = img(r, True, box).outputs['Color'] if isinstance(r, str) else r
    if k in ROUGH_FLOOR and not isinstance(rr, (int, float)):            # clamp the roughness map from below (gold hot spots)
        mx_ = N.new('ShaderNodeMath'); mx_.operation = 'MAXIMUM'; L.new(rr, mx_.inputs[0]); mx_.inputs[1].default_value = ROUGH_FLOOR[k]; rr = mx_.outputs[0]
    if col is None: col, rough, met = c, rr, metal; continue
    col = mix(masks[k], col, c); rough = mix(masks[k], rough, rr, 'FLOAT'); met = mix(masks[k], met, metal, 'FLOAT')
ao = N.new('ShaderNodeAmbientOcclusion'); ao.inputs['Distance'].default_value = 0.03; ao.samples = 16
dirt = N.new('ShaderNodeMath'); dirt.operation = 'MULTIPLY_ADD'; L.new(ao.outputs['AO'], dirt.inputs[0]); dirt.inputs[1].default_value = -0.5; dirt.inputs[2].default_value = 0.5   # (1 - AO) x 0.5: recesses darken (it was inverted)
cm = N.new('ShaderNodeMix'); cm.data_type = 'RGBA'; cm.blend_type = 'MULTIPLY'; L.new(dirt.outputs[0], cm.inputs['Factor'])
L.new(col, cm.inputs[6]); cm.inputs[7].default_value = (0.35, 0.3, 0.27, 1)
geo = N.new('ShaderNodeNewGeometry'); ramp = N.new('ShaderNodeMapRange'); L.new(geo.outputs['Pointiness'], ramp.inputs[0]); ramp.inputs[1].default_value = 0.52; ramp.inputs[2].default_value = 0.62
wear = N.new('ShaderNodeMath'); wear.operation = 'MULTIPLY'; L.new(ramp.outputs[0], wear.inputs[0]); L.new(masks['plate'], wear.inputs[1])
worn = cm.outputs[2]                                                   # edge wear off: pointiness lit every detailed plate grey (pass 5)
L.new(worn, bs.inputs['Base Color']); L.new(rough, bs.inputs['Roughness']); L.new(met, bs.inputs['Metallic'])
cloth = N.new('ShaderNodeMath'); cloth.operation = 'ADD'; L.new(masks['red'], cloth.inputs[0]); L.new(masks['linen'], cloth.inputs[1])
sw = N.new('ShaderNodeMath'); sw.operation = 'MULTIPLY'; L.new(cloth.outputs[0], sw.inputs[0]); sw.inputs[1].default_value = 0.12
L.new(sw.outputs[0], bs.inputs['Sheen Weight']); bs.inputs['Sheen Roughness'].default_value = 0.6; bs.inputs['Sheen Tint'].default_value = (0.8, 0.25, 0.2, 1)
rng = json.load(open(os.path.join(P, 'relief_project.json')))['u16_png_range_m']
h = img(os.path.join(P, 'detail_height_u16.png'), True)
m1 = N.new('ShaderNodeMath'); m1.operation = 'SUBTRACT'; m1.inputs[1].default_value = 0.5; L.new(h.outputs['Color'], m1.inputs[0])
m2 = N.new('ShaderNodeMath'); m2.operation = 'MULTIPLY'; m2.inputs[1].default_value = 2 * rng; L.new(m1.outputs[0], m2.inputs[0])
bump = N.new('ShaderNodeBump'); bump.inputs['Distance'].default_value = 1.0; L.new(m2.outputs[0], bump.inputs['Height']); L.new(bump.outputs['Normal'], bs.inputs['Normal'])
ob.data.materials.clear(); ob.data.materials.append(mat)
for p in ob.data.polygons: p.material_index = 0
w = bpy.data.worlds.new('tx_world'); sc.world = w; w.use_nodes = True; bg = w.node_tree.nodes['Background']
env = w.node_tree.nodes.new('ShaderNodeTexEnvironment'); env.image = bpy.data.images.load(HDRI); w.node_tree.links.new(env.outputs['Color'], bg.inputs['Color']); bg.inputs['Strength'].default_value = float(OV.get('hdri_strength', 0.8))
sc.render.film_transparent = True   # the studio HDRI lights and reflects; the backdrop is composited dark
for name, rot, e in (('key', (55, 0, -35), 2.5), ('rim', (100, 0, 180), 1.5)):
    Ld = bpy.data.lights.new(name, 'SUN'); Ld.energy = e; Ld.angle = math.radians(3); lo = bpy.data.objects.new(name, Ld); sc.collection.objects.link(lo); lo.rotation_euler = [math.radians(v) for v in rot]
cam = bpy.data.cameras.new('tx_cam'); co = bpy.data.objects.new('tx_cam', cam); sc.collection.objects.link(co); sc.camera = co
sc.render.engine = 'CYCLES'; sc.cycles.samples = 128; sc.cycles.use_denoising = True; sc.view_settings.view_transform = 'AgX'
try:
    pr = bpy.context.preferences.addons['cycles'].preferences; pr.compute_device_type = 'CUDA'; pr.get_devices()
    for d in pr.devices: d.use = True
    sc.cycles.device = 'GPU'
except Exception as e: print('GPU unavailable', e)
shots = {'front': ((0, -3.2, 0.55), (90, 0, 0), 1.15, 1100), 'back': ((0, 3.2, 0.55), (90, 0, 180), 1.15, 1100),
         'right': ((-3.2, 0, 0.55), (90, 0, -90), 1.15, 1100), 'lion_breast': ((0.0, -3.2, 0.66), (90, 0, 0), 0.32, 900),
         'pauldron_R': ((-0.42, -3.2, 0.8), (90, 0, 0), 0.36, 900)}
for name, (pos, rot, ortho, r) in shots.items():
    co.location = pos; co.rotation_euler = [math.radians(v) for v in rot]; cam.type = 'ORTHO'; cam.ortho_scale = ortho
    sc.render.resolution_x = sc.render.resolution_y = r; sc.render.filepath = f'{OUT}/{name}.png'
    bpy.ops.render.render(write_still=True); print('RENDER', name)
bpy.ops.wm.save_as_mainfile(filepath=f'{OUT}/textured_scene.blend', copy=True)
