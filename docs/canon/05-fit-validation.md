<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Canon 05 — Fit validation: receipts a number can stand on

Status: **CANONICAL for the receipts, the controls and the verdict rule; the LIMITS are PROPOSED (none adopted by the captain).**
Implemented by: Titan `tools/armour_validate.py` (pure) + `armour-validate.py` + `recipes/armour-validate-ue.py` (the UE leg:
the engine's own CPU skinning through a leader pose); Titan `seam_ledger.py`; LT `pipeline/validate.py` + `features/validate_pose.py`
(Blender leg); LT `features/workflows.py:251 rig_armor`, `features/rig.py:273 pose_test`; shelf grt `strain_*`/`gap_seam*` runs.

## A. Problem

Judge a bound piece in poses. Inputs: the bound piece (weights + its own bind), its ORIGINAL shell (pre-fit, own frame, same
vertex identities or a source map), per-part roles, the source seam ledger, the native body package (sidecar weights, bind
table), a pose set, a limits file with `status: proposed|adopted`. Output: per pose x part receipts and one verdict per row.

## B. Method — the receipts (each per part, per pose)

1. **Source fidelity** (metal, once): similarity of the original shell onto the placed rest (canon 02, scale recorded).
2. **Pose rigidity** (metal): rigid fit, scale FIXED, of the frozen rest onto the posed part; `rigid_residual_mm` max and rms.
3. **Edge strain**: `|l_posed / l_rest - 1|` per edge vs the frozen rest; report p95 and max. A zero-length rest edge is refused.
   Leather keeps the tear rule as a diagnostic: an edge > 2x AND > 1 cm (memory metal-never-blended "Keep the tear rule for leather").
4. **Seam gap**: for every pair in the **source ledger** (vertex pairs with exactly equal source coordinates across parts:
   `titan.frozen-seam-ledger/1`, `coverage.origin = source-exact-coordinate-groups`), the distance in the pose; count pairs open
   over 2 mm and the max (Titan `seam_ledger.py:126 measure`, threshold 0.2 cm). Membership comes from the ledger, never from
   distances in an already deformed mesh (`seam_ledger.py:3`).
5. **Crossings**, both instruments, both directions: `surface_crossings` = piece edges crossing body triangles and body edges
   crossing piece triangles (Titan `segment_box_overlap` pre-filter, `armour_validate.py:529`); `inside_vertices` = piece vertices
   with body winding number > 0.5 (canon 15). Limit (proposed): body crossings 0.
6. **Positive crossing control**: push the piece into the skin where it is NEAREST, by the distance to the skin plus
   `min(1 cm, half the piece's extent along the push)` (Titan `armour_validate.py:548 control_shift`). The instrument must see
   crossings; if it does not, the run is UNPROVEN (a buried rivet crosses no surface: golden C14).
7. **Bind check**: the piece's own reference pose vs the native bind, bone by bone (0.01 cm, 0.01 deg, scale 1e-4).
8. **Influence fidelity**: every vertex keeps every source influence and no weight moves more than one 8-bit step (1/255)
   across export/import (Titan `armour_validate.py:176 influence_check`); a mesh whose rest does not match its source within
   0.01 cm is UNMATCHED, not evidence.
9. **Pose expectations, measured before anything else**: each pose declares e.g. `{joint: hand_r, along: forward, min_cm: 5}` or
   `{joint: middle_03_r, closer_to: thigh_r, min_cm: 0.3}`; the posed JOINTS are measured; a failing expectation REFUSES the pose
   (Titan `armour_validate.py:672 check_expect`). Axes are named from the body's joints (`up`, `forward` = foot_l->ball_l levelled,
   `lateral`, `{line:[a,b]}`, `{perp:[a,b],to:axis}`) so a pose means the same on every MetaHuman (`recipes/armour-poses.json`).
10. **Judge**: per role against the declared limits plus the body limits; a role or metric the limits do not cover is UNVERIFIED,
    never PASS; verdicts PASS | FAIL | UNVERIFIED | REFUSED | UNPROVEN; the limits' status rides on every verdict; `ok` only when
    nothing is FAIL/UNVERIFIED/UNPROVEN and either the limits are adopted or the note says "PASS under proposed limits".

