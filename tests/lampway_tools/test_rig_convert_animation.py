# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the TITAN project, same author (tools/test_animation_canon.py, sha256 a9228509f116), on 2026-10-06. The suite runs unchanged against the port; the UE editor leg is needs_box.
"""Canonical animation contract: physical round trips, not count-only checks."""
import copy
import math
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
import tempfile
from unittest.mock import patch
from types import SimpleNamespace
from contextlib import redirect_stdout
import io
import os
import hashlib


RC = Path(__file__).resolve().parents[2] / "src/scripts/mixar/modules/lampway_tools/rig_convert"
UE_RECIPES = Path(__file__).resolve().parents[2] / "src/scripts/mixar/modules/lampway_tools/ue_recipes"
sys.path.insert(0, str(RC))
UE_EDITOR = os.environ.get("LAMPWAY_UE_EDITOR", "")
# needs_box: the UE editor leg is on hold; these run only where a UE editor is configured (LAMPWAY_UE_EDITOR names it)
needs_box = unittest.skipUnless(UE_EDITOR and Path(UE_EDITOR).exists(), "needs_box: no UE editor configured (LAMPWAY_UE_EDITOR)")
import animation_canon as ac  # noqa: E402


def qz(degrees):
    half = math.radians(degrees) / 2
    return [0, 0, math.sin(half), math.cos(half)]


def transform(position, rotation=None):
    return {"translation": position, "rotation": rotation or [0, 0, 0, 1],
            "scale": [1, 1, 1]}


def profile():
    # Native +Y forward, metres; arm bind and T reference deliberately differ.
    return ac.make_profile("synthetic", [
        {"name": "root", "parent": None, "bind": transform([0, 0, 0]),
         "reference": transform([0, 0, 0])},
        {"name": "arm", "parent": "root", "bind": transform([0, 0, 1], qz(35)),
         "reference": transform([0, 0, 1], qz(90))},
        {"name": "helper", "parent": "arm", "bind": transform([0.5, 0.2, 1], qz(35)),
         "reference": transform([0, 1, 1], qz(90))},
    ], basis=qz(-90), centimeters_per_unit=100)


def motion():
    return [{"time": time, "pose": {
        "root": transform([0, i * 0.1, 0], qz(i * 9)),
        "arm": transform([0.1, i * 0.1, 1], qz(17 + i * 11)),
        "helper": transform([0.4, 0.2 + i * 0.1, 1], qz(-12 + i * 11)),
    }} for i, time in enumerate(ac.sample_times("0.08"))]


