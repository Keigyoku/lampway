<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# `lampway_rig_map` — source bones to the project's slots, as a receipt

**Build order 2.** Canon 16.

## Purpose

Produce `map.json`: every UE slot -> the source bone that fills it (or the synthesis rule that places it), the unmapped source
bones, the family, the required set it ran against, and the hashes that make it reproducible. Every later tool takes this file
instead of re-deriving a mapping.

## Upstream

- **Ported (data):** MB's per-family bone-name tables in `rigs_liss_my_op` (`MagicBoneTop_Panel.py:19258-30067`): Rigify
  (`:19290-19412`), ActorCore AccuRIG (`:19417-19540`), Mixamo (`:19547-19660`), then UE4, Auto-Rig UE4, CC3/4, Human Generator,
  DAZ G8/G9 (five variants each), VRoid VRM 0/1. Ported as JSON tables under `rig/families/<family>.json`, each file headed
  "Bone-name tables derived from MB UE5 Rig Creator Pro 3.1.0 (MagicBoneTools), GPL-3.0-or-later". Each table is VERIFIED
  against one real rig of that family before it ships (a table row is a claim: MB's AccuRIG table maps `head` to `CC_Base_NeckTwist02`,
  `:19461`, unverified here).
- **Not ported:** MB's per-family side effects (the DAZ G8 branch edits mesh vertex groups, `:19670-19737`; the axis booleans
  `my_boolStand_*` set per family, `:19401-19412`) — canon 17 measures axes instead.
- **Re-implemented:** detection, mapping, synthesis, receipts (canon 16 B.2-B.7); Lampway's `animation.build_mapping` label
  parse (`animation.py:44-68`) becomes the fallback proposer, marked `by: label`.

## Contract

```json
{"armature": "object | file", "family": "auto|<family>|<map.json>", "profile": "ue5_body|ue5_body_fingers|metahuman",
 "reference": "fit_body package | reference FBX", "synthesize": true, "out": "rig/<name>.map.json", "dry_run": false}
```
Refusals: a family tie (the hits printed); a REQUIRED slot missing (named) with no synthesis rule; a synthesized slot on a
chain with fewer than two mapped joints; two slots mapped to one bone; an existing different `out`.
Receipt = the written map: `{schema: "lampway.rig-map/1", family, hits, required_set, map: {slot: {source, by}},
synthesized: {slot: {chain, fraction}}, unmapped, collision_renames, sha256: {source_rest, reference_rest, tables}}`.

## Goldens

R01: family hits, slot map, tie refusal, synthesis at reference fractions (spine_03 0.500, spine_04 0.722); falsifiers:
substring mapping (`hand_l` -> `LeftHandIndex1`), midpoint synthesis (65.3 mm).

## Place in the three-input pipeline

A rigged example and every animation source pass through the map; the native body's own map is the identity and is written once
as the reference.

## Upgrades

`animation_retarget`'s `mapping="auto"` calls this tool and stores its map instead of writing `anim/presets/<src>__<tgt>.json`
on every run (`animation.py:350-356`).