**Pose sources:** authored (`armour-poses.json`: rest, wrist ±30, elbow 70, finger curls 1/3, 1/2, 2/3, 1 at 80/95/60 deg about
the knuckle line), `closest` (canon 08's `pose.json`), captured (the body's post-process graph state replayed bone by bone WITH
scale, `captured_pose`), and existing AnimSequence frames (`sequence_pose_specs`). MetaHuman correctives follow their parents in
authored poses; only captured poses carry the graph state (the receipt says which).

**Engines:** `engine` (UE editor, leader pose, `GetCPUSkinnedVertices`: what the game draws — authoritative) and `blender`
(fast, local: skin the NATIVE body from the sidecar with all influences, never the 4-influence GLB). One receipt schema for both.

## C. Invariants

- **INV-05.1** Never measure fidelity against a posed or baked rest (canon 02 INV-02.3).
- **INV-05.2** Never refit scale per pose.
- **INV-05.3** A verdict is never stronger than its limits; no limits -> UNVERIFIED.
- **INV-05.4** A control that cannot fail makes the run UNPROVEN, not PASS ("write the check, not the sentence").
- **INV-05.5** A wrong-sign pose is refused, never measured — the expectation is checked on posed JOINT positions, not on the
  commanded angle (an expectation that reads back its own command cannot fail).
- **INV-05.6** Poses are named from joints, never Euler angles on a rig's local axes (local axes differ between rigs and between
  import conventions, canon 01 C.1).
- **INV-05.7** Position agreement is not weight agreement: influence fidelity is its own check (Myth, 2026-09-30).

## D. Failure modes already hit

| Date | What | Lesson | Source |
|---|---|---|---|
| 2026-09-30 | Tear rule read 0 while metal strained 15–19 % (p95) in a ±30 deg wrist sweep | metal has its own receipts | memory metal-never-blended |
| 2026-09-30 | First UE run: all four curls REFUSED on their expect (curl axis pinky->index bent fingers back) | expectations before measurement; axis = index_01 -> pinky_01 | `recipes/armour-poses.json` |
| 2026-09-30 | run25: a 0.2 cm rivet pushed 1 cm past the skin crossed nothing; the control would have been blind | cap the push at half the piece's extent | `armour_validate.py:548-563` |
| 2026-09-30 | A body-forward control push slid a dorsal hand rivet along the hand | push along the CLOSEST pair, never a fixed direction | same |
| 2026-10-06 | MetaTailor MT-1: an authored 4.0 mm cap-to-leather gap closed to 0.03 mm (pinky_2) at bind and 0.00 mm in a fist; nothing in its output reports it | seam gaps are measured against the source ledger, per part pair (GMT.2) | `goldens/metatailor` MT-1 |
| 2026-09-29 | Per-part torn-edge metric was blind to seams opening 8.7 cm | seam gap from the ledger | memory seams-need-positional-weights |
| 2026-09-24 | Weight read-back refused 0.090 vs 1.4e-05 on two identical bracers: saved and written vertices matched by position rounded to 0.001 cm, one float32 vertex crossed a rounding boundary | match within a tolerance (0.002 cm), never by rounded key | GENERATED-EQUIPMENT §7h |
| 2026-09-29 | Seam band measured on the rigged warrior: 5 cm positional blend cut seam drift p95 from 2.47 to 0.27 cm (walk), pairs over 2 cm 5.62 % -> 1.24 % | the seam band is a positional weight, measured by the ledger | `<shelf-scratch>/grt/gap_seam0.log`, `gap_seam5all.log` |

## E. Golden tests

| Test | Fixture | Expected | Falsifier |
|---|---|---|---|
| G05.1 breathing | `C01_rigid` `Q_breathe_1pct` | rigid residual >= 1.95 mm -> FAIL under 0.5 mm | per-pose scale fit -> 0 -> PASS |
| G05.2 seam ledger | `C03_seam_tube` | 32 ledger pairs; per-part bones: max 8.208 cm, 32 pairs over 2 mm; positional: 0 | a seam set built from distances in the posed mesh |
| G05.3 crossing control | `C14_controls` | capped push: >= 4 surface crossings; uncapped: 0 -> UNPROVEN | uncapped 1 cm control reported as ok |
| G05.4 crossing sign | `C05_clearance` spike | outside (winding 0) | nearest-face normal reports inside |
| G05.5 expectation | `C07_pose_solve` rig: `+20 deg lower` must move the elbow down by >= 2 cm | measured on the posed joint | negate the axis: REFUSED; an expectation that checks the commanded Euler angle passes the negated axis |
| G05.6 cloth without limits | any cloth part | UNVERIFIED, `ok=false` | a default cloth limit inferred by the tool |

