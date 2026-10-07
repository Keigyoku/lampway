/* SPDX-FileCopyrightText: 2026 Lampway contributors
 *
 * SPDX-License-Identifier: GPL-3.0-or-later */

/** \file
 * \ingroup spagentbubble
 *
 * Facelift contract 08: the media pane's "Before you send" column. It draws what
 * lampway_tools/ui/generate_pump.py wrote into the WindowManager
 * (`lampway_gen_*`): the estimate as a dashed chip (an estimate is never drawn
 * like a quote), the route host, the job against its cap as a meter (amber from
 * 80 percent, red over), the session line and the policy as the Generate
 * button's hover. Nothing here computes a price or a policy.
 */

#include <algorithm>
#include <cstring>
#include <optional>
#include <string>

#include "BKE_appdir.hh"
#include "BKE_context.hh"

#include "BLF_api.hh"

#include "BLI_path_utils.hh"
#include "BLI_rect.h"
#include "BLI_string.h"

#include "BLT_translation.hh"

#include "DNA_windowmanager_types.h"

#include "GPU_immediate.hh"
#include "GPU_state.hh"

#include "RNA_access.hh"

#include "UI_mixar_theme.hh"
#include "UI_mixar_tokens.hh"

#include "agent_ui_pane_kit.hh"
#include "agent_ui_tabmedia_intern.hh"
#include "agent_ui_text.hh"

