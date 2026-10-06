<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Canon 04 — Bind at the fit pose, return to rest (the exact inverse of linear blend skinning)

Status: **CANONICAL maths; GAP in both implementations** (Lampway has no return; Titan's return uses the wrong inverse).
Implemented by: LT `features/fit_bind.py` stage `return` (reports a residual only); Titan `tools/equipment_fitpose.py:69-85`
(`return_maps`, `bind_return`).

## A. Problem

The fit poses the stock skeleton INTO the piece (CC5's method: the captain, 2026-09-28: "the reason CC5 fitting is SO good is
because a human goes through and does the posing then the transfer of their built in object type weights"). The piece is
weighted where it sits — at the fit pose — and must then leave **in the native rest pose**, skinned to the native skeleton,
because UE's leader-pose validation requires the piece's own bind to equal the native reference bone by bone (memory
native-body-canonical-for-fit; canon 05 `bind_check`).

Inputs: piece vertices `v_fit` (body frame, metres) authored/placed at the fit pose; per-vertex weights `w_b` (canon 07, sampled
at the fit pose); per-bone fit-pose world matrices `F_b` and rest (native reference) world matrices `R_b` (4x4, from the body
package and `pose.json`). Output: `v_rest` such that forward skinning of `v_rest` by the fit pose reproduces `v_fit` exactly.

## B. Method

Forward LBS (Magnenat-Thalmann et al. 1988; the engine's model): `v_posed = (Σ_b w_b P_b R_b^-1) v_rest`.
Let `M_b = F_b R_b^-1` (the bone's rest -> fit-pose map).

**Exact return (canon):**

    A(v) = Σ_b w_b(v) M_b              (one 4x4 per vertex)
    v_rest = A(v)^-1 v_fit             (refuse when |det A(v)[:3,:3]| < 1e-9)

- A rigid (single-bone) vertex returns by `M_b^-1`, a rigid transform: **metal stays rigid by construction.**
- Two copies of a seam vertex carry bit-identical weights (canon 07), so they return to the same point: **seams stay closed.**
- A vertex whose blended transform is singular (bones turned ~180 deg against each other in one blend band) cannot be returned:
  the tool refuses and names the vertices; the fix is a smaller fit pose or a narrower band, never a pseudo-inverse.

**Wrong return (the falsifier):** `v_rest = Σ_b w_b M_b^-1 v_fit` (the blend of inverses). `inverse(Σ w A) ≠ Σ w inverse(A)`:
measured on golden C02 (two-bone tube, 60 deg at the elbow, 10 cm smoothstep band) the round trip misses by up to **10.8 mm on
46 blended vertices**, rigid vertices exact. `<codex-shelf>/task131-skin-reference-next-design.md` (2026-09-16) measured the same
class in Blender: blending inverse corrections failed native recovery by 1.118 units and rebinding a baked reference failed a
future pose by 1.461.

**Frame corrections cancel; geometry does not.** A per-joint right correction D applied to both bind and pose cancels:
`(P D)(R D)^-1 = P R^-1` (canon 01 C.4). So a bone-axis convention change is applied to the matrices, never baked into the mesh.

**Dual-quaternion skinning** (Kavan et al. 2008, "Geometric Skinning with Approximate Dual Quaternion Blending", ACM TOG) has a
different inverse; the return must invert the model the ENGINE evaluates. The UE armour pieces are linear-blend skinned
[UNVERIFIED for every UE skin-cache path — the validation engine leg settles it by reading `GetCPUSkinnedVertices`].

## C. Invariants

- **INV-04.1** Forward-skin(`v_rest`, fit pose) == `v_fit` within 1e-6 m for every vertex, or the vertex is refused by name.
- **INV-04.2** A metal part's return is one rigid transform (per part, by its single bone): its rest is a similarity of its source
  shell with the placement scale (canon 02 INV-02.2).
- **INV-04.3** The returned rest is never measured against itself: fidelity is against the ORIGINAL shell (canon 02 INV-02.3).
- **INV-04.4** Bind == native reference after return (`bind_mismatch` 0.01 cm / 0.01 deg / 1e-4 scale, Titan
  `armour_validate.py:414`; LT `pipeline/validate.py:84`).
- **INV-04.5** Custom shading normals are preserved by the same per-vertex linear map's inverse-transpose or refused; never
  recomputed silently (`<codex-shelf>/task131-skin-reference-next-design.md`: "full records must preserve or refuse").

## D. Failure modes already hit

| Date | What | Lesson | Source |
|---|---|---|---|
| 2026-09-28 | The fit-tool design wrote the return as `v_rest = Σ w_b Rest_b Posed_b^-1 v` and Titan implemented it (`equipment_fitpose.bind_return`) | blend of inverses; replaced by the exact inverse here | GENERATED-EQUIPMENT §7l (3); `equipment_fitpose.py:74-85` |
| 2026-09-16 | A baked T-reference mesh with blended inverse corrections lost native geometry (1.118 units) | change joint FRAMES (they cancel), never bake geometry through blended inverses | `<codex-shelf>/task131-skin-reference-next-design.md` |
| 2026-09-30 | A piece's bind with primary bone axis Y moved gear up to 28.8 cm although joint positions matched to 1e-4 cm | bind check is bone FRAMES, not positions | memory native-body-canonical-for-fit |

## E. Golden tests (`goldens/C02_inverse_lbs`)

| Test | Input | Expected | Falsifier |
|---|---|---|---|
| G04.1 exact return | `piece_fit_pose.obj` + `weights.json` (fit pose: B 60 deg about X at its head) | `v_rest` = `expected.json` `rest_vertices` within 1e-7 m; round trip < 1e-9 m | the blend of inverses: max 10.825 mm, 46 vertices > 1 mm |
| G04.2 rigid vertices | vertices with a single bone | exact under both methods (the error lives only in the band) | — |
| G04.3 singular refusal | w = (0.5, 0.5), B turned 180 deg | REFUSED, vertex named | a pseudo-inverse returns a point |
| G04.4 seam closure | C03 tube, positional weights, return from the twist | the ledger pairs' gap after return = 0 | per-part bones: 8.208 cm |

## F. Implementation gap

- LT `features/fit_bind.py:188-206` (`return_report`) computes a similarity residual of each metal part's evaluated REST mesh
  against the original; it performs no return (the module docstring :11 says so). The bound object is the piece AS PLACED
  (rest = placement), so a fit made at a posed body cannot leave in the native rest today.
- Titan `equipment_fitpose.py:74-85` implements the blend of inverses (B "wrong").
- Neither implementation refuses singular blends.

## G. Agent-facing tool contract — `lampway_fit_bind stage=return`

```json
{"stage": "return", "piece": "<piece>_fit", "pose": "pose.json (the fit pose)", "body": "fit_body package dir", "out_dir": "dir",
 "singular_det_min": 1e-9}
```
- Precondition: stage `weights` done at the fit pose; `pose.json` hash equals the one `weights` used.
- Refusals: `pose.json` changed since `weights` ("the weights were sampled at another pose: re-run stage weights");
  singular vertices (lists up to 50 ids with their bones and det, "reduce the fit pose at <bone> or narrow its blend band");
  metal part whose returned rest is not a similarity of its source within 0.5 mm (PROPOSED limit, "a metal part was blended:
  see canon 03 INV-03.2").
- Writes `<piece>_rest` (new object) + `return.json` `{round_trip_max_m, vertices, singular: [], per_metal_part: {scale, rms_mm,
  max_mm}, bind_check: {...}, pose_sha256, weights_sha256}`.

## H. Open questions

None for the captain. The [UNVERIFIED] engine skinning model is settled by the UE validation leg (canon 05).
