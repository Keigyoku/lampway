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
