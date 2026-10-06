/* SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
 *
 * SPDX-License-Identifier: GPL-3.0-or-later */

/** \file
 * \ingroup edinterface
 */

#include <cstring>

#include "BLI_listbase.h"

#include "DNA_theme_types.h"
#include "DNA_userdef_types.h"

#include "UI_mixar_theme.hh"
#include "UI_mixar_tokens.hh"

namespace blender::ui {

struct MixarThemeRec {
  bool agent_space;
  int offset;
  unsigned char fallback[4];
};

static const MixarThemeRec k_mixar_theme[] = {
    {false, offsetof(ThemeUI, mixar_canvas), {14, 16, 22, 255}},
    {false, offsetof(ThemeUI, mixar_panel), {22, 25, 34, 255}},
    {false, offsetof(ThemeUI, mixar_input), {17, 19, 26, 255}},
    {false, offsetof(ThemeUI, mixar_control), {30, 34, 45, 255}},
    {false, offsetof(ThemeUI, mixar_selected), {58, 47, 23, 255}},
    {false, offsetof(ThemeUI, mixar_text), {236, 232, 223, 255}},
    {false, offsetof(ThemeUI, mixar_text_strong), {247, 244, 238, 255}},
    {false, offsetof(ThemeUI, mixar_text_secondary), {169, 166, 157, 255}},
    {false, offsetof(ThemeUI, mixar_border), {43, 48, 61, 255}},
    {false, offsetof(ThemeUI, mixar_focus), {237, 185, 68, 255}},
    {false, offsetof(ThemeUI, mixar_primary), {90, 71, 32, 255}},
    {false, offsetof(ThemeUI, mixar_danger), {240, 118, 107, 255}},
    {false, offsetof(ThemeUI, mixar_warning), {237, 185, 68, 255}},
    {false, offsetof(ThemeUI, mixar_action), {22, 25, 34, 255}},
    {false, offsetof(ThemeUI, mixar_glyph), {236, 232, 223, 255}},
    {false, offsetof(ThemeUI, mixar_chip), {30, 34, 45, 255}},
    {false, offsetof(ThemeUI, mixar_chip_active), {58, 47, 23, 255}},
    {false, offsetof(ThemeUI, mixar_gray_800), {17, 19, 26, 255}},
    {false, offsetof(ThemeUI, mixar_gray_700), {30, 34, 45, 255}},
    {false, offsetof(ThemeUI, mixar_border_strong), {59, 66, 82, 255}},
    {false, offsetof(ThemeUI, mixar_bg), {22, 25, 34, 255}},
    {false, offsetof(ThemeUI, mixar_fg_1), {236, 232, 223, 255}},
    {false, offsetof(ThemeUI, mixar_fg_2), {207, 203, 194, 255}},
    {false, offsetof(ThemeUI, mixar_fg_3), {169, 166, 157, 255}},
    {false, offsetof(ThemeUI, mixar_fg_4), {125, 122, 115, 255}},
    {false, offsetof(ThemeUI, mixar_pane_wash), {22, 25, 34, 255}},
    {false, offsetof(ThemeUI, mixar_pane_pill_dim), {43, 48, 61, 255}},
    {false, offsetof(ThemeUI, mixar_pane_pill_on), {58, 47, 23, 255}},
    {false, offsetof(ThemeUI, mixar_brand), {237, 185, 68, 255}},
    {false, offsetof(ThemeUI, mixar_brand_text), {14, 16, 22, 255}},
    {false, offsetof(ThemeUI, mixar_queue), {43, 48, 61, 255}},
    {false, offsetof(ThemeUI, mixar_queue_count), {125, 122, 115, 255}},
    {false, offsetof(ThemeUI, mixar_slider_track), {17, 19, 26, 255}},
    {false, offsetof(ThemeUI, mixar_slider_thumb), {237, 185, 68, 255}},
    {false, offsetof(ThemeUI, mixar_slider_thumb_hover), {246, 205, 107, 255}},
    {false, offsetof(ThemeUI, mixar_slider_label), {236, 232, 223, 255}},
    {false, offsetof(ThemeUI, mixar_cinema_pill_fill), {17, 19, 26, 255}},
    {false, offsetof(ThemeUI, mixar_cinema_pill_border), {43, 48, 61, 255}},
    {false, offsetof(ThemeUI, mixar_cinema_pill_on_a), {58, 47, 23, 255}},
    {false, offsetof(ThemeUI, mixar_cinema_pill_on_b), {90, 71, 32, 255}},
    {false, offsetof(ThemeUI, mixar_cinema_pill_border_on), {237, 185, 68, 255}},
    {false, offsetof(ThemeUI, mixar_cinema_pill_label), {125, 122, 115, 255}},
    {false, offsetof(ThemeUI, mixar_cinema_pill_label_on), {247, 244, 238, 255}},
    {false, offsetof(ThemeUI, mixar_viewport_fill), {17, 19, 26, 255}},
    {false, offsetof(ThemeUI, mixar_viewport_border), {43, 48, 61, 255}},
    {false, offsetof(ThemeUI, mixar_viewport_label), {169, 166, 157, 255}},
    {false, offsetof(ThemeUI, mixar_viewport_label_on), {236, 232, 223, 255}},
    {false, offsetof(ThemeUI, mixar_profile_fill), {22, 25, 34, 255}},
    {false, offsetof(ThemeUI, mixar_profile_label), {236, 232, 223, 255}},
    {false, offsetof(ThemeUI, mixar_profile_avatar), {38, 43, 56, 255}},
    {false, offsetof(ThemeUI, mixar_profile_glyph), {207, 203, 194, 255}},
    {false, offsetof(ThemeUI, mixar_cinema_row_top), {38, 43, 56, 255}},
    {false, offsetof(ThemeUI, mixar_cinema_row_bottom), {22, 25, 34, 255}},
    {false, offsetof(ThemeUI, mixar_cinema_row_hover), {38, 43, 56, 255}},
    {false, offsetof(ThemeUI, mixar_cinema_row_track), {17, 19, 26, 255}},
    {false, offsetof(ThemeUI, mixar_cinema_row_text_on), {247, 244, 238, 255}},
    {false, offsetof(ThemeUI, mixar_cinema_row_text_off), {207, 203, 194, 255}},
    {false, offsetof(ThemeUI, mixar_cinema_row_text_disabled), {125, 122, 115, 255}},
    {false, offsetof(ThemeUI, mixar_cinema_row_caption), {169, 166, 157, 217}},
    {false, offsetof(ThemeUI, mixar_cinema_row_slider_on), {237, 185, 68, 255}},
    {false, offsetof(ThemeUI, mixar_cinema_card_top), {30, 34, 45, 245}},
    {false, offsetof(ThemeUI, mixar_cinema_card_bottom), {22, 25, 34, 245}},
    {false, offsetof(ThemeUI, mixar_cinema_label), {169, 166, 157, 255}},
    {false, offsetof(ThemeUI, mixar_cinema_dimmer), {43, 48, 61, 255}},
    {false, offsetof(ThemeUI, mixar_cinema_keycap), {125, 122, 115, 255}},
    {false, offsetof(ThemeUI, mixar_cinema_phone), {43, 48, 61, 255}},
    {false, offsetof(ThemeUI, mixar_cinema_chip), {43, 48, 61, 255}},
    {false, offsetof(ThemeUI, mixar_cinema_brand_top), {14, 16, 22, 255}},
    {false, offsetof(ThemeUI, mixar_cinema_brand_bottom), {58, 47, 23, 255}},
    {false, offsetof(ThemeUI, mixar_cinema_gate_fill), {236, 232, 223, 18}},
    {false, offsetof(ThemeUI, mixar_widget_border), {43, 48, 61, 255}},
    {false, offsetof(ThemeUI, mixar_ink), {247, 244, 238, 255}},
    {false, offsetof(ThemeUI, mixar_sunken), {17, 19, 26, 255}},
    {false, offsetof(ThemeUI, mixar_gradient_start), {90, 71, 32, 255}},
    {false, offsetof(ThemeUI, mixar_gradient_mid_a), {90, 71, 32, 255}},
    {false, offsetof(ThemeUI, mixar_gradient_mid_b), {90, 71, 32, 255}},
    {false, offsetof(ThemeUI, mixar_gradient_end), {90, 71, 32, 255}},
    {false, offsetof(ThemeUI, mixar_toolbar_background), {22, 25, 34, 255}},
    {false, offsetof(ThemeUI, mixar_toolbar_border), {43, 48, 61, 255}},
    {false, offsetof(ThemeUI, mixar_toolbar_primary), {58, 47, 23, 255}},
    {false, offsetof(ThemeUI, mixar_toolbar_primary_border), {237, 185, 68, 255}},
    {false, offsetof(ThemeUI, mixar_toolbar_text), {236, 232, 223, 255}},
    {false, offsetof(ThemeUI, mixar_toolbar_muted), {125, 122, 115, 255}},
    {false, offsetof(ThemeUI, mixar_toolbar_selected), {58, 47, 23, 255}},
    {false, offsetof(ThemeUI, mixar_glass_wash), {14, 16, 22, 51}},
    {false, offsetof(ThemeUI, mixar_sketch_ink), {125, 122, 115, 255}},
    {true, offsetof(ThemeSpace, agent_border), {59, 66, 82, 255}},
    {true, offsetof(ThemeSpace, agent_tab_active), {58, 47, 23, 255}},
    {true, offsetof(ThemeSpace, agent_accent), {237, 185, 68, 255}},
};

static_assert(sizeof(k_mixar_theme) / sizeof(k_mixar_theme[0]) == int(MixarThemeSlot::Count),
              "theme slot table must match LampwayThemeSlot");

static const unsigned char *mixar_theme_stored(MixarThemeSlot slot)
{
  const int index = int(slot);
  if (index < 0 || index >= int(MixarThemeSlot::Count)) {
    return nullptr;
  }
  bTheme *theme = static_cast<bTheme *>(U.themes.first);
  if (theme == nullptr) {
    return nullptr;
  }
  const MixarThemeRec &rec = k_mixar_theme[index];
  unsigned char *base = rec.agent_space ? reinterpret_cast<unsigned char *>(&theme->space_agent_bubble) :
                                           reinterpret_cast<unsigned char *>(&theme->tui);
  return base + rec.offset;
}

static bool mixar_theme_is_set(const unsigned char color[4])
{
  return (color[0] | color[1] | color[2] | color[3]) != 0;
}

void mixar_theme_color_u(MixarThemeSlot slot, unsigned char out[4])
{
  const int index = int(slot);
  if (index < 0 || index >= int(MixarThemeSlot::Count)) {
    memset(out, 0, sizeof(unsigned char[4]));
    return;
  }
  const unsigned char *stored = mixar_theme_stored(slot);
  const unsigned char *src = (stored != nullptr && mixar_theme_is_set(stored)) ?
                                 stored :
                                 k_mixar_theme[index].fallback;
  memcpy(out, src, sizeof(unsigned char[4]));
}

void mixar_theme_copy_u(MixarThemeSlot slot, const unsigned char fallback[4], unsigned char out[4])
{
  if (int(slot) >= 0 && int(slot) < int(MixarThemeSlot::Count)) {
    /* Old preferences must use the current palette, not a caller's old artboard colors. */
    mixar_theme_color_u(slot, out);
  }
  else {
    memcpy(out, fallback, sizeof(unsigned char[4]));
  }
}

void mixar_theme_color_f(MixarThemeSlot slot, float out[4])
{
  unsigned char color[4];
  mixar_theme_color_u(slot, color);
  out[0] = float(color[0]) / 255.0f;
  out[1] = float(color[1]) / 255.0f;
  out[2] = float(color[2]) / 255.0f;
  out[3] = float(color[3]) / 255.0f;
}

const unsigned char *mixar_theme_color_ptr(MixarThemeSlot slot)
{
  static unsigned char cache[int(MixarThemeSlot::Count)][4];
  static unsigned char zero[4] = {};
  const int index = int(slot);
  if (index < 0 || index >= int(MixarThemeSlot::Count)) {
    return zero;
  }
  mixar_theme_color_u(slot, cache[index]);
  return cache[index];
}

void mixar_moodboard_canvas_color(float out[4])
{
  const bTheme *theme = static_cast<const bTheme *>(U.themes.first);
  /* TH_BACK chooses sidebar colors in TOOL_PROPS; the drawer is a canvas. */
  for (int i = 0; i < 3; i++) {
    out[i] = theme ? float(theme->space_mixie.back[i]) / 255.0f : 38.0f / 255.0f;
  }
  out[3] = 1.0f;
}

namespace mixar_tokens {

const Palette &mixar_zen()
{
  static Palette palette = zen;
  auto load = [](MixarThemeSlot slot, float out[4]) { mixar_theme_color_f(slot, out); };
  load(MixarThemeSlot::Canvas, palette.canvas);
  load(MixarThemeSlot::Panel, palette.panel);
  load(MixarThemeSlot::Input, palette.input);
  load(MixarThemeSlot::Control, palette.control);
  load(MixarThemeSlot::Selected, palette.selected);
  load(MixarThemeSlot::Text, palette.text);
  load(MixarThemeSlot::TextStrong, palette.strong);
  load(MixarThemeSlot::TextSecondary, palette.secondary);
  load(MixarThemeSlot::Border, palette.border);
  load(MixarThemeSlot::Focus, palette.focus);
  load(MixarThemeSlot::Primary, palette.primary);
  load(MixarThemeSlot::Danger, palette.danger);
  load(MixarThemeSlot::Warning, palette.warning);
  load(MixarThemeSlot::Action, palette.action);
  return palette;
}

}  // namespace mixar_tokens
}  // namespace blender::ui
