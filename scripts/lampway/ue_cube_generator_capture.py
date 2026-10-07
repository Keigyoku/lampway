# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""UE-only renderer sampling, never a CPU tonemapper. See the companion handoff.

QA request lives at <project>/Saved/LampwayCubeQA/request.json. No asset is saved.
RGBA8 final-color sampling intentionally records engine display quantization.
"""
import hashlib
import json
import math
from pathlib import Path
import re
import time

SHAPER_KEYS = ('base', 'lin_side_slope', 'lin_side_offset', 'log_side_slope', 'log_side_offset')


def grid(size, shaper):
    """Inverse input LogAffineTransform only; this is not a tone curve."""
    if not 2 <= size <= 64:
        raise ValueError('LUT size must be 2..64')
    if set(shaper) != set(SHAPER_KEYS) or not all(math.isfinite(float(v)) for v in shaper.values()):
        raise ValueError('exact finite five-field shaper required')
    if shaper['base'] != 2 or shaper['lin_side_slope'] <= 0 or shaper['log_side_slope'] <= 0:
        raise ValueError('a monotone log2 shaper is required')
    values = [(2 ** ((i / (size - 1) - shaper['log_side_offset']) / shaper['log_side_slope'])
               - shaper['lin_side_offset']) / shaper['lin_side_slope'] for i in range(size)]
    if not all(math.isfinite(v) and 0 <= v <= 65504 for v in values):
        raise ValueError('shaper samples exceed the nonnegative half-float input range')
    for blue in values:
        for green in values:
            for red in values:
                yield red, green, blue


def engine_identity(raw, expected):
    match = re.match(r'^(\d+\.\d+\.\d+)-(\d+)', raw)
    if not match or match[1] != expected['version'] or int(match[2]) != expected['changelist']:
        raise ValueError('actual UE version/changelist differs from profile')
    return {'version': match[1], 'changelist': int(match[2]), 'raw': raw}


def write_outputs(root, request, engine, rows, settings, controls):
    if len(rows) != request['profile']['project']['cvars']['r.LUT.Size'] ** 3:
        raise ValueError('incomplete engine capture; no cube published')
    if any(len(row) != 3 or not all(math.isfinite(v) and 0 <= v <= 1 for v in row) for row in rows):
        raise ValueError('invalid display pixels; no cube published')
    if len(controls) != 4 or any('tone_curve_disabled' not in row for row in controls):
        raise ValueError('raw-input and disabled-tone controls are required')
    for control in controls:
        if max(abs(a - b) for a, b in zip(control['input'], control['raw'])) > 0.005:
            raise ValueError('raw-input controls failed')
    if max(abs(a - b) for a, b in zip(controls[1]['display'], controls[1]['tone_curve_disabled'])) <= 1 / 255:
        raise ValueError('tone-curve controls failed')
    name = request['name']
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', name):
        raise ValueError('name must be a simple QA output basename')
    target = root / (name + '.cube')
    sidecar = root / (name + '.cube.json')
    if target.exists() or sidecar.exists():
        raise ValueError('QA output already exists; choose a new name')
    size = request['profile']['project']['cvars']['r.LUT.Size']
    data = ('# Actual UE FinalColorLDR capture; RGBA8 display precision\nLUT_3D_SIZE ' + str(size)
            + '\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n'
            + ''.join(' '.join(format(v, '.10g') for v in row) + '\n' for row in rows)).encode()
    meta = {'schema': 'lampway.ue-cube-meta/1', 'engine': engine,
            'tonemapper': request['profile']['tonemap'],
            'generator': {'name': 'UE QA SceneCapture sampler', 'version': '1',
                          'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
            'cube': {'file': target.name, 'sha256': hashlib.sha256(data).hexdigest(), 'size': size,
                     'domain_min': [0, 0, 0], 'domain_max': [1, 1, 1], 'order': 'red_fastest'},
            'shaper': request['shaper'], 'capture': {'source': 'SCS_FINAL_COLOR_LDR',
                     'readback': 'RenderingLibrary.read_render_target_pixel', 'format': 'RTF_RGBA8',
                     'precision_bits_per_channel': 8, 'output': 'engine sRGB display pixels',
                     'postprocess_readback': settings, 'controls': controls,
                     'shaper_source': request['shaper_source'],
                     'profile_sha256': hashlib.sha256(json.dumps(request['profile'], sort_keys=True).encode()).hexdigest()}}
    # Sidecar is the completion marker; incomplete output has no valid sidecar.
    with target.open('xb') as output:
        output.write(data)
    with sidecar.open('x', encoding='utf-8') as output:
        json.dump(meta, output, indent=2, sort_keys=True)
    return target, sidecar


def _postprocess_value(got, wanted, key):
    """Compare typed UE values; wrapper display strings may contain addresses."""
    mismatch = 'actual postprocess differs: ' + key
    if all(hasattr(wanted, axis) for axis in ('x', 'y', 'z', 'w')):
        if type(got) is not type(wanted):
            raise ValueError(mismatch)
        values = []
        for axis in ('x', 'y', 'z', 'w'):
            observed, expected = float(getattr(got, axis)), float(getattr(wanted, axis))
            if not (math.isfinite(observed) and math.isfinite(expected)) or abs(observed - expected) > 1e-5:
                raise ValueError(mismatch)
            values.append(observed)
        return values
    if isinstance(wanted, bool):
        if not isinstance(got, bool) or got != wanted:
            raise ValueError(mismatch)
        return got
    if isinstance(wanted, (int, float)):
        if not isinstance(got, (int, float)) or isinstance(got, bool):
            raise ValueError(mismatch)
        if not (math.isfinite(float(got)) and math.isfinite(float(wanted))) or abs(float(got) - float(wanted)) > 1e-5:
            raise ValueError(mismatch)
        return got
    # Native EnumBase values compare semantically. Find their typed class members
    # rather than serializing the display string or assuming an undocumented .value API.
    if type(got) is not type(wanted) or got != wanted:
        raise ValueError(mismatch)
    members = [name for name in dir(type(wanted)) if name.isupper()
               and getattr(type(wanted), name) == wanted]
    if not members:
        raise ValueError('unsupported postprocess value type: ' + key)
    return {'enum_type': type(got).__name__, 'members': sorted(members)}


def postprocess_readback(actual, fields):
    settings = {}
    for key, wanted in fields.items():
        if not actual.get_editor_property('override_' + key):
            raise ValueError('actual postprocess override missing: ' + key)
        settings[key] = _postprocess_value(actual.get_editor_property(key), wanted, key)
    return settings


def plan(request):
    size = request['profile']['project']['cvars']['r.LUT.Size']
    count = sum(1 for _ in grid(size, request['shaper']))
    seconds = float(request['max_seconds'])
    if not 1 <= seconds <= 3600:
        raise ValueError('max_seconds must be 1..3600')
    return {'mode': 'plan', 'size': size, 'cube_rows': count,
            'scene_captures': count + 12, 'control_captures': 12,
            'max_capture_seconds': seconds, 'writes': False,
            'runtime_estimate': 'unmeasured: calibrate with actual UE control capture; time limit refuses incomplete output',
            'precision_bits_per_channel': 8}


def capture(ue):
    root = (Path(ue.Paths.project_dir()).resolve() / 'Saved' / 'LampwayCubeQA')
    request = json.loads((root / 'request.json').read_text())
    if request.get('disposable_qa_project') is not True:
        raise ValueError('request must explicitly identify a disposable QA project')
    if not request.get('shaper_source'):
        raise ValueError('actual UE shaper source/settings provenance is required')
    plan(request)
    profile = request['profile']
    if profile['tonemap']['method'] != 'Filmic' or profile['tonemap']['grading'] != 'neutral':
        raise ValueError('this sampler supports Filmic with neutral grading only')
    if profile['project']['working_color_space'] != 'sRGB':
        raise ValueError('this sampler requires sRGB working color space')
    engine = engine_identity(ue.SystemLibrary.get_engine_version(), profile['engine'])
    points = list(grid(profile['project']['cvars']['r.LUT.Size'], request['shaper']))
    for name, value in profile['project']['cvars'].items():
        if ue.SystemLibrary.get_console_variable_int_value(name) != value:
            raise ValueError('actual project CVar differs from profile: ' + name)
    world = ue.EditorLevelLibrary.get_editor_world()
    actors = []
    try:
        material = ue.Material()
        material.set_editor_property('shading_model', ue.MaterialShadingModel.MSM_UNLIT)
        material.set_editor_property('two_sided', True)
        expr = ue.MaterialEditingLibrary.create_material_expression(material, ue.MaterialExpressionVectorParameter)
        expr.set_editor_property('parameter_name', 'LampwaySample')
        if not ue.MaterialEditingLibrary.connect_material_property(expr, '', ue.MaterialProperty.MP_EMISSIVE_COLOR):
            raise ValueError('UE emissive material connection failed')
        ue.MaterialEditingLibrary.recompile_material(material)
        plane = ue.EditorLevelLibrary.spawn_actor_from_class(ue.StaticMeshActor, ue.Vector(0, 0, 0))
        actors.append(plane)
        mesh = plane.get_component_by_class(ue.StaticMeshComponent)
        mesh.set_static_mesh(ue.load_asset('/Engine/BasicShapes/Plane.Plane'))
        plane.set_actor_scale3d(ue.Vector(10, 10, 10))
        mesh.set_material(0, material)
        dynamic = mesh.create_dynamic_material_instance(0)
        camera = ue.EditorLevelLibrary.spawn_actor_from_class(ue.SceneCapture2D, ue.Vector(0, 0, 100), ue.Rotator(-90, 0, 0))
        actors.append(camera)
        component = camera.get_component_by_class(ue.SceneCaptureComponent2D)
        component.set_editor_property('capture_every_frame', False)
        component.set_editor_property('capture_on_movement', False)
        component.set_editor_property('primitive_render_mode', ue.SceneCapturePrimitiveRenderMode.PRM_USE_SHOW_ONLY_LIST)
        component.show_only_actor_components(plane)
        pp = ue.PostProcessSettings()
        tm = profile['tonemap']
        fields = {'film_' + key: value for key, value in tm['film'].items()}
        fields.update({key: tm[key] for key in ('blue_correction', 'expand_gamut', 'tone_curve_amount', 'white_temp', 'white_tint')})
        fields.update({'auto_exposure_method': ue.AutoExposureMethod.AEM_MANUAL,
                       'auto_exposure_apply_physical_camera_exposure': False, 'auto_exposure_bias': 0.0,
                       'bloom_intensity': 0.0, 'vignette_intensity': 0.0, 'motion_blur_amount': 0.0,
                       'scene_fringe_intensity': 0.0})
        for band in ('', '_shadows', '_midtones', '_highlights'):
            for key in ('color_saturation', 'color_contrast', 'color_gamma', 'color_gain', 'color_offset'):
                value = 0 if key == 'color_offset' else 1
                fields[key + band] = ue.Vector4(value, value, value, value)
        fields['color_grading_intensity'] = 0.0
        for key, value in fields.items():
            pp.set_editor_property('override_' + key, True)
            pp.set_editor_property(key, value)
        component.set_editor_property('post_process_settings', pp)
        component.set_editor_property('post_process_blend_weight', 1.0)
        actual = component.get_editor_property('post_process_settings')
        settings = postprocess_readback(actual, fields)
        target = ue.RenderingLibrary.create_render_target2d(world, 8, 8, ue.TextureRenderTargetFormat.RTF_RGBA8)
        raw_target = ue.RenderingLibrary.create_render_target2d(world, 8, 8, ue.TextureRenderTargetFormat.RTF_RGBA16F)

        def sample(rgb, raw=False):
            dynamic.set_vector_parameter_value('LampwaySample', ue.LinearColor(*rgb, 1))
            component.set_editor_property('capture_source', ue.SceneCaptureSource.SCS_SCENE_COLOR_HDR if raw
                                          else ue.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
            component.set_editor_property('texture_target', raw_target if raw else target)
            component.capture_scene()
            if raw:
                pixel = ue.RenderingLibrary.read_render_target_raw_pixel(world, raw_target, 4, 4, False)
                return [pixel.r, pixel.g, pixel.b]
            pixel = ue.RenderingLibrary.read_render_target_pixel(world, target, 4, 4)
            return [pixel.r / 255.0, pixel.g / 255.0, pixel.b / 255.0]

        controls = []
        for rgb in ((0, 0, 0), (0.18, 0.18, 0.18), (1, 0, 0), (4, 4, 4)):
            raw = sample(rgb, True)
            if max(abs(a - b) for a, b in zip(raw, rgb)) > 0.005:
                raise ValueError('raw scene-color input control failed; no cube emitted')
            controls.append({'input': list(rgb), 'raw': raw, 'display': sample(rgb)})
        disabled = ue.PostProcessSettings()
        # Clone every applied field so the negative control changes only the native UE curve/gamut.
        for key, value in fields.items():
            disabled.set_editor_property('override_' + key, True)
            disabled.set_editor_property(key, value)
        disabled.set_editor_property('tone_curve_amount', 0.0)
        disabled.set_editor_property('expand_gamut', 0.0)
        component.set_editor_property('post_process_settings', disabled)
        for control in controls:
            control['tone_curve_disabled'] = sample(control['input'])
        component.set_editor_property('post_process_settings', pp)
        if max(abs(a - b) for a, b in zip(controls[1]['display'], controls[1]['tone_curve_disabled'])) <= 1 / 255:
            raise ValueError('native disabled-tone negative control showed no curve difference')
        started, rows = time.monotonic(), []
        max_seconds = float(request.get('max_seconds', 600))
        if not 1 <= max_seconds <= 3600:
            raise ValueError('max_seconds must be 1..3600')
        for index, rgb in enumerate(points):
            if time.monotonic() - started > max_seconds:
                raise ValueError('bounded QA capture timed out; no cube emitted')
            rows.append(sample(rgb))
            if index % 1024 == 0:
                print('LAMPWAY_UE_CUBE_PROGRESS ' + str(index) + '/' + str(len(points)))
        paths = write_outputs(root, request, engine, rows, settings, controls)
        print('LAMPWAY_UE_CUBE_COMPLETE ' + json.dumps({'cube': paths[0].name, 'sidecar': paths[1].name, 'rows': len(rows)}))
    finally:
        for actor in reversed(actors):
            ue.EditorLevelLibrary.destroy_actor(actor)


if __name__ == '__main__':
    import sys
    try:
        if len(sys.argv) > 1 and sys.argv[1] == '--plan':
            import argparse
            parser = argparse.ArgumentParser(description='Offline UE cube capture plan; touches nothing')
            parser.add_argument('--plan', type=Path, required=True)
            args = parser.parse_args()
            print(json.dumps(plan(json.loads(args.plan.read_text())), sort_keys=True))
        else:
            import unreal
            capture(unreal)
    except Exception as exc:
        print('error: UE cube capture refused: ' + str(exc))
        print('help[1]: inspect the QA request, actual UE profile, source shaper, and capability probe')
        raise
