# Wave 3: fit, bind and export to the engine (branch lp/wave3 from lp/wave2)

Build path: <workspace>/wt-wave3/build/Prod is not separate: the Wave 3 python was run in the shared native build (<workspace>/wt-build/build/Prod, rebuilt from lp/wave0 tips) via scripts/lampway/sync_python.sh.
Tests: see the numbers at the end of this file; every tool below was observed RED first (or says it was not), and the ones with a mutant say which mutant turned a test red.

| tool | where | evidence |
|---|---|---|
| weight_audit (audit, plan), weight_cleanup | features/weights.py | test_wave3_weights.py: rigid plate, competing bones, side check, rigid-vs-deforming plan flips across the joint, limit to 4 and renormalise, 40 % mass-zeroing refused (mutants red) |
| weight_transfer (algorithmic and robust) | features/weights.py, scripts/rig/robust_weight_transfer.py | the robust engine is the paper's biharmonic solve (robust Laplacian, scipy); libigl and robust_laplacian were installed in a venv (approved); same matches as the algorithmic engine; the pocket blends 0.2..0.8 |
| garment_clearance | features/clearance.py | signed distance per pose, class tolerances, poses reset afterwards (mutant red), unplaced and unskinned refusals |
| fit_validate (measure, judge) | pipeline/validate.py, features/validate_pose.py | rigid residual with the scale fixed (a breathing pose fails: mutant red), strain, seam gap, crossings, crossing control, PASS/FAIL/UNVERIFIED/REFUSED/UNPROVEN, the original required |
| skeleton_export_check, engine_import_check | features/export_checks.py | FBX written by the real binary and read back: leaf bones, missing/extra/parent, 100x scale, posed rest, header version, UCX_ collision names, missing textures |
| fit_body | features/fit_body.py | hashed package, parents first, verify refuses a changed byte, native-only, weights need a sidecar |
| fit_export | features/fit_export.py | gates (FAIL, UNVERIFIED roles, bind check, texture hash chain, unknown bones, existing tag) and a read-back of every joint's position AND axes (a position-only gate mutant is red; Blender's default axes fail the read-back) |
| fit_bind | features/fit_bind.py | roles required, metal rigid on one bone, blend refused, seams and rigid groups, seam_opens gate at apply, weights from a scene body, return residual (mutants red) |
| fit_glove | pipeline/fit_glove.py | the typed plate-label decision (labels stage); pose/bind/report: needs_decision |
| fit_state | pipeline/fit_glove.py | needs_decision (is the Laya route still the direction?) |

## Live check on the real MetaHuman body (GLB from the user's Pictures, 2026-10-05)
fit_body built a package of 342 joints and 132 800 vertices (verify green); weight_audit on it: 0 unweighted vertices, 16 519 vertices over a 4-influence cap (MetaHuman skins use more), 33 sums not 1, hotspots named (neck_01/spine_04, head/neck_02);
skeleton_export_check on the imported armature: no leaf bones, unit scale 1.0, up Z, and three posed corrective bones (upperarm_in_l/r, lowerarm_in_r) that the glTF import leaves posed with no animation (a finding, not a defect of the check: clear them before an export).

## Honest limits
- No UE editor leg: the native weights sidecar, helpers and reference bind (armour-validate sidecar/helpers) are the user's box; fit_body refuses uproject, takes a sidecar file, and fit_bind's body weights come from a scene body object (stated as an approximation in its result).
- fit_validate's receipt is lampway.armour-validation/1 (Titan's shape could not be read); the engine leg and captured poses are not built; default limits are PROPOSED placeholders; cloth, leather and embroidery have none (UNVERIFIED, never PASS).
- fit_export's read-back compares against joints.json in the Blender frame; the UE-frame bind.json comparison (bind_mismatch against the native pose) is not built (bind_mismatch itself is, in pipeline/validate.py).
- fit_bind: the fit-pose bind-and-return deformation is not built (return reports the rest residual only); the profile data files (fit-profiles, piece-weights) are not vendored.
- Nothing here was run on a real armour piece against the MetaHuman body: the pieces were synthetic, because placing a real piece needs fit_place on a mesh_to_npz pair.
- fit_glove pose/bind and fit_state are decisions, not tools; weight_cleanup mirror_from is refused (not built).

## Test counts at the head
client tests/lampway_tools: 528 passed, 5 skipped (real binary; LAMPWAY_PYTHON_SCIENCE and the shelf variables set); server suite green (rc 0); the root suite has no failure the pre-session commit did not already have.
