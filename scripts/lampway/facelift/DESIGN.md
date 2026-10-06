<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Lampway client: the design language

Written 2026-10-05 for the client facelift. It carries lampway.dev (`specs/brand/site_v2/`) into a dense desktop 3D tool built on Blender 5.2. Brand rules it inherits and does not restate: `specs/brand/BRAND.md`. Every colour below is a token in `theme/tokens.json`; `theme/check_theme.py` fails when this file's table and that file disagree, and when the shipped theme XML strays from either.

## 1. The idea

The site is a lamp carried through a dark workshop: one warm light, and a path that lights as you go. The app is the workshop itself, and the same rule holds inside it: **light falls only where your hand is needed.**

- The room is night slate and quiet. Panels, headers and the viewport recede.
- **Flame is you.** Your selection is lit. A decision waiting for you (a spend, a plan to approve, a question, a route to open) is the only thing in the window that glows.
- **Dusk is the agent.** Whatever the agent proposes, runs or says carries a dusk edge, so you can always tell its work from yours.
- **Wire is data leaving the machine,** and it is the only thing that moves on its own. When nothing leaves, nothing moves.
- **Every number names its source.** A price says where it was read back from; a count says when it was taken; an estimate says it is one.

Spend your boldness once: the lamplight glow behind a waiting decision. Everything else stays disciplined so that glow means something.

## 2. Colour

Dark ("Lampway Night") is the app default. Light ("Lampway Paper") exists for documentation captures, bright rooms and people who need it; it is a full theme, not an inversion.

### 2.1 Tokens

The table is parsed by `theme/check_theme.py` (T1): keep the first three columns in this shape.

| token | dark | light | brand name | role |
|---|---|---|---|---|
| `canvas` | #0E1016 | #E4DCCB | Night / Linen-deep | editor gaps, headers, the darkest recess |
| `well` | #11131A | #FFFFFF | (new) | text and number fields, sunken inputs |
| `surface` | #161922 | #F7F3EA | Smoke / Paper | editor and region background |
| `raised` | #1E222D | #FFFFFF | Slate / White | panel headers, buttons, cards |
| `raised_hi` | #262B38 | #EFE8D9 | (new) | hover on raised |
| `line` | #2B303D | #DDD5C3 | Line | borders and rules |
| `line_hi` | #3B4252 | #C9BFA9 | (new) | strong border, menu outline, scrollbar thumb |
| `text` | #ECE8DF | #1B1B22 | Moon / Ink | body text |
| `text_hi` | #F7F4EE | #0E1016 | (new) | text on a lamplit bed, emphasis |
| `text_dim` | #CFCBC2 | #3A3934 | (new) | secondary body text, unselected values |
| `muted` | #A9A69D | #5C5A55 | Ash / Graphite | labels, captions, header text |
| `muted_dim` | #7D7A73 | #8A877F | (new) | disabled, placeholders (never body text) |
| `accent` | #EDB944 | #EDB944 | Flame | the lamp: a decision waiting for your hand; selection; focus |
| `accent_hi` | #F6CD6B | #E3AB2C | Flame-hi | hover on accent; the active object |
| `accent_text` | #EDB944 | #8A5A00 | Flame / Ember | accent as text or a thin line |
| `on_accent` | #0E1016 | #1B1B22 | Night / Ink | text on an accent fill |
| `accent_bed` | #3A2F17 | #F6E7BF | (new) lamplit | selected toggle, tab, list row: lit, not shouting |
| `accent_bed_hi` | #5A4720 | #EED9A0 | (new) lamplit | primary button bed, slider fill, the outliner's active row |
| `agent` | #9EA0F7 | #4547B8 | Dusk | the agent: what it proposes, runs or says |
| `agent_bed` | #23264A | #E3E3FA | (new) | agent cards, plan blocks, info rows |
| `go` | #5BC48F | #1F7A4D | Go | done, landed, local and free |
| `go_bed` | #163527 | #DCEFE4 | (new) | success rows |
| `stop` | #F0766B | #B3372C | Stop | failed, refused, over a cap |
| `stop_bed` | #3D1C1D | #F7DEDA | (new) | error rows, alert buttons |
| `wire` | #F27BCB | #9C1F7A | (new) Wire | data leaving this machine; nothing else ever uses it |
| `wire_bed` | #3A1A33 | #F6DCEB | (new) | the egress pill and log rows while sending |
| `viewport_hi` | #1A1D27 | #D9D3C6 | (new) | 3D view radial centre (the pool of light) |
| `viewport_lo` | #0B0D12 | #C2BBAD | (new) | 3D view radial edge |
| `shadow` | #05060A | #3C2D0A | (new) | emboss and drop shadow base (used with alpha) |

