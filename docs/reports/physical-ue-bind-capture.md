<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Physical UE bind diagnosis and minimal capture

The supplied actual 8fde receipt identifies candidate SHA256 `379ec5d80206dc2d9d2c7e6e9215b64d13aa6acbeb2a26365d294fffe8601d75`, engine `5.8.2-56702186+++UE5+Release-5.8`, 343 imported bones, and extra parent `qa_metahuman_ue` above the original native `root`. All 342 original component/world rows fail unchanged bars: position 0.01 cm, shortest quaternion rotation 0.01 degree and absolute scale-component difference 0.0001. Maxima are 26.4093923524 cm, 179.999999210 degrees and 99.00127554 scale difference. Assets were not saved and sources were unchanged.

The archive supplies aggregates and root/pelvis/spine_01 errors, not their signed transforms. Its raw FBX diagnostic is synthetic, not from the candidate hash. It does not record the executed importer classes/properties, reference-pose accessor or component-transform composition. These are specific missing inputs, not a reason to upload the original mesh.

The pinned Blender writer puts `unit_scale * global_scale` into `global_matrix` for `FBX_SCALE_NONE` and then writes UnitScaleFactor 1 (`upstream/scripts/addons_core/io_scene_fbx/export_fbx_bin.py`). The matching recipe enables unit conversion. A genuine synthetic export therefore retains a scale-100 Null ancestor even though the direct LimbNode scale check and UnitScaleFactor pass. Existing readback also omits one extra root by hierarchy shape and compares the conformed armature against itself when no independent reference is supplied. Those checks cannot establish the original native binds.

Scale difference near 99 does not prove that world positions are uniformly 100 times too large; a hierarchy can retain scale while child translations compensate. Root rotation near 179 degrees while pelvis/spine differ little also cannot justify a single corrective rotation. Diagnose container/unit retention, translator axes, changed per-bone rest frames and comparator-space semantics separately. No `.01` import scale, scene-unit change, corrective rotation, armature rename or native-reference-pose update is selected.

## Sole-validator capture

Keep original geometry, vertex/index arrays, skin weights and FBX bytes local. Instrument the already working physical comparison code; do not invent a coordinate API. Record unavailable properties explicitly. Use fresh transient imports with no saves or changes to the native reference asset.

1. Parse the actual matching FBX locally:

   ```bash
   python scripts/lampway/diagnose_fbx_bind.py --fbx "$CANDIDATE_FBX" --out "$NEW_PRIVATE_FBX_REPORT"
   ```

   Verify its source SHA before/after equals the candidate above. Retain this raw transform-only report locally. Return only its source hash, GlobalSettings axis/unit flags and the Null ancestors/root model transform properties initially. Do not send source FBX bytes or geometry.
