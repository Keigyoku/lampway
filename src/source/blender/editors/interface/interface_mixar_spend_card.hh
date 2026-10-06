/* SPDX-FileCopyrightText: 2026 Lampway contributors
 *
 * SPDX-License-Identifier: GPL-3.0-or-later */

/** \file
 * \ingroup edinterface
 *
 * Facelift contract 13 (P1): the drawn spend card's elements (see interface_mixar_spend_card.cc).
 */

#pragma once

#include "UI_mixar_types.hh"

namespace blender {
struct rcti;
}

namespace blender::ui {
struct Button;
struct Layout;

/** Add one spend-card row to \a layout: a label tagged as \a element (a #MixarCardElement) with its rule state. */
void UI_layout_mixar_spend_row(Layout *layout, int element, const char *text, int rule);

/** Paint \a but when it is a spend-card element; false for any other element. */
bool UI_mixar_spend_card_draw(const Button *but, const rcti *rect, MixarCardElement element);

}  // namespace blender::ui
