<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# AC65 authorized starting defaults (2026-10-07)

The captain explicitly authorized judgment using the supplied MetaHumanBase and
gear references, with untested results labelled. This supersedes the earlier
measurement-prerequisites-only recommendation. These six decisions are adopted
starting defaults, **physically untested**. They do not establish acceptance of
an original piece, native engine parity, or an independently measured optimum.
Only pair scale and facing margin correspond to normalization D4 and D6.

| AC65 decision | Chosen default and rationale | Technical evidence and remaining physical work |
|---|---|---|
| Facing margin (D6) | `0.05` best-minus-second silhouette IoU: require five IoU points of separation; a symmetric tie still refuses. | `test_ac65_defaults.py` exercises the omitted-margin native plate path and untested receipt; `test_canon_normalize_facing.py` retains rotation/tie controls. Approved original plates and correct/wrong-facing separation remain unmeasured. |
| Pair scale group (D4) | `per_side`: retain one proper, reversible similarity per rigid side. The reference shins' reported scales 0.887/0.853 motivate preserving asymmetry; explicit `common` remains available. | Default-path asymmetric tubes retain identities and inverse error below 1e-9 m; `test_canon_pair_scale.py` retains both modes. These inputs do not prove physical left/right proportions or clearance. |
| Glove pose and bind | Independently supplied labels and roles, native joint keypoints, the complete side-specific gauntlet table below, and shared bind-at-fit-pose/return/validate engines. No inferred mirror labels. | Default tests cover unlabelled refusal and independently labelled right-side routing; finger-target and glove-state tests retain curl/role controls. Original glove geometry, rigid-cap fidelity, seams and full bind/return acceptance remain untested. |
| Fit-pose DOFs | Adopt the complete bounded waist, boots and gauntlets tables in canon08 B.8; keep chest and helmet tables. All new region thresholds are 0.002 m diagnostics using the existing torso/neck sensitivity. | Default tests cover both sides, actual synthetic sweeps, nonempty regions and reversed-sign refusal. Bounds/steps are judgment choices from the prior candidates; the threshold is not a new physical acceptance bar. Natural pose and regional sensitivity need original-input review. |
| Collar depth | `20 mm`: middle of the proposed 10/20/35 mm variants, retaining a formed collar while limiting intrusion. Explicit flange depth still overrides it. | Default-path opening tests and existing manifold/winding/clearance controls are technical proof. Actual posed visibility, through-depth, lip geometry and opening-specific keep/gasket/delete decisions remain untested. |
| Boots scale anchor | `width`: shaft span with wear clearance follows the enclosure rule. Prior height left the foot 8% short; foot scaling placed the shaft 118 mm above the knee. Width avoids choosing either length over enclosure. | Default tests compare omitted anchor with explicit width and reject unknown anchors. Height remains explicit and sole-relative with translation controls. Original shaft/foot/knee relationships, pose clearance and the 4 cm sole-band calibration remain untested. |

`canon_asset.SETTINGS` records each numeric/placement default's value, ruling date,
source, rationale and `physical_status: untested`. `decision_tables.adopted`
records the same proof limit for the new pose tables. Explicit measurement
candidates remain experimental; a successful candidate run alone does not change
these defaults. The maintained tests are implementation checks, not physical
acceptance; the worker's frozen native selection passed 45 tests (one warning), including 20 default cases, after the initial defaults run failed nine and passed one. This is a selected-suite receipt, not a full-suite or original-input acceptance claim. The implementation checkpoint retains the exact binary/source provenance.

Generated golden `C15_ac65_defaults/case.json` pins the complete values and both-side tables. Its13 checks retain missing-default, wrong-side, wrong-sign and false-physical-promotion falsifiers plus six reversible sign probes. Production settings/tables are compared directly to this generated case.

The supplied Drive documentary references have SHA-256
`8cf58eb66e7a52bf1e1f5b8e60ab8234bfa96aeb4937a3eb63ffb4bb4a9c89df`
(MetaHumanBase provenance) and
`1ac36dbaae4fbff8046be4c3c102a0a26fbe44f7a6727a47941cef753e575e4d`
(modular gear provenance). They distinguish legacy body export/import limits
and authored gear pose/shape channels; they do not supply physical measurements
for these defaults. The reported Drive search found documentary references,
not raw MetaHumanBase or gear files. No original asset fit was inferred from the
references, and private identities, paths and asset bytes are omitted here.

For physical validation use `scripts/lampway/measure_fit_decisions.py` with
recorded original inputs, source hashes and fixed body-relative bounds. It
provides facing, pair, boots, pose and collar jobs; glove labels/bind use
`api.fit_glove`. All-vertex clearance remains distinct from sampled diagnostics;
the runner does not measure every full-chain crossing, innermost gap or
hideable-skin clause. Keep original assets and detailed receipts private.
