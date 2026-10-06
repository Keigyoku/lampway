# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the TITAN project, same author (tools/test_skin_bind.py, sha256 a93a1eb4ec16), on 2026-10-06. The suite runs unchanged against the port (skin and morph are WIP).
"""Geometry oracles for the explicit native-bind skinning seam."""
import copy
import importlib.util
from pathlib import Path
import sys
import subprocess
import unittest

HERE = Path(__file__).resolve().parents[2] / "src/scripts/mixar/modules/lampway_tools/rig_convert"
sys.path.insert(0, str(HERE))
import canon


class SkinBindTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((HERE / 'skin_bind.py').is_file(),
                        'explicit bind skinning is not available')
        spec = importlib.util.spec_from_file_location('skin_bind', HERE / 'skin_bind.py')
        self.s = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.s)
        self.mesh = canon.normalize_mesh({'meshes': [{
            'name': 'body', 'verts': [[2,3,4], [-5,7,9], [6,-2,1]],
            'faces': [[0,1,2]], 'loop_uv': [[0,0],[1,0],[0,1]],
            'materials': ['skin'], 'face_mat': [0],
        }]}, canon.IDENTITY)
        # Deliberately dissimilar native axes, translation, scale and shear.
        self.joints = [
            {'name': 'root', 'parent': None,
             'bind': [[0,-2,0,5],[1,0,0,-7],[0,0,.5,9],[0,0,0,1]]},
            {'name': 'arm', 'parent': 'root',
             'bind': [[1,.25,0,11],[0,1,.5,13],[0,0,2,-3],[0,0,0,1]]},
        ]
        self.weights = {'body': [[['root',1]], [['arm',1]], [['arm',.3],['root',.7]]]}

    def test_blender_verification_recipe_is_argument_driven(self):
        recipe=HERE/'recipes/skin-bind-verify-blender.py'
        self.assertTrue(recipe.is_file(),'repeatable Blender bind verification recipe is missing')
        help_run=subprocess.run([sys.executable,str(recipe),'--help'],capture_output=True,text=True)
        self.assertEqual(help_run.returncode,0,help_run.stderr)
        for flag in ('--fbx','--mesh','--space','--poses','--out-dir'):
            self.assertIn(flag,help_run.stdout)
        bad=subprocess.run([sys.executable,str(recipe),'--typo'],capture_output=True,text=True)
        self.assertEqual(bad.returncode,2)
        self.assertNotIn('ModuleNotFoundError',bad.stderr)

    def test_export_comparison_recipe_requires_both_artifacts_and_authored_poses(self):
        recipe=HERE/'recipes/skin-bind-compare-blender.py'
        self.assertTrue(recipe.is_file(),'independent export comparison recipe is missing')
        result=subprocess.run([sys.executable,str(recipe),'--help'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        for flag in ('--reference','--candidate','--mesh','--space','--poses','--out-dir','--render'):
            self.assertIn(flag,result.stdout)
        bad=subprocess.run([sys.executable,str(recipe),'--typo'],capture_output=True,text=True)
        self.assertEqual(bad.returncode,2)
        self.assertNotIn('ModuleNotFoundError',bad.stderr)

    def test_shaded_packet_requires_explicit_geometry_only_evaluation(self):
        self.mesh['meshes'][0]['shading'] = {'schema':'titan.mesh-shading/1',
            'face_smooth':[True], 'corner_normals':[[0.,0.,1.]]*3}
        packet = self.s.capture(self.mesh, self.joints, self.weights)
        before = canon.serialize(packet)
        pose = {j['name']:j['bind'] for j in self.joints}
        with self.assertRaisesRegex(ValueError, 'geometry_only'):
            self.s.evaluate(packet, pose)
        result = self.s.evaluate(packet, pose, geometry_only=True)
        self.assertNotIn('shading', result['meshes'][0])
        self.assertEqual(result['meshes'][0]['verts'], self.mesh['meshes'][0]['verts'])
        self.assertEqual(canon.serialize(packet), before)
        rebound, _ = self.s.rebind(packet, self.joints, {'arm':'arm','root':'root'})
        self.assertEqual(rebound['mesh'], packet['mesh'])

    def test_normal_comparison_keeps_rest_strict_and_calibrates_pose(self):
        import math
        spec=importlib.util.spec_from_file_location('compare',HERE/'recipes/skin-bind-compare-blender.py')
        compare=importlib.util.module_from_spec(spec);spec.loader.exec_module(compare)
        self.assertTrue(hasattr(compare,'normal_errors'),'independent calibrated normal comparison is absent')
        rules=compare.load_rules(HERE/'recipes/skin-bind-compare-rules.json')
        def rotated(angle):return [[math.cos(math.radians(angle)),math.sin(math.radians(angle)),0.]]
        self.assertEqual(compare.normal_errors([[1.,0.,0.]],rotated(.224),rules['rest_degrees'])['over_tolerance'],1)
        self.assertEqual(compare.normal_errors([[1.,0.,0.]],rotated(.224),rules['posed_degrees'])['over_tolerance'],0)
        self.assertEqual(compare.normal_errors([[1.,0.,0.]],rotated(.26),rules['posed_degrees'])['over_tolerance'],1)
        with self.assertRaises(ValueError):compare.normal_errors([[0.,0.,0.]],rotated(.1),rules['posed_degrees'])

    def test_bind_pose_preserves_every_vertex_and_surface_field(self):
        original = copy.deepcopy((self.mesh, self.joints, self.weights))
        packet = self.s.capture(self.mesh, self.joints, self.weights)
        result = self.s.evaluate(packet, {j['name']: j['bind'] for j in self.joints})
        self.assertEqual(canon.serialize(result), canon.serialize(self.mesh))
        self.assertEqual((self.mesh, self.joints, self.weights), original)

    def test_pose_changes_vertices_and_morph_directions_by_analytic_values(self):
        self.mesh['meshes'][0]['morphs'] = {'dent': [[1.0,2.0,3.0]] * 3}
        self.mesh['meshes'][0]['morph_names'] = {'dent': 'dent'}
        packet = self.s.capture(self.mesh, self.joints, self.weights)
        # Independently authored global poses: root applies (10-2y, 3x-4, z/2+7),
        # arm applies (x-2, 6-z, y+1) to the bind-space mesh.
        pose = {'root': [[-2,0,0,24],[0,-6,0,11],[0,0,.25,11.5],[0,0,0,1]],
                'arm': [[1,.25,0,9],[0,0,-2,9],[0,1,.5,14],[0,0,0,1]]}
        result = self.s.evaluate(packet, pose)['meshes'][0]
        self.assertEqual(result['verts'], [[4,2,9],[-7,-3,8],[11,11.3,4.95]])
        self.assertEqual(result['morphs']['dent'], [[-4,3,1.5],[1,-3,2],[-2.5,1.2,1.65]])
        self.assertEqual(result['faces'], [[0,1,2]])
        self.assertEqual(packet['mesh'], self.mesh)

    def test_evaluated_near_zero_has_canonical_positive_zero_bytes(self):
        packet=self.s.capture(self.mesh,self.joints,self.weights)
        pose={j['name']:copy.deepcopy(j['bind']) for j in self.joints}
        pose['root'][0][3]=2.99999999
        result=self.s.evaluate(packet,pose)
        self.assertEqual(result['meshes'][0]['verts'][0],[0.0,3.0,4.0])
        self.assertNotIn(b'-0.0',canon.serialize(result))

    def test_refuse_incomplete_cyclic_or_invalid_bind_tables(self):
        cases = []
        def changed(index, field, value):
            joints = copy.deepcopy(self.joints); joints[index][field] = value; cases.append(joints)
        changed(1, 'parent', 'absent')
        changed(1, 'parent', None)
        changed(1, 'parent', 'arm')
        changed(0, 'parent', 'arm')
        changed(1, 'name', 'root')
        changed(1, 'name', '')
        changed(1, 'tail_guess', [1,0,0])
        changed(1, 'bind', [[1,0,0,0],[0,0,0,0],[0,0,1,0],[0,0,0,1]])
        changed(1, 'bind', [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,1,0,1]])
        changed(1, 'bind', [[1,0,0,float('nan')],[0,1,0,0],[0,0,1,0],[0,0,0,1]])
        changed(1, 'bind', [[1,0,0,True],[0,1,0,0],[0,0,1,0],[0,0,0,1]])
        changed(1, 'bind', [[1,0],[0,1]])
        cases.extend([[], None])
        for joints in cases:
            with self.subTest(joints=joints):
                with self.assertRaises(ValueError): self.s.capture(self.mesh, joints, self.weights)

    def test_refuse_missing_unknown_or_nonpositive_vertex_weight_mass(self):
        cases = [None, {}, dict(self.weights, extra=[]), {'body': []}]
        for row in [[], [['root',0]], [['root',-1]], [['absent',1]],
                    [['root',True]], [['root',float('inf')]], [['root','1']], [['root']],
                    [['root',1],['arm',-.01]], [['root',1],['absent',0]]]:
            weights = copy.deepcopy(self.weights); weights['body'][0] = row; cases.append(weights)
        for weights in cases:
            with self.subTest(weights=weights):
                with self.assertRaises(ValueError): self.s.capture(self.mesh, self.joints, weights)

    def test_refuse_corrupt_packets_or_incomplete_pose_instead_of_substituting(self):
        packet = self.s.capture(self.mesh, self.joints, self.weights)
        pose = {j['name']: j['bind'] for j in self.joints}
        for bad_pose in [None, {}, {'root':pose['root']}, dict(pose, ghost=pose['root'])]:
            with self.subTest(pose=bad_pose):
                with self.assertRaises(ValueError): self.s.evaluate(packet, bad_pose)
        cases = [dict(packet, guessed_frame=True), dict(packet, schema='other')]
        for rows in [[], [[['root',1,0]]]*3, [[['root',2,2]]]*3,
                     [[['root',1,2]]]*3, [[['root',-1,1]]]*3,
                     [[['ghost',1,1]]]*3, [[['root',True,1]]]*3]:
            bad = copy.deepcopy(packet); bad['weights']['body'] = rows; cases.append(bad)
        bad = copy.deepcopy(packet); bad['mesh']['meshes'][0]['faces'] = [[0,1,3]]; cases.append(bad)
        for bad in cases:
            with self.subTest(packet=bad):
                with self.assertRaises(ValueError): self.s.evaluate(bad, pose)

    def test_named_weights_are_exact_order_independent_and_never_capped(self):
        joints = copy.deepcopy(self.joints)
        for index in range(12):
            joints.append(dict(joints[1], name='extra'+str(index)))
        row = [[joint['name'],.1] for joint in joints] + [['root',.2],['arm',0]]
        weights = {'body': [row, row, row]}
        first = self.s.capture(self.mesh, joints, weights)
        second = self.s.capture(self.mesh, list(reversed(joints)),
                                {'body': [list(reversed(row))]*3})
        self.assertEqual(canon.serialize(first), canon.serialize(second))
        self.assertEqual(len(first['weights']['body'][0]), 14)
        self.assertEqual(dict((name,(n,d)) for name,n,d in first['weights']['body'][0])['root'], (3,16))
        from fractions import Fraction
        self.assertEqual(sum(Fraction(n,d) for _,n,d in first['weights']['body'][0]), 1)

    def test_rebind_keeps_fitted_surface_despite_different_target_bases(self):
        self.mesh['meshes'][0]['morphs']={'dent':[[1.0,2.0,3.0]]*3}
        self.mesh['meshes'][0]['morph_names']={'dent':'dent'}
        packet=self.s.capture(self.mesh,self.joints,self.weights)
        target=[{'name':'body','parent':None,
                 'bind':[[0,1,0,300],[-1,0,0,-200],[0,0,1,50],[0,0,0,1]]},
                {'name':'hand','parent':'body',
                 'bind':[[2,0,0,-80],[0,3,0,70],[0,0,4,90],[0,0,0,1]]}]
        before=copy.deepcopy((packet,target))
        out,receipt=self.s.rebind(packet,target,{'root':'body','arm':'hand'})
        self.assertEqual(out['mesh'],packet['mesh'])
        self.assertEqual(out['joints'],target)
        self.assertEqual((packet,target),before)
        pose={j['name']:copy.deepcopy(j['bind']) for j in target}
        self.assertEqual(self.s.evaluate(out,pose),packet['mesh'])
        pose['hand'][0][3]+=10
        evaluated=self.s.evaluate(out,pose)['meshes'][0]
        self.assertEqual(evaluated['verts'],[[2,3,4],[5,7,9],[9,-2,1]])
        self.assertEqual(evaluated['morphs'],self.mesh['meshes'][0]['morphs'])
        self.assertEqual(receipt['geometry_sha256'],canon.digest(canon.serialize(packet['mesh'])))
        self.assertEqual(receipt['merged_targets'],{})
        self.assertEqual(receipt['vertices'],3)

    def test_rebind_merges_rational_mass_explicitly_without_dropping_or_guessing(self):
        packet=self.s.capture(self.mesh,self.joints,self.weights)
        out,receipt=self.s.rebind(packet,[self.joints[0]],{'root':'root','arm':'root'})
        self.assertEqual(out['weights']['body'],[[['root',1,1]]]*3)
        self.assertEqual(out['mesh'],packet['mesh'])
        self.assertEqual(receipt['merged_targets'],{'root':['arm','root']})
        self.assertEqual(receipt['mapped_mass'],{
            'arm':{'target':'root','mass_approx':1.3,'mass_terms':[[3,10,1],[1,1,1]]},
            'root':{'target':'root','mass_approx':1.7,'mass_terms':[[7,10,1],[1,1,1]]}})
        self.assertEqual(receipt['dropped_mass'],[0,1])
        repeat,again=self.s.rebind(packet,[self.joints[0]],{'arm':'root','root':'root'})
        self.assertEqual(canon.serialize((out,receipt)),canon.serialize((repeat,again)))

    def test_rebind_refuses_incomplete_or_ambiguous_maps_and_corrupt_packets(self):
        packet=self.s.capture(self.mesh,self.joints,self.weights)
        for mapping in (None,{}, {'root':'root'}, {'root':'root','arm':None},
                        {'root':'root','arm':'absent'}, {'root':'root','arm':['arm']},
                        {'root':'root','arm':'arm','unused':'root'}):
            with self.subTest(mapping=mapping):
                with self.assertRaises(ValueError): self.s.rebind(packet,self.joints,mapping)
        bad=copy.deepcopy(packet); bad['weights']['body'][0]=[['root',2,2]]
        with self.assertRaises(ValueError): self.s.rebind(bad,self.joints,{'root':'root','arm':'arm'})
        target=copy.deepcopy(self.joints); target[1]['parent']='absent'
        with self.assertRaises(ValueError): self.s.rebind(packet,target,{'root':'root','arm':'arm'})

    def test_rebind_receipt_does_not_expand_coprime_denominators(self):
        # Real normalized weights have many distinct denominators. Their exact
        # sum can exceed Python's integer-to-string guard despite modest input.
        primes=[]; candidate=1009
        while len(primes)<1800:
            if all(candidate%n for n in range(2,int(candidate**.5)+1)): primes.append(candidate)
            candidate+=2
        mesh=copy.deepcopy(self.mesh); mesh['meshes'][0]['verts']=[[1.,2.,3.]]*len(primes)
        mesh['meshes'][0]['weights']=[[] for _ in primes]
        packet=self.s.capture(mesh,self.joints,{'body':[[['root',1]]]*len(primes)})
        packet['weights']['body']=[[['arm',p-1,p],['root',1,p]] for p in primes]
        out,receipt=self.s.rebind(packet,self.joints,{'arm':'arm','root':'root'})
        self.assertLess(len(canon.serialize(receipt)),150000)
        self.assertEqual(out,packet)
        self.assertEqual(sorted(receipt['mapped_mass']['root']['mass_terms']),sorted([[1,p,1] for p in primes]))


if __name__ == '__main__': unittest.main()
