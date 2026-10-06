<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Animation from video

The idea: draw a short clip of your character walking (or doing any motion) with an AI video model, recover the motion as bone rotations from the clip, check it with numbers, and turn it into a seamless loop for your game engine. Each stage is a measured, gated tool. A stage that fails its gate stops the run; **a clip is never re-drawn without you, because every draw is a new charge**.

Code: `src/scripts/mixar/modules/lampway_tools/pipeline/anim_*.py` and `features/anim_render.py`, `features/animation.py`, with agent tools registered in `server/lampway_server/agent/lampway_tools.py`. Tests: `tests/lampway_tools/test_wave4_*.py`.

**Read this first: what is proven and what is not.** Every tool here is built and tested. The tests use **synthetic** figures and clips: a synthetic two-view walk recovers every bone direction within 5 degrees (observed 1.9 worst) and the leg identity in 100 % of frames, and the single-view control fails identity on the same clip. No clip was drawn (an agent never spends), so the live acceptance evidence (a recorded clip, a walk cycle, an edit and an upscale) has not been produced, and the numbers below are the **proposed** thresholds, not validated ones.

## 1. The pipeline

`lampway_anim_from_video` plans the whole chain as **one dry-run plan** with one spend card; nothing runs and nothing is spent until you confirm each paid step.

| Step | Tool | Cost | Output |
|---|---|---|---|
| 1. Reference render | `lampway_anim_reference_render` | free | the character at rest from a **known orthographic camera** on a plain grey background, front and side: `ref_<view>.png`, `ref_<view>_mask.png` and `cameras.json` (orthographic scale, px per metre, centre, axes). Workbench, anti-aliasing off, so the grey is exact and two renders are byte-identical. Refused: a perspective camera, a posed character, no skinned model, a figure whose feet or head leave the frame |
| 2. Clip plan | `lampway_anim_clip` | dry run | the locked-camera prompt (`locked camera, no cuts, no zoom, the whole body and feet in frame, <motion> in place`), the model arguments and the list price (22.5 Higgsfield credits per 720p 9:16 5 s Seedance 2.0 clip, 45 for two views; about $0.76, or $0.46 with the front clip as video reference, on OpenRouter: derived from the model's price table, not measured). Refused: a 16:9 clip, under 4 s, a reference without its recorded camera |
| 3. Draw | `lampway_video_gen` (see [providers](providers.md)) | your click | the clip. Presets: `anim-walk-side-track`, `anim-split-front-side`, `anim-walk-ortho-inplace`, `anim-loop`, `anim-motion-transfer` and others in the prompt library |
| 4. Clip gate | `lampway_video_gate kind=clip` | free | 24 fps with every frame distinct, 720x1280, 5.0 s, figure at least 1000 px tall and never touching the border, locked camera, at least 4 strides (the stride count is unverified without foot contacts) |
| 5. Track | `lampway_anim_multiview_fit` | free | motion from one split-screen clip, see section 2 |
| 6. Check | `lampway_anim_check` | free | section 3 |
| 7. Loop and export | `lampway_anim_loop_export` | free | section 4 |

`stock_first` refuses a pipeline when a stock animation already has the move: retarget it instead with `lampway_animation_retarget`.

## 2. The primary tracker: `anim_multiview_fit`

Input: a **synchronised split-screen clip** (front panel and side panel) and the camera record from step 1. For each panel the 2D positions of 15 joints (in the order of `pipeline.anim_mv.JOINTS`, as JSON) are triangulated orthographically into 3D, pelvis-relative. The side view's near/far leg labels are fixed per frame from the front view's heights; where the heights tie (both feet down), a constant-velocity continuity prediction decides (without it the arms swapped at the crossings by 52 degrees in the synthetic test). The scale comes from head-to-sole calibration or `cameras.json`; a grid clip's parallax gives the root speed (16 px per frame becomes metres per second), but its **direction is assumed forward** because the correlation is unsigned. Refused: panels out of sync, no scale. `single_view=true` is the control that cannot tell legs apart and says so.

What is not built: the 2D detector (`stage=detect` answers `needs_approval`; you supply keypoints as JSON), and the two-view silhouette analysis-by-synthesis with the **skinned** character in headless Blender (only the pure core exists: `refine`, a capsule silhouette and the recorded cameras).

`lampway_anim_track` is the decision stub for other trackers. It answers `needs_decision` with the question and the model slots (GEM-X body tracking, a hosted SAM 3D Body, Uthana: all `needs_approval`), and refuses GVHMR for shipped work (a research-only licence that needs SMPL-X) and MetaHuman Animator Markerless off Windows. The provider is the maintainer's open decision: MHA is Windows-only, and the measured local alternative (SAM 3D Body) reads about 80 % on the leg-identity gate against an 85 % threshold. A coverage gate requires at least 90 % of frames recognised (a tracker that recognised 33 of 122 frames fails it).

## 3. The check: `anim_check`

Judges the tracked motion against **both** views' masks and the ground, with numbers (thresholds are proposed, not adopted):

| Gate | Threshold |
|---|---|
| G-OUT-front, G-OUT-side | outline IoU at least 0.80 and 0.85 |
| G-LEGS | at least 85 % of lifted frames have the lifted foot travelling forward |
| G-FOOT-SLIDE, G-FOOT-PLANT | at most 1 cm |
| G-TWIST | at most 5 degrees per bone (unverified without tracker or refined yaws) |
| G-CLAIMS | every motion claim carries a measurement |

**Controls run on the same take**: a fore-aft mirrored copy must read about 0 on G-LEGS, and a dragged stance foot must fail the slide gate. A check whose controls cannot fail does not pass. A single view is refused. Without posed silhouettes a capsule stand-in is drawn and the result says so in `silhouette_source`. G-TOE is unverified.

## 4. Loop and export: `anim_loop_export`

Takes a checked multi-stride take, finds the period by autocorrelation refined by least squares across strides, averages the strides by phase, and reports the export gates: G-LOOP (at most 1 degree between strides, root offset one period), G-LOOP-WRAP, G-SPEED (planted-foot speed within 5 % of the root's), G-STRIDES (at least 4), G-SKEL (the bone set against your reference bones; unverified without them). Refused: a take that failed `anim_check`, one stride, an export onto Manny. The output is `loop.json`.

**Not built: the engine leg.** No AnimSequence is published; G-FIDELITY and G-ENGINE are reported `not_run` or unverified, never a pass. The loop limit stays at 1 degree until it has been measured on more than one rig.

## 5. Neighbouring tools

- `lampway_animation_retarget` bakes an animation from one skeleton onto another: a new Action, rest poses compensated, the root scaled by the pelvis-height ratio, with the world-direction error, foot slide and stretch measured. `mapping='auto'` reads bone names (Mixamo, Rigify, UE, Bip01) and `dry_run` shows the mapping first. The `constraints` method does not compensate a different rest pose and a test pins that.
- `lampway_clip_classify` names what kind of motion each action is, from six landmark bones, with a tri-state loop decision; its thresholds come from one subject on one rig.
- `lampway_video_gate` also has loop (closure, wrap jump), duplicates, upscale and edit kinds (SSIM, PSNR), tested on real ffmpeg clips.
- `lampway_video_ingest_url` brings a reference clip in from a link you paste, after your confirm, with provenance.

## 6. Open items

The tracker provider decision, the UE editor leg, the RTMW detector, the skinned silhouette synthesis, and the live evidence (a drawn clip and a walk cycle on a real character) are listed in the [roadmap](roadmap.md).
