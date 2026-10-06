<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Canon 02 — Rigid and similarity fit (the metal primitive)

Status: **CANONICAL**. Implemented by: LT `pipeline/validate.py:21 rigid_fit` (Umeyama, `with_scale`) and Titan
`tools/armour_validate.py:709 rigid_fit` (Horn quaternion, no scale) and Titan `tools/hand_pose.py:78 similarity`
(Horn + Umeyama scale). Three implementations of one primitive; see Gap.

## A. Problem

Given paired points P (source) and Q (target), find the transform Q ≈ s R P + t with R a **proper** rotation (det +1),
s a single positive scale (or s ≡ 1), and report the residual. Used for: a metal part's source fidelity (static placement is a
similarity of its original shell), a metal part's pose rigidity (every pose is a RIGID transform of the frozen rest), a glove's
palm fit (thumb base + four knuckles), the reference-to-body registration of an example, and correspondence checks
(MetaTailor export: one similarity x1.19, 33 deg, ~10 cm, 0.49 cm median residual).

Inputs: P, Q (n x 3, n >= 3, not collinear), `with_scale`. Outputs: R (3x3), s, t, per-point residual (rms, max, p95).
Units: whatever P and Q are in; receipts state mm.

## B. Method

1. Centre: A = P - mean(P), B = Q - mean(Q).
2. H = B^T A; SVD H = U S V^T; D = diag(1, 1, sign det(U V^T)); R = U D V^T (Umeyama 1991, "Least-squares estimation of
   transformation parameters between two point patterns", IEEE PAMI 13(4); equivalent to Horn 1987, "Closed-form solution
   of absolute orientation using unit quaternions", JOSA A 4(4), and Kabsch 1976).
3. s = trace(S D) / ||A||^2 when `with_scale`, else 1.
4. t = mean(Q) - s R mean(P).
5. Residual e_i = ||s R p_i + t - q_i||.

Refuse: fewer than 3 pairs; points on one line (rotation about it unfixed — `hand_pose.similarity` refuses this, the LT version
does not); non-finite input.

## C. Invariants

- **INV-02.1 Proper rotation always.** A reflection is never returned; a mirrored target shows up as residual (golden C01 mirror:
  rms 0.1217 m on a 0.3 m cloud).
- **INV-02.2 Scale is fitted ONCE, at the source-fidelity step, and recorded.** Pose rigidity is judged with scale FIXED against
  the frozen, sized rest; never refit scale per pose — it hides breathing (memory metal-never-blended; golden C01 breathe:
  1 % breathing reads 1.95 mm max residual rigid, 0 with scale).
- **INV-02.3 Fidelity is measured against the ORIGINAL shell**, never a posed or baked rest (the gauntlet's part22 read 0 torn
  edges against its baked rest while it was 19.3 mm RMS off its original; memory metal-never-blended, 2026-09-30).
- **INV-02.4 Correspondence first.** Pairs come from identity (same vertex id, the source ledger, or rest position within
  tolerance), never from nearest neighbours of an already deformed mesh (Titan `seam_ledger.py:3`).

## D. Failure modes already hit

| Date | What happened | Ruling / lesson | Source |
|---|---|---|---|
| 2026-09-30 | A position-based LBS baked the gauntlet's fused metal shell (vambrace + tongue) non-rigidly: 19.3 mm RMS from the original after the best similarity, while the torn-edge rule reported zero | metal = one similarity per part; two receipts (source fidelity, pose rigidity) | memory metal-never-blended |
| 2026-09-29 | One similarity for the WHOLE gauntlet swung the bracer off the forearm (x1.28) | a gauntlet has two anchors (bracer stays; hand into the example's hand) | memory seams-need-positional-weights; GENERATED-EQUIPMENT §7m |
| 2026-09-24 | Reference registration: Horn's similarity over shared joints left 1.5–6.5 cm residuals; spine_03 and hands off by 17/13 cm (rigs differ, shield hand raised) | exclude joints whose rigs disagree; report per-joint residual | GENERATED-EQUIPMENT §7h |
| 2026-09-28 | Surface ICP registered the fitted warrior 3–5 cm forward of the body (armour thicker in front) | registration of armour to a body is by enclosure (canon 09), not surface ICP | memory armour-registration-bias |

## E. Golden tests (`goldens/C01_rigid`)

| Test | Input | Expected | Falsifier |
|---|---|---|---|
| G02.1 | 40 points, s 1.07, 37 deg about (1,2,3), t (0.12,-0.40,1.30) | s, angle, axis, t to 1e-6; rms < 1e-6 | an implementation that skips centring returns a wrong t |
| G02.2 | the same target mirrored in x | det R = +1, rms > 0.01 m | a solver without the D correction returns det -1 and rms 0 |
| G02.3 | 1 % breathing | with_scale=false: max >= 0.5 % of the cloud radius (1.95 mm here); with_scale=true: s = 1.01, rms 0 | per-pose scale fitting reads 0 and PASSes a breathing plate |
| G02.4 | one vertex moved 5 mm | max residual in [4, 5] mm | an rms-only receipt hides it (rms 0.75 mm) |

## F. Implementation gap

- Three copies: LT `pipeline/validate.py:21-33`, Titan `armour_validate.py:709-732`, Titan `hand_pose.py:78-102` (plus a
  fourth in Titan `equipment_cage.py:280 rigid_fit`). LT's lacks the collinear refusal and a p95. **Canon: one module in
  Lampway, LT `pipeline/validate.py` grows `similarity_fit(P, Q, with_scale)` returning `{R, s, t, rms, max, p95}` and refuses
  n < 3 / collinear; every other caller imports it.**
- LT `features/fit_bind.py:202` computes the metal return residual with `with_scale=True` (correct for fidelity) but
  LT `features/validate_pose.py:69` computes `rest_fidelity` over the WHOLE bound mesh, not per metal part (INV-02.3 wants per
  part): a fused piece with one bad part averages out.

## G. Agent-facing tool contract

This is a library primitive, not an agent tool. Exposed through `lampway_fit_validate` receipts (`rest_fidelity`,
`rigid_residual_mm`) and `lampway_fit_place` (registration rows). No refusals beyond B. Receipt fields:
`{scale, rotation_deg, axis, translation_m, rms_mm, max_mm, p95_mm, n, with_scale}`.

## H. Open questions

None for the captain. The proposed metal limits (< 0.5 mm rigid residual, p95 strain < 1 %) belong to canon 05.
