# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Motion graphics: video drawn by code, frame by frame, deterministic (specs/motion_graphics/motion_graphics.md).

Two calls, each given ``new_capture``: a factory of FRESH capture adapters (``frames.Chromium``, or a fake). ``render(project_root, args,
new_capture)`` drives one adapter one frame at a time (t = i / fps, never real time, in order from frame 0 in one browser), hashes every frame,
streams it to one ffmpeg (``encode``), self-checks the sampled frames (``check``), then probes that the scene is a pure function of t: a SECOND,
fresh browser renders from frame 0 in sequence up to the last of 8 evenly spaced probe frames, and those frames must match exactly (a re-capture in
the same browser differs where an image is redrawn at a new scale: the decoded-image cache, measured on the teaser). It writes the outputs and the
receipt to ``<project>/motion/out/<name>-<code8>-<unique-run>/``. ``verify(project_root, args, new_capture)`` re-renders a receipt's inputs from frame 0 in a
fresh browser and compares every frame hash and both files. A refusal raises ``Refused`` with the fix in its text; a failing self-check is not a refusal (the files
are written and ``ok`` is false)."""
import hashlib
import os
from contextlib import ExitStack
import io
import json
import math
import re
import shutil
import tempfile
import time
from pathlib import Path

from PIL import Image

from . import check as C
from . import encode as E
from . import frames as F
from . import receipt as R
from .cancellation import checkpoint

INPUTS = ("action", "scene", "html", "entry", "name", "duration_s", "fps", "width", "height", "formats", "samples", "template", "variables", "vault", "receipt")
KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_SAMPLES, PROBE_FRAMES, DEFAULT_SAMPLES = 24, 8, 10
MAX_LONG_EDGE, MAX_SHORT_EDGE = 3840, 2160
# One defaults order for every rendered dimension (scene.md): an explicit argument, then the template's defaults, then the scene's own
# window.__scene, then the tool's fallback. Each resolved value records where it came from.
RESOLVED = ("width", "height", "fps", "duration_s")
FALLBACK = {"width": 1920, "height": 1080, "fps": 30}
SOURCES = ("explicit", "template", "scene", "tool default")


class Refused(ValueError):
    """A refusal that names its fix."""


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def inputs(args: dict) -> dict:
    """The validated inputs (specs/motion_graphics/tool.md, Inputs): every refusal names its fix. There is no frame range and no shard: a frame rendered out of order differs
    (measured), so the only order is from frame 0."""
    if not isinstance(args, dict):
        raise Refused("motion arguments must be a JSON object")
    if any(not isinstance(k, str) for k in args):
        raise Refused("motion argument names must be strings")
    unknown = sorted(set(args) - set(INPUTS))
    if unknown:
        raise Refused(f"{', '.join(unknown)}: not an input of motion_graphics; frames are rendered in order from frame 0 in one browser (no frame range, "
                      f"no sharding: an out-of-order frame differs, measured); the inputs are {', '.join(INPUTS)}")
    if any(value is None for value in args.values()):
        raise Refused("null is not a motion input value: omit optional properties to use defaults")
    for key in ("action", "scene", "html", "entry", "name", "template", "receipt"):
        if args.get(key) is not None and (not isinstance(args[key], str) or not args[key].strip()):
            raise Refused(f"{key}: pass a non-empty string")
    if "vault" in args and not isinstance(args["vault"], bool):
        raise Refused("vault: pass true or false")
    if args.get("variables") is not None:
        if not isinstance(args["variables"], dict):
            raise Refused("variables: pass a JSON object")
        try:
            _json_value(args["variables"])
        except (TypeError, ValueError, RecursionError) as exc:
            raise Refused("variables: pass JSON values with string keys and finite numbers") from exc
    if args.get("html") is not None and args.get("scene") is not None:
        raise Refused("pass one scene source: scene or html, not both")
    a = {"action": args.get("action") or "render", "scene": args.get("scene"), "html": args.get("html"), "entry": args.get("entry") or "index.html",
         "name": args.get("name"), "duration_s": args.get("duration_s"), "fps": args.get("fps"),
         "width": args.get("width"), "height": args.get("height"),
         "formats": args.get("formats", ["mp4", "webm"]), "samples": args.get("samples"), "template": args.get("template") or None,
         "variables": args.get("variables") or None, "vault": args.get("vault", True) is not False, "receipt": args.get("receipt")}
    if a["action"] not in ("render", "verify"):
        raise Refused(f"action {a['action']!r}: pass render or verify")
    if a["fps"] is not None:
        _check_fps(a["fps"])
    if a["width"] is not None or a["height"] is not None:          # a lone explicit edge is checked with the fallback for the other
        _check_size(FALLBACK["width"] if a["width"] is None else a["width"], FALLBACK["height"] if a["height"] is None else a["height"])
    if a["duration_s"] is not None:
        _duration(a["duration_s"])
    if not isinstance(a["formats"], list) or not a["formats"] or not all(isinstance(f, str) for f in a["formats"]) or not set(a["formats"]) <= set(E.FORMATS) or len(set(a["formats"])) != len(a["formats"]):
        raise Refused(f"formats {a['formats']}: pass a non-empty subset of {list(E.FORMATS)}")
    if a["samples"] is not None:
        s = a["samples"]
        if not isinstance(s, list) or not s or len(s) > MAX_SAMPLES or not all(isinstance(x, (int, float)) and not isinstance(x, bool) and (isinstance(x, int) or math.isfinite(x)) and x >= 0 for x in s):
            raise Refused(f"samples: pass 1 to {MAX_SAMPLES} times in seconds (>= 0) to self-check, or none for {DEFAULT_SAMPLES} evenly spaced plus the first and last frame")
    if a["name"] is not None and not (isinstance(a["name"], str) and KEBAB.match(a["name"])):
        raise Refused(f"name {a['name']!r} is not kebab-case: pass a name of a-z, 0-9 and single hyphens")
    if a["action"] == "verify":
        if not a["receipt"]:
            raise Refused("verify needs receipt: pass the receipt.json path")
        return a
    if a["html"] is not None and not a["name"]:
        raise Refused("html needs a name: pass name (the scene is written to motion/scenes/<name>/index.html)")
    if a["html"] is None and not a["scene"]:
        raise Refused("pass scene (a project-relative folder) or html (a single-file scene) with a name")
    return a


def _check_fps(fps) -> None:
    if _int(fps) is None or not 1 <= fps <= 60:
        raise Refused(f"fps {fps} out of range 1..60: pass fps between 1 and 60")


def _check_size(w, h) -> None:
    # the ceiling is by edge, not by axis: 2160x3840 (vertical 4K) is the same frame as 3840x2160
    if (_int(w) is None or _int(h) is None or w % 2 or h % 2 or min(w, h) < 16 or max(w, h) > MAX_LONG_EDGE or min(w, h) > MAX_SHORT_EDGE):
        raise Refused(f"size {w}x{h}: width and height must be even, long edge 16..{MAX_LONG_EDGE}, short edge 16..{MAX_SHORT_EDGE}")


_RESOLUTION = re.compile(r"^(\d{3,4})p$", re.IGNORECASE)
_NAMED = {"hd": 720, "fhd": 1080, "2k": 1440, "4k": 2160, "uhd": 2160}
_ASPECT = re.compile(r"^(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)$")


def template_defaults(params) -> dict:
    """A motion template's ``defaults`` (resolution + aspect_ratio, duration) as tool inputs: the short edge from the resolution
    ("1080p", "4k"), the long edge from the aspect ("16:9" -> 1920x1080, "9:16" -> 1080x1920), both rounded to even pixels."""
    params = params if isinstance(params, dict) else {}
    out = {}
    res, aspect = params.get("resolution"), params.get("aspect_ratio")
    if res is not None or aspect is not None:
        m = _RESOLUTION.match(str(res or "1080p"))
        short = int(m.group(1)) if m else _NAMED.get(str(res).lower())
        a = _ASPECT.match(str(aspect or "16:9"))
        if short is None or a is None or float(a.group(1)) <= 0 or float(a.group(2)) <= 0:
            raise Refused(f"template defaults resolution {res!r} / aspect_ratio {aspect!r}: use a resolution like 1080p and an aspect like 16:9 or 9:16")
        rw, rh = float(a.group(1)), float(a.group(2))
        long_ = 2 * round(short * max(rw, rh) / min(rw, rh) / 2)
        out["width"], out["height"] = (long_, short) if rw >= rh else (short, long_)
    if params.get("duration") is not None:
        out["duration_s"] = params["duration"]
    return out


def _declared(scene) -> dict:
    """The scene's own window.__scene values that can serve as defaults (well-typed ones only)."""
    scene = scene if isinstance(scene, dict) else {}
    out = {k: scene[k] for k in ("width", "height", "fps") if _int(scene.get(k)) is not None}
    d = scene.get("duration_s")
    if isinstance(d, (int, float)) and not isinstance(d, bool):
        out["duration_s"] = d
    return out


