<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Issue 2 import cleanup audit

This inventory covers live import consumers in `lampway_tools`. Imports route through
`canon_io.import_raw` or `canon_io.load_library`. Successful persistent imports retain
owned datablocks. An exception or explicit failure removes the imported datablocks,
preserving the caller's existing datablocks and selection. Temporary inspection and
readback imports remove their datablocks on success as well as failure.

The measured checks below use disposable native application processes and the current
source overlay. They perform no paid calls and use no owner desktop scene. Each test
checks datablock inventories rather than object counts alone. These receipts establish
the named test cases; they do not establish every supported file format or every failure
point.

| Consumer | Cleanup and checked case | Durable covering test |
|---|---|---|
| Canonical native import boundary | Native PLY import completes, then planted importer exception; new IDs removed | `test_canon_io.py::test_partial_native_import_rolls_back_every_new_id` |
| `normalize_mesh` | File imports, facing refusal, repeat refusal and accepted retry without suffixed names | `test_canon_normalize_mesh.py::test_a_refused_import_leaves_the_scene_exactly_as_it_was_and_a_retry_gets_the_plain_names` |
| `rig_fit._example` | Successful two-mesh GLB import then single-mesh refusal | `test_canon_io.py::test_downstream_import_refusals_remove_only_imported_ids[rig_example]` |
| `rig_fit.fit` | Successful GLB import then missing-reference refusal | Same test `[rig_fit]` |
| `live_load.load_rebuild` | Successful GLB import then invalid declared-turn refusal | Same test `[live_rebuild]` |
| `motion_generate.generate` | Successful GLB import then missing-armature refusal | Same test `[motion]` |
| `animation.retarget` | Successful GLB import without source armature; existing target preserved | Same test `[animation]` |
| UI `compare.ensure_textured` | Successful camera-only GLB import then missing-geometry refusal | Same test `[compare_ui]` |
| `model_compare._import_merged` | Temporary imported mesh, materials and images removed on success and failure | `test_wave2b_model_compare.py::test_temporary_geometry_import_cleans_materials_and_failure` |
| `batch_export._verify` | Temporary readback success and downstream failure remove imported IDs | `test_wave5_batch_export.py::test_readback_cleans_all_ids_on_success_and_failure` |
| `glb_optimize` | Default Cube context; planted failure after import; public DamagedHelmet repeated optimization and pixel-check exception | `test_wave6_glb_optimize.py::test_default_cube_context_and_failed_import_leave_all_ids_unchanged`, `test_public_helmet_optimizer_receipt_on_default_scene` |
| `skeleton_export_check` and `engine_export_check` | Scoped temporary imports; export checks and empty comparison/root refusal | `test_wave3_export_checks.py` (seven original checks), `test_empty_comparison_and_missing_root_cannot_pass` |
| `fit_export` readback | Success and planted partial native exception; every imported ID removed | `test_wave3_fit_body_export.py::test_readback_removes_every_imported_id_and_partial_exception_ids` |
| `rig_tools.readback` | Nested imported IDs and selection restored on success and partial failure | `test_rig_tools.py::test_readback_success_and_partial_failure_restore_nested_ids_and_selection` |
| `rig_export` readback | Full-ID cleanup implemented by the rig lane; native canonical export suite | `test_rig_export_ue.py` |
| `studio_landing.import_file` | Successful GLB import then planted file-stat exception removes new IDs (`test_canon_io.py`, same downstream test `[studio]`); post-normalization collection failure also restores replacement mesh and selection (`test_issue2_import_inventory.py::test_studio_collection_failure_restores_every_imported_id_and_selection`). A normalization refusal intentionally lands a raw asset and returns its diagnostic; this is successful intake | `test_canon_normalize_mesh.py::test_the_studio_landing_normalizes_with_a_declared_turn_and_lands_raw_without_one` |
| `asset_place` | Successful native GLB mesh import then planted placement exception; actual append/link load then downstream placement exception restores IDs and selection | `test_canon_io.py::test_downstream_import_refusals_remove_only_imported_ids[asset_place]`; `test_issue2_import_inventory.py::test_library_placement_failure_restores_every_id_and_selection[append/link]` |

The downstream-refusal run measured **8 passing checks** (six parameterized consumers,
partial native import and temporary model comparison). Removing each consumer's scope
guard measured **6 failing checks**, establishing that those downstream failure tests
reach successful import and detect the leak. The complete scoped geometry run measured
**18 passing checks**. The rig lane's separate combined readback run measured **18
passing checks**. These are separate runs, not a summed whole-suite claim.

`canon_io.load_image` and `load_library` participate in import scopes. Native append and
link loader-exit exception plants create actual object/mesh/material/image dependencies
before raising; `test_partial_library_loader_exception_restores_every_id_and_selection`
checks every ID, including Library IDs, and caller selection. The initial mode matrix
measured **3 failures / 14 passes**: both loader variants leaked a Library ID, and Studio
collection failure leaked a normalization replacement mesh. The narrow fixes add Library
IDs to canonical ownership and record imported-asset normalization replacements in the
Studio scope. The resulting matrix measures **17 passes**.

