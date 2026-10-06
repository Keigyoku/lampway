# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/partseg/verify_set.py, sha256 63bc7a5caac7) on 2026-10-06. The header below, with the measured rules behind
# the code, is the original's; the evidence-name check covers every evidence/ path rather than one set's file names.
# SPIKE (2026-10-03): independent check of an exported part set (no Blender): every part GLB named by SET.<v>.json is
# re-read with a minimal glTF reader; its triangle count must equal part.json `faces`, every triangle centre must equal
# the source smart-mesh face its `face_ids` names, its sha256 must equal `glb_sha256`, and the set must cover every
# source face exactly once.
# Usage: python3 verify_set.py <source.glb> <set dir> <set_version> [original.glb]   (writes <set dir>/evidence/VERIFY.<v>.json)
# With original.glb (critique-6 H13): the first faces of <source.glb> are compared with it - positions, UVs, winding.
# v2 (critique-7 I9 / H13): each part's triangles are also compared corner by corner with <source.glb> (positions, UVs,
# corner order = winding), so a part GLB with a turned face or a changed UV fails; part.json repaired_mesh sha is checked.
# v3 (critique-8 K6): every part GLB's mesh nodes are named exactly the part id.
# v4 (critique-10 M2): every evidence file named in the SET or a part.json - with or without its folder - carries the
# set version in its name and resolves (a bare r6_orient.json in a note named the v0003 file for three sets).
# --- AXI prelude (tools/AXI.md): no args shows what this is; too few args or an unknown flag refuses on stdout (script runs only, never on import) ---
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
_A = _sys.argv[1:]
_bad = [] if __name__ != '__main__' else [x for x in _A if x.startswith('--') and x.split('=')[0] not in []]
if _bad: print(f'error: unknown flag(s) {_bad}'); _ax.helps(['python3 scripts/partseg/verify_set.py <source.glb> <set dir> <set_version> [original.glb]']); _sys.stdout.flush(); raise SystemExit(2)
if __name__ == '__main__' and len(_A) < 3:
    if not _A: _ax.home(__file__, 'Independent check of an exported part set (no Blender): every part GLB named by SET.<v>.json, corner by corner')
    else: print(f'error: {len(_A)} argument(s); at least 3 needed')
    _ax.helps(['python3 scripts/partseg/verify_set.py <source.glb> <set dir> <set_version> [original.glb]']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
# --- end AXI prelude ---
import hashlib, json, re, os, struct, sys
import numpy as np

CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NC = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}


def read_glb(path, uv=False):
    b = open(path, 'rb').read()
    if b[:4] != b'glTF': raise ValueError(f'{path}: not a GLB')
    n = struct.unpack('<I', b[12:16])[0]; js = json.loads(b[20:20 + n]); o = 20 + n
    binc = b[o + 8:o + 8 + struct.unpack('<I', b[o:o + 4])[0]]
    if js.get('extensionsUsed'): raise ValueError(f'{path}: extensions {js["extensionsUsed"]} not supported')

    def acc(i):
        a = js['accessors'][i]; v = js['bufferViews'][a['bufferView']]
        start = v.get('byteOffset', 0) + a.get('byteOffset', 0); dt = np.dtype(CT[a['componentType']]); k = NC[a['type']]
        stride = v.get('byteStride', dt.itemsize * k)
        raw = np.frombuffer(binc, np.uint8, count=stride * (a['count'] - 1) + dt.itemsize * k, offset=start)
        return np.lib.stride_tricks.as_strided(raw.view(dt), (a['count'], k), (stride, dt.itemsize)).copy()
    tris = []
    for node in js.get('nodes', []):
        if 'mesh' not in node: continue
        if any(k in node for k in ('matrix', 'rotation', 'scale', 'translation')): raise ValueError(f'{path}: node transforms not supported')
        for p in js['meshes'][node['mesh']]['primitives']:
            if p.get('mode', 4) != 4: raise ValueError(f'{path}: non-triangle primitive')
            pos = acc(p['attributes']['POSITION']); idx = acc(p['indices']).ravel()
            t = pos[idx].reshape(-1, 3, 3)
            if uv:
                u = acc(p['attributes']['TEXCOORD_0'])[idx].reshape(-1, 3, 2); t = (t, u)
            tris.append(t)
    if uv: return np.concatenate([t[0] for t in tris]), np.concatenate([t[1] for t in tris])
    return np.concatenate(tris)


def node_names(path):
    b = open(path, 'rb').read(); n = struct.unpack('<I', b[12:16])[0]; js = json.loads(b[20:20 + n])
    return sorted({x.get('name') for x in js.get('nodes', []) if 'mesh' in x} | {m.get('name') for m in js.get('meshes', [])})


