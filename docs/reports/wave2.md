# Wave 2: armour pipeline to the engine set (branch lp/wave2 from lp/wave1)

Build path: <workspace>/wt-wave2/build/Prod (hardlinked copy; python synced from wt-wave2).
Tests at the head: client `tests/lampway_tools` 469 passed, 11 skipped (real binary, with LAMPWAY_SHELF_DIR / LAMPWAY_SHELF_SCRATCH set; without them the shelf-backed tests skip); server suite green (rc 0);
`tests/lampway` (brand, PII, link and env gates) 126 passed; the root suite has no failure the pre-session commit did not already have.

| tool | where | evidence |
|---|---|---|
| plate_pick / plate_prep | pipeline/plates.py | test_wave2_plates.py |
| seed_catalog, seed_audit (+ lineup) | server seeds.py, pipeline/seed_audit.py, features/seed_lineup.py | test_seed_catalog.py, test_wave2_seed_audit.py |
| tripo.regen actions | studios/actions.py | Wave 0 |
| piece_ratios (proportion score) | scripts/proportion/piece_ratios.py | test_wave2_piece_ratios.py |
| uv_score, uv_texel_density | features/uv_*.py | test_wave2_uv.py |
| mesh_defect_scan, silhouette_compare | features/defect_scan.py, silhouette.py | test_wave2_defect_scan.py |
| fit_place, fit_openings | pipeline/fit_place.py, features/opening.py | test_wave2_fit_place.py, test_wave2_openings.py |
| parts_critique | pipeline/parts_critique.py | test_wave2_parts_critique.py (9; class guard and weak-threshold mutants red) |
| palette_fit (+ live PAL: nodes) | pipeline/palette_fit.py, palette_live.py | test_wave2_palette_fit.py (8; linear measurement pinned) |
| studio_texture_flow | studios/actions.py tripo.texture.state / refs / restore, refs_set | server/tests/test_studio_texture_flow.py (10) |
| bake_maps | features/bake.py + scripts/bake/bake_maps.py | test_wave2_bake_maps.py (6, headless Cycles; Combined-lighting mutant red) |
| pbr_pack | pipeline/pbr_pack.py, features/pbr_audit.py | test_wave2_pbr_pack.py (9) |
| armor_piece_pipeline | pipeline/armor_piece.py | test_wave2_armor_pipeline.py (12) |
| fit_pose | posing.py | chest routed to pose_clearance; every other kind answers needs_decision (DOF ranges are the user's) |

## Honest limits
- Thresholds are unverified placeholders: seam 1 cm, cuff-up margin, TIE 5 %, weak 0.6 / far 30 mm / 50 polygons, asymmetry 0.8..1.25, bake black-texel 0.5 %, bake alignment 2 %, overlap 0.001.
- parts_critique's render stage and the palette nodes were not seen on a real piece; palette_fit's recorded multipliers are reproduced from synthetic colours, not the recorded run.
- bake_maps supports normal, albedo and ao; curvature, cavity, dust, bevel and position are not Cycles bake types and are refused by name. No helmet-crest acceptance run.
- armor_piece_pipeline maps the runbook onto 15 numbered steps myself (the contract's table was not numbered); it plans and records, it does not run the sub-tools, and it never confirms a spend.
- studio_texture_flow: the live driver was not run against a real Studio; the fake executor returns text shaped like the driver's.
- The in-app docs anchor check was dropped when the site left the repository: the route list pins paths, not anchors.
- Native C++ built and exercised (G4/G6/G8, spark avatar, splash) on lp/build tips; the spark avatar was not seen on screen (no agent window opened under Xvfb).

## Live verification on the user's shelf pieces (2026-10-05)
- **palette_fit, chest (p17 albedo vs the pbrA studio base, 4K, six classes):** the recorded fit is the MEDIAN in sRGB: plate val 0.677 (recorded 0.677), gold val 1.311 (1.308), worst class difference 0.19 (linen and embroidery, whose recorded values were later hand-overridden); linear-median misses by 4.0, sRGB-mean by 0.64. The residual after applying is lower for sRGB too (gold 0.144 vs 0.190). The default is now sRGB median; `space="linear"` stays. This answers the contract's open question 13.
- **parts_critique, chest transfer r1:** the pre-pass flags exactly the 90 islands transfer_parts marked (same ids), 16 part rows (two absent roundels, small tassets and flaps); `weak=1.0` flags 270.
- **bake_maps, Boots1 attempt_2 (27 753 faces) onto a 20 % decimation (8 256 faces) with the algorithmic Smart UV:** the planner refused the unwrap's 0.9 % UV overlap (and the overlap check now measures at the bake size, not 256 px, which had over-counted dense layouts); with allow_overlap the normal bake had 0 % black texels (mean 127/128/240); AO at the default cage had 64.5 % black texels with the "cage too small" hint, and 9.5 % after raising cage 0.08 / ray 0.16 as the hint says. The worker also gives the scene a world (AO needs one) and hides the target from the donor's rays. No helmet-crest high-poly exists on the shelf, so this is a boots donor-to-decimated-target bake, not the contract's crest.
- **armor_piece_pipeline, Boots1:** plan from step 8 = unwrap 20 + texture 30 + PBR 5 = 55 (155 for each of the five pieces); a run record with the real variant and attempt_2 artefacts (sha256 kept) refuses texture before the unwrap is recorded, passes after it, and flips the texture to stale when a later step changes the mesh hash. No credit was spent and no Studio action ran.

## Wave 2 remainder (branch lp/wave5)
Built: 05 model_compare (glb_stats, normalise by scale then centre, pairing, interior_diff / silhouette_compare interior=true), 07 view_verify folded into reference_pack (admit, measured front/back checks, the judge rule, actions, the character-sheet template set), the mesh_defect_scan amendments (ray coverage, scale-free epsilon), the ledger and receipt secret-prefix and userinfo-URL rejection, and upload identification by magic bytes.
Not built: the model_compare windowed viewer; the asset_gates amendment waits for Wave 5b. Tests per item are named in the commit messages (RED observed first in each).
