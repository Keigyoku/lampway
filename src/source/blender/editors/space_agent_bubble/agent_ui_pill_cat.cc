/* SPDX-FileCopyrightText: 2026 Mixar Authors
 * SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
 *
 * SPDX-License-Identifier: GPL-3.0-or-later */

/** \file
 * \ingroup spagentbubble
 *
 * The agent avatar on the resting pill and the Parallel Agents cards: a flame in a ring, drawn procedurally at any UI scale. The activity state machine
 * (agent_ui_cat_activity.hh) still decides which state to show.
 */

#include <algorithm>
#include <cmath>

#include "BLI_listbase.h"
#include "BLI_rect.h"
#include "BLI_time.h"
#include "BLI_utildefines.h"

#include "DNA_screen_types.h"
#include "DNA_space_types.h"
#include "DNA_windowmanager_types.h"

#include "GPU_immediate.hh"
#include "GPU_matrix.hh"
#include "GPU_state.hh"

#include "../interface/interface_qa_inspect.hh"

#include "agent_ui_cat_activity.hh"
#include "agent_ui_cat_style.hh"
#include "agent_ui_pill_cat.hh"
#include "agent_ui_pill_cat_pose.hh"

namespace blender {

namespace {

rcti g_last_cat_rect = {};
bool g_last_cat_valid = false;
MixieCatActivity g_last_activity = MixieCatActivity::Idle;

/** Geometry owns its pixel-sized coverage fringe. Widget roundbox shaders
 * assume pixel-space coordinates and cannot be used under the mascot scale. */
void polygon(const float (*points)[2],
             int count,
             float pixel,
             const float color[4],
             const float *anchor = nullptr)
{
  float center[2] = {};
  for (int i = 0; i < count; i++) {
    center[0] += points[i][0] / count;
    center[1] += points[i][1] / count;
  }
  if (anchor) {
    center[0] = anchor[0];
    center[1] = anchor[1];
  }
  GPUVertFormat *format = immVertexFormat();
  const uint pos = GPU_vertformat_attr_add(format, "pos", gpu::VertAttrType::SFLOAT_32_32);
  const uint col = GPU_vertformat_attr_add(format, "color", gpu::VertAttrType::SFLOAT_32_32_32_32);
  immBindBuiltinProgram(GPU_SHADER_3D_SMOOTH_COLOR);
  immBegin(GPU_PRIM_TRIS, count * 9);
  auto vertex = [&](float x, float y, float alpha) {
    immAttr4f(col, color[0], color[1], color[2], alpha);
    immVertex2f(pos, x, y);
  };
  for (int i = 0; i < count; i++) {
    const float *a = points[i], *b = points[(i + 1) % count];
    float outer[2][2];
    for (int k = 0; k < 2; k++) {
      const float *v = k == 0 ? a : b;
      const float dx = v[0] - center[0], dy = v[1] - center[1];
      const float factor = pixel / std::max(0.001f, std::sqrt(dx * dx + dy * dy));
      outer[k][0] = v[0] + dx * factor;
      outer[k][1] = v[1] + dy * factor;
    }
    vertex(center[0], center[1], color[3]);
    vertex(a[0], a[1], color[3]);
    vertex(b[0], b[1], color[3]);
    vertex(a[0], a[1], color[3]);
    vertex(outer[0][0], outer[0][1], 0.0f);
    vertex(outer[1][0], outer[1][1], 0.0f);
    vertex(a[0], a[1], color[3]);
    vertex(outer[1][0], outer[1][1], 0.0f);
    vertex(b[0], b[1], color[3]);
  }
  immEnd();
  immUnbindProgram();
}

/** Lampway's agent avatar, "Spark" (scripts/dev/brand_art/logo_agent_spark.svg): a ring in the worker's colour around a small flame. Working alternates two flame
 * frames every 1.6 s (the second one ghosted), offline shows the flame out with a grey wisp. All coordinates are in a unit square (-0.5..0.5, y up),
 * mapped from the SVG's 64 px frame. */
void disc(float cx, float cy, float radius, float pixel, const float color[4])
{
  constexpr int count = 48;
  float points[count][2];
  for (int i = 0; i < count; i++) {
    const float angle = float(i) * 6.283185307f / count;
    points[i][0] = cx + radius * std::cos(angle);
    points[i][1] = cy + radius * std::sin(angle);
  }
  const float center[2] = {cx, cy};
  polygon(points, count, pixel, color, center);
}

void ring(float radius, float width, float pixel, const float color[4])
{
  constexpr int count = 48;
  const float outer = radius + width * 0.5f, inner = radius - width * 0.5f;
  for (int i = 0; i < count; i++) {
    const float a0 = float(i) * 6.283185307f / count, a1 = float(i + 1) * 6.283185307f / count;
    const float quad[4][2] = {{outer * std::cos(a0), outer * std::sin(a0)},
                              {outer * std::cos(a1), outer * std::sin(a1)},
                              {inner * std::cos(a1), inner * std::sin(a1)},
                              {inner * std::cos(a0), inner * std::sin(a0)}};
    const float mid[2] = {(quad[0][0] + quad[2][0]) * 0.5f, (quad[0][1] + quad[2][1]) * 0.5f};
    polygon(quad, 4, pixel, color, mid);
  }
}

/** The leaf-shaped flame: two cubic curves from the tip down to the base and back, `top` and `bottom` in the SVG's 64 px frame. */
void flame(float top, float bottom, float lean, float pixel, const float color[4])
{
  constexpr int steps = 14;
  constexpr int count = steps * 2;
  const float height = bottom - top;
  const float mid = top + height * 0.55f;
  /* Left curve control points: tip -> (-8, +9) -> (-7, -2 from the base) -> base; the right curve mirrors it. */
  const auto to_unit = [](float px, float py, float out[2]) {
    out[0] = (px - 32.0f) / 64.0f;
    out[1] = -(py - 32.0f) / 64.0f;
  };
  float points[count][2];
  for (int side = 0; side < 2; side++) {
    const float k = side == 0 ? -1.0f : 1.0f;
    const float c[4][2] = {{32.0f + lean, top},
                           {32.0f + lean + k * 7.0f, top + height * 0.33f},
                           {32.0f + k * 8.0f, mid + height * 0.05f},
                           {32.0f, bottom}};
    for (int i = 0; i < steps; i++) {
      const float t = float(i) / (steps - 1);
      const float u = 1.0f - t;
      const float px = u * u * u * c[0][0] + 3 * u * u * t * c[1][0] + 3 * u * t * t * c[2][0] + t * t * t * c[3][0];
      const float py = u * u * u * c[0][1] + 3 * u * u * t * c[1][1] + 3 * u * t * t * c[2][1] + t * t * t * c[3][1];
      /* Left side runs tip -> base, right side base -> tip, so the outline is one closed loop. */
      float *dst = points[side == 0 ? i : count - 1 - i];
      to_unit(px, py, dst);
    }
  }
  polygon(points, count, pixel, color);
}

/** The offline state: a grey wisp where the flame was. */
void wisp(float pixel, const float color[4])
{
  constexpr int steps = 10;
  const float width = 2.5f / 64.0f;
  float left[steps][2], right[steps][2];
  for (int i = 0; i < steps; i++) {
    const float t = float(i) / (steps - 1);
    const float y = 44.0f - 28.0f * t;
    const float x = 32.0f + 3.5f * std::sin(t * 6.2831853f);
    left[i][0] = (x - 32.0f) / 64.0f - width;
    left[i][1] = -(y - 32.0f) / 64.0f;
    right[i][0] = (x - 32.0f) / 64.0f + width;
    right[i][1] = left[i][1];
  }
  for (int i = 0; i + 1 < steps; i++) {
    const float quad[4][2] = {{left[i][0], left[i][1]}, {right[i][0], right[i][1]}, {right[i + 1][0], right[i + 1][1]}, {left[i + 1][0], left[i + 1][1]}};
    polygon(quad, 4, pixel, color);
  }
  disc(0.0f, -(46.0f - 32.0f) / 64.0f, 3.0f / 64.0f, pixel, color);
}

}  // namespace

static void draw_spark(const rctf &chip, const MixieCatStyle &style, const bool working, const bool offline, const float alpha)
{
  const float s = std::min(BLI_rctf_size_x(&chip), BLI_rctf_size_y(&chip)) - 2.0f;
  if (s < 6.0f || alpha <= 0.0f) {
    return;
  }
  const float a = std::clamp(alpha, 0.0f, 1.0f);
  const float px = 0.7f / s;
  const float smoke[4] = {0.086f, 0.098f, 0.133f, a};  /* #161922 */
  const float ring_color[4] = {offline ? 0.941f : style.ring[0], offline ? 0.463f : style.ring[1], offline ? 0.420f : style.ring[2], a};
  const float flame_color[4] = {0.929f, 0.725f, 0.267f, a};   /* #EDB944 */
  const float ghost_color[4] = {0.965f, 0.804f, 0.420f, a * 0.5f}; /* #F6CD6B at half strength */
  const float ash[4] = {0.663f, 0.651f, 0.616f, a};            /* #A9A69D */
  const bool second_frame = working && (int(BLI_time_now_seconds() / 0.8) & 1);

  GPU_matrix_push();
  GPU_matrix_translate_2f(BLI_rctf_cent_x(&chip), BLI_rctf_cent_y(&chip));
  GPU_matrix_scale_2f(s, s);
  disc(0.0f, 0.0f, 29.0f / 64.0f, px, smoke);
  ring(29.0f / 64.0f, 3.0f / 64.0f, px, ring_color);
  if (offline) {
    wisp(px, ash);
  }
  else if (working) {
    flame(second_frame ? 16.0f : 14.0f, second_frame ? 43.0f : 45.0f, 0.0f, px, flame_color);
    flame(second_frame ? 14.0f : 18.0f, second_frame ? 45.0f : 42.0f, 2.0f, px, ghost_color);
  }
  else {
    flame(16.0f, 43.0f, 0.0f, px, flame_color);
  }
  GPU_matrix_pop();
}

void agent_ui_draw_cat(
    const rctf &chip, const double /*now*/, const bool working, const int variation, const float alpha)
{
  draw_spark(chip, mixie_cat_style(variation), working, false, alpha);
}

void agent_ui_draw_pill_cat(const rctf *chip,
                            const MixieCatPose & /*pose*/,
                            const MixieCatActivity activity)
{
  g_last_cat_valid = false;
  if (chip == nullptr || BLI_rctf_size_x(chip) < 8.0f || BLI_rctf_size_y(chip) < 8.0f) {
    return;
  }
  g_last_cat_rect = {int(std::floor(chip->xmin)),
                     int(std::ceil(chip->xmax)),
                     int(std::floor(chip->ymin)),
                     int(std::ceil(chip->ymax))};
  g_last_cat_valid = true;
  g_last_activity = activity;
  draw_spark(*chip, mixie_cat_style(1), mixie_cat_is_working(activity), activity == MixieCatActivity::Offline, 1.0f);
}

bool agent_ui_pill_cat_last_rect(rcti *r_rect)
{
  if (!g_last_cat_valid || r_rect == nullptr) {
    return false;
  }
  *r_rect = g_last_cat_rect;
  return true;
}

void agent_ui_pill_cat_clear()
{
  g_last_cat_valid = false;
}

namespace {

void pill_cat_qa_targets(const wmWindow * /*win*/,
                         const ScrArea *area,
                         const ARegion *region,
                         std::vector<MixarQATarget> &r_targets)
{
  if (area == nullptr || region == nullptr) {
    return;
  }
  if (area->spacetype != SPACE_AGENT_BUBBLE || region->regiontype != RGN_TYPE_HEADER) {
    return;
  }
  bool has_body = false;
  for (ARegion &other : area->regionbase) {
    if (ELEM(other.regiontype, RGN_TYPE_WINDOW, RGN_TYPE_TOOLS)) {
      has_body = true;
      break;
    }
  }
  if (has_body) {
    return;
  }

  rcti cat;
  if (!agent_ui_pill_cat_last_rect(&cat)) {
    return;
  }
  rcti mapped = cat;
  mapped.xmin += region->winrct.xmin;
  mapped.xmax += region->winrct.xmin;
  mapped.ymin += region->winrct.ymin;
  mapped.ymax += region->winrct.ymin;
  rcti dummy;
  if (!BLI_rcti_isect(&mapped, &region->winrct, &dummy)) {
    mapped = region->winrct;
  }

  MixarQATarget t;
  t.surface = "pill_cat";
  t.text = "Lampway";
  t.value = mixie_cat_activity_name(g_last_activity);
  t.rect_win = mapped;
  r_targets.push_back(std::move(t));
}

}  // namespace

void agent_ui_pill_cat_qa_register()
{
  Mixar_qa_register_target_provider(SPACE_AGENT_BUBBLE, pill_cat_qa_targets);
}

}  // namespace blender