Worker ring colours are BRAND.md's six (Flame, Dusk, Mint #5BC48F, Coral #F0766B, Sky #6FC3E8, Orchid #D58FE0), always beside the worker's name.

### 2.2 Measured contrast (WCAG relative luminance, computed)

| pair | dark | light |
|---|---|---|
| `text` on `surface` | 14.36:1 | 15.46:1 (on Paper) |
| `muted` on `surface` | 7.21:1 | 6.22:1 |
| `muted_dim` on `canvas` (disabled only) | 4.44:1 | 3.24:1 on Paper (disabled only, never body) |
| `accent` on `canvas` | 10.53:1 | not used as text: `accent_text` Ember 5.35:1 |
| `on_accent` on `accent` | 10.53:1 | 9.48:1 |
| `text_hi` on `accent_bed_hi` (primary button) | 8.12:1 | 13.64:1 |
| `text` on `accent_bed` (selected) | 10.74:1 | 13.94:1 |
| `agent` on `canvas` | 7.99:1 | 6.66:1 on Paper |
| `wire` on `canvas` | 7.67:1 | 6.56:1 on Paper |
| `wire` on `wire_bed` | 6.16:1 | 5.66:1 |

`check_theme.py` T5 recomputes the readable pairs from the shipped XML, not from this table.

### 2.3 Where each colour may appear

- `accent` fills only four things: a spend or approve button, a checked checkbox, the playhead, the slider thumb. Everything "selected" uses `accent_bed` with `accent` as a 1 px edge. If a screen shows more than two accent fills at rest, something is wrong.
- Selection in the 3D view is the lamp: selected objects `accent`, the active object `accent_hi`, edit-mode selection `accent`. Mixar's green and Blender's orange are both gone.
- The viewport grid is the site's floor: `accent` at 8 percent for minor lines and 15 percent for major lines (v2; 11 and 20 in v1), over a radial `viewport_hi` to `viewport_lo` background (the pool of light). Axis lines keep Blender's red, green and blue: they are a 3D convention, not brand colour, and they are copied from upstream's own preset.
- `agent` never marks a user action; `accent` never marks an agent action. A plan the agent wrote is dusk-edged; your Approve button on it is flame.
- `wire` appears only when a byte is about to leave or has left the machine. It is never decoration and never a worker colour.
- Blender's domain palettes (bone colour sets, collection and strip colours, node categories, keyframe shapes, curve handles, animated-property states) are copied from upstream Blender 5.2's preset so muscle memory survives; the builder marks them `domain:upstream` and T4 exempts them.

## 3. Type

