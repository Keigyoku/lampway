# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Additional read-only LDR/material/neutral-grading surface checks before capture.

This does not compile materials, create actors, render pixels or prove a capture.
"""
import json

REQUIRED = {
    'RenderingLibrary': ['read_render_target_pixel', 'read_render_target_raw_pixel'],
    'TextureRenderTargetFormat': ['RTF_RGBA8', 'RTF_RGBA8_SRGB'],
    'StaticMeshComponent': ['set_static_mesh', 'set_material', 'create_dynamic_material_instance'],
    'MaterialInstanceDynamic': ['set_vector_parameter_value'],
    'Actor': ['get_component_by_class', 'set_actor_scale3d'],
    'Material': [], 'MaterialExpressionVectorParameter': [], 'Vector4': [],
    'PostProcessSettings': [],
    'TextureRenderTarget2D': [], 'SceneCaptureComponent2D': [],
}


def probe(ue):
    missing = [owner + '.' + method for owner, methods in REQUIRED.items()
               for method in methods if not hasattr(getattr(ue, owner, None), method)]
    missing.extend(owner for owner in REQUIRED if not hasattr(ue, owner))
    props = {'Material': ['shading_model', 'two_sided'],
             'MaterialExpressionVectorParameter': ['parameter_name'],
             'PostProcessSettings': ['color_grading_intensity', 'override_color_grading_intensity'],
             'TextureRenderTarget2D': ['srgb', 'render_target_format', 'target_gamma',
                                       'use_legacy_gamma', 'size_x', 'size_y'],
             'SceneCaptureComponent2D': ['post_process_blend_weight', 'capture_every_frame',
                                         'capture_on_movement']}
    for band in ('', '_shadows', '_midtones', '_highlights'):
        for key in ('color_saturation', 'color_contrast', 'color_gamma', 'color_gain', 'color_offset'):
            props['PostProcessSettings'].extend([key + band, 'override_' + key + band])
    for owner, fields in props.items():
        factory = getattr(ue, owner, None)
        if factory is None:
            continue
        try:
            obj = factory()
        except Exception:
            missing.append(owner + '.constructor')
            continue
        for field in fields:
            try:
                obj.get_editor_property(field)
            except Exception:
                missing.append(owner + '.' + field)
    return {'schema': 'lampway.ue-cube-supplemental-capabilities/1',
            'available': not missing, 'missing': sorted(set(missing)),
            'capture': 'SCS_FINAL_COLOR_LDR', 'format': 'RTF_RGBA8_SRGB',
            'readback': 'RenderingLibrary.read_render_target_pixel',
            'note': 'Read-only Python surface check; does not prove shader compilation or captured pixels.'}


if __name__ == '__main__':
    import unreal
    result = probe(unreal)
    print('LAMPWAY_UE_CUBE_SUPPLEMENTAL_PROBE ' + json.dumps(result, sort_keys=True))
    if not result['available']:
        print('error: supplemental UE capture surface is absent: ' + ', '.join(result['missing']))
        print('help[1]: inspect the actual UE Python surface before attempting the full QA cube capture')
        raise RuntimeError('UE cube supplemental capability probe refused')
