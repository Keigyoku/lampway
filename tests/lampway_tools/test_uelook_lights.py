# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The light map (specs/ue_parity/UE_RENDERER.md §3.2, T-LGT-01): Blender lights to the UE values the profile's k gives.
sun lux = k * S; point and spot candela = k * P / (4 pi); spot cones the least-squares fit of UE's squared ramp to EEVEE's smoothstep (test below); source radius in cm;
area lights and temperature-driven lights are refused (LGT-03, LGT-15). Pure, so it runs here."""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.ue import lights as LM  # noqa: E402


def test_lgt01_units_and_cones():
    sun = LM.ue_light({"type": "SUN", "energy": 1.0, "angle_rad": math.radians(0.526)}, k=683)
    assert sun["class"] == "DirectionalLight" and sun["intensity"] == 683.0 and sun["unit"] == "lux"
    assert sun["source_angle_deg"] == 0.526
    pt = LM.ue_light({"type": "POINT", "energy": 1000.0, "radius_m": 0.1}, k=683)
    assert pt["class"] == "PointLight" and pt["unit"] == "cd" and round(pt["intensity"]) == 54351 and pt["source_radius_cm"] == 10.0
    assert pt["use_inverse_squared_falloff"] is True
    sp = LM.ue_light({"type": "SPOT", "energy": 1000.0, "radius_m": 0.0, "spot_size_rad": math.radians(45.0), "spot_blend": 0.15}, k=683)
    assert sp["class"] == "SpotLight" and round(sp["intensity"]) == 54351
    assert sp["outer_cone_deg"] == 22.7583 and sp["inner_cone_deg"] == 21.0726
    assert LM.ue_light({"type": "POINT", "energy": 1000.0, "radius_m": 0.0}, k=1)["intensity"] == pytest.approx(1000 / (4 * math.pi))


def test_light_exposure_multiplies_the_power():
    a = LM.ue_light({"type": "POINT", "energy": 10.0, "radius_m": 0.0, "exposure": 1.0}, k=683)
    b = LM.ue_light({"type": "POINT", "energy": 20.0, "radius_m": 0.0}, k=683)
    assert a["intensity"] == pytest.approx(b["intensity"])


@pytest.mark.parametrize("light, message", [
    ({"type": "AREA", "energy": 10.0}, "area lights are not mapped (LGT-03): convert to spot/point or exclude"),
    ({"type": "POINT", "energy": 10.0, "radius_m": 0.0, "use_temperature": True}, "a temperature-driven light is not mapped (LGT-15): set its colour instead"),
])
def test_refused_lights_name_their_fix(light, message):
    with pytest.raises(LM.LightMapError, match=message.replace("(", r"\(").replace(")", r"\)")):
        LM.ue_light(light, k=683)



def eevee_spot(theta_deg, size_deg, blend):
    """EEVEE's spotmask on the axis plane (eevee_light_lib.bsl.hh:89-96; eevee_light.cc:244-248): smoothstep in cosine."""
    co = math.cos(math.radians(size_deg / 2))
    x = (math.cos(math.radians(theta_deg)) - co) / max(1e-8, (1 - co) * blend)
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def ue_spot(theta_deg, outer_deg, inner_deg):
    """UE's SpotAttenuation (DynamicLightingCommon.ush:58-66; SpotLightSceneProxy.cpp:18-23): a squared ramp in cosine."""
    co, ci = math.cos(math.radians(outer_deg)), math.cos(math.radians(inner_deg))
    x = (math.cos(math.radians(theta_deg)) - co) / max(1e-12, ci - co)
    return min(1.0, max(0.0, x)) ** 2


@pytest.mark.parametrize("size_deg, blend", [(45.0, 0.15), (45.0, 0.5), (90.0, 0.15), (30.0, 1.0), (120.0, 0.3)])
def test_lgt02_the_spot_cones_follow_eevees_falloff(size_deg, blend):
    """The live lights scene (lampway-finish-pr1): with inner = outer * (1 - blend) UE's ramp was 1.83 times EEVEE's, and the
    probes at 20.4 and 21.7 deg read about 40 % dark. No UE cone pair reproduces a smoothstep; the fitted pair stays within the
    fit's own bound (rms 0.025, max 0.095 of full intensity) at every angle."""
    sp = LM.ue_light({"type": "SPOT", "energy": 1.0, "radius_m": 0.0, "spot_size_rad": math.radians(size_deg), "spot_blend": blend}, k=1)
    lo = 0.0
    errs = [ue_spot(th, sp["outer_cone_deg"], sp["inner_cone_deg"]) - eevee_spot(th, size_deg, blend)
            for th in [lo + i * (size_deg / 2 * 1.2) / 4000 for i in range(4001)]]
    band = [e for e in errs if e != 0.0]
    assert max(abs(e) for e in errs) <= 0.096
    assert band and math.sqrt(sum(e * e for e in band) / len(band)) <= 0.06


def test_a_spot_without_blend_has_coincident_cones():
    sp = LM.ue_light({"type": "SPOT", "energy": 1.0, "radius_m": 0.0, "spot_size_rad": math.radians(60.0), "spot_blend": 0.0}, k=1)
    assert sp["outer_cone_deg"] == sp["inner_cone_deg"] == 30.0
