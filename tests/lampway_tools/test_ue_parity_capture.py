# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The UE half of ue_parity (scripts/lampway/ue_parity_capture.py): pure frame, light, texture and request controls.
SYNTHETIC: none of these is UE render proof; the live capture is a separate receipt."""
import importlib.util
import json
import math
import struct
import zlib
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('ue_parity_capture', ROOT / 'scripts/lampway/ue_parity_capture.py')
U = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(U)

from mixar.modules.lampway_tools.ue import lights as LM            # noqa: E402
from mixar.modules.lampway_tools.ue import parity_metrics as PM    # noqa: E402
from mixar.modules.lampway_tools.ue import parity_scene as PS      # noqa: E402

PROFILE = json.loads((ROOT / 'src/scripts/mixar/modules/lampway_tools/ue/profiles/engine_defaults.json').read_text())


def parity_profile(**changes):
    p = json.loads(json.dumps(PROFILE))
    p['source'] = 'disposable UE QA live readback (parity)'
    p['project']['cvars'].update(U.PARITY_CVARS)
    p['post'].update(bloom=0, vignette=0, ssao=0)
    for key, value in changes.items():
        node = p
        *path, last = key.split('.')
        for part in path:
            node = node[part]
        node[last] = value
    return p


def ue_pixel(cam, p_cm, size):
    """UE's own pinhole for a SceneCapture2D (horizontal FOV, square target): forward and right from the keyword rotator."""
    rot = U.rotator_from_forward(U.camera_forward(cam))
    pitch, yaw = math.radians(rot['pitch']), math.radians(rot['yaw'])
    f = np.array([math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)])
    r = np.array([-math.sin(yaw), math.cos(yaw), 0.0])                 # UE GetRightVector for roll 0
    u = np.cross(f, r)                                                   # left-handed: up = forward x right
    d = np.asarray(p_cm, float) - np.asarray(U.to_ue_cm(cam['location']), float)
    s = (size / 2) / math.tan(math.radians(cam['ue_hfov_deg']) / 2)
    return [size / 2 + s * (d @ r) / (d @ f), size / 2 - s * (d @ u) / (d @ f)]


@pytest.mark.parametrize('view', list(PS.VIEWS))
def test_ue_cameras_frame_every_chart_patch_on_the_lampway_pixel(view):
    """T-HAR-02 both ways: the UE capture camera this script builds sees each patch centre where the Lampway half's camera does."""
    desc = PS.describe('chart', 768, (view,))
    cam = desc['cameras'][view]
    assert cam['ue_hfov_deg'] == pytest.approx(39.597752, abs=1e-6)
    for p in desc['objects']['patches']:
        want = PM.project_blender([PS._to_cam(cam, p['location'])], PS.LENS_MM, PS.SENSOR_MM, 768, 768)[0]
        got = ue_pixel(cam, U.to_ue_cm(p['location']), 768)
        assert got == pytest.approx(list(want), abs=1e-6), (view, p['location'])


def test_an_unmirrored_frame_flips_the_image(monkeypatch):
    """The plant: mapping metres to centimetres without the Y mirror (camera and points alike) mirrors the picture left to
    right, so the off-centre patches leave their pixels (the framing check is not vacuous)."""
    desc = PS.describe('chart', 768, ('front',))
    cam = desc['cameras']['front']
    monkeypatch.setattr(U, 'to_ue_cm', lambda p: tuple(100.0 * float(v) for v in p))
    monkeypatch.setattr(U, 'to_ue_dir', lambda d: tuple(float(v) / math.sqrt(sum(float(c) ** 2 for c in d)) for v in d))
    p = desc['objects']['patches'][0]
    want = PM.project_blender([PS._to_cam(cam, p['location'])], PS.LENS_MM, PS.SENSOR_MM, 768, 768)[0]
    got = ue_pixel(cam, U.to_ue_cm(p['location']), 768)
    assert abs(got[0] - want[0]) > 50 and got[0] == pytest.approx(768 - want[0], abs=1e-6)


def test_light_directions_and_units_go_out_through_lampways_one_light_map():
    desc = PS.describe('lights', 768, ('front',))
    out = U.ue_lights(desc, 683.0)
    assert [o['mapped'] for o in out] == [LM.ue_light(light, 683.0) for light in desc['lights']]
    sun, point, spot = out
    assert sun['mapped']['class'] == 'DirectionalLight' and sun['mapped']['intensity'] == pytest.approx(683.0)
    assert point['mapped']['intensity'] == pytest.approx(683.0 * 100.0 / (4 * math.pi))
    assert sun['forward'] == pytest.approx(U.to_ue_dir(desc['lights'][0]['direction']))
    assert sun['forward'][1] < 0 < desc['lights'][0]['direction'][1]          # mirrored
    assert spot['location_cm'] == pytest.approx((80.0, 150.0, 80.0))
    assert U.ue_lights(desc, 1.0)[0]['mapped']['intensity'] == pytest.approx(1.0)


@pytest.mark.parametrize('forward', [(1, 0, 0), (0, -1, 0), (0.2, -1, -0.4), (0, 0.35, -1)])
def test_keyword_rotator_turns_ue_x_onto_the_forward_vector(forward):
    f = U.to_ue_dir(forward)
    r = U.rotator_from_forward(f)
    p, y = math.radians(r['pitch']), math.radians(r['yaw'])
    assert (math.cos(p) * math.cos(y), math.cos(p) * math.sin(y), math.sin(p)) == pytest.approx(f, abs=1e-12)
    assert r['roll'] == 0.0


