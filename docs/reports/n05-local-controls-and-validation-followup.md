<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Complete N05 controls and current validation follow-up

This increment starts from PR1 source `6b99d1730e10db1aec790658b0e09d4c564d180d` on `lp/mcp-wrapper-migration-main-20261007-v2`. It implements bounded capture/output and validation corrections from the complete owner-local N05 evidence and Issue2 G30/G32/G34–G36. It does not certify the historical renderer cause, a successful current GPU capture or complete physical acceptance.

## Source-bound actual N05 evidence

The complete supplied archive is 262,842 bytes with SHA256 `8cf9a87f31eab95087806f307b70d71fd9e7f9ac3b18418c765900952a4782fc`. ZIP CRC passes; its captured generator bytes exactly match source6b99, SHA256 `b5e8dc28cd433af02b14ba7f9d41d52db6cbd55aa6409a3f8a90a5e478a8ac1c`. Logs, project profiles and original capture files remain private and are excluded from tracked changes.

UE5.8.2 changelist56702186 used Vulkan SM5 on AMD Ryzen7 7700X integrated graphics, RADV/Mesa26.2.2. The typed postprocess receipt reads tone amount1→0 and gamut expansion1→0, then verifies normal settings restored. Actual RGB byte controls are:

| Input linear RGB | Normal display | Disabled tone/gamut display |
| --- | --- | --- |
| black0 | (0,0,0) | (0,0,0) |
| gray0.18 | (42,42,42) | (42,42,42) |
| red(1,0,0) | (216,0,0) | (255,0,0) |
| white4 | (241,241,241) | (255,255,255) |

All raw input controls meet the existing0.005 limit. The unchanged gray display correctly triggers the strict greater-than1/255 refusal. Red and white change, so the record does not establish globally ignored settings. The run records neither actual target sRGB/gamma state nor paired byte/raw display readback; gamma, render history and a gray coincidence remain unproved hypotheses. No cube or accepted sidecar was published.

## Implemented capture corrections

The generator's stated output is encoded sRGB display data. The old route requested generic RTF_RGBA8 without reading its encoding state; the main capability report instead advertised FINAL_TONE_CURVE_HDR. The current route requests explicit RTF_RGBA8_SRGB and both probes describe the actual FINAL_COLOR_LDR/color-readback pipeline separately from linear HDR input controls.

Before sampling, target admission verifies exact typed native format, boolean sRGB/legacy flags, integer8×8 dimensions and finite disabled custom gamma. Actual capture blend weight and frame/movement flags are read back. Optional history/camera-cut flags are recorded only if available. Each normal/disabled display control receives both color-byte and raw-float reads from the same completed GPU capture; there is no extra scene capture. Typed target/component provenance reaches durable controls and completed sidecars.

The unchanged gray guard remains in both capture and publication, and the twelve preliminary capture count remains unchanged. Raw display diagnostics and different red/white outputs cannot substitute for gray acceptance. Input shaper inversion remains the only computed input transform; no CPU tone mapper, fabricated cube, renderer-source copy or GPU-setting exception is added.

Epic explicitly documents [RTF_RGBA8_SRGB](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/TextureRenderTargetFormat?application_version=5.6) as sRGB-encoded RGB. The [readback APIs](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/RenderingLibrary?application_version=5.6) distinguish assumed LDR sRGB byte output from raw values. This substantiates the explicit output contract and new observations, not the historical initialized flag or an actual current gray PASS. A fresh owner-local controls-only capture and then all32,768 rows remain required. The [handoff](../../scripts/lampway/ue_cube_generator_capture_handoff.md) gives exact unchanged request/run/validation commands.

## Other local validation corrections

G32/G34 reference admission now declares websocket-client, explicit private scratch/chest inputs and original V3 plates, actual authored SVG rendering, and executable chrome-headless-shell. Browser version alone is insufficient: a bounded disposable blank-page startup uses unchanged production flags and preserves sandbox/worker containment. Outer launcher keyring overrides are removed only from the isolated suite environment; original-fixture snapshots remain enforced.

