# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The light map (specs/ue_parity/UE_RENDERER.md §3.2, T-LGT-01): Blender lights to the UE values the profile's k gives.
sun lux = k * S; point and spot candela = k * P / (4 pi); spot outer = size / 2, inner = outer * (1 - blend); source radius in cm;
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
    assert sp["class"] == "SpotLight" and sp["outer_cone_deg"] == 22.5 and sp["inner_cone_deg"] == 19.125 and round(sp["intensity"]) == 54351
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