/* Mixar 5.2 port: namespace wrap. */
namespace blender {

static void face_string(PointerRNA *wm_ptr, const char *name, char *out, const int out_len)
{
  out[0] = '\0';
  PropertyRNA *prop = RNA_struct_find_property(wm_ptr, name);
  if (prop && RNA_property_type(prop) == PROP_STRING) {
    /* The pump's strings have no maxlen: copy with the buffer's bound (the char* getter writes the whole string). */
    const std::string value = RNA_property_string_get(wm_ptr, prop);
    BLI_strncpy(out, value.c_str(), size_t(out_len));
  }
}

static float face_float(PointerRNA *wm_ptr, const char *name)
{
  PropertyRNA *prop = RNA_struct_find_property(wm_ptr, name);
  return (prop && RNA_property_type(prop) == PROP_FLOAT) ? RNA_property_float_get(wm_ptr, prop) : 0.0f;
}

bool media_face_read(const bContext *C, const char *owner, MediaFace *r_face)
{
  *r_face = {};
  wmWindowManager *wm = CTX_wm_manager(C);
  if (!wm) {
    return false;
  }
  PointerRNA wm_ptr = RNA_id_pointer_create(&wm->id);
  char face_owner[96];
  face_string(&wm_ptr, "lampway_gen_owner", face_owner, sizeof(face_owner));
  if (!face_owner[0] || !STREQ(face_owner, owner)) {
    return false;
  }
  face_string(&wm_ptr, "lampway_gen_estimate", r_face->estimate, sizeof(r_face->estimate));
  face_string(&wm_ptr, "lampway_gen_estimate_kind", r_face->estimate_kind, sizeof(r_face->estimate_kind));
  face_string(&wm_ptr, "lampway_gen_estimate_tip", r_face->estimate_tip, sizeof(r_face->estimate_tip));
  face_string(&wm_ptr, "lampway_gen_cap_job", r_face->cap_job, sizeof(r_face->cap_job));
  face_string(&wm_ptr, "lampway_gen_cap_job_level", r_face->cap_job_level, sizeof(r_face->cap_job_level));
  face_string(&wm_ptr, "lampway_gen_cap_session", r_face->cap_session, sizeof(r_face->cap_session));
  face_string(&wm_ptr, "lampway_gen_route", r_face->route, sizeof(r_face->route));
  face_string(&wm_ptr, "lampway_gen_content", r_face->content, sizeof(r_face->content));
  face_string(&wm_ptr, "lampway_gen_button", r_face->button, sizeof(r_face->button));
  face_string(&wm_ptr, "lampway_gen_button_kind", r_face->button_kind, sizeof(r_face->button_kind));
  face_string(&wm_ptr, "lampway_gen_policy", r_face->policy, sizeof(r_face->policy));
  face_string(&wm_ptr, "lampway_gen_refusal", r_face->refusal, sizeof(r_face->refusal));
  face_string(&wm_ptr, "lampway_gen_last_run", r_face->last_run, sizeof(r_face->last_run));
  r_face->cap_job_fill = face_float(&wm_ptr, "lampway_gen_cap_job_fill");
  r_face->cap_session_fill = face_float(&wm_ptr, "lampway_gen_cap_session_fill");
  return r_face->button[0] != '\0';
}

float media_face_column_w(const rctf &panel, const float u)
{
  const float w = BLI_rctf_size_x(&panel);
  if (w < 560.0f * u) {
    return 0.0f; /* Too narrow for two columns: the Generate label still carries the number. */
  }
  return std::min(380.0f * u, w * 0.36f);
}

/** IBM Plex Mono (release/datafiles/fonts/PlexMono.woff2) for numbers; the default face when it is missing. */
static int face_mono_font()
{
  static int font = -2;
  if (font == -2) {
    font = -1;
    if (std::optional<std::string> dir = BKE_appdir_folder_id(BLENDER_DATAFILES, "fonts")) {
      char path[FILE_MAX];
      BLI_path_join(path, sizeof(path), dir->c_str(), "PlexMono.woff2");
      font = BLF_load(path);
    }
  }
  return font >= 0 ? font : BLF_default();
}

static void face_text(const char *text, const float x, const float cy, const float size, const float col[4], const bool mono)
{
  if (!text || !text[0]) {
    return;
  }
  if (!mono) {
    pane_label_left(text, x, cy, size, col);
    return;
  }
  const int font = face_mono_font();
  BLF_size(font, size);
  BLF_color4fv(font, col);
  BLF_position(font, x, cy - size * 0.35f, 0.0f);
  BLF_draw(font, text, strlen(text));
}

static float face_text_w(const char *text, const float size, const bool mono)
{
  if (!mono) {
    return pane_text_width(text, size);
  }
  const int font = face_mono_font();
  BLF_size(font, size);
  return BLF_width(font, text, strlen(text));
}

/** \a text cut (UTF-8 safe) with an ellipsis until it fits \a max_w in its face; the whole line stays in the hover. */
static void face_fit(char *text, const size_t capacity, const float max_w, const float size, const bool mono)
{
  if (!mono) {
    pane_fit_text(text, capacity, max_w, size);
    return;
  }
  if (face_text_w(text, size, true) <= max_w) {
    return;
  }
  size_t len = strlen(text);
  while (len > 0) {
    do {
      len--;
    } while (len > 0 && (uchar(text[len]) & 0xC0) == 0x80);
    text[len] = '\0';
    char trial[512];
    SNPRINTF(trial, "%s\u2026", text);
    if (face_text_w(trial, size, true) <= max_w || len == 0) {
      BLI_strncpy(text, trial, capacity);
      return;
    }
  }
}

/** A dashed outline (DESIGN.md 8: an estimate is dashed, so it can never be read as a quote). */
static void face_dashed_rect(const rctf &r, const float dash, const float col[4])
{
  const int along_x = int(BLI_rctf_size_x(&r) / (2.0f * dash)) + 1;
  const int along_y = int(BLI_rctf_size_y(&r) / (2.0f * dash)) + 1;
  GPUVertFormat *format = immVertexFormat();
  const uint pos = GPU_vertformat_attr_add(format, "pos", gpu::VertAttrType::SFLOAT_32_32);
  immBindBuiltinProgram(GPU_SHADER_3D_UNIFORM_COLOR);
  immUniformColor4fv(col);
  immBegin(GPU_PRIM_LINES, 4 * (along_x + along_y));
  for (int i = 0; i < along_x; i++) {
    const float x = r.xmin + 2.0f * dash * i;
    const float x1 = std::min(x + dash, r.xmax);
    immVertex2f(pos, x, r.ymin);
    immVertex2f(pos, x1, r.ymin);
    immVertex2f(pos, x, r.ymax);
    immVertex2f(pos, x1, r.ymax);
  }
  for (int i = 0; i < along_y; i++) {
    const float y = r.ymin + 2.0f * dash * i;
    const float y1 = std::min(y + dash, r.ymax);
    immVertex2f(pos, r.xmin, y);
    immVertex2f(pos, r.xmin, y1);
    immVertex2f(pos, r.xmax, y);
    immVertex2f(pos, r.xmax, y1);
  }
  immEnd();
  immUnbindProgram();
}

rctf media_face_paint(const MediaFace &face, const rctf &column, const float u)
{
  float text[4], muted[4], line[4], stop[4], warn[4], track[4];
  ui::mixar_theme_color_f(ui::MixarThemeSlot::Text, text);
  ui::mixar_theme_color_f(ui::MixarThemeSlot::TextSecondary, muted);
  ui::mixar_theme_color_f(ui::MixarThemeSlot::BorderStrong, line);
  ui::mixar_theme_color_f(ui::MixarThemeSlot::Danger, stop);
  ui::mixar_theme_color_f(ui::MixarThemeSlot::Warning, warn);
  ui::mixar_theme_color_f(ui::MixarThemeSlot::Border, track);

  const float font = PANE_FONT * agent_ui_text_unit();
  const float font_sub = PANE_FONT_SUB * agent_ui_text_unit();
  const float x = column.xmin;
  const float w = BLI_rctf_size_x(&column);
  float y = column.ymax;

  GPU_blend(GPU_BLEND_ALPHA);
  pane_column_divider(column.xmin - 0.5f * PANE_INSET_X * u, column.ymin, column.ymax, u);

  /* "Before you send". */
  y -= font_sub;
  face_text(IFACE_("Before you send"), x, y, font_sub, muted, false);

  /* The estimate chip, then the route. */
  y -= 2.2f * font;
  const bool estimate = STREQ(face.estimate_kind, "estimate");
  const bool unknown = STREQ(face.estimate_kind, "unknown");
  const float pad = 8.0f * u;
  const float chip_w = face_text_w(face.estimate, font, true) + 2.0f * pad;
  const rctf chip = {x, x + chip_w, y - 0.9f * font, y + 0.9f * font};
  if (estimate) {
    face_dashed_rect(chip, 3.0f * u, line);
  }
  else if (!unknown) {
    face_dashed_rect(chip, 1.0e4f, line); /* One dash longer than any side: a solid outline, a quote's. */
  }
  face_text(face.estimate, chip.xmin + pad, y, font, unknown ? stop : text, true);
  if (face.route[0]) {
    face_text(face.route, chip.xmax + 2.0f * pad, y, font_sub, muted, false);
  }

  /* The job against its cap: words, then the meter (clear of the chip's outline). */
  y -= 2.5f * font;
  const bool over = STREQ(face.cap_job_level, "over");
  const bool amber = STREQ(face.cap_job_level, "warn");
  const float *meter_col = over ? stop : amber ? warn : muted;
  char cap_job[sizeof(face.cap_job) + 4];
  STRNCPY(cap_job, face.cap_job);
  face_fit(cap_job, sizeof(cap_job), w, font_sub, true);
  face_text(cap_job, x, y, font_sub, over ? stop : text, true);
  y -= 0.9f * font;
  const rctf bar = {x, x + w, y - 1.5f * u, y + 1.5f * u};
  pane_fill_round(&bar, 1.5f * u, track);
  if (face.cap_job_fill > 0.0f) {
    const rctf fill = {x, x + w * std::min(face.cap_job_fill, 1.0f), bar.ymin, bar.ymax};
    pane_fill_round(&fill, 1.5f * u, meter_col);
  }

  /* The session line, the content, and a refusal in the stop colour. */
  y -= 1.4f * font;
  char cap_session[sizeof(face.cap_session) + 4];
  STRNCPY(cap_session, face.cap_session);
  face_fit(cap_session, sizeof(cap_session), w, font_sub, true);
  face_text(cap_session, x, y, font_sub, muted, true);
  y -= 1.4f * font;
  if (face.content[0]) {
    char leaves[192];
    SNPRINTF(leaves, "%s %s", IFACE_("leaves:"), face.content);
    face_fit(leaves, sizeof(leaves), w, font_sub, false);
    face_text(leaves, x, y, font_sub, muted, false);
  }
  if (face.refusal[0]) {
    y -= 1.4f * font;
    char refusal[sizeof(face.refusal)];
    STRNCPY(refusal, face.refusal);
    pane_fit_text(refusal, w, font_sub);
    face_text(refusal, x, y, font_sub, stop, false);
  }
  if (face.last_run[0]) {
    /* The last run, billed against what was estimated before it was sent: the numbers in Plex Mono. */
    y -= 1.8f * font;
    char last_run[sizeof(face.last_run) + 4];
    STRNCPY(last_run, face.last_run);
    face_fit(last_run, sizeof(last_run), w, font_sub, true);
    face_text(last_run, x, y, font_sub, muted, true);
  }
  GPU_blend(GPU_BLEND_NONE);

  /* Generate fills the column's foot. */
  const float h = 1.15f * PANE_ROW_H * u;
  return {x, column.xmax, column.ymin, column.ymin + h};
}

}  // namespace blender