class CanonicalAnimationTests(unittest.TestCase):
    def test_retarget_between_world_units_and_bases_keeps_canonical_motion(self):
        source=profile(); bones=[]
        # A second world expresses the same rig after +90deg in centimetres.
        for bone in source['bones']:
            entry={'name':bone['name'],'parent':bone['parent']}
            for field in ['bind','reference']:
                pose=bone[field]
                entry[field]=transform([x*100 for x in ac.rotate(qz(90),pose['translation'])],
                                       ac.qmul(qz(90),pose['rotation']))
            bones.append(entry)
        target=ac.make_profile('second-world',bones,basis=qz(-180),centimeters_per_unit=1)
        packet=ac.normalize(motion(),source,duration='0.08',channels={})
        rules={'map':{b['name']:b['name'] for b in bones},'reference_follow':[],
               'translation_scales':{b['name']:1 for b in bones},'anchors':{}}
        moved=ac.retarget(packet,target,rules)
        delta=ac.compare(packet['samples'],moved['samples'])
        self.assertLess(delta['translation_max'],1e-5)
        self.assertLess(delta['rotation_max_degrees'],1e-5)

    def test_retarget_preserves_target_segments_and_anchors_helpers(self):
        def rig(name, size, twist, extra=False):
            bones = [
                {'name':'root','parent':None,'bind':transform([0,0,0]),'reference':transform([0,0,0])},
                {'name':'joint','parent':'root','bind':transform([0,0,10*size],qz(twist)), 'reference':transform([0,0,10*size],qz(twist))},
                {'name':'tip','parent':'joint','bind':transform([10*size,0,10*size],qz(twist)), 'reference':transform([10*size,0,10*size],qz(twist))},
            ]
            if extra:
                bones.append({'name':'extra','parent':'tip','bind':transform([12.5*size,0,10*size],qz(twist)), 'reference':transform([12.5*size,0,10*size],qz(twist))})
            bones.append({'name':'helper','parent':'root','bind':transform([10*size,0,12*size]),'reference':transform([10*size,0,12*size])})
            return ac.make_profile(name,bones,basis=qz(0),centimeters_per_unit=1)
        source,target=rig('source',1,0),rig('target',2,90,True)
        samples=[{'time':[0,1],'pose':{
            'root':transform([3,0,0]), 'joint':transform([3,0,10],qz(90)),
            'tip':transform([3,10,10],qz(90)), 'helper':transform([3,10,12],qz(90))}}]
        packet=ac.normalize(samples,source,duration='0',channels={'notifies':[{'name':'FootUp','time':0}]})
        rules={'map':{n:n for n in ['root','joint','tip','helper']},'reference_follow':['extra'],
               'translation_scales':{n:2 for n in ['root','joint','tip','helper']},
               'anchors':{'helper':{'source':'tip','target':'tip','scale':2}}}
        result=ac.retarget(packet,target,rules)
        actual=ac.adapt(result,target)[0]['pose']
        for bone,expected in {'root':[6,0,0],'joint':[6,0,20],'tip':[6,20,20],
                              'extra':[6,25,20],'helper':[6,20,24]}.items():
            for got,want in zip(actual[bone]['translation'],expected):
                self.assertAlmostEqual(got,want,places=5,msg=bone)
        self.assertEqual(result['channels'],packet['channels'])
        self.assertEqual(ac.encode(result),ac.encode(ac.retarget(packet,target,rules)))
        identity_rules={'map':{b['name']:b['name'] for b in source['bones']},'reference_follow':[],
                        'translation_scales':{b['name']:1 for b in source['bones']},'anchors':{}}
        same=ac.retarget(packet,source,identity_rules)
        self.assertLess(ac.compare(samples,ac.adapt(same,source))['translation_max'],1e-6)
        for bad in [dict(rules,map={'root':'root'}),dict(rules,reference_follow=[]),
                    dict(rules,anchors={'helper':{'source':'tip','target':'missing','scale':2}})]:
            with self.assertRaises(ValueError): ac.retarget(packet,target,bad)

    def test_round_trip_keeps_positions_rotations_helpers_and_terminal(self):
        original = motion()
        packet = ac.normalize(original, profile(), duration="0.08", channels={
            "notifies": [{"name": "LeftFootUp", "time": 0.04}],
            "curves": {"Speed": {"keys": [[0, 10], [0.08, 30]], "interpolation": "cubic"}},
            "root_motion": False, "sync_markers": [],
        })
        self.assertEqual(packet["samples"][-1]["time"], [2, 25])
        self.assertEqual(len(packet["profile"]["bones"]), 3)
        restored = ac.adapt(packet, profile())
        receipt = ac.compare(original, restored)
        self.assertLess(receipt["translation_max"], 0.000001)
        self.assertLess(receipt["rotation_max_degrees"], 0.00001)
        self.assertEqual(packet["channels"]["notifies"][0]["name"], "LeftFootUp")
        self.assertEqual(original, motion(), "normalization must not mutate its caller")
        self.assertEqual(packet["samples"][1]["pose"]["root"]["translation"], [10, 0, 0])

    def test_reference_maps_to_identity_frames_not_native_bind_delta(self):
        p = profile()
        self.assertEqual(p["bones"][2]["canonical_reference_local"]["translation"], [100, 0, 0])
        self.assertEqual(p["bones"][2]["canonical_reference_local"]["rotation"], [0, 0, 0, 1])
        pose = {b["name"]: b["reference"] for b in p["bones"]}
        packet = ac.normalize([{"time": [0, 1], "pose": pose}], p,
                              duration="0", channels={})
        for bone in packet["samples"][0]["pose"].values():
            self.assertEqual(bone["rotation"], [0, 0, 0, 1])
        # An A-bind animation stays A in physical space after the inverse adapter.
        bind = {b["name"]: b["bind"] for b in p["bones"]}
        source = [{"time": [0, 1], "pose": bind}]
        a = ac.normalize(source, p, duration="0", channels={})
        self.assertGreater(ac.compare(a["samples"], packet["samples"])["rotation_max_degrees"], 50)
        self.assertLess(ac.compare(source, ac.adapt(a, p))["rotation_max_degrees"], 0.00001)

    def test_same_bytes_idempotent_and_quaternion_sign_independent(self):
        p, source = profile(), motion()
        first = ac.normalize(source, p, duration="0.08", channels={})
        negated = copy.deepcopy(source)
        for sample in negated:
            for bone in sample["pose"].values():
                bone["rotation"] = [-x for x in bone["rotation"]]
        again = ac.normalize(negated, p, duration="0.08", channels={})
        self.assertEqual(ac.encode(first), ac.encode(again))
        self.assertEqual(ac.encode(first), ac.encode(ac.normalize(first, p)))
        self.assertNotIn(b"-0.0", ac.encode(first))

    def test_refuses_profile_mismatch_corruption_missing_channels_and_bad_time(self):
        p = profile()
        packet = ac.normalize(motion(), p, duration="0.08", channels={})
        changed = copy.deepcopy(p)
        changed["bones"][1]["reference"]["translation"][0] += 1
        with self.assertRaisesRegex(ValueError, "profile"):
            ac.adapt(packet, changed)
        corrupt = copy.deepcopy(packet)
        corrupt["samples"][0]["pose"]["arm"]["translation"][0] += 1
        with self.assertRaisesRegex(ValueError, "hash"):
            ac.adapt(corrupt, p)
        for mutation in ("missing", "time", "nan", "scale"):
            samples = motion()
            if mutation == "missing":
                del samples[0]["pose"]["helper"]
            elif mutation == "time":
                samples[1]["time"] = [1, 25]
            elif mutation == "nan":
                samples[0]["pose"]["arm"]["translation"][0] = math.nan
            else:
                samples[0]["pose"]["arm"]["scale"] = [1, 2, 1]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                ac.normalize(samples, p, duration="0.08", channels={})

    def test_uniform_scale_composes_and_survives_the_round_trip(self):
        """A pack's uniform bone scale (a weapon pack's head at 0.999) is a similarity transform, not a refusal."""
        p = profile()
        samples = motion()
        for sample in samples:
            sample["pose"]["arm"]["scale"] = [0.999, 0.999, 0.999]
        packet = ac.normalize(samples, p, duration="0.08", channels={})
        self.assertEqual(packet["samples"][0]["pose"]["arm"]["scale"], [0.999, 0.999, 0.999])
        self.assertEqual(ac.normalize(packet, p), packet)
        # The scaled bone carries its children: a child offset of 10 under a 0.5 parent sits 5 away, and the
        # relative round trip returns the local offset unchanged.
        parent = {"translation": [0, 0, 0], "rotation": [0, 0, 0, 1], "scale": [0.5, 0.5, 0.5]}
        local = {"translation": [10, 0, 0], "rotation": [0, 0, 0, 1], "scale": [1, 1, 1]}
        world = ac._compose(parent, local)
        self.assertEqual(world["translation"], [5, 0, 0])
        self.assertEqual(world["scale"], [0.5, 0.5, 0.5])
        back = ac._relative(parent, world)
        self.assertEqual([round(x, 6) for x in back["translation"]], [10, 0, 0])
        self.assertEqual([round(x, 6) for x in back["scale"]], [1, 1, 1])   # the local scale, recovered
        # float32 evaluation noise around 1 is canonicalized, not refused (the pack's clips sample 1 +/- a few ulps).
        noisy = ac._transform({"translation": [0, 0, 0], "rotation": [0, 0, 0, 1], "scale": [0.9999995, 1.0000001, 1.0]})
        self.assertEqual(noisy["scale"], [1, 1, 1])
        self.assertEqual(ac._transform({"translation": [0, 0, 0], "rotation": [0, 0, 0, 1], "scale": [0.999, 0.9990001, 0.9989999]})["scale"], [0.999, 0.999, 0.999])
        for bad in ([1, 2, 1], [0, 0, 0], [-1, -1, -1], [1, 1.001, 1]):
            with self.subTest(scale=bad), self.assertRaisesRegex(ValueError, "affine"):
                ac._transform({"translation": [0, 0, 0], "rotation": [0, 0, 0, 1], "scale": bad})

    def test_profile_refuses_ambiguous_hierarchy_units_and_root(self):
        bones = copy.deepcopy(profile()["bones"])
        for bad in (bones[::-1], bones + [bones[-1]]):
            with self.assertRaises(ValueError):
                ac.make_profile("bad", bad, basis=qz(0), centimeters_per_unit=1)
        with self.assertRaises(ValueError):
            ac.make_profile("bad", bones, basis=[0, 0, 0, 0], centimeters_per_unit=1)
        with self.assertRaises(ValueError):
            ac.make_profile("bad", bones, basis=qz(0), centimeters_per_unit=0)

    def test_align_reference_rotates_descendants_without_changing_lengths(self):
        source = [
            {"name": "root", "parent": None, "local": transform([0, 0, 0])},
            {"name": "upper", "parent": "root", "local": transform([0, 0, 10], qz(30))},
            {"name": "lower", "parent": "upper", "local": transform([4, 0, 0], qz(20))},
            {"name": "hand", "parent": "lower", "local": transform([3, 0, 0])},
            {"name": "helper", "parent": "hand", "local": transform([1, 0, 0])},
        ]
        aligned = ac.align_reference(source, [
            {"bone": "upper", "toward": "lower", "direction": [1, 0, 0]},
            {"bone": "lower", "toward": "hand", "direction": [1, 0, 0]},
        ])
        by_name = {b["name"]: b for b in aligned}
        self.assertEqual(len(by_name), 5)
        for name, x in (("lower", 4), ("hand", 7), ("helper", 8)):
            for actual, expected in zip(by_name[name]["reference"]["translation"], [x, 0, 10]):
                self.assertAlmostEqual(actual, expected, places=7)
        for before, after in zip(source, aligned):
            self.assertEqual(before["local"]["translation"], after["reference_local"]["translation"])


