# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The UE Renderer (specs/ue_parity): a predictor of what Unreal Engine 5.8 shows, governed by one UE profile.

  profile       lampway.ue-profile/1: load, validate, hash, the exposure formula (pure)
  material_map  Principled -> UE Default Lit translation, deterministic (pure)
  material_group  the LW_UE_DefaultLit_v1 node group and the '<material> [UE]' preview (bpy, EEVEE)
"""