def _png_rgb(data):
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    w, h = struct.unpack('>II', data[16:24])
    idat = data[data.index(b'IDAT') + 4:data.index(b'IEND') - 8]
    raw = zlib.decompress(idat)
    rows = [raw[i * (1 + 3 * w) + 1:(i + 1) * (1 + 3 * w)] for i in range(h)]
    return np.array([list(r) for r in rows], dtype=float).reshape(h, w, 3)


def test_the_normal_map_is_the_lampway_dome_formula_in_directx_green():
    img = _png_rgb(U.dome_dx_png(64, 3)) / 255.0 * 2 - 1     # PNG rows top-down
    v, u = (np.mgrid[0:64, 0:64] + 0.5) / 64
    v = v[::-1]                                              # parity_scene._dome_dx is in Blender rows (bottom-up)
    nx, ny = np.zeros((64, 64)), np.zeros((64, 64))
    for i in range(3):
        x, y = (u - (i + 0.5) / 3) * 3 * 2.2, (v - 0.5) * 3 * 2.2
        inside = x * x + y * y < 1
        nx, ny = np.where(inside, x * 0.7, nx), np.where(inside, y * 0.7, ny)
    ln = np.sqrt(nx * nx + ny * ny + 1)
    want = np.dstack([nx / ln, -ny / ln, 1 / ln])
    assert np.abs(img - want).max() < 2.5 / 255 * 2
    flipped = want.copy()
    flipped[..., 1] *= -1
    assert np.abs(img - flipped).max() > 0.3                 # a +Y (OpenGL) green would not pass


def test_parity_post_carries_the_profiles_manual_exposure_and_turns_every_effect_off():
    post = U.parity_post(parity_profile())
    assert post['camera_iso'] == 100 and post['camera_shutter_speed'] == 60 and post['depth_of_field_fstop'] == 4
    assert post['auto_exposure_bias'] == 1.0 and post['auto_exposure_apply_physical_camera_exposure'] is True
    assert post['bloom_intensity'] == post['vignette_intensity'] == post['ambient_occlusion_intensity'] == 0.0


@pytest.mark.parametrize('change,why', [
    ({'source': 'engine-defaults'}, 'engine defaults'),
    ({'exposure.method': 'auto'}, 'manual exposure'),
    ({'post.bloom': 0.675}, 'bloom'),
    ({'post.local_exposure': {'highlight': 0.8, 'shadow': 1.0, 'detail': 1.0}}, 'local exposure'),
    ({'project.cvars.r.ReflectionMethod': 2}, 'r.ReflectionMethod'),
])
def test_a_request_the_parity_rules_forbid_is_refused(change, why):
    profile = parity_profile()
    for key, value in change.items():
        if key.startswith('project.cvars.'):
            profile['project']['cvars'][key[len('project.cvars.'):]] = value
        else:
            profile = parity_profile(**{key: value}) if '.' in key else {**profile, key: value}
    request = {'disposable_qa_project': True, 'name': 'chart_front', 'profile': profile, 'scene': PS.describe('chart', 64, ('front',))}
    with pytest.raises(ValueError, match=why):
        U.check_request(request)


@pytest.mark.parametrize('bad', [{'disposable_qa_project': False}, {'name': '../out'}, {'views': ['grazing']},
                                 {'scene': {'schema': 'other'}}])
def test_a_request_outside_a_disposable_qa_run_is_refused(bad):
    request = {'disposable_qa_project': True, 'name': 'chart_front', 'profile': parity_profile(),
               'scene': PS.describe('chart', 64, ('front',)), **bad}
    with pytest.raises((ValueError, KeyError)):
        U.check_request(request)


def test_a_valid_parity_request_names_its_views():
    request = {'disposable_qa_project': True, 'name': 'chart_front', 'profile': parity_profile(),
               'scene': PS.describe('chart', 64, ('front', 'grazing'))}
    assert U.check_request(request) == ['front', 'grazing']


@pytest.mark.parametrize('scene', list(PS.SCENES))
def test_settle_points_lie_in_the_regions_the_comparison_reads(scene):
    """The first furnace run settled on three background pixels, which a missing sky light also leaves black."""
    desc = PS.describe(scene, 768, ('front',))
    pts = U.settle_points(desc, 'front')
    assert 1 <= len(pts) <= 12
    regions = desc['regions']['front']
    rects = [r['rect'] if isinstance(r, dict) else r for c, rs in regions.items() if c != 'LGT' for r in rs]
    probes = {tuple(p) for p in regions.get('LGT', [])}
    for x, y in pts:
        assert (x, y) in probes or any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in rects), (scene, x, y)


def test_a_description_without_regions_cannot_settle():
    desc = PS.describe('chart', 64, ('front',))
    desc['regions']['front'] = {}
    with pytest.raises(ValueError, match='no region'):
        U.settle_points(desc, 'front')


def _ue_up(rot):
    """UE's roll about X as measured on UE 5.8.2 (uv probe 2): roll +90 takes the Plane's +Z normal to +Y."""
    r = math.radians(rot['roll'])
    assert rot['pitch'] == 0.0 and rot['yaw'] == 0.0
    return (0.0, math.sin(r), math.cos(r))


@pytest.mark.parametrize('scene', ['normals', 'lights'])
def test_every_parity_plane_faces_its_camera_in_ue(scene):
    """The first live normals run read 0 % sign agreement: the plane faced away (roll -90) and its map read from the back."""
    desc = PS.describe(scene, 64, ('front',))
    up = _ue_up(U.plane_rotation(desc['objects']['plane']['rotation_euler']))
    cam = desc['cameras']['front']
    to_cam = np.subtract(U.to_ue_cm(cam['location']), U.to_ue_cm(desc['objects']['plane']['location']))
    assert np.dot(up, to_cam) > 0, (scene, up)
