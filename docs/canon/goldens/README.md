<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Canon goldens

Synthetic, public-safe test assets and their generator. No asset of the captain's is committed here; where a canon cites a number
measured on one of his pieces, that number is cited in the canon page as a regression value, and the asset stays on the shelf.

```
python3 gen_goldens.py [out_dir]       # writes C01..C14 (OBJ + JSON), deterministic: two runs are byte-identical
python3 selftest.py [dir]              # reproduces every expected value with reference.py and shows each falsifier failing
python3 gen_rig_goldens.py [out_dir]   # writes R01..R07 (case.json each), deterministic; R07 reads C02
python3 rig_selftest.py [dir]          # the same for the rig canon (16-22) with rig_reference.py
```
numpy only. Frame: metres, body frame (Z up, faces -Y, wearer's left +X) unless a case says otherwise. Expected values are analytic
from the construction; where a value is a property of a known-WRONG method (a falsifier), `selftest.py` recomputes it.

| Case | Canon | What it pins | Falsifier it kills |
|---|---|---|---|
| C01_rigid | 02, 05 | similarity recovery; proper rotation on a mirror; 1 % breathing seen by a rigid fit; one-vertex residual | per-pose scale fitting; det -1 solvers; rms-only receipts |
| C02_inverse_lbs | 04 | exact return to rest = inverse of the blended transform; singular refusal | blend of inverses (10.8 mm on 46 vertices) |
| C03_seam_tube | 07, 05 | one shell, two parts; source seam ledger (32 pairs); positional weights keep the seam shut in a 40 deg twist | one bone per part (8.208 cm chord) |
| C04_weld_inpaint | 07 | weld before inpainting; duplicates bit-identical | index-graph fill (30 unweighted) |
| C05_clearance | 15, 05 | signed distance on a closed sphere; winding-number sign at a needle apex; open-body fractional winding | nearest-face-normal sign |
| C06_enclosure | 09 | inner-wall enclosure recovers a displacement exactly | all-vertex extents (12.5 mm bias) |
| C07_pose_solve | 08, 05 | the sweep returns the authored arm angle (30 deg) with zero penetration | ranking by mean clearance; no sign check |
| C08_multiview | 11 | exact orthographic triangulation; one-view refusal; robust outlier drop | plain least squares (43 mm) |
| C09_uv | 13 | utilization/overlap/flip with a half-open raster; seam-split components; the 70 mm² relief rule | inclusive raster (0.00167 phantom overlap); index adjacency |
| C10_bake | 14 | analytic cap normals; DX = GL green flipped; cage/ray rules | ray shorter than the cage on a sunk HP |
| C11_proportion | 10 | section extents; scale-free ratios; aspect-preserving IoU | crop-and-stretch IoU (1.0 for a 2:1 vs 1:1) |
| C12_gasket | 06 | a capped site, rim radius at clearance, manifold result | silent default collar depth |
| C13_retopo | 12 | property targets on a dense sphere | one-sided deviation (to build: G12.2) |
| C14_controls | 05 | the crossing control capped at half the piece's extent | the uncapped 1 cm push buries a rivet |
| R01_mapping | 16 | naming family by table hits; slot map; tie refusal; missing spine joints at reference arc-length fractions | substring mapping (`hand_l` -> `LeftHandIndex1`); midpoint synthesis (65.3 mm) |
| R02_rest_frames | 17, 21 | frames from joints + up hint, Blender (Y along) and UE axes (X along); the convention classifier | track-then-apply keeps the input roll (40 deg) |
| R03_apply_scale | 18 | exact translation transfer under non-uniform object scale; uniform control | per-channel scaling: 0.2236 m, equal to GRT 4.3.0 measured on Blender 5.2.1 |
| R04_retarget | 19, 22 | `W_t = W_s R_s^-1 R_t`, parent-first keys | local copy (55.7 deg); pose-space copy changes bone length (30 mm) |
| R05_root_motion | 19 | root on the ground, never tilted, exact recomposition, yaw none/heading | copying the pelvis rotation tilts the root (5.96 deg) |
| R06_template_fit | 20 | joints written from the example (residual 0), length ratios, missing-joint refusal | joints copied from the template body: `copied_not_fitted` |
| R07_rest_change | 19, 04 | a baked rest returned by the exact inverse (0.0) | return through the new bind = blend of inverses (12.5 mm, 46 vertices) |

The R cases are synthetic (made-up proportions); R01 carries public bone-NAME conventions only. No vendor skeleton geometry.

`metatailor/` holds **black-box reference observations**, not pass/fail targets. MetaTailor 2.7.2.3 fitted four synthetic
pieces in one FBX export on 2026-10-06:

- MT-1: a rigid-cap glove (Gloves, 21 keypoints);
- MT-2: a shoulder plate (Accessory tried, Shirts exported);
- MT-3: a 16-strip skirt (Skirts);
- MT-4: a lidded greave (Pants).

The folder has the input generator, the analyser, `results.json`, the settings and clicks, and the hashes of the binaries
kept in scratch. Its README §6 lists the contrasts GMT.1–GMT.8 the canons cite.
