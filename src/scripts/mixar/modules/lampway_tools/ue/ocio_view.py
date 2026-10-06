# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The UE view (specs/ue_parity/contracts/ue_look.md §6; docs/ue-look.md): an OCIO view whose colour space is the sidecar's log2
shaper (an OCIO LogAffineTransform) followed by the profile's cube, sampled trilinearly, added to the app's own config.

The cube is DATA generated on the UE side (``cube``): this module never computes a tonemapper and never copies the cube. The
generated config lives in ``<lampway data>/ue_look/<key8>/ocio/config.ocio`` (key = the cube's sha256 and the shaper),
points at the app's own colour-management directory by absolute search path and at the cube where it lies.

The two traps the audit found (SCR/ocio_view_probe.json) are refused, never worked around:
  - a config with an error makes Blender log one line and fall back to its built-in config (AgX): ``view_for`` checks the view
    exists in THIS session and refuses otherwise;
  - a cube rewritten during a session is ignored (Blender keeps the processor it built): every apply re-validates the cube
    against its sidecar (sha256), and a re-described cube has a new key, so a new view name the running session does not have."""

import hashlib
import json
from pathlib import Path

from . import cube as CB
from . import profile as PR

VIEW_PREFIX = "UE 5.8 Filmic"
DISPLAY = "sRGB"


class ViewError(ValueError):
    pass


def _sha_file(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def names(profile, check) -> dict:
    """Where this cube's view lives and what it is called. The view is the cube and its shaper, nothing else of the profile
    (k and exposure act on the scene), so the key is their hash: another cube, or the same cube re-described, is another view."""
    from . import look
    key = hashlib.sha256(PR.canonical_json({"cube": check["sha256"], "shaper": check["shaper"]}).encode()).hexdigest()[:8]
    d = look.data_dir() / key / "ocio"
    return {"dir": d, "config": d / "config.ocio", "view_name": f"{VIEW_PREFIX} {key}", "colorspace": f"{VIEW_PREFIX} {key} sRGB"}


def _colorspace(n, check) -> str:
    s = check["shaper"]
    return f"""
  - !<ColorSpace>
    name: {n['colorspace']}
    family: Display
    equalitygroup:
    bitdepth: 32f
    description: |
      Lampway UE view: the sidecar's log2 shaper then the UE-side cube {Path(check['cube']).name} (sha256 {check['sha256']}), trilinear
    isdata: false
    from_scene_reference: !<GroupTransform>
      children:
        - !<ColorSpaceTransform> {{src: ACES2065-1, dst: Linear Rec.709}}
        - !<RangeTransform> {{min_in_value: 0, min_out_value: 0}}
        - !<LogAffineTransform> {{base: {s['base']!r}, lin_side_slope: {s['lin_side_slope']!r}, lin_side_offset: {s['lin_side_offset']!r}, log_side_slope: {s['log_side_slope']!r}, log_side_offset: {s['log_side_offset']!r}}}
        - !<RangeTransform> {{min_in_value: 0, max_in_value: 1, min_out_value: 0, max_out_value: 1}}
        - !<FileTransform> {{src: {json.dumps(str(Path(check['cube']).resolve()))}, interpolation: linear}}
"""


def _config_text(base_text, base_dir, n, check) -> str:
    """The app's config with an absolute search path, the UE colour space and the view on the sRGB display (and in active_views)."""
    lines = base_text.splitlines()
    try:
        d = next(i for i, l in enumerate(lines) if l.rstrip() == f"  {DISPLAY}:")
        c = next(i for i, l in enumerate(lines) if l.rstrip() == "colorspaces:")
        sp = next(i for i, l in enumerate(lines) if l.startswith("search_path:"))
    except StopIteration:
        raise ViewError("the app's config.ocio has no search_path, sRGB display or colorspaces section: it is not the config this view extends") from None
    rel = lines[sp].split(":", 1)[1].strip().strip('"').split(":")
    lines[sp] = "search_path: " + json.dumps(":".join(str(Path(base_dir) / r) for r in rel if r))
    lines.insert(d + 1, f"    - !<View> {{name: {n['view_name']}, colorspace: {n['colorspace']}}}")
    c += 1 if c > d else 0
    lines.insert(c + 1, _colorspace(n, check).strip("\n"))
    for i, l in enumerate(lines):
        if l.startswith("active_views: ["):                                 # an active_views list hides every view it does not name
            lines[i] = l.replace("active_views: [", f"active_views: [{n['view_name']}, ", 1)
            break
    return "\n".join(lines) + "\n"


def _validate_config(path, view):
    """Load the written config with OpenColorIO (bundled with the app) and require the view: a config error must fail here, not
    fall back silently at the next launch."""
    try:
        import PyOpenColorIO as OCIO
    except ImportError:
        return
    try:
        cfg = OCIO.Config.CreateFromFile(str(path))
        cfg.validate()
    except Exception as exc:
        raise ViewError(f"the generated config does not load: {exc}") from None
    if view not in cfg.getViews(DISPLAY):
        raise ViewError(f"the generated config has no view {view!r}")


def generate(profile, base_dir=None, cube=None, meta=None) -> dict:
    """Write the view's config for a VALID cube (refused otherwise, with the fix). Idempotent for one profile and cube."""
    check = CB.require(profile, cube, meta)
    n = names(profile, check)
    if not n["config"].is_file():
        base = Path(base_dir) if base_dir else None
        if base is None or not (base / "config.ocio").is_file():
            raise ViewError("the app's colour-management directory (datafiles/colormanagement) was not found")
        n["dir"].mkdir(parents=True, exist_ok=True)
        tmp = n["dir"] / "config.ocio.partial"
        tmp.write_text(_config_text((base / "config.ocio").read_text(encoding="utf-8"), base, n, check), encoding="utf-8")
        _validate_config(tmp, n["view_name"])
        tmp.rename(n["config"])
    return {"config_path": str(n["config"]), "view_name": n["view_name"], "config_sha256": _sha_file(n["config"]),
            "cube_path": check["cube"], "cube_sha256": check["sha256"], "engine_version": check["engine_version"],
            "launch": f"start Lampway with OCIO={n['config']} (the launcher does it while UE Look is enabled): Blender reads OCIO once, at start"}


def view_present(name) -> bool:
    """Whether this session's colour management has the view. The view enum is dynamic (it depends on the display), so its
    class-level items read NONE: the only reliable test is to set it on a scene and put the old value back."""
    import bpy
    vs = bpy.context.scene.view_settings
    old = vs.view_transform
    try:
        vs.view_transform = name
        return vs.view_transform == name
    except TypeError:
        return False
    finally:
        vs.view_transform = old


def view_for(profile, check) -> dict:
    """The view apply sets: the cube is valid (``check``) and the view must exist in this session, or apply is refused."""
    n = names(profile, check)
    if not view_present(n["view_name"]):
        raise ViewError(f"the UE view is missing: Blender fell back to its built-in config or was not started with OCIO={n['config']}; "
                        "check the OCIO error line in the log; enable UE Look (ue_look enable) and restart Lampway: the launcher starts it with the view")
    return {"state": "ready", "view_name": n["view_name"], "config_path": str(n["config"]), "cube_sha256": check["sha256"]}
