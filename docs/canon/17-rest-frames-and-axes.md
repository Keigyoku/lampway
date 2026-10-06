<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Canon 17 — Rest frames and axis conventions: UE5 / MetaHuman bones in Blender, chains, fingers, head, feet

Status: **CANONICAL** conventions and the frame rule; **DRAFT** per-bone up-axis table for the 30 finger bones (owed from the
native skeleton, H.1). Implemented by: MB `CreateRig.py:7164-10742` (arm/leg/foot/clavicle/spine orientation by constraints +
Apply Pose as Rest), MB `fingersnewup.py`, `handfingerfix.py` (finger chains), MB `FixHeadRot.py` (orientations copied from the
reference rig), GRT Unreal `Utility_Functions.py:50-82` (visual transform + Apply Pose as Rest); Titan `tools/proc_body.py:84-133`
(`chain_ends`, `finger_axis`, `curl_delta`), Titan `tools/hand_pose.py`. Builds on canon 01 (frames, the glTF tail fact).

## A. Problem

A bone's rest is a position (head) and a FRAME (three axes). Retargeting, IK rigs, pose solving and the engine's bind all read
the frame; Blender draws a tail. Two conventions coexist and must never mix in one armature:

- **Blender-native** — local Y runs head -> tail along the limb; roll sets X/Z. GRT's `UE5_Manny_DEFORM` (79 bones): the angle
  between each bone's Y and its head->first-child direction has median 0 deg (max 36 deg, branching bones); measured on GRT's
  bundled asset, 2026-10-05.
- **UE axes baked into Blender** — the engine's local axes copied verbatim, so X runs along the limb and Blender's Y (the tail)
  points sideways. GRT's Unreal armature `root` (88 bones): median 90 deg (24.8-155.2). MB's reference rig hard-codes the
  mannequin rest the same way (tails about 18.5 cm off-limb, `MagicBoneTop_Panel.py:1799-4380`, `makeuerig`).

Output of this canon: one frame per bone, computed from joints and the reference skeleton, in ONE declared convention, plus the
exporter setting that carries that convention to the engine unchanged (canon 21).

## B. Method

1. **Detect the convention** of any armature: per bone the angle between local Y and head->child; all ~0 -> `blender`, all ~90
   -> `ue_axes`, else `mixed` -> refuse (golden R02 classifier; tolerance 10 deg on non-branching bones).
2. **The frame rule** (deterministic, joint-driven): `along = unit(child_head - head)` (the next joint on the chain, Titan
   `proc_body.chain_ends`, never the imported tail — canon 01); `up = the reference bone's secondary axis, transported onto this
   limb by the minimal rotation taking the reference along-axis to this along-axis`; `frame = Gram-Schmidt(along, up)` with
   `along` on Y (`blender`) or X (`ue_axes`). Golden R02 checks the construction on a 3-bone arm.
3. **Leaves** (head, hand, foot, ball, finger _03, twist bones): along from the reference bone's along-axis transported by the
   parent's rotation (a leaf has no child joint); a foot's along is ankle -> ball, its up the ground normal; a twist bone takes
   its parent's frame (twist bones rotate about the parent's along-axis only).
4. **Fingers.** Along = joint -> next joint; the BEND axis is the knuckle line: the unit vector index_01 -> pinky_01 (left/right
   signed), orthogonalised against along (Titan `proc_body.finger_axis`; memory gltf-bone-tail-is-not-direction). The thumb's bend
   axis is the normal of its own plane (thumb_01, thumb_02, thumb_03), oriented toward the palm. MB instead asks the person
   which SOURCE axis runs along each finger (booleans `my_boolStand_x/xn/z/zn/zt/znt/xt/xnt`, `handfingerfix.py:1226-2148`) or
   rotates helper bones by fixed T-pose/A-pose quaternions (`CreateRig.py:297-300`, `:379-382`); both are replaced by the
   measured rule.
5. **Orientation transfer from the reference ("head rotation fix").** MB `FixHeadRot.py:36-49` copies every bone's WORLD rotation
   from the reference rig and applies it as rest: correct only when the source limb points like the reference's. The canon
   transports the reference frame (step 2), so a raised arm keeps its own direction and the reference's roll relative to it.
6. **No track-then-apply.** MB orients chains with Damped Track / Locked Track constraints and Apply Pose as Rest
   (`CreateRig.py:7334-7625`, `:10255-10388`): the minimal rotation keeps whatever roll came in, so two sources differing only
   in roll leave with frames 40 deg apart (R02 falsifier); GRT's `apply_all_bone_constraints_and_pose` (`Utility_Functions.py:71-82`)
   bakes constraint results the same way. The canon computes frames in closed form and writes them as rest matrices.