2. Extend the existing reference comparator to capture the exact native 342 and candidate 343 rest rows locally. Preserve all parents and the extra container. For each bone record the original signed values before comparison, both parent-local rest and the exact component rest transform used by the comparator. Do not replace an accessor with guessed matrix multiplication. Save the capture to a new private JSON with permissions 0600.
3. Record engine/importer/comparator metadata separately: actual legacy FBX versus Interchange route; factory/translator/pipeline class and stack identities; executed typed properties and saved import-data properties. Required semantics are offsets, scene/front/unit conversion when exposed, selected skeleton or new transient skeleton, Use T0 as Reference Pose, Update Skeleton Reference Pose, animation/reference source, meshes-in-bone-hierarchy and supported root/transform-baking options. Each property records `{owner_class, property_name, type, status, value}`; unavailable is not false. Retain the existing native-reference fingerprint before/after. Interchange options depend on the actual stack; [Epic's reference](https://dev.epicgames.com/documentation/en-us/unreal-engine/interchange-import-reference-in-unreal-engine) documents offsets, skeleton selection and reference-pose controls. [Legacy options](https://dev.epicgames.com/documentation/en-us/unreal-engine/fbx-import-options-reference-in-unreal-engine) must not be presumed to control Interchange.
4. First compare the original native reference with itself through the same capture path, explicitly marked as a control. Require 342 rows with zero positional/scale differences and quaternion-sign equivalence. If an untouched original native FBX is already available, import it through the same settings into a new transient skeleton and retain its comparison as a pipeline control. Then compare the candidate. Never update the original skeleton reference pose to make the comparison pass.

## Exact local comparison input

`scripts/lampway/compare_ue_bind_capture.py` accepts the local JSON below. The arrays contain all 342/343 bone rows; the illustrated single row is only a shape example. The helper does not execute UE, derive component transforms, reconstruct geometry or select a corrective transform.

```json
{
  "schema": "lampway.ue-bind-capture/1",
  "provenance": {
    "candidate_fbx_sha256": "<64 lower-case hex>",
    "native_reference_sha256": "<independent original native-reference content hash>",
    "engine": "<actual engine/build>",
    "capture_code_sha256": "<64 lower-case hex>",
    "comparator_description": "<verified accessor names, raw rest source, composition implementation/order>"
  },
  "conventions": {
    "translation_unit": "cm",
    "quaternion_order": "xyzw",
    "spaces": {"local": "parent_local", "component": "component"}
  },
  "tables": {
    "native": [{
      "name": "root", "parent": null,
      "local": {"translation_cm": [0,0,0], "quaternion_xyzw": [0,0,0,1], "scale_xyz": [1,1,1]},
      "component": {"translation_cm": [0,0,0], "quaternion_xyzw": [0,0,0,1], "scale_xyz": [1,1,1]}
    }],
    "candidate": []
  }
}
```

Use actual values, never these illustrative identity numbers. Set `native_self_control: true` only for the explicitly identified original-native self comparison. Candidate/reference identities must otherwise be independent.

```bash
python scripts/lampway/compare_ue_bind_capture.py --capture "$PRIVATE_SIGNED_REST_CAPTURE" --out "$NEW_PRIVATE_DERIVED_REPORT"
```

The returned report contains only per-bone signed translation/rotation/scale differences and scale ratios, topology changes, counts and input/provenance hashes. It omits the original absolute rest transforms and geometry. Keep the original signed row tables local; return the derived report plus the limited raw container/axis/unit metadata and executed import settings. stdout contains only counts/hashes. Comparison bars remain unchanged; a numeric comparison on supplied data is not a physical API or complete leader-bind acceptance claim.

Root scale retained only in component rows with native-sized local scales identifies ancestor inheritance. Differing left-relative quaternion deltas rule out one common component-space left rotation; they do not by themselves rule out a right bone-axis correction or an orthogonal basis conjugation. A failing original control instead identifies capture/pipeline semantics. These measurements determine the next source patch; no exporter/importer correction is declared yet.


## Actual follow-up and unit-carrier correction (2026-10-07)

The bounded follow-up archive SHA256 is `302cdc5e3758b07480459220ac9fd145ad120a95e69a5403f1c8abedbf01f753`. Actual legacy FbxFactory import used offsets zero, uniform scale1, convert_scene=true, convert_scene_unit=false, force_front_x_axis=false, a new candidate skeleton, no animation, T0 reference=false and skeleton-reference update=false. The independently preserved native reference fingerprint was unchanged. Native-self342 rows pass; candidate343 rows retain the extra container, with336 local and342 component rows over unchanged bars. All local scale deltas pass (maximum1.26362e-5), while component scale ratios are approximately100. The matching source Null authors scale100 and UnitScaleFactor1. This independently identifies inherited scale; it does not establish a GPU/render or mesh-versus-Skeleton pose calibration. NullRHI RenderData and pose-parent reflection were unavailable; no divergence is inferred.

The correction changes representation on independent export copies: metre coordinates become centimetre coordinates, including copied location keys/handles and shape coordinates. The effective exporter global_scale is the inverse of the pinned writer's `units_blender_to_fbx_factor(scene)`; scene units, originals, source actions and preferences stay unchanged. This produces raw identity Null scale and UnitScaleFactor1 without an arbitrary engine import multiplier. Unsupported dependency graphs and exporter RNA scale limits refuse before copies. The default convention recipes opt into this representation; their R08 bone-axis pairs stay unchanged. Explicit legacy/custom recipes retain their stated representation, but raw nonunit Null ancestors cannot publish.

Readback does not apply object scale to the imported rig. The pinned importer adds `UnitScaleFactor / units_blender_to_fbx_factor(scene)` as its global unit carrier (`import_fbx.py`). Only after independently admitting raw identity Null scales, UnitScaleFactor1 and direct unit bone scales, readback converts position units to metres and excludes that known uniform importer carrier from the scale comparison. Raw geometry, rest matrices, mesh parents and skin weights remain untouched; position/rotation/scale bars remain0.01cm/0.01degree/1e-4. A preliminary object-scale application exceeded the existing1e-6m joint-drift guard on oblique frames and was rejected, not promoted or accommodated with a looser limit.

The existing local QA export tool can generate a new candidate with `recipe=auto` from the same normalized private-copy armature, mesh list and independently supplied reference when available. Use a new output filename. Parse that candidate locally to verify Null1/UnitScaleFactor1, then import into a fresh transient candidate through the exact recorded legacy settings. Keep the original reference untouched. This candidate addresses unit inheritance only; native frame/hierarchy parity remains measured, not assumed from a Blender self-reference pass.

Re-run the supplied-data comparison helper on both existing private captures using fresh output names; no UE recollection is needed for this diagnostic extension. Each row now includes `quaternion_right_delta_xyzw = inverse(ref) * got`, `rotation_angle_identity_delta_deg = angle(got)-angle(ref)` and `translation_norm_delta_cm = norm(got)-norm(ref)`. Existing left-relative deltas and acceptance metrics remain unchanged. Compare sign-equivalent right-delta dispersion to distinguish a common right correction; basis conjugation preserves rotation angle, and an orthogonal coordinate rotation preserves translation norm. A remaining ambiguity needs local accessor/mesh-pose calibration; no common rotation is selected or applied. Return derived reports only.

## Actual corrected-unit candidate remains refused

The follow-up archive SHA256 is `b928ccff136ed47f979a4898fb745bf468ff9635a9c0f053d069e43cf685654a`. It tests the exact exporter Python from `1368c88253a1ed524bfa067ef0bb2660494b1e0d` on the existing binary, excluding current native UI build acceptance. The source FBX SHA256 is `ac5e1be20ca4468a949a1800c5337b0462d6257e6392bfe79f8399e679cdf80e`. Raw UnitScaleFactor1 and Null scale1 pass, and all342 UE component scale differences pass (maximum1.30535e-5). Blender correctly refuses publication: eight twist rows exceed the unchanged0.01degree rotation bar, up to0.488degree. The subsequent UE import is explicitly a diagnostic import of that rejected file.

Native-self342 still passes. Candidate343 has one extra container and one root parent change;336 local and342 component comparisons fail. Component position and rotation maxima remain26.40938361cm and179.99999602degrees. The reconstructed scene and16 original inputs are unchanged. No successful export, engine bind or GPU acceptance is inferred.

Sign-invariant quaternion dispersion rules out one common left or right rotation. Component angle-to-identity differences reach178.915789degrees, ruling out pure orthogonal basis conjugation. Among unchanged parent edges, local translation-norm differences reach9.021457cm. Component norm differences alone cannot rule out a global translation. The comparator therefore additionally reports signed component joint-distance differences for unchanged parent-child edges and four fixed pairs; these are diagnostic differences only, with no absolute positions/distances or new acceptance bars. Reprocessing the existing private capture requires no UE recollection.

A native synthetic short-bone probe reproduces copy-time rotation error before the FBX writer: at a1.53m-height oblique head, lengths0.1mm and0.01mm yield approximately0.037degree and0.912degree error after armature-data scaling. The pinned armature transform reconstructs head/tail-relative rest orientation in float32. Assigning edit-bone matrices with the original scaled lengths also exceeds the bar, so that alternative was rejected. This synthetic mechanism is excluded for the actual eight source bones by the subsequent measurements below; no owner frame or display length is altered to make it pass.

The bounded next owner-local evidence is: exact map/conform/normalize arguments and reference schema/hash; same-space source-to-conformed-to-normalized position/rotation deltas; and, for the eight refused twist rows, original length, head magnitude, copied length and source-to-centimetre-copy position/rotation/scale errors with before/after scene fingerprints. Retain all absolute matrices, geometry and weights locally. Inspect the exact installed legacy importer root/container predicate with its source hash before selecting any container treatment. These controls distinguish pre-export reconstruction from export precision and importer hierarchy semantics; they do not select an arbitrary rotation, armature rename or changed tolerance.

## Public copy probe and exact bounded follow-up fields

The nonprivate probe is [`scripts/lampway/capture_export_copy_deltas.py`](../../scripts/lampway/capture_export_copy_deltas.py). Load it with `runpy.run_path` inside the existing isolated Blender reconstruction, then call its `capture(actual_armature_name)`. The historical b1e300 version pins the two exporter modules to1368; the current probe pins the corrected modules by their exact SHA256 and returns only eight named twist rows, unchanged bars, source hashes, lengths/head magnitudes and source-to-copy errors. It uses the existing disposable-copy context and requires source/scene fingerprints to match afterward. It performs no FBX import/export, scene save, egress or native build. Keep the caller-selected armature name and local paths in the private harness; they are not returned in the receipt. Use the existing exclusive0600 receipt writer, retaining the complete raw source locally.

For reconstruction, return these fields from the existing exact tool calls and receipts, using stable local object aliases instead of private names/paths:

- `tool_source_sha256`: loaded `rig_tools.py`, `rig_conform.py`, `rig_tools/core.py` and exporter module hashes; `reconstruction_code_sha256` and the executed Python overlay commit.
- `arguments.map`: `family`, `profile`, `synthesize`, `dry_run`; `arguments.conform`: `reference_supplied`, `convention`, `ik_bones`, `dry_run`, `offsets_count`, `offsets_sha256`, `merge_weights_count`, `merge_weights_sha256`; `arguments.normalize`: `unit`, `apply_scale`, `dry_run`. Record the actual enum/boolean/numeric values, including defaults that were executed.
- `reference`: `kind` (`shipped_manny` or `explicit_profile`), `schema`, `sha256_file`, `sha256_bones`, `bone_count`, `adapter.centimeters_per_unit`, `adapter.basis`, and declared `space` fields where present. No full profile or absolute bind rows. The default conform reference is the shipped Manny profile; an empty argument must not be reported as an independently supplied native reference.
- `map_receipt`: `family`, `required_set`, counts of `map`, `unmapped`, `synthesized`, `collision_renames`, and `sha256.source_rest/reference_rest/tables`.
- `conform_receipt`: `convention`, `reference_kind`, counts of `renamed/reparented/unreferenced/synthesized`, `sha256.input/map/reference/output`, `rest_vertex_drift_m`, `posed_skin_drift_m`, `max_frame_error_deg` where present. Mark absent fields explicitly, rather than synthesizing a successful receipt.
- `normalize_receipt`: `unit`, `unit_factor`, `applied_scale`, `uniform`, `changed`, `frames_checked`, `max_world_drift_m`, `sha256.input/output` where present.
- `scene_units`: `system`, `scale_length`; `stage_objects.source/conformed/normalized`: `object_scale`, `world_scale`, `world_determinant`, `has_parent`, `object_rotation_angle_identity_deg`. Return no absolute object translations or raw transform matrices.
- `stage_deltas`: `source_to_conformed` and `conformed_to_normalized`, with `frame_space`, `translation_unit`, bone counts, parent-change counts and per-shared-bone `{name, position_delta_magnitude_m, shortest_rotation_delta_deg, scale_delta_max_abs}`. Derive from the existing raw snapshots in one declared Blender world space, respecting recorded units and correspondence; do not invent a cross-engine axis adapter. Return before/after scene/source hashes and unchanged-original flags. Retain all absolute snapshots locally.

For the importer predicate, start in the installed engine's `Engine/Source/Editor/UnrealEd/Private/Fbx/`. Candidate files to locate are `FbxMainImport.cpp` and `FbxSkeletalMeshImport.cpp`; their exact UE5.8 contents and symbols have not been verified in this cloud environment. Read-only search:

```bash
rg -n -C 12 'Armature|armature|GetRootSkeleton|RecursiveBuildSkeleton|IsNodeSkelMesh' \
  "$UE_FBX_SOURCE/FbxMainImport.cpp" "$UE_FBX_SOURCE/FbxSkeletalMeshImport.cpp"
```

Return only `engine_version`, source-relative `source_file`, `source_sha256`, `symbol`, the bounded relevant predicate lines, and which node-name/type/parent/creator checks govern retaining or skipping an armature container. If those names moved, locate the corresponding legacy FbxFactory root-selection function and report its actual path/symbol; if installed source is absent, report unavailable. From the existing candidate header return only `creator_detected_as_blender` and the predicate's matching node type/name for the known extra container, without arbitrary Creator strings, credentials, settings-file dumps or geometry. A name-based exporter change remained unselected until the exact predicate was established below.


## Actual reconstruction and installed importer evidence (2026-10-08)

The complete bounded evidence archive is `b1e300-actual-diagnosis.zip`, SHA256
`45d41249a44daac0959127e88f541345f3038d83c41d944e344eac0d6454ebcd`.
It includes the actual source/copy probe, exact reconstruction arguments, prior
reconstruction identity control, installed importer source predicates and derived
native/candidate comparisons. Absolute transforms, geometry and weights remain
owner-local. All16 original inputs remain unchanged; no new UE or Vulkan run was
performed for these measurements.

The eight actual source bones measure10.064–15.222cm. Maximum source-to-copy
rotation is0.000086766degree, position0.0000269895cm and scale5.36442e-7: all pass
the unchanged bars. The synthetic source-short-bone mechanism above does not
explain the actual0.488degree imported readback refusal. A separate long-source,
coincident-child writer/importer control tests imported display reconstruction;
its synthetic result does not establish the actual eight-row cause without
matching authored-file-to-imported-frame measurements.

The prior default conform supplied no independent reference and loaded the
shipped161-bone Manny profile (profile SHA256
`aa495c6943c10ab1dc42f2233d1602744bfb9adfc4469d0d11803b620c6c2f09`, bones SHA256
`93e7716dd3cd6865f51f489417e1b5ad9ff6fa6a4c3be738f12df057eced3e97`).
Source-to-conform positions drift at most2.66977e-7m but rotations change up to
179.869degree. Conform-to-normalize positions are unchanged. Native342 conform
now requires an explicit reference. `reference="source_copy"` preserves the
verified native graph and authored rest/skin on independent copies with identity
mapping and matching measured convention; mixed/unknown conventions refuse.
It reports preservation, not independent native UE acceptance.

Installed UE5.8.2-56702186+++UE5+Release-5.8 source hashes:

- `Source/Editor/UnrealEd/Private/Fbx/FbxMainImport.cpp`:
  `1ee1b75fca964f270726eabd3f5982ecc8b6dd98d233092c2e2710a8d1678aa6`.
- `Source/Editor/UnrealEd/Private/Fbx/FbxSkeletalMeshImport.cpp`:
  `5eec28f77f77d787ca66c333eec763a85ba137abeaeb9479a63652930ee35824`.

Creator detection at lines1123–1126 selects Blender for a Creator beginning with
`Blender`. `FFbxImporter::GetRootSkeleton` lines2617–2632 stops ascent through a
Null container only for the case-insensitive name `Armature` with a scene-root
parent. The actual candidate's creator/type/parent qualify but its container
name does not. The default convention recipes now declare the verified name
for the disposable export copy only. An occupied exact object name refuses
before allocation; originals are never renamed or modified. Native UE import
must still confirm the resulting342-bone hierarchy.

The existing supplied-data comparator finds21.8793cm signed distance difference
between the hands and9.02143cm on an unchanged parent-child edge. These rule out
any single global rigid correction for the supplied tables. They do not identify
which native mesh or Skeleton pose should govern; direct native mesh-versus-
Skeleton calibration remains unavailable. No common rotation or translation is
selected, and no acceptance bar is changed.


## Bounded next owner-local test

Load the exact published Python overlay in the existing disposable reconstruction
and inspect the untouched source with `api.rig_inspect(armature=SOURCE,
profile="metahuman")`. Use only its measured `blender` or `ue_axes` convention.
If it reports mixed/unknown, stop with that receipt: this correction does not
invent a source conversion or independent native reference.

Create a new map from that untouched source, then conform with the explicit
`reference="source_copy"`, the measured convention and a fresh output object
name. Record source-to-copy all342 position/rotation/scale deltas and original
fingerprints. Run the existing normalizer on this private copy, retaining its
complete native receipt, then export `recipe="auto"` to a fresh filename. Supply
an independent reference only when its authored source/provenance is actually
available; a self roundtrip must remain labelled self_roundtrip.

Require raw Null `Armature` with identity scale, UnitScaleFactor1 and every authored
node/BindPose/cluster bind under the unchanged0.01cm/0.01deg/1e-4 bars. Return the
bounded authored-bind consistency and imported display-error receipts. For the
eight historical refused rows, derive source→copy→authored-node/pose/cluster→RNA
rotation errors and imported display lengths without sharing absolute matrices.
This establishes whether the synthetic display reconstruction mechanism matches
the actual source. Unsupported layouts, occupied Armature or any bind contradiction
remain refusals, not acceptance.

Only after that gate passes, import the fresh candidate through the previously
recorded legacy settings into a new transient native UE skeleton. Reuse the
unchanged342-row native self control; require exactly342 candidate rows with no
extra container/parent changes and all original bars. Save no original asset.
If distances or frames still differ, retain the derived comparison and measure
native mesh-versus-Skeleton reference pose through verified local accessors;
do not select a rigid correction or switch reference poses to obtain a pass.
No combined cross-PR candidate or build is required for this owner-local test.
