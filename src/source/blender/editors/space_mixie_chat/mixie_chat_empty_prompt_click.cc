/* SPDX-FileCopyrightText: 2025 Blender Authors
 * SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
 * SPDX-FileCopyrightText: 2026 Lampway contributors
 *
 * SPDX-License-Identifier: GPL-3.0-or-later */

/** \file
 * \ingroup spmixiechat
 *
 * LAMPWAY: keep the existing empty-prompt click dispatch in its own bounded module.
 */

#include "BLI_rect.h"
#include "BLT_translation.hh"
#include "BKE_context.hh"
#include "DNA_screen_types.h"
#include "DNA_space_types.h"
#include "RNA_access.hh"
#include "WM_api.hh"
#include "WM_types.hh"
#include "mixie_chat_intern.hh"

namespace blender {

static SpaceMixieChat *get_space_mixie_chat(const bContext *C)
{
  ScrArea *area = CTX_wm_area(C);
  if (area && area->spacetype == SPACE_AGENT_BUBBLE) {
    return static_cast<SpaceMixieChat *>(area->spacedata.first);
  }
  return nullptr;
}

bool mixie_chat_handle_empty_prompt_click(bContext *C,
                                          ARegion *region,
                                          float mouse_x,
                                          float mouse_y)
{
  SpaceMixieChat *smixie = get_space_mixie_chat(C);
  if (!smixie) {
    return false;
  }
  MixieChatRuntime *rt = mixie_chat_ensure_runtime(smixie);

  if (!rt->empty_prompts_visible) {
    return false;
  }

  for (int i = 0; i < CHAT_EMPTY_PROMPT_COUNT; i++) {
    if (BLI_rctf_isect_pt(&rt->empty_prompts[i].bounds, mouse_x, mouse_y)) {
      wmOperatorType *ot = WM_operatortype_find("mixie_chat.insert_prompt_text", true);
      if (ot) {
        PointerRNA op_ptr = WM_operator_properties_create_ptr(ot);
        RNA_string_set(&op_ptr, "text", IFACE_(rt->empty_prompts[i].text));
        RNA_string_set(&op_ptr, "mode", g_empty_prompt_modes[i]);
        RNA_string_set(&op_ptr, "generate_type", g_empty_prompt_generate_types[i]);
        mixie_chat_call_operator_and_redraw(C, region, ot, &op_ptr);
        WM_operator_properties_free(&op_ptr);
        return true;
      }
    }
  }

  return false;
}

}  // namespace blender