| role | face | where | licence | mechanism |
|---|---|---|---|---|
| interface | **Inter** (Blender's bundled UI font, variable) | every native widget, panel and menu | SIL OFL 1.1 | unchanged; `ThemeStyle` sets the sizes |
| display | **Fraunces** (variable, optical size) | splash, onboarding headlines, empty states, the price on a spend card, Vault and cockpit window titles | SIL OFL 1.1 | BLF: `BLF_load_mem` from a datatoc'd woff2 in C++ surfaces; `blf.load()` in Python draw handlers |
| measurement | **IBM Plex Mono** 400/500 | every price, cap, byte count, elapsed clock, model id, file:line, log row | SIL OFL 1.1 | BLF as above; native labels cannot change face, so Python panels show mono only through a draw handler or a custom C++ widget |

**Accepted 2026-10-05 (F1): Inter for the UI.** IBM Plex Sans is the site's text face. Inside the app, Inter stays the body face: it is what Blender's widgets are measured against (caret, IME, number fields, CJK fallback), and BRAND.md 5.3 already says the UI keeps Blender's font. Swapping the UI font to Plex Sans would be one preference (`PreferencesView.font_path_ui`); the captain kept Inter (F1). The `?ui=plex` switch stays in the mockups for comparison.

Scale (UI scale 1.0, px): widget 11 pt (`ThemeStyle.widget.points`), panel title 11.5 pt weight 600, tooltip 11 pt; chat body 13.5; caption 10; display 20 (card title), 24 (price), 28 (empty state), 44 (splash). Weights: Fraunces 340 for display, 420 for prices; Inter 400/600; Plex Mono 400/500. No shadow on text (`shadow="0"`): the theme is flat, light does the work.

Fonts ship as subset woff2 (the site's own files: `site_v2/assets/fonts/`) with their OFL texts in `LICENSES/`, alongside Inter's.

## 4. Space, shape, elevation

- **Grid.** 4 px base, Blender's 20 px `UI_UNIT`. Tokens 2, 4, 8, 12, 16, 24, 32, 48.
- **Radii.** xs 3 (fields), sm 5 (buttons), md 8 (cards, panels), lg 12 (floating panes: the island, cards, dialogs), pill (chips, status). In the theme: `roundness` 0.3 on fields, 0.35 on buttons, 0.4 on tabs, 1.0 on scrollbars and progress; `panel_roundness` 0.4.
- **Elevation is lightness, not shadow.** Level 0 `canvas` (headers, gaps), 1 `surface` (editors), 2 `raised` (panels, buttons), 3 floating (`raised` at 97 percent plus `menu_shadow_width` 10 at 0.5). The fork's liquid glass stays for the island and pill, with its green tint and the moving specular removed (contract 03).
- **Lamplight.** The one coloured elevation: a radial glow of `accent` at 22 percent (BRAND.md 5.4's glow value) behind a card that waits for your hand. Drawn with the existing glass painter's shadow pass recoloured, or a 2D radial quad in `gpu`. Never behind anything the agent owns.

## 5. Motion

Durations are the fork's own (`UI_mixar_motion.hh:16-22`): hover 0.14 s, press 0.08 s, select 0.20 s, enter 0.26 s, exit 0.20 s, stagger 0.05 s, ease-out cubic.

- Motion answers an action (open, expand, arrive, confirm) or carries one fact: **sending** (the wire dot crossing its line, 1.2 s). Nothing else moves by itself. v2 (the captain, 2026-10-05: only egress moves) retires the working flame's two-frame animation that BRAND.md 7 describes: **working** is now a static arc on the ring, and the running clock says the agent is alive.
- Removed: the glass specular sweep (`specular_period` 6 s), the cat's idle choreography, the simulated progress light that creeps to 90 percent on Parallel Agents cards (`view3d_agent_panel.hh:180-182`: "Simulated visual progress"). A card that does not know its progress does not pretend to.
- A spend or decision waiting for you does not pulse; it glows, steadily. Loud by light, not by animation.
- Reduced motion: a Lampway preference (`reduce_motion`, mirrored to `WindowManager.lampway_reduce_motion` for C++) stops the wire dot (the pill still reads "Sending") and zeroes enter/exit slides.

## 6. Iconography

- **Construction.** Monoline on a 16 px grid, 1.5 px stroke at 1x, round caps and joins, no fills except a flame or a status dot. The same construction as the mark (BRAND.md 5.4) at UI size.
- **Delivery.** Native: `src/release/datafiles/icons_svg/*.svg`, compiled by `editors/datafiles/CMakeLists.txt` and enumerated in `UI_icons.hh` (a C++ rebuild per new icon). Theme-coloured where it helps: `interface_icons.cc`'s `icon_source_edit_cb` already rewrites `blender_*` gradient stops from the theme (the send arrow does this today). Python-only surfaces use `bpy.utils.previews` PNG icons rendered from the same SVGs, no rebuild.
- **Retire.** `icons_svg/sparkle.svg` and the magic-wand reading of `generate.svg` (BRAND.md 2: "no sparkle iconography, no magic wand"); the credit badges (`credits_*.svg`, Mixar commerce).
- **Add** (contract 14 lists all 24 with their grid): lamp (local, on this machine), wire (leaves this machine), coin (a price), cap (a limit), receipt, route, shield-ok / shield-half / shield-open / shield-unknown (retention classes), hand (needs you), spark (agent), worker, pane (cockpit), compare, vault, gate (the confirm gate), path node lit / half / unlit.

## 7. Agent-state language

One vocabulary everywhere an agent appears: the island pill, the chat, Parallel Agents cards, the cockpit's session rows. Shape and word always carry the state; colour confirms it.

**v2 (superseding the table below where they differ):** the ring is the state, not the worker. Working is a static amber arc on a quiet ring (no animation); unread is a dusk dot on a dusk ring; blocked is a thick amber ring on a lit card; the worker's colour moves to a 6 px dot before its name, so identity and state no longer compete for the same pixel. The full vocabulary is section 13.

| state | Spark (avatar) | ring | word | extra | motion |
|---|---|---|---|---|---|
| idle | still flame | worker colour | ready | | none |
| working | still flame, amber arc on the ring (v2) | `line_hi` ring | working | elapsed clock in mono, `2:14` | none (v2: only egress moves) |
| unread | still flame | worker colour, plus a solid `accent` dot at one o'clock | new answer | name in 600 weight; the row lifts to `raised` | none |
| blocked | still flame | `accent` ring, card on lamplight | needs you: answer / approve / spend / sign in | the hand glyph and the one action that clears it | none (it glows) |
| paused | still flame | worker colour, dashed | waiting on … | what it waits on, in words | none |
| done | steady flame and a check | `go` | done | duration in mono; settles after 1.2 s, never sooner than read | slide out |
| failed | flame out: grey wisp over an ember dot | `stop` | failed | the reason in one line and its fix; stays until dismissed | none |

The Spark replaced the cat at `a4ccd8db` (`agent_ui_pill_cat.cc:181-218`), but only idle, working and offline are drawn: `agent_ui_draw_cat` passes `offline=false` always (`:214-218`), so cards cannot show done or failed on the avatar and lean on a right-hand glyph alone. Contract 05 draws all seven.

## 8. Money

The captain's rule: spend is a click you make, and it must be unmistakable. Three price states, each with its own shape, so an estimate can never be mistaken for a quote:

| state | chip | example |
|---|---|---|
| estimate (computed by us, not yet read back) | dashed outline, `≈` prefix, `muted` text | `≈ $0.10 est.` |
| quote (read back from the provider) | solid `accent_text` outline, mono | `13.5 credits, read back from Tripo 14:32` |
| spent (on the ledger) | filled `accent_bed`, mono, with the receipt glyph | `$0.05 billed` |
| no cost | `go` outline and the lamp glyph | `local, no cost` |
| plan usage (subscription, not money) | `agent` outline | `on your ChatGPT plan` |

- **The spend card** (contract 13) is the site's "Ask before it spends" panel made native: a `raised` card with a 4 px `accent` left rule and lamplight behind it; the price in Fraunces 24 with the unit in Plex Mono; the source and time of the quote; the caps it falls under drawn as meters; two buttons, `Spend 13.5 credits` (accent fill, the price repeated on the button) and `Not now`. The button label carries the number so the click and the price are one thing.
- **Caps** are meters, never only numbers: job, day and session, each `well` track with an `accent_bed_hi` fill that turns `stop` above 90 percent, labelled `$0.31 of $5.00 today`.
- **The ledger in the status bar** is always visible: `Spent today $0.31 of $5.00` in mono. A waiting spend adds a lit `1 waiting for you` chip that opens the card.
- An agent can plan a spend and can never confirm one (CONTRACT_TEMPLATE.md law). The card says so when the plan came from an agent: "Planned by the agent. Only your click spends."

## 9. Privacy

The captain's rule: loudly visible choices, opt in to each, and you can see when data goes over the wire (`specs/cloud/egress_consent.md`).

- **Route chips.** Every place a provider is named shows where the work runs: `on this machine` (lamp glyph, `go`) or `leaves this machine: openrouter.ai` (wire glyph, `wire`). Retention class beside it as a shield: ok (solid), conditional (half), retains (open), unknown (question mark), always with the word.
- **The wire indicator** lives at the right of the status bar, in three states: all routes off ("Nothing leaves this machine", `muted`, lamp glyph); routes open and idle ("2 routes open", `wire` outline); sending (`wire_bed` pill, `wire` text, "Sending to OpenRouter, 1.2 MB", the dot travelling along the wire glyph). It is lit from the moment a gated call starts until it returns, as the contract says. Click opens the egress log.
- **The routes panel** (contract 12) lists every route with an off-by-default switch, its policy text or the word "unknown", and its last use. Switching one on is a deliberate act: the switch shows `accent` only while the confirm row ("Let data leave for openrouter.ai") is open.
- **The egress log** is a mono table: time, route, host, what (kind, size, asset ids), retention class. Never content, query or headers.
- A private asset refused on a retaining route says so in the place you tried, with the three ways out.

## 10. Status honesty, carried from the site

Tool panels carry the site's status chips, shape and word, never colour alone: **Live** (filled dot, `go`), **Built** (ring, `agent`), **Partial** (half dot, `accent_text`), **Planned** (dashed ring, `muted`). A tool panel for a Planned tool says Planned and shows no Run button. Numbers in panels name their run: `91 candidates, read 14:02`.

## 11. Words

The site's voice, compressed for buttons. A button says what happens, with the number when there is one: `Spend 13.5 credits`, `Approve plan`, `Open route`, `Send`. The toast says the same verb back: "Spent 13.5 credits on Tripo." Errors name the fix: "openrouter is off: switch it on in Privacy to let data leave." Empty states invite: "Ask Lampway Agent anything. Plans, questions and spends wait for you." (BRAND.md 6). No "magic", no "AI-powered", no exclamation marks.

## 12. What Blender can render, and what it cannot

| want | mechanism | limit | fallback |
|---|---|---|---|
| colours, roundness, fonts sizes, widget states | theme XML (`theme/lampway_dark.xml`) loaded through the preset path, and the same values compiled into `userdef_default_theme.c` to make it the default | the 5 hidden Mixar slots (`mixar_pane_pill_dim`, `_pane_pill_on`, `_cinema_pill_fill`, `_profile_fill`, `_cinema_gate_fill`) have no RNA and do not load from XML; an all-zero colour means "unset" to the fork's slots (`interface_mixar_theme.cc:138-155`), so pure transparent black cannot be themed there | change the compiled fallbacks in `interface_mixar_theme.cc:27-117` and the hard-coded painter colours (contract 01) |
| a brand face for display and numbers | BLF in C++ spaces and Python `blf` draw handlers | native `layout.label` cannot change face or colour per label | mono and display text only on custom-drawn surfaces; native panels use Inter |
| lamplight glow, meters, chips with shapes | `gpu` immediate mode / the fork's glass painter (`interface_mixar_liquid_glass_draw.cc`) in C++; `gpu.shader` + `batch_for_shader` in Python draw handlers | a draw handler cannot add hit-testable widgets; its rects drift if the layout changes under it | draw in C++ custom regions (the island, the cards region); in Python panels use native widgets with `alert`, `depress` and icons, and keep the glow to C++ |
| a per-label colour in a Python panel | none natively; `alert=True` (stop bed) and `active=False` (dim) only | | icons carry the meaning (coin, wire, shield) plus words |
| a pop-out window | `WM_window_open` (C++ precedent `space_agent_bubble.cc:3035`), `screen.area_dupli` [UNVERIFIED in this fork] | per-pixel alpha is not composited (`agent_ui_theme.hh:71-75`) | opaque windows; frost only where GHOST supports it |
| a terminal in a window (Herdr cockpit) | none: Blender has no terminal widget | a C++ terminal editor is a project, not a contract row | a chromeless browser window on the server's loopback page (contract 10), framed and titled to match |
| icons | `icons_svg` + C++ rebuild; `bpy.utils.previews` for Python | no new native icon without a rebuild | preview icons in Python panels until the rebuild lands |
| reduced motion | none in Blender | | a Lampway preference mirrored to a WindowManager property |

## 13. Glance cues (v2)

State reads from shape first, colour second, words third. Each family has a small closed set; within a family every state has its own glyph, so the set reads in greyscale and for deuteranopia and protanopia (`theme/check_cues.py` fails otherwise and writes `theme/cues_report.md` with the measured distances). Only the live-egress cue moves; only a cue that waits for you glows.

| family | state | glyph | colour | motion | glows |
|---|---|---|---|---|---|
| agent | idle | plain ring around the flame | `line_hi` | none | no |
| agent | working | ring with an amber arc (static), clock beside | `accent` arc | none | no |
| agent | unread (a new answer) | ring with a filled dot at one o'clock, name in bold | `agent` | none | no |
| agent | blocked (needs you) | thick ring, hand on the action, card lit | `accent` | none | **yes** |
| agent | paused (waiting on something) | dashed ring | `muted_dim` | none | no |
| agent | done | ring with a check under a smaller flame | `go` | none | no |
| agent | failed | ring with the flame out (grey wisp), red left edge on the card | `stop` | none | no |
| spend | under a cap | gauge bar | `accent_bed_hi` | none | no |
| spend | near a cap (80 percent and up) | gauge bar + triangle | `accent` | none | no |
| spend | over a cap (refused) | gauge bar + cross | `stop` | none | no |
| spend | waiting for your click | hand + the price on the button | `accent` | none | **yes** |
| egress | idle, nothing can leave | lamp + "local" | `muted_dim` | none | no |
| egress | routes open, idle | wire + count | `muted` | none | no |
| egress | live, data leaving | wire pill + travelling dot + "Sending to …" | `wire` | **the one moving thing** | no |
| route | off | switch, knob left, hollow | `muted_dim` | none | no |
| route | waiting for your confirm | switch, knob right on an amber track | `accent` | none | **yes** |
| route | on | switch, knob right on a magenta track | `wire` | none | no |
| build | Live / Built / Partial / Planned | filled dot / ring / half dot / dashed ring | `go` / `agent` / `accent_text` / `muted` | none | no |

Measured (dark theme, CIE76): the riskiest colour pair, `go` against `stop`, keeps delta E 19 under deuteranopia and 17 under protanopia (90 in normal vision); their glyphs (check, wisp; bar, cross) differ, so the meaning never rests on that pair alone.

## 14. The calm pass (v2): hierarchy, disclosure, density

The captain, 2026-10-05: "I still want the same information, just better presented and better at a glance cues." Every datum stays; how it is presented changes.

- **Three tiers per surface.** Tier 1 is the one thing the eye lands on (the waiting decision, the selected object, the price); tier 2 is what you act on next; tier 3 (`t3`: `muted_dim`, 10.5 px) is everything else. Size, weight and contrast make the tiers, not boxes.
- **One hover away**: descriptions, policy text, task lines, state words, receipt ids, measurement settings. In Blender a hover is a native tooltip: an operator or property `description`, or a label drawn as an unembossed operator button whose description carries the detail (a plain `layout.label` has no tooltip).
- **One click away**: secondary meters, step logs, the rest of a turn, provenance, per-job caps, refusal explanations. In Blender: `layout.panel(idname, default_closed=True)` (5.2 layout panels) or a `DEFAULT_CLOSED` sub-panel; in C++ surfaces, a disclosure row.
- **Fewer containers.** Panels lose their outlines and header bars, fields and buttons their borders (theme v2: `panel_outline` and `panel_header` folded into the surface, widget outlines equal to their fill), list stripes fade to 3 percent, chips lose their outlines unless the outline means something (the dashed estimate, the spent bed).
- **Alignment over boxes.** Rows share columns (label, value, cue) on a grid; repeated labels become one column header; related numbers sit in one gauge ("$0.31 of $3.00 session" with the bar).
- **Calm.** One glow per screen, and only on something waiting for you; nothing moves unless data is leaving.
- **Proof, not adjectives.** `mockups/parity.py` lists every v1 datum and where it lives on v2 (visible, hover, expander) and fails if one is lost; `mockups/busyness.py` measures text runs, boxes, borders, colours, glows and motion from the rendered pages, v1 against v2, and fails when a surface gets busier. Results: `mockups/parity.md`, `mockups/busyness.md`.
