/* SPDX-FileCopyrightText: 2025 Blender Authors
 * SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
 * SPDX-FileCopyrightText: 2026 Lampway contributors
 *
 * SPDX-License-Identifier: GPL-3.0-or-later */

/** \file
 * \ingroup spmixiechat
 *
 * LAMPWAY: existing message content and hover-state traversal in a bounded module.
 */

#include "BLI_time.h"
#include "BKE_context.hh"
#include "DNA_screen_types.h"
#include "DNA_space_types.h"
#include "RNA_access.hh"
#include "WM_api.hh"
#include "WM_types.hh"
#include "mixie_chat_intern.hh"

namespace blender {

bool mixie_chat_message_has_slot_content(PointerRNA *msg_ptr)
{
  bool has_slot_content = false;
  int bubble_id_len = g_msg_props.bubble_id ?
      RNA_property_string_length(msg_ptr, g_msg_props.bubble_id) : 0;
  if (bubble_id_len > 0) {
    bool loader_visible = g_msg_props.loader_visible ?
        RNA_property_boolean_get(msg_ptr, g_msg_props.loader_visible) : false;
    int content_len = g_msg_props.content ?
        RNA_property_string_length(msg_ptr, g_msg_props.content) : 0;
    int ephemeral_len = g_msg_props.ephemeral ?
        RNA_property_string_length(msg_ptr, g_msg_props.ephemeral) : 0;
    int todo_count = g_msg_props.todo_items ?
        RNA_property_collection_length(msg_ptr, g_msg_props.todo_items) : 0;
    int action_count = g_msg_props.action_items ?
        RNA_property_collection_length(msg_ptr, g_msg_props.action_items) : 0;
    int step_count = g_msg_props.step_items ?
        RNA_property_collection_length(msg_ptr, g_msg_props.step_items) : 0;
    int thinking_len = g_msg_props.thinking_text ?
        RNA_property_string_length(msg_ptr, g_msg_props.thinking_text) : 0;
    bool thinking_active = g_msg_props.thinking_active ?
        RNA_property_boolean_get(msg_ptr, g_msg_props.thinking_active) : false;
    (void)thinking_active;
    has_slot_content = loader_visible || (content_len > 0) || (ephemeral_len > 0) || (todo_count > 0) || (action_count > 0) || (step_count > 0) || (thinking_len > 0);
  }
  return has_slot_content;
}

void mixie_chat_update_message_cursor(const bContext *C,
                                      wmWindow *win,
                                      const MixieChatRuntime *rt)
{
  /* Update cursor based on slot action, action button, and feedback hover states */
  bool any_button_hovered = false;
  for (const MessageLayoutData &layout : rt->layout_cache) {
    for (int i = 0; i < layout.slot_action_count; i++) {
      if (layout.slot_actions[i].is_hovered) {
        any_button_hovered = true;
        break;
      }
    }
    if (!any_button_hovered) {
      for (int i = 0; i < layout.action_button_count; i++) {
        if (layout.action_buttons[i].is_hovered) {
          any_button_hovered = true;
          break;
        }
      }
    }
    /* Feedback votes highlight on hover without changing the island cursor. */
    if (any_button_hovered) {
      break;
    }
  }

  if (win) {
    /* The Agent Bubble never shows the hand cursor (see
     * mixie_chat_main_region_cursor) — hover highlights still draw. */
    ScrArea *cursor_area = CTX_wm_area(C);
    const bool suppress_hand = (cursor_area &&
                                cursor_area->spacetype == SPACE_AGENT_BUBBLE);
    WM_cursor_set(win,
                  (any_button_hovered && !suppress_hand) ? WM_CURSOR_HAND :
                                                           WM_CURSOR_DEFAULT);
  }
}

float mixie_chat_message_slide_offset(ARegion *region,
                                      MixieChatRuntime *rt,
                                      bool *r_active)
{
  float slide_x_offset = 0.0f;
  bool slide_anim_active = false;
  if (rt->slide_anim_msg_index >= 0) {
    double now = BLI_time_now_seconds();
    double elapsed = now - rt->slide_anim_start;
    const double anim_duration = 0.25;
    if (elapsed >= anim_duration) {
      rt->slide_anim_msg_index = -1;
    }
    else {
      slide_anim_active = true;
      float t = float(elapsed / anim_duration);
      /* Ease-out cubic: fast start, gentle deceleration */
      float progress = 1.0f - (1.0f - t) * (1.0f - t) * (1.0f - t);
      slide_x_offset = float(region->winx) * 0.3f * (1.0f - progress);
    }
  }
  *r_active = slide_anim_active;
  return slide_x_offset;
}

}  // namespace blender
