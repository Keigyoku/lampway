# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure packing/input falsifiers. These fixtures are SYNTHETIC, never UE render proof."""
import importlib.util
import json
from pathlib import Path
import pytest

PATH = Path(__file__).resolve().parents[2] / 'scripts/lampway/ue_cube_generator_capture.py'
SPEC = importlib.util.spec_from_file_location('cube_capture', PATH)
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)
SHAPER = dict(base=2, lin_side_slope=1, lin_side_offset=1, log_side_slope=1, log_side_offset=0)


def test_input_grid_is_red_fastest_and_does_not_compute_an_output():
    assert list(C.grid(2, SHAPER))[:4] == [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)]


@pytest.mark.parametrize('shaper', [dict(SHAPER, base=10), dict(SHAPER, log_side_slope=0),
                                    dict(SHAPER, lin_side_offset=3), dict(SHAPER, base=float('nan'))])
def test_invalid_input_shaper_is_refused(shaper):
    with pytest.raises(ValueError):
        list(C.grid(2, shaper))


def test_engine_is_measured_and_exact_version_and_changelist_must_match():
    expected = dict(version='5.8.2', changelist=56702186)
    assert C.engine_identity('5.8.2-56702186+++UE5+Release-5.8', expected)['raw'].startswith('5.8.2-')
    for raw in ('5.8.2-1+++UE5', '5.8.1-56702186+++UE5', '5.8.2'):
        with pytest.raises(ValueError, match='actual UE'):
            C.engine_identity(raw, expected)


def test_incomplete_capture_never_publishes_a_sidecar(tmp_path):
    request = {'profile': {'project': {'cvars': {'r.LUT.Size': 2}}}}
    with pytest.raises(ValueError, match='incomplete'):
        C.write_outputs(tmp_path, request, {}, [[0, 0, 0]], {}, [])
    assert not list(tmp_path.iterdir())


def test_uncontrolled_capture_never_claims_a_genuine_cube(tmp_path):
    request = {'profile': {'project': {'cvars': {'r.LUT.Size': 2}}, 'tonemap': {}},
               'name': 'synthetic', 'shaper': SHAPER, 'shaper_source': 'synthetic test only'}
    with pytest.raises(ValueError, match='controls'):
        C.write_outputs(tmp_path, request, {}, [[0, 0, 0]] * 8, {}, [])
    assert not list(tmp_path.iterdir())


def test_synthetic_capture_packing_matches_existing_cube_validator(tmp_path):
    repo = PATH.parents[2]
    profile = json.loads((repo / 'src/scripts/mixar/modules/lampway_tools/ue/profiles/engine_defaults.json').read_text())
    profile['project']['cvars']['r.LUT.Size'] = 2
    request = dict(profile=profile, name='synthetic', shaper=SHAPER, shaper_source='synthetic test only')
    controls = [dict(input=[0.18] * 3, raw=[0.18] * 3, display=[0.4] * 3,
                     tone_curve_disabled=[0.5] * 3) for _ in range(4)]
    cube, sidecar = C.write_outputs(tmp_path, request, profile['engine'], list(C.grid(2, SHAPER)), {}, controls)
    spec = importlib.util.spec_from_file_location('existing_cube_validator',
            repo / 'src/scripts/mixar/modules/lampway_tools/ue/cube.py')
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    assert validator.validate(profile, cube, sidecar)['state'] == 'valid'
    meta = json.loads(sidecar.read_text())
    assert meta['capture']['precision_bits_per_channel'] == 8
    assert meta['capture']['controls'] == controls
    with pytest.raises(ValueError, match='already exists'):
        C.write_outputs(tmp_path, request, profile['engine'], list(C.grid(2, SHAPER)), {}, controls)


def test_plan_counts_actual_renderer_calls_without_claiming_runtime():
    request = dict(profile={'project': {'cvars': {'r.LUT.Size': 32}}}, shaper=SHAPER, max_seconds=600)
    result = C.plan(request)
    assert result['cube_rows'] == 32768 and result['scene_captures'] == 32780
    assert result['writes'] is False and 'unmeasured' in result['runtime_estimate']


