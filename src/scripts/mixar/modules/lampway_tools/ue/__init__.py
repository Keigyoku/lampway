# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The UE Renderer (specs/ue_parity): a predictor of what Unreal Engine 5.8 shows, governed by one UE profile.

  profile       lampway.ue-profile/1: load, validate, hash, the exposure formula (pure)
  material_map  Principled -> UE Default Lit translation, deterministic (pure)
  material_group  the LW_UE_DefaultLit_v1 node group and the '<material> [UE]' preview (bpy, EEVEE)
  lights        Blender light -> UE light by the profile's k (pure)
  look          the UE Look mode: apply / status / revert with an exact receipt (bpy)
  ocio_view     the UE view's consumer side: a profile-named cube behind UE's log2 shaper, and the two traps refused
  export        ue_export: one canonical export path per asset type, with receipts (bpy)
  fbx_bytes     a minimal binary FBX reader: the timestamp-free content hash and the read-back facts (pure)
"""
