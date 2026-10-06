<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# MetaTailor golden references MT-1..MT-4 (black box, 2026-10-06)

These are **reference observations** of MetaTailor's fit, not targets. They record what a commercial template fitter does with
four SYNTHETIC pieces whose geometry is known exactly, so that each Lampway canon can state where it must do differently and
by how much. Nothing of the captain's armour went in. MetaTailor's output is a reference and is never shipped
(free tier, noncommercial; memory metatailor-study).

**Method: black box only.** Inputs (GLB) in, one FBX out, both measured. No binary was inspected. The settings come from
the UI and the app's own `Player.log`.

## 1. Export budget

| Item | Value |
|---|---|
| Tier | free, 5 FBX exports per month |
| Counter in the UI | **none shown.** Checked the Export tab, the export dialog, notifications, the account avatar and settings |
| Counter in the log | MetaTailor logs `Found N recent exports` before each export. Previous log (2026-09-29): `Found 0`, then `Found 1`. This run: `Found 2` |
| Used this month | **3 of 5**: 2 on 2026-09-29 (the gauntlet study), plus **1 for MT-1..MT-4**, which share one "Export Full Model" FBX |
| Remaining | **2**: MT-5 in reserve, plus one spare |

The cancelled glove attempts (curled-finger inputs, see §3 MT-1) logged six `Import Failed` user errors inside the Gloves
fitment sequence. They spent no export.

## 2. Inputs (synthetic, reproducible)

- **Generator:** `gen_mt_inputs.py` (this folder; headless Blender 5.2.1, `nice -n 15`). Environment:
  - `MT_BODY_GLB` = the native MetaHuman FullBody GLB (342 bones, rest pose);
  - `MT_OUT` = the GLB output dir;
  - `MT_SRC` = the JSON output dir.

  The pieces are built from the body's own joints and ray-measured radii. Every vertex carries its index in its UV:
  `uv = ((i mod N)+0.5)/N, ((i div N)+0.5)/N`. MetaTailor reorders, splits and welds vertices, but the UVs survive, so the
  UV grid is the correspondence.
- `measure_mh.py` writes the native joints (`mh_joints.json`) used for the frame check.
- **Reproduced 2026-10-06:** this folder's copies regenerated all 5 GLBs, all 6 JSON sidecars and `mh_joints.json`
  byte-identical to the ones MetaTailor imported.
- **Avatar in MetaTailor:** the stock MetaHuman FullBody already in the app (`titan_metahuman`). The fit ran in the existing
  study project, which was **not saved** afterwards.

| Case | Piece (labels) | Geometry |
|---|---|---|
| MT-1 | `mt1_glove_r` (palm, `{finger}_{1..3}`, `cap_{finger}_{i}`, `marker_*`); 2294 v | Palm tube wrist->middle_01 at hand radius +3 mm. **Straight** fingers: each keeps its base joint and phalanx lengths (direction fwd 0.85 + splay 0.15). Each phalanx is a constant-radius tube at the curled body finger's measured radius +3 mm. A separate **rigid cap** sits over each phalanx except thumb_1: 7 arcs over ±60° at r+7 mm, so the authored cap-to-leather gap is 4.0 mm. Landmark spheres (r 4.5 mm) sit dorsally at r+10 mm, coloured per finger, with white tips at 0.85 of phalanx 3 |
| MT-1 view copy | `mt1_glove_r_view` | The same mesh rigidly turned so all 21 keypoints show in one front view. `view = R·src + t`, recorded in `src/mt1_glove_r_view_transform.json` (t ≈ (-0.662, 0.977, 0.900) m). **This copy is the one fitted** |
| MT-2 | `mt2_plate_r` (plate); 143 v | 13x11 spherical patch over the deltoid (centre = lateral + 0.6 up from upperarm_r), 2 cm off the skin |
| MT-3 | `mt3_skirt` (belt, `strip_00..15`); 768 v | Belt: 2 rings x 64 at z 0.985 / 0.945, 1.5 cm outside the body. 16 strips, 4x10 grid each, 20.5° wide at a 22.5° pitch, z 0.94 -> 0.60. Strip `q` spans θ = 22.5q+1 .. 22.5q+21.5° from +X toward +Y; the body faces -Y, so strips 03/04 are the back, 11/12 the front and 00/15, 07/08 the sides. Each strip's radius = the body's max radius under it + 2 cm (0.156–0.222 m) |
| MT-4 | `mt4_greave_r` (greave, lid); 289 v | Tube calf_r -> foot_r, t 0.12–0.88, 12 rings x 24, +1.5 cm. Its top is **closed by a fan** whose single apex vertex (`lid`) lies on the leg axis, 41 mm **inside** the leg |

