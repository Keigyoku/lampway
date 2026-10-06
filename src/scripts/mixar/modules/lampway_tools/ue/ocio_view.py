# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The UE view (specs/ue_parity/contracts/ue_look.md §6): an OCIO view whose colour space is the profile's log2 shaper (an OCIO
LogAffineTransform) followed by the profile's 32^3 cube, sampled trilinearly, added to a copy of the app's own config.

The cube is DATA. The profile's ``tonemap.lut`` names it: {cube, cube_sha256, size, shaper {base, lin_side_slope,
lin_side_offset, log_side_slope, log_side_offset}}. Lampway does not generate it in this pass: the generator's provenance is a
captain decision (docs/reports/uelook.md, item 1), so a profile without a cube answers needs_decision and the view is left alone.

The two traps the audit found (SCR/ocio_view_probe.json) are refused, never worked around:
  - a config with an error makes Blender log one line and fall back to its built-in config (AgX): ``view_for`` checks the view
    exists in THIS session and refuses otherwise;
  - a cube rewritten during a session is ignored (Blender keeps the processor it built): a generated directory is named by the
    profile hash (``<lampway data>/ue_look/<sha8>/``), a cube there is never rewritten, the view name carries the hash, and the
    cube's bytes are checked against the profile's cube_sha256 at every apply."""

import hashlib
import shutil
from pathlib import Path

from . import profile as PR

VIEW_PREFIX = "UE 5.8 Filmic"
DISPLAY = "sRGB"
NEEDS_DECISION = ("the UE 5.8 Filmic cube is not generated in Lampway: where its generator lives (a port of the tonemapper maths in "
                  "Lampway, or a UE-side generator whose cube the profile names in tonemap.lut) is the captain's decision "
                  "(specs/ue_parity/REPORT.md decision 6; docs/reports/uelook.md item 1)")


class ViewError(ValueError):
    pass


def _sha_file(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def names(profile) -> dict:
    """Where this profile's view lives and what it is called (the hash is the profile's: a new profile is a new view)."""
    from . import look
    sha8 = PR.sha256(profile)[:8]
    d = look.data_dir() / sha8 / "ocio"
    return {"dir": d, "config": d / "config.ocio", "cube": d / "luts" / f"ue_filmic_{sha8}.cube", "view_name": f"{VIEW_PREFIX} {sha8}",
            "colorspace": f"{VIEW_PREFIX} {sha8} sRGB"}


def _colorspace(n, lut) -> str:
    s = lut["shaper"]
    return f"""
  - !<ColorSpace>
    name: {n['colorspace']}
    family: Display
    equalitygroup:
    bitdepth: 32f
    description: |
      Lampway UE view: the profile's log2 shaper then its {lut['size']}^3 cube (sha256 {lut['cube_sha256']}), trilinear
    isdata: false
    from_scene_reference: !<GroupTransform>
      children:
        - !<ColorSpaceTransform> {{src: ACES2065-1, dst: Linear Rec.709}}
        - !<RangeTransform> {{min_in_value: 0, min_out_value: 0}}
        - !<LogAffineTransform> {{base: {s['base']!r}, lin_side_slope: {s['lin_side_slope']!r}, lin_side_offset: {s['lin_side_offset']!r}, log_side_slope: {s['log_side_slope']!r}, log_side_offset: {s['log_side_offset']!r}}}
        - !<RangeTransform> {{min_in_value: 0, max_in_value: 1, min_out_value: 0, max_out_value: 1}}
        - !<FileTransform> {{src: {n['cube'].name}, interpolation: linear}}
