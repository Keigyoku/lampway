# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# The headless Cycles worker of material_bake_export: opens the object the tool wrote (a .blend with its material, node groups and packed images), bakes each requested channel of the material to an image
# on the CPU (EMIT of the Principled input, or NORMAL / AO) and writes the files, plus the packed ORM. Always niced by the runner; never run in the user's live scene.
# blender -b -P material_bake.py -- <object.blend> <args.json> <result.json>
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
_A = (_sys.argv[_sys.argv.index('--') + 1:] if '--' in _sys.argv else [])
if __name__ == '__main__' and len(_A) < 3:
    if not _A: _ax.home(__file__, "Bake a material's channels (base colour, roughness, metallic, normal, AO, emission) to images in headless Cycles")
    else: print(f'error: {len(_A)} argument(s); 3 needed')
    _ax.helps(['blender -b -P scripts/bake/material_bake.py -- <object.blend> <args.json> <result.json>']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
import json, os, bpy, numpy as np
BLEND, ARGS, OUT = _A[:3]
a = json.load(open(ARGS))
bpy.ops.wm.read_factory_settings(use_empty=True)
with bpy.data.libraries.load(BLEND) as (src, dst):
    dst.objects = list(src.objects)
for o in dst.objects:
    bpy.context.scene.collection.objects.link(o)
ob = bpy.data.objects[a['object']]
sc = bpy.context.scene
sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = a['samples']
sc.cycles.use_denoising = False
if sc.world is None:
    sc.world = bpy.data.worlds.new('bake_world')
size, margin = a['size'], a['margin_px']
FMT = {'png': ('PNG', 'png'), 'exr': ('OPEN_EXR', 'exr'), 'tiff': ('TIFF', 'tif'), 'jpeg': ('JPEG', 'jpg')}[a['format']]
SOCKET = {'base_color': 'Base Color', 'roughness': 'Roughness', 'metallic': 'Metallic', 'emission': 'Emission Color'}
mats = [s.material for s in ob.material_slots if s.material and s.material.use_nodes]
if not mats:
    raise SystemExit('the object has no node material')
bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True); bpy.context.view_layer.objects.active = ob


def principled(nt):
    for n in nt.nodes:
        if n.type == 'BSDF_PRINCIPLED':
            return n
    return None


files, colourspace = {}, {}
for ch in a['channels']:
    srgb = ch in ('base_color', 'emission')
    img = bpy.data.images.new(f"{ob.name}_{ch}", size, size, alpha=False, float_buffer=(a['format'] == 'exr'))
    img.colorspace_settings.name = 'sRGB' if srgb else 'Non-Color'
    colourspace[ch] = img.colorspace_settings.name
    rigs = []
    for m in mats:
        nt = m.node_tree
        tex = nt.nodes.new('ShaderNodeTexImage'); tex.image = img
        for n in nt.nodes:
            n.select = False
        tex.select = True; nt.nodes.active = tex
        rigs.append((nt, tex))
        if ch in SOCKET:
            bsdf = principled(nt)
            if bsdf is None:
                raise SystemExit(f'the material {m.name} has no Principled BSDF to read {ch} from')
            sock = bsdf.inputs[SOCKET[ch]]
            em = nt.nodes.new('ShaderNodeEmission'); mo = nt.nodes.new('ShaderNodeOutputMaterial'); mo.is_active_output = True
            nt.links.new(em.outputs['Emission'], mo.inputs['Surface'])
            if sock.is_linked:
                nt.links.new(sock.links[0].from_socket, em.inputs['Color'])
            else:
                dv = sock.default_value
                em.inputs['Color'].default_value = tuple(dv)[:3] + (1.0,) if hasattr(dv, '__len__') else (dv, dv, dv, 1.0)
            rigs[-1] = (nt, tex, em, mo)
    kw = dict(margin=margin, use_clear=True)
    if ch == 'normal':
        sc.render.bake.normal_r = 'POS_X'; sc.render.bake.normal_g = 'POS_Y' if a['normal_green'] == 'gl' else 'NEG_Y'; sc.render.bake.normal_b = 'POS_Z'
        bpy.ops.object.bake(type='NORMAL', normal_space='TANGENT', **kw)
    elif ch == 'ao':
        sc.world.light_settings.distance = max(float(max(ob.dimensions)) * 0.5, 1e-3)
        bpy.ops.object.bake(type='AO', **kw)
    else:
        bpy.ops.object.bake(type='EMIT', **kw)
    for r in rigs:                                  # take the rig away again: the baked object is a temporary copy, but keep it honest
        nt = r[0]
        for n in r[2:]:
            nt.nodes.remove(n)
        nt.nodes.remove(r[1])
    path = os.path.join(a['out_dir'], f"{ob.name}_{ch}.{FMT[1]}")
    img.filepath_raw = path; img.file_format = FMT[0]
    img.save()
    files[ch] = path
    img.pixels  # keep the pixels alive for the ORM pack below
    if ch in ('roughness', 'metallic', 'ao'):
        files.setdefault('_img', {})[ch] = np.array(img.pixels[:], dtype=np.float32).reshape(size, size, 4)[:, :, 0]
imgs = files.pop('_img', {})
warnings = []
if a['pack'] == 'orm':
    ao = imgs.get('ao')
    if ao is None:
        ao = np.ones((size, size), dtype=np.float32)
        warnings.append('no ao channel was baked: R of the ORM map is filled with 1.0')
    orm = bpy.data.images.new(f"{ob.name}_orm", size, size, alpha=False, float_buffer=(a['format'] == 'exr'))
    orm.colorspace_settings.name = 'Non-Color'
    px = np.ones((size, size, 4), dtype=np.float32)
    px[:, :, 0], px[:, :, 1], px[:, :, 2] = ao, imgs['roughness'], imgs['metallic']
    orm.pixels.foreach_set(px.ravel())
    path = os.path.join(a['out_dir'], f"{ob.name}_orm.{FMT[1]}")
    orm.filepath_raw = path; orm.file_format = FMT[0]
    orm.save()
    files['orm'] = path
    colourspace['orm'] = 'Non-Color'
json.dump({'files': files, 'colourspace': colourspace, 'warnings': warnings}, open(OUT, 'w'))
_ax.kv({'baked': ','.join(files), 'size': size})
