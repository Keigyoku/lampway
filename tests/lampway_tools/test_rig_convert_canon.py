# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the TITAN project, same author (tools/test_canon.py, sha256 481a5dcd2e0e), on 2026-10-06. The suite runs unchanged against the port.
"""Canonical mesh normalization: geometry, topology and actual CLI receipts."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[2] / "src/scripts/mixar/modules/lampway_tools/rig_convert"


class CanonMeshTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((HERE / 'canon.py').is_file(), 'normalize-first mesh module is not available')
        spec = importlib.util.spec_from_file_location('canon', HERE / 'canon.py')
        self.c = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.c)
        self.space = {'unit_cm': 100, 'basis_to_canonical': [[1,0,0],[0,-1,0],[0,0,1]]}
        self.doc = {'meshes': [{'name': 'piece', 'verts': [[0,0,0],[.2,0,0],[0,.3,.1]],
            'faces': [[0,1,2]], 'loop_uv': [[0,0],[1,0],[0,1]], 'materials': ['metal'], 'face_mat': [0],
            'weights': [[],[],[]], 'morphs': {'dent': [[0,0,0],[0,0,0],[.01,.02,.03]]}}]}

    def test_geometry_winding_uv_and_morph_round_trip(self):
        n = self.c.normalize_mesh(self.doc, self.space)
        m = n['meshes'][0]
        self.assertEqual(m['verts'], [[0,0,0],[20,0,0],[0,-30,10]])
        self.assertEqual(m['faces'], [[2,1,0]])
        self.assertEqual(m['loop_uv'], [[0,1],[1,0],[0,0]])
        self.assertEqual(m['morphs']['dent'][2], [1,-2,3])
        restored = self.c.adapt_mesh(n, self.space)
        for old, new in zip(self.doc['meshes'][0]['verts'], restored['meshes'][0]['verts']):
            for a,b in zip(old,new): self.assertAlmostEqual(a,b,places=9)
        self.assertEqual(restored['meshes'][0]['faces'], [[0,1,2]])
        self.assertEqual(restored['meshes'][0]['loop_uv'], [[0,0],[1,0],[0,1]])
        self.assertEqual(self.c.serialize(n), self.c.serialize(self.c.normalize_mesh(restored,self.space)))

    def test_authored_corner_shading_survives_reflected_round_trip(self):
        shading = {'schema': 'titan.mesh-shading/1', 'face_smooth': [True],
                   'corner_normals': [[1,0,0],[0,1,0],[0,0,1]]}
        self.doc['meshes'][0]['shading'] = shading
        original = copy.deepcopy(self.doc)
        canonical = self.c.normalize_mesh(self.doc, self.space)
        self.assertEqual(canonical['meshes'][0]['shading']['corner_normals'],
                         [[0,0,1],[0,-1,0],[1,0,0]])
        self.assertEqual(canonical['meshes'][0]['shading']['face_smooth'], [True])
        restored = self.c.adapt_mesh(canonical, self.space)
        self.assertEqual(restored['meshes'][0]['shading'], shading)
        self.assertEqual(self.c.serialize(canonical), self.c.serialize(self.c.normalize_mesh(canonical)))
        self.assertEqual(self.doc, original)

    def test_determinism_idempotence_and_input_unchanged(self):
        original = copy.deepcopy(self.doc)
        a = self.c.normalize_mesh(self.doc,self.space)
        b = self.c.normalize_mesh(copy.deepcopy(self.doc),dict(reversed(list(self.space.items()))))
        self.assertEqual(self.c.serialize(a), self.c.serialize(b))
        self.assertEqual(self.c.serialize(a), self.c.serialize(self.c.normalize_mesh(a)))
        self.assertEqual(self.doc,original)

    def test_native_morph_names_survive_normalization(self):
        native_name = 'e\u0301'
        self.doc['meshes'][0]['morphs'] = {native_name: [[0,0,0],[0,0,0],[0,0,.1]]}
        canonical = self.c.normalize_mesh(self.doc, self.space)
        self.assertIn('é', canonical['meshes'][0]['morphs'])
        restored = self.c.adapt_mesh(canonical, self.space)
        self.assertEqual(list(restored['meshes'][0]['morphs']), [native_name])
        self.assertEqual(self.c.serialize(canonical), self.c.serialize(self.c.normalize_mesh(restored,self.space)))

    def test_shading_validation_and_old_payload_stability(self):
        old = self.c.normalize_mesh(self.doc, self.space)
        self.assertNotIn('shading', old['meshes'][0])
        shading = {'schema':'titan.mesh-shading/1','face_smooth':[False],
                   'corner_normals':[[.267261242,.534522484,.801783726]]*3}
        self.doc['meshes'][0]['shading'] = shading
        valid = self.c.normalize_mesh(self.doc, self.space)
        self.assertEqual(valid, self.c.normalize_mesh(valid))
        self.assertEqual(valid, self.c.normalize_mesh(self.c.adapt_mesh(valid,self.space),self.space))
        for field,value in [('schema','unknown'),('face_smooth',[1]),('face_smooth',[]),
                            ('corner_normals',[[0,0,0]]*3),('corner_normals',[[0,0,2]]*3),
                            ('corner_normals',[[0,0,float('nan')]]*3),('corner_normals',[]),
                            ('unknown',True)]:
            bad = copy.deepcopy(self.doc);bad['meshes'][0]['shading'][field]=value
            with self.subTest(field=field,value=value):
                with self.assertRaises(ValueError):self.c.normalize_mesh(bad,self.space)
        corrupt = copy.deepcopy(valid);corrupt['meshes'][0]['shading']['corner_normals'][0][0]+=.00000000001
        with self.assertRaisesRegex(ValueError,'noncanonical'):
            self.c.normalize_mesh(corrupt)
        self.assertEqual(old,self.c.normalize_mesh(old))

    def test_refuse_ambiguous_or_unsupported_inputs(self):
        cases = []
        bad = copy.deepcopy(self.doc);bad['bones']=[{'name':'root'}];cases.append((bad,self.space))
        bad = copy.deepcopy(self.doc);bad['meshes'][0]['weights'][0]=[['root',1]];cases.append((bad,self.space))
        bad = copy.deepcopy(self.doc);bad['meshes'][0]['verts'][1][0]=float('nan');cases.append((bad,self.space))
        bad = copy.deepcopy(self.doc);bad['meshes'][0]['faces'][0][1]=9;cases.append((bad,self.space))
        bad = copy.deepcopy(self.doc);bad['meshes'][0]['loop_uv'].pop();cases.append((bad,self.space))
        bad = copy.deepcopy(self.doc);bad['meshes'][0]['morphs']={'e\u0301':[[0,0,0]]*3,'é':[[0,0,0]]*3};cases.append((bad,self.space))
        bad = copy.deepcopy(self.doc);bad['meshes'][0]['mystery_deformation']=[1,2];cases.append((bad,self.space))
        cases.extend([(self.doc,dict(self.space,unit_cm=0)),(self.doc,dict(self.space,basis_to_canonical=[[1,0,0],[0,1,0],[0,1,0]])),(self.doc,None)])
        for doc,space in cases:
            with self.subTest(doc=repr(doc)[:80],space=space):
                with self.assertRaises(ValueError): self.c.normalize_mesh(doc,space)

    def test_cli_actual_publication_and_refusal(self):
        def run(*args):
            return subprocess.run([sys.executable,str(HERE/'canon.py'),*map(str,args)],capture_output=True,text=True)
        home=run();self.assertEqual(home.returncode,0,home.stdout);self.assertIn('unrigged',home.stdout);self.assertIn('help[',home.stdout)
        bad=run('normalize','--mystery');self.assertEqual(bad.returncode,2);self.assertEqual(bad.stderr,'');self.assertIn('error:',bad.stdout)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);inp=p/'input.json';profile=p/'space.json';out=p/'canonical.json'
            inp.write_text(json.dumps(self.doc));profile.write_text(json.dumps(self.space))
            args=('normalize','--input',inp,'--profile',profile,'--out',out)
            first=run(*args);self.assertEqual(first.returncode,0,first.stdout);data=out.read_bytes()
            again=run(*args);self.assertEqual(again.returncode,0,again.stdout);self.assertEqual(out.read_bytes(),data)
            manifest=json.loads(Path(str(out)+'.manifest.json').read_text());self.assertEqual(manifest['output_sha256'],self.c.digest(data))
            check=run('check','--input',out);self.assertEqual(check.returncode,0,check.stdout)
            malformed=copy.deepcopy(self.doc);malformed['meshes'][0]['morphs']=[]
            inp.write_text(json.dumps(malformed))
            invalid=run(*args);self.assertEqual(invalid.returncode,1);self.assertEqual(invalid.stderr,'');self.assertIn('error:',invalid.stdout)
            changed=copy.deepcopy(self.doc);changed['meshes'][0]['verts'][0][0]=4;inp.write_text(json.dumps(changed))
            refused=run(*args);self.assertEqual(refused.returncode,1,refused.stdout);self.assertEqual(out.read_bytes(),data)


if __name__ == '__main__': unittest.main()