def _resolve(a: dict, template: dict, declared: dict) -> tuple:
    """(values, sources) for width, height, fps and duration_s in the one order: explicit, template, scene, tool default."""
    values, sources = {}, {}
    for key in RESOLVED:
        for source, layer in (("explicit", {key: a.get(key)}), ("template", template or {}), ("scene", declared), ("tool default", FALLBACK)):
            if layer.get(key) is not None:
                values[key], sources[key] = layer[key], source
                break
        else:
            values[key], sources[key] = None, None
    return values, sources


def _overrides(values: dict, sources: dict, declared: dict) -> tuple:
    """(findings, help): one warning when an explicit or template value overrides a differing window.__scene value."""
    over = [k for k in RESOLVED if sources.get(k) in ("explicit", "template") and k in declared and declared[k] != values[k]]
    if not over:
        return [], []
    detail = ", ".join(f"{k} {values[k]:g} ({sources[k]}) over the scene's {declared[k]:g}" for k in over)
    return ([{"check": "scene_override", "severity": "warn", "detail": f"window.__scene is overridden: {detail}"}],
            [f"to render the scene's own {', '.join(over)}: omit {' and '.join(over)} (and any template default for {'it' if len(over) == 1 else 'them'}), or change window.__scene"])


def _json_value(value):
    if isinstance(value, dict):
        if any(not isinstance(k, str) for k in value):
            raise TypeError("non-string JSON key")
        for item in value.values():
            _json_value(item)
    elif isinstance(value, list):
        for item in value:
            _json_value(item)
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite JSON number")
    elif value is not None and not isinstance(value, (str, int, bool)):
        raise TypeError("not a JSON value")