@needs_box
@unittest.skipUnless(os.environ.get("LAMPWAY_ANIM_INTAKE_FIXTURE"), "explicit native intake fixture not configured")
class EditorIntakeTests(unittest.TestCase):
    def test_existing_intake_refuses_and_canonical_repeat_preserves_artifacts(self):
        fixture = json.loads(Path(os.environ["LAMPWAY_ANIM_INTAKE_FIXTURE"]).read_text())
        recipe = Path(fixture["recipe"])
        config = json.loads(recipe.read_text())
        out = Path(fixture["out_dir"])
        project = Path(fixture["project"])
        files = list(out.glob("*.json"))
        self.assertEqual(len(files), len(config["sequences"]) + len(config["profiles"]) + 1)
        files += [project.parent / "Content" / (r["asset"][6:] + ".uasset") for r in config["sequences"]]
        files += [project.parent / "Content" / (r["skeleton"][6:] + ".uasset") for r in config["profiles"]]
        files += [Path(r["source"]) for r in config["sequences"]]
        def snapshot():
            return {str(p): {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                             "mtime_ns": p.stat().st_mtime_ns} for p in files}
        before = snapshot()
        command = [sys.executable, str(UE_RECIPES / "anim-normalize-ue.py"), "--config", str(recipe),
                   "--engine", os.environ["UE_ROOT"], "--project", str(project), "--out-dir", str(out)]
        refused = subprocess.run(command + ["--import-fbx"], capture_output=True, text=True)
        self.assertEqual(refused.returncode, 1, refused.stdout + refused.stderr)
        self.assertIn("existing import destination refused", refused.stdout)
        self.assertEqual(snapshot(), before)
        repeated = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(repeated.returncode, 0, repeated.stdout + repeated.stderr)
        self.assertEqual(snapshot(), before)
        receipt = {"verdict": "PASS", "files": before, "refusal": refused.stdout,
                   "repeat": repeated.stdout, "scope": "native intake collision and canonical publication repeat"}
        Path(fixture["receipt"]).write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")


