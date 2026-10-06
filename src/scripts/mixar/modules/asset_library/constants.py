# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Asset Vault editor's fixed values (specs/asset_library/asset_ui_editor.md sections 5-6)."""

SPACE = "MIXAR_ASSETS"                 # the dockable editor the Vault lives in (the Mixar stub space, renamed in the UI)
PAGE = 96                              # tiles per page
DEBOUNCE_S = 0.25                      # typing waits this long; Enter sends at once
THUMB_LRU = 512                        # preview handles kept
TILE_MIN, TILE_MAX, TILE_DEFAULT = 64, 256, 128
FACETS = ("piece_type", "material_role", "kind", "source", "license", "rating", "studio", "model", "motion_type", "camera_template", "verdict")
KINDS = ("mesh", "image", "material", "texture_set", "map", "hdri", "video", "animation", "rig")
SORTS = ("score", "created", "name", "rating", "faces", "duration")