def _duration(d) -> float:
    if isinstance(d, bool) or not isinstance(d, (int, float)) or not 0 < d <= 120:
        if isinstance(d, (int, float)) and not isinstance(d, bool):
            try:
                label = f"{d:g}"
            except OverflowError:
                label = "(numeric magnitude exceeds representable seconds)"
            raise Refused(f"duration {label} s out of range (0, 120]: split the video or shorten the scene")
        raise Refused(f"duration {d!r} out of range (0, 120]: split the video or shorten the scene")
    return float(d)


def _jail(root: Path, rel: str) -> Path:
    import os
    full = Path(rel) if Path(rel).is_absolute() else root / rel
    real_root, real = Path(os.path.realpath(root)), Path(os.path.realpath(full))
    if real != real_root and real_root not in real.parents:
        raise Refused(f"{rel} is outside the project root")
    return real


def _scene(root: Path, a: dict) -> tuple:
    """(scene dir, entry path, project-relative scene path); an inline html is written to motion/scenes/<name>/index.html first."""
    if a["html"] is not None:
        rel = f"motion/scenes/{a['name']}"
        d = _jail(root, rel)
        data = a["html"].encode("utf-8")
        # Pin the scene parent and exclusively create new entries. An equal existing
        # entry is read through a checked descriptor and never rewritten.
        with ExitStack() as stack:
            current = os.open(root.resolve(), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            stack.callback(os.close, current)
            try:
                for part in d.relative_to(root.resolve()).parts:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=current)
                    except FileExistsError:
                        pass
                    current = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
                    stack.callback(os.close, current)
                actual = Path(os.readlink(f"/proc/self/fd/{current}"))
                if not actual.is_relative_to(root.resolve()) or actual != d.resolve():
                    raise Refused("inline scene directory changed: use real project directories")
                try:
                    fd = os.open("index.html", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=current)
                except FileExistsError:
                    pinned = Path(f"/proc/self/fd/{current}/index.html")
                    if pinned.is_symlink():
                        raise Refused("inline scene entry is a symlink: use a regular index.html in the scene folder")
                    with F._open_scene_file(pinned, root.resolve()) as source:
                        if source.read() != data:
                            raise Refused(f"{rel}/index.html exists and differs: pass a new name, or render the folder with scene")
                else:
                    with os.fdopen(fd, "wb") as target:
                        target.write(data)
            except (OSError, F.SceneError):
                raise Refused("inline scene directory or entry changed: use regular project files") from None
        a = dict(a, entry="index.html")
    else:
        rel = str(a["scene"]).rstrip("/")
        d = _jail(root, rel)
    entry = d / a["entry"]
    if not d.is_dir() or not entry.is_file() or d not in entry.resolve().parents:
        raise Refused(f"no scene entry {a['entry']} in {rel}: pass entry")
    a["entry"] = entry.resolve().relative_to(d).as_posix()
    return d, entry, d.relative_to(root.resolve()).as_posix()


def _sample_frames(n: int, samples, fps: int) -> list:
    if samples:
        return sorted({min(n - 1, int(round(float(s) * fps))) if s < (n - 1) / fps else n - 1 for s in samples})
    return sorted({0, n - 1} | {int(round(k * (n - 1) / (DEFAULT_SAMPLES + 1))) for k in range(1, DEFAULT_SAMPLES + 1)})


def _probe_frames(n: int) -> list:
    return sorted({int(round(k * (n - 1) / (PROBE_FRAMES - 1))) for k in range(PROBE_FRAMES)}) if n > 1 else [0]


def _pixels(png: bytes):
    im = Image.open(io.BytesIO(png))
    return im.size, hashlib.sha256(im.convert("RGB").tobytes()).hexdigest()


SCENE_DOC = "specs/motion_graphics/scene.md"


def _page_error(capture) -> str:
    """The page's first script error, for a refusal: a syntax error leaves __frame undefined, and the parse error is the cause."""
    errors = capture.errors() if hasattr(capture, "errors") else []
    return f" (the page reported {len(errors)} script error{'s' if len(errors) != 1 else ''}; the first: {errors[0]})" if errors else ""


class EngineDiffers(Exception):
    pass


