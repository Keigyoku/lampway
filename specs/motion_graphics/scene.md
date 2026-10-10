<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Scene, templates and workflow

## Scene contract (section 4 of the original implementation references)

A scene is a project-contained directory with HTML and every required font, image, script and stylesheet. Use local or embedded resources. The author must supply:

```javascript
window.__scene = { duration_s: 13, width: 1920, height: 1080 };
window.__setup = async () => ({ fonts: [], images: [] });
window.__frame = t => { /* set every visible animated property from t */ };
window.__audit = () => ({ text: [], marks: [] });
```

This is an interface sketch, not a complete acceptable scene. `__setup()` must load all assets/fonts before capture and return an object containing both arrays, reporting each resource as `{font,ok}` or `{src,ok}` with a nonempty string identifier and boolean readiness. Use empty arrays when no resources of that type are needed. Malformed reports are refused in both capture passes; false readiness names the missing resource. Width, height, fps and duration follow one defaults order: an explicit tool argument, then the template's `defaults` (`resolution` and `aspect_ratio` give width and height, `duration` gives `duration_s`), then the scene's own `__scene` (integer `width`, `height`, `fps`; numeric `duration_s`), then the tool fallback (1920 × 1080, 30 fps; there is no fallback duration). The resolved values determine the viewport: a scene-declared size is rendered in a fresh browser opened at that size. The receipt's `input_sources` and the summary's `inputs` name each value's source (`explicit`, `template`, `scene`, `tool default`). When an explicit or template value overrides a differing `__scene` value, the receipt carries one `scene_override` warning (frame 0) naming both, and a help line says how to render the scene's own. Captured PNG dimensions must match that viewport.

`__scene` may also declare `opening_s`, the seconds of an intentional draw-on opening (see Empty/sparse below); the receipt records it.

`__frame(t)` must establish animation from time alone. Authoring forbids clocks, unseeded randomness, requestAnimationFrame and independently advancing CSS animations/transitions. Runtime checks `document.getAnimations()` after setup and rejects active animations; it does not statically enforce every forbidden JavaScript API. Use deterministic math/data and preloaded resources; fresh sequential browser checks establish sampled agreement.

`__audit()` is required after setup and returns arrays for all visible text and marks at the captured time. Text items include `sel`, `text`, `box=[x0,y0,x1,y1]`, `font_px`, `opacity`. Mark items include `sel`, `box`. Coordinates are viewport pixels with finite ordered bounds. Runtime validates arrays, selectors, finite ordered geometry, text strings, positive font size and opacity in [0,1]. Authored completeness remains an author responsibility: the renderer cannot discover omitted elements. Empty lists are appropriate only when no such elements are visible.

## Self-check contract (section 6 of implementation references)

| Check | Current acceptance rule |
|---|---|
| Empty/sparse | Local luminance-detail share below 0.01% fails; below 0.1% warns, except inside a declared opening: `__scene.opening_s` (0 to 3 s, at most half the duration) marks a draw-on build-in, and a sparse sample before it is `info`. Empty still fails there |
| Title safe | Reported text must lie within 5% inset on each side |
| Font size | Reported text under 22 px fails |
| Scene override | An explicit or template width, height, fps or duration that overrides a differing `__scene` value warns (`scene_override`), with a help line |
| Script errors | The page's uncaught exceptions and `console.error` lines are collected (`Runtime.enable`). A missing `__frame`/`__audit` refusal names the first one as scene-relative `file:line:col: message`; one that does not stop the render warns (`page_error`) |
| Contrast | For opacity ≥0.95, measured contrast below 4.5 fails; at ≥24 px threshold is 3.0; unavailable measurement is not an automatic failure |
| Crop | Reported marks extending beyond viewport fail |
| Overlap | Reported text overlapping `figure` or `card*` fails, except `.card .tag` |
| Probe | A differing fresh-browser probe RGB hash fails |
| Resources | Forbidden request in either render pass fails |