def main(src, setdir, ver, original=None):
    S, SU = read_glb(src, True); sc = S.mean(1); src_sha = hashlib.sha256(open(src, 'rb').read()).hexdigest()
    setj = json.load(open(os.path.join(setdir, f'SET.{ver}.json')))
    seen = np.zeros(len(S), np.int32); rows = []
    for p in setj['parts']:
        d = os.path.join(setdir, p['part'], p['version']); pj = json.load(open(os.path.join(d, 'part.json')))
        g = os.path.join(d, pj['glb']); T, TU = read_glb(g, True); ids = np.array(pj['face_ids'])
        sha_ok = hashlib.sha256(open(g, 'rb').read()).hexdigest() == pj['glb_sha256']
        dist = float(np.abs(T.mean(1) - sc[ids]).max()) if len(T) == len(ids) else None
        seen[ids] += 1
        corners_ok = len(T) == len(ids) and np.allclose(T, S[ids], atol=1e-6) and np.allclose(TU, SU[ids], atol=1e-6)
        rm = pj.get('repaired_mesh'); rm_ok = rm is None or rm.get('sha256') == src_sha
        names_ok = node_names(g) == [p['part']]
        ok = sha_ok and len(T) == pj['faces'] == len(ids) and dist is not None and dist < 1e-6 and corners_ok and rm_ok and names_ok
        rows.append({'part': p['part'], 'version': p['version'], 'faces': pj['faces'], 'glb_faces': len(T),
                     'max_face_centre_distance_m': dist, 'corners_positions_uvs_winding_equal': bool(corners_ok), 'repaired_mesh_sha_ok': bool(rm_ok) if rm else None, 'node_names_equal_part': bool(names_ok),
                     'glb_sha256_ok': sha_ok, 'ok': bool(ok)})
    EVID = re.compile(r'evidence/[\w.\-]+?\.(?:jsonl|json|glb)\b')     # every evidence path named; the shelf's bare-name list was one set's file names
    texts = [open(os.path.join(setdir, f'SET.{ver}.json')).read()] + [open(os.path.join(setdir, p['part'], p['version'], 'part.json')).read() for p in setj['parts']]
    names = [m.group(0) for t in texts for m in EVID.finditer(t)]
    bad_ptr = sorted({n for n in names if not (n.startswith('evidence/') and f'.{ver}.' in n and os.path.exists(os.path.join(setdir, n)))})
    cov = {'faces_total': int(len(S)), 'covered_once': int((seen == 1).sum()), 'uncovered': int((seen == 0).sum()), 'covered_twice_or_more': int((seen > 1).sum())}
    out = {'set_version': ver, 'source': {'file': os.path.basename(src), 'sha256': src_sha, 'faces': int(len(S))},
           'check': 'verify_set.py v4: every evidence file named carries the set version and resolves; mesh node and mesh names equal the part id; each part GLB re-read with a minimal glTF reader (no Blender); triangle count equals part.json faces and face_ids; each triangle equals the face of <source.glb> it names corner by corner (positions, UVs, corner order) (the repaired mesh for a repaired set); part.json repaired_mesh sha256 equals <source.glb>; glb sha256 equals part.json; every source face covered exactly once',
           'coverage': cov, 'evidence_names': len(names), 'evidence_names_bad': bad_ptr,
           'all_ok': all(r['ok'] for r in rows) and cov['covered_once'] == len(S) and not bad_ptr, 'parts': rows}
    if original:                              # critique-6 H13: the repaired mesh's source faces against the ORIGINAL smart mesh
        (O, OU), (R, RU) = read_glb(original, True), read_glb(src, True); n = len(O)
        pos_bad = [i for i in range(n) if not np.allclose(np.sort(O[i], 0), np.sort(R[i], 0), atol=1e-6)]
        def order(i):
            for sh in range(3):
                if np.allclose(np.roll(R[i], sh, 0), O[i], atol=1e-6): return 'same'
                if np.allclose(np.roll(R[i][::-1], sh, 0), O[i], atol=1e-6): return 'reversed'
            return 'other'
        orders = [order(i) for i in range(n)]
        uv_bad = [i for i in range(n) if not np.allclose(np.sort(np.round(OU[i], 5), 0), np.sort(np.round(RU[i], 5), 0), atol=1e-5)]
        out_orig = {'original': os.path.basename(original), 'original_sha256': hashlib.sha256(open(original, 'rb').read()).hexdigest(), 'source_faces': n,
                    'position_differs': pos_bad[:50], 'n_position_differs': len(pos_bad), 'uv_differs': uv_bad[:50], 'n_uv_differs': len(uv_bad),
                    'winding_reversed': [i for i, o in enumerate(orders) if o == 'reversed'], 'order_other': sum(1 for o in orders if o == 'other')}
    out['against_original'] = out_orig if original else None
    os.makedirs(os.path.join(setdir, 'evidence'), exist_ok=True)
    f = os.path.join(setdir, 'evidence', f'VERIFY.{ver}.json')
    if os.path.exists(f): _ax.refuse(f'{f} exists; never overwritten', ['python3 scripts/partseg/verify_set.py <source.glb> <set dir> <next set_version>'])
    json.dump(out, open(f, 'w'), indent=1)
    print(json.dumps({'all_ok': out['all_ok'], 'coverage': cov, 'bad': [r['part'] for r in rows if not r['ok']], 'evidence_names_bad': bad_ptr}))
    return 0 if out['all_ok'] else 1


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:5]))
