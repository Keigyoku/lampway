<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Canon 01 — Frames, units, bones and identities (the conventions every other canon cites)

Status: **CANONICAL** (every row below is a measured fact with its source; nothing here is a design choice).
Implemented by: no single tool; every fit, weight, pose, bake and export tool must state which row it relies on.

## A. Problem

Every algorithm in this canon moves points between frames: a generator's export, Blender's import, the body package, the
piece's own frame, Unreal's component space. Most re-derivations in the project's history started with a frame or a bone
convention guessed from memory. This page pins them once.

## B. The frames (measured)

| Frame | Up | Front | Wearer's left | Units | Handed | Source |
|---|---|---|---|---|---|---|
| **Body frame** (all fit tools; `body.npz`, `placed.npz`) | +Z | **-Y** (the body faces -Y) | **+X** | metres | right | shelf `proportion/place_piece.py:4`, `proportion/proportion_fit.py:9`; LT `pipeline/fit_place.py:11` |
| Tripo / Hi3D glTF as exported | +Y | +X | (glTF -Z) | ~0.98 m longest side, NOT real size | right | memory tripo-studio-invariants ("glTF frame (Y up, front +X)"); memory pipeline-set-hp-lp ("normalised to ~0.98 m") |
| Same file after Blender glTF import | +Z | +X | **+Y** | as exported | right | memory tripo-studio-invariants (Edit Mesh bbox "From the Blender-import frame (X front, Y wearer's left, Z up)"); shelf `partseg/delete_caps.py:5` |
| Import -> body frame | a turn of **-90 deg about Z** maps X-front to -Y-front and Y-left to +X-left | | | | | shelf `proportion/proportion_ratios.py:12` ("Tripo FBX / Triangle glb: -90") |
| Unreal asset / component space | +Z | (asset-dependent) | | **centimetres** | **left** | Titan `armour-validate.py sidecar` conventions block, LT `features/fit_body.py:23` |
| MetaHuman native body | Z up; wearer's left is UE +X (measured from the left bracer's placement) | | | cm | left | Titan `docs/design/GENERATED-EQUIPMENT.md` §7f |

Per-piece facing is NOT uniform even inside one Tripo set: in the "proportioned" Pipeline set the greaves and helmet face
+X, the chest -Y and the waist's wide axis is Y; the chest's low-poly is turned +90 deg about Z against its high-poly and
the gauntlets' 270 deg (memory pipeline-set-hp-lp). **A tool never assumes the turn; it takes `turn_deg` as an input and
the placement report records it.**

**Absolute size never survives a generator.** Tripo normalises every file to ~0.98 m on its longest side; the captain's
nine pre-pipeline FBXs all measured 0.99951171875 Blender units longest dimension (`<codex-shelf>/captain-equipment-assessment.md`,
2026-09-21). Scale comes from the body at placement (canon 09), per piece, never one shared multiplier.

## C. Bones (measured)