class UEVector4:
    def __init__(self, x, y, z, w):
        self.x, self.y, self.z, self.w = x, y, z, w

    def __str__(self):
        return '<Struct Vector4 (0x%x) %r>' % (id(self), [self.x, self.y, self.z, self.w])


class UEPostProcess:
    def __init__(self, **values):
        self.values = values

    def get_editor_property(self, key):
        return True if key.startswith('override_') else self.values[key]


def test_real_ue_shaped_vector_readbacks_compare_values_not_wrapper_addresses():
    wanted = UEVector4(1, 1, 1, 1)
    got = UEVector4(1, 1, 1, 1)
    assert str(wanted) != str(got)
    settings = C.postprocess_readback(UEPostProcess(color_saturation=got), {'color_saturation': wanted})
    assert settings == {'color_saturation': [1.0, 1.0, 1.0, 1.0]}
    assert '0x' not in json.dumps(settings)


@pytest.mark.parametrize('components', [(1, 1, 1, 0.9), (float('nan'), 1, 1, 1),
                                        (1, float('inf'), 1, 1)])
def test_vector_mismatch_or_nonfinite_component_is_refused(components):
    with pytest.raises(ValueError, match='actual postprocess differs'):
        C.postprocess_readback(UEPostProcess(color_gain=UEVector4(*components)),
                              {'color_gain': UEVector4(1, 1, 1, 1)})


def test_vector_float_readback_tolerance_is_preserved():
    result = C.postprocess_readback(UEPostProcess(color_gain=UEVector4(1 + 1e-7, 1, 1, 1)),
                                   {'color_gain': UEVector4(1, 1, 1, 1)})
    assert result['color_gain'][0] == 1 + 1e-7


@pytest.mark.parametrize('got,wanted', [(float('nan'), 1), (1, float('nan')),
                                      (float('inf'), 1), (0.1, 0), ('1', 1), (1, True)])
def test_scalar_nonfinite_or_typed_mismatch_is_refused(got, wanted):
    with pytest.raises(ValueError, match='actual postprocess differs'):
        C.postprocess_readback(UEPostProcess(white_tint=got), {'white_tint': wanted})


class UEExposureMethod:
    def __init__(self, value):
        self.value = value

    def __eq__(self, other):
        return type(self) is type(other) and self.value == other.value

    def __str__(self):
        return '<Enum AutoExposureMethod (0x%x)>' % id(self)


UEExposureMethod.AEM_MANUAL = UEExposureMethod(2)
UEExposureMethod.AEM_HISTOGRAM = UEExposureMethod(1)


def test_enum_readback_uses_typed_value_equality_and_stable_member_receipt():
    result = C.postprocess_readback(UEPostProcess(auto_exposure_method=UEExposureMethod(2)),
                                   {'auto_exposure_method': UEExposureMethod.AEM_MANUAL})
    assert result == {'auto_exposure_method': {'enum_type': 'UEExposureMethod', 'members': ['AEM_MANUAL']}}
    assert '0x' not in json.dumps(result)
    with pytest.raises(ValueError, match='actual postprocess differs'):
        C.postprocess_readback(UEPostProcess(auto_exposure_method=UEExposureMethod.AEM_HISTOGRAM),
                              {'auto_exposure_method': UEExposureMethod.AEM_MANUAL})
    with pytest.raises(ValueError, match='actual postprocess differs'):
        C.postprocess_readback(UEPostProcess(auto_exposure_method=2),
                              {'auto_exposure_method': UEExposureMethod.AEM_MANUAL})


class UEPositionalRotator:
    """The actual documented UE Python order is roll, pitch, yaw."""
    def __init__(self, roll=0, pitch=0, yaw=0):
        self.roll, self.pitch, self.yaw = roll, pitch, yaw


def test_capture_rotation_uses_explicit_pitch_not_ue_positional_roll():
    from types import SimpleNamespace
    rotation = C.capture_rotation(SimpleNamespace(Rotator=UEPositionalRotator))
    assert (rotation.pitch, rotation.yaw, rotation.roll) == (-90, 0, 0)


