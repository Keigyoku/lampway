# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/meshqa/mesh_qa.py, SPIKE 2026-10-04) on 2026-10-05. The analysis is now
# mixar.modules.lampway_tools.meshqa.candidates (shared with the live operators); this command-line tool keeps the
# FBX import, the review renders and the files. Two kinds of candidate:
#   open_loop   - connected boundary edges (after a weld by distance) of at least --min-perimeter; a loop that borders
#                 several parts is split per part when giant (one giant boundary on the Tripo chest was 2,264 edges joining every hem);
#   loose_shell - a mesh shell of at most --max-shell-tris whose nearest other shell is further than --float-mm (it floats).
# Each candidate gets a typed descriptor (geometry, bordering parts and their motion classes, which side of the body, which
# standard views see it, what a ray through it hits behind) and two renders: a crop facing it and a whole-piece locator, faces
# coloured by part, back faces magenta (a magenta patch seen through a loop = a hole you can see into), the candidate yellow.
# The renders are deliberately not the textured look: part colours make a mislabel and a see-through hole obvious.
# Measured 2026-10-04 on chest seed 9c052d49: 321 boundary loops; 152 are 8-edge loops (rivet bases, open by design, hidden on
# the plate) - the perimeter floor drops them; 62 loops are >= 0.15 m.
# blender -b -P mesh_qa.py -- <mesh.fbx> <owner_poly.npy> <recipe.json> <out_dir> [--turn -90] [--min-perimeter 0.15]
#        [--max-shell-tris 400] [--float-mm 3] [--delete-polys deletions.json] [--no-render]
#   deletions.json: {"polys": [...]} faces already ruled deleted (original indices); removed before the analysis
# Writes out_dir/candidates.json (descriptors; loops carry segments_m, shells orig_polys, for drawing the marks elsewhere) and
# out_dir/img/<id>.png (crop) + <id>_loc.png (locator).
# --- AXI prelude (tools/AXI.md): no args shows what this is; too few args or an unknown flag refuses on stdout (script runs only, never on import) ---
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
_A = (_sys.argv[_sys.argv.index('--') + 1:] if '--' in _sys.argv else [])
if __name__ == '__main__' and len(_A) < 4:
    if not _A: _ax.home(__file__, 'Mesh QA candidates (open loops, floating shells) with typed descriptors and review renders')
    else: print(f'error: {len(_A)} argument(s); at least 4 needed')
    _ax.helps(['blender -b -P scripts/meshqa/mesh_qa.py -- <mesh.fbx> <owner_poly.npy> <recipe.json> <out_dir> [--turn -90]']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
# --- end AXI prelude ---
import argparse, bpy, json, math, colorsys, os, numpy as np
from mathutils import Vector
from mixar.modules.lampway_tools.meshqa import candidates as C
ap = argparse.ArgumentParser(prog='mesh_qa.py'); [ap.add_argument(k) for k in ('mesh', 'owner', 'recipe', 'out')]
ap.add_argument('--turn', type=float, default=0.0); ap.add_argument('--min-perimeter', type=float, default=0.15)
ap.add_argument('--max-shell-tris', type=int, default=400); ap.add_argument('--float-mm', type=float, default=3.0)
ap.add_argument('--delete-polys', default=None); ap.add_argument('--no-render', action='store_true', help='descriptors only - no EEVEE renders (light, for when the captain works live)')
a = ap.parse_args(_A); os.makedirs(os.path.join(a.out, 'img'), exist_ok=True)
rec = json.load(open(a.recipe)); names = list(rec['parts']); own = np.load(a.owner)
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.fbx(filepath=a.mesh)
ob = next(o for o in bpy.data.objects if o.type == 'MESH'); me = ob.data
if len(own) != len(me.polygons): _ax.refuse(f'owner has {len(own)} labels for {len(me.polygons)} polygons', [])
ob.rotation_euler[2] += math.radians(a.turn); bpy.context.view_layer.update()
dele = json.load(open(a.delete_polys))['polys'] if a.delete_polys else []
prep = C.prepare(me, ob.matrix_world.copy(), own, delete_polys=dele)
cands = C.analyse(prep, rec, C.Params(a.min_perimeter, a.max_shell_tris, a.float_mm))
bm, fpart = prep.bm, prep.fpart
center = np.array([v.co[:] for v in bm.verts]).mean(0)
# ---- renders: the welded mesh back onto the object, part colours, the candidate in yellow
bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True); bpy.context.view_layer.objects.active = ob
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
me.clear_geometry(); bm.to_mesh(me); me.update()
for i, p in enumerate(me.polygons): p.material_index = int(fpart[i])
bm.faces.ensure_lookup_table(); bm.edges.ensure_lookup_table()
for kk, nm in enumerate(names):
    m = bpy.data.materials.new(nm); m.use_nodes = True; nt = m.node_tree; b = nt.nodes['Principled BSDF']
    col = (*colorsys.hsv_to_rgb((kk * 0.618) % 1, 0.5 if kk % 2 else 0.7, 0.85 if kk % 3 else 0.7), 1)
    geo = nt.nodes.new('ShaderNodeNewGeometry'); mx = nt.nodes.new('ShaderNodeMix'); mx.data_type = 'RGBA'
    nt.links.new(geo.outputs['Backfacing'], mx.inputs['Factor']); mx.inputs[6].default_value = col; mx.inputs[7].default_value = (1, 0, 1, 1)
    nt.links.new(mx.outputs[2], b.inputs['Base Color']); b.inputs['Roughness'].default_value = 0.85; me.materials.append(m)
