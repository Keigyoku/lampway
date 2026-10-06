<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Canon implementation plan

What an implementer builds, in what order, which existing Lampway tool each item replaces or upgrades, and the agent skill
entries that make agents call the canon's tools instead of improvising. Every item is RED-first against the named goldens; a
golden's falsifier must be observed failing the OLD code before the new code lands. Laws: `<specs>/CONTRACT_TEMPLATE.md`
(proven code first; model slots behind the same interface; no credit spend without the captain's click).

## 1. Order (dependencies first)

| # | Item | Canon | Replaces / upgrades (LT = `lampway_tools`) | RED goldens | Size |
|---|---|---|---|---|---|
| 1 | **`canon_geom` — one module of shared primitives**: `similarity_fit`, `lbs` / `lbs_inverse` (singular refusal), `winding_number` / `signed_distance`, `raster_half_open`, `inner_wall_centre` + slice rays, `triangulate` / `triangulate_robust`, the joint-named axis grammar (`resolve_axis`, `pose_cs`, `expand_pose`, `check_expect` on joints), `chain_ends`, `finger_axis`, `curl_delta`. Port from `goldens/reference.py` and Titan's stdlib modules (`armour_validate`, `proc_body`, `views_joints`), keep their tests. | 01, 02, 04, 05, 09, 11, 13, 15 | replaces LT `pipeline/validate.rigid_fit` and `check_expect`, the nearest-normal sign in LT `clearance.py`, `rig._clearance`, `validate_pose`; the inclusive rasters in LT `uv_islands`, `uv.uv_report` | C01, C02, C05, C06, C08, C09 (run `selftest.py` logic inside the Lampway suite, then point it at `canon_geom`) | M |
| 2 | **Validation receipts** | 05 | upgrades `lampway_fit_validate` (LT `validate_pose.py`, `pipeline/validate.py`), `pose_test`, `rig_armor`: joint-measured expectations; joint-named poses (vendor Titan `recipes/armour-poses.json`); source seam ledger (port Titan `seam_ledger.py`); surface crossings + winding-inside both ways; capped crossing control; per-metal-part fidelity; limits file = Titan `armour-limits.json` (status proposed); WIKI8 Euler poses demoted to a stress set | C01 breathe, C03, C05 spike, C07 sign, C14 | M |
| 3 | **Weights** | 07 | upgrades `lampway_weight_transfer` (LT `weights.transfer`), `fit_bind stage=weights`, `scripts/rig/robust_weight_transfer.py`: weld first; native sidecar sampling with region + normal constraints (port Titan `surface_query.py`); restrict with ancestor remap + fallback (port `weight_profile.remap_table`); dress; plate by area centroid; rigid fade; continuous falloff; seam band; bone segments by `chain_ends`; no 4-influence default | C03, C04, G07.3–G07.6 | L |
| 4 | **Bind and return** | 04 | upgrades `fit_bind stage=return` to produce `<piece>_rest` by the exact inverse; refuses singular vertices; bind_check after return. **Titan note (not Lampway):** `equipment_fitpose.bind_return` uses the blend of inverses — hand to the Titan crew as a finding | C02, C03 (return from the twist) | S |
| 5 | **Placement** | 09 | upgrades `lampway_fit_place` (LT `pipeline/fit_place.py`, `sections.py`): inner-wall enclosure for every kind; rigid axis correction applied (not only refused > 25 deg); joint-relative constants; source-part check (detached-glove guard) | C06 | M |
| 6 | **Clearance** | 15 | upgrades `lampway_garment_clearance`: winding sign; open-body refusal; innermost-layer gap; hideable (port the per-view enclosed share from Titan `recipes/fit-measure-blender.py` once its uncommitted edit lands) | C05, G15.4 | M |
| 7 | **Pose solve, all kinds** | 08 | upgrades `lampway_fit_pose` (LT `posing.py`, `scripts/proportion/pose_clearance.py`): DOF tables in the joint grammar; regions from joints (no absolute heights); `pose.json` replayable by `pose_cs`. Kinds beyond the chest wait for the captain's ranges (BUILD_ORDER decision 1) — build the engine and the chest table now | C07, the chest regression (166/207 -> 90/103) | M |
| 8 | **UV measurement unification** | 13 | LT `uv.uv_report` delegates to `uv_islands` (one island definition, one raster rule, one `res`); packer option `xatlas` behind the same interface [measure before default] | C09 | S |
| 9 | **Bake** | 14 | upgrades `lampway_bake_maps`: `auto` cage/ray from measured LP<->HP distances (ray >= cage + depth); 16-bit normals; one GL bake + DX by green flip; explicit hit mask; bake groups; tangent basis in `bake.json`; never overwrite (hash dirs) | C10 | M |
| 10 | **Retopo** | 12 | upgrades `lampway_retopo`: two-sided deviation in LT `common.mesh_report`; `use_preserve_sharp`; per-part remesh with the part map carried; explicit fallback | C13, G12.2, G12.3 | M |
| 11 | **Openings fixes** | 06 | LT `features/opening.py`: site axes from the posed body; the section loop containing the bone point; texture detection from the material | C12 | S |
| 12 | **Joints from views (static)** | 11 | new `lampway_joints_from_views` (ports Titan `views_joints.py` + grt `centre.py`); detector = model slot pending the captain's ruling | C08, G11.4 | M |
| 13 | **`lampway_fit` orchestrator** | 03 | new composite over items 2–11 with the order gates and `fit.json`; extends LT `pipeline/armor_piece.py` past step 15 | G03.1–G03.4 | M |
| 14 | **Soft-part conform** (after the captain's decision 03-H2) | 03 | new; ARAP with clearance handles measured against the cage on cloth/leather only; metal guard | G03.1, G03.4 | L |

**The first five items** (the first slice): `canon_geom`, validation receipts, weights, bind-and-return, placement. They turn every
fit number Lampway prints into one a ruling can stand on, and they are where the measured defects live.

## 2. Test discipline

- Copy the goldens' cases into `tests/lampway_tools/test_canon_*.py`; each test loads the case's `expected.json` and the OBJ, runs
  the Lampway function, compares within the case's tolerance. The OBJ/JSON stay in `docs/canon/goldens` (regenerate with
  `gen_goldens.py`; the test asserts the generator's bytes are unchanged).
- Each falsifier in a case is a second test asserting the OLD behaviour fails (kept as a mutant test after the fix).
- Blender-side tests run headless, niced, in a factory-empty scene; never the captain's live window; Workbench/EEVEE renders only.
- Regression pins measured on the captain's pieces (the chest pose sweep, the Boots1 UV row, the chest placement) run only where
  the shelf is mounted (`LAMPWAY_SHELF_SCRATCH`), and skip with a stated reason elsewhere — never a pass.

## 3. Agent skill entries (so agents use the canon)

1. **`lampway-canon` skill** (Lampway repo, `.agents/skills/lampway-canon/SKILL.md`), loaded before ANY fit, weight, pose, placement,
   proportion, retopology, UV or bake work. Body: the INDEX table; the rule "find the canon page, call its tool, never re-derive";
   one line per tool with its refusal-to-next-command map; the decisions owed (do not decide them).
2. **Trigger rows** in the Lampway agent's tool catalogue: each `lampway_*` tool's description names its canon page
   (`"canon": "docs/canon/07-skin-weights.md"`), and every refusal message ends with that page.
3. **A pre-tool guard** in the Lampway agent: a request to run `run_blender_python` whose script contains bone weights,
   `vertex_groups.new`, `bake(`, `quadriflow_remesh`, `uv.unwrap` or a pose loop is answered with the matching canon tool (a
   reminder, not a block, until the tools in §1 exist).
4. **Shelf and Titan pointers:** one line in shelf `tools/TOOLS.md` and in Titan `tools/AGENTS.md` pointing at the canon for the
   algorithms they implement, so the three code bases cite one specification.
5. **Memory:** the TITAN memory notes stay the source of the rulings; the canon cites them by name. When a ruling changes, the
   canon page's D table gains a row (date, what, ruling) in the same change.

## 3a. Rig tools: the ordered rewrite of MB UE5 Rig Creator Pro and Game Rig Tools (canons 16-22, `rig_tools/`)

The captain, 2026-10-05: rewrite `Downloads/Assets/MBTools/` and `Downloads/Assets/GameRigTools/` as agent-facing Lampway tools.
The orphans lane builds them; STATUS row O36 is items R1-R4 plus the read-back half of R5. Every item is RED-first against the
named golden, and each test also asserts the upstream behaviour named as the falsifier.

| # | Tool (spec) | Canon | Depends on | Ports / re-implements | RED goldens | Size |
|---|---|---|---|---|---|---|
| R1 | `lampway_rig_inspect` ([spec](rig_tools/rig_inspect.md)) | 16-18 | `canon_geom` (item 1) | re-implemented | R01, R02 | S |
| R2 | `lampway_rig_map` ([spec](rig_tools/rig_map.md)) | 16 | R1 | MB family tables PORTED (GPL-3.0-or-later attribution); upgrades `animation.build_mapping` | R01 | M |
| R3 | `lampway_rig_normalize` ([spec](rig_tools/rig_normalize.md)) | 18 | R1 | re-implemented (GRT/MB behaviour = falsifier) | R03, G18.3 | S |
| R4 | `lampway_rig_convert` — O36 ([spec](rig_tools/rig_convert.md)) | 22 | R1, R2 | Titan `animation_canon` / `canon` / `skin_bind` PORTED on the captain's word, with their tests | Titan suite, G22.1-4 | M |
| R5 | `lampway_rig_export_ue` ([spec](rig_tools/rig_export_ue.md)) | 21 | R1 | re-implemented; Titan's measured cm-native recipe; read-back by Titan's `bind_mismatch` rule | G21.1-3 | M |
| R6 | `lampway_rig_conform` ([spec](rig_tools/rig_conform.md)) | 16, 17 | R2, R3 | re-implemented from MB `CreateRig` behaviour | R01, R02 + a conform test | L |
| R7 | `lampway_rig_fit_template` ([spec](rig_tools/rig_fit_template.md)) | 20 | R6, item 12 (joints from views) | Titan `rig-axi` design PORTED on the captain's word; GRT Unreal re-implemented | R06 | L |
| R8 | `lampway_rig_retarget` ([spec](rig_tools/rig_retarget.md)) | 19 | R2 | upgrades `animation_retarget`; MB root motion re-implemented | R04, R05, G22.2 | M |
| R9 | `lampway_rig_game_extract` ([spec](rig_tools/rig_game_extract.md)) | 19 | R1 | GRT `Deform_Rig_Generator` + bendy-bone conversion PORTED with fixes (GPL-2.0-or-later attribution) | G19.4 | M |
| R10 | `lampway_rig_bake` ([spec](rig_tools/rig_bake.md)) | 19 | R9 | GRT Action Bakery semantics PORTED; bake re-implemented | R04 (identity) | M |
| R11 | `lampway_rig_rest_pose` ([spec](rig_tools/rig_rest_pose.md)) | 19, 04 | item 4 (exact inverse) | re-implemented from MB `helperT` / `PoseUE` behaviour | R07 | M |

**First five rig items:** R1 inspect, R2 map, R3 normalize, R4 convert (O36), R5 export read-back. They need no destructive
Blender writes, they close O36's "external rig-conversion and normalization tool", and they gate everything after them.

**Where the rig tools enter the fit plan (§1).** R7 feeds item 7 (pose solve) with an example rigged at its own joints; R5's
read-back is item 13's last gate; R8 + R10 give item 2's validation poses real animation to replay.

**Agent skill entries (§3, extended).** The `lampway-canon` skill gains a rig table: "a rig arrives -> `rig_inspect`; never edit
bone names, rolls or parents by hand -> `rig_map` + `rig_conform`; never apply object scale by hand -> `rig_normalize`; animation
across rigs -> `rig_convert` (canonical) or `rig_retarget` (in Blender); a control rig -> `rig_game_extract` + `rig_bake`; to the
engine -> `rig_export_ue`, and its read-back is the claim". The pre-tool guard (§3.3) adds `edit_bones`, `.roll`,
`armature_apply`, `transform_apply(scale` and `export_scene.fbx` to its reminder list. MB's and GRT's add-ons stay installable
for the captain's own interactive use; agents never drive them.

**Not in this plan:** MB's DAZ/VRoid-specific mesh edits (vertex-group merges, `Genesis9` modifier renames) until a DAZ or VRoid
asset is in the pipeline; MB's Rigify control-rig link/unlink (`MBRigfy.py`), superseded by R9/R10.

## 4. What is NOT in this plan

No model is trained or downloaded; no Studio credit is spent; MetaTailor exports are spent only on the captain's approval
(§5: one spent, 2026-10-06); the Titan repo is not
edited by this plan (findings for its crew are flagged in the plan's rows).

## 5. MetaTailor golden cases (MT-1..MT-4 run 2026-10-06; MT-5 in reserve)

Free tier: 5 FBX exports a month, noncommercial, never shipped. Inputs go in as GLB (its FBX importer ignores axis settings).
Outputs are studied by UV correspondence, because it reorders and welds vertices but the UVs survive. All inputs are
SYNTHETIC (generated, public-safe). The captain approved MT-1..MT-4 ("yeah when we can let's do the other MetaTailor pieces").
They ran on 2026-10-06 in **one** "Export Full Model" FBX. Exports this month: **3 of 5 used, 2 remaining** (MT-5 plus one
spare). The UI shows no counter; the count comes from the app log's `Found N recent exports`. Full record, settings, clicks,
hashes and the analyser: `goldens/metatailor/`.

| # | Input (synthetic, `goldens/metatailor/gen_mt_inputs.py`) | Template / step | Result (measured) | Canon |
|---|---|---|---|---|
| MT-1 | Glove: palm tube, straight 3-phalanx fingers, a separate rigid cap per phalanx (4 mm gap), 21 coloured keypoint markers; fitted as a rotated view copy | Gloves, right, 21 keypoints clicked, Keep Source on | Non-rigid warp: whole residual 18.1 mm RMS. **Caps not rigid**: scale 0.94–1.71, 0.44–5.32 mm RMS. Cap gap 4.0 -> 0.03 mm. 46 vertices inside the hand (min -23.1 mm). 94 bones, up to 29 influences | 03 INV-03.2; 05; 07; 15 |
| MT-2 | Curved shoulder plate 2 cm off the deltoid | Accessory tried: default parent `hand_r`, plate moved off the shoulder, not exported. **Exported as Shirts**, Keep Source on | Geometry unchanged. 10 bones (upperarm_out 0.46, clavicle 0.25). Bends 22 % (p95) at a 60° arm lift | 07 INV-07.6; 09 |
| MT-3 | 16-strip skirt on a belt | Skirts, Keep Source on | Geometry unchanged. Thigh share 0.63 at the strip tops -> 1.0 by z 0.68. Strips stretch 36 % (p95) in a 60° hip flexion (front/back strips 18–22 mm non-rigid); strip gaps stay open | 07 dress; 03 INV-03.2 |
| MT-4 | Greave tube with a closed top lid (apex 41 mm inside the leg) | Pants, Keep Source on | No opening detected. Apex pushed to +6 mm, 14 tube vertices moved, lid kept as a skewed cone. Tube rigid through a 90° knee bend (0.18 mm) | 06; 15 |
| MT-5 | (reserve) | — | — | — |

Not yet run: **"Keep Source Dimensions" off** (MetaTailor's rescale). Every case kept the source scale, so that question is still
open. It is the natural MT-5 if the captain wants it.

## 6. Optional: Alpaca3D as reference behaviour

On public meshes only (the goldens' sphere, the C10 bump pair, a public-domain sculpt), under Proton on the headless display used for
MetaTailor, as a licensed user, recording inputs and outputs and measured quality (UV utilization by `lampway_uv_score`, bake
normals against C10's analytic values). Never inspect, disassemble or decompile the binary. Not done for this canon (see INDEX).
