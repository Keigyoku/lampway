<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# The floating agent pill: where each datum went

The captain: "get rid of the separate floating agent-pill ... it should either be toggleable, off by default or just
combined into the chat window". Both are done: the pill is the preference "Floating agent pill" (Preferences >
Interface > Agent), off by default, existing users included, and every datum it showed has a place without it.
"Header" is the chat window's header band, which the island paints natively (`agent_ui_draw.cc`,
`agent_ui_draw_header_glance`, in the slot between the scene and handwriting buttons); "top-bar chip" is the agent chip
the top bar draws while the chat is closed and the pill is off (`agent_bubble_module._draw_topbar_open_agent`,
`agent_bubble/ui/glance.py`).

| the pill showed (source) | where it is now | test |
|---|---|---|
| The agent's state as the Spark's expression (`agent_ui_draw_status_pill`, `cat_activity`) | Header: the Spark itself in its contract 05 state (working, blocked, paused, idle). Top-bar chip: the contract 14 state glyph (`agent_working`, `agent_blocked`, `agent_idle`, `agent_failed`, `agent_paused`, `agent_unread`) | `test_the_chat_header_shows_every_pill_datum` |
| The state in words: Disconnected, Connecting, Reconnecting, Running (with the pulse dots), Awaiting Input, Working, Idle (`header._get_status`, the compact pill's `status_text`) | Header: the state enum's name (`status_text`, "Working" for an open run), as the compact pill drew it. Top-bar chip: the `_get_status` words, Reconnecting included | same |
| Outstanding generations: "Image Gen 1:24" / "3 jobs 1:24" (`_queue_label`) | Top-bar chip: the same words and clock (part of `_get_status`). Header: "N jobs", no clock | same (the queue path is `_get_status`'s own) |
| Delegated workers busy (`status_active`, the lit dot) | Header and top-bar chip: "Working", plus "N agents running" from the Parallel Agents mirror; the header adds "N jobs" | same |
| The activity word while working: Thinking, Reading, Generating, Responding (`mixie_cat_activity_name`) | Header: the same word. Top-bar chip: "Running" | same (source pin) |
| Newest user prompt, dimmed ("Ask Lampway Agent anything..." when none) | The chat's transcript and composer placeholder (the chat window itself) | not separately tested |
| The sketch draft, its caret and the Voice button while a sketch is armed (`agent_ui_draw_pill_draft`) | The chat's composer, which shows the same draft (`sketch_prompt`) and the Voice chip | not separately tested |
| Click: restore the chat | Top-bar chip: opens the chat (`mixar.agent_bubble_open_window`); Ctrl+Shift+B toggles it | `test_closing_the_chat_with_the_pill_off_closes_it` |
| Drag: move the pill | Nothing to move: there is no pill. The chat window itself still drags | n/a |
| (new) What the agent said while the chat was closed | Top-bar chip: "N unread" | `test_the_chat_header_shows_every_pill_datum` |

With the preference on, the pill behaves exactly as before.

Gaps, said plainly: the pill's sketch draft over the viewport has not been driven with the pill off in a running app;
it reads the same `mixie_chat_input` the composer shows, but only a live run proves the sketch flow lands in the
composer with no pill window to type into.
