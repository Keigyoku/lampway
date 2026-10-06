# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/partseg/export_parts.py, sha256 96e870b7f7e1) on 2026-10-06. The header below, with the measured rules behind
# the code, is the original's; the runner starts Blender empty, so the first argument is the mesh (mesh_load.py) and the rest are the shelf's; owner-specific defaults
# (file names, folders, the scale sentence) come from the recipe or are generic.
# SPIKE (2026-10-03): export a finished part set as Parts Library candidates - one GLB per part plus part.json.
# Layout: <out>/Parts Library/Candidates/<Item>/<source smart mesh stem>/<part>/v####/{<part>.glb, part.json}
# part.json: id, version, item, source smart mesh (file + Drive sha256), face count, face ids into the source mesh,
# recipe lineage and stages, motion class, bind, scale stage, the held notes keyed to the part, glb sha256. Geometry is
# the source mesh's own faces (positions, UVs, normals untouched); nothing is re-topologised or rescaled at this stage.
# Versions never overwrite: a part whose faces, class, bind and held notes equal its latest version is kept as it is
# (not rewritten); any change writes the next v####. The set file is SET.<set_version>.json and is never overwritten.
# v2 (parts critique round 4, F3/F8): held notes are {note, parts}; a legacy plain-string note still attaches by name.
# v3 (critique-5 G6 + r6 hole repair): recipe lineage is part of the change test; '*' notes reach every part; a
# recipe 'repair' block names the repaired mesh's source face count and its record, and part.json counts repair faces;
# geometry_changed / winding_turned_faces and a per-part geometry sentence (critique-6 H12).
# v4 (critique-7 I2/I9 + repair UVs): the change test also compares the part's triangles corner by corner (positions and
# UVs, as glTF stores them) with its previous version's GLB, so a UV-only change is a new version; turned faces are
# counted source and repair apart; part.json names the repaired mesh (file + sha256) beside the original's.
# K6 (critique 8): a scene object or mesh already holding the part's name is renamed aside for the export and back after,
# so the GLB node and mesh are named exactly the part id (a long-lived session gave .001/.002 names and session-dependent bytes).
# Background: blender -b <votes.blend> -P export_parts.py -- <object> <owner.npy> <recipe.json> <out_dir> <item> <source_sha256> <set_version>
# Live:       exec(open(path).read()); export_set(obj_name, owner, recipe, out, item, src_sha, set_version)
import bpy, bmesh, sys, os, re, json, hashlib, numpy as np

h = lambda p: hashlib.sha256(open(p, 'rb').read()).hexdigest()
_VS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'verify_set.py')
_vs = {'__name__': 'vs', '__file__': _VS}; exec(open(_VS).read(), _vs)


def corners(me, ids, mw):
    """the part's triangles as glTF stores them: positions (x, z, -y) after the object transform, UVs with V flipped"""
    uv = me.uv_layers.active.data; P = []; U = []
    for i in ids:
        p = me.polygons[i]
        P.append([tuple(mw @ me.vertices[me.loops[li].vertex_index].co) for li in p.loop_indices]); U.append([tuple(uv[li].uv) for li in p.loop_indices])
    P = np.array(P); U = np.array(U)
    return np.stack([P[..., 0], P[..., 2], -P[..., 1]], -1), np.stack([U[..., 0], 1 - U[..., 1]], -1)


def same_as_glb(me, ids, mw, glb):
    try: T, TU = _vs['read_glb'](glb, True)
    except Exception: return False
    P, U = corners(me, ids, mw)
    return T.shape == P.shape and np.allclose(T, P, atol=1e-6) and np.allclose(TU, U, atol=1e-6)


def held_for(rec, name):
    out = []
    for x in rec.get('held', []):
        if isinstance(x, dict):
            if name in x['parts'] or '*' in x['parts']: out.append(x['note'])
        elif name in x: out.append(x)
    return out


def latest(d):
    vs = sorted(v for v in (os.listdir(d) if os.path.isdir(d) else []) if re.fullmatch(r'v\d{4}', v))
    return vs[-1] if vs else None