"""


def _config_text(base_text, n, lut) -> str:
    """The app's config with the UE colour space appended to its colour spaces and the view added to the sRGB display."""
    lines = base_text.splitlines()
    try:
        d = next(i for i, l in enumerate(lines) if l.rstrip() == f"  {DISPLAY}:")
        c = next(i for i, l in enumerate(lines) if l.rstrip() == "colorspaces:")
    except StopIteration:
        raise ViewError("the app's config.ocio has no sRGB display or colorspaces section: it is not the config this view extends") from None
    lines.insert(d + 1, f"    - !<View> {{name: {n['view_name']}, colorspace: {n['colorspace']}}}")
    c += 1 if c > d else 0
    lines.insert(c + 1, _colorspace(n, lut).rstrip("\n").lstrip("\n"))
    act = [i for i, l in enumerate(lines) if l.startswith("active_views: [")]
    if act:                                                             # an active_views list hides every view it does not name
        i = act[0]
        lines[i] = lines[i].replace("active_views: [", f"active_views: [{n['view_name']}, ", 1)
    return "\n".join(lines) + "\n"


def generate(profile, base_dir=None) -> dict:
    """Write ``<lampway data>/ue_look/<sha8>/ocio/``: a copy of the app's colour-management directory whose config.ocio carries the
    UE view. Idempotent for one profile; a cube already there is never rewritten."""
    lut = profile["tonemap"]["lut"]
    if lut is None:
        return {"ok": False, "state": "needs_decision", "error": NEEDS_DECISION, "help": ["Ask the captain (REPORT.md decision 6)"]}
    src = Path(lut["cube"])
    if not src.is_file():
        raise ViewError(f"the profile's cube {src} is missing")
    if _sha_file(src) != lut["cube_sha256"]:
        raise ViewError(f"{src.name} does not match the profile's cube_sha256: the cube changed after the profile was written (re-dump the profile)")
    n = names(profile)
    if n["config"].is_file():
        if _sha_file(n["cube"]) != lut["cube_sha256"]:
            raise ViewError(f"the cube changed on disk in {n['dir']}: a cube is never rewritten in place (Blender keeps the old one); remove the directory to regenerate")
    else:
        base = Path(base_dir) if base_dir else None
        if base is None or not (base / "config.ocio").is_file():
            raise ViewError("the app's colour-management directory (datafiles/colormanagement) was not found")
        tmp = n["dir"].with_name("ocio.partial")
        if tmp.exists():
            shutil.rmtree(tmp)
        shutil.copytree(base, tmp)
        (tmp / "luts").mkdir(exist_ok=True)
        shutil.copyfile(src, tmp / "luts" / n["cube"].name)
        (tmp / "config.ocio").write_text(_config_text((base / "config.ocio").read_text(encoding="utf-8"), n, lut), encoding="utf-8")
        _validate(tmp / "config.ocio", n["view_name"])
        tmp.rename(n["dir"])
    return {"ok": True, "config_path": str(n["config"]), "cube_path": str(n["cube"]), "view_name": n["view_name"],
            "config_sha256": _sha_file(n["config"]), "launch": f"start Lampway with OCIO={n['config']} for the view to exist (Blender reads OCIO once, at start)"}


def _validate(path, view):
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


def view_for(profile) -> dict:
    """What apply does about the view transform: needs_decision without a cube; otherwise the view must exist in this session
    and its cube must still be the profile's, or apply is refused."""
    lut = profile["tonemap"]["lut"]
    if lut is None:
        return {"state": "needs_decision", "view_name": None, "why": NEEDS_DECISION}
    n = names(profile)
    if n["cube"].is_file() and _sha_file(n["cube"]) != lut["cube_sha256"]:
        raise ViewError(f"the cube changed on disk ({n['cube']}): Blender keeps the cube it loaded at start, so the picture would not be "
                        "this profile's; restart Lampway after regenerating (ue_look generate)")
    if not view_present(n["view_name"]):
        raise ViewError(f"the UE view is missing: Blender fell back to its built-in config or was not started with OCIO={n['config']}; "
                        "check the OCIO error line in the log (ue_look generate writes the config)")
    return {"state": "ready", "view_name": n["view_name"], "config_path": str(n["config"]), "cube_sha256": lut["cube_sha256"]}
