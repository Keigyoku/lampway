/* SPDX-FileCopyrightText: 2026 Lampway contributors
 *
 * SPDX-License-Identifier: GPL-3.0-or-later */

/** \file
 * \ingroup edinterface
 *
 * Facelift contract 13 (P1): the drawn spend card. The card is still the Python popup of `lampway.studio_confirm`
 * (Python owns the words, the operators and the gate); its rows are labels the RNA item `layout.mixar_spend()` tags
 * as spend elements, and this file paints them:
 *
 *   SpendTitle  the action in Fraunces, the card's left rule beside it
 *   SpendPrice  the number in Fraunces, large, its unit in IBM Plex Mono, and the kind as an outlined chip
 *   SpendMeter  the words above a meter whose used part and pending part are two segments (the pending part
 *               hatched), the used part in stop when it passes 90 percent
 *   SpendLine   a plain secondary line
 *
 * Every element draws the 4 px rule at its left edge in the card's state colour (accent waiting, stop refused,
 * agent when an agent tried, go when spent), so a column of elements reads as one card with one rule.
 * A meter's label packs its numbers after the words: "<words>\x1f<used>\x1f<pending>\x1f<hot>".
 */

#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <optional>
#include <string>

#include "BKE_appdir.hh"

#include "BLF_api.hh"

#include "BLI_math_vector.h"
#include "BLI_path_utils.hh"
#include "BLI_rect.h"
#include "BLI_string.h"

#include "GPU_immediate.hh"
#include "GPU_immediate_util.hh"
#include "GPU_state.hh"

#include "UI_interface_c.hh"
#include "UI_interface_layout.hh"
#include "UI_mixar.hh"
#include "UI_resources.hh"
#include "UI_mixar_tokens.hh"

#include "interface_intern.hh"
#include "interface_mixar_spend_card.hh"

