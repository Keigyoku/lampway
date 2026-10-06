<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# `lampway_rig_convert` — the external rig-conversion and normalization tool (STATUS O36)

**Build order 6; O36's core.** Canon 22 (the maths), with 16 (maps), 18 (units, uniform scale), 19 (retarget rule), 21 (native
emission is judged by read-back bars).

## Purpose

The Titan ruling (captain, by 2026-09-15, recorded in `<codex-shelf>/blocked-slice-33-normalize-owner.md`): "the rig-conversion and
normalization is all external. The input the Game takes is the output from the external tool". This tool is that external
step for Lampway: profile a native rig, normalize its animation (and later skin and mesh) to the canonical form of Titan ADR
0012, adapt it back onto the ORIGINAL rig of any world, retarget between profiles, compare and verify — with exact receipts.

## Upstream

Port from Titan, on the captain's word (H.1): `tools/animation_canon.py` (profile, align_reference, normalize, adapt, compare,
retarget; 439 lines, pure Python, no numpy), `tools/canon.py` (unrigged mesh normalize/adapt/serialize, 280 lines),
`tools/skin_bind.py` (capture, rebind, evaluate, 228 lines), and the reviewed publication layer of Titan Task 130
(`rig-convert.py convert --recipe --out`, `rig_convert.prepare_transfer` / `publish_transfer`; on the codex lane's branch at
`480ecc44`, not in this worktree — `<codex-shelf>/review-task130-canonical-converter-*.md`). Their tests come with them and run
unchanged as the first golden suite. Nothing of GRT or MB is used.

## Contract

```json
{"verb": "profile|normalize|adapt|retarget|compare|verify|publish",
 "input": "native packet | canonical packet", "profile": "profile.json", "target_profile": "profile.json",
 "rules": "rules.json", "recipe": "recipe.json", "out": "file", "dry_run": false}
```
- `profile`: from an inspected native rig (bind + reference tables, adapter basis, cm per unit) -> `titan.animation-profile/1`.
- `normalize` / `adapt`: canon 22 B.4; `adapt` targets the ORIGINAL profile only.
- `retarget`: canon 22 B.8 with an exhaustive rules file (map, reference_follow, translation_scales, anchors).
- `compare` / `verify`: rows per bone and time; `verify` applies ADR 0012 A1's bars to a native emission and records both hashes.
- `publish`: immutable output + adjacent receipt; preflight both destinations; input alias / hard-link / symlink guards; a
  different existing output refuses; an identical repeat keeps bytes and mtimes.
Refusals: incomplete or non-rebuilding profile; non-uniform scale; schedule not 30 fps rational + terminal; incomplete map;
roster mismatch; raw native input where canonical is required; a different existing output.
Receipt: `{verb, sha256: {input, profile, target_profile, rules, recipe, output}, owners: {module: version}, rows_over_bars,
both_hashes}`.

## Goldens

The ported Titan test suite (as reviewed: Task 130 recorded 23 of 26 tests passing with 3 skips on its focused controls, 199 of
203 on the wider set), plus G22.1-G22.4 (round trip, retarget agreement with R04, scale refusal, time schedule).

## Place in the three-input pipeline

Animation for the native body and for every rig the pieces ride travels through the canonical form; the engine receives the
adapter's output (the Game reads only this tool's output, per the ruling).

## Upgrades

New (O36). Lampway's in-Blender `animation_retarget` remains for interactive work and is checked against `retarget` on R04's
profiles (they implement one rule).

## Decisions owed

1. Port the Titan modules into Lampway (same owner; Lampway GPL-3.0-or-later) or call Titan's tool as an external process?
2. The skin/morph half (Titan Task 131, open): ship animation first and refuse skin packets until 131 closes?