@pytest.mark.parametrize('direction', [(1, 0, 0), (0, 0, 1), (0.1, 0, -1),
                                       (float('nan'), 0, -1), (0, float('inf'), -1)])
def test_actual_capture_component_wrong_or_nonfinite_forward_is_refused(direction):
    from types import SimpleNamespace
    component = SimpleNamespace(get_forward_vector=lambda: SimpleNamespace(x=direction[0], y=direction[1], z=direction[2]))
    with pytest.raises(ValueError, match='does not point down world Z'):
        C.capture_forward_readback(component)


def test_actual_component_forward_readback_records_finite_values_with_tolerance():
    from types import SimpleNamespace
    component = SimpleNamespace(get_forward_vector=lambda: SimpleNamespace(x=1e-7, y=0, z=-1))
    assert C.capture_forward_readback(component) == [1e-7, 0.0, -1.0]


def test_wrong_component_direction_prevents_capture_and_outputs_and_cleans_qa_actors(tmp_path):
    from types import SimpleNamespace
    profile = json.loads((PATH.parents[2] / 'src/scripts/mixar/modules/lampway_tools/ue/profiles/engine_defaults.json').read_text())
    root = tmp_path / 'Saved/LampwayCubeQA'
    root.mkdir(parents=True)
    request = dict(disposable_qa_project=True, profile=profile, name='synthetic', shaper=SHAPER,
                   shaper_source='synthetic test only', max_seconds=1)
    (root / 'request.json').write_text(json.dumps(request))
    destroyed, spawned, renders = [], [], []
    def unexpected_render(*args):
        renders.append(args)
        raise AssertionError('wrong camera must refuse before any render')
    material = SimpleNamespace(set_editor_property=lambda *args: None)
    dynamic = object()
    mesh = SimpleNamespace(set_static_mesh=lambda *args: None, set_material=lambda *args: None,
                           create_dynamic_material_instance=lambda *args: dynamic)
    plane = SimpleNamespace(get_component_by_class=lambda cls: mesh, set_actor_scale3d=lambda vector: None)
    # An actor can face down while its relative capture component faces sideways.
    component = SimpleNamespace(get_forward_vector=lambda: SimpleNamespace(x=1, y=0, z=0),
                                capture_scene=unexpected_render)
    camera = SimpleNamespace(get_component_by_class=lambda cls: component,
                             get_actor_forward_vector=lambda: SimpleNamespace(x=0, y=0, z=-1))
    def spawn(*args):
        actor = plane if not spawned else camera
        spawned.append(actor)
        return actor
    ue = SimpleNamespace(
        Paths=SimpleNamespace(project_dir=lambda: str(tmp_path)),
        SystemLibrary=SimpleNamespace(get_engine_version=lambda: '5.8.2-56702186+++UE5',
            get_console_variable_int_value=lambda key: profile['project']['cvars'][key]),
        EditorLevelLibrary=SimpleNamespace(get_editor_world=lambda: object(), spawn_actor_from_class=spawn,
                                           destroy_actor=lambda actor: destroyed.append(actor)),
        Material=lambda: material, MaterialShadingModel=SimpleNamespace(MSM_UNLIT=object()),
        MaterialEditingLibrary=SimpleNamespace(create_material_expression=lambda *args: material,
            connect_material_property=lambda *args: True, recompile_material=lambda *args: None),
        MaterialExpressionVectorParameter=object(), MaterialProperty=SimpleNamespace(MP_EMISSIVE_COLOR=object()),
        StaticMeshActor=object(), StaticMeshComponent=object(), SceneCapture2D=object(), SceneCaptureComponent2D=object(),
        Rotator=UEPositionalRotator, Vector=lambda *args: args, load_asset=lambda path: object(),
        RenderingLibrary=SimpleNamespace(create_render_target2d=unexpected_render))
    with pytest.raises(ValueError, match='does not point down world Z'):
        C.capture(ue)
    assert len(spawned) == 2 and destroyed == list(reversed(spawned)) and not renders
    assert not list(root.glob('*.cube')) and not list(root.glob('*.cube.json'))