/* Mixar 5.2 port: namespace wrap. */
namespace blender::ui {

namespace {

int spend_font(const char *file)
{
  if (std::optional<std::string> dir = BKE_appdir_folder_id(BLENDER_DATAFILES, "fonts")) {
    char path[FILE_MAX];
    BLI_path_join(path, sizeof(path), dir->c_str(), file);
    const int font = BLF_load(path);
    if (font >= 0) {
      return font;
    }
  }
  return BLF_default();
}

int fraunces()
{
  static int font = -2;
  if (font == -2) {
    font = spend_font("Fraunces.woff2");
  }
  return font;
}

int plex_mono()
{
  static int font = -2;
  if (font == -2) {
    font = spend_font("PlexMono.woff2");
  }
  return font;
}

void rule_colour_get(const int rule, float r_col[4])
{
  static const float agent[4] = {0x9E / 255.0f, 0xA0 / 255.0f, 0xF7 / 255.0f, 1.0f}; /* tokens: agent */
  static const float go[4] = {0x5B / 255.0f, 0xC4 / 255.0f, 0x8F / 255.0f, 1.0f};    /* tokens: go */
  const mixar_tokens::Palette &p = mixar_tokens::mixar_zen();
  const float *src = rule == 1 ? p.danger : rule == 2 ? agent : rule == 3 ? go : p.focus;
  copy_v4_v4(r_col, src);
}

void fill_rect(const rctf &r, const float col[4])
{
  const uint pos = GPU_vertformat_attr_add(immVertexFormat(), "pos", gpu::VertAttrType::SFLOAT_32_32);
  immBindBuiltinProgram(GPU_SHADER_3D_UNIFORM_COLOR);
  immUniformColor4fv(col);
  immRectf(pos, r.xmin, r.ymin, r.xmax, r.ymax);
  immUnbindProgram();
}

void draw_rule(const rcti *rect, const int rule)
{
  float col[4];
  rule_colour_get(rule, col);
  const rctf r = {float(rect->xmin), float(rect->xmin) + 4.0f * UI_SCALE_FAC, float(rect->ymin) - 1.0f,
                  float(rect->ymax) + 1.0f};
  fill_rect(r, col);
}

void text_at(const int font, const char *text, const float x, const float cy, const float size, const float col[4])
{
  BLF_size(font, size);
  BLF_color4fv(font, col);
  BLF_position(font, x, cy - size * 0.35f, 0.0f);
  BLF_draw(font, text, strlen(text));
}

float text_w(const int font, const char *text, const float size)
{
  BLF_size(font, size);
  return BLF_width(font, text, strlen(text));
}

/** "<words>\x1f<used>\x1f<pending>\x1f<hot>" -> the parts (the numbers default to 0). */
void unpack_meter(const std::string &s, std::string &r_words, float &r_used, float &r_pending, bool &r_hot)
{
  const size_t a = s.find('\x1f');
  r_words = s.substr(0, a);
  r_used = r_pending = 0.0f;
  r_hot = false;
  if (a == std::string::npos) {
    return;
  }
  const size_t b = s.find('\x1f', a + 1);
  const size_t c = b == std::string::npos ? std::string::npos : s.find('\x1f', b + 1);
  r_used = float(std::atof(s.substr(a + 1, b - a - 1).c_str()));
  if (b != std::string::npos) {
    r_pending = float(std::atof(s.substr(b + 1, c - b - 1).c_str()));
  }
  if (c != std::string::npos) {
    r_hot = s.substr(c + 1) == "1";
  }
}

void draw_title(const Button *but, const rcti *rect)
{
  const float size = 17.0f * UI_SCALE_FAC;
  const float x = float(rect->xmin) + 14.0f * UI_SCALE_FAC;
  text_at(fraunces(), but->str.c_str(), x, BLI_rcti_cent_y_fl(rect), size, mixar_tokens::mixar_zen().strong);
}

void draw_price(const Button *but, const rcti *rect)
{
  const mixar_tokens::Palette &p = mixar_tokens::mixar_zen();
  /* "18 credits|quoted": the number, its unit, the kind. */
  std::string s = but->str;
  std::string kind;
  if (const size_t bar = s.find('\x1f'); bar != std::string::npos) {
    kind = s.substr(bar + 1);
    s = s.substr(0, bar);
  }
  std::string number = s, unit;
  if (const size_t sp = s.find(' '); sp != std::string::npos) {
    number = s.substr(0, sp);
    unit = s.substr(sp + 1);
  }
  const float cy = BLI_rcti_cent_y_fl(rect);
  const float big = std::min(40.0f * UI_SCALE_FAC, float(BLI_rcti_size_y(rect)) * 0.8f);
  float x = float(rect->xmin) + 14.0f * UI_SCALE_FAC;
  text_at(fraunces(), number.c_str(), x, cy, big, p.strong);
  x += text_w(fraunces(), number.c_str(), big) + 8.0f * UI_SCALE_FAC;
  const float small = 13.0f * UI_SCALE_FAC;
  if (!unit.empty()) {
    text_at(plex_mono(), unit.c_str(), x, cy, small, p.secondary);
    x += text_w(plex_mono(), unit.c_str(), small) + 12.0f * UI_SCALE_FAC;
  }
  if (!kind.empty()) {
    const float pad = 6.0f * UI_SCALE_FAC;
    const float w = text_w(plex_mono(), kind.c_str(), small) + 2.0f * pad;
    const rctf chip = {x, x + w, cy - 0.85f * small, cy + 0.85f * small};
    draw_roundbox_corner_set(CNR_ALL);
    draw_roundbox_4fv(&chip, false, 4.0f * UI_SCALE_FAC, p.border);
    text_at(plex_mono(), kind.c_str(), x + pad, cy, small, p.secondary);
  }
}

void draw_meter(const Button *but, const rcti *rect)
{
  const mixar_tokens::Palette &p = mixar_tokens::mixar_zen();
  std::string words;
  float used, pending;
  bool hot;
  unpack_meter(but->str, words, used, pending, hot);
  const float x0 = float(rect->xmin) + 14.0f * UI_SCALE_FAC;
  const float x1 = float(rect->xmax) - 8.0f * UI_SCALE_FAC;
  const float h = float(BLI_rcti_size_y(rect));
  const float size = 12.0f * UI_SCALE_FAC;
  text_at(plex_mono(), words.c_str(), x0, float(rect->ymin) + h * 0.66f, size, p.text);
  const float bar_y = float(rect->ymin) + h * 0.24f;
  const float bar_h = 4.0f * UI_SCALE_FAC;
  const rctf track = {x0, x1, bar_y, bar_y + bar_h};
  fill_rect(track, p.border);
  const float w = x1 - x0;
  const float u = std::clamp(used, 0.0f, 1.0f);
  const float q = std::clamp(pending, 0.0f, 1.0f - u);
  if (u > 0.0f) {
    fill_rect({x0, x0 + w * u, track.ymin, track.ymax}, hot ? p.danger : p.secondary);
  }
  if (q > 0.0f) {
    /* The pending amount, hatched: stripes 2 px wide every 5 px, in the accent. */
    const float a = x0 + w * u, b = a + w * q;
    for (float s = a; s < b; s += 5.0f * UI_SCALE_FAC) {
      fill_rect({s, std::min(s + 2.0f * UI_SCALE_FAC, b), track.ymin, track.ymax}, p.focus);
    }
  }
}

void draw_line(const Button *but, const rcti *rect)
{
  text_at(BLF_default(), but->str.c_str(), float(rect->xmin) + 14.0f * UI_SCALE_FAC, BLI_rcti_cent_y_fl(rect),
          12.0f * UI_SCALE_FAC, mixar_tokens::mixar_zen().secondary);
}

}  // namespace

void UI_layout_mixar_spend_row(Layout *layout, const int element, const char *text, const int rule)
{
  layout->label(text ? text : "", ICON_NONE);
  Block *block = layout->block();
  if (!block->buttons_ptrs.is_empty()) {
    mixar_style_card(block->buttons_ptrs.last().get(), MixarCardElement(element), float(rule));
  }
}

bool UI_mixar_spend_card_draw(const Button *but, const rcti *rect, const MixarCardElement element)
{
  if (!ELEM(element, MixarCardElement::SpendTitle, MixarCardElement::SpendPrice, MixarCardElement::SpendMeter,
            MixarCardElement::SpendLine))
  {
    return false;
  }
  GPU_blend(GPU_BLEND_ALPHA);
  draw_rule(rect, int(but->mixar_style.icon));
  switch (element) {
    case MixarCardElement::SpendTitle:
      draw_title(but, rect);
      break;
    case MixarCardElement::SpendPrice:
      draw_price(but, rect);
      break;
    case MixarCardElement::SpendMeter:
      draw_meter(but, rect);
      break;
    default:
      draw_line(but, rect);
      break;
  }
  return true;
}

}  // namespace blender::ui
