# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The procedural library's data (specs/asset_library/asset_seed_procedural.md): 12 parametric TEMPLATES and the 55 presets that instantiate them.

A template names the feature that defines a material (hammered dimples, brushed grain, a woven cloth ...); ``procedural_library.emit`` builds every template from one
emitter with that feature switched on. Colours are sRGB looks (converted to linear when the script is written). ``look_ref`` is the nearest ambientCG CC0 material
for the captain to compare against, a reference only. Pure data: no bpy."""

TEMPLATES = {
    "metal_base": "Principled metal: tint, roughness curve, micro-noise, Mask-driven edge wear",
    "hammered": "metal_base + overlapping Voronoi dimples into Bump",
    "brushed": "metal_base + noise stretched along one axis",
    "scratched": "metal_base + thresholded wave lines, brighter in the wear",
    "pitted": "metal_base + inverted small Voronoi pits into Bump and Roughness",
    "rust_overlay": "metal_base + a noise mask of rust that drops Metallic",
    "patina_overlay": "metal_base + a verdigris bloom in the low noise",
    "damascus": "metal_base + wave bands in tone and roughness",
    "leather_grain": "Voronoi + noise grain, wear darkening, non-metal",
    "weave": "warp and weft wave bands, thread variation, sheen, non-metal",
    "embroidery": "a raised thread pattern over a cloth ground, two colours, non-metal",
    "cloth_fold": "long strands or slow folds: noise stretched along one axis, sheen, non-metal",
}
CATEGORIES = ("metal", "leather", "cloth", "embroidery")


def _metal(template, name, desc, color, rough, wear=0.25, bump=0.25, scale=3.0, look_ref=None, **feat):
    params = {"color": color, "rough": rough, "micro": feat.pop("micro", 0.3), "hammer": feat.pop("hammer", 0.0), "brushed": feat.pop("brushed", False),
              "patina": feat.pop("patina", 0.0), "scratch": feat.pop("scratch", 0.0), "pits": feat.pop("pits", 0.0), "rust": feat.pop("rust", 0.0),
              "bands": feat.pop("bands", 0.0), "wear": wear, "scale": scale, "bump": bump}
    assert not feat, feat
    return {"template": template, "category": "metal", "name": name, "description": desc, "params": params, "look_ref": look_ref}


def _leather(name, desc, color, rough, grain=0.5, wear=0.3, bump=0.4, scale=3.0, stitch=0.0):
    return {"template": "leather_grain", "category": "leather", "name": name, "description": desc,
            "params": {"color": color, "rough": rough, "grain": grain, "wear": wear, "scale": scale, "bump": bump, "stitch": stitch}}


def _cloth(template, name, desc, color, rough, weave=0.5, wear=0.2, bump=0.35, scale=3.0, strands=False):
    return {"template": template, "category": "cloth", "name": name, "description": desc,
            "params": {"color": color, "rough": rough, "weave": weave, "wear": wear, "scale": scale, "bump": bump, "strands": strands}}


def _embroidery(name, desc, ground, thread, pattern, density, rough=0.85, wear=0.15, bump=0.5, scale=3.0):
    return {"template": "embroidery", "category": "embroidery", "name": name, "description": desc,
            "params": {"color": ground, "thread": thread, "pattern": pattern, "density": density, "rough": rough, "wear": wear, "scale": scale, "bump": bump}}


PRESETS = {
    # bronze (6)
    "bronze_polished": _metal("metal_base", "Bronze, polished", "Warm polished bronze with a faint micro-grain.", (0.80, 0.50, 0.20), 0.22, wear=0.15, bump=0.15, micro=0.35, look_ref="Metal032"),
    "bronze_hammered": _metal("hammered", "Bronze, hammered", "Hand-hammered bronze: overlapping dimples over a warm base.", (0.74, 0.44, 0.18), 0.35, bump=0.6, hammer=1.0),
    "bronze_brushed": _metal("brushed", "Bronze, brushed", "Bronze with a fine directional grain.", (0.70, 0.45, 0.22), 0.30, brushed=True, bump=0.2),
    "bronze_cast_rough": _metal("pitted", "Bronze, cast rough", "Sand-cast bronze: pitted and matte.", (0.62, 0.40, 0.21), 0.55, pits=0.8, wear=0.35, bump=0.5),
    "bronze_patina_light": _metal("patina_overlay", "Bronze, light patina", "Bronze with a verdigris bloom in the recesses.", (0.72, 0.45, 0.22), 0.4, wear=0.3, bump=0.4, hammer=0.4, patina=0.55),
    "bronze_patina_heavy": _metal("patina_overlay", "Bronze, heavy patina", "Bronze mostly under a green crust.", (0.60, 0.40, 0.20), 0.55, wear=0.4, bump=0.45, patina=1.0),
    # brass (3)
    "brass_polished": _metal("metal_base", "Brass, polished", "Bright yellow brass.", (0.88, 0.74, 0.33), 0.18, wear=0.1, bump=0.1),
    "brass_brushed": _metal("brushed", "Brass, brushed", "Satin-brushed brass.", (0.80, 0.68, 0.31), 0.32, brushed=True, bump=0.2),
    "brass_antique": _metal("brushed", "Brass, antique", "Yellow-green antique brass, brushed and tarnished.", (0.71, 0.60, 0.25), 0.38, wear=0.45, bump=0.25, brushed=True, patina=0.12, scratch=0.2),
    # gold (5)
    "gold_polished": _metal("metal_base", "Gold, polished", "Bright polished gold.", (1.0, 0.76, 0.34), 0.16, wear=0.1, bump=0.1, micro=0.2),
    "gold_hammered": _metal("hammered", "Gold, hammered", "Beaten gold sheet.", (0.95, 0.70, 0.30), 0.28, bump=0.55, hammer=0.9),
    "gold_aged": _metal("scratched", "Gold, aged", "Gold dulled by handling: darker, rougher in the wear.", (0.85, 0.64, 0.28), 0.3, wear=0.55, micro=0.35, scratch=0.5),
    "gold_matte_leaf": _metal("metal_base", "Gold, matte leaf", "Gilded leaf: soft, matte, pale.", (0.92, 0.78, 0.45), 0.55, wear=0.2, bump=0.1, micro=0.5),
    "gold_rubbed_edges": _metal("scratched", "Gold, rubbed edges", "Gold rubbed bright and rough where it is handled.", (0.78, 0.58, 0.22), 0.42, wear=0.75, scratch=0.3),
    # copper (3)
    "copper_polished": _metal("metal_base", "Copper, polished", "Fresh polished copper.", (0.86, 0.45, 0.30), 0.2, wear=0.1, bump=0.1),
    "copper_oxidised": _metal("metal_base", "Copper, oxidised", "Copper darkened to a brown oxide.", (0.55, 0.30, 0.18), 0.5, wear=0.4, micro=0.45),
    "copper_verdigris": _metal("patina_overlay", "Copper, verdigris", "Copper under blue-green verdigris.", (0.70, 0.40, 0.27), 0.6, wear=0.45, patina=1.6),
    # iron (6)
    "iron_forged_dark": _metal("hammered", "Iron, forged dark", "Dark forged iron with a scaled surface.", (0.30, 0.30, 0.31), 0.55, wear=0.4, bump=0.5, micro=0.5, hammer=0.5, scratch=0.2),
    "iron_blackened": _metal("metal_base", "Iron, blackened", "Oil-blackened iron, near black, satin.", (0.16, 0.16, 0.17), 0.42, wear=0.3, micro=0.35),
    "iron_pitted": _metal("pitted", "Iron, pitted", "Old iron eaten by small pits.", (0.40, 0.39, 0.38), 0.62, pits=1.0, wear=0.35, bump=0.55),
    "iron_rust_light": _metal("rust_overlay", "Iron, light rust", "Iron with rust blooming in patches.", (0.42, 0.41, 0.40), 0.5, rust=0.5, wear=0.35),
    "iron_rust_heavy": _metal("rust_overlay", "Iron, heavy rust", "Iron mostly gone to rust.", (0.38, 0.36, 0.34), 0.7, rust=1.6, wear=0.4, bump=0.45),
    "iron_scaled": _metal("rust_overlay", "Iron, mill-scaled", "Hot-rolled iron with blue-grey scale and rust flecks.", (0.33, 0.35, 0.38), 0.6, rust=0.8, pits=0.4, wear=0.3),
    # steel (7)
    "steel_polished": _metal("metal_base", "Steel, polished", "Mirror-polished steel.", (0.80, 0.80, 0.81), 0.1, wear=0.05, bump=0.05, micro=0.15),
    "steel_brushed": _metal("brushed", "Steel, brushed", "Satin-brushed steel.", (0.70, 0.70, 0.71), 0.3, brushed=True, bump=0.2),
    "steel_hammered": _metal("hammered", "Steel, hammered", "Hand-beaten steel plate.", (0.60, 0.60, 0.61), 0.32, hammer=0.9, bump=0.5),
    "steel_scratched": _metal("scratched", "Steel, scratched", "Steel crossed by fine scratches.", (0.68, 0.68, 0.69), 0.22, scratch=0.8, wear=0.3),
    "steel_damascus": _metal("damascus", "Steel, damascus", "Pattern-welded steel: flowing light and dark bands.", (0.50, 0.50, 0.52), 0.35, bands=1.0, wear=0.2),
    "steel_blued": _metal("metal_base", "Steel, blued", "Heat-blued steel: deep blue-black.", (0.16, 0.20, 0.34), 0.3, wear=0.25),
    "steel_battle_worn": _metal("scratched", "Steel, battle-worn", "Grey steel scratched and dulled by use.", (0.62, 0.63, 0.65), 0.35, wear=0.6, bump=0.3, micro=0.35, scratch=1.0),
    # silver (3)
    "silver_polished": _metal("metal_base", "Silver, polished", "Bright polished silver.", (0.92, 0.92, 0.91), 0.14, wear=0.05, bump=0.05, micro=0.15),
    "silver_tarnished": _metal("metal_base", "Silver, tarnished", "Silver gone grey and dull.", (0.55, 0.54, 0.52), 0.42, wear=0.5, micro=0.4),
    "silver_engraved_matte": _metal("scratched", "Silver, engraved matte", "Matte silver with engraved lines.", (0.78, 0.78, 0.76), 0.5, scratch=0.6, wear=0.2),
    # other (7)
    "pewter": _metal("metal_base", "Pewter", "Soft grey pewter.", (0.58, 0.58, 0.57), 0.45, wear=0.3, micro=0.4),
    "tin": _metal("metal_base", "Tin", "Bright, slightly soft tin.", (0.84, 0.84, 0.83), 0.3, wear=0.15),
    "lead_dull": _metal("metal_base", "Lead, dull", "Dull blue-grey lead.", (0.42, 0.43, 0.46), 0.65, wear=0.3, micro=0.5),
    "gunmetal": _metal("metal_base", "Gunmetal", "Dark grey bronze-steel tone.", (0.26, 0.27, 0.29), 0.3, wear=0.2),
    "titanium_dark": _metal("brushed", "Titanium, dark", "Dark brushed titanium.", (0.36, 0.36, 0.39), 0.35, brushed=True),
    "electrum": _metal("metal_base", "Electrum", "Pale gold-silver alloy.", (0.93, 0.85, 0.58), 0.22, wear=0.15),
    "orichalcum_pale": _metal("hammered", "Orichalcum, pale", "A pale red-gold alloy, lightly beaten.", (0.90, 0.62, 0.40), 0.26, hammer=0.5, bump=0.35),
    # leather (5)
    "leather_oiled_brown": _leather("Leather, oiled brown", "Oiled brown leather with a soft sheen.", (0.30, 0.17, 0.08), 0.5, grain=0.6, wear=0.3, bump=0.4),
    "leather_charcoal_glove": _leather("Leather, charcoal glove", "Fine-grained charcoal glove leather.", (0.10, 0.10, 0.11), 0.55, grain=0.5, wear=0.25, bump=0.35),
    "leather_tan_worn": _leather("Leather, tan worn", "Tan leather worn pale at the edges.", (0.62, 0.42, 0.24), 0.62, grain=0.6, wear=0.6),
    "leather_black_matte": _leather("Leather, black matte", "Matte black leather.", (0.05, 0.05, 0.05), 0.8, grain=0.4, wear=0.2, bump=0.3),
    "leather_stitched_edge": _leather("Leather, stitched edge", "Brown leather with a running stitch.", (0.40, 0.22, 0.12), 0.6, grain=0.5, stitch=1.0),
    # cloth (6)
    "cloth_linen_black": _cloth("weave", "Linen, black", "Black plain-weave linen.", (0.07, 0.07, 0.08), 0.92, weave=0.5, wear=0.2, bump=0.35),
    "cloth_wool_red": _cloth("weave", "Wool, red", "Soft red wool, a loose weave.", (0.62, 0.10, 0.10), 0.96, weave=0.35, wear=0.25, bump=0.3, scale=1.6),
    "cloth_cloak_crimson_heavy": _cloth("weave", "Cloak cloth, heavy crimson", "Heavy crimson wool cloak cloth.", (0.50, 0.05, 0.07), 0.95, weave=0.8, wear=0.3, bump=0.5, scale=2.2),
    "cloth_woven_crimson": _cloth("weave", "Woven crimson", "A tight crimson weave with a sheen.", (0.72, 0.08, 0.16), 0.75, weave=0.6, wear=0.15, scale=5.0),
    "cloth_quilted_padding": _cloth("cloth_fold", "Quilted padding", "Off-white quilted linen padding.", (0.80, 0.76, 0.66), 0.9, weave=0.7, wear=0.3, bump=0.7, scale=1.2),
    "cloth_horsehair_plume_crimson": _cloth("cloth_fold", "Horsehair plume, crimson", "Crimson horsehair: long glossy strands.", (0.58, 0.04, 0.05), 0.55, weave=0.6, wear=0.1, bump=0.6, strands=True),
    # embroidery (4)
    "embroidery_gold_on_red": _embroidery("Embroidery, gold on red", "Gold thread embroidery on a red ground.", (0.55, 0.06, 0.07), (0.85, 0.65, 0.25), "satin", 0.55),
    "embroidery_greek_key_trim_gold": _embroidery("Greek key trim, gold", "A gold meander trim on a dark red band.", (0.35, 0.05, 0.06), (0.90, 0.72, 0.30), "key", 0.45),
    "embroidery_stitch_edge_thread": _embroidery("Stitch edge, thread", "A pale running stitch on dark cloth.", (0.12, 0.11, 0.10), (0.78, 0.72, 0.60), "edge", 0.25),
    "embroidery_braided_cord_gold": _embroidery("Braided cord, gold", "Twisted gold cord.", (0.40, 0.28, 0.10), (0.92, 0.74, 0.32), "braid", 0.8, rough=0.6),
}
