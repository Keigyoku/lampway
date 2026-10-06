/* SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
 * SPDX-License-Identifier: GPL-3.0-or-later */

#pragma once
#include "BLI_sys_types.h"
#include "UI_mixar_types.hh"
#include "UI_mixar_text.hh"
#include "UI_mixar_density.hh"

namespace blender::ui::mixar_tokens {
/* [[maybe_unused]]: the full palette is defined up front as the reference
 * palette; individual tokens land as each widget phase uses them. */
inline constexpr uchar MX_BG[4] = {22, 25, 34, 255};
inline constexpr uchar MX_BG_SUNKEN[4] = {17, 19, 26, 255};
inline constexpr uchar MX_GRAY_800[4] = {17, 19, 26, 255};
inline constexpr uchar MX_GRAY_700[4] = {30, 34, 45, 255};
inline constexpr uchar MX_BORDER[4] = {43, 48, 61, 255};
inline constexpr uchar MX_BORDER_STRONG[4] = {59, 66, 82, 255};
inline constexpr uchar MX_ACCENT[4] = {237, 185, 68, 255};
inline constexpr uchar MX_TOGGLE_ON[4] = {58, 47, 23, 255};
inline constexpr uchar MX_WARNING[4] = {237, 185, 68, 255};
inline constexpr uchar MX_DANGER[4] = {240, 118, 107, 255};
inline constexpr uchar MX_INK[4] = {247, 244, 238, 255};
inline constexpr uchar MX_FG_1[4] = {236, 232, 223, 255};
inline constexpr uchar MX_FG_2[4] = {207, 203, 194, 255};
inline constexpr uchar MX_FG_3[4] = {169, 166, 157, 255};
inline constexpr uchar MX_FG_4[4] = {125, 122, 115, 255};

/* Generate gradient is stored in ThemeUI; see MixarThemeSlot::GradientStart. */

/* Corner radii in px @ 1x DPI (scaled by UI_SCALE_FAC at draw time). */
inline constexpr float MX_R_SM = 4.0f;     /* --mx-r-sm: inputs / selects */
inline constexpr float MX_R_MD = 8.0f;     /* --mx-r-md: grouped cards    */
inline constexpr float MX_R_PILL = 999.0f; /* fully rounded; clamped to h/2 */

struct Palette {
  float canvas[4], panel[4], input[4], control[4], selected[4];
  float text[4], strong[4], secondary[4], border[4], focus[4];
  float primary[4], danger[4], warning[4], action[4];
};
inline constexpr Palette zen = {
    {14.0f / 255.0f, 16.0f / 255.0f, 22.0f / 255.0f, 255.0f / 255.0f},
    {22.0f / 255.0f, 25.0f / 255.0f, 34.0f / 255.0f, 255.0f / 255.0f},
    {17.0f / 255.0f, 19.0f / 255.0f, 26.0f / 255.0f, 255.0f / 255.0f},
    {30.0f / 255.0f, 34.0f / 255.0f, 45.0f / 255.0f, 255.0f / 255.0f},
    {58.0f / 255.0f, 47.0f / 255.0f, 23.0f / 255.0f, 255.0f / 255.0f},
    {236.0f / 255.0f, 232.0f / 255.0f, 223.0f / 255.0f, 255.0f / 255.0f},
    {247.0f / 255.0f, 244.0f / 255.0f, 238.0f / 255.0f, 255.0f / 255.0f},
    {169.0f / 255.0f, 166.0f / 255.0f, 157.0f / 255.0f, 255.0f / 255.0f},
    {43.0f / 255.0f, 48.0f / 255.0f, 61.0f / 255.0f, 255.0f / 255.0f},
    {237.0f / 255.0f, 185.0f / 255.0f, 68.0f / 255.0f, 255.0f / 255.0f},
    {90.0f / 255.0f, 71.0f / 255.0f, 32.0f / 255.0f, 255.0f / 255.0f},
    {240.0f / 255.0f, 118.0f / 255.0f, 107.0f / 255.0f, 255.0f / 255.0f},
    {237.0f / 255.0f, 185.0f / 255.0f, 68.0f / 255.0f, 255.0f / 255.0f},
    {22.0f / 255.0f, 25.0f / 255.0f, 34.0f / 255.0f, 255.0f / 255.0f}};
/** Live palette. `zen` stays the measured artboard; painters read this. */
const Palette &mixar_zen();
/** Default density, unscaled. Island chips keep these aliases. Chrome
 * hosts use Compact (`mixar_chrome::density`) without rebinding these. */
inline constexpr MixarDensityMetrics default_density =
    mixar_density_unscaled(MixarDensity::Default);
inline constexpr MixarDensityMetrics compact_density =
    mixar_density_unscaled(MixarDensity::Compact);
inline constexpr float control_height = default_density.control_height;
inline constexpr float radius = default_density.radius;
/* Compatibility aliases. New explicit text uses MixarTextRole. */
inline constexpr float font = mixar_text_role_size(MixarTextRole::Body);
inline constexpr float caption_font = mixar_text_role_size(MixarTextRole::Caption);
inline constexpr float prompt_font = mixar_text_role_size(MixarTextRole::Prompt);
inline constexpr float padding = default_density.padding;
inline constexpr float gap = default_density.gap;
inline constexpr float icon = default_density.icon;
inline constexpr float icon_gap = default_density.icon_gap;
}  // namespace blender::ui::mixar_tokens
