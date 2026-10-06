<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# `lampway_rig_retarget` — motion from one skeleton onto another, with a root bone when asked

**Build order 10.** Canon 19 B.1-B.3, B.5; canon 22 B.8 (the canonical twin).

## Purpose

Upgrade Lampway's `animation_retarget` from "bake a mapped rotation retarget" to the full canonical tool: map from `rig_map`,
rotation retarget `W_t = W_s R_s^-1 R_t`, pelvis travel scaled by the pelvis-height ratio, an optional `root` bone extracted from
the pelvis (ground projection, yaw none or heading), and receipts that can be compared with `rig_convert retarget`.

## Upstream

- **Lampway `features/animation.py` (upgraded in place):** mapping (`:44-68`), rest compensation and parent-first keys
  (`:212-283`), root scale (`:216-221`), measurement of world-angle error, foot slide and edge stretch (`:297-339`).
- **MB (re-implemented from documented behaviour, not ported):** the offset-parent retarget of `GetAnimInRigCrea.py` (UE bones
  parented to mapped source bones, `:244-717`, Copy Transforms in pose space, `:168-172`, `:768-770`; nla bake, `:1110`) — exact
  only for a target built from the source's own rest; R04's falsifier (30 mm length drift) shows why it is not the general
  method. MB's root bone (`rootmake.py`; `GetAnimInRigCrea.py:869-895`): ground projection with per-axis toggles, rotation
  toggles default off (`MagicBoneTop_Panel.py:5783-5785`) — the canon's `yaw: none` default.

## Contract

```json
{"source": "armature | file", "target": "armature", "action": "name|all", "map": "auto|rig/<x>.map.json", "method": "matrix",
 "root_motion": "keep|in_place|root_bone", "root_yaw": "none|heading", "scale": "auto|<float>", "frames": "action|[a, b]",
 "fps": null, "check_objects": [], "name": "<action>_rt", "dry_run": false}
```
Refusals (existing ones kept, `animation.py:132-196`): unknown method / root_motion / scale range; required slots missing (now
named from the map); a source without animation. New: `root_bone` on a target with no `root` bone in its reference; a map whose
source sha differs.
Receipt (existing fields kept, `animation.py:343-347`) plus `{root: {bone, yaw, max_tilt_deg, recompose_error_m},
map_sha256, canonical_agreement_deg}` — the last when `rig_convert` is installed: the same retarget computed canonically on the
two profiles and compared.

## Goldens

R04 (rule, parent-first keys; falsifiers local copy 55.7 deg, pose-space copy 30 mm); R05 (root bone: z 0, tilt 0, exact
recomposition; falsifier 5.96 deg); G22.2 (agreement with the canonical retarget).

## Place in the three-input pipeline

Gives the native body (and the example, for its motion check) the animations the pieces must survive; the pose tests of canon
05 replay its keys.

## Upgrades

`animation_retarget` keeps its name as an alias; the `constraints` method moves to `rig_bake`; presets stop being written on
every run (`animation.py:350-356`) — the map file is the record.
