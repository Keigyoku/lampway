# Lampway fork patches — report (lp/fork-patches)

Worktree: `<workspace>/wt-fork-patches`, branch `lp/fork-patches`, base `edaeb32f`.
Pushed: `git push origin lp/fork-patches` (three pushes: `[new branch]`, `29036afb..a94fcc6f`,
`a94fcc6f..c7b0190f`); remote head `c7b0190f2213` = local HEAD (verified with
`git ls-remote --heads origin lp/fork-patches`). Working tree clean. Nothing pushed to any other branch.

## Commits (author Keigyoku, no attribution trailers)

```
0ccdf4c5 config: Lampway identity module; backend defaults to our server with a runtime override
83c71441 creator: compile out the native login gate behind LAMPWAY (default ON)
04dbb999 hosts: every mixar.app link and the tour CDN go through configuration
d597d6cb telemetry: off by default, and only ever to the configured backend
32f96d35 brand: Lampway product and agent names on every user-facing surface
c200d8f1 brand: generated placeholder art replaces every Mixar brand asset
cef1789b docs: README, TRADEMARKS and NOTICE describe Lampway as an unaffiliated fork
8174b986 tests: the tour script pins the agent-name constant, not the upstream name
29036afb hosts: keep the Help menu's Tutorials row on our website; tests pin the constants
a94fcc6f tests: stub the platform keyring in the sandbox-hosts test like the other standalone tests
c7b0190f tests: the Lampway tests must not change later files' outcomes
```

(The first seven were cut once, then re-cut from the base so the brand-licence deletion landed in the
art commit instead of the config commit — same content, different SHAs; nothing had been pushed.)

## What changed

### 1. C++ startup gate (deliverable 1)

- `cmake/mixar_overrides.cmake:81-93` — `set(LAMPWAY ON CACHE BOOL ...)` and `LAMPWAY_PRODUCT_NAME`
  cache string; status message either way. `-DLAMPWAY=OFF` restores upstream.
- `src/source/creator/CMakeLists.txt:138-146` — `if(LAMPWAY) add_definitions(-DLAMPWAY)`; fallback for
  `LAMPWAY_PRODUCT_NAME`. `:1829-1841` macOS `MACOSX_BUNDLE_BUNDLE_NAME` uses `${LAMPWAY_PRODUCT_NAME}`
  (bundle id `com.mixar.mixar` unchanged on purpose: preferences/keychain stay put).
- `src/source/creator/creator.cc:394-413` — the whole `show_startup_dialog()` block is inside
  `#ifndef LAMPWAY`, marked `// LAMPWAY:`. A Lampway build never exits for a missing keyring token;
  login is the Python browser SSO. `show_startup_dialog` is still compiled (dead), so OFF is a clean
  revert.
- `src/source/creator/creator_startup.cc:85-96` — `get_mixar_base_url()` reads `LAMPWAY_BACKEND_URL`
  before the baked `MIXAR_BASE_URL` macro (same variable the Python side reads).
- `src/source/creator/creator_startup.cc:437-456` — the token exchange keeps requiring `https://` for
  every URL except, under `#ifdef LAMPWAY`, plain `http://127.0.0.1[:/]` and `http://localhost[:/]`
  (loopback only; any other `http://` is still refused with the upstream message).
- Baked defaults: `scripts/unix/settings.sh:39-42`, `scripts/windows/settings.bat:38-41`,
  `.env.example:8-13` → `MIXAR_BACKEND_URL` / `MIXAR_FRONTEND_URL` default to `http://127.0.0.1:8787`.

### 2. Hosts through config (deliverable 2)

- NEW `src/scripts/mixar/config/brand.py` (bpy-free; the ONE place): `PRODUCT_NAME="Lampway"`,
  `AGENT_NAME="Lampway Agent"`, `WEBSITE_URL="https://lampway.app"` (PLACEHOLDER), `DEFAULT_BACKEND_URL=
  "http://127.0.0.1:8787"`, `ENV_BACKEND_URL="LAMPWAY_BACKEND_URL"`, `TOUR_PACKS_PATH`,
  `DEFAULT_ASSET_HOSTS=(amazonaws.com, cloudflarestorage.com, 127.0.0.1, localhost)`, `website_url(path)`.