class NormalizationRecipeTests(unittest.TestCase):
    @needs_box
    def test_explicit_fbx_intake_reaches_editor_with_pinned_sources(self):
        path = UE_RECIPES / "anim-normalize-ue.py"
        spec = importlib.util.spec_from_file_location("normalize_intake_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        config = json.loads(path.with_name("anim-normalize-mobility.json").read_text())
        config["sequences"] = config["sequences"][:1]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.fbx"
            source.write_bytes(b"pinned source fixture")
            config["sequences"][0].update(source=str(source), sha256=module.hashlib.sha256(source.read_bytes()).hexdigest())
            recipe = root / "recipe.json"
            recipe.write_text(json.dumps(config))
            result = root / "result.json"
            result.write_text(json.dumps({"errors": ["native fixture deliberately refused"]}))
            run = SimpleNamespace(result_path=str(result), receipt_path=str(root / "receipt.json"))
            with patch.object(module, "run_editor", return_value=run) as editor, redirect_stdout(io.StringIO()) as stdout:
                try:
                    code = module.main(["--config", str(recipe), "--engine", "/unused",
                                        "--project", str(root / "Scratch.uproject"),
                                        "--out-dir", str(root / "output"), "--import-fbx"])
                except SystemExit as exc:
                    code = exc.code
            self.assertEqual(code, 1, stdout.getvalue())
            self.assertTrue(editor.called, stdout.getvalue())
            self.assertTrue(editor.call_args.args[1]["import_fbx"])
            self.assertFalse((root / "output").exists())

    def test_native_blender_comparison_uses_rest_axes_and_detects_motion_error(self):
        path = RC / 'recipes/anim-compare-blender.py'
        spec = importlib.util.spec_from_file_location('blender_compare', path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        p = profile()
        # This native UE profile is expressed in cm; rest axes are deliberately
        # different in Blender. The motion starts away from rest.
        p = ac.make_profile('cm', [{'name':b['name'],'parent':b['parent'],
                                   'bind':b['bind'],'reference':b['reference']} for b in p['bones']],
                            basis=qz(0), centimeters_per_unit=1)
        expected = motion(); decoded = {'bind_pose':{}, 'parents':{}, 'samples':[]}
        offsets = {b['name']:qz(31+i*7) for i,b in enumerate(p['bones'])}
        def world(value, name):
            q=value['rotation']
            result=transform([value['translation'][0],-value['translation'][1],value['translation'][2]],
                             ac.qmul([-q[0],q[1],-q[2],q[3]],offsets[name]))
            result['scale']=[0.01*v for v in value['scale']]
            return result
        for b in p['bones']:
            decoded['bind_pose'][b['name']] = world(b['bind'],b['name'])
            decoded['parents'][b['name']] = b['parent']
        for sample in expected:
            decoded['samples'].append({'time':sample['time'],'pose':{n:world(v,n) for n,v in sample['pose'].items()}})
        check=module.compare_native(expected,p,decoded)
        self.assertEqual(check['verdict'],'PASS')
        bad=copy.deepcopy(decoded)
        bad['samples'][0]['pose']['arm']['rotation']=qz(0)
        self.assertEqual(module.compare_native(expected,p,bad)['verdict'],'FAIL')
        bad=copy.deepcopy(decoded);del bad['bind_pose']['helper']
        with self.assertRaises(ValueError):module.compare_native(expected,p,bad)
        bad=copy.deepcopy(decoded);bad['parents']['helper']='root'
        with self.assertRaises(ValueError):module.compare_native(expected,p,bad)

    def test_published_reference_tables_retain_all_helpers_and_actual_t_directions(self):
        for name, count in (("mobility", 68), ("manny", 161)):
            path = RC / "recipes" / ("anim-profile-" + name + ".json")
            p = json.loads(path.read_text())
            bones = {b["name"]: b for b in p["bones"]}
            self.assertEqual(len(bones), count)
            self.assertTrue({"ik_foot_root", "ik_foot_l", "ik_foot_r", "ik_hand_root",
                             "ik_hand_gun", "ik_hand_l", "ik_hand_r"} <= bones.keys())
            for side, sign in (("l", -1), ("r", 1)):
                for a, b in (("upperarm", "lowerarm"), ("lowerarm", "hand")):
                    start = bones[a + "_" + side]["canonical_reference"]["translation"]
                    end = bones[b + "_" + side]["canonical_reference"]["translation"]
                    self.assertAlmostEqual(start[0], end[0], places=6)
                    self.assertAlmostEqual(start[2], end[2], places=6)
                    self.assertGreater(sign * (end[1] - start[1]), 20)
            for b in bones.values():
                self.assertEqual(b["canonical_reference"]["rotation"], [0, 0, 0, 1])
                self.assertIn("bind_local", b)
                self.assertIn("reference_local", b)
                self.assertIn("canonical_reference_local", b)

    @needs_box
    def test_authored_recipe_has_pins_and_refuses_missing_or_ambiguous_profile(self):
        path = UE_RECIPES / "anim-normalize-ue.py"
        spec = importlib.util.spec_from_file_location("normalization_recipe", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        config = json.loads(path.with_name("anim-normalize-mobility.json").read_text())
        module.validate(config)
        self.assertEqual([p["bones"] for p in config["profiles"]], [68, 161])
        for edit in ("pin", "profile", "traversal"):
            altered = copy.deepcopy(config)
            if edit == "pin":
                altered["sequences"][0]["sha256"] = "123"
            elif edit == "profile":
                altered["profiles"].append(altered["profiles"][0])
            else:
                altered["sequences"][0]["name"] = "../escape"
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                module.validate(altered)

    @needs_box
    def test_recipe_cli_unknown_flags_and_content_first_state(self):
        path = UE_RECIPES / "anim-normalize-ue.py"
        state = subprocess.run([sys.executable, str(path)], capture_output=True, text=True)
        self.assertEqual(state.returncode, 0, state.stdout + state.stderr)
        self.assertIn("state", state.stdout)
        self.assertIn("help", state.stdout)
        invalid = subprocess.run([sys.executable, str(path), "--unknown"], capture_output=True, text=True)
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("error", invalid.stdout)
        self.assertEqual(invalid.stderr, "")


if __name__ == "__main__":
    unittest.main()
