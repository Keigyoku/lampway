<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# `lampway_rig_game_extract` — an engine-clean deform rig from any control rig

**Build order 8.** Canon 19 B.4. The rewrite of GRT's "Generate Game Rig" and its extra operators.

## Purpose

From a control rig (Rigify, a tweak rig, any constraint stack) produce a deform-only game rig that follows it through
constraints, with every mesh re-pointed to it, ready for `rig_bake`.

## Upstream — PORTED with fixes

"Portions derived from Game Rig Tools 4.3.0 (TinkerBoi), GPL-2.0-or-later" on the ported module.

- `Deform_Rig_Generator.py` `GRT_Generate_Game_Rig.execute` (`:344-635`): copy control object and data (`:402-409`), Rigify
  hierarchy fix (`:421-438`), per-bone cleanup (`:469-534`), pose-bone cleanup and constraints to the control twin
  (`:550-609`), mesh re-pointing with world matrix kept (`:612-624`). Extract modes (`:16-21`), hierarchy modes (`:50-54`),
  constraint types (`:11-15`).
- `GRT_Convert_Bendy_Bones_To_Bones.py` (`:125-291`): one bone per B-Bone segment from `bbone_segment_matrix(i, rest=True)`,
  Armature constraint to the bendy bone, Damped Track to the next segment / stretch target / child at the tail / own tail,
  Limit Scale 1 unless stretch.
- Utilities kept as verbs: flatten hierarchy, disconnect bones, proximity parent (orphan -> bone whose TAIL is nearest the
  child's HEAD within `max_distance`; `GRT_Proximity_Parent.py:88-113`), unbind mesh (`GRT_Unbind.py:46-64`), batch rename
  vertex groups, constraint to armature by name (`GRT_Constraint_To_Armature.py`), mute/unmute.

Fixes carried into the port (each has a test): the collection reset moved out of the per-bone loop (measured: only the last
bone ended in "Deform", `:493-510`); `Hierarchy_Mode` is the one hierarchy argument and the presets set it (the "Flat" preset
never flattened, `:354-362`; it set a removed property, preset line 13); no `exec` of scene text (`:630-633` dropped);
`Unlock Bones Transform` flags un-swapped (`GRT_Unlock_Bones_Transform.py:35-43`, measured); `Disconnect All Bones` refuses
with no armature instead of `NameError` (`GRT_Disconnect_All_Bones.py:15-22`); removals collect names first, then remove
(GRT iterates the collection it removes from: no skip observed on Blender 5.2, kept as a guard).

## Contract

```json
{"control": "armature", "name": "<control>_game", "extract": "deform|selected|selected_deform|deform_and_selected",
 "hierarchy": "keep|rigify_fix|flat", "constraint": "lotrot|transform|none", "root_scale_from": "auto|<bone>|none",
 "bbones": "refuse|convert", "rebind_meshes": true, "collection": "Deform", "dry_run": false}
```
Refusals: B-Bones present with `bbones: refuse`; a deform bone whose nearest deform ancestor is ambiguous under `rigify_fix`
(two `DEF-` twins); a mesh parented to the control with a non-identity parent inverse it cannot preserve; the game name taken by
a different object.
Receipt: `{bones: {kept, dropped}, hierarchy_changes, constraints_added, meshes_repointed, collection_members, sha256: {control,
game}}` — `collection_members` equals `kept` (the measured GRT defect is the falsifier).

## Goldens

G19.4 (to build, headless): the 9-bone probe rig of 2026-10-05 (5 deform, 4 control bones, one spine bone with 4 constraints):
5 kept, all 5 in the collection, hierarchy per mode, the spine's four control constraints gone and two `lotrot` constraints
present, meshes re-pointed; GRT 4.3.0's result (1 of 5 in the collection) is the falsifier.

## Place in the three-input pipeline

Animation authored on a control rig (Rigify, the captain's tweak rigs) becomes keys on the deform skeleton the pieces ride.

## Upgrades

New.