- `src/scripts/mixar/config/config.py:230-262` — `get_server_url()`: env override > bundled `backend_url`
  > `DEFAULT_BACKEND_URL`; `get_frontend_url()`: env override > bundled `frontend_url` > backend (our
  server serves the SSO page). Trailing slash on the override is stripped.
- `scripts/generate_config.py:21-36, 97-103` — loads `brand.py` by file path (the `mixar.config` package
  imports bpy, so it cannot be imported at build time) and defaults both URLs to `DEFAULT_BACKEND_URL`.
- Links: `modules/common/notifications/constants.py:42-43` (referrals, creator program),
  `modules/common/updates/constants.py:78` (downloads), `modules/mcp_bridge/constants.py:16` (setup
  guide), `modules/common/job_queue/ui/lists/queue_uilist.py:44` (bug report),
  `modules/space_mixie_chat/ui/topbar.py:97-105` (about/docs/bug report fallback menu),
  `bootstrap/splash_menu.py:212-219` (About → `/about`; the upstream Discord invite replaced by a
  "Website" row), `modules/common/ui/panels/privacy_panel.py:45-47` (privacy policy),
  `src/scripts/startup/bl_ui/space_topbar.py:602-620` (Help menu: Tutorials/Documentation/Report a
  Bug/Creator Program, all `website_url(...)`, import deferred to draw time because `bl_ui` can load
  before bootstrap puts `mixar` on `sys.path`), `:117-121` and `:131-132` (app menu says "Lampway"),
  `src/source/blender/editors/interface/interface_mixar_profile_card.cc:56-60` (`LAMPWAY_WEBSITE_URL
  "/docs"`, `"/bug-report"`), `modules/texel_density/texel/add_td_operators.py:264`.
- Tour packs: `modules/onboarding/core/tour/config.py:41-45` static default = backend + path;
  `modules/onboarding/core/tour/pack_fetch.py:42-48` `manifest_url()` = `MIXAR_TOUR_PACKS_URL` else
  `get_server_url() + "/tour-packs/manifest.json"` (live backend, not the upstream CDN).
  `scripts/dev/tour_pack/cli.py:37-40` (the pack-building dev tool) defaults its base likewise.
- Sandbox: `modules/space_mixie_chat/core/sandbox_modules.py:287-293` default allow-list from
  `DEFAULT_ASSET_HOSTS`; `MIXAR_ASSET_HOSTS` still overrides.
- Non-link literals: `modules/common/usage/core/account.py:11` and
  `src/source/blender/editors/include/UI_mixar_types.hh:50` (doc examples → example.com);
  `src/build_files/cmake/packaging.cmake:8-12` (installer metadata, PLACEHOLDER `https://github.com/Keigyoku/lampway/issues`).
- Headless sandbox children already receive `MIXAR_BACKEND_URL=get_server_url()` from the parent
  (`bootstrap/sandbox_supervisor.py:151`), so the override propagates without a change there.

### 3. Rebrand (deliverable 3)

- NEW `src/source/blender/blenlib/BLI_lampway_brand.h` — `LAMPWAY_PRODUCT_NAME`, `LAMPWAY_AGENT_NAME`,
  `LAMPWAY_WEBSITE_URL`; `tests/lampway/test_lampway_brand.py` pins it to `brand.py`.
- Window title `windowmanager/intern/wm_window.cc:797, 881`; platform-support dialogs
  `wm_platform_support.cc:148,170,179,202,215,226`; file filters + startup-file prompt
  `wm_files.cc:2790,3646,4425`.
- Agent name in C++: `agent_ui_controls_paint.cc:439` (chip fallback), `agent_ui_chip_fit.hh:29-37,145`
  (guarded mirror `#ifndef LAMPWAY_AGENT_NAME` because `tests/chip_fit_harness.cc` compiles this header
  with a single `-I` and no blenlib; the test keeps the mirror equal to `brand.AGENT_NAME`),
  `agent_ui_draw.cc:147-153` (pill prompt "Ask %s anything..."), `mixie_chat_rules_rows.cc:55-58`.