The local SVG failure is measured: ImageMagick could not find its rsvg-convert delegate. With the actual rasterizer on PATH, committed splash/icon controls pass without artwork changes. The downloaded official headless-shell reports its version but fails actual cloud startup because its sandbox is unavailable. Current complete-suite preflight explicitly refuses that environment; no sandbox disabling or OS/privilege change was performed.

G35's synthetic three-bone rig used an unstamped native twist-helper name, so canonical plan correctly refused incomplete verified topology before weights. Generic region/nearest-ancestor controls now use an anatomical descendant with identical coordinates, ancestry and source weights, and assert planning success. An explicit original partial-native-helper refusal keeps topology admission strict and verifies no state/object publication. The genuine far-zero-row refusal and all geometric weight assertions remain.

G36's histogram already includes zero-influence vertices. The public Bunny chain counted those rows again through unweighted_vertices. It now independently compares the full histogram and zero bin against actual written rows, and checks finite/nonnegative normalized-or-empty weights before all existing output acceptance, source-hash and lineage assertions. The actual pinned Stanford Bunny preserves all source bytes and the named five-hole contract. Its output still has18 unweighted vertices; this source-identity/default acceptance is not complete skin quality or original Tripo acceptance.

## Measured controls and remaining acceptance

The meaningful pre-fix failures were observed: wrong target format in complete native-shaped capture orchestration; inconsistent probe reporting/missing surface properties; unadmitted environment/outer keyring; three native plan refusals; and eighteen Bunny rows counted twice. Current focused UE controls pass101 cases, including same-capture readback, typed encoding/state plants, selective-gray refusal, restoration, cleanup and sidecar revocation. These are synthetic control results, not renderer proof.

Prerequisite/harness tests pass55 cases; the earlier actual committed-art/harness selection passes78, and three original chest/parts/palette cases pass. Selections overlap and are not added into an aggregate. Six G35 native cases pass; the complete public Bunny chain plus unchanged named-hole case pass2, and three independent corrupted-accounting/weight plants are rejected. Native runs used current Python on the identified older diagnostic binary, SHA256 `0e220513b65610fd017fbae8185e512cd7516fbd8ac01ad867b27f245d297e62`; they are not matching-native full-gate acceptance.

The supplied complete local client gate remains historical RED with77 failures/19 errors, including all54 prior baseline identities and42 additional identities. Corrected scoped admission and native tests do not erase that whole-gate result. Current source/GPU gray and full-cube acceptance, matching-native complete-suite/UI/hardware checks, genuine live/human operations and I05 physical motion remain separate open obligations. No baseline, deadline, numeric bar or worker security assertion is weakened. Post-merge follow-ups retain their original timing and owners.

## Inherited fixture reconciliation and shared interfaces

Full collection of the original54 failing identities now confirms52 PASS and two FAIL, with zero ERROR. The shared chat/cat selection passes443 cases. Cached chat modules had retained another collection-time bpy double; the fixture now restores those globals for its own lifetime. Scene doubles model Blender's separate custom-property mapping, teardown uses the current dictionary registry, and todo/cost doubles accept and positively assert the forwarded scene/session. Old-fixture restoration and custom-property plants fail, while current controls pass. Behavioral assertions and the baseline remain unchanged.

Two remaining production conflicts cross the separately assigned Agent Mode boundary. They remain strict failing tests, not environment skips:

- Matgen construction must capture a copy of execution provenance (source, session_id, turn_id and instance_id) synchronously, then forward that saved context through the actual queued worker's _post body after caller context clears. The old test's submit/queue API is obsolete, but its construction-time provenance assertion is still required. Current MatgenJob does not implement that provenance interface.
- Parked resume's strict contract requires only the first eligible scene per _ask event, while current production deliberately resumes every eligible tab. Existing per-session one-shot guards do not settle that event-level policy conflict.

These interfaces are reported to the owning crew; this lane changes test fixtures only. No Agent Mode product implementation or policy was changed.
