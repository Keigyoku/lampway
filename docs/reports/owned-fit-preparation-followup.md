<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Authored preparation and example-rig follow-up

The owned fit lane now exposes explicit `segment_mesh` authored FACE-part
preparation. It copies faces into disjoint part groups using supplied ownership,
retains original vertex/face IDs and original seam relationships, and preserves
source corner-normal vectors separately from measured native encoding
quantization. Bind planning validates the source, recipe, ownership and copied
topology before consuming that seam ledger. Moving a copied part cannot erase
an original same-shell seam or approve its opening.

The canonical example-rig route now replaces inherited armature bindings and
armature parenting on output copies, evaluates joint-inside rays at REST and
restores pose state on exceptions. Procedural weights come from the referenced
ray-sized elliptical body and nearest-polygon transfer, using child-owned
quarter-shorter-bone joint widths. They no longer use constant global nearest-
segment falloff.

Incremental isolated native checks passed: 31 preparation/segmentation/bind
controls and seven example-rig controls, followed by a combined 38-case run.
The old global falloff gave a synthetic finger vertex eleven unrelated groups;
the new method matches the independently executed Titan reference's single
finger influence. Duplicate binding, stale parenting, REST evaluation and
source-seam corruption controls retain their genuine pre-fix failures.
These checks execute current Python against an older diagnostic native binary;
they do not certify a rebuilt native application or physical acceptance.

The supplied-source preparation, placement, pose and plan execute, but weighting
still correctly refuses a soft sleeve contact with two differently anchored
rigid surfaces. The original contact and source IDs remain in private receipts.
The supplied example-rig route still refuses genuinely outside measured joints.
Neither source labels nor a successful algorithm control approve a cut, change
joint measurements, establish acceptable motion or waive an existing guard.
Those physical input/review dependencies remain explicit.

Portable verification helpers cover copied preparation, ten native UI cases,
independently referenced 342-row export and fresh UE import, actual cube controls
and intended native GPU backends. They retain exact source/build/input identity
checks and classify unexecuted local legs separately. Historical UE gray-control
failure and unmatched crash artifacts are unresolved evidence, not component
passes. The final packet must preserve original acceptance thresholds and
separately owned Agent Mode dependencies.

## Canonical seam and influence follow-up

The public fit_bind weights path previously did not call canon07's positional seam band. A genuine C03 control measured an 82.084836 mm seam gap and different duplicate rows before the correction. The existing plan accepts explicit source-bound flexible planar cut recipes through bind_overrides._seam_bands; complete contacts, working source/world/ownership identity, endpoint fields and disjoint flexible scope are checked before sampling/publication. The band uses the canonical primitive, precedes strict rigid fade and retains original source/opening and inverse gates. The original contact conflict is not waived by this method.

The public weight_transfer default previously capped native influences at four. Its default is now zero (no cap), preserving the source influences while positive requested limits remain explicit. Native current-Python controls cover the public defaults, positional C03 and refusal/identity boundaries. These controls use an older binary and do not establish matching native or original-asset physical acceptance. Complete local recipe/acceptance tooling is delivered separately; accepted source contact and physical review remain genuine inputs.
