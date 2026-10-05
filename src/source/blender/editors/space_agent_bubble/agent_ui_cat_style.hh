/* SPDX-FileCopyrightText: 2026 Lampway contributors
 *
 * SPDX-License-Identifier: GPL-3.0-or-later */

#pragma once

#include <array>

namespace blender {

/** The agent avatar's ring colour per worker (docs/brand/BRAND.md 5.1, "worker colours"); the name is always shown beside it so colour is never the
 * only cue. Index 1 (Dusk) is the main agent's own colour. */
struct MixieCatStyle {
  const char *name;
  std::array<float, 4> ring;
};

constexpr std::array<MixieCatStyle, 6> MIXIE_CAT_STYLES = {{
    {"Flame", {0.929f, 0.725f, 0.267f, 1.0f}},   /* #EDB944 */
    {"Dusk", {0.620f, 0.627f, 0.969f, 1.0f}},    /* #9EA0F7 */
    {"Mint", {0.357f, 0.769f, 0.561f, 1.0f}},    /* #5BC48F */
    {"Coral", {0.941f, 0.463f, 0.420f, 1.0f}},   /* #F0766B */
    {"Sky", {0.435f, 0.765f, 0.910f, 1.0f}},     /* #6FC3E8 */
    {"Orchid", {0.835f, 0.561f, 0.878f, 1.0f}},  /* #D58FE0 */
}};

inline const MixieCatStyle &mixie_cat_style(const int ordinal)
{
  return MIXIE_CAT_STYLES[size_t(ordinal < 0 ? 0 : ordinal) % MIXIE_CAT_STYLES.size()];
}

}  // namespace blender
