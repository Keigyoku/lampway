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
import io
import json
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

INPUTS = ("action", "scene", "html", "entry", "name", "duration_s", "fps", "width", "height", "formats", "samples", "template", "variables", "vault", "receipt")
KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_SAMPLES, PROBE_FRAMES, DEFAULT_SAMPLES = 24, 8, 10
NETWORK_OK = ("file:", "data:")


class Refused(ValueError):
    """A refusal that names its fix."""


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def inputs(args: dict) -> dict:
    """The validated inputs (section 4): every refusal names its fix. There is no frame range and no shard: a frame rendered out of order differs
    (measured), so the only order is from frame 0."""
    args = args if isinstance(args, dict) else {}
    unknown = sorted(set(args) - set(INPUTS))
    if unknown:
        raise Refused(f"{', '.join(unknown)}: not an input of motion_graphics; frames are rendered in order from frame 0 in one browser (no frame range, "
                      f"no sharding: an out-of-order frame differs, measured); the inputs are {', '.join(INPUTS)}")
    a = {"action": args.get("action") or "render", "scene": args.get("scene"), "html": args.get("html"), "entry": args.get("entry") or "index.html",
         "name": args.get("name"), "duration_s": args.get("duration_s"), "fps": 30 if args.get("fps") is None else args["fps"],
         "width": 1920 if args.get("width") is None else args["width"], "height": 1080 if args.get("height") is None else args["height"],
         "formats": args.get("formats", ["mp4", "webm"]), "samples": args.get("samples"), "template": args.get("template") or None,
         "variables": args.get("variables") or None, "vault": args.get("vault", True) is not False, "receipt": args.get("receipt")}
    if a["action"] not in ("render", "verify"):
        raise Refused(f"action {a['action']!r}: pass render or verify")
    if a["action"] == "verify":
        return a
    fps, w, h = _int(a["fps"]), _int(a["width"]), _int(a["height"])
    if fps is None or not 1 <= fps <= 60:
        raise Refused(f"fps {a['fps']} out of range 1..60: pass fps between 1 and 60")
    if w is None or h is None or w % 2 or h % 2 or not 16 <= w <= 3840 or not 16 <= h <= 2160:
        raise Refused(f"size {a['width']}x{a['height']}: width and height must be even, 16..3840 x 16..2160")
    if a["duration_s"] is not None:
        _duration(a["duration_s"])
    if not isinstance(a["formats"], list) or not a["formats"] or not all(isinstance(f, str) for f in a["formats"]) or not set(a["formats"]) <= set(E.FORMATS) or len(set(a["formats"])) != len(a["formats"]):
        raise Refused(f"formats {a['formats']}: pass a non-empty subset of {list(E.FORMATS)}")
    if a["samples"] is not None:
        s = a["samples"]
        if not isinstance(s, list) or not s or len(s) > MAX_SAMPLES or not all(isinstance(x, (int, float)) and not isinstance(x, bool) and x >= 0 for x in s):
            raise Refused(f"samples: pass 1 to {MAX_SAMPLES} times in seconds (>= 0) to self-check, or none for {DEFAULT_SAMPLES} evenly spaced plus the first and last frame")
    if a["name"] is not None and not (isinstance(a["name"], str) and KEBAB.match(a["name"])):
        raise Refused(f"name {a['name']!r} is not kebab-case: pass a name of a-z, 0-9 and single hyphens")
    if a["html"] is not None and not a["name"]:
        raise Refused("html needs a name: pass name (the scene is written to motion/scenes/<name>/index.html)")
    if a["html"] is None and not a["scene"]:
        raise Refused("pass scene (a project-relative folder) or html (a single-file scene) with a name")
    return a


