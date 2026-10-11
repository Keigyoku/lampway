# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic native-shaped controls; never actual UE/GPU acceptance."""
import enum
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('encoding_capture', ROOT / 'scripts/lampway/ue_cube_generator_capture.py')
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)


class Format(enum.Enum):
    RTF_RGBA8 = 1
    RTF_RGBA8_SRGB = 2
    RTF_RGBA16F = 3


class Source(enum.Enum):
    SCS_SCENE_COLOR_HDR = 1
    SCS_FINAL_COLOR_LDR = 2


class Settings:
    def __init__(self, **values):
        self.values = values

    def get_editor_property(self, key):
        return self.values[key]

    def set_editor_property(self, key, value):
        self.values[key] = value


def native_surface(tmp_path, target_patch=None):
    profile = json.loads((ROOT / 'src/scripts/mixar/modules/lampway_tools/ue/profiles/engine_defaults.json').read_text())
    request = dict(disposable_qa_project=True, profile=profile, name='synthetic_encoding',
                   shaper=dict(base=2, lin_side_slope=1, lin_side_offset=1, log_side_slope=1, log_side_offset=0),
                   shaper_source='synthetic control only', max_seconds=1, controls_only=True)
    root = tmp_path / 'Saved/LampwayCubeQA'
    root.mkdir(parents=True)
    (root / 'request.json').write_text(json.dumps(request))
    rgb = [[0, 0, 0]]
    dynamic = NS(set_vector_parameter_value=lambda key, value: rgb.__setitem__(0, [value.r, value.g, value.b]))
    material = Settings()
    mesh = NS(set_static_mesh=lambda value: None, set_material=lambda *args: None,
              create_dynamic_material_instance=lambda value: dynamic)
    plane = NS(get_component_by_class=lambda cls: mesh, set_actor_scale3d=lambda value: None)
    component = Settings(always_persist_rendering_state=False)
    captures, reads, targets, destroyed = [], [], [], []
    component.get_forward_vector = lambda: NS(x=0, y=0, z=-1)
    component.show_only_actor_components = lambda value: None
    component.capture_scene = lambda: captures.append((component.values['capture_source'], component.values['texture_target']))
    camera = NS(get_component_by_class=lambda cls: component)
    spawned = []

    def spawn(*args):
        actor = plane if not spawned else camera
        spawned.append(actor)
        return actor

    def create_target(world, width, height, fmt):
        target = Settings(render_target_format=fmt, srgb=fmt is Format.RTF_RGBA8_SRGB,
                          target_gamma=0.0, use_legacy_gamma=False, size_x=width, size_y=height)
        targets.append(target)
        if target_patch and fmt is Format.RTF_RGBA8_SRGB:
            target_patch(target)
        return target

    def read_raw(world, target, x, y, normalize):
        assert normalize is False
        reads.append(('raw', len(captures), target))
        if component.values['capture_source'] is Source.SCS_SCENE_COLOR_HDR:
            return NS(r=rgb[0][0], g=rgb[0][1], b=rgb[0][2])
        return NS(r=0.123, g=0.234, b=0.345)

    def read_color(world, target, x, y):
        reads.append(('color', len(captures), target))
        off = component.values['post_process_settings'].values['tone_curve_amount'] == 0
        value = 150 if off else 100
        return NS(r=value, g=value, b=value)

    ue = NS(Paths=NS(project_dir=lambda: str(tmp_path)),
        SystemLibrary=NS(get_engine_version=lambda: '5.8.2-56702186+++UE5',
                         get_console_variable_int_value=lambda key: profile['project']['cvars'][key]),
        EditorLevelLibrary=NS(get_editor_world=lambda: object(), spawn_actor_from_class=spawn,
                              destroy_actor=lambda actor: destroyed.append(actor)),
        Material=lambda: material, MaterialShadingModel=NS(MSM_UNLIT=object()),
        MaterialEditingLibrary=NS(create_material_expression=lambda *args: material,
            connect_material_property=lambda *args: True, recompile_material=lambda *args: None),
        MaterialExpressionVectorParameter=object(), MaterialProperty=NS(MP_EMISSIVE_COLOR=object()),
        StaticMeshActor=object(), StaticMeshComponent=object(), SceneCapture2D=object(), SceneCaptureComponent2D=object(),
        Rotator=lambda **kw: kw, Vector=lambda *args: args, Vector4=lambda x,y,z,w: NS(x=x,y=y,z=z,w=w),
        LinearColor=lambda r,g,b,a: NS(r=r,g=g,b=b,a=a), load_asset=lambda path: object(),
        SceneCapturePrimitiveRenderMode=NS(PRM_USE_SHOW_ONLY_LIST=object()),
        AutoExposureMethod=NS(AEM_MANUAL=False), PostProcessSettings=Settings,
        TextureRenderTargetFormat=Format, SceneCaptureSource=Source,
        RenderingLibrary=NS(create_render_target2d=create_target, read_render_target_raw_pixel=read_raw,
                            read_render_target_pixel=read_color))
    ue.synthetic_sample_rgb = rgb
    return ue, root, targets, captures, reads, destroyed


