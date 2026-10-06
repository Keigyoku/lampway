/* SPDX-FileCopyrightText: 2026 Lampway contributors
 *
 * SPDX-License-Identifier: GPL-3.0-or-later */

/** \file
 * \ingroup spmixarassets
 *
 * The Asset Vault's drag and drop: its tiles drag, and the 3D viewport, a node tree and a material slot take the drop.
 */

#pragma once

namespace blender {
struct ARegion;
struct bContext;

/** The Vault's main region layout: the panels, then every tile button made draggable. */
void mixar_assets_main_region_layout(const bContext *C, ARegion *region);
void mixar_assets_operatortypes();
void mixar_assets_dropboxes();
}  // namespace blender
