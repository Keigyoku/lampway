<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# AC65 decision prerequisites (2026-10-07)

AC65 names six decisions. They are not normalization decisions D1–D6: only
pair scale group and facing margin correspond to normalization D4 and D6.
The canon supplies working engines and some proposals, but does not contain a
complete accepted numerical default table for all six. Explicit candidate
measurements can proceed; successful execution alone cannot select defaults.

| AC65 decision | Current implementation and recommendation | Evidence needed before a default can be adopted |
|---|---|---|
| Facing margin (normalization D6) | `features/normalize.py` measures all four cardinal yaws against the approved Front plate; `canon_asset.SETTINGS.facing_margin` remains unset. Use actual approved per-piece plates and the shared native-aspect loader to measure best-minus-second IoU gaps. No number is currently recommended by canon. | Original approved plates, declared correct-facing labels, repeatability under the documented loader/render settings, and correct/wrong/tied cases establishing a separation margin. Keep the symmetric tie and unchanged-geometry falsifiers in `test_canon_normalize_facing.py`, then record the justified value and default-path golden. |
| Pair scale group (normalization D4) | `pipeline/fit_place.py` implements explicit `common` and `per_side`, preserving identities and inverse maps. Compare both on actual asymmetric boots/gauntlets and retain one proper similarity per rigid group. Omitted mode retains the historical calculation and an unresolved-decision marker; it is not a canonical common-scale ruling. | Actual side-specific source-part identities and body-relative comparison of proportions, placement, all-vertex clearance and rest/posed rigid fidelity. Synthetic asymmetric tubes prove independent routing, not the physical choice. `test_canon_pair_scale.py` retains both alternatives and scene replay. |
| Glove pose and bind | Use the implemented shared engines with independently recorded plate labels, roles, native body joints and native-sidecar weights. `pipeline/fit_glove.py` runs pose and bind/return; no automatic mirror-label algorithm is required for an independently labelled glove. Default gauntlet DOFs still depend on the next decision. | Original labelled glove geometry on each side, source-part fidelity, a justified complete hand/forearm pose table and coupled curl-TO targets, bind-at-fit-pose/return/validate receipts, and rigid-cap plus seam falsifiers. `test_wave3_glove_state.py`, `test_canon_finger_targets.py`, `test_canon_item4_tools.py` and `test_canon_g03_chain.py` prove engines on synthetic inputs. |
| Fit-pose degrees of freedom | `posing.py` has canonical chest and accepted complete helmet tables. `pipeline/decision_tables.py` supplies bounded experimental waist, boots and gauntlets tables, with explicit anatomical sign expectations and region thresholds. Measure these candidates rather than treating their experimental envelopes as accepted defaults. | Actual placed pieces, both side identities, joints, reversible pose grammar, sign checks and sensitivity of remaining ranges/steps/regions to natural pose and clearance. `test_canon_item7_pose.py` and `test_canon_finger_targets.py` pin the solver; canon08 still lacks three complete accepted numerical tables. |
| Collar depth | `features/opening.py` accepts explicit gasket flange depth and renders variants; canon06 proposes 10/20/35mm for review, without accepting one. `pipeline/decision_measure.py` has a `collar` variant job. Preserve the keep/gasket/delete decision and material role. | Actual posed opening descriptors, body visibility/through-depth, matching camera views for all proposed variants, flange/lip geometry and manifold/winding checks. The selected depth needs a ruling grounded in those views; C12 must retain no-flange and zero-clearance falsifiers. |
| Boots scale anchor | `pipeline/fit_place.py` supports explicit shaft `width`, knee `height`, or `foot` length; canon09 does not prefer one. The measurement runner compares all three. Height now measures knee-to-sole length; body/world translation cannot change its scale. Re-run any earlier height candidates on this corrected source. | Actual approved boot/body inputs, body-relative fixed-bound views, knee/sole/foot relationships, per-side scales, all-vertex signed clearance and relevant pose metrics. `test_boot_height_translation.py` pins body-only and both-input translation and the original sole-at-zero result. Physical owner views must identify current source hashes; the 4cm sole-band thickness remains a separate calibration limitation. |

The concrete entry point is `scripts/lampway/measure_fit_decisions.py`, backed by
`pipeline/decision_measure.py`: `facing`, `pair`, `boots`, `pose` and `collar`
jobs. Glove labels/bind use `api.fit_glove` with their recorded independent
inputs. Body-relative pair/boots jobs require explicit body context, fixed world
bounds and acceptance limits; they distinguish all-vertex clearance from
sampled distance diagnostics and refuse ambiguous opening bands. They do not
measure every full-chain surface crossing, innermost gap or hideable-skin clause.

Owner scenes, raw matrices and measurements remain external and read-only.
Before a recommendation becomes a default, retain its private input/source
hashes and receipts, write the accepted value into the owning canon/settings,
add default-path goldens and wrong-choice falsifiers, then rerun the actual
original inputs. Until that evidence exists, keep AC65 open rather than deriving
numbers from the criterion's phrase “recommended values.”
