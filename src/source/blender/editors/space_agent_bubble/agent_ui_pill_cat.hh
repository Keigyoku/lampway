/* SPDX-FileCopyrightText: 2026 Mixar Authors
 * SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
 *
 * SPDX-License-Identifier: GPL-3.0-or-later */

/** \file
 * \ingroup spagentbubble
 *
 * Mixie — an ink-black cat with luminous eyes. Shared by the resting pill
 * and parallel task cards, with a pure time-driven pose and six variations.
 */

#pragma once

#include "BLI_rect.h"

namespace blender {
struct MixieCatPose;
enum class MixieCatActivity;

/**
 * Paint Mixie inside \a chip. Every vertex stays inside that rect: the
 * pill window IS the capsule, and paint past it is clipped with no signal
 * (see `test_agent_bubble_pill_paint.py`).
 *
 * The region-owned activity controller supplies a smoothly blended pose.
 */
void agent_ui_draw_pill_cat(const rctf *chip, const MixieCatPose &pose, MixieCatActivity activity);

/** The seven agent states one painter draws everywhere an agent appears (facelift contract 05, DESIGN.md 7 and 13). */
enum class AgentSparkState { Idle, Working, Unread, Blocked, Paused, Done, Failed };

/** The Spark in \a state; the ring is the state, every colour the theme's, nothing animates. */
void agent_ui_draw_spark(const rctf &chip, AgentSparkState state, float alpha);

/** Shared painter (idle or working); does not modify the pill's QA geometry. Alpha follows card
 * transitions. */
void agent_ui_draw_cat(const rctf &chip, double now, bool working, int variation, float alpha);

/** Last painted chip, in the same window-content pixels the painter used. */
bool agent_ui_pill_cat_last_rect(rcti *r_rect);

/** Drop the last-painted rect. Call from the compact status-pill path so a
 * stale Mixie target is not exported while the island is open. */
void agent_ui_pill_cat_clear();

/** HEADER-region provider on the pill window; `surface` is `pill_cat`. */
void agent_ui_pill_cat_qa_register();

}  // namespace blender
