<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# `lampway_rig_bake` — constraint-driven motion to plain keys, action by action

**Build order 9.** Canon 19 B.6. The rewrite of GRT's "Action Bakery".

## Purpose

For each listed action of a driver rig (the control rig after `rig_game_extract`, or a retarget's constraint setup), write a
clean action on the target rig: parent-first local keys sampled from evaluated world matrices, named by rule, with a per-frame
world-error receipt.

## Upstream

- **Ported semantics** ("Portions derived from Game Rig Tools 4.3.0 (TinkerBoi), GPL-2.0-or-later"): the bake list and its
  loaders (by name, all, active, from NLA; `GRT_Action_Bakery.py:154-341`), frame-range modes ACTION / SET / TRIM with an
  inclusive end (`:1221-1237`), naming by prefix / suffix / replace or a local name (`:1186-1216`, `:1023-1047`), the
  same-name check before baking (`check_invalid_name`, `:1050-1064`), overwrite by rename-remap-remove (`:1246-1252`), offset
  to frame one (`:1300-1306`), push to NLA with stale-track cleanup (`:1310-1345`), unmute-before / mute-after (`:1167-1171`,
  `:1353-1357`).
- **Re-implemented:** the bake itself — GRT calls `anim_utils.bake_action_objects` with visual keying (`:1261-1278`); the port
  samples world matrices and writes keys parent-first (the same solve as `rig_retarget` with an identity map), so the result
  does not depend on constraint evaluation order and the receipt can state the error.
- Fixes: `bl_options` (GRT declares `bl_info`, no undo, `:1079`); an action list on a rig with no animation data refuses loudly
  instead of doing nothing (`:1153`); the control rig's previous action is restored even when it had none (`:1359-1361`).

## Contract

```json
{"driver": "armature", "target": "armature", "actions": ["names"] , "frames": "action|[start, end]|trim:[a, b]",
 "name": {"mode": "suffix|prefix|replace|local", "value": "_baked", "to": ""}, "overwrite": false, "offset_to_one": false,
 "push_to_nla": true, "channels": ["location", "rotation", "scale"], "dry_run": false}
```
Refusals: a baked name equal to its source action's name with `overwrite` (GRT's own refusal, kept); an action that drives no
bone of the driver; frame range empty; target bones missing from the driver's mapping.
Receipt per action: `{source, baked, frames: [start, end], keys, max_world_error: {m, deg}, nla_track}`; any frame over 1e-4 m or
0.01 deg fails that action and leaves no partial action behind.

## Goldens

R04 with an identity map (bake equals the driver to storage precision); a headless test bakes a 2-bone constraint rig over 10
frames and checks the receipt rows.

## Place in the three-input pipeline

Turns animation on control rigs into keys the native body and the pieces can play; the input to `rig_convert` for the engine.

## Upgrades

New. LT `animation_retarget`'s `constraints` method (`animation.py:285-296`) becomes `rig_retarget` + this bake.