These checks use sampled pixels and authored geometry. They do not detect all readability, omitted text, poor pacing, layout or animation defects. Review the contact sheet and rendered video separately. Keep sparse-opening and other warnings visible.

For reproduction of the detail gate, resize to half-resolution with bilinear filtering, compute luminance using RGB weights 0.2126/0.7152/0.0722, and measure the share whose summed horizontal/vertical local differences exceed 10 on the 0–255 scale. Detail and contrast decisions use the measured ratio before display rounding; a value just below a threshold still fails or warns. Overlap selectors are literal authored values: `sel == "figure"` or `sel.startswith("card")`, with the exact text selector exemption `.card .tag`.

## Template contract

All eight builtins are version `1.0.0`, purpose `motion-graphics`, media `video`. Defaults are `1080p`, `16:9` (`9:16`, so 1080 × 1920, for `mg-social-clip`), `min_text_px=28`; resolution, aspect and duration are render defaults (below explicit arguments, above `__scene`), `min_text_px` is authoring guidance. Runtime minimum remains 22 px. Six non-TITAN templates use the supplied brand stylesheet's palette; TITAN templates deliberately have no palette variable.

| ID | Duration guidance | Required variables | Additional defaults (abbreviated prose values) |
|---|---|---|---|
| `mg-site-clip` | 13 s | None | `logo_dir=public/assets`, `copy_source=public/index.html`, `media_dir=public/media`, `read_s=1.2`; focus keys, three features, source build |
| `mg-social-clip` | 12 s, 9:16 | `copy_source`, `focus` | `logo_dir=assets`, `media_dir=media`, `hook_s=1.5`, `read_s=1.5`; any project's own brand assets |
| `mg-tutorial` | 20 s | `task` | `step_count=4`, `step_s=3`, numbered tutorial list as `steps_source` |
| `mg-release` | 15 s | `version`, `date`, `notes_source` | `max_items=6`, `read_s=1.5` |
| `mg-facelift-ui-demo` | 10 s | `point`, `region` | `surface=spend`, `whole_s=1.5` |
| `mg-report-card` | 10 s | `data_source`, `headline`, `fields` | None |
| `mg-titan-animatic` | 30 s | `sequence`, `shot_list` | `shot_count=6`, `aspect=16:9` |
| `mg-titan-ui-motion` | 12 s | `element`, `states`, `tokens_source` | `state_s=1`, `transition_ms=200` |

The tool checks template purpose, resolves version, stores effective variables/prompt provenance and warns (with a help line) about a path-like `*_dir`/`*_source` variable that names nothing under the project. Reference-image and template gate declarations guide authoring; the tool does not receive/validate required reference images or turn those declarations into runtime thresholds. Templates do not promise a verified finished output.

## End-to-end workflow

1. Choose a scoped use case and local, authorized assets. Record provenance and optional template/version/variables. Do not add paid services or external asset fetches.
2. Author setup, time-driven frame function and complete audit. Vault filing is automatic during a passing render when enabled and available, before the following review/verify steps. Use `vault=false` for an initial review without filing; there is no dedicated later-filing action. Keep source files stable; render sequentially with the intended dimensions, fps, duration and formats.
3. Inspect receipt findings/contact sheet and watch exported video. A warning needs a stated disposition; a failure requires a changed scene and a fresh run. Do not hide findings by omitting audit entries.
4. Verify against the saved trusted receipt in the recorded environment. Report full frame/new-output reproduction separately from sampled render acceptance and original-file integrity.
5. Check media metadata and publication safety. Inspect any automatic Vault capture, variants/QA edges and spool status separately. Filing uses sealed checked bytes and carries replayable relationships; a partial/failed filing requires reconciliation rather than blind duplicate submission.
6. Attach exact commit, environment, outputs/digests, test results and unresolved gaps to acceptance. A synthetic-only run cannot close live-browser acceptance.
