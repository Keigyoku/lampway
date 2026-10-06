<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Normalization audit: who normalizes, who assumes, who skips (2026-10-06)

The law under audit: **every tool works on a canonical asset** (canon 01 frames and units; canon 17 rest frames and axes;
canon 18 rig scale and units; canon 22 canonical rig and animation normalization). Each row asks one question: *what does this
code do to an input that is not canonical?*

## Snapshot and placeholders

| token | what it is |
|---|---|
| `<lampway>` | the integration worktree `wt-wave5`, read at `10ea778c` (local `lp/wave5`). It is **47 commits ahead of `origin/lp/wave5` (`00d907d4`)**: it holds the vault-ops, vault-ui and rail merges that origin does not. During the audit it moved to `56ebbd94` (one sandbox hotfix; no audited file changed). |
| `LT` | `<lampway>/src/scripts/mixar/modules/lampway_tools` |
| `SRV` | `<lampway>/server/lampway_server` |
| `MX` | `<lampway>/src/scripts/mixar/modules` (upstream Mixar modules) |
| `orphans@` | branch `lp/orphans` (read through `git show`; first at `aa0ff61a`, then its three new commits up to `1b4ef4c0`) |
| `wave6@` | branch `lp/wave6` at `43f48407` |
| `rail@`, `docs@` | `origin/lp/rail` `756b7636`, `origin/lp/docs` `10672940` (no geometry code; rail's skills read) |
| `canon@` | `lp/canon` = `00d907d4`: no commits beyond `origin/lp/wave5` |
| `<shelf>` | the claude-2 helper crew's tool shelf (`tools/`) |
| `<specs>` | this spec tree; `<memory>` the TITAN crew memory notes |

**Graph reach.** The code graph indexes neither `wt-wave5` nor the lanes (`list_projects`: no project rooted there); the indexed
`lampway-harden` tree is an ancestor 132 commits behind with 269 differing files under `LT` and `SRV`, so it was not used. The
shelf is indexed (`shelf-tools`) but vendored environments swamp it (18,678 function nodes under `partseg/`). **Every file:line
below comes from reading the file.** No row claims a symbol has or lacks callers; "no writer" claims name the files read.

## Classes

- **NORMALIZES (N)**: brings its input into a stated convention itself (or is legitimately convention-free: scale- and
  rotation-invariant by construction).
- **ASSUMES, enforced (A+)**: needs canonical input and refuses some non-canonical input (the aspect refused is named).
- **ASSUMES, unenforced (A-)**: needs canonical input, checks nothing; correct only if every caller already normalized.
- **SKIPS (S)**: produces a wrong or unlabelled result on the inputs it actually receives today, or lands raw data where the
  next tool will treat it as canonical. A bug.
- **NOT WIRED (NW)**, **N/A**, **UNRESOLVED (?)**: stated, never folded into another class.

Aspect letters: F frame/axes, U units/real scale, X object transform, B bone direction/frames, R rest pose/naming, W weld/topology,
V UV convention, C colour space, Nm normal-map convention, M material model, P provenance hash.

## Counts

| scope | rows | N | A+ | A- | S | NW | N/A | ? |
|---|---|---|---|---|---|---|---|---|
| ingress (I) | 29 | 2 | 1 | 2 | 20 | 2 | 0 | 2 |
| tools (T) | 62 | 14 | 3 | 29 | 14 | 0 | 2 | 0 |
| specs (P) | 16 | 6 | 0 | 3 | 7 | 0 | 0 | 0 |
| **total** | **107** | **22** | **4** | **34** | **41** | **2** | **2** | **2** |

Confidence: the I and T rows rest on code read in full or on the function bodies cited; group rows (T53, T56, T60, T61) rest on
module docstrings plus the bodies cited and are the least certain. Specs: 16 of roughly 250 contract files were read for this
audit (the ones that touch ingress, schema, placement, export and scale); the rest are listed under "Not read" at the end.

## The ranked SKIPS (root causes, by blast radius)

Many S rows share one root cause. Ranked by how many downstream tools inherit the error.

| rank | root cause | rows | why it is wide |
|---|---|---|---|
| 1 | **No ingress normalizes into a recorded canonical form, and no tool door checks one.** The Studios panel imports raw files (`LT/studio_landing.py:16-34`, `LT/ui/operators/studio_ops.py:189-204`); Vault placement imports raw files with Blender's default importer settings (`LT/features/asset_place.py:168-187`); a user's File > Import has no door at all. The pieces stay in the importer's frame (Tripo: +X front after import, canon 01 B) at generator scale (~0.98 m longest side, canon 01 B) with seam-split vertices (canon 01 D.1). | I1 I2 I3 I14 I16 | every scene tool downstream |
| 2 | **The Vault has no canonical form, no frame and no scale provenance.** `extract_glb` reads bounds in glTF-local space, node transforms not applied, axes unlabelled (`SRV/library/ingest.py:72-100`, docstring :74); `required_provenance` is empty for every kind (`SRV/library/schema.py:27-28`); `store.put` validates kind, name and source key only (`SRV/library/store.py:269-277`). `mesh_stats.unit_scale` exists (migration 0001 l.19) but **no writer fills it** (read: `ingest.py`, `importers.py`, `cc0.py`, `provenance.py`, `seed_sets.py`), so `asset_place`'s `scale_to_unit` (`asset_place.py:146-150`) never fires. | I8 I9 I11 I12 I13 I15 P6 P7 P8 | every Vault query by size, every placement |
| 3 | **`mesh_to_npz` is the fit chain's single ingress and decides nothing.** Default importer, world coordinates, no turn, no weld, and the npz carries no conventions (`LT/scripts/proportion/mesh_to_npz.py:23-48`). Every consumer re-supplies a `turn`. | I24 | fit_place, place_piece, proportion_ratios, piece_ratios, pose_clearance, transfer_parts, seed_audit |
| 4 | **The turn that brings a piece to -Y front has three defaults and is never stored on the asset.** `api.fit_place` defaults `turn=0.0` (`LT/api.py:1040`) and passes it to `place_piece.build` for the chest, whose own default is -90 (`LT/scripts/proportion/place_piece.py:18,41`) and whose contract says -90 (`<specs>/shelf/fit_place.md` §4). `seed_audit`/`seed_lineup` turn every piece by -90 (`LT/api.py:1026`, `LT/features/seed_lineup.py:20`) although canon 01 B measured per-piece facing inside one Tripo set (greaves and helmet +X, chest -Y). Upstream Mixar's landing turns by one angle per engine (`MX/moodboard/core/generation_enqueue.py`, `model_front_zrot`: Tripo -90, "Assumes Rodin ... faces -Y"). | T11 T42 I17 P11 | placement, proportion ranking, seed audits, Model Gen landings |
| 5 | **Bone direction is read from the imported tail.** `weights.plan` (`LT/features/weights.py:103`), `fit_bind._hist` (`LT/features/fit_bind.py:52`), `rig._proximity_weights` on any armature (`LT/features/rig.py:103`, reached from `bind_to_armature` :180-185, :200-202). Canon 01 C.1: a glTF-imported UE bone's head-to-tail is about 90 degrees off its limb. | T2 T4 T5 T8 | every bind plan's bone choice on an imported MetaHuman or UE rig |
| 6 | **Adjacency without a weld on seam-split meshes** (canon 01 D.1). `segment_mesh` shells/islands (`LT/features/segment.py:20-43`); `retopo` hands QuadriFlow an unwelded mesh and silently falls back to the voxel remesh when it refuses (`LT/features/retopo.py:144-151`); `weight_transfer`'s harmonic fill walks mesh edges (`LT/features/weights.py:335-355`); `pose_test` and `fit_validate` find seams as pairs of different shells (`LT/features/rig.py:215-248`, used by `LT/features/validate_pose.py:74`), so on a Tripo smart mesh every UV island is a "plate". | T3 T7 T12 T32 T33 | parts, retopology, weights, the validation seam metric |
| 7 | **UV texel density measured in local coordinates.** `uv_report` computes `sqrt(UV area / 3D area)` from `me.vertices.co` without the object matrix (`LT/features/uv.py:61-71`), and `uv_unwrap` enforces `texel_density` from it (`LT/features/uv.py:297-309`); only non-uniform scale is refused (:267-269). `uv_texel_density` measures in world space (`LT/features/uv_texel.py:96-104`): two tools give two densities for one object. Both read "per metre" off a piece at generator scale. | T28 | every texel target |
| 8 | **Video-to-animation lands in a mirrored frame.** `anim_multiview_fit` writes joints with X lateral (+ = left), **Y forward**, Z up (`LT/pipeline/anim_mv.py:9`, `triangulate` :48-59; `LT/pipeline/anim_io.py:71-74`). Read against the recorded cameras (`anim_ref.py:12-13`: front image right = world +X, side image right = world +Y) and `triangulate` (`Y = side_origin_u - side_u`, :55), Y_multiview = -Y_world: a REFLECTION of the body frame (left = +X, forward = +Y, up = +Z cannot be a right-handed frame). Positions survive a y-flip; any rotation or bone direction computed in it (`bone_dirs`, :71) is mirrored. Nothing stamps the frame on `fit.json`; `anim_loop_export` reads `quats [frame][bone][w,x,y,z]` with no frame or rest reference (`anim_io.py:137-163`). Canon REPORT contradiction 8 already ruled the body frame. | I22 | the whole video-to-motion path |
| 9 | **Retarget silently drops scale.** `animation_retarget` builds every rest rotation with `matrix_world.to_3x3().normalized()` (`LT/features/animation.py:212-213`), discarding unit and non-uniform object scale that canon 18 INV-18.2 and canon 22 B.5 refuse; the source file is imported with the importer's defaults and its unit is never recorded (`animation.py:93-98`). | I23 | retargeted clips |
| 10 | **Colour-space and normal-map facts are lost at ingress or guessed at use.** Vault image extraction writes no colour space and no normal convention although both columns exist (`SRV/library/ingest.py:113-121`; migration 0001 l.25-26); CC0 texture sets are tagged `colorspace: "sRGB"` as a whole set, normal/roughness/AO included (`SRV/library/cc0.py:260`); `pbr_pack` treats every input normal as OpenGL with no way to declare otherwise (`LT/pipeline/pbr_pack.py:7`, :79-83); `bake_maps` wires a DirectX bake straight into Blender's Normal Map node when it attaches the result (`LT/features/bake.py:108-113`, while the bake itself honours `normal_green`, `LT/scripts/bake/bake_maps.py:49-51`). | I10 T34 T36 | every PBR set and its engine look |
| 11 | **Absolute-metre thresholds run on generator-scale pieces.** A- rows, listed because the pipeline today keeps scene pieces at ~0.98 m until placement, and placement works on npz files only (`LT/pipeline/fit_place.py`): `weight_transfer` 0.05 m (`weights.py:260-265`), `garment_clearance` 0.015 m and 0.5 m (`clearance.py:22-23`), `mesh_defect_scan` 3 mm and 2 mm (`defect_scan.py:20`, :91), mesh QA 0.15 m perimeter and 3 mm float (`LT/meshqa/candidates.py`, `Params`), `fit_openings` millimetres (`opening.py:279`), `pose_test` seam radius 0.02 m (`rig.py:273`). | T7 T13 T15 T44 T47 T3 | every measured threshold |
| 12 | **Studio cross-pass records a re-generated mesh as a version of its parent** with no frame or scale reconciliation, though each studio re-normalizes its output (`orphans@ server/lampway_server/crosspass.py`, docstring). | I4 | lineage-based comparisons |
| 13 | **The spec template never asks for a canonical input.** `CONTRACT_TEMPLATE.md` sections 1-13 have no "input conventions" section; the wiki area's inherited conventions C1-C9 (`<specs>/wiki/INDEX.md`) name envelope, copies, decisions, spend, jail, workers, labels, jobs and renders, but no frame, unit or scale. Every contract written from them inherited the gap. | P1 P2 P5 | every future tool |

## The table

### Ingress (I)

| id | path (file:line) | class | aspects | evidence |
|---|---|---|---|---|
| I1 | Studios panel Import: `LT/ui/operators/studio_ops.py:189-204` -> `LT/studio_landing.py:16-34` | S | F U X W P | default importer by extension, objects moved to collection `Studio`, prefixed by job id; no turn, no transform apply, no scale decision, no weld, no hash or Vault record on the objects |
| I2 | Studio REST drivers (Meshy, Hyper3D, Hi3D, Tripo REST): `SRV/studios/rest/driver.py:70-71`, `SRV/studios/rest/shapes.py` | S | F U W | downloads with sha256 (P kept, correct as a raw store); no landing step normalizes afterwards. Scale levers exist and are unused: Hyper3D `bbox_condition` (`shapes.py:171-175`), Tripo API `auto_size` to real metres and `export_orientation` (`<specs>/studios/tripo.md`) |
| I3 | Tripo Studio browser drivers: `SRV/studios/tripo/tripo_fetch.py` (header), `tripo_mesh.py` | S | F U W | raw variants hashed; `tripo_fetch` captures the viewer's copy: "Triangle ones as tripo_model_<id>_meshopt.glb (EXT_meshopt_compression, quantised: a viewer copy, not the Export file)" (header l.13-14) |
| I4 | Studio cross-pass: `orphans@ server/lampway_server/crosspass.py` (docstring, `CROSS_ACTIONS`) | S | F U | result catalogued as a version with `parent_id`; no frame or scale reconciliation between studios |
| I5 | Higgsfield 3D | NW | | `SRV/higgsfield.py` read in full: `PARAMS_TOOLS = generate_video, generate_image, motion_control` (l.22); no `generate_3d` path. `<specs>/studios/STUDIO_MAP.md` correction 2 agrees |
| I6 | fal gateway: `SRV/fal.py` | ? | | head read only (queue provider, receipts); whether any route returns a mesh, and how it lands, was not read |
| I7 | MetaTailor | NW | | no Lampway code; studied as a black box (`<memory>` metatailor-study; canon IMPLEMENTATION_PLAN §5). Its export reorders and welds vertices and its FBX importer ignores axis settings: any future landing needs a UV-correspondence normalizer |
| I8 | Vault ingest scan/import/watch: `SRV/library/ingest.py:30-58` (classify), :72-100 (`extract_glb`), :113-121 (`extract_image`), :275-296 (`_spec`), :364-372 (`ingest_file`) | S | F U X C Nm | glTF stats in local space, axes unlabelled; FBX/blend/OBJ marked "pending: tier-2" and never extracted (:289-290); no colour space or normal convention |
| I9 | Vault shelf-seeds importer: `SRV/library/importers.py:48-139` | S | F U | FBX seeds stored with `"extract": "pending: tier-2"` (:82); sha256 cross-check kept (P) |
| I10 | Vault CC0 importer: `SRV/library/cc0.py:251-270` | S | C | `texture_set` stats `colorspace: "sRGB"` for the whole set (:260); per-map normal convention from the source's naming (:265, N) and `dimensions_m` (:150, :167, N) are correct |
| I11 | Vault seed sets (initial folder import): `SRV/library/seed_sets.py:89-120` | S | F U X C | puts every file through `Ingest._spec` (I8) |
| I12 | Vault provenance capture: `SRV/library/provenance.py:52-123` | S | (twin) | generation outputs go to CAS with hashes (P; raw keeping is correct); no canonical twin exists to link them to |
| I13 | Vault store and schema: `SRV/library/store.py:269-360`, `SRV/library/schema.py:11-28`, `SRV/library/migrations/0001_init.sql` | S | F U P | no canonical table, no frame or scale-provenance fields; `required_provenance=[]`; stats filtered to columns, never validated |
| I14 | Vault to scene: `LT/features/asset_place.py:141-187` | S | F U X W | importer defaults; footprint dropped on the drop point (:151-156); `scale_to_unit` reads a field no writer fills (:146-150); stamps `lw_asset_*` (P) |
| I15 | Vault to Blender asset library: `LT/scripts/library/catalog_export.py` (header, `IMPORT` table) | S | F U X | imports each record's file into a factory scene and marks it; publishes the raw import |
| I16 | Blender File > Import (the user) | S | all | no Lampway door: an imported object carries nothing that says raw, and no tool asks |
| I17 | Mixar job-queue Model Gen landing: `MX/common/job_queue/core/model_io.py` `rename_generated_model`, `_set_origin_bottom_and_center`; `MX/moodboard/core/generation_enqueue.py` `model_front_zrot` | S | F U | the only landing that normalizes (front to -Y, transforms applied, origin to bbox bottom-centre), with a per-ENGINE turn that canon 01 B contradicts per PIECE and an unverified Rodin assumption; no scale decision, nothing recorded |
| I18 | Mixar generations library: `MX/asset_search/core/generation_library.py` (docstring) | S | F U | archives every succeeded generation as it landed |
| I19 | `splat_import`: `LT/features/splat.py:96-127` | S | F U | PLY positions copied verbatim; a splat's frame and scale are whatever its trainer used |
| I20 | `image_to_3d` (algorithmic): `LT/features/image3d.py:130-207` | N | F U | builds in the body frame ("Front u=+X ... Z up", l.11) at the caller's `size` (default 1.0); the size is declared, not recorded on the object |
| I21 | Video ingest and analysis: `SRV/videoingest.py`, `SRV/library/video.py` | N | time | true motion fps, holds and blends measured (`video.py` docstring); not geometry |
| I22 | `anim_multiview_fit`: `LT/pipeline/anim_mv.py:9`, :48-59; `LT/pipeline/anim_io.py:41-78` | S | F | +Y forward output frame (rank 8); scale from px_per_m is measured (N for U) |
| I23 | `animation_retarget` source import: `LT/features/animation.py:85-112`, :198-223 | S | U | N for rest (`W = Ws Rs^-1 Rt`, :232-234), naming (`pipeline/anim_labels.py`), root ratio (recorded, :216-221); S for scale (rank 9) |
| I24 | `mesh_to_npz`: `LT/scripts/proportion/mesh_to_npz.py:23-48` | S | F U W P | rank 3 |
| I25 | Batch scripts that import a file: `clay_view.py:25-28`, `scripts/texlib/uv_score.py:20-28`, `render_owner.py:24-30`, `delete_caps.py:32-37`, `patch_holes.py:47-56`, `uv_patches.py:31`, `scripts/meshqa/mesh_qa.py` (header) | A- | F U | each imports with defaults; each takes `--turn` with its own default (clay_view, patch_holes -90; render_owner 0.0); `delete_caps` declares its frame "Blender import (X front, Y wearer's left, Z up), metres" (l.11) and thresholds in it |
| I26 | Rebuild landing: `LT/live_load.py:26-67` | A- | F U | transforms applied (:46), turn applied (default -90, :47) and not recorded on the object (`api.py:341`: "the loaded object has the rebuild's turn baked in"); masks loaded Non-Color (:55, N for C) |
| I27 | Agent scene reads: `MX/scene_graph/core/tools.py:34-87`, `traversal.py` | S | all | hierarchy only; the agent cannot see whether an object is canonical, and its raw script path (`execute_script`) bypasses every tool |
| I28 | External motion (Kimodo, HY-Motion, Cascadeur) into `motion_experiment`: `wave6@ LT/features/motion_experiment.py` (docstring, `_err` l.109-117) | A+ | R | an imported B/C clip whose first or last pose misses the brief's by more than 0.5 deg is refused; rest and frame are not normalized |
| I29 | Mixar feature landings (retopology, segment, UV, animate): `MX/hunyuan/core/*_enqueue.py`, `model_io.import_file` | ? | | the enqueue side and the generic importer were read; the per-feature `on_imported` hooks (`_retopology_on_imported`, ...) were not |

### Tools (T)

| id | tool (file:line) | class | aspects | evidence |
|---|---|---|---|---|
| T1 | `auto_rig`: `LT/features/rig.py:35-49`, :131-157 | A- | F | facing `-Y` or anything else = `+Y` (:48); +Z up assumed; height fractions are scale-free |
| T2 | `bind_to_armature`: `rig.py:160-203` | S | B W | proximity fallback uses `head_local`/`tail_local` of any armature (:103); `transfer` mode with no weld (:186-198) |
| T3 | `pose_test`: `rig.py:215-316` | S | W U | seam pairs from vertex-index shells (:215-248); 0.02 m radius; Euler on bone-local axes |
| T4 | `rig_armor`: `LT/features/workflows.py:251-283` | S | B W | composes T2 and T3 |
| T5 | `weight_audit` / `plan`: `LT/features/weights.py:46-49`, :95-114 | S | B F U | imported tail (:103); side from world x beyond 0.05 m (:46-49) assumes body frame and metres |
| T6 | `weight_cleanup`: `weights.py:141-157`, :175-238 | A- | X | region bbox in LOCAL coordinates (:145-148) while every other weight tool works in world space |
| T7 | `weight_transfer`: `weights.py:260-372` | S | W U | no weld before the harmonic fill; `max_distance` in absolute metres |
| T8 | `fit_bind`: `LT/features/fit_bind.py:49-55`, :95-107, :138-185 | S | B W | imported tail (:52); weights via T7; seams by position within 1e-5 (:107, N for seam detection) |
| T9 | `fit_export`: `LT/features/fit_export.py:67-127` | A+ | B R P | verifies the body package hash (:74), bone names against it (:87-90), reads every joint's position AND axes back (:36-59) |
| T10 | `fit_body`: `LT/features/fit_body.py:23`, :53-98 | A- | F U R | writes `units: m, frame: blender` (:66) as a declaration, not a measurement; no roster check (canon 01 C.6) |
| T11 | `fit_place`: `LT/pipeline/fit_place.py:37-42`, :171-207; `LT/api.py:1040-1056` | S | F | N for scale (one uniform similarity from body landmarks, meta recorded, :202-206); S for the default turn (rank 4); body thresholds absolute (`|x|<0.27`, :71) |
| T12 | `fit_validate measure`: `LT/features/validate_pose.py:53-131` | S | W U | seam pairs from T3 (:74); scale-fixed rigid residual and rest fidelity are correct (`pipeline/validate.py:21-33`) |
| T13 | `garment_clearance`: `LT/features/clearance.py:22-23`, :49-107 | A- | U F | metres; 0.5 m "run place_piece first" guard (:59-61) is the only check |
| T14 | `fit_pose` / `pose_clearance`: `LT/posing.py`; `LT/scripts/proportion/pose_clearance.py:63-79`, :125 | A- | U F | absolute heights (`1.15 < z < 1.52`, `1.50 < z < 1.62`); the SIGN CHECK refuses a wrong arm axis (:69-71, A+ for that one fact) |
| T15 | `fit_openings`: `LT/features/opening.py:77-96`, :266-281 | A- | U | millimetres and cm on world coordinates |
| T16 | `fit_glove labels`: `LT/pipeline/fit_glove.py` via `api.py:1334-1347` | N/A | | reads vertex-group names only |
| T17 | `clip_classify`: `LT/features/clip_classify.py:69-106` | N | F U | lengths in figure heights; an explicit Y-up adapter (`_y_up`, :69-70) |
| T18 | `anim_reference_render`: `LT/features/anim_render.py:47-53`, :116-173 | A- | F | assumes the character faces -Y; the rest pose is enforced (:47-53, A+ for R) |
| T19 | `anim_check`, `anim_loop_export`: `LT/pipeline/anim_io.py:108-163` | A- | F R | take frame unspecified; skeleton by name only |
| T20 | `skeleton_export_check`: `LT/features/export_checks.py:52-113` | A- | B R | reads the unit ratio (N for U, :96, :107); the bone table holds parent and length only (:57); `up` is the axis of largest extent (:61) |
| T21 | `engine_import_check`: `export_checks.py:127-172` | N/A | | static package read |
| T22 | `export_piece`: `LT/api.py:582-631` | A- | F U | Blender FBX defaults (no axis, unit or apply settings pinned) |
| T23 | `batch_export`: `LT/features/batch_export.py:102-113`, :284-291 | N | X F U | transforms applied with winding reversed on det<0; project convention recorded and enforced; the re-import check compares SORTED dimensions (:213-216), blind to an axis swap |
| T24 | `scene_cleanup`: `LT/features/scene_cleanup.py:48-55`, :143-160 | N | X W | opt-in; merge distance relative to the bounding diagonal |
| T25 | `mesh_prep`: `LT/features/workflows.py:143-174` | N | W P | weld at an absolute 1e-5 (scale-dependent); three hashes recorded |
| T26 | `asset_acceptance`: `workflows.py:199-248` | A+ | X | refuses an unapplied object scale (:221-224); its "orientation" gate checks bounds against a reference, not axes |
| T27 | `asset_lineage`: `LT/features/lineage.py:27-46`, :94-105 | A- | X | anchors in OBJECT space: applying a transform (the first normalization step) breaks `verify` |
| T28 | `uv_unwrap` / `uv_report`: `LT/features/uv.py:57-121`, :253-321 | S | U X | rank 7 |
| T29 | `uv_score` / `uv_islands`: `LT/features/uv_islands.py:27-121` | N | V | stretch normalized by its median (scale-free); `seam_m` in mesh units |
| T30 | `uv_texel_density`: `LT/features/uv_texel.py:96-192` | A- | U | px per metre in world units, on a piece whose metre is not real until placement |
| T31 | `uv_rectify`, `uv_layout`: `LT/api.py:816-834` | A- | U F | `match_tolerance` in metres; mirror plane at the mesh centre |
| T32 | `segment_mesh`: `LT/features/segment.py:20-138` | S | W | rank 6 |
| T33 | `retopo`: `LT/features/retopo.py:108-156` | S | W | rank 6; the AutoRemesher path tells the user to run `mesh_prep` only after a failure (:86) |
| T34 | `bake_maps`: `LT/features/bake.py:32-116` | S | Nm | refuses non-uniform scale and misalignment (:48-61, A+ for X); attaches a DX bake without a flip (:112-113) |
| T35 | `material_bake_export`: `LT/features/material_bake_export.py:24-87` | N | C Nm | colour spaces and the normal convention written into the README with sha256 |
| T36 | `pbr_pack`: `LT/pipeline/pbr_pack.py:37-89` | S | Nm C | input normal assumed GL; `merge.json` colour spaces list BaseColor, ORM and normals only (:84) |
| T37 | `pbr_pack audit`: `LT/features/pbr_audit.py:35-64` | N | C | checks each channel's image colour space |
| T38 | `palette_fit`: `LT/pipeline/palette_fit.py:29-36` | N | C | explicit `space` srgb or linear |
| T39 | `project_views`, `texture_gen`, `repair_texture`, `ai_render`: `LT/features/texture.py:108-115`, :181-244 | A- | F | views fixed by `render.TO_CAMERA` (Front = camera at -Y, `render.py:16`); a piece still facing +X gets its front plate painted on its side |
| T40 | clay render, `silhouette_compare`: `LT/features/render.py:16-65`; `LT/features/silhouette.py:106-153` | A- | F | silhouette refuses unapplied scale (:118-120, A+ for X); frame assumed |
| T41 | `model_compare`: `LT/features/model_compare.py:73-111` | N | U | every model scaled to a 2-unit box (scale-free by design); yaw is the caller's `rotation_deg` |
| T42 | `seed_audit` / `seed_lineup`: `LT/api.py:1026`; `LT/features/seed_lineup.py:20-36` | S | F | one -90 turn for every seed of every piece (rank 4) |
| T43 | `parts_critique`, `render_owner`: `LT/api.py:1072-1085`; `scripts/partseg/render_owner.py:22` | A- | F | the api passes `--turn -90` explicitly; the script's own default is 0.0 |
| T44 | Mesh QA (`qa_*`, `meshqa/candidates.py`, `meshqa/live.py`) | N | F W | an explicit analysis frame (`turn`, `offset` kept in `QAConfig`, `live.py` l.47-62) and a weld by distance before loops (`candidates.py` docstring); thresholds tuned at generator scale |
| T45 | Rebuild loop: `LT/rebuild.py:38-58`; the partseg scripts | A- | F | `turn=-90` default; owner maps keyed by polygon index across tools |
| T46 | `meshpaint`: `LT/api.py:487-504`, `LT/meshpaint.py` | A- | F | `turn` default -90 |
| T47 | `mesh_defect_scan`: `LT/features/defect_scan.py:20-23`, :91-190 | A- | U W | absolute 3 mm and 2 mm; shells by vertex index |
| T48 | `detail_normals`: `LT/detail_normals.py:61-74` | A- | U | object-space box projection at a fixed scale assumes real size (NormalGL is correct for Blender, N for Nm) |
| T49 | `procedural_library`, `layered_material`: `LT/api.py:896-915` | A- | U | object-space procedural materials: tiling depends on the piece's real size |
| T50 | `asset_place` shading kinds: `LT/features/asset_place_shading.py:13`, :80-92, :107-146 | N | C Nm | colour space by role; DX green flipped |
| T51 | `side_label_check`, `mirror_pair`: `orphans@ LT/features/handedness.py:148-200`, :255-319 | A+ | X F | refuses an unapplied rotation or scale (:160-161, :185-186); facing is a parameter |
| T52 | `scale_to_measure`: `orphans@ LT/features/scale_measure.py:85-133` | N | U | one uniform factor from a measured or reference length, recorded with a rollback (`lw_prev_scale`) |
| T53 | orphans group: `region_extract`, `zones`, `local_edit`, `join_boolean`, `multi_piece`, `material_id`, `condition_passes`, `rig_plans`, `image3d_views`, `island_labels`, `parts_slots`, `uv_check` (docstrings) | A- | F U | -Y front, metres and applied transforms assumed; `join_boolean` clearance in mm |
| T54 | `lod_chain`: `wave6@ LT/features/lod_chain.py` (docstring) | N | U | deviation relative to the bounding diagonal, silhouette IoU |
| T55 | `modular_character`: `wave6@ LT/api_wave6.py:22-30` | A- | F U | validates equal scales and each part's side against -Y facing (partial check) |
| T56 | wave6 group: `secondary_chain`, `motion_experiment`, `playblast`, `character_pipeline` | A- | F B | bone-local Euler poses; chain along the region's principal axis |
| T57 | Vault `similar` / `embed`: `SRV/library/similar.py:1-26` | N | U F | shape descriptor "scale removed on purpose" |
| T58 | Vault previews: `SRV/library/render_worker.py:29-50`, `camera_for` | A- | F | "glTF +Y up / +Z front is Blender +Z up / -Y front": the glTF spec's front; a Tripo GLB faces +X |
| T59 | `glb_stats` (model_compare stats): `LT/pipeline/glb_stats.py:125-128` | A- | U | reports `bbox_m` with `"unit_scale_note": "glTF is metres"`: true of the unit, false of the size (~0.98 m generator normalization) |
| T60 | shelf tools not ported (`partseg` build_r6, export_parts, orient_faces, repair_holes, repair_uvs, verify_set; `texlib` relief, seamless, fidelity; `studios/tripo` uv, texture, regen) | A- | F | weld by position 1e-5 m before adjacency (N for W); the import frame is declared in each header; `export_parts` records a "scale stage" per part |
| T61 | 2D image tools: `plates`, `segment_image`, `view_verify`, `imgops`, `seamless_tile`, `upscale`, `relief_tiles` | A- | C | 8-bit sRGB assumed, never declared |
| T62 | `anim_abs` (O26 analysis-by-synthesis): `orphans@1b4ef4c0 LT/features/anim_abs.py` (docstring, `AXES = (0, 2)`) | A- | B | "Twist about a bone's own axis (local Y)": assumes the Blender-native bone convention; canon 17 A names a second (UE axes, X along) that it would search wrongly |

### Specs (P)

| id | spec | class | evidence |
|---|---|---|---|
| P1 | `<specs>/CONTRACT_TEMPLATE.md` | S | 13 required sections; none asks for the input's frame, units, scale state or colour space |
| P2 | `<specs>/wiki/INDEX.md` conventions C1-C9 | S | inherited by 76 contracts; no geometry convention |
| P3 | `canon/01-conventions.md` | N | defines the frames (B), bones (C), identities (D) and a `conventions` receipt block (F) for canon tools only; nothing enforces it at a door |
| P4 | `canon/16`-`22`, `canon/rig_tools/` | N | rig and animation normalization specified (inspect, map, normalize, convert); none built; contradiction 18 (working frame vs canon 22's interchange frame) awaits the captain |
| P5 | `canon/IMPLEMENTATION_PLAN.md` | S | no schema, no door, no ingress item; item 1 (`canon_geom`) is primitives only |
| P6 | `asset_library/asset_schema.md` | S | `mesh_stats.unit_scale` with no definition of what it means or who writes it; no frame, no scale provenance, no raw/canonical link (relation `derived_from` exists, a `normalized_from` does not) |
| P7 | `asset_library/asset_ingest.md` | S | tier-2 extraction "runs the existing lampway_tools mesh report" in whatever frame the importer gives; no normalize stage |
| P8 | `asset_library/asset_place.md` | A- | §6: "apply `scale_to_unit` using `mesh_stats.unit_scale`" and "the convention read from `image_stats.normal_convention`": fields no writer fills (I8, I13) |
| P9 | `studios/STUDIO_MAP.md`, `studios/tripo.md` | S | document Tripo API `auto_size` (real metres) and `export_orientation`, Hyper3D `bbox_condition`, Meshy Resize; specify no landing step |
| P10 | `generation/studio_tripo.md`, `generation/studio_cross_pass.md` | S | §5: Import "puts a file in the `Studio` collection"; cross-pass lineage without frame/scale |
| P11 | `shelf/fit_place.md` | A- | §4 `"turn": -90.0` default; the built api diverges to 0.0 (rank 4) |
| P12 | `shelf/fit_body_package.md` | N | joints "metres in the Blender frame and cm in the UE frame, both stated"; hashed package |
| P13 | `wiki/mesh_prep.md` | A- | §6.4 proposes a relative weld and marks Tripo's scale `[UNVERIFIED]`; canon 01 B has since measured it (~0.98 m) |
| P14 | `wiki/scale_to_measure.md` | N | the right primitive; optional, never on the ingress path |
| P15 | `wiki/asset_acceptance.md` | N | asks for front axis, side, scale and pivot in the orientation gate |
| P16 | `ue_parity/DIFFERENCES.md` GEO, NRM, TEX rows | N | egress facts measured; **GEO-17's evidence is false at this snapshot**: "Refused today by `fit_export`/`asset_acceptance`" (l.160), but `fit_export.run` has no transform or scale check (T9, read in full); only `asset_acceptance` refuses (T26) |

## What the brief's framing missed

1. **"Tools that skip" understates it: the ingress skips.** Only one landing normalizes at all (I17, upstream Mixar), and it
   applies a per-engine turn that the canon's own measurements contradict. The Lampway-built landings (I1, I14, I24, I26) do
   less than the upstream one.
2. **Scale is not a single fact.** A Tripo piece has a *unit* (metres, true by the glTF spec) and a *size* (normalized to about
   0.98 m, false). Two tools conflate them (T59, P8). The schema below separates `units` (always m) from `scale.state`
   (`real | generator_normalised | unknown`), so a tool can say which it needs: proportion scoring and model compare are
   scale-free and correct on generator scale; weights, clearance, openings and texel density are not.
3. **There are four working frames today**, not one: the Blender import frame (partseg, mesh QA, rebuild, `delete_caps`), the
   body frame (fit, proportion, render, anim reference), the multiview frame (+Y forward), and canon 22's interchange frame
   (cm, left-handed, +X forward). Every transition is a `turn` argument with its own default, stored nowhere.
4. **The tool registry is already a single door.** Every agent-callable tool, including the orphan and Wave 6 lanes, registers
   through `api.tool` into `_REGISTRY` -> `TOOL_FUNCS` (`LT/api.py:51-67`, :1553-1575; `orphans@ orphans_api.py` "They register
   through `api.tool`"; `wave6@ api_wave6.py` "api.py wraps every name in TOOLS"). That is where the schema door belongs, and
   it makes the enforcement closed by construction (DOOR.md).

## Not read (and therefore not classified)

- Specs: `generation/` (21 of 25 files), `mixar_docs/` (36), `resources/` (11), `mrmak/` (17), `wiki/` (72 of 77), `cloud/`,
  `connections/`, `canon/rig_tools/` bodies, `asset_library/` (15 of 21), `ue_parity/contracts/` (5).
- Code: `SRV/fal.py` beyond its head; `MX/hunyuan/core/*` `on_imported` hooks; `LT/pipeline/plates.py`, `segment_image.py`,
  `view_verify*.py`, `parts_critique.py`, `armor_piece.py`, `clip_features.py`, `interior_diff.py`, `imgops.py`, `anim_gates.py`,
  `anim_plan.py` beyond their api docstrings; `LT/features/uv_layout.py`, `uv_rectify.py`, `camera_shot.py`, `procedural_*`,
  `layered_material.py`, `asset_catalog.py` bodies; the orphan and Wave 6 feature bodies except `scale_measure.py`,
  `handedness.py`, `motion_experiment.py` (to l.120), `anim_abs.py` (to l.40); `docs@` pages.
