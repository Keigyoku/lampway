<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Canon 20 — Template fit: rig the fitted example from its own mesh (the three-input pipeline's rig step)

Status: **CANONICAL** method and provenance rule; **DRAFT** joint sources for the hidden joints (pelvis, hips under a skirt; H.1).
Implemented by: Titan `tools/rig-axi.py` (`joints`, `fit`, `check`, `weights`, `slices`), Titan `tools/views_joints.py`,
`tools/hand_pose.py`, `tools/proc_body.py`; GRT Unreal module (`grt.append_mannequin`, `grt.tweak_rig`, `grt.apply_rig`); shelf
`grt/rigfit.py` (2026-09-28, the defective first run); Lampway LT `features/rig.py:131-157` (`auto_rig`, landmark heuristics).
Builds on canons 11 (joints from views), 16 (mapping, synthesis), 17 (frames), 07 (weights), 08 (pose solve).

## A. Problem

The captain's law (2026-09-29, memory three-input-fit-pipeline): a set is made from a fitted example on a humanoid, the native
body, and the separate pieces; "we rig the fitted example, then ref-pose the fitted example and the MetaHuman the same". The rig
step places the engine skeleton at the EXAMPLE's own joints, so posing the example and the native body into one pose compares
like with like. Inputs: the example mesh, its joints (measured), the template skeleton (the native body's). Output: a rigged
example whose joint heads equal the measured joints, frames per canon 17, a per-joint residual and inside-check receipt.

## B. Method

1. **Joints are measured on the example, never read from the template's body.** Sources, in order: (a) multi-view 2D keypoints,
   triangulated, calibrated by the offsets the native body's known joints measure in the same cameras, each limb joint centred in
   its cross-section (canon 11; Titan `rig-axi.py:16-21`, `:373-429`); (b) the hand model for the 30 finger joints (`rig-axi.py:22-24`,
   `:357-370`; the whole-body model read fingers 0.3-2.6 cm off, 2026-09-29); (c) a mapped existing rig when the example arrives
   rigged (canon 16). Hidden joints (pelvis, hips under armour or cloth) keep a base measurement and are named in the receipt
   (`rig-axi.py:81`, `HIDDEN_DEFAULT = 'pelvis,thigh_l,thigh_r'`).
2. **Fit = write the joints.** The template's joint heads are set to the measured joints (golden R06: residual 0); bones the
   measurement does not name (twists, metacarpals, spine_03/04, neck_02) are synthesized at the template's fractions (canon 16
   B.4); frames by canon 17. A numeric fit (Titan `rig-axi fit`: GRT's tweak controls moved by damped Gauss-Newton on a measured
   Jacobian of joint heads against control translations, `rig-axi.py:29-31`; shelf `grt/rigfit.py:37-48`) is needed only when the
   template is a control rig whose controls do not map one-to-one to joints; it reached rms 0.017 cm, max 0.045 cm on the warrior
   (shelf `grt/rig_axi/run3.log`).
3. **Provenance is checked, not trusted.** A joints file records the sha256 of the mesh it measured (`rig-axi.py:423`,
   `example_sha256`); the fit refuses a joints file whose mesh sha differs from the example's. A fit whose every bone length
   equals the template's within 0.1 % is flagged `copied_not_fitted` (R06): the 2026-09-28 rig had joints within 0.1 cm of the
   MetaHuman's rest and identical bone lengths because `rigfit.py` targeted the MetaHuman skeleton (`rigfit.py:19-20`).
4. **Inside check.** Every joint lies inside the example's volume: six axis rays from the joint each hit the mesh (Titan
   `rig-axi check`); joints outside are listed (run3: 11 finger joints outside -> fingers re-measured by B.1b).
5. **The example's own weights** come from the procedural body on the fitted bones, transferred to the example (Titan
   `rig-axi.py:32-37`; canon 07), never copied from the native body: the defective rig copied the MetaHuman's weights, so posing
   the example moved it like the MetaHuman, not like itself.
6. **Ref-pose both.** The example rig and the native body are posed into the same pose by the pose solver over the shared joint
   grammar (canon 08). The pieces' bind, weights and validation are the NATIVE body's (memory native-body-canonical-for-fit,
   2026-09-30; canons 04, 05, 07): the example rig supplies the pose and the armour-to-body relationship, the native body the
   bind (REPORT contradiction 1).
