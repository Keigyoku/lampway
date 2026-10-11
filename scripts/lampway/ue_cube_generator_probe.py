# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only UE Python probe; run with -ExecutePythonScript, not -run=pythonscript.

The JSON marker is authoritative. Unreal's process exit does not prove Python success.
No level, material, settings, output cube or project asset is written by this probe.
"""
import json

REQUIRED = {
    "SystemLibrary": ["get_engine_version", "get_console_variable_int_value"],
    "RenderingLibrary": ["create_render_target2d", "read_render_target_raw_pixel", "read_render_target_pixel"],
    "MaterialEditingLibrary": ["create_material_expression", "connect_material_property", "recompile_material"],
    "EditorLevelLibrary": ["spawn_actor_from_class", "get_editor_world", "destroy_actor"],
    "SceneCaptureComponent2D": ["capture_scene", "show_only_actor_components"],
    "SceneCaptureSource": ["SCS_FINAL_TONE_CURVE_HDR", "SCS_SCENE_COLOR_HDR", "SCS_FINAL_COLOR_LDR"],
    "Material": [], "MaterialExpressionVectorParameter": [], "SceneCapture2D": [],
    "StaticMeshActor": [], "PostProcessSettings": [], "LinearColor": [], "Vector": [], "Rotator": [],
    "MaterialProperty": ["MP_EMISSIVE_COLOR"], "MaterialShadingModel": ["MSM_UNLIT"],
    "TextureRenderTargetFormat": ["RTF_RGBA16F", "RTF_RGBA8_SRGB"], "AutoExposureMethod": ["AEM_MANUAL"],
    "SceneCapturePrimitiveRenderMode": ["PRM_USE_SHOW_ONLY_LIST"],
    "Paths": ["project_dir"], "load_asset": [],
}
POSTPROCESS = (
    "film_slope", "film_toe", "film_shoulder", "film_black_clip", "film_white_clip",
    "blue_correction", "expand_gamut", "tone_curve_amount", "white_temp", "white_tint",
    "auto_exposure_method", "auto_exposure_bias", "auto_exposure_apply_physical_camera_exposure",
    "bloom_intensity", "vignette_intensity", "motion_blur_amount", "scene_fringe_intensity",
)
CVARS = ("r.LUT.Size", "r.LUT.Shaper", "r.HDR.Aces.Version", "r.AntiAliasingMethod")


def probe(ue):
    missing = [f"{owner}.{method}" for owner, methods in REQUIRED.items()
               for method in methods if not hasattr(getattr(ue, owner, None), method)]
    missing += [owner for owner in REQUIRED if not hasattr(ue, owner)]
    settings = None
    if hasattr(ue, "PostProcessSettings"):
        try:
            settings = ue.PostProcessSettings()
        except Exception:
            missing.append("PostProcessSettings.constructor")
    if settings is not None:
        for key in POSTPROCESS:
            for field in (key, "override_" + key):
                try:
                    settings.get_editor_property(field)
                except Exception:
                    missing.append("PostProcessSettings." + field)
    engine, cvars = None, {}
    if "SystemLibrary.get_engine_version" not in missing and hasattr(ue, "SystemLibrary"):
        try:
            engine = ue.SystemLibrary.get_engine_version()
        except Exception:
            missing.append("SystemLibrary.get_engine_version.call")
    if "SystemLibrary.get_console_variable_int_value" not in missing and hasattr(ue, "SystemLibrary"):
        for name in CVARS:
            try:
                cvars[name] = ue.SystemLibrary.get_console_variable_int_value(name)
            except Exception:
                missing.append("console_variable." + name)
    return {"schema": "lampway.ue-cube-capabilities/1", "engine_version": engine,
            "available": not missing, "missing": sorted(set(missing)), "cvars": cvars,
            "capture": "SCS_FINAL_COLOR_LDR", "format": "RTF_RGBA8_SRGB",
            "readback": "RenderingLibrary.read_render_target_pixel",
            "raw_control_capture": "SCS_SCENE_COLOR_HDR",
            "raw_control_readback": "RenderingLibrary.read_render_target_raw_pixel(normalize=False)",
            "note": "Capability introspection only; no captured cube or renderer proof. CVar existence/value must be verified against the actual engine before capture."}


def run(ue):
    result = probe(ue)
    print("LAMPWAY_UE_CUBE_PROBE " + json.dumps(result, sort_keys=True))
    if not result["available"]:
        print("error: required UE cube capture capability is absent: " + ", ".join(result["missing"]))
        print("help[1]: run in a disposable UE QA project with the already authorized Python/editor scripting plugins available")
        return 1
    return 0


if __name__ == "__main__":
    import unreal
    if run(unreal):
        raise RuntimeError("UE cube capability probe refused; inspect LAMPWAY_UE_CUBE_PROBE")