def test_disabled_control_checks_applied_settings_and_restores_on_capture_error():
    from types import SimpleNamespace
    fields = dict(tone_curve_amount=1.0, expand_gamut=1.0, white_tint=0.0)
    class Settings:
        def __init__(self):
            self.values = {}
        def set_editor_property(self, key, value):
            self.values[key] = value
        def get_editor_property(self, key):
            return self.values[key]
    normal = Settings()
    for key, value in fields.items():
        normal.set_editor_property('override_' + key, True)
        normal.set_editor_property(key, value)
    current = [normal]
    component = SimpleNamespace(set_editor_property=lambda key, value: current.__setitem__(0, value),
                                get_editor_property=lambda key: current[0])
    def broken_sample(rgb):
        assert current[0].values['tone_curve_amount'] == 0.0
        assert current[0].values['expand_gamut'] == 0.0
        raise RuntimeError('synthetic readback failure')
    with pytest.raises(RuntimeError, match='synthetic readback'):
        C.disabled_tone_controls(SimpleNamespace(PostProcessSettings=Settings), component,
                                 normal, fields, [{'input': [0.18] * 3}], broken_sample)
    assert current[0] is normal


def test_disabled_control_rejects_unapplied_override_before_sampling():
    from types import SimpleNamespace
    normal = UEPostProcess(tone_curve_amount=1.0, expand_gamut=1.0)
    calls = []
    component = SimpleNamespace(set_editor_property=lambda *args: calls.append(args),
                                get_editor_property=lambda key: normal)
    class IgnoredSettings:
        def set_editor_property(self, *args):
            pass
    with pytest.raises(ValueError, match='actual postprocess differs: tone_curve_amount'):
        C.disabled_tone_controls(SimpleNamespace(PostProcessSettings=IgnoredSettings), component,
                                 normal, dict(tone_curve_amount=1.0, expand_gamut=1.0),
                                 [{'input': [0.18] * 3}], lambda rgb: pytest.fail('must check before sampling'))
    assert calls[-1] == ('post_process_settings', normal)


def test_disabled_control_reads_back_every_field_and_restores_normal_state():
    from types import SimpleNamespace
    fields = dict(tone_curve_amount=1.0, expand_gamut=1.0, white_tint=0.0)
    class Settings:
        def __init__(self):
            self.values = {}
        def set_editor_property(self, key, value):
            self.values[key] = value
        def get_editor_property(self, key):
            return self.values[key]
    normal = Settings()
    for key, value in fields.items():
        normal.set_editor_property('override_' + key, True)
        normal.set_editor_property(key, value)
    current = [normal]
    component = SimpleNamespace(set_editor_property=lambda key, value: current.__setitem__(0, value),
                                get_editor_property=lambda key: current[0])
    controls = [{'input': [0.18] * 3}]
    result = C.disabled_tone_controls(SimpleNamespace(PostProcessSettings=Settings), component,
                                     normal, fields, controls, lambda rgb: [0.5] * 3)
    assert result == dict(tone_curve_amount=0.0, expand_gamut=0.0, white_tint=0.0)
    assert controls[0]['tone_curve_disabled'] == [0.5] * 3
    assert current[0] is normal and normal.values['tone_curve_amount'] == 1.0


@pytest.mark.parametrize('difference', [0.0, 1 / 255])
def test_unchanged_or_one_code_value_tone_control_refuses_publication(tmp_path, difference):
    request = {'profile': {'project': {'cvars': {'r.LUT.Size': 2}}}}
    controls = [dict(input=[0.18] * 3, raw=[0.18] * 3, display=[0.0] * 3,
                     tone_curve_disabled=[difference] * 3) for _ in range(4)]
    with pytest.raises(ValueError, match='tone-curve controls failed'):
        C.write_outputs(tmp_path, request, {}, [[0, 0, 0]] * 8, {}, controls)
    assert not list(tmp_path.iterdir())


