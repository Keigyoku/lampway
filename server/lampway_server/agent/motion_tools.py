# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The agent's motion-graphics tool (specs/motion_graphics/motion_graphics.md): ``lampway_motion_graphics`` renders scene code to MP4 and WebM
frame by frame in a headless Chromium, self-checks it, writes a receipt and files an accepted render in the Asset Vault; ``verify`` re-renders a
receipt and proves it reproduces. It runs here on the server (never in Blender), spends nothing and sends nothing: the long work runs in a thread
and the call returns the paths. It is not a job service: the job registry takes only the Mixar client's wire job types."""
import asyncio
import json
from pathlib import Path

from .. import config
from .. import motion as M
from ..motion import encode as E
from ..motion import frames as F
from ..motion import receipt as R
from ..motion.cancellation import Cancellation, MotionCancelled, checkpoint
from .providers.base import ToolSpec

NAME = "lampway_motion_graphics"
NAMES = {NAME}

_S, _I, _N, _B, _O = {"type": "string"}, {"type": "integer"}, {"type": "number"}, {"type": "boolean"}, {"type": "object"}
SPEC = ToolSpec(NAME, (
    "Render a video from scene CODE (HTML with Canvas, SVG, CSS or three.js) frame by frame in a headless Chromium (t = i / fps, never real time, in "
    "order from frame 0), encode it to MP4 and WebM, self-check sampled frames (empty frame, text outside title-safe, text under 22 px, contrast, "
    "text over a figure or card, a mark cut by the edge, and a fresh browser re-rendering sequentially from frame 0 to compare sampled frame hashes), "
    "write a receipt (code hash, "
    "every frame's hash, output hashes) under motion/out/<name>-<code8>-<unique-run>/, and file an accepted render in the Asset Vault as kind video. Look at "
    "contact.png yourself: some defects only an eye sees. The scene contract: window.__scene = {duration_s, width, height}; await window.__setup() "
    'loads every font and image, then returns both required arrays. Setup return example: {"fonts":[{"font":"28px sans-serif","ok":true}],'
    '"images":[{"src":"assets/figure.png","ok":true}]}. Resource identifiers are non-empty strings; ok is a boolean. '
    'Empty-resource setup: {"fonts":[],"images":[]} is appropriate when none are needed. '
    'window.__frame(t) sets every animated property from t alone. window.__audit() returns both arrays for all visible text and marks. '
    'Audit return example: {"text":[{"sel":"#title","text":"Title","box":[100,100,500,160],"font_px":28,"opacity":1}],'
    '"marks":[{"sel":"figure","box":[600,200,1000,700]}]}. Each row needs a non-empty sel and box=[x0,y0,x1,y1] '
    'with finite ordered viewport coordinates. Text additionally needs string text, positive finite font_px and finite opacity in [0,1]; '
    'marks require sel and box. Empty audit: {"text":[],"marks":[]} is appropriate only when none are visible. '
    "No Date, performance.now, Math.random, requestAnimationFrame, CSS animations or transitions; every file lives in the scene "
    "folder (a network request fails the render). A failing self-check writes the files, returns ok false and files nothing. action verify "
    "re-renders a receipt and reports reproduced, frame/output equality and engine_matches separately from integrity_matches (checked existing requested-media bytes) and provenance_matches (source, driver and flags). Corrupt or missing media can still reproduce from a trusted receipt; inspect all three statuses. Caller cancellation joins owned workers/processes, blocks new filing and reports committed assets; retained evidence is preserved. Refuses: fps outside 1..60, an odd "
    "or out-of-range size, a duration outside (0, 120], a path outside the project, a missing entry, no headless Chromium (set LAMPWAY_CHROMIUM), "
    "no ffmpeg, a scene without __frame, a setup miss, CSS animations, a page resize. Spends nothing; nothing leaves the machine."),
    {"type": "object", "additionalProperties": False, "required": [], "properties": {
        "action": {**_S, "enum": ["render", "verify"], "description": "render (default) or verify (re-render a receipt and compare)"},
        "scene": {**_S, "description": "render: the scene folder, project-relative (e.g. motion/scenes/spend-gate)"},
        "html": {**_S, "description": "render: a single-file scene instead of a folder; written to motion/scenes/<name>/index.html first (needs name)"},
        "entry": {**_S, "description": "the scene's HTML entry inside its folder (default index.html)"},
        "name": {**_S, "description": "kebab-case output name (default: the scene folder's name); outputs go to motion/out/<name>-<code8>-<unique-run>/"},
        "duration_s": {**_N, "exclusiveMinimum": 0, "maximum": 120, "description": "seconds, (0, 120]; default: the scene's own window.__scene.duration_s"},
        "fps": {**_I, "minimum": 1, "maximum": 60, "description": "frames per second, 1..60 (default 30)"},
        "width": {**_I, "minimum": 16, "maximum": 3840, "description": "even, 16..3840 (default 1920)"},
        "height": {**_I, "minimum": 16, "maximum": 2160, "description": "even, 16..2160 (default 1080)"},
        "formats": {"type": "array", "items": {**_S, "enum": list(E.FORMATS)}, "description": "a non-empty subset of mp4, webm (default both)"},
        "samples": {"type": "array", "items": {**_N, "minimum": 0}, "maxItems": M.MAX_SAMPLES,
                    "description": "seconds to self-check, at most 24 (default: 10 evenly spaced plus the first and last frame)"},
        "template": {**_S, "description": "provenance only: the motion-graphics prompt template id@version the scene was written from"},
        "variables": {**_O, "description": "provenance only: that template's variables"},
        "vault": {**_B, "description": "file an accepted render in the Asset Vault (default true)"},
        "receipt": {**_S, "description": "verify: the project-relative path of the render's receipt.json"}}})


