# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""The UE half of lampway_ue_parity: build a standard parity scene from the SAME JSON description the Lampway half wrote
(`scene.json`, schema lampway.ue-parity-scene/1, built by mixar.modules.lampway_tools.ue.parity_scene.describe) in a disposable
UE QA project, capture it linear (SCS_SCENE_COLOR_HDR into a float target) per view, and export ue_<view>.exr for the Lampway
half's comparison (`ue_parity ue_captures=<dir>`). Run inside the UE editor:

    UnrealEditor-Cmd <QA.uproject> -RenderOffscreen ... -ExecutePythonScript=<this file>

Request: <project>/Saved/LampwayParityQA/request.json = {disposable_qa_project: true, name, profile (lampway.ue-profile/1,
the parity profile), scene (the scene.json object), views}. Outputs, all under <project>/Saved/LampwayParityQA/<name>/:
ue_<view>.exr and capture.json (engine, cvars, the capture settings and post-process overrides read back, every light's
forward vector, settle agreement, file hashes). Nothing is saved to the project's content; the editor quits without saving.

Contract: the off-tree ue_parity.md §6 and ue_editor_leg.md `capture` job (EXR not .hdr, keyword rotators, three settle
captures, post-process overrides from the parity profile, the level's own lights hidden). Deviation, stated: it runs as a
Lampway QA script in a disposable project, not through Titan's editor_runner on the Titan project.

Units and frames: the description is lampway.body/1 (metres, +Z up, right-handed); UE is centimetres, +Z up, left-handed:
(x, y, z) m -> (100 x, -100 y, 100 z) cm, the mirror the FBX convention uses. Lights go out through Lampway's own light map
(src/.../ue/lights.py, loaded by path: one formula), so lux = k S and cd = k P / (4 pi); emission goes out multiplied by k,
which the Lampway half divides back out (parity.py)."""

import hashlib
import importlib.util
import json
import math
import re
import struct
import zlib
from pathlib import Path

SCHEMA = 'lampway.ue-parity-capture/1'
SCENE_SCHEMA = 'lampway.ue-parity-scene/1'
SETTLE = 3
SKY_TICKS = 120                     # engine ticks after the build: the sky light's recapture and its mip filtering run on ticks
PARITY_CVARS = {'r.DynamicGlobalIlluminationMethod': 0, 'r.ReflectionMethod': 0}
LIGHT_CLASSES = ('Light', 'SkyLight', 'SkyAtmosphere', 'ExponentialHeightFog', 'PostProcessVolume', 'VolumetricCloud')
_LIGHTS_PY = Path(__file__).resolve().parents[2] / 'src/scripts/mixar/modules/lampway_tools/ue/lights.py'


def light_map():
    spec = importlib.util.spec_from_file_location('lampway_ue_lights', _LIGHTS_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def to_ue_cm(p):
    """A lampway.body/1 point (metres) as a UE location (centimetres, Y mirrored)."""
    x, y, z = (float(v) for v in p)
    return (100.0 * x, -100.0 * y, 100.0 * z)


def to_ue_dir(d):
    """A lampway.body/1 direction as a unit UE direction (Y mirrored)."""
    x, y, z = float(d[0]), -float(d[1]), float(d[2])
    n = math.sqrt(x * x + y * y + z * z)
    if not n or not math.isfinite(n):
        raise ValueError('a direction must be finite and nonzero')
    return (x / n, y / n, z / n)


def camera_forward(cam):
    """The Blender camera of parity_scene._camera (rotation [pi/2, 0, yaw]) looks along (-sin yaw, cos yaw, 0)."""
    rx, ry, yaw = cam['rotation_euler']
    if abs(rx - math.pi / 2) > 1e-9 or abs(ry) > 1e-9:
        raise ValueError('only the parity cameras (rotation [pi/2, 0, yaw]) are supported')
    return to_ue_dir((-math.sin(yaw), math.cos(yaw), 0.0))


def rotator_from_forward(forward):
    """Pitch and yaw (degrees, keyword use) that turn UE +X onto `forward`; roll 0."""
    x, y, z = forward
    return {'pitch': math.degrees(math.asin(max(-1.0, min(1.0, z)))), 'yaw': math.degrees(math.atan2(y, x)), 'roll': 0.0}


def plane_rotation(rotation_euler):
    """A parity plane (Blender default plane, normal +Z, turned by rotation_euler about X only) as UE keyword rotation for
    /Engine/BasicShapes/Plane (normal +Z): the normal turns with it, mirrored."""
    rx, ry, rz = (float(v) for v in rotation_euler)
    if abs(ry) > 1e-9 or abs(rz) > 1e-9:
        raise ValueError('only planes turned about X are supported')
    # Blender R_x(a) takes +Z to (0, -sin a, cos a); mirrored, (0, sin a, cos a) in UE, which UE reaches with roll +a: measured
    # on UE 5.8.2 (lampway-finish-pr1 uv probe 2: roll +90 puts the Plane's normal at +Y and an image upright and unmirrored
    # before a camera at +Y; roll -90 faces it away and turns the image upside down).
    return {'pitch': 0.0, 'yaw': 0.0, 'roll': math.degrees(rx)}


def ue_lights(desc, k):
    lm = light_map()
    out = []
    for light in desc['lights']:
        mapped = lm.ue_light(light, k)
        row = {'mapped': mapped}
        if light['type'] in ('SUN', 'SPOT'):
            row['forward'] = to_ue_dir(light['direction'])
        if light['type'] in ('POINT', 'SPOT'):
            row['location_cm'] = to_ue_cm(light['location'])
        out.append(row)
    return out


def dome_dx_png(n=256, bumps=3):
    """parity_scene._dome_dx as an 8-bit RGB PNG (same formula; DirectX green), written without numpy (UE's Python has none)."""
    rows = []
    for j in range(n):
        v = (j + 0.5) / n
        row = bytearray([0])
        for i in range(n):
            u = (i + 0.5) / n
            nx = ny = 0.0
            for b in range(bumps):
                x, y = (u - (b + 0.5) / bumps) * bumps * 2.2, (v - 0.5) * bumps * 2.2
                if x * x + y * y < 1:
                    nx, ny = x * 0.7, y * 0.7
            ln = math.sqrt(nx * nx + ny * ny + 1.0)
            for c in (nx / ln * 0.5 + 0.5, -ny / ln * 0.5 + 0.5, 1.0 / ln * 0.5 + 0.5):
                row.append(max(0, min(255, round(c * 255))))
        rows.append(bytes(row))
    # Blender pixel rows run bottom-up; a PNG's run top-down
    raw = b''.join(reversed(rows))

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', n, n, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def settle_points(desc, view, most=12):
    """Pixels inside the regions the comparison measures (rect centres, LGT probe points): the settle captures are checked
    where the answer is read, never on background a missing sky or material would also leave black."""
    pts = []
    for cls, items in desc['regions'][view].items():
        for item in items:
            if cls == 'LGT':
                pts.append((int(item[0]), int(item[1])))
            else:
                x0, y0, x1, y1 = item['rect'] if isinstance(item, dict) else item
                pts.append(((x0 + x1) // 2, (y0 + y1) // 2))
    if not pts:
        raise ValueError(f'{view}: the scene description measures no region to settle on')
    step = max(1, len(pts) // most)
    return pts[::step][:most]


def parity_post(profile):
    """The parity profile's post-process overrides for the capture component (exposure manual; every effect off)."""
    ex, post = profile['exposure'], profile['post']
    if ex['method'] != 'manual':
        raise ValueError('a parity capture needs manual exposure (the parity profile)')
    if post['bloom'] or post['vignette'] or post['ssao'] or any(v != 1 for v in post['local_exposure'].values()):
        raise ValueError('a parity capture needs bloom, vignette, SSAO off and local exposure identity (the parity profile)')
    return {'auto_exposure_apply_physical_camera_exposure': bool(ex['apply_physical_camera']),
            'auto_exposure_bias': float(ex['bias']), 'camera_iso': float(ex['iso']), 'camera_shutter_speed': float(ex['shutter']),
            'depth_of_field_fstop': float(ex['fstop']), 'bloom_intensity': 0.0, 'vignette_intensity': 0.0,
            'ambient_occlusion_intensity': 0.0, 'motion_blur_amount': 0.0, 'lens_flare_intensity': 0.0,
            'local_exposure_highlight_contrast_scale': 1.0, 'local_exposure_shadow_contrast_scale': 1.0,
            'local_exposure_detail_strength': 1.0}


def check_request(request):
    if request.get('disposable_qa_project') is not True:
        raise ValueError('request must explicitly identify a disposable QA project')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', str(request.get('name', ''))):
        raise ValueError('name must be a simple QA output basename')
    desc, profile = request['scene'], request['profile']
    if desc.get('schema') != SCENE_SCHEMA or desc.get('frame') != 'lampway.body/1':
        raise ValueError('scene must be the Lampway half\'s scene.json (lampway.ue-parity-scene/1, lampway.body/1)')
    if profile.get('schema') != 'lampway.ue-profile/1' or profile.get('source') == 'engine-defaults':
        raise ValueError('profile must be a live lampway.ue-profile/1 parity profile, not engine defaults')
    views = request.get('views') or list(desc['cameras'])
    if not views or any(v not in desc['cameras'] for v in views):
        raise ValueError('views must name cameras of the scene description')
    for name, value in PARITY_CVARS.items():
        if profile['project']['cvars'][name] != value:
            raise ValueError(f'the parity profile must set {name} {value}')
    parity_post(profile)
    return views


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _vec(ue, v):
    return ue.Vector(*v)


def _readback(component, overrides):
    pp = component.get_editor_property('post_process_settings')
    out = {}
    for key, wanted in overrides.items():
        if not pp.get_editor_property('override_' + key):
            raise ValueError('actual post-process override missing: ' + key)
        got = pp.get_editor_property(key)
        if type(wanted) is bool:
            if bool(got) is not wanted:
                raise ValueError('actual post-process value differs: ' + key)
        elif not math.isfinite(float(got)) or abs(float(got) - wanted) > 1e-4 * max(1.0, abs(wanted)):
            raise ValueError('actual post-process value differs: ' + key)
        out[key] = got if type(wanted) is bool else float(got)
    return out


def capture(ue):
    """The whole job at once (tests); in the editor run_ticking drives the same steps one tick apart."""
    for _ in capture_steps(ue):
        pass


def capture_steps(ue):
    root = Path(ue.Paths.project_dir()).resolve() / 'Saved' / 'LampwayParityQA'
    request = json.loads((root / 'request.json').read_text())
    views = check_request(request)
    out = root / request['name']
    out.mkdir(exist_ok=False)
    desc, profile = request['scene'], request['profile']
    k = float(profile['light_units']['k'])
    raw = ue.SystemLibrary.get_engine_version()
    m = re.match(r'^(\d+\.\d+\.\d+)-(\d+)', raw)
    if not m or m[1] != profile['engine']['version'] or int(m[2]) != profile['engine']['changelist']:
        raise ValueError('actual UE version/changelist differs from the profile')
    # a fresh, never-saved blank level: the editor's startup map (UE's OpenWorld template) carries its own sun, sky and fog
    ue.get_editor_subsystem(ue.LevelEditorSubsystem).new_level('/Temp/LampwayParityQA_' + request['name'], False)
    for _ in range(5):
        yield 'new_level'
    world = ue.EditorLevelLibrary.get_editor_world()
    for name, value in PARITY_CVARS.items():
        ue.SystemLibrary.execute_console_command(world, f'{name} {value}')
    for name, value in profile['project']['cvars'].items():
        if ue.SystemLibrary.get_console_variable_int_value(name) != value:
            raise ValueError('actual project CVar differs from the parity profile: ' + name)
    receipt = {'schema': SCHEMA, 'name': request['name'], 'scene': desc['scene'], 'engine': raw, 'k': k,
               'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'cvars': {n: ue.SystemLibrary.get_console_variable_int_value(n) for n in profile['project']['cvars']},
               'deviation': 'disposable QA project through UnrealEditor-Cmd -ExecutePythonScript, not Titan editor_runner on the Titan project',
               # SCS_SCENE_COLOR_HDR: "SceneColor (HDR) in RGB, Inv Opacity in A"; the Lampway half converts (parity.to_coverage)
               'alpha': 'inverse_opacity', 'capture_source': 'SCS_SCENE_COLOR_HDR',
               'views': {}}
    made, hidden = [], []
    try:
        for actor in ue.EditorLevelLibrary.get_all_level_actors():
            if any(isinstance(actor, getattr(ue, c)) for c in LIGHT_CLASSES if hasattr(ue, c)):
                hidden.append((actor, actor.is_hidden_ed(), actor.get_editor_property('hidden')))
                actor.set_is_temporarily_hidden_in_editor(True)
                actor.set_actor_hidden_in_game(True)
        receipt['level_actors_hidden'] = len(hidden)
        primitives = _build(ue, world, desc, k, made, out, receipt)
        for i in range(SKY_TICKS):
            if i == SKY_TICKS // 2 and receipt.get('sky'):
                for light in made:                           # recapture once the dome's material is resident
                    if isinstance(light, ue.SkyLight):
                        light.get_component_by_class(ue.SkyLightComponent).recapture_sky()
            yield 'settle_build'
        size = int(desc['size'])
        target = ue.RenderingLibrary.create_render_target2d(world, size, size, ue.TextureRenderTargetFormat.RTF_RGBA32F)
        if target.get_editor_property('render_target_format') != ue.TextureRenderTargetFormat.RTF_RGBA32F:
            raise ValueError('actual capture target is not RGBA32F')
        overrides = parity_post(profile)
        for view in views:
            cam = desc['cameras'][view]
            forward = camera_forward(cam)
            actor = ue.EditorLevelLibrary.spawn_actor_from_class(ue.SceneCapture2D, _vec(ue, to_ue_cm(cam['location'])),
                                                                 ue.Rotator(**rotator_from_forward(forward)))
            made.append(actor)
            comp = actor.get_component_by_class(ue.SceneCaptureComponent2D)
            got = comp.get_forward_vector()
            got = [float(got.x), float(got.y), float(got.z)]
            if max(abs(a - b) for a, b in zip(got, forward)) > 1e-5:
                raise ValueError(f'{view}: actual capture forward differs from the description')
            comp.set_editor_property('fov_angle', float(cam['ue_hfov_deg']))
            comp.set_editor_property('capture_source', ue.SceneCaptureSource.SCS_SCENE_COLOR_HDR)
            if comp.get_editor_property('capture_source') != ue.SceneCaptureSource.SCS_SCENE_COLOR_HDR:
                raise ValueError(f'{view}: actual capture source is not SCS_SCENE_COLOR_HDR (the receipt names its alpha from it)')
            comp.set_editor_property('texture_target', target)
            comp.set_editor_property('capture_every_frame', False)
            comp.set_editor_property('capture_on_movement', False)
            comp.set_editor_property('primitive_render_mode', ue.SceneCapturePrimitiveRenderMode.PRM_USE_SHOW_ONLY_LIST)
            for shown in primitives:                    # the method the cube capture uses; the property is template-only
                comp.show_only_actor_components(shown)
            pp = comp.get_editor_property('post_process_settings')
            pp.set_editor_property('override_auto_exposure_method', True)
            pp.set_editor_property('auto_exposure_method', ue.AutoExposureMethod.AEM_MANUAL)
            for key, value in overrides.items():
                pp.set_editor_property('override_' + key, True)
                pp.set_editor_property(key, value)
            comp.set_editor_property('post_process_settings', pp)
            comp.set_editor_property('post_process_blend_weight', 1.0)
            if comp.get_editor_property('fov_angle') - float(cam['ue_hfov_deg']) > 1e-4:
                raise ValueError(f'{view}: actual capture field of view differs')
            settings = _readback(comp, overrides)
            samples = []
            for _ in range(SETTLE):
                comp.capture_scene()
                yield 'settle_capture'                     # three settle captures, ticks apart
                px = [ue.RenderingLibrary.read_render_target_raw_pixel(world, target, x, y, False)
                      for x, y in settle_points(desc, view)]
                samples.append([[float(p.r), float(p.g), float(p.b)] for p in px])
            if samples[-1] != samples[-2]:
                raise ValueError(f'{view}: the settle captures disagree; shaders or streaming not settled')
            if not any(any(c) for c in samples[-1]):
                raise ValueError(f'{view}: every measured region reads zero: nothing rendered there (a sky or material not ready)')
            ue.RenderingLibrary.export_render_target(world, target, str(out), f'ue_{view}.exr')
            exr = out / f'ue_{view}.exr'
            if not exr.is_file() or exr.read_bytes()[:4] != b'\x76\x2f\x31\x01':
                raise ValueError(f'{view}: the exported capture is not an OpenEXR file')
            receipt['views'][view] = {'exr': exr.name, 'sha256': _sha(exr), 'camera_forward': got, 'settings': settings,
                                     'settle_samples': samples, 'hfov_deg': float(comp.get_editor_property('fov_angle'))}
        (out / 'capture.json').write_text(json.dumps(receipt, indent=1, default=str))
        print('LAMPWAY_UE_PARITY_COMPLETE ' + json.dumps({'out': str(out), 'views': sorted(receipt['views'])}), flush=True)
    finally:
        for actor in made:
            try:
                ue.EditorLevelLibrary.destroy_actor(actor)
            except Exception:  # noqa: BLE001 - attempt every cleanup; the original error stands
                pass
        for actor, editor_hidden, game_hidden in hidden:
            actor.set_is_temporarily_hidden_in_editor(editor_hidden)
            actor.set_actor_hidden_in_game(game_hidden)


def _material(ue, name, unlit, normal=None):
    mat = ue.Material()
    mat.set_editor_property('two_sided', True)
    lib = ue.MaterialEditingLibrary
    if unlit:
        mat.set_editor_property('shading_model', ue.MaterialShadingModel.MSM_UNLIT)
        e = lib.create_material_expression(mat, ue.MaterialExpressionVectorParameter)
        e.set_editor_property('parameter_name', 'Emissive')
        lib.connect_material_property(e, '', ue.MaterialProperty.MP_EMISSIVE_COLOR)
    else:
        for param, prop, vector in (('BaseColor', ue.MaterialProperty.MP_BASE_COLOR, True),
                                    ('Metallic', ue.MaterialProperty.MP_METALLIC, False),
                                    ('Roughness', ue.MaterialProperty.MP_ROUGHNESS, False),
                                    ('Specular', ue.MaterialProperty.MP_SPECULAR, False)):
            cls = ue.MaterialExpressionVectorParameter if vector else ue.MaterialExpressionScalarParameter
            e = lib.create_material_expression(mat, cls)
            e.set_editor_property('parameter_name', param)
            if not lib.connect_material_property(e, '', prop):
                raise ValueError(f'UE material connection failed: {param}')
        if normal is not None:
            t = lib.create_material_expression(mat, ue.MaterialExpressionTextureSampleParameter2D)
            t.set_editor_property('parameter_name', 'Normal')
            t.set_editor_property('texture', normal)    # a normal sampler over the default colour texture fails to compile
            t.set_editor_property('sampler_type', ue.MaterialSamplerType.SAMPLERTYPE_NORMAL)
            if not lib.connect_material_property(t, 'RGB', ue.MaterialProperty.MP_NORMAL):
                raise ValueError('UE normal connection failed')
    lib.recompile_material(mat)
    return mat


def _mesh(ue, world, shape, loc_cm, scale, rotation, material, made):
    actor = ue.EditorLevelLibrary.spawn_actor_from_class(ue.StaticMeshActor, ue.Vector(*loc_cm), ue.Rotator(**rotation))
    made.append(actor)
    comp = actor.get_component_by_class(ue.StaticMeshComponent)
    comp.set_static_mesh(ue.load_asset(f'/Engine/BasicShapes/{shape}.{shape}'))
    actor.set_actor_scale3d(ue.Vector(scale, scale, scale))
    comp.set_material(0, material)
    return actor, comp.create_dynamic_material_instance(0)


def _lit(ue, inst, base, metallic=0.0, roughness=0.5):
    inst.set_vector_parameter_value('BaseColor', ue.LinearColor(*base, 1.0))
    inst.set_scalar_parameter_value('Metallic', float(metallic))
    inst.set_scalar_parameter_value('Roughness', float(roughness))
    inst.set_scalar_parameter_value('Specular', 0.5)


def _build(ue, world, desc, k, made, out, receipt):
    """The description's objects, world and lights in UE; returns the primitives the capture shows."""
    shown = []
    obj, scene = desc['objects'], desc['scene']
    flat = {'pitch': 0.0, 'yaw': 0.0, 'roll': 90.0}   # Blender's camera-facing patch (normal -Y), mirrored: normal +Y in UE
    if scene == 'chart':
        mat = _material(ue, 'chart', True)
        for p in obj['patches']:
            actor, inst = _mesh(ue, world, 'Plane', to_ue_cm(p['location']), p['size_m'], flat, mat, made)
            inst.set_vector_parameter_value('Emissive', ue.LinearColor(*[k * c for c in p['emission']], 1.0))
            shown.append(actor)
    elif scene == 'furnace':
        mat = _material(ue, 'furnace', False)
        for s in obj['spheres']:
            actor, inst = _mesh(ue, world, 'Sphere', to_ue_cm(s['location']), s['radius_m'] * 2.0, flat, mat, made)
            _lit(ue, inst, s['base_color'], s['metallic'], s['roughness'])
            shown.append(actor)
    elif scene == 'normals':
        png = out / 'dome_dx.png'
        png.write_bytes(dome_dx_png(bumps=obj['plane']['bumps']))
        task = ue.AssetImportTask()
        for key, value in (('filename', str(png)), ('destination_path', '/Game/LampwayParityQA'), ('automated', True),
                           ('save', False), ('replace_existing', True)):
            task.set_editor_property(key, value)
        ue.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        tex = ue.load_asset('/Game/LampwayParityQA/dome_dx.dome_dx')
        tex.set_editor_property('srgb', False)
        tex.set_editor_property('compression_settings', ue.TextureCompressionSettings.TC_NORMALMAP)
        tex.set_editor_property('flip_green_channel', False)   # DirectX green, UE's own convention
        mat = _material(ue, 'normals', False, normal=tex)
        pl = obj['plane']
        actor, inst = _mesh(ue, world, 'Plane', to_ue_cm(pl['location']), pl['size_m'], plane_rotation(pl['rotation_euler']), mat, made)
        _lit(ue, inst, (0.8, 0.8, 0.8))
        inst.set_texture_parameter_value('Normal', tex)
        shown.append(actor)
    else:
        mat = _material(ue, 'lights', False)
        pl, sp = obj['plane'], obj['sphere']
        actor, inst = _mesh(ue, world, 'Plane', to_ue_cm(pl['location']), pl['size_m'], plane_rotation(pl['rotation_euler']), mat, made)
        _lit(ue, inst, pl['base_color'])
        shown.append(actor)
        actor, inst = _mesh(ue, world, 'Sphere', to_ue_cm(sp['location']), sp['radius_m'] * 2.0, flat, mat, made)
        _lit(ue, inst, sp['base_color'])
        shown.append(actor)
    w = desc['world']
    sky = [k * float(w['strength']) * c for c in w['color']]
    if any(sky):
        back = _material(ue, 'sky', True)
        dome, inst = _mesh(ue, world, 'Sphere', (0.0, 0.0, 0.0), 100.0, flat, back, made)   # 50 m radius, seen from inside
        inst.set_vector_parameter_value('Emissive', ue.LinearColor(*sky, 1.0))
        light = ue.EditorLevelLibrary.spawn_actor_from_class(ue.SkyLight, ue.Vector(0, 0, 0))
        made.append(light)
        sl = light.get_component_by_class(ue.SkyLightComponent)
        sl.set_editor_property('source_type', ue.SkyLightSourceType.SLS_CAPTURED_SCENE)
        sl.set_editor_property('lower_hemisphere_is_black', False)
        sl.set_editor_property('sky_distance_threshold', 1000.0)   # capture the 50 m dome, never the scene within 10 m
        sl.set_editor_property('intensity', 1.0)
        sl.recapture_sky()
        receipt['sky'] = {'radiance_k_scaled': sky, 'dome_radius_cm': 5000.0, 'sky_distance_threshold_cm': 1000.0}
    lights = []
    for row in ue_lights(desc, k):
        mapped = row['mapped']
        cls = getattr(ue, mapped['class'])
        actor = ue.EditorLevelLibrary.spawn_actor_from_class(cls, ue.Vector(*row.get('location_cm', (0.0, 0.0, 0.0))),
                                                             ue.Rotator(**rotator_from_forward(row.get('forward', (1.0, 0.0, 0.0)))))
        made.append(actor)
        comp = actor.get_component_by_class(getattr(ue, mapped['class'] + 'Component'))
        comp.set_editor_property('intensity', float(mapped['intensity']))
        if mapped['class'] == 'DirectionalLight':
            comp.set_editor_property('light_source_angle', float(mapped['source_angle_deg']))
        else:
            comp.set_editor_property('intensity_units', ue.LightUnits.CANDELAS)
            comp.set_editor_property('source_radius', float(mapped['source_radius_cm']))
            comp.set_editor_property('use_inverse_squared_falloff', True)
            if mapped['class'] == 'SpotLight':
                comp.set_editor_property('outer_cone_angle', float(mapped['outer_cone_deg']))
                comp.set_editor_property('inner_cone_angle', float(mapped['inner_cone_deg']))
        f = actor.get_actor_forward_vector()
        lights.append({**mapped, 'forward_readback': [float(f.x), float(f.y), float(f.z)], 'forward_wanted': row.get('forward')})
        if 'forward' in row and max(abs(a - b) for a, b in zip(lights[-1]['forward_readback'], row['forward'])) > 1e-5:
            raise ValueError('actual light forward differs from the description')
    receipt['lights'] = lights
    return shown


def run_ticking(ue):
    """The ticking job (ue_editor_leg.md: -ExecCmds "py <file>", register_slate_post_tick_callback, quit at the end)."""
    steps, state = capture_steps(ue), {}

    def finish():
        ue.unregister_slate_post_tick_callback(state['handle'])
        ue.SystemLibrary.quit_editor()

    def tick(_delta):
        if state.get('busy'):                    # a step can tick the engine itself (material compile, capture): never re-enter
            return
        state['busy'] = True
        try:
            next(steps)
        except StopIteration:
            finish()
        except Exception as exc:  # noqa: BLE001 - one readable line, then the editor quits
            print('error: UE parity capture refused: ' + str(exc), flush=True)
            print('help[1]: inspect the parity request, the parity profile and the scene description', flush=True)
            finish()
        finally:
            state['busy'] = False
    state['handle'] = ue.register_slate_post_tick_callback(tick)


if __name__ == '__main__':
    import unreal
    run_ticking(unreal)