- Python user-facing strings → `AGENT_NAME` / `PRODUCT_NAME`: `open_mixie_op.py`, `quick_prompt_ops.py`,
  `auth_ops.py`, `session_ops.py`, `rules_ops.py`, `credits_notice.py`, `chat_props.py` (property
  names/descriptions + the depth-render hint), `context_folder/.../attach_menu.py`, `byok/core/model_menu.py`
  (`RESET_TEXT = AGENT_NAME`), `onboarding/core/tour/script.py` (captions/hints), `login_panel.py`,
  `topbar.py`, `privacy_panel.py`, `theme_panel.py`, `theme_ops.py`, `bootstrap/analytics_module.py`.
- Identity files: `src/release/freedesktop/mixar.desktop:2` (`Name=Lampway`),
  `org.mixar.Mixar.metainfo.xml` (rewritten; component id kept), `darwin/.../Info.plist` (document type,
  usage descriptions, get-info string), `windows/icons/winmixar.rc:31-35`.
- Placeholder art: NEW `scripts/dev/lampway_placeholder_art.py` (one lamp glyph → SVG, Blender `.dat`
  with the ORIGINAL headers `(16,16,257,320,602,640)` / `(32,32,514,640,1204,1280)`, PNG, lossless WebP,
  ICO 16–256, ICNS 1024). It regenerated all 15 REUSE-listed brand files plus `splash.png` (1672x941)
  and `mixar_logo.png` (256x256). `REUSE.toml:108-135` licenses the 17 paths GPL-3.0-or-later,
  "2026 Lampway contributors (placeholder art)", precedence override.
  `LICENSES/LicenseRef-Mixar-Brand.txt` deleted (no file references it any more).
  Note: `mixar_icons.svg` was upstream's whole Blender icon sheet (602x640, Inkscape) re-tagged as a
  brand asset; it is now a minimal sheet holding only our cell at (257,320). Blender's own icons come
  from `upstream/`, the `.dat` cells are what the build reads, so nothing is lost for the build; a
  designer regenerating `.dat` from the sheet would use our generator instead.
- Docs: `README.md`, `TRADEMARKS.md`, `NOTICE.md` rewritten (fork of the GPL Mixar client, not
  affiliated, brand removed, what stays internal and why).

### 4. Telemetry (deliverable 4)

- `modules/common/analytics/preferences.py:10-16` — `share_usage_data` defaults to `False`.
- `bootstrap/analytics_module.py:309-313` — consent property description says off by default / your
  server. Delivery was already a relative path on the shared client (`capture.py:206-213`), so with the
  backend default moved nothing can reach `mixar.app`; `tests/lampway/test_lampway_telemetry.py` pins it.

## Tests

New suite `tests/lampway/` (9 files, 42 tests): backend URL resolution, build-time config defaults, a
scanner proving no production file names `mixar.app` or the brand licence, sandbox hosts, telemetry
default, tour-pack URL, brand identity + C++ mirror parity + per-file string-literal checks (AST on
Python, comment-stripped literals in C++), C++ gate source pins, placeholder-art formats/dims/headers
and REUSE annotation.

RED (host, before implementation): `python3 -m pytest -q tests/lampway` → 5 collection errors
(`ImportError: cannot import name 'brand' from 'mixar.config'`), then on the four collectable files
10 failed / 6 passed. The six early passes are pins of unchanged behaviour (opt-in/opt-out honoured,
the telemetry path being relative, scanner self-check, `.dat` headers, raster dims) — they were never
red and are stated here as such, not as evidence. Example reds for the right reason:
`preferences.is_enabled()` → `assert True is False`; the scanner listed 48 `mixar.app` lines;
`get_mixar_base_url` body lacked `getenv("LAMPWAY_BACKEND_URL")`; no `#ifndef LAMPWAY`.

GREEN (host): `tests/lampway` + touched existing files → `128 passed` (green3.log), then after the
Tutorials-row/test updates `109 passed, 1 failed` where the failure is
`test_open_mixie_shortcut::test_every_default_shift_m_keymap_is_overridden` — it reads
`upstream/scripts/presets/keyconfig/...` which this linked worktree does not carry; it fails identically
on the untouched main checkout (pre-existing).

