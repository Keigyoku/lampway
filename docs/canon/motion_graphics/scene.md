<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Scene, templates and workflow

Status: **implemented contracts with explicit evidence limits and open requirements**. See the [motion canon](motion_graphics.md) and [acceptance report](../../reports/motion-graphics-acceptance.md); no acceptance is promoted by this write-up.

## A. Problem and invariants

Define deterministic scene authoring, readiness/audit geometry and the template workflow. Readiness is checked after setup; each frame is authored from seconds alone; authored audits enumerate visible text and marks in viewport pixels; sampled checks and template guidance retain their documented limits.

## B. Verification and gaps

The acceptance report maps runtime regressions and live-browser evidence to exact heads. Malformed setup/audit/input, forbidden resources, near-threshold measurements and failed reproduction retain their refusal controls. Dedicated motion goldens and broader-platform proof are not supplied; existing open requirements stay open.


## Scene contract (section 4 of the original implementation references)

A scene is a project-contained directory with HTML and every required font, image, script and stylesheet. Use local or embedded resources. The author must supply:

```javascript
window.__scene = { duration_s: 13, width: 1920, height: 1080 };
window.__setup = async () => ({ fonts: [], images: [] });
window.__frame = t => { /* set every visible animated property from t */ };
window.__audit = () => ({ text: [], marks: [] });
```

This is an interface sketch, not a complete acceptable scene. `__setup()` must load all assets/fonts before capture and return an object containing both arrays, reporting each resource as `{font,ok}` or `{src,ok}` with a nonempty string identifier and boolean readiness. Use empty arrays when no resources of that type are needed. Malformed reports are refused in both capture passes; false readiness names the missing resource. Requested tool dimensions determine the viewport; the metadata does not override tool dimension defaults. Captured PNG dimensions must match that viewport.

`__frame(t)` must establish animation from time alone. Authoring forbids clocks, unseeded randomness, requestAnimationFrame and independently advancing CSS animations/transitions. Runtime checks `document.getAnimations()` after setup and rejects active animations; it does not statically enforce every forbidden JavaScript API. Use deterministic math/data and preloaded resources; fresh sequential browser checks establish sampled agreement.

`__audit()` is required after setup and returns arrays for all visible text and marks at the captured time. Text items include `sel`, `text`, `box=[x0,y0,x1,y1]`, `font_px`, `opacity`. Mark items include `sel`, `box`. Coordinates are viewport pixels with finite ordered bounds. Runtime validates arrays, selectors, finite ordered geometry, text strings, positive font size and opacity in [0,1]. Authored completeness remains an author responsibility: the renderer cannot discover omitted elements. Empty lists are appropriate only when no such elements are visible.

## Self-check contract (section 6 of implementation references)

| Check | Current acceptance rule |
|---|---|
| Empty/sparse | Local luminance-detail share below 0.01% fails; below 0.1% warns |
| Title safe | Reported text must lie within 5% inset on each side |
| Font size | Reported text under 22 px fails |
| Contrast | For opacity ≥0.95, measured contrast below 4.5 fails; at ≥24 px threshold is 3.0; unavailable measurement is not an automatic failure |
| Crop | Reported marks extending beyond viewport fail |
| Overlap | Reported text overlapping `figure` or `card*` fails, except `.card .tag` |
| Probe | A differing fresh-browser probe RGB hash fails |
| Resources | Forbidden request in either render pass fails |

These checks use sampled pixels and authored geometry. They do not detect all readability, omitted text, poor pacing, layout or animation defects. Review the contact sheet and rendered video separately. Keep sparse-opening and other warnings visible.

For reproduction of the detail gate, resize to half-resolution with bilinear filtering, compute luminance using RGB weights 0.2126/0.7152/0.0722, and measure the share whose summed horizontal/vertical local differences exceed 10 on the 0–255 scale. Detail and contrast decisions use the measured ratio before display rounding; a value just below a threshold still fails or warns. Overlap selectors are literal authored values: `sel == "figure"` or `sel.startswith("card")`, with the exact text selector exemption `.card .tag`.

## Template contract

All seven builtins are version `1.0.0`, purpose `motion-graphics`, media `video`. Defaults are `1080p`, `16:9`, `min_text_px=28`; these are authoring guidance, not renderer configuration. Runtime minimum remains 22 px. Five non-TITAN templates use the supplied brand stylesheet's palette; TITAN templates deliberately have no palette variable.

| ID | Duration guidance | Required variables | Additional defaults (abbreviated prose values) |
|---|---|---|---|
| `mg-site-clip` | 13 s | None | `logo_dir=public/assets`, `copy_source=public/index.html`, `media_dir=public/media`, `read_s=1.2`; focus keys, three features, source build |
| `mg-tutorial` | 20 s | `task` | `step_count=4`, `step_s=3`, numbered tutorial list as `steps_source` |
| `mg-release` | 15 s | `version`, `date`, `notes_source` | `max_items=6`, `read_s=1.5` |
| `mg-facelift-ui-demo` | 10 s | `point`, `region` | `surface=spend`, `whole_s=1.5` |
| `mg-report-card` | 10 s | `data_source`, `headline`, `fields` | None |
| `mg-titan-animatic` | 30 s | `sequence`, `shot_list` | `shot_count=6`, `aspect=16:9` |
| `mg-titan-ui-motion` | 12 s | `element`, `states`, `tokens_source` | `state_s=1`, `transition_ms=200` |

The tool checks template purpose, resolves version and stores effective variables/prompt provenance. Reference-image and template gate declarations guide authoring; the tool does not receive/validate required reference images or turn those declarations into runtime thresholds. Templates do not promise a verified finished output.

## End-to-end workflow

1. Choose a scoped use case and local, authorized assets. Record provenance and optional template/version/variables. Do not add paid services or external asset fetches.
2. Author setup, time-driven frame function and complete audit. Vault filing is automatic during a passing render when enabled and available, before the following review/verify steps. Use `vault=false` for an initial review without filing; there is no dedicated later-filing action. Keep source files stable; render sequentially with the intended dimensions, fps, duration and formats.
3. Inspect receipt findings/contact sheet and watch exported video. A warning needs a stated disposition; a failure requires a changed scene and a fresh run. Do not hide findings by omitting audit entries.
4. Verify against the saved trusted receipt in the recorded environment. Report full frame/new-output reproduction separately from sampled render acceptance and original-file integrity.
5. Check media metadata and publication safety. Inspect any automatic Vault capture, variants/QA edges and spool status separately. Filing uses sealed checked bytes and carries replayable relationships; a partial/failed filing requires reconciliation rather than blind duplicate submission.
6. Attach exact commit, environment, outputs/digests, test results and unresolved gaps to acceptance. A synthetic-only run cannot close live-browser acceptance.
