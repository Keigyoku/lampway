#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the TITAN project, same author (tools/canon.py, sha256 f3a67ef0ef23), on 2026-10-06. Pure python; the wire ids are unchanged.
"""Deterministic canonical unrigged meshes; D86 rig/reference stages follow separately.

Pure data seam: normalize_mesh / adapt_mesh / serialize. Native profiles explicitly
map already world-transformed adapter coordinates to canonical centimetres.
No skeleton, skin or animation is silently treated as an unrigged mesh.
"""
import hashlib
import json
import math
from pathlib import Path
import sys
import unicodedata

VERSION = '0.2.0'
SCHEMA = 'titan.canonical-mesh/1'      # a stable wire contract shared with TITAN (the game reads it): never renamed
IDENTITY = {'unit_cm': 1, 'basis_to_canonical': [[1,0,0],[0,1,0],[0,0,1]]}
FORM = json.loads((Path(__file__).parent / 'recipes/canon-form-mesh.json').read_text(encoding='utf-8'))
SHADING_FORM = json.loads((Path(__file__).parent / 'recipes/canon-form-shading.json').read_text(encoding='utf-8'))


def serialize(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       separators=(',', ':')) + '\n').encode('utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def _number(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise ValueError('expected a finite number')
    return float(x)


def _vector(v, count):
    if not isinstance(v, (list, tuple)) or len(v) != count:
        raise ValueError('expected a %d-coordinate vector' % count)
    return [_number(x) for x in v]


def _space(space):
    if not isinstance(space, dict) or set(space) != {'unit_cm', 'basis_to_canonical'}:
        raise ValueError('profile requires only unit_cm and basis_to_canonical; no guessed world convention')
    k = _number(space['unit_cm'])
    if k <= 0: raise ValueError('unit_cm must be positive')
    raw = space['basis_to_canonical']
    if not isinstance(raw, list) or len(raw) != 3: raise ValueError('basis must be 3 by 3')
    b = [_vector(row, 3) for row in raw]
    if any(abs(sum(b[i][z]*b[j][z] for z in range(3)) - (1 if i==j else 0)) > 1e-9
           for i in range(3) for j in range(3)):
        raise ValueError('basis must be orthogonal; put uniform unit scale in unit_cm')
    d = (b[0][0]*(b[1][1]*b[2][2]-b[1][2]*b[2][1])
         - b[0][1]*(b[1][0]*b[2][2]-b[1][2]*b[2][0])
         + b[0][2]*(b[1][0]*b[2][1]-b[1][1]*b[2][0]))
    return k,b,d


def _name(n):
    if not isinstance(n, str) or not n or any(ord(c)<32 for c in n):
        raise ValueError('names must be nonempty strings without control characters')
    return unicodedata.normalize('NFC', n)


def _convert(mesh, k, basis, reflected, quantize):
    allowed = {'name','verts','faces','weights','loop_uv','materials','face_mat','morphs','morph_names','original_name','shading'}
    if not isinstance(mesh, dict) or set(mesh)-allowed:
        raise ValueError('unsupported mesh fields; do not discard unrecognized content')
    if not {'name','verts','faces'} <= set(mesh): raise ValueError('mesh needs name, verts and faces')
    def transform(v):
        v = _vector(v,3)
        result = [sum(basis[i][j]*v[j] for j in range(3))*k for i in range(3)]
        if not all(math.isfinite(x) for x in result): raise ValueError('coordinate conversion overflow')
        digits=FORM['position_decimals_cm']
        return [float(round(x,digits)) if round(x,digits) else 0.0 for x in result] if quantize else result
    if not isinstance(mesh['verts'], list) or not mesh['verts']: raise ValueError('mesh has no vertices')
    verts = [transform(v) for v in mesh['verts']]
    weights = mesh.get('weights', [[] for _ in verts])
    if len(weights) != len(verts) or any(w for w in weights):
        raise ValueError('skinned meshes require the pending canonical rig/reference profile; unrigged normalization refuses weights')
    faces=[]
    if not isinstance(mesh['faces'], list) or not mesh['faces']: raise ValueError('mesh has no faces')
    for face in mesh['faces']:
        if not isinstance(face, list) or len(face)<3 or len(set(face))!=len(face):
            raise ValueError('face needs at least three distinct vertex indices')
        if any(type(i) is not int or not 0<=i<len(verts) for i in face): raise ValueError('face index out of range')
        faces.append(list(reversed(face)) if reflected else list(face))
    uv=mesh.get('loop_uv')
    if uv is not None:
        if len(uv)!=sum(len(f) for f in faces): raise ValueError('corner UV count does not match face loops')
        uv=[_vector(v,2) for v in uv]
        if reflected:
            converted=[];offset=0
            for face in faces:
                converted.extend(reversed(uv[offset:offset+len(face)]));offset+=len(face)
            uv=converted
    materials=mesh.get('materials',[])
    if not isinstance(materials,list) or any(x is not None and not isinstance(x,str) for x in materials):
        raise ValueError('materials must be names or null, not opaque world objects')
    face_mat=mesh.get('face_mat', [0]*len(faces) if materials else [-1]*len(faces))
    if len(face_mat)!=len(faces) or any(type(i) is not int or not (-1<=i<len(materials)) for i in face_mat):
        raise ValueError('material indices do not match faces/slots')
    morphs={}; morph_names={}
    originals=mesh.get('morph_names',{})
    if not isinstance(originals,dict): raise ValueError('invalid original morph-name map')
    raw_morphs=mesh.get('morphs',{})
    if not isinstance(raw_morphs,dict): raise ValueError('morphs must be a name-to-vertex-deltas object')
    for name, deltas in raw_morphs.items():
        n=_name(name)
        if n in morphs: raise ValueError('morph name collision after Unicode normalization')
        if len(deltas)!=len(verts): raise ValueError('morph vertex count mismatch')
        original=originals.get(n,name)
        if _name(original)!=n: raise ValueError('original morph-name map does not match canonical name')
        morph_names[n]=original
        morphs[n]=[transform(v) for v in deltas]
    if set(originals)-set(morphs): raise ValueError('orphan original morph name')
    original_name=mesh.get('original_name',mesh['name'])
    if _name(original_name)!=_name(mesh['name']): raise ValueError('original mesh name does not match canonical name')
    result = {'name':_name(mesh['name']), 'original_name':original_name, 'verts':verts, 'faces':faces, 'weights':[[] for _ in verts],
            'loop_uv':uv, 'materials':list(materials), 'face_mat':list(face_mat), 'morphs':morphs, 'morph_names':morph_names}
    if 'shading' in mesh:
        shading = mesh['shading']
        if not isinstance(shading, dict) or set(shading) != {'schema','face_smooth','corner_normals'}:
            raise ValueError('shading requires schema, face_smooth and corner_normals only')
        if shading['schema'] != SHADING_FORM['schema']:
            raise ValueError('unsupported shading schema')
        smooth, normals = shading['face_smooth'], shading['corner_normals']
        if not isinstance(smooth, list) or len(smooth) != len(faces) or any(type(x) is not bool for x in smooth):
            raise ValueError('face_smooth must contain one boolean per face')
        if not isinstance(normals, list) or len(normals) != sum(map(len,faces)):
            raise ValueError('corner normal count does not match face loops')
        converted = []
        for normal in normals:
            normal = _vector(normal, 3)
            if abs(math.hypot(*normal)-1) > SHADING_FORM['unit_length_tolerance']:
                raise ValueError('corner normals must be unit vectors; normalize in the native adapter')
            # Orthogonal world basis only: normals have no unit scale. Object
            # inverse-transpose belongs in the native extraction adapter.
            vector = [math.fsum(basis[i][j]*normal[j] for j in range(3)) for i in range(3)]
            if quantize:
                vector = [round(x, SHADING_FORM['normal_decimals']) for x in vector]
            converted.append([x if x else 0.0 for x in vector])
        if reflected:
            reordered=[];offset=0
            for face in faces:
                reordered.extend(reversed(converted[offset:offset+len(face)]));offset+=len(face)
            converted=reordered
        result['shading']={'schema':shading['schema'], 'face_smooth':list(smooth), 'corner_normals':converted}
    return result


def normalize_mesh(document, space=None):
    """Return canonical cm mesh data. No input mutation; no inferred rig or world.

    Input may be a mesh dump with empty bones/armature. Existing canonical data
    is validated and idempotently serialized; it cannot be rescaled by a profile.
    """
    if not isinstance(document,dict): raise ValueError('input must be a mesh document')
    canonical=document.get('schema')==SCHEMA
    if canonical:
        if space is not None: raise ValueError('canonical input already declares its space; omit profile')
        if set(document)!={'schema','form','meshes'} or document['form']!=FORM:
            raise ValueError('invalid canonical schema/form')
        space=IDENTITY
    else:
        allowed={'meshes','source','armature','scale','bones'}
        if set(document)-allowed: raise ValueError('unsupported document fields or schema')
        if document.get('bones') or document.get('armature'):
            raise ValueError('rig normalization requires the pending canonical reference profile')
    k,b,d=_space(space)
    raw=document.get('meshes')
    if not isinstance(raw,list) or not raw: raise ValueError('document has no meshes')
    meshes=[_convert(m,k,b,d<0,True) for m in raw]
    if len({m['name'] for m in meshes})!=len(meshes): raise ValueError('mesh name collision after normalization')
    result={'schema':SCHEMA,'form':dict(FORM),'meshes':meshes}
    # Validating a canonical file must never silently round or repair its data.
    if canonical and serialize(result)!=serialize(document): raise ValueError('noncanonical numeric data; normalize the native input')
    return result


def adapt_mesh(document, space):
    """Emit native mesh data through the explicit inverse world profile."""
    canonical=normalize_mesh(document)
    k,b,d=_space(space);inv=[[b[j][i] for j in range(3)] for i in range(3)]
    meshes=[_convert(m,1/k,inv,d<0,False) for m in canonical['meshes']]
    for m in meshes:
        m['name']=m.pop('original_name')
        names=m.pop('morph_names');m['morphs']={names[n]:v for n,v in m['morphs'].items()}
    return {'meshes':meshes}


def _emit(fields, help_rows=()):
    # This surface emits scalar TOON fields and a primitive inline string array.
    for key,value in fields.items(): print(key+': '+json.dumps(value,ensure_ascii=False))
    if help_rows: print('help[%d]: '%len(help_rows)+','.join(json.dumps(v,ensure_ascii=False) for v in help_rows))


def _read(path):
    def pairs(items):
        out={}
        for k,v in items:
            if k in out: raise ValueError('duplicate JSON key '+k)
            out[k]=v
        return out
    return json.loads(Path(path).read_text(encoding='utf-8'),object_pairs_hook=pairs)


def _publish(path, data):
    p=Path(path)
    if p.is_symlink(): raise ValueError('output symlink refused')
    if p.exists():
        if p.read_bytes()!=data: raise ValueError('different existing output: '+str(p))
        return 'unchanged'
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f: f.write(data)
    return 'written'


USAGE = {
    'normalize':'canon.py normalize --input <native.json> --profile <space.json> --out <canonical.json> (profile omitted for canonical input)',
    'adapt':'canon.py adapt --input <canonical.json> --profile <space.json> --out <native.json>',
    'check':'canon.py check --input <canonical.json>',
}


def main(argv=None):
    args=list(sys.argv[1:] if argv is None else argv)
    if args in [['--version'],['-v'],['-V']]: print(VERSION);return 0
    if not args:
        _emit({'bin':str(Path(__file__).resolve()),'description':'Normalize unrigged mesh coordinates, winding, UVs and morph deltas.',
               'schema':SCHEMA,'rig_normalization':'pending; skeletons and skin weights refused'},list(USAGE.values()))
        return 0
    if args==['--help']:
        _emit({'description':'Explicit world profile: unit_cm and orthogonal basis_to_canonical. No defaults.'},list(USAGE.values()));return 0
    verb=args.pop(0)
    if verb not in USAGE:
        _emit({'error':'unknown command '+verb},list(USAGE.values()));return 2
    allowed={'--input'} if verb=='check' else {'--input','--profile','--out'}
    flags={}
    try:
        while args:
            key=args.pop(0)
            if key=='--help':
                if args or flags: raise ValueError('--help must be used alone after the command')
                _emit({'usage':USAGE[verb],'flags':', '.join(sorted(allowed)),'defaults':'none'},[USAGE[verb]]);return 0
            if key not in allowed: raise ValueError('unknown flag '+key+'; valid: '+', '.join(sorted(allowed)))
            if key in flags or not args or args[0].startswith('--'): raise ValueError('missing or duplicate value for '+key)
            flags[key]=args.pop(0)
        required={'--input'} if verb=='check' else {'--input','--out'}
        if verb=='adapt': required.add('--profile')
        if required-set(flags): raise ValueError('required flags: '+', '.join(sorted(required)))
    except ValueError as e:
        _emit({'error':str(e)},[USAGE[verb]]);return 2
    try:
        inp=Path(flags['--input']);document=_read(inp)
        profile=_read(flags['--profile']) if '--profile' in flags else None
        result=adapt_mesh(document,profile) if verb=='adapt' else normalize_mesh(document,profile)
        data=serialize(result)
        if verb=='check':
            if inp.read_bytes()!=data: raise ValueError('canonical file encoding differs from deterministic serialization')
            _emit({'verdict':'PASS','meshes':len(result['meshes']),'sha256':digest(data)});return 0
        out=Path(flags['--out'])
        if out.resolve()==inp.resolve(): raise ValueError('output must differ from source input')
        manifest={'tool':'canon','version':VERSION,'operation':verb,'source':str(inp.resolve()),
                  'source_sha256':digest(inp.read_bytes()),'profile':profile,'output_sha256':digest(data),
                  'scope':'unrigged mesh data; world-adapter visual verification is separate'}
        # Check both destinations before publishing either; never overwrite a prior receipt.
        md=serialize(manifest);mp=Path(str(out)+'.manifest.json')
        for p,d in [(out,data),(mp,md)]:
            if p.is_symlink() or (p.exists() and p.read_bytes()!=d): raise ValueError('different existing output: '+str(p))
        state=_publish(out,data);_publish(mp,md)
        _emit({'state':state,'output':str(out),'sha256':digest(data),'meshes':len(result['meshes'])},
              ['canon.py check --input '+str(out)] if verb=='normalize' else ['Read '+str(mp)+'; run the native adapter verification'])
        return 0
    except (ValueError,TypeError,KeyError,OverflowError,OSError) as e:
        _emit({'error':str(e)},[USAGE[verb]]);return 1


if __name__=='__main__': raise SystemExit(main())