def _ready(capture, entry, W, H, engine=None, ffmpeg=None, scene_root=None) -> None:
    """Open the adapter and run the scene contract's refusals: a different engine (verify), no __frame, a setup miss, CSS animations."""
    capture.scene_root = scene_root or entry.parent
    capture.open(entry, W, H)
    if engine is not None and (capture.product, ffmpeg) != tuple(engine):
        here, there = (capture.product, ffmpeg), tuple(engine)
        k = 0 if here[0] != there[0] else 1
        raise EngineDiffers(f"cannot reproduce: the engine differs (receipt: {there[k]}, here: {here[k]})")
    if not capture.has_frame():
        raise Refused(f"the scene does not define window.__frame{_page_error(capture)}: see the scene contract in {SCENE_DOC}")
    ready = capture.setup()
    if not isinstance(ready, dict):
        raise Refused("window.__setup() must return an object with fonts and images arrays")
    misses = []
    for key, label in (("fonts", "font"), ("images", "src")):
        reports = ready.get(key)
        if not isinstance(reports, list):
            raise Refused(f"window.__setup() must return a {key} array (use [] when none are needed)")
        for report in reports:
            if (not isinstance(report, dict) or not isinstance(report.get(label), str) or not report[label].strip()
                    or not isinstance(report.get("ok"), bool)):
                raise Refused(f"window.__setup() {key}: each row needs a non-empty {label} string and a boolean ok")
            if report["ok"] is False:
                misses.append(report[label])
    if hasattr(capture, "has_audit") and not capture.has_audit():
        raise Refused(f"the scene does not define window.__audit{_page_error(capture)}: return text and marks arrays ({SCENE_DOC})")
    if misses:
        raise Refused(f"scene not ready, these did not load: {misses}: put them in the scene folder and check the paths")
    if capture.animations():
        raise Refused("the scene runs CSS animations or transitions (document.getAnimations() is not empty): drive them from __frame(t)")


def _probe(new_capture, entry, W, H, fps, rows, probe, samples, scene_root=None, cancel=None) -> tuple:
    """(differing probe frames, frames rendered, seconds): a fresh browser, frames 0..max(probe) in sequence (the samples' audits at the same frames,
    as the first pass ran them), each probe frame compared exactly with the first pass."""
    t0, differ, requests = time.monotonic(), [], []
    checkpoint(cancel)
    cap = new_capture()
    cap.cancel = cancel
    try:
        _ready(cap, entry, W, H, scene_root=scene_root)
        want = set(probe)
        for i in range(max(probe) + 1):
            checkpoint(cancel)
            png = cap.frame(i / fps)
            checkpoint(cancel)
            if i in samples:
                C.validate_audit(cap.audit())
            if i in want and _pixels(png)[1] != rows[i].split()[2]:
                differ.append(i)
        requests = cap.requests()
    finally:
        cap.close()
    checkpoint(cancel)
    return differ, max(probe) + 1, round(time.monotonic() - t0, 3), requests