1. **A Blender-imported UE bone's head->tail is NOT its direction.** Blender's glTF import lays every UE bone's head-to-tail
   about 90 deg off its limb, at a different length; measured 2026-09-29 on the rig-axi rig AND on the MetaHuman import
   (memory gltf-bone-tail-is-not-direction). A bone's direction is **head -> the head of its continuation child**:
   `titan/tools/proc_body.py:133 chain_ends` (a named continuation where a bone has several children: pelvis->spine_01,
   spine_05->neck_01, hand->middle_01; a leaf continues its parent's line by 0.8).
2. **Fingers flex about the knuckle line** (`proc_body.py:124 finger_axis`, index_01 -> pinky_01 on the right hand), never
   about bone x palm. The opposite line (pinky -> index) bent the fingers BACK (Titan `recipes/armour-poses.json` "why",
   measured on the engine's own rest skeleton 2026-09-30).
3. **The FBX bone axis decides UE bone frames, positions do not.** A Blender FBX with `primary_bone_axis='Y'` matched joint
   positions to 1e-4 cm while its bone frames were rotated up to 90 deg, moving gear up to 28.8 cm; primary Z / secondary X
   fixed the frames; a centimetre-native FBX (UnitScaleFactor 1, FBX_SCALE_NONE + apply_unit_scale, primary Z / secondary X)
   passed all 342 bone rows (run26, 2026-09-30; memory native-body-canonical-for-fit). **A position-only read-back is never
   an export gate.**
4. **A frame change of a bone cancels in skinning but not in leader-pose binding.** For any per-joint right correction D,
   (P D)(B D)^-1 = P B^-1: rotating a bone's local frame in BOTH its bind and its pose leaves skinned geometry unchanged
   (`<codex-shelf>/task131-skin-reference-next-design.md`, "Second measurement", Blender oracle within 5.9e-7 units,
   2026-09-16). It does NOT leave a UE leader-pose follower unchanged: there the piece's own bind must equal the native
   reference bone by bone (C.3 and canon 05 `bind_mismatch`).
5. **MetaHuman correctives and twist leaves carry authored NON-uniform scale.** In two production clips 45 leaf bones carried
   scale triples like (0.515, 1.255, 1.647) (`<codex-shelf>/task131-production-scale-design.md`, 2026-09-21). A
   similarity-only pose/animation path must refuse them, never average or drop them; replaying such a pose in validation needs
   affine bone matrices.
6. **The body's skeleton is the full rig.** `SKM_Manny_Simple` has 89 bones and is missing 72 of the 161 profile bones
   (`<codex-shelf>/task131-production-scale-design.md`, "Export dependency measurement"); the MetaHuman FullBody has 342
   (memory native-body-canonical-for-fit). A fit tool refuses a body package with a partial roster.

## D. Identities (measured)

1. **Tripo smart meshes split vertices at every UV seam.** Vertex-index adjacency sees every UV island as its own component;
   weld by position (1e-5 m worked on the chest) before any adjacency-based segmentation, weighting or measurement
   (memory smart-mesh-seams-split-vertices; golden C09 `split_seam`).
2. **A weld by position alone can invent identity across independent topology** (lips, eyelids authored coincident at rest and
   separate in motion). Weld for adjacency and weight sharing on GENERATED armour; never as a publication step on an authored
   rig (`<codex-shelf>/task131-weld-refusal-repair-design.md`, rejected alternative; 2026-09-17).
3. **Render vertices map to source vertices by rest position, never by index** (Titan `armour_validate.py:746 map_to_source`).
4. **Mirroring reverses winding.** Handedness (a coordinate reflection) and front-face convention are separate; an adapter that
   reflects must re-order triangle corners and prove it against the original traversal by cyclic correspondence
   (`<codex-shelf>/task131-native-winding-repair-design.md`; all 64,094 triangles had been emitted reversed and an unordered
   comparator hid it, 2026-09-21). Two-sided materials are not a repair.

## E. Placeholders used in every canon page

| Placeholder | Meaning |
|---|---|
| `<memory>` | the TITAN crew's memory directory (`~/.claude/projects/<titan key>/memory/`); "memory X" = `<memory>/X.md` |
| `<shelf>` | the claude-2 helper crew's data directory in the vault's resident data folder |
| `<shelf-scratch>` | that shelf's scratch work area (the crew's `scratch/` per-user directory) |
| `<codex-shelf>`, `<astra-shelf>` | the codex-1 helper crew's and the astra-1 spike crew's data directories, beside `<shelf>` (read only) |
| `<titan>` / "Titan" | the TITAN project repository, the claude-2 helper crew's worktree at `e3d5ebb5` |
| `<lampway>` | the Lampway integration worktree `wt-wave5` at `b806617f` (branch `lp/wave5`); canons 16-22 and `rig_tools/` cite it at `4e9001c7` (the same worktree after the lane merges) |
| `LT` | `<lampway>/src/scripts/mixar/modules/lampway_tools` |
| `<specs>` | the Lampway spec tree (this canon's parent) |
| `<assets>`, `<grt-core>`, `<grt-unreal>`, `<mb>` | the captain's Downloads/Assets folder and the three add-on trees inside it (Game Rig Tools core 4.3.0, Unreal module 4.2.0, MB UE5 Rig Creator Pro 3.1.0); defined in `rig_tools/README.md` |

## F. Agent-facing contract

No tool. Every canon tool's receipt carries a `conventions` block: `{frame, units, turn_deg, bone_direction: "head->child head",
bone_axis_export: "Z/X", weld_m, source_frame}`. A tool that cannot fill a field refuses with the field's name.

Native MetaHuman metacarpals continue to their named finger01 joints beside slide drivers; finger01 continues to02 and02 to03 beside half/dip helpers. Terminal03 with only its exact same-finger/same-side bulge/half children is an anatomical leaf: continue its parent line by0.8, including a single auxiliary child. Any other terminal child is refused, never chosen as a continuation. `tests/lampway_tools/test_native_metacarpal_normalize.py` pins this fanout with actual bone geometry.

`tests/lampway_tools/test_native_terminal_fingers.py` pins all ten terminal joints, one/two auxiliary children, unchanged authored frames, shared weighting endpoints and unknown-child falsifiers. The actual native receipt exposed pinky03 bulge/half fanout; the complete342-name roster confirms these auxiliary names. Full parent/child roster verification remains a separate owner receipt.