7. **Free-hand offsets are parameters.** MB's per-bone Euler offsets (spine Z offsets `my_string41..49`, clavicle Y/Z
   `my_string50..53`, `MagicBoneTop_Panel.py:5645-5661`; applied `CreateRig.py:10458-10739`) become named, recorded parameters of
   the frame rule, refused when not in the map receipt.

## C. Invariants

- **INV-17.1** One armature, one convention; `mixed` is refused, never exported.
- **INV-17.2** A frame depends only on joints and the reference skeleton (same inputs, same matrices to 1e-9).
- **INV-17.3** Rest frames are proper rotations (det +1); a left-handed result refuses.
- **INV-17.4** Joint positions do not move when frames are rewritten (frames and heads are separate writes).
- **INV-17.5** Never read a limb direction from an imported tail (canon 01).

## D. Failure modes already hit

| Date | What | Lesson | Source |
|---|---|---|---|
| 2026-09-30 | Blender FBX export with `primary_bone_axis='Y'`: joints matched to 1e-4 cm, frames rotated up to 90 deg, gear moved up to 28.8 cm | positions passing is not a frame check (canon 21) | memory native-body-canonical-for-fit |
| 2026-09-29 | glTF-imported UE bones: head->tail is 90 deg off the limb | head -> next joint | memory gltf-bone-tail-is-not-direction |
| 2026-10-05 (read) | MB finger chain: `pinky_02_l` listed twice and `pinky_03_l` missing; `thumb_02_r` Locked-Tracks ITSELF; `thumb_02_l` tracks its parent | chains are generated from the hierarchy, never typed | MB `fingersnewup.py:565`, `:1631-1634`, `:1900-1903` |
| 2026-10-05 (read) | MB left-arm block constrains `hand_r` toward `lowerarm_twist_01_l`; a guard tests `lowerarm_twist_02_r` and constrains `lowerarm_twist_01_r` | one rule per side, generated; effect UNVERIFIED (a later pass may overwrite it) | MB `CreateRig.py:7469`, `:7873-7877` |
| 2026-10-05 (read) | MB hand_l is Damped-Tracked to a helper while hand_r copies a helper's rotation | sides differ by construction -> asymmetric frames | MB `fingersnewup.py:383-390` vs `:411-418` |

## E. Golden tests (`goldens/R02_rest_frames`)

| Test | Fixture | Expected | Falsifier |
|---|---|---|---|
| G17.1 frames | 4 arm joints, up hint +Z | the stored matrices for `blender` and `ue_axes`, angles 0 / 90 deg | — |
| G17.2 classify | the three bones, one mixed set | `blender`, `ue_axes`, `mixed` | an exporter that accepts `mixed` |
| G17.3 roll | the same joints, input rolls 0 and 40 deg | identical frames from the rule | Damped Track keeps the roll: 40.0 deg apart |

## F. Implementation gap

- Lampway (`4e9001c7`): no frame computation; `rig.py:78-93` writes head/tail only (Blender's default roll), so frames are
  whatever Blender's roll-0 rule gives for each tail direction; no convention detector; `export_checks.skeleton_check`
  (`export_checks.py:65-113`) compares names/parents/root/scale but not frames (its bone table holds parent and length only, `export_checks.py:52-62`).
- Titan: `proc_body.chain_ends`/`finger_axis` implement steps 2 and 4 for the fit tools, not as a rig-writing tool.

## G. Agent-facing tool contract — part of `lampway_rig_conform` (spec: `rig_tools/rig_conform.md`)

```json
{"armature": "object", "map": "rig/<name>.map.json", "convention": "blender|ue_axes", "reference": "fit_body package | reference FBX",
 "offsets": {"<bone>": {"roll_deg": 0.0}}, "dry_run": false}
```
Refusals: `mixed` input without `convention`; a bone whose along-axis is undefined (head = child head); a finger chain missing a
knuckle joint (the bend axis needs index_01 and pinky_01). Receipt: per bone `{angle_to_reference_deg, along_source, up_source}`,
the detected input convention, the output convention.

## H. Decisions owed by the captain

1. The finger up-axis table: take it from the native MetaHuman skeleton (recommended; measured once, sha-pinned) or from GRT's
   Manny asset.
2. Which convention Lampway keeps inside Blender: `blender` (recommended — Titan's measured export recipe converts axes at the
   FBX writer, canon 21) or `ue_axes` (GRT/MB style). Mixing the two is the 28.8 cm failure.