## F. Implementation gap (Lampway `b806617f`)

1. **The expectation check is a tautology.** LT `features/validate_pose.py:83-88` reads back the pose bone's own
   `rotation_euler` (the angle it just set) and compares it with `min_deg`; it can only fail when the pose author contradicts
   himself (test `test_wave3_validate.py` "wrong_way" passes only because rotate -60 contradicts expect min 20). Canon: measure
   posed joint displacement (`along`) or approach (`closer_to`) as Titan does.
2. **Poses are Euler angles on local axes** (LT `validate_pose.py:28-42`; `workflows.py:23-32` WIKI8 "measured on the
   algorithmic rig"). On the MetaHuman these angles mean different motions. Port the joint-named axis grammar.
3. **Seams from proximity, not the ledger.** LT `rig.py:233-248 _seam_pairs` pairs vertices of different index-shells within
   2 cm at rest; it is not the source ledger and counts any neighbouring shell (a strap over a plate) as a seam.
4. **Crossings one way, signed by one face normal.** LT `validate_pose.py:94-100` counts piece vertices whose nearest body face
   normal says inside (wrong at sharp features, canon 15) and never counts body-through-piece crossings.
5. **The control is uncapped and per-vertex.** LT `validate_pose.py:118-129` pushes one vertex by 1 cm against its nearest normal.
6. **Limits disagree** (see H): LT `pipeline/validate.py:17` PROPOSED metal `rigid_max_mm 1.0`, `strain_max_pct 1.0`,
   `seam_gap_mm 1.0` vs Titan `recipes/armour-limits.json` `rigid_max_mm 0.5`, `strain_p95 0.01`; LT judges strain MAX, Titan p95.
7. **rest_fidelity is whole-mesh** (LT `validate_pose.py:69`), not per metal part.
8. **No engine leg, no captured poses** (LT `<specs>/STATUS.md` fit_validate row).
9. LT `workflows.py:274` `rig_armor` accepts deforming pieces at max edge stretch < 1.35 and a seam limit of 1 cm
   (`SEAM_LIMIT_M`, :34) — neither number has a source.

## G. Agent-facing tool contract — `lampway_fit_validate`

```json
{"stage": "plan|measure|judge|report", "engine": "blender|engine", "piece": "string", "bound": "object|fbx",
 "original": "source shell (REQUIRED)", "roles": {"part": "metal|leather|cloth|embroidery"}, "seam_ledger": "titan.frozen-seam-ledger/1",
 "body": "fit_body package dir", "poses": ["rest", "closest", "<armour-poses name>", "captured:<name>@on"],
 "limits": "titan.armour-limits/1 shape", "project": "uproject (engine leg)", "runner": "box command (engine leg)"}
```
Refusals: no original ("measuring against a baked rest hides the distortion"); no roles; no ledger -> seam row UNVERIFIED (not
refused) with "build the ledger from the source mesh"; `bind_check` not ok -> REFUSED ("leader-driven validation is meaningless");
a pose whose expectation fails -> that pose REFUSED; engine leg without project/runner -> the box command.
Receipt: `titan.armour-validation/1` (one reader for both engines): per pose `{expect, pieces: {part: {role, rigid_residual_mm,
rigid_rms_mm, strain_p95, strain_max, seam: {open_over_2mm, max_cm}, surface_crossings, inside_vertices, judge}}}`, plus
`rest_fidelity` per metal part, `crossing_control`, `bind_check`, `influence_fidelity`, `limits` verbatim, `summary`.

## H. Decisions owed by the captain

1. **Adopt the metal limits?** Proposed (Titan file, agreed with Myth 2026-09-30): rigid residual < 0.5 mm, strain p95 < 1 %,
   body crossings 0. Lampway's placeholders (1.0 mm, strain max 1 %, seam 1 mm) are superseded by this canon until he rules.
2. **Leather / cloth / embroidery limits.** The older authored `fit-profiles.json` says leather 8 %, cloth 25 %, fur 1 % (p95
   edge change); `armour-limits.json` deliberately has none. Canon: UNVERIFIED until he declares.
3. **Seam limit.** The ledger counts pairs over 2 mm; no acceptance limit exists (`rig_armor` uses an unsourced 1 cm).