`test_real_importer_formats_restore_every_id_after_downstream_exception` completes a
native import, verifies new IDs, then raises a downstream exception and checks IDs and
selection. Its twelve parameter cases cover GLB, separate glTF, add-on FBX, native FBX,
OBJ, BVH, USD, USDA, USDC, USDZ, STL and PLY. No native crash occurred in this matrix.

`test_every_subprocess_import_site_is_canonical_and_process_failure_preserves_parent`
checks every import call site in the subprocess inventory below. Each call uses its
canonical adapter and authored importer settings against an isolated authored fixture;
its child completes native import, verifies new objects, then raises a downstream
exception with exit code 1. The parent checks unchanged IDs, selection and input-file
hashes. The same test verifies registered Blender commands are headless subprocess
commands and disable the live bridge. This run measures **1 pass**, covering all listed
sites. It verifies import ownership and failure isolation; it does not claim to exercise
the recipes' unrelated geometry, baking or animation algorithms.

| Subprocess file (relative to `lampway_tools`) | Import path checked |
|---|---|
| `scripts/bake/material_bake.py` | Canonical library load |
| `scripts/bake/bake_maps.py` | Canonical library load |
| `scripts/library/catalog_export.py` | Canonical native import and library load |
| `scripts/texlib/clay_view.py` | Canonical raw import |
| `scripts/texlib/uv_score.py` | Canonical raw import |
| `scripts/proportion/mesh_compare.py` | Canonical raw import |
| `scripts/proportion/pose_clearance.py` | Canonical raw import |
| `scripts/proportion/proportion_fit.py` | Canonical raw import |
| `scripts/proportion/mesh_to_npz.py` | Canonical raw import |
| `scripts/partseg/delete_caps.py` | Canonical raw import |
| `scripts/partseg/mesh_load.py` | Canonical raw import |
| `scripts/partseg/uv_patches.py` | Canonical raw import |
| `scripts/partseg/render_owner.py` | Canonical raw import |
| `scripts/partseg/patch_holes.py` | Canonical raw input import and round-trip readback |
| `scripts/meshqa/mesh_qa.py` | Canonical raw import |
| `rig_convert/recipes/skin-bind-verify-blender.py` | Canonical FBX adapter with authored settings |
| `rig_convert/recipes/anim-compare-blender.py` | Canonical FBX adapter with authored settings |
| `rig_convert/recipes/skin-bind-compare-blender.py` | Canonical FBX adapter with authored settings |

The remaining asset-placement import modes are checked by
`test_each_remaining_placement_import_mode_restores_ids_after_real_load`:
`assign_material`, `assign_maps`, `add_node_group`, `set_world`, `reference_image`,
`add_clip`, `apply_animation` and `attach_rig`. The first seven complete actual
library/image/movieclip loading and plant a downstream failure on the newly loaded
asset before assignment. `attach_rig` completes a native GLB import and naturally
refuses its missing armature. Every case checks caller IDs and selection. Material,
node-group, action, image and movieclip fixtures are authored and isolated; no owner
asset or desktop scene is used.

The final combined inventory run measures **25 passes and one fixture failure**: the
action fixture read a freed EditBone handle after leaving edit mode. Replacing that
access with the authored stable bone name gives **1 pass** for the action case on its
targeted rerun. Thus all **26 distinct inventory cases** have native passing evidence;
this is not a claim of a single 26-pass run. A separate existing importer/refusal
regression run measures **9 passes**. The canonical importer-routing AST check passes.

These call-site checks form the complete subprocess import inventory: a new import call
or a new importing script fails the inventory assertion until its coverage is recorded.
Successful persistent Studio raw intake, asset placement and recipe outputs remain
intentional behavior. Failure cleanup does not erase caller-owned IDs or successful
imports.

An additional downstream-refusal run measured **8 passing parameterized cases**, including
the Studio file-stat and asset-placement failure plants.

Public asset evidence uses Stanford `bun_zipper.ply` and Khronos `DamagedHelmet.glb`.
The Bunny retopo → UV → LOD → weight-transfer test verifies independent output objects,
unchanged approved source geometry, source-hash inheritance, and default
`asset_acceptance` after each stage. Its default weight receipt reports matched fraction
**0.572968**, **951** inpainted vertices and **18** unweighted vertices; acceptance does
not assert skin-weight quality. The public assets do not replace the original Tripo or
MetaHuman acceptance fixtures.

The weight-transfer diagnostic defaults to a matched-fraction warning cutoff of **0.50**.
Its source comment names the native calibration test: a correctly placed coincident
planar grid matches **1.0**, while the unplaced sloped grid matches approximately
**0.03** under the unchanged distance and normal gates. The cutoff remains overridable.
The warning suggests `lampway_fit_place` and never gates export. Boundary checks cover
exactly 0.50, above it, and an unrounded fraction immediately below it.