def test_disabled_control_refuses_incorrect_restored_readback():
    from types import SimpleNamespace
    class Settings:
        def __init__(self):
            self.values = {}
        def set_editor_property(self, key, value):
            self.values[key] = value
        def get_editor_property(self, key):
            return self.values[key]
    normal = UEPostProcess(tone_curve_amount=1.0, expand_gamut=1.0)
    current = [normal]
    def readback(key):
        return UEPostProcess(tone_curve_amount=0.0, expand_gamut=1.0) if current[0] is normal else current[0]
    component = SimpleNamespace(set_editor_property=lambda key, value: current.__setitem__(0, value),
                                get_editor_property=readback)
    with pytest.raises(ValueError, match='actual postprocess differs: tone_curve_amount'):
        C.disabled_tone_controls(SimpleNamespace(PostProcessSettings=Settings), component,
                                 normal, dict(tone_curve_amount=1.0, expand_gamut=1.0),
                                 [{'input': [0.18] * 3}], lambda rgb: [0.5] * 3)


@pytest.mark.parametrize('failure_mode', ['readback_error', 'unchanged_display', 'raw_error',
                                         'raw_nonfinite', 'controls_only'])
def test_capture_restores_native_settings_after_disabled_gpu_readback_error(tmp_path, capsys, failure_mode):
    """Exercise capture itself; the fake is orchestration proof, never GPU proof."""
    from types import SimpleNamespace as NS
    root = tmp_path / 'Saved/LampwayCubeQA'
    root.mkdir(parents=True)
    profile = json.loads((PATH.parents[2] / 'src/scripts/mixar/modules/lampway_tools/ue/profiles/engine_defaults.json').read_text())
    (root / 'request.json').write_text(json.dumps(dict(
        disposable_qa_project=True, profile=profile, name='synthetic', shaper=SHAPER,
        shaper_source='synthetic test only', max_seconds=1, controls_only=failure_mode == 'controls_only')))
    class Settings:
        def __init__(self):
            self.values = {}
        def set_editor_property(self, key, value):
            self.values[key] = value
        def get_editor_property(self, key):
            return self.values[key]
    class Component(Settings):
        def get_forward_vector(self):
            return NS(x=0, y=0, z=-1)
        def show_only_actor_components(self, actor):
            pass
        def capture_scene(self):
            render_calls.append(self.values['capture_source'])
    component, parameter, spawned, destroyed, render_calls = Component(), [], [], [], []
    dynamic = NS(set_vector_parameter_value=lambda key, value: parameter.__setitem__(slice(None), value))
    mesh = NS(set_static_mesh=lambda *args: None, set_material=lambda *args: None,
              create_dynamic_material_instance=lambda *args: dynamic)
    plane = NS(get_component_by_class=lambda cls: mesh, set_actor_scale3d=lambda *args: None)
    camera = NS(get_component_by_class=lambda cls: component)
    def spawn(*args):
        actor = plane if not spawned else camera
        spawned.append(actor)
        return actor
    def raw_pixel(*args):
        if failure_mode == 'raw_error' and parameter[0] == 0.18:
            raise RuntimeError('synthetic readback error at /private/qa-project')
        if failure_mode == 'raw_nonfinite' and parameter[0] == 0.18:
            return NS(r=float('nan'), g=0.18, b=0.18)
        return NS(r=parameter[0], g=parameter[1], b=parameter[2])
    def display_pixel(*args):
        if (failure_mode == 'readback_error'
                and component.values['post_process_settings'].values['tone_curve_amount'] == 0.0):
            raise RuntimeError('synthetic GPU readback error')
        value = 140 if (failure_mode == 'controls_only'
                       and component.values['post_process_settings'].values['tone_curve_amount'] == 0.0) else 100
        return NS(r=value, g=value, b=value)
    expression = NS(set_editor_property=lambda *args: None)
    ue = NS(
        Paths=NS(project_dir=lambda: str(tmp_path)),
        SystemLibrary=NS(get_engine_version=lambda: '5.8.2-56702186+++UE5',
            get_console_variable_int_value=lambda key: profile['project']['cvars'][key]),
        EditorLevelLibrary=NS(get_editor_world=lambda: object(), spawn_actor_from_class=spawn,
                              destroy_actor=lambda actor: destroyed.append(actor)),
        Material=Settings, MaterialShadingModel=NS(MSM_UNLIT=object()),
        MaterialEditingLibrary=NS(create_material_expression=lambda *args: expression,
            connect_material_property=lambda *args: True, recompile_material=lambda *args: None),
        MaterialExpressionVectorParameter=object(), MaterialProperty=NS(MP_EMISSIVE_COLOR=object()),
        StaticMeshActor=object(), StaticMeshComponent=object(), SceneCapture2D=object(), SceneCaptureComponent2D=object(),
        Rotator=UEPositionalRotator, Vector=lambda *args: args, Vector4=UEVector4,
        LinearColor=lambda *args: list(args), load_asset=lambda path: object(), PostProcessSettings=Settings,
        SceneCapturePrimitiveRenderMode=NS(PRM_USE_SHOW_ONLY_LIST=object()),
        AutoExposureMethod=UEExposureMethod,
        TextureRenderTargetFormat=NS(RTF_RGBA8=object(), RTF_RGBA16F=object()),
        SceneCaptureSource=NS(SCS_SCENE_COLOR_HDR=object(), SCS_FINAL_COLOR_LDR=object()),
        RenderingLibrary=NS(create_render_target2d=lambda *args: object(),
            read_render_target_raw_pixel=raw_pixel, read_render_target_pixel=display_pixel))
    error = RuntimeError if failure_mode in ('readback_error', 'raw_error') else ValueError
    reason = ('synthetic .*readback error' if error is RuntimeError else
              'invalid control pixel' if failure_mode == 'raw_nonfinite' else 'native disabled-tone negative control')
    if failure_mode == 'controls_only':
        C.capture(ue)
    else:
        with pytest.raises(error, match=reason):
            C.capture(ue)
    # Actor cleanup alone would hide that the control path never restored normal settings.
    assert component.values['post_process_settings'].values['tone_curve_amount'] == profile['tonemap']['tone_curve_amount']
    assert component.values['post_process_settings'].values['expand_gamut'] == profile['tonemap']['expand_gamut']
    assert destroyed == list(reversed(spawned))
    assert not list(root.glob('*.cube')) and not list(root.glob('*.cube.json'))
    receipt = json.loads((root / 'synthetic.controls.json').read_text())
    assert receipt['status'] == ('completed' if failure_mode == 'controls_only' else 'refused')
    assert '/private/qa-project' not in (root / 'synthetic.controls.json').read_text()
    if failure_mode == 'controls_only':
        assert receipt['stage'] == 'controls_complete' and receipt['controls_only'] is True
        assert len(render_calls) == 12
        assert 'exception_type' not in receipt
        assert len(receipt['controls']) == 4
        assert 'LAMPWAY_UE_CUBE_CONTROLS_COMPLETE' in capsys.readouterr().out
        return
    assert receipt['exception_type'] == error.__name__
    if failure_mode in ('raw_error', 'raw_nonfinite'):
        assert receipt['stage'] == 'raw_input' and receipt['control_index'] == 1
        assert receipt['controls'][0]['raw'] == [0, 0, 0]
        assert receipt['controls'][0]['display'] == [100 / 255] * 3
        assert receipt['controls'][1] == {'input': [0.18] * 3}
        assert 'disabled_postprocess_readback' not in receipt
        return
    assert receipt['normal_settings_restored'] is True
    assert len(receipt['controls']) == 4
    assert receipt['disabled_postprocess_readback']['tone_curve_amount'] == 0.0
    if failure_mode == 'readback_error':
        assert receipt['stage'] == 'disabled_display'
        assert all('tone_curve_disabled' not in row for row in receipt['controls'])
    else:
        assert receipt['stage'] == 'tone_control_guard'
    if failure_mode == 'unchanged_display':
        markers = [line for line in capsys.readouterr().out.splitlines()
                   if line.startswith('LAMPWAY_UE_CUBE_CONTROLS ')]
        assert len(markers) == 1, 'failed controls must retain measured pixels before refusing publication'
        diagnostic = json.loads(markers[0].split(' ', 1)[1])
        assert [row['input'] for row in diagnostic['controls']] == [
            [0, 0, 0], [0.18] * 3, [1, 0, 0], [4] * 3]
        for row in diagnostic['controls']:
            assert row['raw'] == row['input']
            assert row['display'] == row['tone_curve_disabled'] == [100 / 255] * 3
        assert diagnostic['postprocess_readback']['tone_curve_amount'] == profile['tonemap']['tone_curve_amount']
        assert diagnostic['disabled_postprocess_readback']['tone_curve_amount'] == 0.0
        assert diagnostic['disabled_postprocess_readback']['expand_gamut'] == 0.0


