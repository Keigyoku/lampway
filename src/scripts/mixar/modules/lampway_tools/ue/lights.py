# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The light map: a Blender light as the UE light the profile's light-unit factor k makes of it (UE_RENDERER.md §3.2).

Blender sun strength S (W/m^2) gives a white Lambert radiance S/pi and a point power P (W) an intensity P/(4 pi) per steradian
(measured, SCR/light_probe.json); UE directional lights are in lux and point/spot lights in candela, so one factor k relates
them: lux = k * S, cd = k * P / (4 pi) (LGT-01). A Blender spot is not concentrated by its cone, a UE spot in candela is not
either, so spots go out in candela (LGT-02); outer cone = size / 2, inner = outer * (1 - blend). The light's own exposure
multiplies its power by 2^exposure; angles are rounded to 1e-4 degree (Blender stores them as float32 radians). Soft
falloff is off on the Blender side and the source radius goes out in centimetres (LGT-04).
Pure: the caller reads the light into a dict."""

import math


class LightMapError(ValueError):
    pass


def ue_light(light: dict, k: float) -> dict:
    """light: {type SUN|POINT|SPOT|AREA, energy, exposure?, radius_m?, angle_rad?, spot_size_rad?, spot_blend?, use_temperature?}."""
    kind = light["type"]
    if kind == "AREA":
        raise LightMapError("area lights are not mapped (LGT-03): convert to spot/point or exclude")
    if light.get("use_temperature"):
        raise LightMapError("a temperature-driven light is not mapped (LGT-15): set its colour instead")
    power = float(light["energy"]) * 2.0 ** float(light.get("exposure", 0.0))
    if kind == "SUN":
        return {"class": "DirectionalLight", "intensity": k * power, "unit": "lux",
                "source_angle_deg": round(math.degrees(float(light.get("angle_rad", 0.0))), 4)}
    if kind not in ("POINT", "SPOT"):
        raise LightMapError(f"light type {kind} is not mapped: sun, point and spot are")
    out = {"class": "PointLight" if kind == "POINT" else "SpotLight", "intensity": k * power / (4.0 * math.pi), "unit": "cd",
           "source_radius_cm": round(float(light.get("radius_m", 0.0)) * 100.0, 6), "use_inverse_squared_falloff": True}
    if kind == "SPOT":
        outer = math.degrees(float(light["spot_size_rad"])) / 2.0
        out.update(outer_cone_deg=round(outer, 4), inner_cone_deg=round(outer * (1.0 - float(light["spot_blend"])), 4))   # 1e-4 deg: Blender stores the cone as float32 radians
    return out
