# Facelift lane (`lp/facelift`): implementer report

Worktree `wt-build` (owns the native build tree and the `lampway-build` box). Contracts from the facelift spec set
(`client_facelift/`, DESIGN v2), in the order the dispatch gave: 01, 15, 14, 03, 02, 04, 05, 06, 07, 08, 12, 13, 11,
10, 16 (09 belongs to lane vault-ui). This file grows one section per contract.

## Native rebuilds the integrator needs

| commit | what needs the rebuild |
|---|---|
| (contract 01, native) | `userdef_default_theme.c` (the default theme is Lampway Night), `interface_mixar_theme.cc` (slot fallbacks), `UI_mixar_tokens.hh` (zen palette, included widely), `rna_userdef.cc` (RNA reset defaults). Also installs the two theme presets (`sync_python.sh` does not copy `src/scripts/presets/`). |
| `5f37ee91`, `ba835be1` (14) | `UI_icons.hh` (included widely), the 42 `icons_svg/lampway_*.svg` and the datafiles CMake list. |
| `0afc2d19` (03) | `interface_widgets.cc`, `agent_ui_draw.cc`, `interface_mixar_profile_card.cc`, the theme defaults and glass tokens. |
| `c92396d5` (05) | `agent_ui_pill_cat.*`, `view3d_agent_panel*`. |
| `ce3c9897` (02) | `wm_splash_screen.cc` and the `splash.png` datafile. |
| `d6b543fc` (Asset Vault) | `rna_space.cc`, `space_mixar_assets.cc`, the new `space_mixar_assets/mixar_assets_dnd.cc` and its CMake libs. |
| `c272b7c0` (Lamplight and Workshop) | the C++ that compares the workspace name (`STREQ(..., "Lamplight")`). |
| `6881d79` (04 and the pill) | `mixie_chat_*` painters, the `Fraunces.woff2` datafile, `agent_ui_state.cc`, `agent_ui_controls_paint.cc`, `agent_ui_draw.cc`, `agent_bubble_references.cc`, `space_agent_bubble.cc`. |
| (08) | `agent_ui_tabmedia.cc`, the new `agent_ui_tabmedia_estimate.cc` (CMake list), `agent_ui_tabmedia_intern.hh`, the `PlexMono.woff2` datafile, and `MixarVariant::Accent` in `UI_mixar_types.hh` (included widely: an 830-step rebuild), `interface/mixar/components.cc`, `interface/mixar/style.cc`. |
| (12) | `userdef_default_theme.c` (Timeline `simulated_frames` leaves the wire colour) and the two theme presets. |
| (install rule) | `src/source/creator/CMakeLists.txt`: a re-configure and `ninja install` (no compile). |
| `a60dce8d` (12) | `interface_widgets.cc`: an alert without a bed paints its text in the stop colour. |
| `1e857173` (13 P1) | the new `interface_mixar_spend_card.cc/.hh` (CMake list), `MixarCardElement` Spend* in `UI_mixar_types.hh` (included widely), `rna_ui_api.cc` (`layout.mixar_spend`, the `ACCENT` variant item). |
| `0a74414d`, `a21881e4` (04) | `mixie_chat_layout_data.hh`, `mixie_chat_props.cc`, `mixie_chat_ui_widgets.cc` (the who line), `mixie_chat_messages_render.cc`. |
| `d663255d` (audit F24) | `view3d_director_cinema_top.cc` (the badge's wordmark), `interface_mixar_profile_card.cc` (no referral row). |
| `a3356f14` (08) | `agent_ui_tabmedia_intern.hh`, `agent_ui_tabmedia_estimate.cc` (the last-run line; bounded string reads). |

## Status per contract (the lane's order) and per coordinator addition

| item | state | commits |
|---|---|---|
| 01 tokens and theme | done | `8e851a07`, `99d338a4`, `0b5f26fc` |
| 15 visual harness | done | `b28846b2` |
| 14 iconography | done (two fixes) | `5f37ee91`, `ba835be1`, `edf0d549` |
| 03 window chrome | done | `0afc2d19` |
| 02 splash and onboarding | done | `ce3c9897` |
| 04 chat face | done but test 6 (an approved golden) | `6881d79c`, `0a74414d`, `e003f273`, `a21881e4`, `e29f6f49` |
| 05 parallel agents | done | `c92396d5` |
| 06 Studios panel (Providers half to Choices) | done | `10233050` |
| 07 the Way | done (every batch tool has a typed form) | `faa750b3`, `cf1fc1f7`, `39d8ae9e` |
| 08 generation face | done; A/B is a stub that needs the user's click (as ruled) | `a86df92f`, `e7c96c20`, `d02a4e2f`, `a3356f14`, `508a56a7` |
| 12 privacy face | done (the two shortfalls fixed) | `0fff1aed`, `a60dce8d` |
| 13 spend card | done (P0 and the drawn P1 card) | `afa173f9`, `1e857173` |
| Connections window | P0 done | `59279873`, `add28e00` |
| Choices window (CH8, CH1) | P0 done | `c6002ee9`, `add28e00` |
| install carries no agent contract | done | `e6668a6b` |
| 11 model compare | done but the header Pick (in the sidebar) | `3e496b4a`, `e430bfb7`, `64a74195` |
| 10 cockpit window + report cards mounted | done for the page; its terminal is 16's window, not xterm.js | `3f33a237`, `b95d1acc` |
| 16 Lampway terminal | a viewport only (the captain's correction; no tabs, no state, no Focus); tests 6, 7, 9, 11 run live; the image link waits on the captain | `ad44c557`, `e370a70b`, `dca41dd5`, `b9054b3e`, `fb2935a5`, `ebf357d8`, `1968d9c6`, `fd51779d` |
| cloud audit F17, F22, F23, F24 | done | `d2b645b9`, `11b9db7c`, `75fed27f`, `b06be59d`, `d663255d` |
| BUILT_FROM stamped by the build | done | `eeb599d9` |
| brand pages (every page Lampway serves to a browser) | done, report cards and the phone camera page included | `a257a40e`, `535c17c6`, `08e2da21` |
| schema ratchet (integration request 9) | done: 702 -> 691 undescribed, 258 -> 240 unbounded | `97879399` |
| Asset Vault name and drag | done | `d6b543fc` |
| Zen shortcuts (vault-ui's finding) | done: not a bug, pinned with real input | `8eac47fb` |
| Lamplight and Workshop (captain's rename) | done | `c272b7c0` |
| floating agent pill (captain) | done, off by default, combined into the chat header | `6881d79c` |
| 13's submission_unknown UI | done in 06 | `10233050` |
| 09 | not this lane's (vault-ui) | |

## Gate totals at the contract 01 push (`30b6c2fd`, merged with `origin/lp/wave5` `00d907d4`)

- Server suite (`venv-tools`): 0 failed, 6 skipped, rc 0.
- Client, real binary (`tests/lampway_tools`, my Prod build): 826 collected, 780 passed, 46 skipped, 0 failed.
- Client, host (`pytest --continue-on-collection-errors --ignore=tests/lampway_tools`): the same 132 failing ids as the
  integration tip run the same way (most are environment: `mcp` not installed on the host, withheld subtitles, a
  gitignored `.pot`), none new; mine passes 19 more tests.
- Gates: theme 0 (6/6), cues 0 (4/4), WezTerm 0 (4/4), icons (spec copy, contract 14 brings it in) 0 (4/4); pre-push
  PII gate 0 findings.
- Windowed check of the product itself (Xvfb in the build box, a new profile): the app opens in Night, Quick Setup
  reads "Lampway Night".

## Contract 01: tokens and theme

### Review of the stopped attempt's commit `8e851a07`

Read as someone else's work against contract 01 and DESIGN v2. Its content is right: `DESIGN.md` and every file under
`theme/` are byte-identical to the spec set, except `build_theme.py`, which gained `--out` and copies the two presets
into `src/scripts/presets/interface_theme/` (the shipped presets are the generated bytes). Re-measured on this build:
`check_theme.py` 0 findings, self-test 6 of 6; `check_cues.py` 0, 4 of 4; `check_wezterm.py` 0, 4 of 4 (luajit);
`verify_in_blender.py` PASS 959/959 for both files. What it lacked, fixed in a new commit (`99d338a4`), never by
rewriting it:
- the provenance maps and `lampway.wezterm.lua` are generator outputs that nothing compared with a fresh build (a planted
  hand edit to the `.lua` went unnoticed); now pinned.
- `check_wezterm.py` and T7 (the loader, in the real binary) ran only by hand; both are tests now, T7 with the planted
  unknown attribute as its falsifier.
- the README told the reader to copy the presets by hand and linked a contract path that does not exist in the repo.
- `check_theme.py` carried two messages naming the upstream brand ("T4 Mixar green", "in the Mixar green family"),
  which the brand gate (`tests/lampway/test_brand_words.py`, G2) reports; reworded in the contract 01 commit, so the
  repo's `check_theme.py` now differs from the spec copy by those two strings.
- not done by it: the Quick Setup row (contract section 5), the compiled default (6.3/6.4), F2. Those are below.

The two untracked drafts it left were discarded: `save_userpref.py` (an unused route through upstream's tool) and
`check_native.py` (a compiled-green scanner with an unimplemented second check and no observed RED). Their job is done
by `dump_theme_dna.py` and the tests below, written RED first.

### Native: Lampway Night is the compiled default

- **How the C file is generated.** The XML speaks RNA (`view_3d.object_selected`), `userdef_default_theme.c` speaks DNA
  (`.space_view3d.select`); the map lives in C (`rna_userdef.cc`, helpers, renames, scaled getters). It is measured, not
  copied: `dump_theme_dna.py` runs in the built binary, gives every colour attribute a unique colour in one pass, nudges
  every other attribute one at a time, saves the preferences and reads them back as DNA with upstream's own reader.
  It writes `base/theme_dna_0.1.0.json`: the compiled default as DNA, and per attribute its DNA path and kind (colour,
  float/int with the measured scale, flag mask, enum values, one channel of a colour). 957 attributes mapped (938 from
  the XML plus 19 colours RNA hides from presets), 0 unmapped. `build_theme.py` then writes the C file with upstream's
  writer (`upstream/tools/utils/blender_theme_as_c.py`), and the slot fallbacks, the zen palette (`UI_mixar_tokens.hh`)
  and RNA's reset defaults (`rna_userdef.cc`, so "Reset to Default Value" gives Night back) from the same values.
  Round trip checked once before any change: the measured baseline written back by the writer equals the committed
  Forest file field for field (941 non-zero fields; the only difference was an upper-case hex in the hand-edited file).
- **Disagreement with the contract's mechanism, recorded.** 6.3 says "rewrite the RGBA initialisers from the provenance
  map". The provenance map is keyed by RNA path and cannot say which DNA field an RNA attribute lives in, so the
  emitter goes through the measured map instead. It also writes the non-colour fields (roundness, sizes, flags): T8
  "default = preset" would otherwise hold for colours only.
- **What the live test caught.** The first build passed every static test and failed the binary check with 21
  problems: RNA reads a widget's `roundness` as twice its DNA value, so the XML number written straight into DNA gave
  every Night widget double roundness. The probe now measures each number's scale (21 attributes at 0.5, 95 at 1.0);
  a mutant writing the unscaled XML number is killed by the static T8 test. The first build also stopped on the
  generated C (`.strip_color = {` left open: upstream's writer closes a block only on the next field's path, and the
  probe had dropped the padding fields that close it); a test now checks every block closes.
- **Fixed point.** After the rebuild, `dump_theme_dna.py` re-measured the new binary and `build_theme.py` regenerated
  a byte-identical C file; a test pins that the measurement is of the committed file.
- **Hidden colours.** The five Mixar slots and 14 chat/moodboard colours RNA hides from presets take their values from
  rules in the same `RULES` table (`mixar_pane_pill_dim` line, `_pane_pill_on` accent_bed, `_cinema_pill_fill` well,
  `_profile_fill` surface, `_cinema_gate_fill` text@12: values the contract did not give, chosen as the visible slot each
  sits beside). The chat space's DNA carries moodboard copies with no RNA of their own; they follow the moodboard's.
- **Not in this contract's tables.** The glass rows (`interface_mixar_liquid_glass_tokens.cc`, CARD's green rim) are
  contract 03's (its `GlassTint`/`GlassRim` slots and its `test_glass_has_no_green_and_no_sheen`); same lane, next.

### Python (no rebuild)

- Quick Setup's theme row names "Lampway Night" for a profile that picked no preset.
- F2: an existing profile keeps its colours and is offered Night once, a toast with one button
  ("Try Lampway Night" -> `lampway.apply_night_theme`, which loads the shipped preset through the Theme menu's path).
  New profiles already wear Night and are never asked; the offer is recorded in the user config either way; headless
  runs never offer. Forest is no longer offered: the theme panel's "Apply Forest" button and its operator are gone
  (the operator now reset to the compiled default, which is Night, so it would have lied). `Mixar_theme.xml` stays as
  a file for one release, as the contract recommended.

### Tests (RED observed for each before the code)

| test | what it pins |
|---|---|
| `tests/lampway/test_lampway_theme.py` (13) | T1-T6/T10 gates, every generated file committed as generated (presets, provenance, `.lua`, the four native files), the WezTerm gate, the Quick Setup row, the C file closes every block, the measured DNA is the committed file, T8 field by field through the map (colour, float with scale, flag, enum, channel, name), hidden colours follow their rules, no Mixar green in the four tables (allowed: `go`, the dark XML's own values, upstream's domain colours) |
| `tests/test_mixar_theme_colors.py` (20, the fork's) | re-pointed at `Lampway_Night.xml` as T8 says: slot table = DNA = userdef = preset, RNA reset defaults, widgets = preset, the seven contrast pairs on Night values |
| `tests/lampway/test_lampway_night_offer.py` (6) | the offer: new profile never asked, existing profile asked once and nothing applied, headless never offers, startup schedules it, the panel offers Night not Forest, Forest is not registered |
| `tests/lampway_tools/test_lampway_theme_live.py` (6, real binary) | T7 both presets load and read back 959/959, the planted unknown attribute fails, T8 in the binary (factory theme = `lampway_dark.xml`, 938/938), the Theme menu lists Night and Paper and no Forest and the theme is named Lampway Night, the offer and its button in the binary |

Mutation checks (scripted, each applied, asserted applied, run, reverted): colour initialiser, enum, float metric, the
unscaled roundness, the island-opacity channel, the theme name, a hidden slot, a green MX constant, a slot fallback,
an RNA reset default: 10 of 10 killed.

### Not done / open

- **T9 (pixels)** needs contract 15's harness; it is the first state that harness will run.
- **The style block is not compiled.** A new profile gets Night's colours with Mixar's type: measured in the factory
  session, panel titles 12 pt weight 400 with shadow 3, widgets and tooltips 12 pt with shadow 1, where Night says 11.5
  pt / 600 / no shadow and 11 pt / no shadow. The defaults live in the fork's `UI_DEFAULT_*_POINTS`
  (`UI_interface_c.hh`) and upstream's `ui_style_new`; changing them moves every layout in the app (contract 02 notes
  the splash goes from 900 to 825 px). Not in contract 01's native list, so not changed: a decision for the coordinator.
- "Reset Workspace Backgrounds" (theme panel) still writes Forest's neutral greys (#0F0F0F viewport, #1E1E1E moodboard)
  under any theme; not green, but not Night's either. Left as is; a decision.
- `startup/bootstrap/__init__.py::_initialize_theme_defaults` seeds `chat_bubble_hover` with Mixar green when a stored
  profile has none; Night's default is non-zero, so new profiles never reach it. Left as is.

## Contract 15: the visual harness

`tests/lampway_visual/`: `harness.py` (host: launch, sample, diff, approve), `driver.py` (inside the build: waits for
the deferred UI, closes the first-run splash with a simulated Escape, runs the state, applies planted colours,
captures the window with the fork's `Window.mixar_qa_capture_frame`, locates surfaces from
`WindowManager.mixar_qa_ui_dump`), `states/night_startup.py`, `expect.toml`, `golden/APPROVALS.md`.

- Display: the host has no Xvfb; the `lampway-build` box has (`xvfb-run`, Mesa llvmpipe), which answers the contract's
  open question. `LAMPWAY_XVFB` names the prefix, e.g. `podman exec --user 1000:1000 -w <repo> lampway-build xvfb-run
  -a -s '-screen 0 1600x1000x24'`; without it or `xvfb-run` on PATH the three display tests skip with "no virtual
  display: run inside the build box" (measured: 3 passed, 3 skipped).
- States locate their surfaces from the QA dump, never by coordinates in `expect.toml`. Each run has its own HOME and
  XDG dirs; nothing touches a real profile; every timer is bounded.
- T9 for contract 01 is the first state: a new profile, Layout workspace, Cube active and selected. The outliner's active
  row sampled `#5a4720` (`accent_bed_hi`), its back `#161922` (`surface`), both exact. The first back sample landed on
  a `row_alternate` stripe (`#181b24`, inside the 2/255 tolerance by luck); the state now samples a row of the back's
  parity.
- Tests (6): skips loudly without a display; a planted off-token colour fails naming the surface and the token; T9
  passes; a 20 px shift of the outliner exceeds the 1 percent tolerance and an unshifted copy differs by 0; a missing
  golden fails by name; approving a golden is refused without `LAMPWAY_VISUAL_APPROVE=1`. Mutants: a tolerance that
  swallows everything, sampling without the y flip, a diff threshold that swallows everything: 3 of 3 killed.
- No golden is approved: approval is a person's act. The startup state checks tokens only until one is.
- Not built: section 14's busyness and parity scripts measure the mockups' HTML DOM (text runs, borders, glow from
  computed styles); an app-side count from the QA dump and the capture needs a mapping the contract does not give.
  Recorded, not invented.

## Contract 14: iconography

- **One sheet, one generator.** `scripts/dev/brand_art/icons/lampway_icons.svg` is the draft sheet from the spec (65 glyphs)
  plus what the native set and the cue table need and the draft lacked: the agent spark, the seven agent states
  (DESIGN.md 13: plain ring, static amber arc, dot at one o'clock, thick ring, dashed ring, check under a smaller flame,
  the wisp), the gauge in ten steps with its near (triangle) and over (cross) marks, the two frames of the sending wire,
  and Generate redrawn as an image frame with a plus. Those glyphs are mine, drawn to the sheet's construction; the
  contract's open question (a designer pass on optical weight at 16 px) still stands for all of them.
- `scripts/dev/brand_art/lampway_icons.py` writes the 42 native icons (`icons_svg/lampway_*.svg`, white strokes so the
  theme tints them), the generated blocks of `UI_icons.hh` and `editors/datafiles/CMakeLists.txt`, `generate.svg`
  (now a mono `DEF_ICON`), the Python previews (`mixar/modules/common/lampway_icons/<night|paper>/`, 32 px with the cue
  colour of each theme baked in, the agent states also at 16 px) and the acceptance sheets
  `docs/reports/facelift/icons_night.png` and `icons_paper.png` (every native icon at 16, 20, 32 px). Rasterised with
  ImageMagick's librsvg from the same SVG the build compiles (no resvg on this host).
- **Retired**: `sparkle.svg` and the four Mixar credit badges (`credits_*.svg`), their enums and CMake lines. The
  credits banner's three icon calls now use `LAMPWAY_COIN`, `LAMPWAY_ROUTE`, `LAMPWAY_SPARK`, `LAMPWAY_METER_10`; the
  banner itself is Mixar commerce (REBRAND D10) and is left for contract 13's decision.
- `mixar.modules.common.lampway_icons.icon_id(name)` gives a Python surface the coloured cue glyph for the current theme
  (Night on a dark canvas, Paper on a light one).
- Tests: `tests/lampway/test_lampway_icons.py` (8): I1 on the code (every `icon='LAMPWAY_*'` and `ICON_LAMPWAY_*` used
  exists), I2, I3, I4 (enum = SVG = CMake), I5 (retired gone, Generate not a wand), I6 (each preview's alpha mask is the
  native SVG at 32 px within 2 percent), the previews loader, generated = committed. Mutants: a deleted CMake line, a
  retired enum referenced, an unknown icon used, a preview from another glyph: 4 of 4 killed. The I1-on-code test
  passes vacuously until a surface uses a Lampway icon (contract 03 is the first). Real binary
  (`tests/lampway_tools/test_lampway_icons_live.py`): the build knows all 42 `LAMPWAY_*` icons and no retired one, and a
  preview loads (headless, an icon id needs a window, so the test reads the loaded image's size).
- The previews module was written before its test; I removed it, watched the test fail, and put it back. That is a
  test-after with an observed RED, not a test-first.
- Native rebuild: yes (UI_icons.hh is included widely: 1 123 steps).
- The build script's disk floor (100 GB free) refused the build: the shared disk had 79 GB free. I ran it with
  `LAMPWAY_MIN_FREE_GB=40` (an incremental build needs well under 1 GB); every later build in this report did the same.
- **Correction (`ba835be1`).** The 42 icons above never drew in the windowed app: the generated block sat after
  `DEF_ICON_BLANK(LAST_SVG_ITEM)`, and `init_internal_icons()` registers SVG icons only below that boundary, so each had
  an enum value and no icon ("no icon for icon ID: 1045" in every windowed log). The live test checked the enum only,
  which is why it passed. The generator now puts the block above the boundary; a unit test pins the placement (RED
  observed), and the visual harness fails any state that draws an unregistered icon (RED observed on the old build,
  1045 and 1046 = `LAMPWAY_WIRE`, `LAMPWAY_COIN`). Native rebuild: yes.
- **Correction (`edf0d549`).** Retiring the credit badges broke two tests I had not run
  (`tests/lampway/test_lampway_placeholder_art.py`), and `scripts/dev/lampway_placeholder_art.py` still wrote the four
  badges, so regenerating the placeholder art would have brought them back. The generator's badge table is empty,
  REUSE.toml and the test drop them, and a new test regenerates the art into a scratch tree and finds no `credits_*`
  file (RED observed: four).

## Contract 03: window chrome (`0afc2d19`)

- **Status bar** (`lampway_tools/ui/statusbar.py`, `statusbar_state.py`, `status_client.py`): a decision waiting for you
  first (lamplit, opens the first pending approval's confirm), the spend line with the ten-step gauge glyph, the wire chip
  (`local` / `N routes open` / `Sending to <route>`). draw() reads a cache; one timer fills it from `GET /app/egress`,
  `/app/spend`, `/app/studio` (0.5 s while a route is on, 5 s otherwise). A stopped server reads "spend unknown: server
  not running" and "egress unknown", never a stale number. Only the sending wire moves (two frames, 0.4 s), never under
  reduced motion.
- The bar is a **global area** (`Window.global_areas`), not in `screen.areas`: my first redraw walked the screen and so
  never repainted the bar. Found because the visual state could not find the area; RED observed with a unit test.
- **Server**: `GET /app/spend` (read-only): per provider its unit (USD for OpenRouter, credits otherwise), what this
  server session spent, and the caps and click rule. **There is no day ledger** server-side, so the answer says
  `scope: session` and the tooltip says so; DESIGN's "today" is not measurable yet. A day ledger is server work outside
  this lane.
- **Native**: the active tab is an accent underline on the canvas (`wcol_tab`, `interface_widgets.cc`); F6: the credit
  ring around the avatar is gone (`agent_ui_draw.cc`); the account card hides the identity behind a toggle ("Local
  account", `WindowManager.lampway_show_identity`); the glass tokens (cards, island, panel, pill) and the cinema pill
  come from the Night palette through the theme generator. Measured DNA re-dumped; the build is the fixed point
  (`--as-default` 938/938).
- Tests: `tests/lampway/test_statusbar.py` (7), `test_lampway_chrome.py`, `server/tests/test_spend_view.py` (2),
  `tests/agent_panel/test_agent_panel_glass.py` (two tests re-pointed from Mixar's glass values to the facelift rule).
  Visual (real build, Xvfb in the box): `status_local`, `status_open`, `status_sending` read "$0.31 of $5.00", "local" /
  "2 routes open" / "Sending to OpenRouter", "1 waiting for you"; the bar's back samples `canvas` exactly.
- Not done: the account card's action buttons (sign out, Providers) are labels in the mockup's place but not wired to
  new operators; the style block (12 pt Mixar vs Night's 11 pt) is still not compiled (open from contract 01).
- Native rebuild: yes.

## Contract 05: parallel agents (`c92396d5`)

- The Spark has seven states, each its own ring in theme colours, none animated (`agent_ui_pill_cat.cc`,
  `agent_ui_draw_spark`): queued, working (static amber arc on `line_hi`), unread (dot at one o'clock), blocked (accent,
  needs you), paused (dashed `muted_dim`, what it waits on underneath), done (`go` with the check), failed (`stop`, a
  red left edge, its reason or "failed: no reason given"). F9: the worker colour is a dot. The state word and an m:ss
  clock sit at the right.
- The chevron names what it hides ("4 more: 2 working, 1 done, 1 waiting"): `cards.overflow_label`, written by the
  Python mirror to `WindowManager.mixar_agent_cards_overflow`, read by the C++ draw and the QA dump.
- Mirror: BLOCKED and PAUSED come from the server's `needs` / `waiting_on`; `reason` passes through.
- Tests: `tests/lampway/test_lampway_agent_states.py`; visual `agent_cards_a` (blocked `#edb944`, working arc
  `#edb945`, failed `#f0766b`, the chevron text) and `agent_cards_b` (paused dash, done ring `#5bc48f`, queued ring),
  all within 2/255 of their tokens on the real build. The done card dwells 1.2 s then slides out, so that state
  captures after 0.75 s.
- Seen in the capture, not fixed: a paused card's clock reads `0:00` (the clock has no start for a paused card).
- Not done: the blocked and failed cards' action buttons ("Answer", "Retry") are words, not wired operators.
- Native rebuild: yes.

## Contract 02: splash and onboarding (`ce3c9897`)

- **Art**: `splash_v2.svg` rendered with the vendored Fraunces and IBM Plex (`scripts/dev/brand_art/fonts/`, OFL-1.1,
  annotated in REUSE.toml, licence in `LICENSES/OFL-1.1.txt`). librsvg drew tofu with woff2, so the renderer strips the
  SVG's text and draws each line with Pillow from the repo's font file; a face the repo lacks is refused. Each line's
  ink width matches its face's measure within 3 percent (the test measures the shipped PNG).
- **Version once**: the C++ label over the art is removed (`wm_splash_screen.cc`).
- **Menu** (`splash_menu.py`): four recent files, Start (New scene, Recover last session, Open in Zen / Engine), four
  glance cues read from the status bar's cache, one Help menu. No network in draw (tested with `urlopen` raising).
- **Onboarding** (`lampway_tools/onboarding.py`, no bpy; `lampway_tools/ui/onboarding.py`): Quick Setup is step 1 and
  its Continue opens steps 2-4 as dialogs on a rail of node icons. Routes start as the server has them (all off on a
  fresh install) and change only by the user's click, which is recorded. The last button names the outcome ("Continue
  with N route(s) on"), saves the preferences (`wm.save_userpref`, as before) and writes routes and caps to the server.
  Offline the steps say "Lampway's server is not running: Start it" and only the preferences are saved.
  Live: the dialog opens in the real build (Xvfb), offline, rail and message as designed. The online path is proved by
  the server test, not driven live.
- **Disagreements recorded, the brief followed**:
  - Step 2's refusal ("ChatGPT plan needs the chatgpt.com route: switch it on in step 3, or pick a local provider";
    the step stays) means a fresh install whose provider is a plan cannot reach step 3 without first picking another
    provider. The contract orders it so; a reader may want the refusal moved to the last step.
  - Caps: the contract asks for job, day and session caps; the server has no day ledger, so the walk sets job ($1),
    session ($5, D1's "per day" amount) and the click above $0.25, for OpenRouter (the only dollar provider).
  - The provider list is mine (contract 06's choice list is not built yet).
- Tests: `test_lampway_splash.py` (5), `test_lampway_onboarding.py` (8), `server/tests/test_onboarding_walk.py` (a
  fresh state dir, defaults plus one click: exactly that route on; falsifier "one route on by default" killed).
- Not done: test 6 (region diff of the splash against `shots/01-splash.png` and `shots/02-onboarding.png`): those are
  the mockups' HTML renders, and a Blender capture will not match them within the harness's 1 percent; it needs an
  approved golden of the app instead (a person's act).
- Native rebuild: yes (`wm_splash_screen.cc`, `splash.png`).

## Gate totals at the second push (contracts 03, 05, 02 and the 14 fixes; integration had not moved: `origin/lp/wave5` is still `00d907d4`)

- Server suite (`venv-tools`): 0 failed, 6 skipped, rc 0.
- Client, real binary (`tests/lampway_tools`, my Prod build with every commit above): 760 passed, 46 skipped, 0 failed.
- Client, host (the same command as the first push): 148 failing ids against the baseline's 132. The 17 new ids were
  read one by one: 5 were mine (two pill tests and three glass tests pinning Mixar's values that facelift 03 and 05
  changed: re-pointed to the tokens in `61bc6288`, a white rim mutant still killed); 11 are `tests/mcp/*` failing on
  `ModuleNotFoundError: jsonschema` (not installed on the host; files I did not touch); 1 is the gitignored `mixar.pot`
  being stale in this worktree (regenerated: `extract_messages.py --check` rc 0; nothing to commit). One baseline
  failure now passes.
- Visual harness (Xvfb in the build box): 11 passed (night startup, three status bar states, two card states, the
  harness's own falsifiers).
- Gates: theme 0, cues 0, WezTerm 0, icons (spec copy) 0; the pre-push PII gate runs on push.

## Coordinator's additions

### Asset Vault: the name and the drag (`d6b543fc`)

- The `MIXAR_ASSETS` Editor Type label and space name are "Asset Vault" (were Mixar's "Texturing Assets"); RED observed
  in a source test and in the real binary. The 49 `.po` catalogues still carry the old msgid, so the new label is
  untranslated until the catalogues are refreshed (`make i18n_update`, not run here: it rewrites every catalogue).
- Drag and drop, `space_mixar_assets/mixar_assets_dnd.cc`: after the Vault's panels lay out, each
  `mixar.asset_library_select` / `mixar.asset_library_place` button with an `asset_id` gets a named drag
  ("Vault Asset: <id>"); the 3D viewport, the node editor and a material slot take it through `LAMPWAY_OT_vault_drop`,
  which calls `mixar.asset_library_place`. Lane vault-ui's report names no drop operator; that is the one that places.
- **For lane vault-ui**: `mixar.asset_library_place` has only `asset_id`, so where the asset landed is lost. The drop
  passes it as `target_where` (asset_place's `target.where`: `cursor`, `object:<name>`, `slot:<object>:<index>`,
  `node_tree:<material>`) whenever the operator has that property: add `target_where: StringProperty()` and pass
  `target={"where": self.target_where}` when it is set. Until then a drop places the way the kind needs, at the default.
- Tested end to end under Xvfb with stand-ins for vault-ui's two operators (this branch does not carry them): a click
  on a tile selects it; a tile dragged onto the Cube places `a-42` on `object:Cube`. The node-editor and material-slot
  drops are built but not driven by a test.
- The region's draw used to lay the panels out a second time, which rebuilt the buttons without their drag; it now
  draws what the layout callback built (the upstream pattern).
- Native rebuild: yes.

### Zen shortcuts (vault-ui's finding, `8eac47fb`)

Not a keymap override. In Zen, N over the viewport toggles its sidebar and ctrl+alt+Space goes full screen (both
measured in the real build). Plain ctrl+Space does nothing because `screen.screen_full_area` itself returns CANCELLED:
Zen is a single-area screen and upstream refuses to maximise a singleton (`screen_maximize_area_exec`, #144740). No
code changed. Whether ctrl+Space should do something in Zen (full screen, say) is a decision, not a fix. The Vault
hotkeys vault-ui tried were not reproduced here: I do not know which keys or keymap they used.

### Queued (after contract 13, in this order)

The Connections window (`specs/connections/`), then Choices (`specs/choices/`, absorbing the Providers dialog), the
build rule that keeps `AGENTS.md` / `CLAUDE.md` / skills files under `src/` out of the installed app, and the report
cards' Workbench frame in contract 10.

### Lamplight and Workshop (the captain's rename, `c272b7c0`)

- Every user-visible "Zen Mode" / "Engine Mode" is Lamplight / the Workshop: splash, topbar toggle, mode menu and
  operators, workspace name, tooltips and notes, the tour's labels, the theme panel, the analytics allow-list, and the
  C++ that recognises the workspace by name (nine places). Internal identifiers stay.
- Existing files: `workflow/core/workspace_rename.py` renames a "Zen Mode" workspace to Lamplight on load (and once
  at startup for the startup file, which is read before the module registers). Tested in the real binary: the file's
  own workspace comes back as Lamplight with its contents. Renaming marks the file changed, so Lampway asks to save an
  old file on quit; I did not suppress that. The workspace's screen keeps its stored name ("Zen Mode"), which nothing
  displays.
- Gate: `tests/lampway/test_mode_names.py`. Allow-listed with reasons: the legacy name constant itself, and the
  account card's theme-profile style called "Zen" (Python and its C++ enum). That style is a different thing from the
  workspace; whether it becomes "Lamplight" too is the captain's call.
- Not renamed: the tour's recorded narration says "Zen mode" and "engine mode" (its subtitles transcribe the audio, so
  they still do); a world datablock named "Zen Sky"; log messages. The translation catalogues have the new strings
  untranslated.
- **Merge note**: the 48 `.po` catalogues are regenerated. On a conflict, take either side and run
  `scripts/i18n/extract_messages.py && scripts/i18n/update_catalogs.py`.

### The Zen keymap bug, with real input

Confirmed with real X input: xdotool against the app on my own Xvfb display, without `--enable-event-simulate`
(event simulation mode ignores real input, and the visual driver needs it for its Escape, so this run used a
standalone script). The run logged: N toggles the viewport sidebar (`false` to `true`), ctrl+Space changes nothing,
ctrl+alt+Space switches the screen to its full-screen copy. **Cause**: ctrl+Space runs `screen.screen_full_area`, which
returns CANCELLED in Lamplight, because Lamplight is a one-area screen and upstream refuses to maximise a single area
(`screen_maximize_area_exec`, Blender #144740). The keymap is fine and no shortcut is overridden. No code change; the
event-simulated test `test_zen_shortcuts.py` pins N and ctrl+alt+Space.

## Contract 04: the chat face (partial) and the captain's pill change

The chat lives in the floating island (`space_agent_bubble`; the docked chat editor is deprecated), whose transcript is
drawn by `space_mixie_chat`. Measured in the real build under Xvfb (the island is its own window; the states capture it).

Done:
- **Theme spacing** (test 1): bubble spacing and label height read the theme (Mixar forced 8 and 13 over it).
- **User card**: `raised` fill, 1 px `line` border, the corner nearest the composer tight (4 px), in place of the
  glass bed (`chat_ui_draw_user_card`).
- **Rules**: plan (todo), steps, images, thinking and live blocks carry a 3 px rule in the theme's `agent` (dusk), the
  agent's prose too. The running step's glyph is the theme accent; **Mixar's green live accent is gone from the chat
  blocks**, but it is still in `CHAT_ACCENT_LIVE` for the history overlay, the rules editor and the ink overlay
  (not the chat face; recorded, not changed).
- **A question waiting** (choices): lamplight behind the set, a `line_hi` rule beside it, the primary choice an accent
  fill with `on_accent` text (also on hover), danger choices in the theme's `stop`. Visual test
  `tests/lampway_visual/test_chat_face.py`: the primary choice samples `#edb944` (accent). That test was written after
  the code: its RED was not observed.
- **Price chips** (test 2): `lampway_tools/price_chips.py` words each kind (`≈ $0.07 est., openrouter.ai`,
  `13.5 credits, read back from Tripo 14:32`, `$0.05 billed`, `local, no cost`); the slot processor writes them into
  each plan step (`price_text`) and the native row prints them after the step. **Words only**: the dashed / solid /
  filled chip shapes are not drawn in plan rows (they are on the empty state's estimate chips).
- **Route line** (test 3): `lampway_tools/route_line.py` + `chat_route.py`; the status timer writes host, sentence and
  `send_ok` into the WindowManager, the island draws the host beside Send, Send's tooltip is the sentence, and with
  the provider's route off Send is disabled and `mixie_chat.send_message` refuses before the server is asked. An
  unknown provider or a silent server never reads as "this machine". Found by the visual probe: the Send button kept a
  pointer to a per-draw buffer as its tooltip (garbage in the QA dump); it now points at storage that outlives the
  draw.
- **Empty state** (test 4): the brand line ("Ask Lampway Agent anything. Plans, questions and spends wait for you.")
  in Fraunces 28 (vendored into `release/datafiles/fonts/`, OFL-1.1); the two GENERATE prompts carry a dashed estimate
  chip from the generation catalogue's credit cost, or "spends credits: priced first" when it has none. Test written
  after the code; the chip call was mutated out and the test failed.

Not done (contract 04): the who line (Spark 20 px, name, plan chip, mono time); the calm pass's collapses (an answered
question as one line, the step log as "3 steps done, 1.5 s, local"); the lamp glyph for local steps; test 6 (region
diff against `shots/04-chat.png`, a mockup render; needs an approved golden of the app).

### The floating agent pill (the captain: "toggleable, off by default or just combined into the chat window")

Both, as the coordinator asked. The pill was a second always-on-top window created with the chat, sitting above it
(`agent_bubble_show_window_exec`), and the chat's minimised form.
- Preference "Floating agent pill" (Preferences > Interface > Agent), a persisted config key, **off by default,
  existing users included**. Off: no pill window is created; minimise (Escape, the yellow light, Ctrl+Shift+B) closes
  the chat; the workspace switch and the tour no longer bring a pill back; the native minimise refuses. Turning it on
  reopens the open chat with its pill at once.
- What the pill showed now lives in the chat's own header band (painted natively: the Spark in its contract 05 state,
  the activity word or state name, "N agents running", "N jobs") and, while the chat is closed, in a top-bar agent chip
  that opens it (state glyph, the pill's status words with the queue clock, agents running, "N unread").
  `docs/reports/facelift/pill_parity.md` lists every datum and where it went.
- Existing users: a one-time note replaces the header cues until the chat first closes ("No floating pill: its state is
  here (Preferences > Interface > Agent)").
- Tests: `tests/lampway/test_lampway_agent_pill.py` (6: off by default, on shows it, the switch and the tour with the
  pill off, close and reopen, the parity of header and chip, told once) and the real-build
  `tests/lampway_visual/test_agent_pill.py`: a new profile has the chat and no pill; Ctrl+Shift+B closes it and the top
  bar's chip appears; Ctrl+Shift+B opens it; the preference gives the open chat its pill; minimising then rests in the
  pill. RED: the probe on the build before the gate showed the pill window (94 x 26) at startup.
- Reading the coordinator's words: "the chat window" is the island. The pill's sketch draft (typing over the viewport
  while a sketch is armed) was not driven with the pill off; the composer shows the same draft, but only a live run
  proves the flow.
- Native rebuild: yes.

## Contract 06: the Studios panel (the Providers half moved to Choices)

`specs/choices/facelift_06_amendment.md` (the captain's CH8): Choices absorbs the Providers dialog, so 06 keeps the
Studios panel only; the Providers dialog is untouched until the Choices window replaces it.
- A waiting spend is a card: what, the price read back and from which Studio, a **"Spend 13.5 credits"** button (the
  number on the button, on its own row so a narrow sidebar never clips it: measured clipped in a popover before) and
  "Not now". It is the panel's one glow.
- A job Lampway cannot account for (`submission_unknown`) shows "maybe sent" with the user's two ways out, **"It did
  not run"** and **"Link its job id"** (a dialog asks for the provider's job id), visible and not glowing, against the
  integrator's routes (`GET /app/receipts`, `POST .../acknowledge`, `POST .../link`, sent with `"by": "user"`). This is
  also the coordinator's contract 13 addition (the spend surfaces' submission_unknown UI); contract 13's own card will
  reuse it.
- The plan form has typed rows (name, kind: text / number / file / yes-no, value) instead of a JSON field, and is
  closed by default; `plan_args()` turns them into the action's arguments (a file is project-relative).
- Tests: `tests/lampway/test_lampway_studios_face.py` (4, RED observed: the panel read `studio_args`) and the real-build
  `tests/lampway_visual/test_studios_face.py` (the real panel's draw code, as a popover: the sidebar's tab cannot be
  chosen from Python).
- Not done: the accounts lines (name and route; their state belongs to Connections now, the Connections amendment);
  the per-action schema the contract imagined does not exist server-side (the actions list is id and label only), so
  the rows are typed by the user, not generated; `test_providers_entry_opens_choices` waits for the Choices window.

### The visual harness after the integration merge
The integration's root `conftest.py` now points HOME and the XDG homes into the basetemp for every test. Rootless
podman reads its container store from the person's home, so every windowed state failed with "no container
lampway-build". The harness gives the display runner (only) the person's home back; the build inside still gets the
run's own HOME and XDG homes from the `env` in front of it. The Asset Vault drag state now always registers its
stand-ins (vault-ui's real operators are in the build since the merge) and drags its own tile by name.

## Contract 07: the Way (partial)

- **The Way**: a "The way" parent panel ("<piece>: 2 of 7 done") and one panel per step of the captain's piece runbook
  (BUILD_ORDER.md Wave 2), in his order: Seeds and plates, UV score, Mesh QA, Parts critique, Mesh-paint texture, Fit and
  openings, Bind and export. Each header carries the node for this piece (contract 14's `node_lit` / `node_half` /
  `node` previews; the done steps are a custom property on the object, written when a step's tool succeeds) and the
  tool's word (Live, Built, Partial, Planned) at its right.
- **Status words with sources**: `lampway_tools/status.toml`, every live / built / partial word names the report that
  measured it, and the test checks the file exists. The words are measured, not the mockup's: Mesh QA is Live
  (reproduced the recorded runs and ran in the app, `tools.md`); Mesh-paint is Partial (the live image generation has
  not run); Seeds and plates Partial (Studio drivers dry only); Fit and openings Partial (fit_place / fit_pose /
  fit_openings not ported); Bind and export Partial (auto rig and the export bundle built; the UE bind is Wave 3). The
  mockup had Seeds and Mesh-paint Live and Bind Planned.
- **No free-text runner**: the "Parts and proportion tools" and "Features" panels (a tool name plus free-text
  arguments, a feature plus JSON) are gone. Each tool is one operator with its own typed properties
  (`ui/operators/tool_ops.py`), generated from `tool_specs.json`, which `scripts/lampway/facelift/tool_specs.py`
  generates from the agent's own tool definitions (`server/.../agent/lampway_tools.py`), so the form and the agent's
  schema are one thing; a batch tool's command line is built exactly as the server builds it for the agent. Run opens
  the form as a dialog.
- **No work in a draw**: Review proposals reads a cache a timer fills (it called `api.qa_proposals()` on every redraw).
- The last result is one line with a "more" popover.
- Tests: `tests/lampway/test_lampway_the_way.py` (8; RED observed) and the real-build
  `tests/lampway_visual/test_the_way.py` (registered in order, the typed Retopology form's property kinds, the
  free-text panels gone, and a real Retopology run on the Cube from the typed operator marks UV score done).
- **Lost from the UI, said plainly**: 13 batch tools have no typed definition in the agent's registry (uv_score,
  bake_maps, material_bake, clay_view, mesh_paint_set, relief_project, material_masks, uv_patches, patch_holes,
  render_textured, asset_catalog_export, robust_weight_transfer, mesh_qa as a batch). The free-text runner reached them;
  the Way does not. The agent still runs them (`lampway_run_tool`). Each needs a `Def` in the server's registry (not
  this lane's file) to get a form here.
- Not done: the Mesh QA body's redesign (result box with run line, tag counts on one row, "Review 17 by hand" and "Ask
  the agent"); the drawn rail (phase 2, C++); test 6 (a sidebar capture: the sidebar's tab cannot be chosen from
  Python, and child panels do not draw in a popover); the workflow picker (open question 1).

## Contract 08: the generation face (partial)

- **Server** (`POST /app/generate/estimate`, `JobQueue.estimate`, `VideoSystem.listing_estimate`): before anything is
  sent, the price of a request marked as the kind of number it is, the policy the Providers dialog set, whether it needs
  a click and whether a cap refuses it. It sends nothing: an OpenRouter video is priced from the model listing the
  server already read (`pricing_skus`, the same `videogen.estimate` a real run uses; the source says the date the
  listing was read); an image is the measured per-image figure the click decision already used
  (`IMAGE_USD_ESTIMATE`, about $0.07); a Higgsfield price is unknown until its own `get_cost` at submit (no upload is
  made for an estimate). An unknown price needs a click unless the policy is off. Tests:
  `server/tests/test_generate_estimate.py` (6; RED observed: every route 404).
- **The face** (`lampway_tools/generate_face.py`, no bpy, no price arithmetic): the dashed estimate chip
  ("≈ $0.067 est."; a quote reads "$0.40, read back" with neither mark; none reads "price unknown" in the stop colour),
  the job against its cap ("≈ $0.07 of cap $1.00 per job", amber from 80 percent, red over), the session line, the
  route host, the content ("prompt only, no asset" / "prompt and 2 reference images"), the button
  ("Generate, ≈ $0.07" / "Spend $0.40" / "Spend, price unknown" / disabled "Generate") and the policy sentence as its
  hover. A route that is off asks the server nothing and refuses with the egress gate's own sentence ("openrouter is
  off: switch it on in Privacy to let data leave").
- **The pump** (`ui/generate_pump.py`): the island's half and its request (service, model, the catalogue params via
  `collect_params`, the reference images counted the way the pane previews them); 300 ms debounce, the request off the
  main thread, the answer through a timer into `wm.lampway_gen_*`. **Generate refuses** in
  `mixie.moodboard_prompt_generate` (the island button and Enter) before it dispatches, only for the tab the face was
  computed for (a 3D or Splat Generate is never judged by it).
- **Native** (`agent_ui_tabmedia.cc`, new `agent_ui_tabmedia_estimate.cc`): a "Before you send" column on the right of
  the Image / Video pane when it is at least 560 px wide (the chips and prompt box take the rest), numbers in IBM Plex
  Mono (vendored as `datafiles/fonts/PlexMono.woff2`, OFL), Generate at its foot. Generate is the lamplit bed
  (`accent_bed_hi`); a Spend is the accent fill: a new `MixarVariant::Accent` (accent fill, on-accent text; QA dump
  name `ACCENT`). Narrower panes keep Generate in the box with the same label.
- **The prompt library**: a `UIList` (`LAMPWAY_UL_prompt_library`) over `scene.lampway_tools.prompt_library`,
  mirrored by Refresh from `/app/prompts` and `/app/prompts/stats`; filter All / Image / Video with counts; rows are
  name, version and mean billed price ("no runs yet" before the first run); runs and rating are the price's hover
  (the calm pass). Choosing a row chooses the template. The eight cut preview labels are a popover with the whole text.
- Tests: `tests/lampway/test_lampway_generate_face.py` (10; RED observed: the module missing, then the panel test
  failing on the old panel; a mutation treating an unknown price as no click fails `test_unknown_price_needs_a_click`)
  and `tests/lampway_visual/test_generate_face.py` (three policy states in the real build: no click, click, refused).
- **Disagreements with the brief, recorded**: the brief's "18 built-ins (7 video, 11 image)" is the WEBSITE.md
  snapshot; the server ships 27 (19 image, 8 video) and the test checks every one it ships. The brief's image source
  "model listing <date>" is not what the number is: OpenRouter lists image models by token, and the figure is the
  spike's measured per-image cost, so the source says that. The WindowManager carries more than the five named props
  (`_estimate`, `_cap_job`, `_cap_session`, `_route`, `_content`): also the kind, the fills, the button, its kind, the
  policy, the refusal and the owner tab.
- **Not done**: the A/B action (the run log has `variant_of`, no surface submits a variant yet); the results row's
  "billed against the estimate" line; Spend opens the server's approval (the Studios card) rather than contract 13's
  card (13 is later in the order); the pump's own request gathering is not exercised by a test (the visual states fix
  the request: offline there is no catalogue to give the tab a model); acceptance evidence 11 (a real OpenRouter image)
  is a spend this lane does not make.
- Also re-pointed `tests/lampway_tools/test_ui.py::test_the_features_panel_runs_a_feature_on_the_active_object_and_reports_one_line`:
  it asserted the free-text Features panel exists, which contract 07 removed on purpose; it now asserts it is gone (the
  `lampway.feature_run` operator it drives is kept for scripts and still passes its three cases).
- Gates before the push: `scripts/lampway/test_all.sh` on the uncommitted 08 tree with my build: server 1233 passed,
  10 skipped, rc 0; client 8177 passed, 89 skipped, 119 failed + 20 errors, all 138 in `tests/known_red.tsv` and one
  new (the Features-panel assertion above, fixed and re-run: passes). Visual suite (`tests/lampway_visual`) 20 passed.
  Theme 0, cues 0, WezTerm 0, tool specs current.

- After merging `origin/lp/wave5` (`5e5cf3e`): the agent gained seven tools (the orphans lane's O33). `tool_specs.json`
  regenerated (30 tools); five join Parts critique with their own word, Built, sourced to `docs/reports/orphans.md`
  (judge_pack, render_final, export_parts, verify_set, gen_parts_table); libwiki and index_delta are library chores,
  listed in `status.toml`'s `[off_the_way]` with the reason. New gate `test_every_tool_has_a_place` (RED observed: the
  seven were simply absent from the sidebar and nothing said so).

## Contract 12: the privacy face

- **One vocabulary** (`lampway_tools/privacy_face.py`, no bpy): `chip(route, routes)` is the lamp and "this machine",
  or the wire and the route's host; an id no table names says "unknown route" in stop, never blank. `route_rows`: the
  name, a shield for the privacy class (shield, half, open, unknown), the switch (off, waiting for your confirm, on);
  host, last use, retention and training on hover. `last_refusal`: the newest refused row as a card; a private asset
  gets "Use OpenRouter, zero retention", "Run it here instead" and "Allow this asset once (logged)". `log_rows`: time,
  event (glyph + word), route, what; host, class and retention on hover. It reads only the keys it names, so a row
  carrying content renders none of it.
- **The window** (`ui/privacy.py`): one drawing in three places: the viewport sidebar, a pop-out the status bar's wire
  chip now opens ("What leaves this machine"), and Preferences > Interface > Privacy (open question 1, as
  recommended). "Sending now: <host>" with the wire's dot while data leaves (decision F3: the magenta wire and the word,
  not a red DATA LEAVING), the latest refusal, the routes, the confirm row, the log, Export.
- **Two clicks to open a route**: the switch opens the confirm row ("Let data leave for openrouter.ai?"); only its
  "Let it leave" posts. Both refuse while a script runs ("A script cannot open a route: switch it on in Privacy
  yourself"), as does the override (`POST /app/egress/override`, new `EgressClient.override`). The confirm row is the
  only lit thing in the window: an open route is a plain switch (the visual test samples both).
- **The wire is reserved**: the theme mapped Timeline/Dope Sheet `simulated_frames` to the wire; it is now the agent
  violet (`agent@66`), and a gate scans the theme map and the icon renderer (only the travelling dot's two glyphs are
  painted in it). Native: the regenerated `userdef_default_theme.c` and the presets; `base/theme_dna_0.1.0.json`
  re-measured from the rebuilt binary.
- **New route `github`** (server `egress.py`: github.com, objects / release-assets.githubusercontent.com), off by
  default, class ok (a plain GET of a public release asset), for contract 16's WezTerm download.
- Tests: `tests/lampway/test_lampway_privacy_face.py` (6; RED observed: the module missing, the `github` route
  missing, and the wire test catching `simulated_frames`), `tests/lampway_tools/test_lampway_privacy_face_live.py`
  (4, real binary; the gate's falsifier run: with the gate dropped, `test_route_switch_refuses_a_script` fails),
  `tests/lampway_visual/test_privacy_face.py` (the pop-out with a route sending, a refusal and a confirm row).
  `tests/lampway_tools/test_wave4b_egress_ui.py` re-pointed to the new surface (the panel moved to `ui/privacy.py`;
  "OpenRouter: OFF" and the policy line became the row and its hover; DATA LEAVING became "Sending now"; switching on
  is two clicks).
- **Deviations, said plainly**: "Allow this asset once (logged)" is an `alert` button, which Blender draws as a red
  tinted bed, not stop-coloured text on nothing (a Python layout cannot colour text otherwise). "Run it here instead" is
  a line of text, not an action: there is no generic local re-run of a refused job to call. The other surfaces'
  host words (04's route line, 08's route chip) say the same host but do not yet call `privacy_face.chip`.

## Contract 13: the spend card (P0, the Python card)

- **One card** (`lampway_tools/spend_face.py`, no bpy; drawn by `lampway.studio_confirm`'s popup): the action, who
  planned it ("planned by the agent, only your click spends" for an agent or a worker), the price with its kind
  (quoted for a Studio / Higgsfield read-back, estimate for an OpenRouter listing price, "price set by the model" for an
  OpenRouter image), where it was read, the caps as meters from `/app/spend` with the pending amount apart from what is
  used ("this job 18 of 40", "session 31.5 + 18 of 200"; the used part turns stop over 90 percent), the route chip
  (contract 12's vocabulary), the uploads, and `Spend 18 credits` / `Not now`. `invoke_props_confirm` is gone: the
  card is `invoke_popup` with no default button, so Enter has nothing to press; Spend is the card's own button
  (EXEC), the script gate and the server's price check unchanged.
- **States, one row each** (the calm pass): over the per-job cap, past the session cap, the price changed (its new Spend
  button stays visible), an agent or script tried, expired, spent (its job id, "never resubmitted"), and any other
  refusal as "This spend cannot go ahead: <reason>", never blank. A refused confirm reopens the card in its state; a
  confirmed one reopens it as spent. Detail and fixes open in place.
- **Every source opens this card**: the status bar's waiting chip and the Studios panel's Spend invoke it; a generation
  (08) or a chat plan that needs a click becomes a server approval that waits in both. `studio_ops.py` is the only file
  that confirms (a test scans for any other).
- Tests: `tests/lampway/test_lampway_spend_face.py` (6). **RED honestly**: only `test_enter_does_not_spend` was observed
  failing before its code (the popup and the source scan); the other five were written with `spend_face.py` in the
  same step, so I mutation-checked them instead: the button saying "Spend" alone, the origin dropped, the stop tone
  dropped and a blank unknown-state title each fail their test. `tests/lampway_visual/test_spend_card.py`: the card
  waiting and in the five states in the real build (written after the card: they passed on their first run).
- **Not done**: the P1 drawn card (C++: Fraunces price, accent left rule, hatched pending segment); the price is a
  label row, not a large figure (a Python layout cannot size a font). The server's approval carries no uploads or
  read-at time, so the card says "uploads: not reported by the server" and "Read back from <studio>" without a time.
  The day cap is the server's session cap (Lampway keeps no day total), and the card says so.

## Coordinator addition: the Connections window (P0, `specs/connections/connections_face.md`)

- **Against the contract, not yet the server**: the hub's routes live on `origin/lp/connections` (`connections/routes.py`),
  which `origin/lp/wave5` has not merged; the client speaks those routes (`connections_client.py`, read from that
  branch's code) and every test uses a fake client. Nothing was run against a live hub.
- **Words and cues** (`connections_face.py`, no bpy): one glyph per state, readable in greyscale (connected, connected
  with a warning, not checked, signed out, expired, not connected, error, and the hand for a sign-in waiting on the
  browser, the only lit row); "route off" is the route column and a word on hover, never a colour on the glyph; the
  one action that clears the state (Test, Sign in with <label>, Paste a key); the list in the contract's group order
  with source and check age on hover; Sign out only for a login Lampway holds, Forget only for a key or pointer it holds.
  It reads only an allow-list of view fields, so a planted secret in any other field never reaches a word. The cue
  family is in `tokens.json` (`check_cues.py`: rest state "connected"; the warning row is coloured by its accent
  triangle, which is the distinguishing mark) and the eight glyphs are preview-only icons rendered by
  `lampway_icons.py` from the sheet (new symbols `ring-open`, `ring-dashed`, `tri-small`; no native rebuild), plus a
  `plug` preview.
- **The window** (`ui/connections.py`): a pop-out and Preferences > Interface > Connections, one drawing; the status
  bar has a plug beside the wire chip that opens it (server up or down). The pasted key is a WindowManager
  `PASSWORD`, `SKIP_SAVE`, `HIDDEN` field, emptied after the request whatever it returned; refusals are drawn under the
  field; every write refuses while a script runs; the window links to Privacy and has no route switch.
- Tests: `tests/lampway/test_lampway_connections_face.py` (10; RED observed: the module missing, then the route word,
  the foot rule), `tests/lampway_tools/test_lampway_connections_live.py` (5, real binary; mutation-checked: without
  the `finally` the secret-cleared test fails, without the gate the script test fails),
  `tests/lampway/test_statusbar.py::test_the_plug_beside_the_wire_chip_opens_connections` (RED observed), and
  `tests/lampway_visual/test_connections_window.py` (a missing row with the paste field, which the QA dump reports as
  secret; a sign-in waiting).
- **Not done**: test 9 (an agent card's `needs_connection` button: the cards are native, contract 05); the expander's
  Used by, other sources, history and Rotate (only Move into keyring is there); the Studios accounts lines and the
  Privacy rows reading Connections; the splash's fifth cue; captures against `mockups/16-connections.html`.

## Coordinator addition: the Choices window (P0, `specs/choices/choices_face.md`; CH8 and CH1 as ruled)

- **Against the contract, not yet the server**: like Connections, the Choices routes are on `origin/lp/connections`
  (`choices/routes.py`, `views.py`), not in `origin/lp/wave5`; `choices_client.py` speaks them and every test uses a
  fake client.
- **CH8, Choices absorbs Providers**: `lampway.providers_open` (the Studios panel's button, now "Choices: agent, images,
  video, spending", and the splash's row, now "Choices and privacy") opens Choices on Agents. The old dialog is kept as
  `lampway.providers_dialog` for two uses only: Choices' "Change spending" (the spend rows' existing write path), and a
  server that has no Choices yet (an HTTP 404), where the window says so and offers it, so nothing is lost before the
  server lands. Spending is the list's last row: each provider's click rule, caps and session spend from `/app/spend`.
- **Words and cues** (`choices_face.py`): a diamond per purpose (preferred filled, fallback half, override dotted,
  blocked crossed, not chosen dashed) and the hand for a waiting proposal, the one glow; the reason word ("fallback:
  studio:tripo is off", "this project", "not chosen yet", "nothing can run: ..."); each option's six facts (where it
  runs, its connection's glyph from the Connections family, cost on hover with the date it was measured, retention:
  lamp local, shield zero retention, eye "kept by the provider: terms unread", quality); a skipped option's reason and
  its one fix (Open in Privacy, Connect <label>). The `choice` family is in `tokens.json` (`check_cues.py` passes;
  its "waits for you" now counts as waiting for C3), the five diamonds and the eye are preview-only glyphs.
- **CH1, the eye**: an option acknowledged for private content carries the eye; clicking it takes the acknowledgement
  back (`POST /app/choices/acknowledge` with `private: false`); a kept option not yet acknowledged offers "Allow private
  content to <option>".
- **The window** (`ui/choices.py`): pop-out and Preferences > Interface > Choices; the chain reorders with up / down
  (a PUT of the new preferred and fallbacks); proposals are accepted for this project or all projects, or declined;
  "Use yours again" clears a project override. Every write refuses while a script runs; nothing here switches a route
  or touches a connection.
- Tests: `tests/lampway/test_lampway_choices_face.py` (8; RED observed: the module missing, the window file missing),
  `tests/lampway_tools/test_lampway_choices_live.py` (3, real binary: draw pure, the not-running and no-Choices rows,
  the script gate (its falsifier run: dropping the gate fails it), reorder, accept, the Providers button),
  `tests/lampway_visual/test_choices_window.py` (a fallback purpose with a waiting proposal and the eye).
- **Not done**: test 7 (`needs_choice` on an agent card: the cards are native); test 9 (`mockups/parity.py`
  extended to 17-choices); params as typed fields and the scope switch (the window shows scopes and clears an
  override, it does not edit params); the expanders (override policy, recent jobs, quality records, closed
  proposals); "Add an option"; the Connections window's "Used by" linking here.

## Coordinator addition: the install carries no agent contract

- The installed app had `scripts/mixar/modules/lampway_tools/AGENTS.md` and `CLAUDE.md` (the rail's contract files).
  `src/source/creator/CMakeLists.txt` now excludes `AGENTS.md`, `CLAUDE.md`, `SKILL.md`, `.agents` and `.claude` from the
  scripts install, and an `install(CODE)` step removes any an older install still has (an install over an install keeps
  what was there). `scripts/lampway/sync_python.sh` excludes the same names and deletes them from the target, with the
  install's own `_build_env.py` and caches protected.
- Tests: `tests/lampway_tools/test_install_has_no_agent_contracts.py` walks the installed tree of the build under test
  (RED observed: the two files), and `tests/lampway_tools/test_sync_python.py::test_sync_does_not_ship_agent_contracts_and_takes_old_ones_out`
  (written after the sync change; its falsifier run: without `--delete-excluded` it fails).
- Native: the CMake change needs a re-configure and an install (no compile).

## Contract 11: the model-compare window (partial)

- **The window exists now** (`ui/compare.py`, section 6.4 of `mrmak/05`, the local-view path): `lampway.compare_open`
  loads a built set (`compare.json`, the files' own statistics, `numbers.json` when the numbers ran), opens a new window
  on the scratch scene `LW_Compare`, splits its 3D view into one equal column per model (each split leaves 1/n), and
  puts each column in local view of its own model. The probe the feature's docstring was waiting for ran in the real
  build: four views, each local, each in Wire (`tests/lampway_visual/test_compare_window.py`).
- **The overlay** is one `POST_PIXEL` handler: a compare area draws its alias large and, while blind, "name hidden";
  any other area draws nothing. A test records every `blf.draw` argument before and after the reveal (falsifier run:
  an overlay that ignores blind fails it). Labels come from the sealed file only through `reveal`, after a pick.
- **The panel** (sidebar, tab Compare, in every compare view): the mode bar with its keys (1 Wire ... 7 ORM), Sync, Spin,
  the blind state, per view the alias, Pick and its strip (triangles; vertices, quad status, largest texture; channels
  as words, a missing map in stop with a cross: "no normal map baked"), the pair table (pair, worst-view IoU, interior
  difference lit above 0.05) and the blind pick ("Reveal without picking"). Pick records the user's decision through
  `model_compare.record_pick` (refused while a script runs) and reveals. Cameras follow one another on a 100 ms timer.
- `compare_face.py` (no bpy) holds the words; `tests/lampway/test_lampway_compare_face.py` (5; RED observed: the
  module missing).
- **Not done**: the data modes (Base colour, Normal map, ORM) are drawn disabled with "not built yet": they need the
  replacement materials of section 6.5; Spin does not turn the views; the header Pick buttons are in the sidebar panel,
  not the area header; Fraunces / Plex Mono in the overlay (the default face); the capture against `shots/12-compare.png`.

## Contract 10: the cockpit window (the browser fallback beside 16), with the report cards mounted

- **The page** (`server/lampway_server/web/workbench/`: `index.html`, `cockpit.js`, `cockpit.css`, and `tokens.css`
  GENERATED by `build_theme.py` from `tokens.json`, so the browser window and the Blender UI share one source): served at
  `/app/workbench/page` with a CSP that allows this origin only (frames: the loopback cards origin), its assets from a
  whitelist at `/app/workbench/static/<name>`, its data from `/app/workbench/view` behind the bearer. The bearer rides in
  the URL fragment, which a browser never sends to a server, and goes only into this origin's Authorization headers.
- **What it shows**: sessions with a Spark per state (working, waiting, unread, idle, ended), the selected session's
  screen (polled, `textContent`, never parsed as HTML), the input and Stop (Stop asks), the Agent sends switch (off by
  default, the server's record), the reconcile banner on `agent_bed` ("4 sessions re-adopted with their state. 1 pane
  is not ours: left running, never typed into.", with "Nothing was restarted, nothing was killed." in its tooltip), and
  a "not adopted" row for each pane Lampway did not create, with no input and no Stop. Those rules are the server's
  (`workbench_view.py`); the page only draws the flags.
- **The report cards** (coordinator's addition g, vault-ui's "ready but not mounted" frame): the page lists `/app/cards`
  and mounts the chosen card from `/app/cards/{id}/open` in an iframe on the cards' own origin with the same sandbox as
  mrmak 09's frame page.
- **In Blender**: the Sessions panel rows carry the Spark previews (contract 14's agent states), and "Cockpit window"
  opens the page in the browser.
- Tests: `server/tests/test_workbench_page.py` (6; RED observed: the module missing): tokens.css equals tokens.json, the
  banner sentence (and its singular), an unadopted row with no input or Stop, Agent sends off by default, the page's
  CSP and no URL other than loopback in its files, the view behind the bearer and the cards mounted;
  `tests/lampway/test_lampway_cockpit_face.py` (2; RED observed). `tests/lampway_tools/test_wave3b_cockpit_ui.py`'s
  recording layout now takes the row's `icon_value`.
- **Not done**: xterm.js (the pane is the CLI's text, polled; vendoring a third-party terminal is not this lane's call),
  the History search and Resume, the vendored Fraunces / Plex Mono in the page (system faces), test 5's headless-browser
  network log (a static scan of the files and the CSP instead), and the page captured against `shots/11-cockpit.png`.

## Contract 16: the Lampway terminal (partial)

- **Server add-on** (`server/lampway_server/addons/wezterm.py`, pins in `lampway_terminal.toml`, the config a generated
  copy of `theme/lampway.wezterm.lua` written by `build_theme.py`): Get is refused before any request while the `github`
  route is off ("github.com is off: open it in Privacy to download the Lampway terminal (about 49 MB); nothing was
  sent"); the download streams to a `.part`, its SHA-256 must equal the pin AND the release's published `.sha256`, and
  its size the pinned size; redirects are followed one hop at a time so every host passes the egress gate and is
  logged; only then it is moved into `$LAMPWAY_HOME/addons/wezterm/<version>/` with WezTerm's `LICENSE.md` and a
  `PROVENANCE.json`. Launch: `--config-file <Lampway's lua> start --always-new-process --class dev.lampway.terminal
  --workspace lampway`, detached in its own session, the isolated herdr environment, and every directory WezTerm uses
  (HOME, XDG_RUNTIME/DATA/CONFIG/CACHE/STATE) under `$LAMPWAY_HOME/wezterm/`. The CLI always carries the class,
  `--no-auto-start` and Lampway's own GUI socket; [removed later: send-text, focus and the pane registry, see "the
  viewport correction" below]; reconcile
  re-adopts through the recorded pid and `cli list` and spawns nothing; Remove signals only the process group Lampway
  started. Routes `/app/terminal` (status), `/get`, `/open`, `/remove` behind the bearer, an agent origin refused.
- **In Blender**: the Sessions panel's "Lampway terminal" box: "not installed (Get downloads about 49 MB from
  github.com)", Get, then Open (placed just right of Blender's window) and Remove, each the user's click.
- **Live, measured** (2026-10-06): the one allowed download of the pinned release into a scratch Lampway home through
  the github route (`server/tests/test_terminal_live.py`, opt-in): PROVENANCE `{"version": "20240203-110809-5046fc22",
  "sha256": "34010a07...56c60f0", "bytes": 49505472, "verified": true}`, `LICENSE.md` beginning "MIT License /
  Copyright (c) 2018-Present Wez Furlong". The real window on the build box's own virtual display: its GUI socket in
  Lampway's runtime directory, `cli list` answering, the bootstrap pane recording `$WEZTERM_PANE` and
  `$WEZTERM_UNIX_SOCKET` (the spec's [UNVERIFIED] that the GUI exports the socket into panes: it does), reconcile
  re-adopting twice with the same answer.
- **Incident, said plainly**: my first live GUI run gave the WezTerm processes the person's HOME. A `cli` call that
  found no window auto-started `wezterm-mux-server`, which locked and wrote `~/.local/share/wezterm/pid` (8 bytes, its
  own pid, 12:11:15) and ran about six minutes until I stopped it by verified PID. It did not touch `~/.wezterm.lua`,
  `~/.config/wezterm`, the captain's GUI (pids 6497/6500, same uptime before and after) or his GUI socket; no mux
  socket was left in his runtime directory. The stale pid file still names that dead pid: I did not touch it again.
  The fix is in the code and pinned by `test_user_config_untouched` (RED observed): every WezTerm directory is
  Lampway's own, and the CLI never auto-starts a mux server.
- Tests: `server/tests/test_terminal_addon.py` (11; RED observed: the module missing, the redirect hops, the dirs;
  falsifiers run: skipping the checksum or the route check fails its test), `tests/lampway_tools/test_lampway_terminal_ui.py`
  (1, real binary), `tests/lampway/test_lampway_cockpit_face.py::test_the_terminal_opens_beside_blender`.
- **Not done / found**: the vendored Plex Mono is woff2, which WezTerm 20240203 does not load: the window shows a
  "Configuration Error" pane and falls back (it needs the OFL TTF vendored; no converter here). The bootstrap's
  `herdr session attach lampway` (replaced by plain `herdr`) and [removed later: one tab per agent] were not run live;
  tests 6, 7, 9 and 11 (SIGKILL survival, persistence through herdr, images, the fleet socket) were not run; the
  Ctrl Alt T key and Update were not built then (built later; Focus and the state file were built and then removed: the
  viewport correction below).

## After the merge that brought the hub (`d2b142e`: lp/connections is in lp/wave5 now)

- `server/tests/test_facelift_faces_on_the_real_hub.py` runs the real `/app/connections` and `/app/choices` answers
  through the windows' own words (`connections_face`, `choices_face`, loaded by file). Two things the contracts' words
  had not told me, fixed (RED observed for each): the hub's retention words are `local`, `zdr`, `conditional`,
  `retains` and `unknown` (I had `kept`): `retains` and `unknown` draw the eye and need the acknowledgement,
  `conditional` the half shield; a proposal row is `{change: {preferred, ...}, reason, origin}` (I had `option` and
  `why`): `choices_face.proposal_line` reads the hub's shape. Every connection state and every purpose cue of the real
  hub is one the faces know.
- The merge's rail conflict (both lanes edited section 2 of the coding-guidelines skill) is resolved with both bullets
  and its own anneal row; the generated registrations were taken from the integration and re-synced.

## Gate totals at the final push

- `scripts/lampway/test_all.sh` (`--verify-env`: ready) on the merged tree with my build: **GREEN** against
  `tests/known_red.tsv`: server 1625 passed, 11 skipped, rc 0; client 8933 passed, 105 skipped, 110 failed and 15 errors,
  every one in the baseline, none new, none of the baseline now passing.
- Theme 0, cues 0 (self-test 4 of 4 caught), WezTerm 0, tool specs current, rail PASS; PII gate at the pre-push hook.

## Which build is in `build/Prod`

The coordinator's rule from here on: `build/Prod` is built from a clean tree at a pushed sha, and that sha is written to
`build/Prod/BUILT_FROM`. (The 10-06 02:31 build the integrator copied held the then-uncommitted 6881d79 native
changes; the coordinator traced that from the reflog.) The current build's sha is recorded at the end of this file
after each native push.

- `build/Prod` built from `cf1fc1f755218c2a32a433d15ba3c392c29c8693` (pushed, clean tree; `build/Prod/BUILT_FROM`), 2026-10-06.
  It contains contracts 01-08 as pushed and the `origin/lp/wave5` merge `5e5cf3e` (which brought no native change).
- `build/Prod` built from `7f67890d6de3df3acee1552293cf8308a4ed800e` (pushed, clean tree; `build/Prod/BUILT_FROM`),
  2026-10-06: every contract of this lane as pushed and the `origin/lp/wave5` merge `d2b142e` (lp/connections). The
  visual suite on that build: 31 passed. Commits after it are documentation only.

## The owed partials and the cloud audit (2026-10-06, second round)

Order of work: 16's Plex Mono, 12's shortfalls, 13 P1, 08, 04, 07, 11, 10, the live terminal tests, the audit's F22, F24,
F17, F23 (added mid-round), 16's remaining surface, 08's results line, 04's header, the build stamp (added mid-round).
Exploration was by Python and `git grep` scans: the codebase-memory index (`lampway-harden`) is stale and `wt-build` is
not indexed, so no graph query was used this round.

### 16: Plex Mono as TrueType (`e370a70b`)
`scripts/dev/brand_art/fonts_ttf.py` decodes the vendored woff2 into `addons/fonts/IBMPlexMono-{Regular,Medium}.ttf`
(OFL beside them; `--check` is byte-stable, `recalcTimestamp=False`); the add-on copies them into
`$LAMPWAY_HOME/addons/wezterm/fonts/`. Measured live: the window renders in Plex Mono, no Configuration Error pane.

### 12: the two shortfalls (`a60dce8d`)
"Allow once" is red TEXT on no bed (`row.emboss='NONE'`; the native REDALERT non-emboss branch paints the text in the
theme's stop), and "Run it here instead" is an action (`lampway.choices_open` on the kind's group).

### 13 P1: the drawn card (`1e857173`)
`interface_mixar_spend_card.cc`: `layout.mixar_spend(element=TITLE|PRICE|METER|LINE, text, rule)` tags label rows the
native painter draws: the action in Fraunces 17, the price in Fraunces up to 40 with its unit in Plex Mono and the kind as
an outlined chip, the meters with the pending part hatched in the accent (used in stop past 90 percent), and a 4 px left
rule in the card's state colour on every row. Spend is the accent fill (`MixarVariant::Accent`). Visual:
`tests/lampway_visual/test_spend_card.py` (card_rule tokens, the ACCENT variant).

### 08: Spend opens the card (`e7c96c20`), and the last run (`d02a4e2f`, `a3356f14`)
- Spend in the island's Image / Video tab now opens contract 13's card for the approval it caused (the status refresh
  finds it; `test_spend_in_the_tab_opens_the_card`).
- Each image or video run records its estimate and count in the run log; `/app/generate/estimate` answers with the
  last run of its kind, and the column draws it at its foot: "3 images, $0.20 billed against a $0.21 estimate, rated
  4" ("billed amount not read back (a $0.07 estimate)" when no cost came back; "(no estimate before it)" when none was
  made). Tests: `test_the_last_run_line_reads_billed_against_its_estimate`, `test_the_estimate_answer_carries_the_last_run_of_its_kind`
  (a real fake-transport video job end to end), `test_the_results_row_says_the_last_run_billed_against_its_estimate`
  (RED observed for each).
- Found while adding the line: the column's string reads used the `char*` RNA getter, which writes the whole string
  into a fixed buffer; the pump's strings have no `maxlen`, so a long refusal could overrun it. Now bounded by the
  buffer (`std::string` getter + `BLI_strncpy`). No test reaches it (native, no harness for over-long props): said.
- **Not done**: the A/B action (no surface submits a `variant_of` run yet); it would submit paid generations, and is
  the only 08 item left.

### 04: the who line, the step summary, the header parity (`0a74414d`, `e003f273`, `a21881e4`)
- The first agent message of each turn carries "<HH:MM>\x1f<host>\x1f<plan>\x1f<state>"; the island draws the Spark
  (accent while the latest turn works, at rest otherwise), "Lampway Agent", the plan chip in the agent's outline
  ("ChatGPT plan"), the time in Plex Mono, then where the turn came from.
- The step log collapses to "3 steps done, local", "1 step done, 1 failed, local" or "1 of 3 steps done, local". The
  spec's "1.5 s" is not claimed: steps carry no timing.
- **Not done**: the answered question as one line with the other choices in an expander (the choices block is removed
  when answered and its answer becomes a user message; collapsing needs the answered state kept on the message), the
  lamp glyph for local steps, test 6 (needs an approved golden).

### 07: typed forms for the batch tools (`39d8ae9e`)
`server/lampway_server/agent/batch_forms.py`: eight new definitions from each script's own usage line and argparse;
four of the thirteen already had a typed in-app definition, which the Way now offers (`tool_specs.py` FEATURES, 42
tools). `render_textured` is not given one: it needs a .blend before `-P`, which `api.run_tool` does not pass.

### 11: the data modes (`e430bfb7`)
Textured and Base colour / Normal map / ORM on a normalised re-import in the scratch scene (the user's scene
untouched): emission of the base map, the normal map as Non-Color or the flat (0.5, 0.5, 1.0) that makes a missing bake
the finding, ORM's G and B. `tests/lampway_tools/test_lampway_compare_modes.py`. Not done: Spin, the header Pick.

### 10: the cockpit page opens 16's window (`b95d1acc`)
"Open in the Lampway terminal" when the add-on is installed (POST `/app/terminal/open`), else it says it is not
installed. xterm.js is not vendored: 16's window is the terminal.

### 16: the live tests, in an isolated home (`dca41dd5`, `fb2935a5`)
`scripts/lampway/live_terminal_check.py`, run inside `lampway-build` on its own Xvfb, every directory under one scratch
root (`$TMPDIR/lt`: the Lampway home, the herdr root, HOME and every XDG dir; the script refuses to start otherwise);
the herdr server is Lampway's, started by `setsid` (never a systemd unit); the fleet's herdr is observed through
`/proc` cmdline and start times only (the box cannot read another process's environ) and, around the run, from the
host the same way. **A second download** of the pinned release was made for these runs (the first one's files were
deleted after the first round), through the github route into the scratch home: hosts github.com,
release-assets.githubusercontent.com, raw.githubusercontent.com; PROVENANCE verified. The scratch home is deleted at the end.

| test | result |
|---|---|
| 6: SIGKILL of the launching "Blender" (its whole process group) | window and agent alive (gui pid, agent pid unchanged) |
| 7: close the window, reopen | agent alive throughout, the same pid after reopening, reconcile "re-adopted" |
| 9: an inline image through herdr | **no**: iTerm2 and kitty both 0 magenta pixels through herdr (screenshot: the script ran, a blank line), 26 289 without herdr (the control) |
| 9's fallback | an image path in a pane is a link (`lampway-image:`); Ctrl+click queues it under the Lampway home; Blender's status refresh shows it in an Image Editor (a new window when none). Measured: under herdr a plain click goes to herdr (mouse reporting), Ctrl+click queued the path; with the Ctrl binding removed (mutant) nothing queued |
| 11: the fleet's herdr | the three fleet servers and the client: same pids and start times before and after (box and host views) |
| state.json | the tab reads the cue and "probe agent", the right status "Sending to OpenRouter, 2 KB" (judged from the screenshot) |

- The window's first tab is now plain `herdr`. **Disagreement with the brief, measured**: the spec's bootstrap
  `herdr session attach lampway` addresses a named session in herdr's own state (`~/.config/herdr/sessions/lampway`,
  under the isolated HOME), not the server the HERDR_* socket env names; in a pty it drew nothing in 6 s, while plain
  `herdr` drew Lampway's server. `test_open_attaches_the_window_to_lampways_herdr_by_its_socket` (RED observed).
- Then the rest of 16 (`b9054b3e`): Update appears when the pin moves past the installed version; Ctrl Alt T opens the
  terminal (Window keymap). [`b9054b3e` also added a server-written `state.json` with tab-title cues and an egress
  status, and a Focus: all removed by the viewport correction below.]

### Cloud audit (`specs/bugs/2026-10-06-cloud-audit-wave5.md`), re-checked on this branch first
- **F22** (`11b9db7c`): a 401 or no token reads "signed out"; a refused connection still "server not running"
  (`test_signed_out_says_signed_out_not_server_down`, RED observed).
- **F24** (`d663255d`): the Cinema Mode strip's wordmark was a literal "mixar" drawn by `cinema_text_left`; it reads
  "Lampway". The profile card's "Refer a Friend" row is gone, and the low-credit toast that pointed at it no longer
  fires. The C++ brand gate (G4) now also flags the bare name handed to a text-drawing call (`DRAWN` in
  `test_brand_cpp.py`; RED: the whole-tree test failed on the two Cinema lines; the scanner's unit test was written with
  the rule, so it was mutation-checked instead: with the rule off it fails). Left: the referral service, dialog and
  operators remain registered but unreachable from the UI; the credits banner's `TARGET_REFER` (no caller draws the
  banner) is untouched.
- **F17** (`d2b645b9`): observe's targets carry `label` (the text, else the tooltip) and page with `offset`
  (`next_offset` while more remain; handles are positions in the whole list). On the startup window: 40 of 55 targets
  had no text, 10 have no label now. Visual state `observe_labels` (RED observed: no label field).
- **F23** (`75fed27f`, `b06be59d`): walked by real clicks in the real build (`test_onboarding_steps.py`, RED observed: the
  step 2 sentence cut to "until you …", Continue jumping from y 397 to y 27, Back directly above it). Now the sentences
  wrap (translated whole, then wrapped), every step is padded to the tallest step and opens where the first did, so
  Continue stays put, Back sits under the step rail, and the window is redrawn on each step. Cost, said: with the
  server's 24 routes every step is as tall as step 3; a scrolling list for the routes would let the dialog shrink.
  Checked on Xvfb with Mesa (the box has no GPU); the cut was reproduced there too, so it was not a software-GL artefact.

### The build stamp (`eeb599d9`)
`scripts/lampway/built_from.sh` (state / stamp) and `build_linux.sh` call it: the state is read before the compile and
the stamp written after it succeeds; a bare sha only for a clean (`src/source`, `src/CMakeLists.txt`,
`src/build_files`, `src/release/datafiles`, untracked files included), pushed tree that held still; otherwise
`UNCLEAN <sha>: ...` or `UNPUSHED <sha>`. `test_all.py` refuses an UNCLEAN binary by name and reads `UNPUSHED <sha>` as
its sha. `tests/lampway_tools/test_build_stamp.py` (5, RED observed; a mutant that never compares start and end fails
`test_stamp_writes_the_sha_only_when_the_tree_held_still`), `test_test_all.py::test_the_stamp_build_linux_writes_is_read`.
- **What was in `build/Prod` before, said plainly**: the line below that says `7f67890d` was true at 13:45 and false
  from 14:34, when I rebuilt `build/Prod` from `e370a70b` with the 12/13/04 native edits still uncommitted (committed at
  14:36) and deleted `BUILT_FROM` rather than leave the wrong sha. Until this round's stamp the directory had no
  `BUILT_FROM`; I then wrote it by hand as `UNCLEAN e370a70b...` with that history, before the clean build below.

### Brand pages (the captain's addition: "not a basic white HTML page") (`a257a40e`)

**Inventory**, by searching `HTMLResponse`, `text/html`, `<!doctype`, `webbrowser.open` and `send_response` in the server and
the app:

| page | served by | now |
|---|---|---|
| password sign-in (`/app/desktop-login`), wrong password | Lampway server | template |
| ChatGPT plan page (`/app/chatgpt`) and its callback (`/auth/callback`): signed in, cancelled, expired / state mismatch, failed | Lampway server (lane connections' module; HTML only changed) | template |
| Higgsfield page (`/app/higgsfield`) and callback, start failure | Lampway server | template |
| Hyper3D callback (`/auth/hyper3d/callback`, the generic MCP sign-in; the next studio gets it for free through `brand_page.callback`) | Lampway server | template |
| the desktop app's loopback after the Lampway sign-in: success, state mismatch (was `text/plain` "state mismatch") | the app (`auth/core/sso.py`) | generated from the template (`sso_pages.py`) |
| the native loopback (startup sign-in): success, no code | the app (`creator/mixar_local_auth_server.cc`) | generated from the template (`mixar_sso_success_page.h`; its hand-written failure page is gone) |
| the cockpit page (contract 10) | Lampway server | its own document; now Night and Paper, the site's faces and the lockup from its own origin |
| report-card pages | Lampway server (`/app/cards/...`) | the cards' own documents from their builder (lane vault-ui), themed by `?theme=`; the frame shell is a bare iframe container: **not restyled** |
| the virtual camera's phone page | the app's camera server | an app UI, not a status page: **not restyled** |
| chatgpt.com / auth.openai.com, Clerk (Higgsfield), Hyper3D's sign-in, OpenRouter, billing and help pages the app opens | third parties | **not ours to style** |

- **One template**, `server/lampway_server/brand_page.py` (standard library only): `page()` (title, headline, one line, the
  next step, a tone badge, small print) and `callback(service, outcome)` for the four states: "Signed in to ChatGPT" /
  "You can close this tab and return to Lampway."; "ChatGPT sign-in cancelled" (nothing stored, try again from Connections);
  "This sign-in link has expired" (the state matches no sign-in of ours); "ChatGPT sign-in did not finish" (the reason, then
  start a fresh sign-in). Markup inside a page comes only from its own `form()` and `status()`: `page()` refuses raw HTML.
  Text is escaped; no token is ever an argument (the reason is the exception's own sentence).
- **Brand**: the tokens (`tokens.css`, generated from `tokens.json`, now with Paper under `prefers-color-scheme: light`), the
  lockup (crook lantern + wordmark, `web/brand/lockup.svg`), Fraunces for the headline and IBM Plex Sans for the text
  (vendored from the site's subsets, OFL texts beside them, REUSE annotated), all inlined as `data:` URIs: no CDN, no
  script, nothing requested after a loopback shuts down. Every server page carries `Content-Security-Policy: default-src
  'none'; style-src 'unsafe-inline'; font-src data:; img-src data:; form-action 'self'; ...`.
- **The app's pages** are rendered at build time by `scripts/generate_sso_success_page.py` (was a mirror of the Mixar page in
  Clash Grotesk on white): the faces subset to each page's characters (fontTools, only when writing), so each native page
  is about 46-50 KB, under the 64 KB MSVC literal limit the script refuses to pass; `--check` compares the markup with
  the template without needing fontTools.
- **Tests**: `server/tests/test_brand_pages.py` (28, the scan parametrized per module): no auth or loopback module (app.py, chatgpt_auth, mcp_oauth,
  higgsfield_auth, connections/*, the app's sso.py and auth.py) holds an HTML literal (the scan's falsifier: it finds the
  hand-written pages in `c0872d90`'s app.py); every `HTMLResponse` in app.py goes through `html_page` (the cockpit page is
  the one named exception); each state's headline and next step; the outcome mapping; nothing loaded but `data:` and this
  origin; escaping; the served pages carry the CSP; the cockpit serves the faces; the generator `--check`.
  Lane connections' tests pass unchanged (the 139 in the ChatGPT, hardening, SSO, MCP OAuth, Higgsfield auth and connections files, run with the brand and cockpit tests: 174 passed).
  `tests/lampway_web/test_brand_pages_live.py`: a real headless Chromium renders the 12 pages in Night and Paper (24 captures)
  through a proxy that is the test's own server (`--proxy-bypass-list=<-loopback>`), and asserts each page made exactly one
  request (itself) and that its corner is the theme's canvas. Falsifier run: a page with a planted stylesheet and image
  logged both (`CONNECT cdn.example.invalid:443`, `http://fonts.example.invalid/x.css`). The first version of the harness
  sent the CSP with each page, which hid exactly that: the browser never asked. It now judges the markup without it.
  RED observed: Paper failed (the corner stayed Night) before `tokens.css` had its light block. **Not RED-first**: the
  template and the app.py wiring were written before their tests; the scan's falsifier and the planted-request run stand
  in for that.
- **Chromium, said plainly**: no browser is installed on the host or in the box. I copied Playwright's
  `chrome-headless-shell` (build 1243) from `~/.cache/ms-playwright` into the scratch directory (a read of the cache, once)
  and run it only from there, with its own HOME, XDG dirs and profile under the test's directory (`LAMPWAY_CHROMIUM`; the
  test skips without it).
- Left: the report-card pages and the camera page (above); `release/datafiles/fonts/ClashGrotesk-LICENSE.txt` stays though
  no page embeds Clash any more.

### Gates at the end of this round

- `test_all.py --only server` at `a257a40e`: **GREEN**, 1660 passed, 16 skipped, rc 0 (55 min; the box's disk is slow:
  pytest sat in `wait_log_commit`). The same at `c0872d90`: 1632 passed, 16 skipped.
- `test_all.py --only client` on the `a257a40e` build (gated by its BUILT_FROM): 9044 passed, 78 skipped, the 125
  known-red baseline seen, and **one new failure**: `tests/network/test_network_sso_callback_server.py` pinned Mixar's page
  title "Login Successful"; re-pointed to "Signed in to Lampway" (`535c17c6`, test only) and that file re-run alone: 8
  passed. The full client suite was not re-run after that one-line test change. The run at `c0872d90` had found the canon
  door's new one-importer gate failing on my image fallback (`213bca4d` fixed it; re-run: 24 passed).
- Visual suite and the browser captures on the `a257a40e` build: 38 passed (36 visual states, 2 web: 12 pages x Night and
  Paper). Two visual states were fixed on the way (`c0872d90`): the Way's state now retopologises a 128-face sphere (the
  canon door refuses a target over 3x the Cube's 6 faces and under 50), and the image fallback's state judges the main
  window's areas (the island opens its own window, so counting windows was wrong; my first pin of "2 windows" was written
  without a run and failed).
- Theme 0, cues 0, WezTerm 0 (self-test 5 of 5, W5 new), tool specs current, tools.md current, i18n `--check` current,
  `generate_sso_success_page.py --check` current, rail PASS; the PII gate runs at the pre-push hook.

## Which build is in `build/Prod` (this round)

- `build/Prod/BUILT_FROM` = `a257a40e309396457c53b6dc6f358db9ba9c4847`, written by `build_linux.sh` itself (clean native tree,
  pushed): every native change of this round. Earlier in the round the same script stamped `d18d713d` and `c0872d90`.
  Commits after `a257a40e` are tests and this report only (no native source).

## The remainder (2026-10-06, the coordinator's last list) and the captain's viewport correction

### 16: WezTerm is purely a viewport (`ebf357d8`) - this supersedes parts of the sections above
The captain: "No no no no no. Our agent live in herdr, herdr has it's own workspace, we don't make multiple WezTerm tabs.
WezTerm is PURELY a viewport". I had built one tab per agent (`c89632c2`, from the coordinator's list) and, earlier, the
server's `state.json` with tab-title cues and an egress status (`b9054b3e`, from the contract). Both are removed:
- gone: `agent_tabs` (`cli spawn -- herdr agent attach`), `state_doc` / `write_state` and the server's one-second tick,
  the config's `format-tab-title` / `update-status` handlers and its state file, the pane registry, `send_text`, the dead
  cue table in `build_theme.py`; the reset of the pane registry on Open;
- the config sets `enable_tab_bar = false` (so no egress status inside WezTerm either: egress stays in Lampway's status
  bar and Privacy window); the CLI only lists the one window (reconcile);
- then the coordinator's audit (W1-W8) of what was already in `lp/wave5`: Focus is removed too (W6, `1968d9c6`: the route,
  `wezterm.focus`, the Blender operator, its button and the client call), and `c89632c2` is reverted by a normal revert
  commit (`fd51779d`; its code was already gone, so the revert changes no file and records the decision);
- what remains: the branded config, the isolated home and socket, the download and verify (Get, Update, Remove), and ONE
  window that attaches to Lampway's herdr by plain `herdr` (Open, Ctrl Alt T);
- pending the captain's decision (W8, he never asked for it): the Ctrl+click image link; left in place, not extended;
- pinned: `test_the_launcher_issues_no_tab_or_spawn_command` (open and reconcile issue one `start` and only `list`; the
  add-on names no tab, spawn, send or activate verb and has no focus), `test_the_config_has_no_tab_bar_and_mirrors_no_state`,
  `test_the_server_writes_no_terminal_state`, `test_there_is_no_focus_route` (RED observed for each before its removal); the WezTerm gate's W4 is now
  "no tab bar, no tab title or status from state" (self-test: a tab bar turned back on, and a tab-title handler, are caught).
- the record: `specs/client_facelift/16-lampway-wezterm.md` has a new section 0 (the rule, verbatim) and its lines on
  tabs, cues, the state file, spawn and send-text are marked superseded; `10-herdr-cockpit.md` and `docs/cockpit.md` say
  viewport only. (The specs folder is not a git repository: the originals are copied to the scratch directory.)
- Earlier in this file, the live-check row "state.json" describes what was removed (the sentences on send-text, Focus and
  tabs in the contract 16 section are marked). The live terminal check was not re-run after the removal (it needs a third download of the release);
  the config change is gated by `check_wezterm.py` under luajit, not by a live window.
- What the tab work measured, kept as a fact: `herdr agent attach <pane>` refuses a pane with no detected agent
  (`agent_not_found`).

### 04: the answered question collapses to one line (`e29f6f49`)
`lampway_tools/answered.py`: when a choice is answered through the island's action operator, the bubble becomes "Which
glass? Clear, you answered 14:30" and its choices are replaced by one expander row ("2 other choices" / "Hide other
choices", opening "Other choices: Frosted, Amber"). The expander is handled in the island (value `lampway_answered:`),
never sent to the agent; the answer itself still goes once. Natively, a bubble whose only rows are the expander gets no
lamplight and no waiting rule. Tests: `tests/lampway_tools/test_lampway_chat_answered.py` (real binary, fake transport;
RED observed), `test_an_answered_question_has_no_lamplight` (source; RED observed), the visual state `chat_answered`
(captured on the `97879399` build: one line, the expander, no glow).

### 11: Spin (`64a74195`)
The 100 ms poll turns every compare view 2 degrees about the vertical while Spin is on; a manual orbit in one view stops
Spin and the others follow it. Found on the way: the poll compared `view_matrix`, which Blender recomputes only at the next
draw, so a rotation set by the poll read back as the user's orbit; it now compares the views' own rotation, location and
distance (the same lag affected Sync's echo). Visual test `test_compare_spin.py` (RED observed; the "orbit stops it" rule
mutation-checked: removed, the test fails).

### Brand pages: the report cards and the phone camera page (`08e2da21`)
- Report cards: `cards/_shared/report.css` is the template's faces and tokens (Night; Paper under the content server's
  `data-lw-theme="light"`) plus the card layout on `--lw-*` tokens; every page shows the lockup. `test_card_pages_carry_the_brand`
  (RED observed). The cockpit's card frame shell (a bare iframe container) is unchanged.
- Phone camera page: the gate's "MIXAR" wordmark is the lockup, Mixar's green is the flame, the faces and Night tokens come
  from a generated `webapp/brand.css` (Night only: the controls sit over the live picture). `tests/lampway/test_camera_page_brand.py`
  (RED observed).
- The generator (`scripts/generate_sso_success_page.py`) now writes the camera's `brand.css` and lockup too, and leaves the
  sign-in pages alone when their markup is current (the subset fonts are not byte-stable between fontTools runs, so a
  regeneration would otherwise rewrite the native header and force a rebuild).
- Browser captures: the card (Night and Paper) and the camera gate render on their canvas with the lockup and every
  request on their own origin (`test_the_card_pages_and_the_camera_page_are_on_brand_and_stay_on_their_origin`).

### 08: A/B as a stub (`508a56a7`)
"A/B" beside "Edit as my own" in the prompt library: the user's click says it would run two paid generations and sends
nothing; a script cannot press it. `tests/lampway_tools/test_lampway_prompt_ab.py` (RED observed).

### Integration request 9: the schema ratchet (`97879399`)
Every batch form parameter described and every number bounded (bounds taken from each script's defaults with generous
room); `UNDESCRIBED` 702 -> 691 and `UNBOUNDED_NUMBERS` 258 -> 240 (RED observed by lowering them first).

### Merge
`origin/lp/wave5` at `631f4631` merged (`f1a8f67a`, no conflict; it brought no native change). The post-merge hook printed
"unable to read tree (fbe62287...)" while re-pinning `upstream/`; `upstream/` was already at that commit.
