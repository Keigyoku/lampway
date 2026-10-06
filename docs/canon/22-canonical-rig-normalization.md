<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Canon 22 — Canonical rig and animation normalization (the O36 interchange)

Status: **CANONICAL** for sampled animation (form, maths, exactness rules: a decision of the captain, implemented and reviewed on
the Titan side); **DRAFT** for skin, morph and mesh coupling (Titan Task 131 open). This page is the maths STATUS row O36 assigns
to the canon. Sources: Titan `adr/0012-normalize-first.md` (D86, "Proposed canonical form v1", Amendment A1 2026-09-16), Titan
`tools/animation_canon.py` (pure, 439 lines), `tools/canon.py` (unrigged meshes), `tools/skin_bind.py` (explicit bind skinning);
the codex-1 shelf's Task 130/131/37 records (`<codex-shelf>/review-task130-canonical-converter-*.md`,
`issue33-task131-*.md`, `issue33-task37-pose-normalize-evidence.md`, `blocked-slice-33-normalize-owner.md` with the captain's
ruling "the rig-conversion and normalization is all external. The input the Game takes is the output from the external tool").

## A. Problem

The same rig and its motion travel between Blender, Unreal and CC5. A bone NAME match does not establish matching local axes or
reference posture (ADR 0012 Context: a female idle folded although Blender and UE agreed with each other; the source upper-arm
drop was 49.541 deg against the target's 29.739 deg and the target root carried a -90 deg X basis). The fix is one deterministic
`normalize <input> -> <canonical>` step every converter runs before domain work, with world adapters (`to-ue`, `to-blender`,
`to-cc`) the only code that knows a world's conventions.

## B. Method

1. **Canonical space** (ADR 0012 v1): left-handed, +X forward, +Y right, +Z up, centimetres, identity root basis; matrices act on
   column vectors; quaternions serialized Hamilton `(x, y, z, w)`. Adapters own handedness reflection and winding reversal.
2. **Profile** = a COMPLETE ordered per-bone table of the native rig: bind and reference transforms (component space and local),
   the adapter basis quaternion `b`, `centimeters_per_unit`, the canonical T reference; pinned by sha256 and re-validated by
   rebuilding it (`animation_canon.make_profile`, `:188-232`; `_profile` refuses a profile that does not rebuild byte-equal,
   `:243-251`). The root's canonical reference sits at the origin.
3. **Reference alignment** is processing data, never a skeleton edit: authored rules rotate named chains (`bone`, its direct
   `toward` child, a `direction`) by the minimal rotation, keeping every local offset (`align_reference`, `:155-185`; antiparallel
   directions refuse — they need an authored axis).
4. **Normalize a sample**: `q_c = b * q_native * q_ref^-1 * b^-1` (the bone's rotation RELATIVE to the profile's reference,
   expressed in canonical space), `t_c = units * rotate(b, t_native)` (`normalize`, `:287-313`). Inverse (`adapt`, `:328-342`):
   `q_native = b^-1 * q_c * b * q_ref`, `t_native = rotate(b^-1, t_c) / units`, onto the ORIGINAL native profile only.
5. **Numbers**: quaternions normalized with a fixed sign (the last non-zero component positive, `qnorm`, `:43-51`); every number
   rounded to 9 decimals; scale UNIFORM only (non-uniform refuses: tolerance 1e-5, canonical value the mean at 6 decimals,
   `:77-86`) — the same refusal canon 18 reaches for animated armatures.
6. **Time**: 30 fps rational sample times plus the exact terminal time, never overshooting (`sample_times`, `:264-270`);
   duration bounded 0..3600 s; samples must carry EXACTLY the profile's bones (`_samples`, `:273-284`).
7. **Encoding**: JSON with sorted keys, compact separators, UTF-8, NaN refused; the payload's sha256 excludes paths and execution
   metadata (`encode`/`digest`, `:17-23`); no timestamps or random ids; normalizing canonical input is idempotent.
8. **Retarget between profiles** (`retarget`, `:368-439`): exhaustive rules — a one-to-one `map` covering every source bone,
   `reference_follow` for every unmapped target bone, a positive `translation_scales` entry per mapped bone, `anchors` (a helper's
   translation re-derived from an earlier target bone); roots map to roots. The target's world rotation is the source's
   canonical (reference-relative) rotation applied to the target's reference — the same rule as canon 19 B.1
   (`W_t = W_s R_s^-1 R_t`), here in canonical space.
9. **Exactness (A1)**: byte equality is REQUIRED for pure operations (normalize -> adapt -> normalize, idempotent publication,
   repeated extraction of the same native artifact). An independently emitted native artifact is judged by 0.1 cm, 0.1 deg,
   1e-5 scale plus the exact roster/identity/channel rules and unchanged Skeleton and source hashes: Unreal narrows to float
   before it stores (`AnimSequencerController.cpp:1678-1693`, float Euler keys from `:2760`), measured 1.78e-5 cm, 2.76e-5 deg,
   4.77e-8 scale on the 161 -> 353-bone transfer. Both hashes are always recorded; nothing different is ever called identical.
10. **Skin** (DRAFT): finite non-negative weights on named joints, deterministic normalization to an exact sum, NO implicit
    influence cap; binds and vertex offsets transform together (ADR 0012 v1; `skin_bind.capture/rebind/evaluate`,
    `:123-228`, `P * inverse(B)`).

## C. Invariants

- **INV-22.1** `adapt(normalize(x)) == x` to the 9-decimal encoding; `normalize(normalize(x))` byte-equal.
- **INV-22.2** A profile is complete (every bone, parents before children, one root) and rebuilds to its own bytes.
- **INV-22.3** No native skeleton is edited; adapt targets the original profile only (D84).
- **INV-22.4** Unknown conventions refuse; nothing is guessed (units, basis, reference, mapping).
- **INV-22.5** Every bone and every channel is accounted for; nothing is dropped silently.

## D. Failure modes already hit

| Date | What | Lesson | Source |
|---|---|---|---|
| 2026-09-06 | Female idle folded although Blender and UE agreed; reskin moved vertices up to 51.536 cm on an intact body | agreement between runtimes is not correctness: normalize first | Titan ADR 0012 Context |
| 2026-09-16 | Native emission cannot return nine-decimal quaternions byte-identical (UE stores floats) | exact where achievable, physical bars for native emission | ADR 0012 A1 |
| 2026-09-16 | Retarget dropped scale: root 2 became 1, hand 1.5 became 1 | carry the animated/reference-local scale ratio | `<codex-shelf>/issue33-task131-scale-comment.md` |
| 2026-09-15 | A canonical hash changed on round trip (0.295336889 -> 0.29533689) | full intermediate precision, stable 9-decimal quaternions | `<codex-shelf>/issue33-task131-roundtrip-comment.md` |
| 2026-09-16 | Identity retarget numerically close, NOT byte-identical (5.8e-8 cm, 1.6e-7 deg) | never turn closeness into identity | `<codex-shelf>/review-task130-canonical-converter-package.md` |

## E. Golden tests

| Test | Fixture | Expected | Falsifier |
|---|---|---|---|
| G22.1 round trip (Titan suite, to port) | a 3-bone profile, 31 samples over 1 s | `adapt(normalize)` equal to 9 decimals; repeat bytes equal | dropping the reference term `q_ref^-1` |
| G22.2 retarget agreement | R04's chains as two profiles | canonical retarget equals canon 19's `W_s R_s^-1 R_t` | local copy (R04: 55.7 deg) |
| G22.3 scale refusal | a sample with scale (1, 1.2, 1) | refused | quaternion maths on a sheared basis |
| G22.4 time schedule | duration 1.05 s | 33 samples: 0/30 .. 31/30 plus the terminal 21/20 | overshooting to 32/30 |

## F. Implementation gap

- Lampway (`4e9001c7`): none of this exists; STATUS row O36 is an orphan. `animation_retarget` overlaps B.8 only and writes
  Blender actions, not a canonical artifact. The maths exists, reviewed, in Titan's pure Python modules (`animation_canon.py`,
  `canon.py`, `skin_bind.py`), which are the reference implementation for the port.

## G. Agent-facing tool contract — `lampway_rig_convert` (spec: `rig_tools/rig_convert.md`, the O36 build)

```json
{"verb": "profile|normalize|adapt|retarget|compare|verify", "input": "file", "profile": "profile.json", "target_profile": "profile.json",
 "rules": "rules.json", "out": "file"}
```
Refusals: an incomplete or non-rebuilding profile; non-uniform scale; a sample schedule that is not 30 fps rational + terminal;
an incomplete retarget map; an existing different output (publication never overwrites). Receipt: input, profile, rules, output
sha256s; owner module versions; for `verify`, both hashes and every row over the A1 bars.

## H. Decisions owed by the captain

1. Port Titan's `animation_canon.py`, `canon.py`, `skin_bind.py` into Lampway (same owner; Lampway is GPL-3.0-or-later) or call
   them as an external tool from Lampway? The ruling "all external" names the tool's place, not which repository holds it.
2. Lampway's in-Blender working frame (canon 01: right-handed, Z up, faces -Y, metres) and this interchange frame both stand;
   `to-blender` maps between them. Confirm that layering (REPORT contradiction R-1).