sc = bpy.context.scene; sc.render.engine = 'BLENDER_EEVEE' if 'BLENDER_EEVEE' in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items] else 'BLENDER_EEVEE_NEXT'
w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True; w.node_tree.nodes['Background'].inputs['Color'].default_value = (0.05, 0.05, 0.06, 1); w.node_tree.nodes['Background'].inputs['Strength'].default_value = 1.0
for nm_, rot in (('k', (50, 0, 30)), ('f', (60, 0, 200)), ('t', (0, 0, 0))):
    Ld = bpy.data.lights.new(nm_, 'SUN'); Ld.energy = 3.0 if nm_ == 'k' else 1.2; lo = bpy.data.objects.new(nm_, Ld); sc.collection.objects.link(lo); lo.rotation_euler = [math.radians(x) for x in rot]
ym = bpy.data.materials.new('mark'); ym.use_nodes = True; bb = ym.node_tree.nodes['Principled BSDF']; bb.inputs['Base Color'].default_value = (1, 0.9, 0, 1); bb.inputs['Emission Color'].default_value = (1, 0.9, 0, 1); bb.inputs['Emission Strength'].default_value = 4
cam = bpy.data.cameras.new('c'); co = bpy.data.objects.new('c', cam); sc.collection.objects.link(co); sc.camera = co; cam.type = 'ORTHO'; cam.clip_end = 20
sc.render.resolution_x = sc.render.resolution_y = 640; sc.render.film_transparent = False
shell_of = {}
def mark_obj(c):
    vv, ee, ff = [], [], []
    if c['kind'] == 'open_loop':
        for p0, p1 in c['segments_m']:
            j = len(vv); vv += [p0, p1]; ee.append((j, j + 1))
        mm = bpy.data.meshes.new('mk'); mm.from_pydata(vv, ee, []); o = bpy.data.objects.new('mk', mm); sc.collection.objects.link(o)
        o.modifiers.new('s', 'SKIN')
        r_ = max(0.0015, min(0.004, max(c['extent_m']) / 120))
        for sv in mm.skin_vertices[0].data: sv.radius = (r_, r_)
    else:
        src = set(c['orig_polys'])
        for f in bm.faces:
            if prep.forig[f.index] in src:
                j = len(vv); vv += [v.co[:] for v in f.verts]; ff.append(tuple(range(j, j + len(f.verts))))
        mm = bpy.data.meshes.new('mk'); mm.from_pydata(vv, [], ff); o = bpy.data.objects.new('mk', mm); sc.collection.objects.link(o)
        md = o.modifiers.new('d', 'DISPLACE'); md.strength = 0.0008
    mm.materials.append(ym); return o
for c in ([] if a.no_render else cands):
    o = mark_obj(c); n = Vector(c['facing']); ctr = Vector(c['centroid_m'])
    for tag, scale, dist in (('', max(max(c['extent_m']) * 1.7, 0.08), 1.2), ('_loc', 1.25, 3.0)):
        cam.ortho_scale = scale; co.location = (ctr if tag == '' else Vector((center[0], center[1], center[2]))) + n * dist
        tgt = ctr if tag == '' else Vector((center[0], center[1], center[2]))
        co.rotation_euler = (tgt - co.location).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(a.out, 'img', f"{c['id']}{tag}.png"); bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(o)
json.dump({'mesh': a.mesh, 'owner': a.owner, 'recipe': a.recipe, 'turn': a.turn, 'deleted_before': a.delete_polys, 'frame': '-y front, +x the body left after --turn',
           'candidates': cands}, open(os.path.join(a.out, 'candidates.json'), 'w'), indent=1)
_ax.kv({'candidates': len(cands), 'open_loops': sum(c['kind'] == 'open_loop' for c in cands), 'loose_shells': sum(c['kind'] == 'loose_shell' for c in cands), 'out': a.out})
_ax.helps([f'blender -b -P scripts/partseg/patch_holes.py -- {a.mesh} {a.owner} {a.recipe} {a.out}/candidates.json <decisions.jsonl> <out_prefix> --turn {a.turn}'])