def test_control_receipt_is_private_exclusive_and_not_a_cube_marker(tmp_path):
    import stat
    with C.ControlEvidence(tmp_path, 'synthetic') as evidence:
        evidence.update('raw_input', controls=[{'input': [0, 0, 0]}])
    path = tmp_path / 'synthetic.controls.json'
    original = path.read_bytes()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        with C.ControlEvidence(tmp_path, 'synthetic'):
            pytest.fail('must not overwrite a prior diagnostic')
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]
    with pytest.raises(ValueError, match='simple QA output basename'):
        C.ControlEvidence(tmp_path, '../outside')


def test_controls_only_plan_keeps_profile_and_strict_boolean():
    request = {'profile': {'project': {'cvars': {'r.LUT.Size': 32}}},
               'shaper': SHAPER, 'max_seconds': 600, 'controls_only': True}
    result = C.plan(request)
    assert result['size'] == 32 and result['cube_rows'] == 0 and result['scene_captures'] == 12
    assert request['profile']['project']['cvars']['r.LUT.Size'] == 32
    request['controls_only'] = 'true'
    with pytest.raises(ValueError, match='controls_only must be a boolean'):
        C.plan(request)


def test_control_diagnostic_write_failure_preserves_original_callback_error(tmp_path, monkeypatch, capsys):
    with pytest.raises(RuntimeError, match='original callback error'):
        with C.ControlEvidence(tmp_path, 'synthetic') as evidence:
            def fail_write(**kwargs):
                raise OSError('synthetic filesystem write failure')
            monkeypatch.setattr(evidence, 'update', fail_write)
            raise RuntimeError('original callback error')
    assert 'LAMPWAY_UE_CUBE_DIAGNOSTIC_WRITE_FAILED' in capsys.readouterr().out


