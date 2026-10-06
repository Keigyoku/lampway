<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Rig tools — agent-facing rewrites of MB UE5 Rig Creator Pro and Game Rig Tools

The captain, 2026-10-05: "you guys keep forgetting I have Downloads/Assets/MBTools/ & Downloads/Assets/GameRigTools/ we can
rewrite them for our tools and make them agent facing." This folder is the rewrite specification: one spec per Lampway tool, each
naming the canon page it implements (16-22), the upstream code it ports (with attribution) or re-implements, its contract, its
goldens and its place in the three-input fit pipeline. The orphans lane builds them, with STATUS row O36 (`rig_convert.md`).

## The tools, in build order

| # | Tool | Spec | Canon | Upstream | Port or re-implement | Replaces / upgrades in Lampway | Goldens |
|---|---|---|---|---|---|---|---|
| 1 | `lampway_rig_inspect` | [rig_inspect.md](rig_inspect.md) | 16, 17, 18 | MB `Button_Checkbones` (slot checks) | re-implemented from documented behaviour | new (reads what `skeleton_export_check` reads, plus frames) | R01, R02 |
| 2 | `lampway_rig_map` | [rig_map.md](rig_map.md) | 16 | MB `rigs_liss_my_op` name tables | PORT the tables (data) with attribution; logic re-implemented | upgrades `animation.build_mapping` | R01 |
| 3 | `lampway_rig_normalize` | [rig_normalize.md](rig_normalize.md) | 18 | GRT Apply Armature Scale (Xin), MB auto scale | re-implemented (exact maths; upstream behaviour is the falsifier) | new | R03 |
| 4 | `lampway_rig_conform` | [rig_conform.md](rig_conform.md) | 16, 17 | MB `CreateRig`, `fingersnewup`, `handfingerfix`, `FixHeadRot`, `ShoulderFix`, `spinnew` | re-implemented from documented behaviour | replaces `rig.auto_rig`'s fixed table for mapped rigs | R01, R02 |
| 5 | `lampway_rig_export_ue` | [rig_export_ue.md](rig_export_ue.md) | 21 | MB `exportfbxf`, batch export; GRT's `root` object convention | re-implemented; Titan's measured recipe | upgrades `skeleton_export_check` (frames, scale) and `fit_export` | R02 + G21.2-3 (to build) |
| 6 | `lampway_rig_convert` (O36) | [rig_convert.md](rig_convert.md) | 22 | Titan `animation_canon.py`, `canon.py`, `skin_bind.py` | PORT from Titan (captain's decision owed) | new (O36) | G22.x + Titan suite |
| 7 | `lampway_rig_fit_template` | [rig_fit_template.md](rig_fit_template.md) | 20 | GRT Unreal (append / tweak / apply), Titan `rig-axi.py` | re-implemented (GRT); Titan design ported (decision owed) | replaces `rig.auto_rig` for the fitted example | R06 |
| 8 | `lampway_rig_game_extract` | [rig_game_extract.md](rig_game_extract.md) | 19 | GRT `Deform_Rig_Generator`, `GRT_Convert_Bendy_Bones_To_Bones`, extra operators | PORT with fixes, GPL attribution | new | G19.4 (to build) |
| 9 | `lampway_rig_bake` | [rig_bake.md](rig_bake.md) | 19 | GRT `GRT_Action_Bakery` | frame-range/naming semantics PORTED; bake re-implemented | new | R04 (identity map) |
| 10 | `lampway_rig_retarget` | [rig_retarget.md](rig_retarget.md) | 19, 22 | MB `GetAnimInRigCrea`, `rootmake`; LT `animation_retarget` | re-implemented; upgrades the Lampway tool | upgrades `animation_retarget` (root bone, receipts) | R04, R05 |
| 11 | `lampway_rig_rest_pose` | [rig_rest_pose.md](rig_rest_pose.md) | 19, 04 | MB `helperT`, `PoseUE` | re-implemented from documented behaviour | new | R07 |

**O36's first slice** (the orphans lane): tools 1, 2, 3, 6 and the read-back half of 5 — inspect, map, normalize, the canonical
converter, and the export read-back. They need no Blender-side writing beyond what `skeleton_export_check` already does, and they
are the "external rig-conversion and normalization tool" the Titan ruling names. Tools 4, 5 (write), 7-11 follow.

## How the tools serve the three-input fit pipeline

1. The **fitted example** is rigged by `rig_fit_template` from joints measured on its own mesh (canon 20, 11); when it arrives
   already rigged, `rig_inspect` -> `rig_map` -> `rig_normalize` -> `rig_conform` give it the native bone grammar instead.
2. The example and the native body are posed the same by the pose solver (canon 08) over that grammar.
3. The pieces bind, weight and validate on the NATIVE body (canons 04, 05, 07; ruling 2026-09-30); `rig_export_ue` writes them
   with the measured recipe and reads every bone back.
4. Animation for the native body (and any body) moves through `rig_convert` (canonical, exact) or `rig_retarget` (in Blender,
   measured); `rig_game_extract` and `rig_bake` turn control rigs into engine-clean deform rigs.

## Shared contract rules (every tool)

- AXI: JSON args in, a receipt out (`{ok, ..., sha256: {...}}`), structured refusals naming the fix and the canon page; unknown
  arguments refused with the valid ones; a `dry_run` on every writing tool.
- Never touch the captain's live Blender: tools run in Lampway's headless worker, `nice`, factory-empty scene, Workbench/EEVEE
  renders only.
- Never mutate an input: a writing tool works on a copy unless `in_place: true` is passed and recorded.
- Never: delete actions, join meshes, rename UV layers, rename the user's objects, change preferences, `exec` scene text, delete
  scene objects (all observed upstream, canon 16 D, 19 D).
- Receipts carry the input and output sha256 and the reference sha256; re-running on the same inputs reproduces them.
- A test per tool imports the matching golden case and asserts both the expected values and the falsifier.

## Sources and licences (read 2026-10-05; nothing copied into this folder)

| Upstream | Version | Licence as stated in the files | Attribution for ported code |
|---|---|---|---|
| Game Rig Tools — Core | 4.3.0 (`Game-Rig-Tools-CORE_Blender_5_0_5_1.zip` inside `Game_Rig_Tools_-_Core_Module.zip`); the brief's `..._Blender_4_0.zip` also read for differences | `LICENSE` = GNU GPL v3 full text; `blender_manifest.toml`: `SPDX:GPL-2.0-or-later`; no per-file headers. Maintainer TinkerBoi; docs CGDive | "Portions derived from Game Rig Tools 4.3.0 (TinkerBoi), GPL-2.0-or-later" — compatible with Lampway's GPL-3.0-or-later under either reading |
| Game Rig Tools — Unreal Module | 4.2.0 (`Game_Rig_Tools_UNREAL_Blender4.3~5.1.zip`) | same LICENSE text and manifest licence; bl_info author "BlenderBoi" | as above; its `Assets/*.blend` are Epic mannequin content (UE EULA) — measured (counts, angles), never copied |
| Apply Armature Scale (inside GRT) | — | credited in GRT `Preferences.py:82-88` to Xin, gitlab.com/x190/apply_armature_scale | not ported (canon 18 replaces it) |
| MB UE5 Rig Creator Pro | 3.1.0 (`__init__.py` bl_info; zip identical to the unpacked folder) | `__init__.py:1-12`: GPL "either version 3 of the License, or (at your option) any later version"; no LICENSE file, no copyright line; author "MagicBoneTools" | "Bone-name tables derived from MB UE5 Rig Creator Pro 3.1.0 (MagicBoneTools), GPL-3.0-or-later" |
| Titan tools (`rig-axi.py`, `animation_canon.py`, `canon.py`, `skin_bind.py`, `proc_body.py`, `hand_pose.py`, `views_joints.py`) | Titan worktree at `e3d5ebb5` (rig-axi last touched at `4782f6bb`) | the captain's project repository | port only on the captain's word (rig_convert H.1, rig_fit_template H.1) |

Placeholders: `<assets>` = the captain's `Downloads/Assets`; `<grt-core>` = `GameRigTools-4.3.0/` inside the core zip;
`<grt-unreal>` = `Game_Rig_Tools_Unreal/` inside the Unreal zip; `<mb>` = `MB UE5 Rig Creator Pro/`; `<codex-shelf>`, `<shelf>`,
`<titan>`, `LT` as in canon 01. File:line citations in canon 16-22 and here are to those trees as read on 2026-10-05.

**Reading depth (disclosed).** GRT: every Python file of both modules read in full (core 4,650 lines in 29 files, Unreal
1,405 in 18). MB: 79,026 lines in 23 files, about 16,400 unique, read through a lossless-by-reference view (`dedupe_view.py` in
scratch: a run of four or more lines identical to an earlier run is replaced by a pointer to it; 23,275 view lines). Read in
full through that view: `CreateRig.py`, `AutoScalenew.py`, `ApplyScalear.py`, `Centermake.py`, `FixHeadRot.py`, `dazApplyL.py`,
`fingersnewup.py`, `handfingerfix.py`, `GetAnimInRigCrea.py` (and `GetAnimInWPose.py` by diff against it), `helperT.py`,
`rootmake.py`, `ShoulderFix.py`, `PoseUE.py` (`posemake_op`, `animpose_only_op`, `expoer_fbx_op`; its `makeuerig` is the
panel's copy, diffed), and in `MagicBoneTop_Panel.py`: `MyProperties`, `rigs_liss_my_op` (Rigify, AccuRIG, Mixamo tables and the
start of the DAZ G8 branch), `Button_footfixpm`, `Button_fixfootroto`, `Button_footuezz`, `Button_MakeDEF_Bones`,
`SetTargetName_OT_my_op`, `Button_SetScalerf`, the save/apply operators, `fix_twist_op`, `fix_twistback_op`,
`fbatch_aexport_op`, `write_some_data`. Read only by structure (operator list, called `bpy.ops`, string constants): `MBRigfy.py`,
`naming.py`, `namingbonebutt.py` (79 one-line slot buttons), `selectdele.py`, `spinnew.py` (first operator in full),
`uevspicur.py`, `__init__.py` registration, `Button_Checkbones` (per-slot warnings), `Save_OT`/`Load_OT` (167 keys),
`bone_liss_my_op`, the rest of `rigs_liss_my_op` (other families), `makeuerigauto`, `makeuerigclav`, `hiderigs`,
`deletforbach*`, and the UI panels. Every defect cited was re-read on the raw lines. GRT's `Manual.pdf` and `Resources.pdf` are
pointers to online docs and CGDive videos (no algorithm text); the seven tutorial videos were not watched. MB's `__pycache__`
holds compiled files of modules absent from the source (`ApplyMyPose`, `AutoMatching`, `Autorig_a`, `Autoriga`,
`CreateShape_Keys`, `FastMode`, `FootFix`, `GetAnimGen`, `GetUEPose`, `blenrigop`, `ControlAndAnim`, `autoD`): not inspected
(compiled code is not read).