def _duration(d) -> float:
    if isinstance(d, bool) or not isinstance(d, (int, float)) or not 0 < d <= 120:
        raise Refused(f"duration {d:g} s out of range (0, 120]: split the video or shorten the scene" if isinstance(d, (int, float)) and not isinstance(d, bool)
                      else f"duration {d!r} out of range (0, 120]: split the video or shorten the scene")
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
        entry = d / "index.html"
        if entry.is_symlink():
            raise Refused("inline scene entry is a symlink: use a regular index.html in the scene folder")
        data = str(a["html"]).encode("utf-8")
        if entry.exists() and entry.read_bytes() != data:
            raise Refused(f"{rel}/index.html exists and differs: pass a new name, or render the folder with scene")
        d.mkdir(parents=True, exist_ok=True)
        entry.write_bytes(data)
        a = dict(a, entry="index.html")
    else:
        rel = str(a["scene"]).rstrip("/")
        d = _jail(root, rel)
    entry = d / a["entry"]
    if not d.is_dir() or not entry.is_file() or d not in entry.resolve().parents:
        raise Refused(f"no scene entry {a['entry']} in {rel}: pass entry")
    return d, entry, rel


def _sample_frames(n: int, samples, fps: int) -> list:
    if samples:
        return sorted({min(n - 1, int(round(float(s) * fps))) for s in samples})
    return sorted({0, n - 1} | {int(round(k * (n - 1) / (DEFAULT_SAMPLES + 1))) for k in range(1, DEFAULT_SAMPLES + 1)})


def _probe_frames(n: int) -> list:
    return sorted({int(round(k * (n - 1) / (PROBE_FRAMES - 1))) for k in range(PROBE_FRAMES)}) if n > 1 else [0]


def _pixels(png: bytes):
    im = Image.open(io.BytesIO(png))
    return im.size, hashlib.sha256(im.convert("RGB").tobytes()).hexdigest()


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
        raise Refused("the scene does not define window.__frame: see the scene contract in motion_graphics.md section 4")
    ready = capture.setup() or {}
    misses = [f.get("font") for f in ready.get("fonts") or [] if not f.get("ok")] + [i.get("src") for i in ready.get("images") or [] if not i.get("ok")]
    if misses:
        raise Refused(f"scene not ready, these did not load: {misses}: put them in the scene folder and check the paths")
    if capture.animations():
        raise Refused("the scene runs CSS animations or transitions (document.getAnimations() is not empty): drive them from __frame(t)")


def _probe(new_capture, entry, W, H, fps, rows, probe, samples, scene_root=None) -> tuple:
    """(differing probe frames, frames rendered, seconds): a fresh browser, frames 0..max(probe) in sequence (the samples' audits at the same frames,
    as the first pass ran them), each probe frame compared exactly with the first pass."""
    t0, differ = time.monotonic(), []
    cap = new_capture()
    try:
        _ready(cap, entry, W, H, scene_root=scene_root)
        want = set(probe)
        for i in range(max(probe) + 1):
            png = cap.frame(i / fps)
            if i in samples:
                cap.audit()
            if i in want and _pixels(png)[1] != rows[i].split()[2]:
                differ.append(i)
    finally:
        cap.close()
    return differ, max(probe) + 1, round(time.monotonic() - t0, 3)