@pytest.mark.parametrize('suffix', ['.cube', '.cube.json', '.controls.pending'])
def test_existing_qa_output_refuses_before_reserving_diagnostic(tmp_path, suffix):
    prior = tmp_path / ('synthetic' + suffix)
    prior.write_text('original QA output')
    with pytest.raises(ValueError, match='QA output already exists'):
        with C.ControlEvidence(tmp_path, 'synthetic'):
            pytest.fail('existing output must refuse before scene work')
    assert prior.read_text() == 'original QA output'
    assert list(tmp_path.iterdir()) == [prior]


@pytest.mark.parametrize('field', ['input', 'raw', 'display', 'tone_curve_disabled'])
def test_nonfinite_control_cannot_publish_a_sidecar(tmp_path, field):
    profile = json.loads((PATH.parents[2] / 'src/scripts/mixar/modules/lampway_tools/ue/profiles/engine_defaults.json').read_text())
    profile['project']['cvars']['r.LUT.Size'] = 2
    request = dict(profile=profile, name='synthetic', shaper=SHAPER, shaper_source='synthetic test only')
    controls = [dict(input=[0.18] * 3, raw=[0.18] * 3, display=[0.4] * 3,
                     tone_curve_disabled=[0.5] * 3) for _ in range(4)]
    controls[0][field][0] = float('nan')
    with pytest.raises(ValueError, match='invalid control pixel'):
        C.write_outputs(tmp_path, request, profile['engine'], [[0.2] * 3] * 8, {}, controls)
    assert not list(tmp_path.iterdir())