def specs() -> list:
    return [SPEC]


def _prompt_provenance(template, variables):
    """Rendered motion template with effective variables and resolved version, or None."""
    if not template:
        return None
    from ..prompts import library as PL
    from ..prompts import render as PR
    tid, _, version = str(template).partition("@")
    lib = PL.Library.from_env()
    t = lib.get(tid, version or None)
    if t["purpose"] != "motion-graphics":
        raise M.Refused(f"{template}: purpose is {t['purpose']}, not motion-graphics: choose a motion-graphics template")
    return PR.render(lib, tid, variables or {}, version=t["version"])


def _capture():
    return F.Chromium(F.chromium_binary(), config.state_dir() / "motion" / "chromium-home")


def _work(vault, root: Path, a: dict, new_capture, cancel=None):
    checkpoint(cancel)
    if new_capture is None:
        F.chromium_binary()                                                # refuse before anything is written when there is no browser
        new_capture = _capture
    if a["action"] == "verify":
        return M.verify(root, {key: value for key, value in a.items() if value is not None}, new_capture, cancel=cancel)
    prompt = _prompt_provenance(a["template"], a["variables"])
    if prompt is not None:
        a = dict(a, template=prompt["template"], variables=prompt["variables"])
    E.require()
    checkpoint(cancel)
    bundle = {}

    def handoff(receipt, pinned_out):
        if receipt["ok"] and a.get("vault", True) is not False and vault is not None:
            bundle.update(R.seal(receipt, pinned_out, root, cancel=cancel))

    out = M.render(root, {key: value for key, value in a.items() if value is not None}, new_capture, cancel=cancel, handoff=handoff)
    checkpoint(cancel)
    filed = {"assets": [], "spooled": False, "filed": False}
    if out["ok"] and a.get("vault", True) is not False and vault is not None:
        checkpoint(cancel)
        filed = R.file_in_vault(vault, root, bundle["receipt"], prompt_text=prompt["prompt"] if prompt else None, sealed=bundle, cancel=cancel)
    if cancel is not None:
        cancel.record_filing(filed)
    checkpoint(cancel)
    out["vault"] = filed
    return out


async def call(vault, project_root, name: str, arguments: dict, capture=None) -> tuple:
    """(JSON text, is_error). ``capture`` is a factory of fresh capture adapters (the tests' fake); by default the user's headless Chromium."""
    if name != NAME:
        return json.dumps({"ok": False, "error": f"unknown tool {name!r}"}), True
    root = Path(project_root)
    try:
        a = M.inputs(arguments)
        cancel = Cancellation()
        worker = asyncio.create_task(asyncio.to_thread(_work, vault, root, a, capture, cancel))
        try:
            out = await asyncio.shield(worker)
        except asyncio.CancelledError:
            cancel.cancel()
            # Shield keeps the thread tracked; repeated caller cancellation cannot abandon its owned cleanup.
            while not worker.done():
                try:
                    await asyncio.shield(worker)
                except asyncio.CancelledError:
                    cancel.cancel()
                except Exception:
                    break
            if worker.done():
                try:
                    worker.result()
                except Exception:
                    pass
            return json.dumps({"ok": False, "cancelled": True, "error": "motion graphics cancelled",
                               "vault": cancel.snapshot_filing()}), True
    except (MotionCancelled, M.Refused, F.ChromiumMissing, E.FfmpegMissing, F.SceneError) as exc:
        return json.dumps({"ok": False, "error": str(exc)}), True
    except Exception as exc:  # noqa: BLE001 - reported to the model
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), True
    if "reproduced" in out:
        return json.dumps(out), False
    return json.dumps(out), not out["ok"]
