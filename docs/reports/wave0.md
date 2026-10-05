# Wave 0: shipped-tool correctness defects (branch lp/wave0 from lp/prompts, commit 0c744957)

Build path: <workspace>/wt-wave0/build/Prod (hardlinked copy of the prompts build, python synced from wt-wave0).
Tests: server full suite green (rc 0); client lampway_tools 341 passed, 11 skipped (real binary); new tests/lampway_tools/test_wave0.py (8) + server tests.
Each fix was observed RED on the shipped code first; mutants (seam check off, flip threshold off, copy off, n-limit off) each fail a test.

| defect | fix | evidence |
|---|---|---|
| asset_acceptance identity hard-coded to pass | identity = recorded source (lw_source_hash) AND it matches the reference hash or source_hash; typed checks; self-reference refused | test_identity_fails_for_a_derivative... |
| rig_armor rigid stretch cannot fail; 4 poses | clearance_body judges each pose against the POSED body (the only check a rigid plate can fail); pose set = wiki8 with multi-bone poses; rigid reports stretch_check "vacuous" and lists clearance as not_checked when no body is given | two tests |
| 7.3 cm cuirass seam tear passes 1.35 | pose_test measures seam gap growth between shells (pairs of different shells within 2 cm at rest); rig_armor fails above 1 cm | test_a_seam_that_tears... (worst_stretch < 1.35 while gap > 5 cm) |
| auto_rig mutates the source | copy=True default (<name>_rigged); copy=False opt-in; legacy tests made explicit | test_auto_rig_leaves_its_source_alone |
| mesh_prep misses flipped open shells; hash ignores UVs | per-shell outward ray votes (flagged shells turned over); hash {geometry, uv, material} | two tests |
| tripo_regen has no action row | six free actions tripo.regen.retry/sift/harvest/collect/apply/discard (region stays off: it needs the captain's approval flag) | server tests; the validation test caught n=0 silently becoming 5 |
| detail_normals has no caller | api tool, Features-panel entry, server Def lampway_detail_normals | test + server test |

## Honest limits
- Pose angles in WIKI8 are approximations in the algorithmic rig's bone axes (the wiki gives no numbers); the clearance/seam thresholds (0 m, 1 cm) are unverified defaults the captain owns.
- Flipped-shell detection reads a shell with no opposite wall (a half-cylinder) as outward.
- Seam-aware weight transfer (bind_to_armature ignoring roles and seams) is NOT fixed here: Wave 3 fit_bind owns it. Wave 0 only makes the acceptance gate catch the tear.
- The Studio regen actions are tested against the fake executor; nothing was run against the live Studio.
- rig_armor still passes a rigid plate with no clearance_body (the existing test requires it); the verdict says what was not checked.