def test_display_contract_uses_explicit_srgb_target_and_same_capture_raw_readback(tmp_path):
    ue, root, targets, captures, reads, destroyed = native_surface(tmp_path)
    C.capture(ue)
    assert targets[0].values['render_target_format'] is Format.RTF_RGBA8_SRGB
    assert len(captures) == 12 and len(destroyed) == 2
    color_reads = [row for row in reads if row[0] == 'color']
    assert len(color_reads) == 8
    for _, serial, target in color_reads:
        assert ('raw', serial, target) in reads
    result = json.loads((root / 'synthetic_encoding.controls.json').read_text())
    assert result['status'] == 'completed' and result['normal_settings_restored']
    assert result['render_targets']['display']['srgb'] is True
    assert result['render_targets']['raw']['srgb'] is False
    assert result['controls'][1]['display_capture']['raw_pixel'] == [0.123, 0.234, 0.345]
    assert result['controls'][1]['disabled_display_capture']['raw_pixel'] == [0.123, 0.234, 0.345]
    assert not list(root.glob('*.cube*'))


@pytest.mark.parametrize('key,value', [('srgb',False),('srgb',1),('srgb','True'),
    ('target_gamma',float('nan')),('target_gamma',True),('target_gamma',2.2),('target_gamma',1e-6),
    ('use_legacy_gamma',True),('size_x',True),('size_y',4),
    ('render_target_format',Format.RTF_RGBA8)])
def test_unverified_or_mismatched_encoding_refuses_before_captures(tmp_path,key,value):
    def corrupt(target):
        target.values[key] = value
        target.set_editor_property = lambda *args: None
    ue, root, _, captures, _, destroyed = native_surface(tmp_path,corrupt)
    with pytest.raises(ValueError,match='render target'):
        C.capture(ue)
    assert not captures and len(destroyed)==2
    assert not list(root.glob('*.cube*'))


def test_identical_gray_still_refuses_even_if_other_controls_change(tmp_path):
    ue, root, _, _, _, destroyed = native_surface(tmp_path)
    old = ue.RenderingLibrary.read_render_target_pixel
    def unchanged_gray(*args):
        pixel = old(*args)
        return NS(r=42,g=42,b=42) if ue.synthetic_sample_rgb[0] == [0.18]*3 else pixel
    ue.RenderingLibrary.read_render_target_pixel = unchanged_gray
    with pytest.raises(ValueError,match='no curve difference'):
        C.capture(ue)
    result=json.loads((root/'synthetic_encoding.controls.json').read_text())
    assert result['status']=='refused' and result['normal_settings_restored']
    assert result['controls'][1]['display'] == result['controls'][1]['tone_curve_disabled']
    assert result['controls'][2]['display'] != result['controls'][2]['tone_curve_disabled']
    assert result['controls'][3]['display'] != result['controls'][3]['tone_curve_disabled']
    assert len(destroyed)==2 and not list(root.glob('*.cube*'))