def _output_directory(root, parent, prefix, stack):
    """Pin every ancestor and the new directory; render through fds rather than raceable pathnames."""
    root = root.resolve()
    relative = parent.absolute().relative_to(root)
    current = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    stack.callback(os.close, current)
    try:
        for part in relative.parts:
            try:
                os.mkdir(part, mode=0o700, dir_fd=current)
            except FileExistsError:
                pass
            current = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            stack.callback(os.close, current)
        # mkdtemp has exclusive creation; its parent descriptor survives any pathname swap.
        stable_parent = Path(f"/proc/self/fd/{current}")
        created = Path(tempfile.mkdtemp(prefix=prefix, dir=stable_parent))
        descriptor = os.open(created.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
        stack.callback(os.close, descriptor)
        logical = parent / created.name
        actual = Path(os.readlink(f"/proc/self/fd/{descriptor}"))
        if not actual.is_relative_to(root) or logical.resolve() != actual:
            raise Refused("output directory changed or is outside the project: use real project directories")
        return Path(f"/proc/self/fd/{descriptor}"), logical.relative_to(root).as_posix(), descriptor
    except OSError:
        raise Refused("output directory changed or contains a symlink: use real project directories") from None


def _run(root: Path, a: dict, new_capture, out_root: Path, threads: int, engine=None, probe_on=True, cancel=None, handoff=None, defaults=None) -> dict:
    checkpoint(cancel)
    with ExitStack() as stack:
        return _run_pinned(root.resolve(), a, new_capture, out_root.absolute(), threads, engine, probe_on, stack, cancel, handoff, defaults)


def _run_pinned(root: Path, a: dict, new_capture, out_root: Path, threads: int, engine, probe_on, stack, cancel=None, handoff=None, defaults=None) -> dict:
    """One render: refusals, then the sequential pass, the probe (a fresh browser; not in verify, which is itself the full re-render), the files
    and the receipt. ``engine`` (verify) = the receipt's (chromium, ffmpeg) pair: a different engine stops the run before any frame."""
    checkpoint(cancel)
    t_start = time.monotonic()
    scene_dir, entry, scene_rel = _scene(root, a)
    E.require()
    ffmpeg = E.version(cancel=cancel)
    code_sha, files = F.scene_hash(scene_dir, cancel=cancel)
    checkpoint(cancel)
    name = a["name"] or scene_dir.name
    if not KEBAB.match(name):
        raise Refused(f"name {name!r} (the scene folder's) is not kebab-case: pass name")
    template = defaults or {}
    provisional, _ = _resolve(a, template, {})                              # the page must be opened at a size before __scene can be read
    W, H = provisional["width"], provisional["height"]
    _check_size(W, H)
    enc = None
    checkpoint(cancel)
    capture = new_capture()
    capture.cancel = cancel
    try:
        _ready(capture, entry, W, H, engine, ffmpeg, scene_root=scene_dir)                       # inside the try: a launch that fails half way is still closed
        checkpoint(cancel)
        declared = _declared(capture.scene())
        resolved, sources = _resolve(a, template, declared)
        _check_fps(resolved["fps"])
        _check_size(resolved["width"], resolved["height"])
        duration = _duration(resolved["duration_s"])
        fps = resolved["fps"]
        if (resolved["width"], resolved["height"]) != (W, H):                # the scene's own size: render it in a FRESH browser opened at that size
            capture.close()
            W, H = resolved["width"], resolved["height"]
            capture = new_capture()
            capture.cancel = cancel
            _ready(capture, entry, W, H, engine, ffmpeg, scene_root=scene_dir)
            checkpoint(cancel)
        resolved["duration_s"] = duration
        size_notes, override_help = _overrides(resolved, sources, declared)
        n = int(round(duration * fps))
        if n < 1:
            raise Refused(f"duration {duration:g} s at {fps} fps is no frame: lengthen the scene")
        samples = set(_sample_frames(n, a["samples"], fps))
        t_setup = time.monotonic() - t_start
        checkpoint(cancel)
        out, out_rel, out_fd = _output_directory(root, out_root, f"{name}-{code_sha[:8]}-", stack)
        (out / "samples").mkdir()
        paths = {fmt: out / f"{name}.{fmt}" for fmt in E.FORMATS if fmt in a["formats"]}
        argv = E.argv(paths, fps, threads)
        enc = E.Encoder(argv, pass_fds=(out_fd,), cancel=cancel)
        rows, checks, t_cap = [], [], 0.0
        t_loop = time.monotonic()
        for i in range(n):
            checkpoint(cancel)
            t = i / fps
            c0 = time.monotonic()
            png = capture.frame(t)
            checkpoint(cancel)
            t_cap += time.monotonic() - c0
            size, pix = _pixels(png)
            if size != (W, H):
                raise Refused(f"frame {i} is {size[0]}x{size[1]}, not {W}x{H}: the scene must not resize the page")
            rows.append(R.row(i, t, pix))
            enc.write(png)
            if i in samples:
                audit = capture.audit()
                C.validate_audit(audit)
                im, stats = C.frame_stats(png)
                found = C.findings(im, stats, audit, W, H)
                stem = f"f{i:04d}"
                (out / "samples" / f"{stem}.png").write_bytes(png)
                (out / "samples" / f"{stem}.json").write_text(json.dumps({"frame": i, "t": t, "stats": stats, "audit": audit, "findings": found}, indent=1), encoding="utf-8")
                checks.append({"frame": i, "t": round(t, 4), "stats": stats, "findings": found})
        t_render = time.monotonic() - t_loop
        e0 = time.monotonic()
        enc.finish()
        checkpoint(cancel)
        t_encode_tail = time.monotonic() - e0
        enc = None
        requests = capture.requests()
        page_errors = capture.errors() if hasattr(capture, "errors") else []
    finally:
        if enc is not None:
            enc.abort()
        capture.close()
    probe, differ, probe_frames, t_probe, probe_requests = _probe_frames(n), [], 0, 0.0, []
    if probe_on:                                                           # the scene must be a pure function of t: a fresh browser agrees
        differ, probe_frames, t_probe, probe_requests = _probe(new_capture, entry, W, H, fps, rows, probe, samples, scene_root=scene_dir, cancel=cancel)
    checkpoint(cancel)
    (out / "frames.sha256").write_text(R.frames_text(rows), encoding="utf-8")
    digest = R.digest(rows)
    artifact_hashes = {}
    C.contact_sheet(out / "samples", out / "contact.png", hashes=artifact_hashes)
    if page_errors:                                                        # an error that did not stop the render still deserves a look
        size_notes = size_notes + [{"check": "page_error", "severity": "warn",
                                    "detail": f"the page reported {len(page_errors)} script error(s); the first: {page_errors[0]}"}]
    findings = [{"frame": 0, **f} for f in size_notes] + [{"frame": c["frame"], **f} for c in checks for f in c["findings"]]
    findings += [{"frame": i, "check": "determinism", "severity": "fail", "detail": f"the scene is not a pure function of t: frame {i} differs on a second capture"} for i in differ]
    non_file = list(dict.fromkeys(u for u in requests + probe_requests
                                  if not (u.startswith("data:") or F.allowed_file_url(u, scene_dir))))
    outputs = {fmt: {"sha256": F.sha256_file(p, cancel=cancel), "bytes": p.stat().st_size, "probe": E.probe(p, pass_fds=(out_fd,), cancel=cancel)} for fmt, p in paths.items()}
    wall = time.monotonic() - t_start
    fail = sum(1 for f in findings if f["severity"] == "fail")
    warn = sum(1 for f in findings if f["severity"] == "warn")
    ok = fail == 0 and not non_file
    run_id = f"mg-{Path(out_rel).name}"
    files_out = {fmt: f"{out_rel}/{p.name}" for fmt, p in paths.items()}
    files_out.update(contact=f"{out_rel}/contact.png", receipt=f"{out_rel}/receipt.json", frames=f"{out_rel}/frames.sha256")
    receipt = {
        "ok": ok, "tool": "motion_graphics", "run_id": run_id, "out_dir": out_rel, "files": files_out,
        "inputs": {"scene": scene_rel, "entry": a["entry"] if a["html"] is None else "index.html", "name": name, "fps": fps, "width": W, "height": H,
                   "duration_s": duration, "formats": [f for f in E.FORMATS if f in a["formats"]], "samples": a["samples"], "template": a["template"],
                   "variables": a["variables"]},
        "input_sources": sources, "help": override_help,
        "frames": n, "code_sha256": code_sha, "scene_files": [{"path": p, "sha256": d} for p, d in files],
        "engine": {"chromium": capture.product, "chrome_flags": list(capture.flags), "ffmpeg": ffmpeg,
                   "encoder": {"threads": threads, "args": E.receipt_args(argv)}, "driver_sha256": F.sha256_file(F.__file__)},
        "frames_sha256_digest": digest, "frame_hash": R.FRAME_HASH, "artifact_hashes": artifact_hashes,
        "outputs": outputs,
        "network": {"requests": len(requests), "non_file": non_file},
        "timing_s": {"setup": round(t_setup, 3), "render_loop": round(t_render, 3), "capture": round(t_cap, 3), "encode_tail": round(t_encode_tail, 3),
                     "probe": t_probe, "wall": round(wall, 3), "wall_per_video_second": round(wall / duration, 3), "capture_ms_per_frame": round(1000 * t_cap / n, 1)},
        "self_check": {"fail": fail, "warn": warn, "findings": findings, "samples": checks},
        "determinism_probe": ({"browser": "fresh", "frames": probe, "differing": differ, "rendered_frames": probe_frames, "seconds": t_probe} if probe_on
                              else {"browser": None, "skipped": "verify re-renders every frame itself"}),
    }
    if non_file:
        receipt["error"] = f"the scene asked for {non_file[0]}: every file must be in the scene folder"
    checkpoint(cancel)
    if _jail(root, out_rel) != Path(os.readlink(f"/proc/self/fd/{out_fd}")):
        raise Refused("output directory changed: restore the real project output directory")
    (out / "receipt.json").write_text(json.dumps(receipt, indent=1), encoding="utf-8")
    checkpoint(cancel)
    if handoff is not None:
        handoff(receipt, out)
        checkpoint(cancel)
    return receipt


def summary(receipt: dict) -> dict:
    """The tool's answer (specs/motion_graphics/tool.md, Outputs) from a receipt."""
    out = {"ok": receipt["ok"], "run_id": receipt["run_id"], "out_dir": receipt["out_dir"],
           "files": {k: v for k, v in receipt["files"].items() if k in ("mp4", "webm", "contact")}, "code_sha256": receipt["code_sha256"],
           "frames": receipt["frames"], "frames_sha256_digest": receipt["frames_sha256_digest"],
           "outputs": {k: {"sha256": v["sha256"], "bytes": v["bytes"]} for k, v in receipt["outputs"].items()},
           "self_check": {k: receipt["self_check"][k] for k in ("fail", "warn", "findings")}, "network": receipt["network"],
           "timing_s": {k: receipt["timing_s"][k] for k in ("wall", "wall_per_video_second", "capture_ms_per_frame")}}
    sources = receipt.get("input_sources") or {}
    if sources:
        out["inputs"] = [{"name": k, "value": receipt["inputs"][k], "source": sources[k]} for k in RESOLVED if k in sources]
    if receipt.get("error"):
        out["error"] = receipt["error"]
    out["help"] = list(receipt.get("help") or []) + next_steps(receipt)
    return out


def next_steps(receipt: dict) -> list:
    """The agent's generic next steps after a render (the CLI words its own)."""
    return [f"look at {receipt['files']['contact']} yourself and watch the video: some defects only an eye sees",
            f"verify the render: action verify, receipt {receipt['out_dir']}/receipt.json"]


def render(project_root, args: dict, new_capture, threads: int = E.THREADS, cancel=None, handoff=None, defaults=None) -> dict:
    """``defaults``: a template's defaults as tool inputs (``template_defaults``); they rank below explicit arguments."""
    checkpoint(cancel)
    root = Path(project_root).resolve()
    a = inputs(args)
    return summary(_run(root, a, new_capture, root / "motion" / "out", threads, cancel=cancel, handoff=handoff, defaults=defaults))


def _receipt_inputs(receipt):
    """Validate the receipt data verification relies on before launching a renderer."""
    def require(condition, field):
        if not condition:
            raise Refused(f"invalid motion receipt: {field}; use an unchanged receipt from a completed render")
    def text(value):
        return isinstance(value, str) and bool(value.strip())
    def digest(value):
        return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None
    require(isinstance(receipt, dict), "expected a JSON object")
    try:
        _json_value(receipt)
    except (TypeError, ValueError, RecursionError):
        raise Refused("invalid motion receipt: use JSON values with finite numbers") from None
    for field in ("inputs", "engine", "outputs", "files"):
        require(isinstance(receipt.get(field), dict), field)
    require(receipt.get("tool") == "motion_graphics", "tool")
    require(isinstance(receipt.get("ok"), bool), "ok")
    require(text(receipt.get("out_dir")) and text(receipt.get("run_id")), "output identity")
    for field in ("code_sha256", "frames_sha256_digest"):
        require(digest(receipt.get(field)), field)
    require(receipt.get("frame_hash") == R.FRAME_HASH, "frame_hash")
    saved = receipt["inputs"]
    fields = ("scene", "entry", "name", "fps", "width", "height", "duration_s", "formats", "samples")
    require(all(field in saved for field in fields), "saved inputs")
    require(all(text(saved[field]) for field in ("scene", "entry", "name")), "saved scene, entry and name")
    require(saved["duration_s"] is not None, "saved duration_s")
    try:
        a = inputs({field: saved[field] for field in fields if saved[field] is not None})
    except Refused as exc:
        raise Refused(f"invalid motion receipt inputs: {exc}") from None
    require(_int(receipt.get("frames")) is not None and receipt["frames"] >= 1, "frames")
    require(receipt["frames"] == round(a["duration_s"] * a["fps"]), "frame count and duration")
    engine = receipt["engine"]
    require(text(engine.get("chromium")) and text(engine.get("ffmpeg")), "engine versions")
    require(isinstance(engine.get("chrome_flags"), list) and all(isinstance(v, str) for v in engine["chrome_flags"]), "chrome_flags")
    require(digest(engine.get("driver_sha256")), "driver_sha256")
    encoder = engine.get("encoder")
    require(isinstance(encoder, dict), "encoder")
    require(_int(encoder.get("threads")) is not None and encoder["threads"] > 0, "encoder threads")
    require(isinstance(encoder.get("args"), list) and all(isinstance(v, str) for v in encoder["args"]), "encoder args")
    require(set(receipt["outputs"]) == set(a["formats"]), "requested outputs")
    for fmt in a["formats"]:
        output = receipt["outputs"][fmt]
        require(isinstance(output, dict), f"outputs.{fmt}")
        require(digest(output.get("sha256")), f"outputs.{fmt}.sha256")
        require(_int(output.get("bytes")) is not None and output["bytes"] > 0, f"outputs.{fmt}.bytes")
        require(text(receipt["files"].get(fmt)), f"files.{fmt}")
    inventory = receipt.get("scene_files")
    require(isinstance(inventory, list) and bool(inventory), "scene_files")
    rows = []
    for item in inventory:
        require(isinstance(item, dict) and text(item.get("path")) and digest(item.get("sha256")), "scene file row")
        path = Path(item["path"])
        require(not path.is_absolute() and ".." not in path.parts, "scene file path")
        rows.append((item["path"], item["sha256"]))
    require(len({path for path, _ in rows}) == len(rows), "duplicate scene file paths")
    inventory_digest = hashlib.sha256("".join(f"{path}\0{sha}\n" for path, sha in sorted(rows)).encode()).hexdigest()
    require(inventory_digest == receipt["code_sha256"], "scene inventory digest")
    return a


def _receipt_frames(root, path, receipt, cancel=None):
    checkpoint(cancel)
    with F._open_scene_file(_jail(root, str(path)), root) as source:
        try:
            data = source.read().decode("utf-8")
        except UnicodeError:
            raise Refused("invalid motion receipt: frames.sha256 must be UTF-8") from None
    checkpoint(cancel)
    rows = data.splitlines()
    if len(rows) != receipt["frames"] or data != R.frames_text(rows) or R.digest(rows) != receipt["frames_sha256_digest"]:
        raise Refused("invalid motion receipt: frame list count or digest differs; preserve the original frame list")
    for i, row in enumerate(rows):
        fields = row.split()
        if len(fields) != 3 or re.fullmatch(r"[0-9a-f]{64}", fields[2]) is None or row != R.row(i, i / receipt["inputs"]["fps"], fields[2]):
            raise Refused("invalid motion receipt: malformed frame row; preserve the original frame list")
    return rows


def _verify_media_file(root, path, expected, cancel=None):
    """Hash checked original bytes and retain inode identity without exposing filesystem metadata."""
    checkpoint(cancel)
    try:
        with F._open_scene_file(_jail(root, path), root) as source:
            before = os.fstat(source.fileno())
            sha = hashlib.sha256()
            for block in iter(lambda: source.read(1 << 20), b""):
                checkpoint(cancel)
                sha.update(block)
            after = os.fstat(source.fileno())
        checkpoint(cancel)
        identity = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        stable = identity(before) == identity(after)
        matches = stable and sha.hexdigest() == expected["sha256"] and after.st_size == expected["bytes"]
        return {"matches": matches, "sha256": sha.hexdigest(), "bytes": after.st_size,
                "error": None if matches else ("changed_during_read" if not stable else "hash_mismatch")}, identity(after)
    except FileNotFoundError:
        return {"matches": False, "error": "missing"}, None
    except (Refused, F.SceneError):
        return {"matches": False, "error": "outside_project_or_not_regular"}, None
    except OSError as exc:
        import errno
        if exc.errno not in (errno.EACCES, errno.EPERM, errno.ENOTDIR, errno.ELOOP):
            raise
        return {"matches": False, "error": "unreadable"}, None


def verify(project_root, args: dict, new_capture, cancel=None) -> dict:
    """Keep recorded reproduction separate from original-media integrity and provenance identity."""
    checkpoint(cancel)
    root = Path(project_root).resolve()
    if not isinstance(args, dict):
        raise Refused("motion arguments must be a JSON object")
    rel = inputs({**args, "action": "verify"})["receipt"]
    if not rel:
        raise Refused("verify needs receipt: the project-relative path of a render's receipt.json")
    path = _jail(root, rel)
    if not path.is_file():
        raise Refused(f"no receipt at {rel}: pass the receipt.json of a render")
    with F._open_scene_file(path, root) as source:
        try:
            r = json.loads(source.read().decode("utf-8"))
        except (ValueError, UnicodeError, RecursionError):
            raise Refused("invalid motion receipt: expected a valid UTF-8 JSON receipt") from None
    checkpoint(cancel)
    a = _receipt_inputs(r)
    original_out = _jail(root, r["out_dir"])
    original_frames = _jail(root, str(original_out / "frames.sha256"))
    old_rows = _receipt_frames(root, original_frames, r, cancel)
    before_media = {fmt: _verify_media_file(root, r["files"][fmt], r["outputs"][fmt], cancel) for fmt in a["formats"]}
    scene = _jail(root, a["scene"])
    source_before = F.scene_hash(scene, cancel=cancel)[0]
    driver_before = F.sha256_file(F.__file__, cancel=cancel)
    checkpoint(cancel)
    captures = []
    def capture_factory():
        cap = new_capture()
        captures.append(cap)
        return cap
    work = root / "motion" / "out" / f".verify-{time.monotonic_ns()}"
    new, mismatch = None, None
    try:
        try:
            new = _run(root, a, capture_factory, work, r["engine"]["encoder"]["threads"], engine=(r["engine"]["chromium"], r["engine"]["ffmpeg"]),
                       probe_on=False, cancel=cancel)
        except EngineDiffers as exc:
            mismatch = str(exc)
        checkpoint(cancel)
        current_rows = _receipt_frames(root, root / r["out_dir"] / "frames.sha256", r, cancel)
        new_rows = _receipt_frames(root, root / new["out_dir"] / "frames.sha256", new, cancel) if new is not None else []
        integrity = {}
        for fmt in a["formats"]:
            before, before_id = before_media[fmt]
            after, after_id = _verify_media_file(root, r["files"][fmt], r["outputs"][fmt], cancel)
            changed = before_id != after_id
            replaced = before_id is not None and (after_id is None or before_id[:2] != after_id[:2])
            integrity[fmt] = {"matches": before["matches"] and after["matches"] and not changed,
                              "before": before, "after": after, "changed": changed, "replaced": replaced}
        source_after = F.scene_hash(scene, cancel=cancel)[0]
        driver_after = F.sha256_file(F.__file__, cancel=cancel)
        flags = list(captures[-1].flags) if captures else None
        provenance = {
            "source": {"matches": r["code_sha256"] == source_before == source_after and (new is None or new["code_sha256"] == r["code_sha256"]),
                       "recorded": r["code_sha256"], "before": source_before, "after": source_after},
            "driver": {"matches": r["engine"]["driver_sha256"] == driver_before == driver_after and (new is None or new["engine"]["driver_sha256"] == r["engine"]["driver_sha256"]),
                       "recorded": r["engine"]["driver_sha256"], "before": driver_before, "after": driver_after},
            "flags": {"matches": r["engine"]["chrome_flags"] == flags, "recorded": r["engine"]["chrome_flags"], "current": flags}}
        checkpoint(cancel)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    checks = {"integrity_matches": all(item["matches"] for item in integrity.values()), "integrity": integrity,
              "provenance_matches": mismatch is None and all(item["matches"] for item in provenance.values()), "provenance": provenance}
    if mismatch is not None:
        eq = {f"{fmt}_equal": False if fmt in a["formats"] else None for fmt in E.FORMATS}
        return {"reproduced": False, "frames_differing": [], **eq, "engine_matches": False, "error": mismatch, **checks}
    differ = R.differing(old_rows, new_rows)
    eq = {f"{fmt}_equal": (r["outputs"].get(fmt) or {}).get("sha256") == (new["outputs"].get(fmt) or {}).get("sha256") if fmt in r["outputs"] else None
          for fmt in E.FORMATS}
    reproduced = current_rows == old_rows and not differ and all(v for v in eq.values() if v is not None) and new["frames_sha256_digest"] == r["frames_sha256_digest"]
    return {"reproduced": reproduced, "frames_differing": differ, **eq, "engine_matches": True, "receipt": rel, "frames": new["frames"], **checks}