def _run(root: Path, a: dict, new_capture, out_root: Path, threads: int, engine=None, probe_on=True) -> dict:
    """One render: refusals, then the sequential pass, the probe (a fresh browser; not in verify, which is itself the full re-render), the files
    and the receipt. ``engine`` (verify) = the receipt's (chromium, ffmpeg) pair: a different engine stops the run before any frame."""
    t_start = time.monotonic()
    scene_dir, entry, scene_rel = _scene(root, a)
    E.require()
    ffmpeg = E.version()
    code_sha, files = F.scene_hash(scene_dir)
    name = a["name"] or scene_dir.name
    if not KEBAB.match(name):
        raise Refused(f"name {name!r} (the scene folder's) is not kebab-case: pass name")
    W, H, fps = a["width"], a["height"], a["fps"]
    enc = None
    capture = new_capture()
    try:
        _ready(capture, entry, W, H, engine, ffmpeg, scene_root=scene_dir)                       # inside the try: a launch that fails half way is still closed
        duration = _duration(a["duration_s"] if a["duration_s"] is not None else (capture.scene() or {}).get("duration_s"))
        n = int(round(duration * fps))
        if n < 1:
            raise Refused(f"duration {duration:g} s at {fps} fps is no frame: lengthen the scene")
        samples = set(_sample_frames(n, a["samples"], fps))
        t_setup = time.monotonic() - t_start
        # Never reuse a published directory: even identical requests own different runs.
        # Reject symlink ancestors before creating the exclusive, unpredictable directory.
        _jail(root, str(out_root))
        for parent in (out_root, *out_root.parents):
            if parent == root:
                break
            if parent.is_symlink():
                raise Refused("output directory contains a symlink: use a real directory under the project root")
        out_root.mkdir(parents=True, exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix=f"{name}-{code_sha[:8]}-", dir=out_root))
        out_rel = out.relative_to(root).as_posix()
        (out / "samples").mkdir()
        paths = {fmt: out / f"{name}.{fmt}" for fmt in E.FORMATS if fmt in a["formats"]}
        argv = E.argv(paths, fps, threads)
        enc = E.Encoder(argv)
        rows, checks, t_cap = [], [], 0.0
        t_loop = time.monotonic()
        for i in range(n):
            t = i / fps
            c0 = time.monotonic()
            png = capture.frame(t)
            t_cap += time.monotonic() - c0
            size, pix = _pixels(png)
            if size != (W, H):
                raise Refused(f"frame {i} is {size[0]}x{size[1]}, not {W}x{H}: the scene must not resize the page")
            rows.append(R.row(i, t, pix))
            enc.write(png)
            if i in samples:
                audit = capture.audit() or {}
                im, stats = C.frame_stats(png)
                found = C.findings(im, stats, audit, W, H)
                stem = f"f{i:04d}"
                (out / "samples" / f"{stem}.png").write_bytes(png)
                (out / "samples" / f"{stem}.json").write_text(json.dumps({"frame": i, "t": t, "stats": stats, "audit": audit, "findings": found}, indent=1), encoding="utf-8")
                checks.append({"frame": i, "t": round(t, 4), "stats": stats, "findings": found})
        t_render = time.monotonic() - t_loop
        e0 = time.monotonic()
        enc.finish()
        t_encode_tail = time.monotonic() - e0
        enc = None
        requests = capture.requests()
    finally:
        if enc is not None:
            enc.abort()
        capture.close()
    probe, differ, probe_frames, t_probe = _probe_frames(n), [], 0, 0.0
    if probe_on:                                                           # the scene must be a pure function of t: a fresh browser agrees
        differ, probe_frames, t_probe = _probe(new_capture, entry, W, H, fps, rows, probe, samples, scene_root=scene_dir)
    (out / "frames.sha256").write_text(R.frames_text(rows), encoding="utf-8")
    digest = R.digest(rows)
    C.contact_sheet(out / "samples", out / "contact.png")
    findings = [{"frame": c["frame"], **f} for c in checks for f in c["findings"]]
    findings += [{"frame": i, "check": "determinism", "severity": "fail", "detail": f"the scene is not a pure function of t: frame {i} differs on a second capture"} for i in differ]
    non_file = [u for u in requests if not u.startswith(NETWORK_OK)]
    outputs = {fmt: {"sha256": F.sha256_file(p), "bytes": p.stat().st_size, "probe": E.probe(p)} for fmt, p in paths.items()}
    wall = time.monotonic() - t_start
    fail = sum(1 for f in findings if f["severity"] == "fail")
    warn = sum(1 for f in findings if f["severity"] == "warn")
    ok = fail == 0 and not non_file
    run_id = f"mg-{out.name}"
    files_out = {fmt: f"{out_rel}/{p.name}" for fmt, p in paths.items()}
    files_out.update(contact=f"{out_rel}/contact.png", receipt=f"{out_rel}/receipt.json", frames=f"{out_rel}/frames.sha256")
    receipt = {
        "ok": ok, "tool": "motion_graphics", "run_id": run_id, "out_dir": out_rel, "files": files_out,
        "inputs": {"scene": scene_rel, "entry": a["entry"] if a["html"] is None else "index.html", "name": name, "fps": fps, "width": W, "height": H,
                   "duration_s": duration, "formats": [f for f in E.FORMATS if f in a["formats"]], "samples": a["samples"], "template": a["template"],
                   "variables": a["variables"]},
        "frames": n, "code_sha256": code_sha, "scene_files": [{"path": p, "sha256": d} for p, d in files],
        "engine": {"chromium": capture.product, "chrome_flags": list(capture.flags), "ffmpeg": ffmpeg,
                   "encoder": {"threads": threads, "args": E.receipt_args(argv)}, "driver_sha256": F.sha256_file(F.__file__)},
        "frames_sha256_digest": digest, "frame_hash": R.FRAME_HASH,
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
    (out / "receipt.json").write_text(json.dumps(receipt, indent=1), encoding="utf-8")
    return receipt


def summary(receipt: dict) -> dict:
    """The tool's answer (section 5) from a receipt."""
    out = {"ok": receipt["ok"], "run_id": receipt["run_id"], "out_dir": receipt["out_dir"],
           "files": {k: v for k, v in receipt["files"].items() if k in ("mp4", "webm", "contact")}, "code_sha256": receipt["code_sha256"],
           "frames": receipt["frames"], "frames_sha256_digest": receipt["frames_sha256_digest"],
           "outputs": {k: {"sha256": v["sha256"], "bytes": v["bytes"]} for k, v in receipt["outputs"].items()},
           "self_check": {k: receipt["self_check"][k] for k in ("fail", "warn", "findings")}, "network": receipt["network"],
           "timing_s": {k: receipt["timing_s"][k] for k in ("wall", "wall_per_video_second", "capture_ms_per_frame")}}
    if receipt.get("error"):
        out["error"] = receipt["error"]
    return out


def render(project_root, args: dict, new_capture, threads: int = E.THREADS) -> dict:
    root = Path(project_root)
    a = inputs(args)
    return summary(_run(root, a, new_capture, root / "motion" / "out", threads))


def verify(project_root, args: dict, new_capture) -> dict:
    """Re-render a receipt's inputs from frame 0 in a fresh browser; compare every frame hash and both files. A different Chromium or ffmpeg is
    answered with engine_matches false and no frame comparison."""
    root = Path(project_root)
    rel = (args or {}).get("receipt")
    if not rel:
        raise Refused("verify needs receipt: the project-relative path of a render's receipt.json")
    path = _jail(root, rel)
    if not path.is_file():
        raise Refused(f"no receipt at {rel}: pass the receipt.json of a render")
    r = json.loads(path.read_text(encoding="utf-8"))
    i = r["inputs"]
    a = inputs({k: i[k] for k in ("scene", "entry", "name", "fps", "width", "height", "duration_s", "formats", "samples")})
    work = root / "motion" / "out" / f".verify-{time.monotonic_ns()}"
    try:
        try:
            new = _run(root, a, new_capture, work, int(r["engine"]["encoder"]["threads"]), engine=(r["engine"]["chromium"], r["engine"]["ffmpeg"]),
                       probe_on=False)
        except EngineDiffers as exc:
            return {"reproduced": False, "frames_differing": [], "mp4_equal": False, "webm_equal": False, "engine_matches": False, "error": str(exc)}
        old_rows = R.read_rows(root / r["out_dir"] / "frames.sha256")
        new_rows = R.read_rows(root / new["out_dir"] / "frames.sha256")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    differ = R.differing(old_rows, new_rows)
    eq = {f"{fmt}_equal": (r["outputs"].get(fmt) or {}).get("sha256") == (new["outputs"].get(fmt) or {}).get("sha256") if fmt in r["outputs"] else None
          for fmt in E.FORMATS}
    reproduced = not differ and all(v for v in eq.values() if v is not None) and new["frames_sha256_digest"] == r["frames_sha256_digest"]
    return {"reproduced": reproduced, "frames_differing": differ, **eq, "engine_matches": True, "receipt": rel, "frames": new["frames"]}