7. **The GRT mechanism, for reference.** GRT appends a Mannequin collection with three armatures (TWEAK = controls, DEFORM =
   Blender-native frames, `root` = UE-axes frames, measured 410 / 79 / 88 bones), the person moves TWEAK controls onto the
   character, and Apply Rig bakes the constraint results into the rests (`Apply_Rig.py:30-51`, `Utility_Functions.py:50-82`).
   The canon keeps the triad's idea (a Blender-native deform rig and an engine-axes export rig derived from it, canon 21) and
   replaces the hand placement by B.1-B.2.

## C. Invariants

- **INV-20.1** No joint of the fitted example comes from the template's body; the joints file's mesh sha256 equals the example's.
- **INV-20.2** Residual between fitted heads and measured joints <= 1e-6 m for written joints; a numeric fit reports its rms/max.
- **INV-20.3** `copied_not_fitted` is a refusal unless the example IS the template body (then the tool says so).
- **INV-20.4** Hidden and synthesized joints are listed with their rule.
- **INV-20.5** Every joint inside the example, or listed.

## D. Failure modes already hit

| Date | What | Lesson | Source |
|---|---|---|---|
| 2026-09-28 | The warrior's UE5 rig: joints fitted to the MetaHuman skeleton registered into the warrior (0.04-0.1 cm), weights copied from the MetaHuman; "ref-posing did nothing" | B.1, B.3, B.5 | memory rigged-warrior-oracle, three-input-fit-pipeline; shelf `grt/rigfit.py:19-20` |
| 2026-09-29 | Whole-body keypoints read the fingers 0.3-2.6 cm off | fingers from the hand model | Titan `rig-axi.py:357-358` |
| 2026-09-29 | 11 finger joints outside the warrior after the views fit | the inside check is part of the fit | shelf `grt/rig_axi/run3.log` |
| 2026-09-29 | The motion check crashed: `bpy_prop_collection[slice]: slice steps not supported` | no `[::n]` on bpy collections | shelf `grt/rig_axi/run5.log`; memory bpy-collection-no-slice-step |

## E. Golden tests (`goldens/R06_template_fit`)

| Test | Fixture | Expected | Falsifier |
|---|---|---|---|
| G20.1 fit | an 11-joint synthetic template; example = legs x1.08, arms x0.95, torso shifted 3 cm | heads = example joints (residual 0); ratios 1.08 / 0.95 | — |
| G20.2 provenance | joints taken from the template itself | `copied_not_fitted` | accepting it |
| G20.3 missing joint | the example's head joint removed | refused | borrowing the template's head |

## F. Implementation gap

- Lampway (`4e9001c7`): `auto_rig` places a fixed UE-named skeleton from height fractions and arm span measured on a T-pose mesh
  (`rig.py:35-75`): no measured joints, no fingers, no twist bones, no provenance, no inside check; weights are Blender heat maps
  with a proximity fallback (`rig.py:142-153`), not the procedural body.
- Titan `rig-axi.py` implements B.1-B.5 as an AXI tool on GRT's Unreal module; its motion check uses world-axis test poses
  (`rig-axi.py:85-92`), not the joint-named grammar of canons 05/08.

## G. Agent-facing tool contract — `lampway_rig_fit_template` (spec: `rig_tools/rig_fit_template.md`)

```json
{"example": "object | .glb", "joints": "joints.json (titan.rig-joints/1) | 'views' | 'rig:<armature>'", "template": "fit_body package",
 "hands": "views | none", "hidden": ["pelvis", "thigh_l", "thigh_r"], "convention": "blender", "out": "rig/<example>.rig.blend"}
```
Refusals: joints file mesh sha256 != example sha256; `copied_not_fitted`; a required joint missing; joints outside the example
(listed) unless `allow_outside` names them. Receipt: `{residual: {rms_m, max_m}, ratios, synthesized, hidden, outside, sha256:
{example, joints, template, out}}`.

## H. Decisions owed by the captain

1. Hidden joints under armour (pelvis, hips): keep the base measurement, or estimate from the native body's proportions scaled
   to the measured knee/shoulder joints?
2. REPORT contradiction 1 (the example's weights vs the native body's): this canon follows the 2026-09-30 ruling for the pieces.
