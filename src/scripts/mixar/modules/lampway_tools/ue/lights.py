# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The light map: a Blender light as the UE light the profile's light-unit factor k makes of it (UE_RENDERER.md §3.2).

Blender sun strength S (W/m^2) gives a white Lambert radiance S/pi and a point power P (W) an intensity P/(4 pi) per steradian
(measured, SCR/light_probe.json); UE directional lights are in lux and point/spot lights in candela, so one factor k relates
them: lux = k * S, cd = k * P / (4 pi) (LGT-01). A Blender spot is not concentrated by its cone, a UE spot in candela is not
either, so spots go out in candela (LGT-02); the cones are the fit below, not size / 2 and outer * (1 - blend). The light's own exposure
multiplies its power by 2^exposure; angles are rounded to 1e-4 degree (Blender stores them as float32 radians). Soft
falloff is off on the Blender side and the source radius goes out in centimetres (LGT-04).
Pure: the caller reads the light into a dict."""

import math


# The spot falloff (LGT-02). EEVEE: smoothstep(t), t = (cos theta - cos o) / w, o = size / 2, w = (1 - cos o) * blend
# (eevee_light_lib.bsl.hh:89-96, eevee_light.cc:244-248). UE: saturate((cos theta - cos out) / (cos in - cos out))^2
# (DynamicLightingCommon.ush:58-66, SpotLightSceneProxy.cpp:18-23). No UE cone pair is a smoothstep; the least-squares pair in t
# is cos out = cos o + A w, cos in = cos o + (A + B) w: rms 0.024, worst 0.095 of full intensity. The old outer * (1 - blend)
# put UE's ramp at 1.83 times EEVEE's for a 45 deg, 0.15 blend spot (worst error 0.73; the live lights scene, lampway-finish-pr1).
SPOT_FIT_A, SPOT_FIT_B = -0.151914, 0.961667


def spot_cones(size_rad, blend):
    """UE (outer, inner) cone half-angles in degrees for an EEVEE spot of full size `size_rad` and blend `blend`."""
    half = float(size_rad) / 2.0
    co = math.cos(half)
    w = (1.0 - co) * float(blend)
    if w <= 0.0:
        return round(math.degrees(half), 4), round(math.degrees(half), 4)
    c_out = max(-1.0, min(1.0, co + SPOT_FIT_A * w))
    c_in = max(-1.0, min(1.0, co + (SPOT_FIT_A + SPOT_FIT_B) * w))
    return round(math.degrees(math.acos(c_out)), 4), round(math.degrees(math.acos(c_in)), 4)


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
        outer, inner = spot_cones(light["spot_size_rad"], light["spot_blend"])    # 1e-4 deg: Blender stores the cone as float32 radians
        out.update(outer_cone_deg=outer, inner_cone_deg=inner)
    return out