def export_set(OBJ, OWNER, RECIPE, OUT, ITEM, SRC_SHA, SET_VERSION, REPAIRED=None):
    src = bpy.data.objects[OBJ]; me = src.data
    owner = np.load(OWNER); rec = json.load(open(RECIPE)); names = list(rec['parts'])
    stem = os.path.splitext(rec['smartmesh'])[0]
    base = os.path.join(OUT, 'Parts Library', 'Candidates', ITEM, stem)
    setf = os.path.join(base, f'SET.{SET_VERSION}.json')
    if os.path.exists(setf): raise SystemExit(f'error: {setf} exists; a set version is never overwritten')
    for o in list(bpy.context.scene.objects): o.select_set(False)
    stages = [s['name'] for s in rec.get('stages', [])]
    made = []
    for k, name in enumerate(names):
        keep = owner == k; spec = rec['parts'][name]; held = held_for(rec, name)
        ids = [int(x) for x in np.flatnonzero(keep)]
        pdir = os.path.join(base, name); prev = latest(pdir)
        if prev:
            pj0 = json.load(open(os.path.join(pdir, prev, 'part.json')))
            if ((pj0['face_ids'], pj0['motion_class'], pj0['bind'], pj0['held_notes'], pj0.get('recipe_sources')) == (ids, spec['class'], spec['bind'], held, spec.get('from', []))
                    and same_as_glb(me, ids, src.matrix_world, os.path.join(pdir, prev, pj0['glb']))):
                made.append({'part': name, 'faces': len(ids), 'version': prev, 'changed': False}); continue
        ver = f'v{int(prev[1:]) + 1:04d}' if prev else 'v0001'
        R = rec.get('repair') or {}; turned = set(R.get('winding_turned_ids', []))
        n_rep = sum(1 for i in ids if R and i >= R['source_faces'])
        n_turn_s = sum(1 for i in ids if i in turned and i < R.get('source_faces', 1 << 30)); n_turn_r = sum(1 for i in ids if i in turned and i >= R.get('source_faces', 1 << 30))
        n_turn = n_turn_s + n_turn_r
        geo_changed = (not prev) or not same_as_glb(me, ids, src.matrix_world, os.path.join(pdir, prev, pj0['glb']))
        geo_text = ('the repaired smart mesh (%s): %d source faces unchanged in position and UV%s%s%s; glTF Y-up export, no materials'
                    % ((REPAIRED or {}).get('file', 'the repaired mesh'), len(ids) - n_rep, (', %d of them with winding turned (%s)' % (n_turn_s, R.get('orient_record'))) if n_turn_s else '',
                       (', plus %d appended repair faces (ids >= %d, %s) whose UVs continue the island around them or are islands of their own (%s)' % (n_rep, R['source_faces'], R['record'], R.get('uv_record', 'no UV record'))) if n_rep else '',
                       (', %d of the repair faces with winding turned' % n_turn_r) if n_turn_r else '')) if R else 'the source smart mesh faces unchanged (positions, UVs, custom normals); glTF Y-up export, no materials'
        bm = bmesh.new(); bm.from_mesh(me); bm.faces.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if not keep[f.index]], context='FACES')
        aside = [x for x in (bpy.data.objects.get(name), bpy.data.meshes.get(name)) if x is not None]
        for x in aside: x.name = name + '__aside_for_export'
        m = bpy.data.meshes.new(name); bm.to_mesh(m); bm.free()
        for attr in [a.name for a in m.attributes if not a.name.startswith('.') and a.name not in ('position', 'UVMap', 'sharp_face', 'custom_normal', 'sharp_edge', 'material_index')]:
            m.attributes.remove(m.attributes[attr])                    # drop analysis attributes (votes, labels, colours)
        for ca in list(m.color_attributes): m.color_attributes.remove(ca)
        o = bpy.data.objects.new(name, m); bpy.context.scene.collection.objects.link(o)
        if (o.name, m.name) != (name, name): raise RuntimeError(f'export names {o.name}/{m.name} != {name}')
        o.matrix_world = src.matrix_world
        d = os.path.join(pdir, ver); os.makedirs(d)
        glb = os.path.join(d, name + '.glb')
        bpy.ops.object.select_all(action='DESELECT'); o.select_set(True); bpy.context.view_layer.objects.active = o
        bpy.ops.export_scene.gltf(filepath=glb, export_format='GLB', use_selection=True, export_apply=False, export_animations=False,
                                  export_materials='NONE', export_yup=True)
        pj = {'id': f'{ITEM}/{stem}/{name}/{ver}', 'part': name, 'version': ver, 'previous_version': prev, 'item': ITEM, 'status': 'candidate',
              'source_smartmesh': {'file': rec['smartmesh'], 'sha256': SRC_SHA},
              'repaired_mesh': REPAIRED,
              'faces': len(ids), 'face_ids': ids,
              'motion_class': spec['class'], 'bind': spec['bind'], 'recipe_sources': spec.get('from', []),
              'recipe_stages': stages,
              'scale_stage': rec.get('scale_stage', 'generator_normalised: the generator size, not yet proportioned to the body'),
              'geometry': geo_text,
              'geometry_changed': geo_changed, 'winding_turned_faces': n_turn, 'winding_turned_source_faces': n_turn_s, 'winding_turned_repair_faces': n_turn_r,
              'repair_faces': int(sum(1 for i in ids if rec.get('repair') and i >= rec['repair']['source_faces'])),
              'held_notes': held, 'glb': os.path.basename(glb), 'glb_sha256': h(glb), 'exporter': f'Blender {bpy.app.version_string} glTF'}
        json.dump(pj, open(os.path.join(d, 'part.json'), 'w'), indent=1)
        bpy.data.objects.remove(o); bpy.data.meshes.remove(m)
        for x in aside: x.name = name
        made.append({'part': name, 'faces': len(ids), 'version': ver, 'changed': True, 'previous_version': prev, 'geometry_changed': geo_changed})
    json.dump({'item': ITEM, 'set_version': SET_VERSION, 'source': rec['smartmesh'], 'repaired_mesh': REPAIRED, 'repair': rec.get('repair'), 'parts': made,
               'recipe': os.path.basename(RECIPE), 'stages': stages, 'held': rec.get('held', [])},
              open(setf, 'w'), indent=1)
    return {'parts': len(made), 'changed': [x['part'] for x in made if x['changed']], 'set': setf}


if bpy.app.background and '--' in sys.argv:
    argv = sys.argv[sys.argv.index('--') + 1:]
    if len(argv) < 8:
        raise SystemExit('error: export_parts <mesh.blend|glb|fbx> <object> <owner.npy> <recipe.json> <out_dir> <item> <source_sha256> <set_version>')
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import mesh_load
    mesh_load.load(argv[0]); r = export_set(*argv[1:8])
    print('EXPORT DONE', r['parts'], 'parts;', len(r['changed']), 'changed ->', r['set'])
