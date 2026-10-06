# Lane canon: the algorithm canon implemented (branch lp/canon)

Brief: implement `specs/canon/IMPLEMENTATION_PLAN.md` in its order, so every agent calls a tested tool instead of re-deriving
the maths ("I'm more worried about deriving these things repeatedly", the captain). Base `lp/wave5` at `00d907d4`.

## Rulings applied (the captain, 2026-10-06, relayed by the coordinator)

- **Contradiction 1:** the native body is canonical for bind, weights and validation; the fitted example supplies the pose and the
  armour-to-body relationship only, never the weights. (fit_bind's weights come from the body object; nothing in this lane reads
  weights from an example.)
- **Fit validation limits:** Titan's limits are the defaults, ADOPTED: metal rigid residual < 0.5 mm, metal edge strain p95 < 1 %,
  no body crossing (`pipeline/validate.DEFAULT_LIMITS`, `status: adopted`). Still owed and flagged `needs_decision` in every
  receipt: leather / cloth / embroidery limits (canon 05 H.2) and a seam acceptance limit (H.3).
- **Chest clearance:** stays `needs_decision` at the canon's default.

## How the goldens run inside the suite

`tests/lampway_tools/canon_goldens/` is a verbatim copy of the canon's generator (`gen_goldens.py`, `meshgen.py`), its reference
implementations (`reference.py`, the oracle) and `selftest.py`. `canon_support.goldens` generates C01-C14 once per session into the
pytest base temp and checks every file against `goldens.sha256` (the canon tree's own bytes, 41 files): a test can never pass on a
drifted fixture, and no OBJ/JSON is committed. Blender-side tests load a golden OBJ verbatim (`canon_support.LOAD_OBJ`, no
importer axis conversion).

## Item 1: `canon_geom`, the one module of shared primitives (DONE)

`lampway_tools/canon_geom/` (numpy only, no bpy; every file under 500 lines). `API_VERSION = 1`; the names in `__all__` are the
stable interface the orphans lane (rig track) and the normalization schema build on. Modules: `rigid` (canon 02 similarity, p95,
refusals), `lbs` (forward LBS and the EXACT inverse, `SingularBlendError` by vertex), `inside` (winding numbers, closest points,
signed distance, `PseudoNormals` - the fast closed-mesh sign - and `boundary_edges`), `uvmeasure` (half-open raster, coverage, the one
island rule, `uv_metrics`), `identity` (`weld_keys`, `components`), `enclosure` (slices, first hits, `inner_wall_centre`,
`harmonic_centre`, `enclosure_shift`), `views` (orthographic triangulation, robust drop, calibration), `axes` (the joint-named
grammar: `resolve_axis`, `pose_cs`, `expand_pose`, `check_expect` in cm, `segment_box_overlap`, the capped `control_shift`), `bones`
(`chain_ends`, `bone_segments`, `flex_axis`, `finger_axis`, `curl_delta`, `CONTINUATION`), `conventions` (the body frame and canon
01 F's `conventions_block`), `seams` (source ledger, gaps, `segment_crossings`), `skinweights` (remap, welded inpaint, dress,
falloff, band), `masks` (true-aspect silhouette fit).

**Ported with their tests:** Titan `armour_validate` (pose_cs, resolve_axis, expand_pose, check_expect, segment_box_overlap,
control_shift), `proc_body` (chain_ends, flex/finger axis, curl_delta), `views_joints` (triangulate, robust, calibrate),
`weight_profile` (remap_table, dress), `hand_pose.falloff_weights`: their cases are in `test_canon_geom_grammar.py` and
`test_canon_weights.py` with the numbers unchanged. These ported tests went in AFTER the code (they are Titan's, already proven
against Titan's implementation); two of them caught real bugs in my port on first run (a loop index shadowed twice in
`PseudoNormals.signs`, and `check_expect` returning numpy bools).

**Goldens (RED then GREEN):** `test_canon_geom.py` 29 cases over C01, C02, C05, C06, C08, C09, each falsifier a test of its own.
RED: collection `ImportError: cannot import name 'canon_geom'` (the module did not exist). GREEN: 29 passed.

**Tool level (RED then GREEN, `test_canon_item1_tools.py`):**
| tool | RED (before the change) | GREEN |
|---|---|---|
| `pipeline/validate.rigid_fit` | `KeyError: 'p95_m'`, no collinear refusal | delegates to `similarity_fit` |
| `uv_islands` / `lampway_uv_score` on C09 | `overlap 0.0017` (the canon's inclusive-raster number) | overlap 0.0, utilization 0.4375 |
| `garment_clearance` on the C05 spike | `min_clearance_m -0.05099, penetrating_vertices 1` | sign by pseudonormal: 0 penetrating |
| `rig.pose_test` clearance on the spike | `{'min_m': -0.05099, 'penetrating_vertices': 1}` | 0 |

Mutation: replacing the pseudonormal sign by one face normal in `rig._signed` fails both spike tests (2 failed).

## Item 2: validation receipts (DONE, engine leg and captured poses not built)

`features/validate_pose.py` rewritten to canon 05; `pipeline/validate.py` judges with Titan's semantics; Titan's poses vendored as
`pipeline/armour_poses.py`. Receipt schema now `titan.armour-validation/1`.
- expectations measured on the posed JOINTS (`{joint, along|closer_to, min_cm}`); an Euler-angle expectation is REFUSED as
  tautological; poses in the joint grammar (axis through the joint, carried by the parents' motion) or by name; Euler poses stay
  as the stress set;
- seam row = the SOURCE ledger (exact source coordinates across parts) measured in the pose: `{pairs, open_over_2mm, max_cm}`;
  without part labels it is UNVERIFIED with the reason;
- SURFACE crossings both ways (BVH ray casts over each piece edge and each nearby body edge) and inside vertices;
- rest fidelity of the whole piece AND of every metal part (canon 02 receipt);
- the capped positive control (`control_shift`, depth 1 cm capped at half the extent) counted by surface crossings;
- limits = Titan's, ADOPTED (the captain's ruling): metal `rigid_max_mm 0.5`, `strain_p95 0.01` (a fraction), body `crossings 0`.

RED (`test_canon_item2_tools.py`, 5 cases): the joint pose errored on the old `expect` format; the Euler expectation was measured
instead of refused; no `seam` key; the face-interior panel read PASS with `surface_crossings None`; no control fields. Pure
(`test_canon_validation.py`, 13): 12 failed (old limits 1.0 mm / strain max %, no ledger, no crossings). GREEN: all.
Mutation: removing the half-extent cap in `control_shift` fails the C14 control test.

## Item 3: weights (DONE for the brief's scope; dress / plate / fade / seam-band profiles NOT wired into fit_bind)

- `weights.transfer` welds first (`weld_m`, default 1e-5 m, 0 for an authored rig): one match per welded vertex (its copies' summed
  normal), every copy gets that row, and the harmonic fill runs over welded vertices (`canon_geom.inpaint_harmonic`).
- `fit_bind` stage weights, restrict parts: matched ONLY on the body's own region for the part's bones (triangles whose dominant bone
  is an allowed bone or descends from one), normal within 30 deg or flipped, barycentric weights; a weight on a disallowed bone moves
  to its nearest allowed ancestor, else to the part's `fallback` (new `bind_overrides` key), else the bone is refused by name; the
  unmatched are inpainted over the welded part; a vertex left with no weight raises `ZeroWeightError` naming it.
- `weights.plan` and `fit_bind._hist` use bone segments head -> continuation child (`weights.bone_segments`), never the tail.

RED (`test_canon_item3_tools.py`): C04 fill `{'unweighted': 30, 'identical': False}` (the canon's 30); sleeve and cuff rows `[{}, {}, ...]`
(zero rows written); no refusal for an unreachable part; the plan named `lowerarm_l` for a piece mid-upperarm (tails up). GREEN: all.
Mutations: no region constraint -> the sleeve test fails (after I made the fixture discriminating: my first fixture let the 30 deg
normal gate alone keep the sleeve off the torso, so the first region mutant SURVIVED; the slab now makes both surfaces normal-compatible);
no weld in the fill -> C04 fails.

## Item 4: bind and return (DONE)

`fit_bind` stage `return` writes `<piece>_rest` by the exact inverse of each vertex's blended transform; the weights stage records
the fit pose (`_pose_record`, sha256 of every pose bone's basis) and `return` refuses at another pose; singular blends are refused
naming vertices and bones; a metal part whose rest is not a similarity of its source within 0.5 mm is refused; the round trip is
measured by Blender's own skinning of the rest by the fit pose.
RED (`test_canon_item4_tools.py`): the old return made no object (`KeyError 'object'`); no `_pose_record`; no refusals. GREEN: rest
within 1e-6 of C02's `rest_vertices`, Blender round trip < 1e-6. The falsifier test (blend of inverses, 10.825 mm) passes against the
reference. **Discipline breach, stated:** I wrote these tests and then applied the implementation without running them first (the
client suite was running and I staged the code); the RED was measured AFTERWARDS, on a detached worktree at the pre-change HEAD with
only the new tests copied in. It failed for the reasons above, so the tests do discriminate, but the order was wrong.

## Item 5: placement (DONE except joint-relative constants and the source-part check)

`pipeline/fit_place`: the waist is scaled by its INNER wall's span and centred by inner-wall enclosure over its band; helmet and
boots are centred by the inner wall too (the head section by the same rule); every section centre is the first harmonic of the
inner wall's radii (canon 09 B.4, `canon_geom.harmonic_centre`) - a ray through an opening is left out of the fit. Gauntlets: the
residual axis angle (< 25 deg) is corrected rigidly per side, not left.
RED (`test_canon_item5_place.py`): waist scale 0.968 (outer extents) and the C06 shift off; gauntlet axis left at 15.0 deg. GREEN.
Shelf regression pins (`test_wave2_fit_place.py` with `LAMPWAY_SHELF_SCRATCH` set to the mounted shelf): all pass. The 4-ray inner
wall first FAILED them (the shelf's waist self-test piece is open at the front: the -y ray left through the slit); the harmonic fit
fixed it; then the helmet missed by 10.8 mm until its head section was centred by the same rule.
Not done: absolute constants (`|x| < 0.27`, foot `z < 0.04`, gauntlet arm `|x| > 0.25`) - re-expressing them needs factors the canon
does not give (a value I would have to invent); the source-part (detached glove) check - `fit_place` has no source input today.

## Items 6 onward: the rest of the main plan (partial)

Same breach as item 4: the tests below were written, the code applied, and the RED measured afterwards on the pre-change HEAD
worktree (`9 failed, 2 passed` across items 4, 6, 8). One of those REDs was for the WRONG reason: the bake test failed on the old
inclusive raster ("overlapping UVs 0.0039", item 1's bug), not on the ray. I then ran the right falsifier as a mutant in the current
tree: `RAY_PER_CAGE = 0.5` fails with `ray 0.0141 != 2 x cage 0.0566`; reverted.

| canon | tool | change | RED reason | test |
|---|---|---|---|---|
| 15 clearance | `garment_clearance` | an OPEN body (boundary edges) is refused unless `body_open_band_m` is declared; vertices within the band of the opening stay unsigned (`unsigned_near_opening`); `body_open` in the receipt | unknown kwarg / no refusal | `test_g15_3_...` |
| 21 / 01 C.3 export | `skeleton_export_check` | per-bone FRAME comparison (largest axis angle, tolerance 0.01 deg) beside positions; the reference FBX is read back with the export convention primary Z / secondary X | `frames` absent (and the old default-axis import read the unit scale as 3) | `test_the_skeleton_export_check_compares_bone_frames...` |
| 14 bake | `bake_maps` plan | default ray = 2 x the cage (`RAY_PER_CAGE`) | ray 0.5 x (mutant) | `test_g14_3_...` |
| 12 retopo | `common.mesh_report` (the retopo receipt) | TWO-SIDED deviation: `to_source_max`, `from_source_max`, `p95_deviation`; `max_deviation` is the worse side | no `from_source_max` | `test_g12_2_...` |
| 10 silhouette | `silhouette_compare` (plate path) | masks put at one subject height with their aspect kept (`canon_geom.fit_masks_true_aspect`) | no `_fit_pair` (old: crop-and-stretch reads 1.0) | `test_g10_4_...` |
| 13 UV (item 8) | `uv.uv_report` (lampway_uv_unwrap's report) | the one island rule and the half-open raster at 1024 (`GRID` 512 inclusive before) | overlap 0.0033 on C09 | `test_canon_item8_uv.py` |
| 05 controls | `fit_validate` | the crossing control capped at half the extent (item 2) | - | item 2 |

Not done in this pass: per-bone SCALE in the export check (Blender stores no rest scale; only pose scale is visible and the existing
`posed` check already reports it); relative pose-clearance heights (the ported shelf script `scripts/proportion/pose_clearance.py`
selects torso/neck/arm regions by absolute heights; re-expressing them from joints needs a measured rule and the chest regression
(166/207 -> 90/103) to re-pin); openings fixes (item 11); joints from views (item 12); the orchestrator (13); soft-part conform (14,
waits on the captain's decision 03-H2); bake 16-bit / hit mask / auto cage (the rest of item 9); retopo per-part and
`use_preserve_sharp` (the rest of item 10).