## 3. Settings, per case (as clicked)

| Case | Import category | Keep Source Dimensions | Other steps | Log trace |
|---|---|---|---|---|
| MT-1 | **Gloves**, "Which hand?" right | on | 21 keypoints clicked on the view copy, all placed green. The clicks are listed below the table | `Auto sizing`, `Warping using HandSkeleton_R`, `Doing Bone warp` |
| MT-2 | **Accessory** first, then **Shirts** | on | Accessory: parented by default to **`hand_r`** and moved off the shoulder. "Parent to Closest" kept `hand_r`. Reset, a manual parent of `clavicle_r` and Quick Place did not put it back on the shoulder, so that layer was deleted. Re-imported as Shirts (cloth); **the export holds the Shirts plate** | Shirts: `Auto sizing`, `Warping using HumanoidSkeleton`, `Doing new fast weights` |
| MT-3 | **Skirts** | on | — | same three lines |
| MT-4 | **Pants** (Shoes previewed, not chosen) | on | — | same three lines |

**MT-1 keypoint clicks** (window 2560x1440, the view copy's front view, in order): wrist 1026,201. Thumb base/first/second/tip:
1140,281 / 1248,484 / 1314,606 / 1342,650. Index knuckle/first/second/tip: 1135,626 / 1142,829 / 1146,942 / 1148,1006.
Middle: 1029,615 / 1029,855 / 1029,1005 / 1028,1058. Ring: 921,577 / 912,793 / 907,947 / 906,986. Pinky: 832,539 / 823,681 /
816,775 / 808,832. Every click landed on the coloured marker sphere for that keypoint.

**Why straight fingers.** The first glove (fingers following the MetaHuman's 86° rest curl) hid the tip landmarks behind the
palm in every view. MetaTailor then refused with "All landmarks must be placed" and the attempt was cancelled. This is an
automation requirement for Lampway: a glove's keypoints must be visible or estimable in the captain's views.

**Export.** "Export Full Model" (avatar + all four layers): FBX, 3.5 MB, `Fbx file generated ... without errors`, 3.50 s.

## 4. Measurement (`analyse_export.py`, this folder)

- **Import.** Blender's FBX importer with `global_scale = 100`. At the default scale the file comes in at 0.01x: the frame
  check is off by ~1 m and every edge "shrinks" 99 %. At 100 the exported joints match the native joints within
  **0.000–0.014 mm** (pelvis, hand_r, upperarm_r, calf_r, foot_r, middle_01_r, index_03_r).
- **Correspondence.** UV grid: 0 conflicts and 100 % coverage on all four pieces. MetaTailor kept every vertex count.
- **Per-part rigidity.** Umeyama similarity source -> export, giving scale, rotation and the rigid RMS/max residual.
- **Strain.** Edge strain |L/L0 - 1|.
- **Weights.** Per-part weight mass by bone, influences per vertex, bones used.
- **Clearance.** Against the exported avatar, by BVH nearest point plus a 3-axis ray-parity inside test.
- **Pose tests.** FK rotations on the exported armature, which drives the body and the pieces together.
- **Seams.** Distance from each separate part to its neighbour's faces.
- **Reproduced 2026-10-06:** this folder's copy, run against the same FBX, wrote `results.json` byte-identical to the
  scratch run.

**Caveats.**
- (a) The pieces are weighted to MetaHuman helper and corrective bones (`*_bulge`, `*_side_*`, `*_twistCor_*`, `*_kneeBack`).
  In UE those bones are driven by RigLogic and pose drivers. In these FK tests they follow their parents rigidly. So the pose
  numbers measure MetaTailor's weights under plain FK, not UE's runtime.
- (b) Ray parity is unreliable where the posed body touches itself (the fist), so the inside counts there are approximate.
- (c) The fist test rotates index..pinky 01–03 by **-40° each** about the index->pinky knuckle line. The middle_03 head moves
  51.5 mm palmar, which confirms flexion. The first attempt used +40°, which opened the hand by 57 mm, and was discarded.

## 5. Results per case

### MT-1 glove (Gloves template, 21 keypoints)

| Measure | Value |
|---|---|
| Whole piece, view copy -> export | scale 0.959, rotation 82.9°, **non-rigid residual 18.1 mm RMS / 56.4 mm max** |
| Edge strain (whole) | median **22.1 %**, p95 118.9 %, max 917 % |
| Leather phalanx parts, scale | 0.82–1.83 (distal phalanges stretched 1.26–1.83, proximal shrunk 0.82–0.94) |
| Leather phalanx parts, rigid RMS | 1.0–7.7 mm |
| **Rigid caps**, scale | **0.94–1.71** |
| **Rigid caps**, rigid RMS / max | **0.44–5.32 / 0.99–12.89 mm** |
| **Rigid caps**, median strain | **4.7–69.6 %** |
| Cap-to-leather gap (authored 4.0 mm min, 4.3–4.4 median) | export bind min **0.03–4.84 mm**: pinky_2 0.03, pinky_1 0.05, ring_1 0.10, thumb_2 0.13, i.e. in contact |
| Cap-to-leather gap in the fist | pinky_2 **0.00** mm |
| Clearance at bind, garment only (1412 v) | min **-23.1 mm**, p01 -18.1 mm, median +3.7 mm |
| Garment vertices inside the hand at bind | **46**: palm 33, thumb_1 10, index_1, cap_index_1, pinky_1 |
| Weights | **94 bones**, influences **max 29** / mean 10.0. Hand helper bones (`*_bulge`, `*_side_inn/out`, `*_pip/dip`, `*_palm*`) carry much of the mass. 12 of 14 caps have their own phalanx bone on top (0.21–0.74); cap_ring_1 has `middle_01_side_out_r` 0.16 and cap_ring_2 has `ring_02_side_inn_r` 0.22. Every cap spreads over 8–21 influences, so it bends |
| Fist (-40° per joint): strain | p95 32.2 % (caps 34.1 %, posed fingers 29.9–45.0 %, palm 15.8 %, thumb 2.8 % (not posed)) |
| Fist: inside the hand | 93 garment vertices (palm 34, index_3 20) |
| Fist: cap rigid RMS vs bind | posed fingers 0.48–4.09 mm (thumb not posed: 0) |
| Landmark spheres after the warp (authored 18–28 mm dorsal of their joints) | **0.9–21.0 mm** from the avatar joint they mark: wrist 0.9, thumb_0 2.1, thumb_2 1.0; thumb_1 21.0; the finger joints 4.0–17.8 |

**Reading.** The landmark warp is a smooth non-rigid map. It does **not** keep a declared-rigid part rigid. It rescales the
distal segments by up to 1.8x, closes the authored cap gap to contact, and leaves the palm up to 23 mm inside the hand. This
is the same behaviour as on the captain's gauntlet in the 2026-09-29 study (finger plates x1.13–1.78), now on known geometry.

### MT-2 shoulder plate

The Accessory route was tried first; see §3. The table is the Shirts plate.

| Measure | Value |
|---|---|
| Geometry | **unchanged**: displacement 0.00 mm, scale 1.000, strain 0 |
| Clearance at bind | min 14.8 mm, median 19.0 mm, none inside (authored 2 cm off the skin) |
| Weights | 10 bones: upperarm_out_r 0.46, clavicle_r 0.25, upperarm_twistCor_01_r 0.13, then upperarm_fwd/bck/in/bicep, twistCor_02, clavicle_out, spine_04 |
| Influences | max 8, mean 6.1 |
| Arm raised 60° (upperarm_r, world Y) | edge strain p95 **21.7 %**, max 32.5 %; rigid RMS vs bind **6.4 mm**; none inside |

**Reading.**
- **Accessory route:** ignores the authored placement even with Keep Source on. It defaults to `hand_r`, and "Parent to
  Closest" re-picks from the moved position. It does **not** choose the plate's bone by position.
- **Cloth route:** keeps the placement but skins the plate as cloth. It blends upper arm and clavicle, so a one-part metal
  plate bends 22 % when the arm lifts.

### MT-3 skirt (Skirts)

| Measure | Value |
|---|---|
| Geometry | **unchanged** (displacement 0.00 mm) |
| Clearance at bind | min 11.8 mm, median 34.2 mm, none inside |
| Weights | 27 bones (pelvis, spine_01/02, thigh and calf helpers both sides); influences max 19 / mean 8.0 |
| Belt | pelvis 0.44 |
| Side strips | thigh_twistCor_02 0.39–0.40 + thigh_twistCor_01 0.29–0.30 |
| Front/back strips | thigh_twistCor_02 0.24–0.31 + pelvis 0.22–0.29 |
| Thigh+calf share of strip weight by height (z m) | 0.94: **0.63** · 0.90: 0.69 · 0.86: 0.77 · 0.83: 0.86 · 0.79: 0.92 · 0.75: 0.97 · 0.71: 0.99 · ≤ 0.68: **1.00** |
| Both hips flexed 60°: strain | p95 **36.2 %** (strips 38.6 %, belt 21.1 %), max 79.4 % |
| Hips flexed: inside | 5 vertices |
| Hips flexed: strip non-rigid RMS vs bind | 2.5–3.1 mm (sides 00/07/08/15) to **18–22 mm** (front 11/12, back 03/04) |
| Hips flexed: strip-to-strip gaps | the authored minima (5.45–49.96 mm, irregular because the strip radii differ) change by at most 4.7 mm (04->05: 17.9 -> 13.1); none closes |
| Hips flexed: strip top to belt | 6.2–18.5 mm (authored 6.3–18.5) |

**Reading.** A height ramp from pelvis-dominant at the belt to thigh-only below about 0.68 m (≈ 0.26 m below the strip tops).
It is similar in shape to our `dress` rule, but the pelvis share at the strip tops averages 0.37. Strips are skinned as
cloth, so the front and back strips stretch 20–40 % in a hip flexion. Gaps between the separate strips stay open:
the smallest change is -4.7 mm, and none closes.

### MT-4 lidded greave (Pants)

| Measure | Value |
|---|---|
| Geometry | 15 of 289 vertices moved |
| The lid apex (authored 41.2 mm inside the leg) | pushed out to **+6.0 mm** clearance, a 47 mm move. The lid stays a closed fan, now a skewed cone (apex-to-tube-wall 55.6 -> 11.9 mm) |
| 14 other tube vertices | moved more than 1 mm; clearance rose 1.0–3.6 mm (12.7–14.8 -> 13.7–18.4 mm). Their place on the tube was not recorded |
| Whole piece | rigid RMS 2.8 mm / max 46 mm (the apex); tube alone 0.54 / 3.23 mm |
| Clearance at bind | min 6.0 mm, median 14.3 mm, **0 inside** (source: 1 inside, -41.2 mm) |
| Weights | 9 bones: calf_twist_01_r 0.49, calf_twist_02_r 0.39, then calfTwistCor/knee/kneeBack/ankle helpers, foot_r, thigh_twistCor_02_r |
| Influences | max 6 / mean 3.5 |
| Knee bent 90° (calf_r) | edge strain p95 0.4 %, max 3.1 %; rigid RMS vs bind **0.18 mm**; none inside |
| Knee bent: lid apex | stays 11.9 mm from the wall |

**Reading.** MetaTailor does not detect or open a cap. It treats the penetrating apex as a collision, pushes it to about
6 mm outside the skin and moves 14 other tube vertices by more than 1 mm, so the closed lid survives as a deformed cone. On the calf, the
twist-bone weighting keeps a tube rigid through a knee bend.

## 6. What each canon takes from this (contrast, not target)

| Golden | Lampway must | MetaTailor (measured) | Canon |
|---|---|---|---|
| GMT.1 rigid caps on a glove | each cap: one similarity, residual ≤ 0.5 mm, strain ≤ 1 % (the captain's limits, 2026-10-06) | caps 0.44–5.32 mm RMS, scale 0.94–1.71, strain up to 70 % | 03 INV-03.2; 07 INV-07.2 |
| GMT.2 authored seam gaps | the cap-to-leather gap per the source ledger, within the seam limit | 4.0 mm -> 0.03 mm (contact) | 05 seam ledger |
| GMT.3 palm clearance | no garment vertex inside the body after fit | 46 inside, min -23.1 mm | 15 clearance; 05 |
| GMT.4 a one-part plate is one bone | weight 1.0 to the bone chosen by measured motion | 10 bones, 22 % strain at 60° arm lift; the accessory path picks `hand_r` | 07 INV-07.2, INV-07.6; 09 |
| GMT.5 strips | metal strips (pteruges) stay rigid per strip; the dress share is only for cloth | strips as cloth: 36 % p95 strain in 60° hip flex; thigh share 0.63 at the top -> 1.0 at 0.68 m | 07 dress; 03 INV-03.2 |
| GMT.6 caps are openings | detect the lid, delete it, gasket the rim (canon 06), then fit | lid pushed out and kept as a skewed cone | 06 |
| GMT.7 influences | cap at the profile limit (native up to 12) with the remap recorded | up to 29 per vertex on the glove, 19 on the skirt | 07 influence cap |
| GMT.8 already-clear input | a placed, clear piece is left untouched by the fit | plate and skirt unchanged (0.00 mm), greave: the apex plus 14 tube vertices | 03 order; 09 |

## 7. Files and hashes (SHA-256)

Large binaries stay out of the canon, in `<boxes>/mixar/scratch/canon/metatailor/`. MetaTailor's original export is in its
prefix at `C:\METATAILOR\out\canon_mt1-4\`.

| File | SHA-256 |
|---|---|
| `export_canon_mt1-4/canon_mt1-4.fbx` (3.5 MB; Armature 338 bones; Model 51 578 v; the four pieces) | `34f0d8a258bf0edece9e3558e8899c4d45abb2fd7a3295d646b833a15757a69c` |
| `mt1_glove_r.glb` (input as authored) | `50e7cf34c0a9cab44d2a6858b3403eb9840d561642c16ace5c7a70d889e8e3b8` |
| `mt1_glove_r_view.glb` (input fitted) | `17417a6f153308f8f0ec1f187489373164463df8071b25f97da3e5d8f5af02f2` |
| `mt2_plate_r.glb` | `02bcf3d4d6aa8ff66fcee80eb524960768d6e999bb14d3a61107af6ccba547ed` |
| `mt3_skirt.glb` | `5de57db293bc034aff1d91ea60413b73a4db2d330d96be4df2275b6d3f85b087` |
| `mt4_greave_r.glb` | `1c3c1cd68914e43a573173a5c19414d179ba85b6e9d2bdc8606209098bf5828d` |
| `src/inputs_meta.json` | `7b8c6e7c2025b40e34a0f21c7bde1a5ec88062d3a15892371025e258d4b04134` |
| `src/mt1_glove_r.json` | `01f21af29e61d705899f3915b282c1a0ef982de55702929eec1d504598ab18ee` |
| `src/mt1_glove_r_view_transform.json` | `67aa056b914b4e144398353d7d3ade127bd086b2abff4c2307b62df175472827` |
| `src/mt2_plate_r.json` | `cba5a810b4c4c0d0976eb4c86f305d7bd721460afb38029cff873f8689d9fbb2` |
| `src/mt3_skirt.json` | `fa148753cc1ae0e2ddcad061eccb3e4ffaa23ab26baeb16d3c1361713054f4f6` |
| `src/mt4_greave_r.json` | `7cc3a241de9c978b53e41813c2e91cb7b2e8e358830c131859498c862a79cef8` |
| `mh_joints.json` | `26cd01deaee34aee74c7e66c12142328932f16f23596c126606bc09957f4d254` |
| `results.json` (this folder; the full measurement) | `e119c6dc6a3e2f5985f6b139d3e89669fc8b28091033cc73c0d57f4bd837ff5a` |

**Re-running.** Run `gen_mt_inputs.py` and `measure_mh.py`, then fit in MetaTailor per §3 (this spends an export). Copy the FBX to
`$MT_WORK/export_canon_mt1-4/` and run `analyse_export.py`. Re-measuring the recorded FBX needs no export.