Full suite (`python -m pytest -q --continue-on-collection-errors`), host, python 3.14 / pytest 9.1.1:
- my tree: `109 failed, 7075 passed, 30 skipped, 21 errors`
- untouched main checkout at the same HEAD `edaeb32f`: `104 failed, 7038 passed, 30 skipped, 21 errors`
- set difference (mine minus baseline) = 5: three `test_tour_script` captions, the model-picker reset
  row, the Help-menu Tutorials test — all pinning the upstream name/channel the brief changes; all
  updated to the constants in `8174b986` / `29036afb` and re-run green.
- the 131 pre-existing failures are environment: `mcp` package absent on the host (tests/mcp/*),
  `paint.procedural_materials` withheld upstream (audit B9), `upstream/` submodule absent in the worktree,
  tour media/subtitle assets absent, `docs/` absent, etc. I did not fix them.
- `tests/test_island_voice_and_sketch_pill.py` (compiles `agent_ui_chip_fit.hh` with the host `c++`
  via `tests/chip_fit_harness.cc`) → `28 passed`, i.e. the guarded `LAMPWAY_AGENT_NAME` mirror compiles
  and the fit rows still parse.
- Final host run of `tests/lampway` at HEAD `c7b0190f`: `42 passed`.
- Honesty note on the box: the FIRST `lampway-dev` box (as handed over) was broken before I touched
  anything? No — I believe I broke it: my very first probe `distrobox enter lampway-dev -- ...` ran
  under the tool's default 120 s timeout and was killed during the box's first-run `apt-get install`,
  which is exactly the "dpkg was interrupted" state `podman logs` then showed. The box was recreated,
  not repaired; the rebuild ran detached with no timeout.

Asset checks beyond the tests: I viewed the generated `splash.png` and `mixar_logo.png` (lamp glyph,
"Lampway", the non-affiliation line) and rasterised `credits_upgrade.svg`, `mixar_icons.svg` and
`mixar-symbolic.svg` with ImageMagick — all parse; the sheet's glyph sits at the (257,320) cell.

### Box verification (distrobox lampway-dev)

The box as handed over had died in its own init (`Container Setup Failure!`, exit 100, `podman logs`:
"dpkg was interrupted"); `podman mount`+`chroot dpkg --configure -a` could not finish (half-installed
`ncurses-bin`), `podman exec` failed with "unable to find user root", and a retry `distrobox enter` hung
in the same init for 30+ min. I killed my two hung PIDs (238053 `distrobox-enter lampway-dev`,
232564 the repair script) and recreated the box (`distrobox rm -f` + `create -i ubuntu:24.04`), then
provisioned python3/pytest/PIL/numpy/g++/libcurl4-openssl-dev/libssl-dev.

Box toolchain after provisioning: Ubuntu 24.04.4, Python 3.12.3, pytest 7.4.4, Pillow 10.2.0,
numpy 1.26.4, g++ 13.3.0, libcurl/openssl headers, plus `pip install -r scripts/python_requirements.txt`
(keyring 24.2, truststore, websocket-client, httpx, mcp 2.2.0, mistune, cryptography). The box keeps
dropping into podman's "unable to find user <name>" state between sessions; every run below starts
with `podman stop lampway-dev; podman start lampway-dev` (the known repair), so each is one
`distrobox enter` session driven from a script under the scratchpad (never `/tmp` directly, never
`pkill`).

Results in the box (all commands bare, exit codes read from the log):

- `tests/lampway` → `42 passed`.
- `tests/lampway` + every touched existing test + `tests/test_island_voice_and_sketch_pill.py`
  → `198 passed, 1 failed`; the failure is the pre-existing keymap test (absent `upstream/`).
- C++ syntax check (`scratchpad/syntax_check.sh`): `g++ -std=c++17 -fsyntax-only -Wall -Wextra` on
  `creator_startup.cc` with a stub `mixar_env_config.h` → **OK, 0 warnings with `-DLAMPWAY`** and
  **OK, 0 warnings without**; `tests/chip_fit_harness.cc` builds against the edited
  `agent_ui_chip_fit.hh` and prints 2664 fit rows; a one-line program including only that header
  prints `Lampway Agent` (the guarded mirror reaches a header-only build). `creator.cc`,
  `wm_window.cc`, `wm_platform_support.cc`, `wm_files.cc`, `agent_ui_*.cc`, `mixie_chat_rules_rows.cc`
  and `interface_mixar_profile_card.cc` need the Blender tree and were NOT compiled — build crew.
- Whole suite in the box, my tree: `116 failed, 7107 passed, 30 skipped, 27 errors`;
  untouched baseline checkout (`edaeb32f`) in the same box: `116 failed, 7065 passed, 30 skipped,
  27 errors`. The two failing-id sets are IDENTICAL (113 unique ids; `comm` both ways empty); the
  +42 passes are the Lampway suite. The box fails 22 more ids than the host (scribble drawer under
  pytest 7.4's fixture semantics, BYOK models cache / tour video / tour watchdog behind a real
  keyring's D-Bus backend) — all in files I did not touch and all failing on the baseline too.

A finding on the way: my first `tests/lampway/test_lampway_sandbox_hosts.py` imported
`sandbox_modules` through its package, which runs `space_mixie_chat.core.__init__` (connection
manager → auth → the real keyring). `tests/lampway` collects early, and in the box that import
flipped nine later tests in files I never touched (`16 failed` vs the baseline's `7 failed` for the
same four files; bisected per Lampway test file inside the box). `sandbox_modules.py` itself imports
only `builtins`/`types`, so the test now loads the file by path; the `requests` stub in
`test_lampway_tour_packs.py` likewise applies only when the package is genuinely absent
(commit `c7b0190f`). After the fix: `tests/lampway` followed by those four files reproduces the
baseline's `7 failed, 11 errors` exactly.

## What the build crew must verify (I did not build Blender)

1. `cmake -C cmake/mixar_overrides.cmake ...` prints `Lampway: native login gate OFF`; the creator target
   compiles with `-DLAMPWAY`; a Prod build with an EMPTY keyring reaches the splash instead of exiting
   (creator.cc gate). Also build once with `-DLAMPWAY=OFF` to prove the revert path still compiles.
2. `BLI_lampway_brand.h` is reachable from `windowmanager/`, `editors/interface`,
   `editors/space_agent_bubble`, `editors/space_mixie_chat` (bf::blenlib include dir; no CMake list edit
   was needed, the overlay has no blenlib CMakeLists). If an include-path error appears, that is the
   place.
3. `BLI_snprintf` with `IFACE_("Ask %s anything...")` / `IFACE_("Add a rule above to guide %s.")`
   compiles (BLI_string.h is already included in both files) and the translated format strings survive
   `make i18n_update` (two new msgids with `%s`; the old literal msgids go stale).
4. `interface_mixar_profile_card.cc`: `constexpr const char *MIXAR_URL_DOCS = LAMPWAY_WEBSITE_URL "/docs";`
   (adjacent-literal concatenation of a macro) compiles under MSVC too.
5. macOS: `MACOSX_BUNDLE_BUNDLE_NAME` now "Lampway x.y"; bundle directory is still `Mixar.app` and the
   executable is still `Mixar`/`mixar` (unchanged on purpose — see open questions).
6. Windows: `winmixar.rc` strings, the new `.ico` files (six sizes, PNG-compressed 256) and the
   `winmixarfile.ico` document icon are accepted by the resource compiler; `Info.plist` on macOS with the
   new `.icns` (PIL-written, 16–1024 px) passes codesign/Finder.
7. The native token exchange: with `LAMPWAY_BACKEND_URL=http://127.0.0.1:8787` the C++ path is no longer
   reached in a LAMPWAY build (gate compiled out), but `get_mixar_base_url()` is still linked — confirm no
   `-Wunused` promotion to error for `show_startup_dialog` on any platform.
8. A real launch: `LAMPWAY_BACKEND_URL` set → the Python SSO opens
   `http://127.0.0.1:8787/app/desktop-login?...`, `GET /api/v1/auth/me` is hit on OUR server, the agent
   WS connects to `ws://127.0.0.1:8787/api/agent/ws/<id>`, telemetry stays off (no
   `POST /api/v1/telemetry/events`), and the tour fetches `/tour-packs/manifest.json` from our server.

## Open questions for the owner

1. `WEBSITE_URL = "https://lampway.app"` and `https://github.com/Keigyoku/lampway/issues` are placeholders (one constant +
   one cmake literal). Confirm the real domain, or that links should be hidden until there is one.
2. `AGENT_NAME = "Lampway Agent"` — rename at will (one constant; the C++ mirror and the chip-fit
   header mirror are pinned by a test and must be changed together).
3. Placeholder art licence: I used GPL-3.0-or-later, copyright "2026 Lampway contributors". If you
   prefer CC0/public domain for the art, change the REUSE block + the SPDX comments in the SVG
   generator.
4. Not renamed (would change paths/ids, not just what users read): `Mixar.app` bundle folder,
   `mixar`/`Mixar` executable names, `com.mixar.mixar` bundle id, the `.mixar` file extension and
   `MIXR` OSType, config folder names (`appdir.cc`), keyring service `MixarSafeStorage`, the "Mixar
   Generations" default asset-library name (`preferences.cc:191`, a stored identity), Python keymap
   names "Mixie" (keyconfig-reload contract), `st->name = "Mixie"` and `bl_category = "Mixie"` of the
   moodboard editor, RNA struct ui names ("Mixar Layers Space", "Mixie Space"), theme section names in
   `rna_userdef.cc`, the Windows installer (`installer_wix`, `msix`) metadata, `Mixar_theme.xml`,
   `CLOG` log lines, `winstuff.cc` console messages, the 49 `.po` translation catalogs (still carry
   Mixar/Mixie msgids/msgstrs; `make i18n_update` needed), and the compiled-out Windows login dialog
   title. Say which of these you want and I will do them as a follow-up.
5. The upstream Discord invite and YouTube channel were removed from the splash/Help menus (they are
   Mixar's); "Tutorials" now points at `website_url("/tutorials")`. OK?
6. `CLAUDE.md`, `CONTRIBUTING.md`, `SECURITY.md`, `SUPPORT.md`, `CODE_OF_CONDUCT.md`,
   `SOURCE_CORRESPONDENCE.md`, `MAINTAINERS.md` still describe Mixar's processes/contacts; out of the
   brief's three named docs, left untouched.

## Graph-reach findings

- `src/scripts/startup/` (the `bl_ui` overlays incl. the Help menu with three `mixar.app` links, and
  the bootstrap loader) is in NEITHER `mixar-addon` (rooted at `src/scripts/mixar`) nor `mixar-app`
  (excludes `src/scripts`). The audit's host list therefore missed `bl_ui/space_topbar.py:605-615`;
  `tests/test_credits_banner.py` led me to it. I indexed it as project `lampway-startup` (fast mode,
  619 nodes) and found the three links plus the "Mixar" app-menu label there.
- Both pre-existing indexes point at `<workspace>/app`, not at this worktree; they are
  at the same HEAD so line numbers matched, but any graph query "after my change" would have to be
  re-indexed against the worktree.
- `search_code` is a literal grep; it cannot distinguish a string literal from an identifier
  (`MixieCatPose`) or a comment, hence the per-file AST / comment-stripped checks in the tests.

## Residue I know about

- The "Hi I'm Mixie" greeting named in comments (`mixie_chat_messages.cc:373`, `chat_props.py:864`) has
  no literal in C++ or Python that `search_code` could find; whatever draws it must build the text from
  another source. Please check the empty-state greeting in a running build.
- `credits_upgrade.svg`'s badge reads more like a funnel than an up-arrow. Placeholder; the four badges
  only need to tell apart.
- i18n: f-strings for `bl_label`/`bl_description` and `n_("…{agent}…").format(...)` mean the translated
  msgid is the template, not the final sentence; catalogs are Mixar's anyway and need regenerating.
