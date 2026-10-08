# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The receipt, the per-frame hashes and the Vault filing (motion_graphics.md section 5).

``frames.sha256`` holds one ``index t sha256`` row per frame, the hash taken over the decoded RGB pixels; ``frames_sha256_digest`` is the sha256 of
that file. Frame hashes are the proof, not output hashes: in the spike a pair whose WebM hashes matched differed in one frame. Paths in a receipt are
relative (no home paths)."""
import hashlib
import json
from pathlib import Path

FRAME_HASH = "sha256 of the decoded RGB pixels of each captured frame"


def row(i: int, t: float, pixels_sha256: str) -> str:
    return f"{i:05d} {t:.6f} {pixels_sha256}"


def frames_text(rows: list) -> str:
    return "\n".join(rows) + "\n"


def digest(rows: list) -> str:
    return hashlib.sha256(frames_text(rows).encode()).hexdigest()


def read_rows(path) -> list:
    return [l for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def differing(a: list, b: list) -> list:
    """Indices whose rows differ (a frame missing on one side counts)."""
    n = max(len(a), len(b))
    return [i for i in range(n) if (a[i] if i < len(a) else None) != (b[i] if i < len(b) else None)]


def seal(receipt: dict, out: Path, project_root: Path, *, cancel=None) -> dict:
    """Copy checked render artifacts while its pinned directory is alive; later filing uses only these bytes."""
    from . import frames as F
    root = Path(project_root).resolve()
    trusted = json.loads(json.dumps(receipt))
    copied = {}
    for fmt in ("mp4", "webm", "receipt", "contact"):
        if cancel is not None:
            cancel.check()
        if fmt not in trusted["files"]:
            continue
        path = Path(out) / Path(trusted["files"][fmt]).name
        with F._open_scene_file(path, root) as source:
            data = source.read()
        if cancel is not None:
            cancel.check()
        if fmt in ("mp4", "webm") and hashlib.sha256(data).hexdigest() != trusted["outputs"][fmt]["sha256"]:
            raise F.SceneError(f"{fmt} changed before Vault sealing: render again")
        if fmt == "contact" and hashlib.sha256(data).hexdigest() != (trusted.get("artifact_hashes") or {}).get("contact"):
            raise F.SceneError("contact sheet changed or lacks a trusted generation hash: render again before Vault filing")
        if fmt == "receipt" and json.loads(data) != trusted:
            raise F.SceneError("receipt changed before Vault sealing: render again")
        copied[fmt] = data
    return {"receipt": trusted, "files": copied}


def file_in_vault(vault, project_root: Path, receipt: dict, prompt_text=None, *, sealed=None, cancel=None) -> dict:
    """ONE ``provenance.capture`` call: MP4 (or WebM when alone) is the primary video render, plus the QA receipt and image strip.
    Relationship intents travel with the capture and spool, so replay completes an interrupted filing. Sealed bytes are never reopened."""
    from ..library import provenance as PV
    from ..library.store import LibraryError
    out_dir = Path(project_root) / receipt["out_dir"]
    sealed = sealed or seal(receipt, out_dir, project_root, cancel=cancel)
    receipt = sealed["receipt"]
    files, name = receipt["files"], receipt["inputs"]["name"]
    outputs, formats = [], []
    primary = "mp4" if "mp4" in files else "webm"
    for fmt in ("mp4", "webm"):
        if fmt in files:
            o = {"bytes": sealed["files"][fmt], "kind": "video", "name": f"{name}.{fmt}"}
            if fmt == primary:
                o.update(subtype="render", role="main")
            outputs.append(o)
            formats.append(fmt)
    outputs.append({"bytes": sealed["files"]["receipt"], "kind": "receipt", "subtype": "qa", "name": f"{name} receipt"})
    formats.append("receipt")
    outputs.append({"bytes": sealed["files"]["contact"], "kind": "image", "subtype": "strip", "name": f"{name} contact sheet"})
    formats.append("contact")
    inputs, engine = receipt["inputs"], receipt["engine"]
    template = inputs.get("template") or ""
    tid, _, tver = template.partition("@")
    gen = {"studio": "lampway", "provider": "local", "model": f"{engine['chromium']} + {engine['ffmpeg']}", "action": "motion_graphics",
           "job_id": receipt["run_id"], "cost_basis": "none", "template_id": tid or None, "template_version": tver or None, "vars": inputs.get("variables") or {},
           "prompt_text": prompt_text,
           "params": {"code_sha256": receipt["code_sha256"], "frames_sha256_digest": receipt["frames_sha256_digest"], "fps": inputs["fps"],
                      "width": inputs["width"], "height": inputs["height"], "duration_s": inputs["duration_s"], "encoder": engine["encoder"]}}
    try:
        lib = vault.lib
    except LibraryError:
        lib = None
    relationships = [{"src": i, "dst": formats.index(primary), "type": "variant_of" if fmt in ("mp4", "webm") else "derived_from"}
                     for i, fmt in enumerate(formats) if fmt != primary]
    if cancel is not None:
        cancel.check()
    res = PV.capture(lib, vault.spool, {"generation": gen, "outputs": outputs, "tool": "motion_graphics", "output_relations": relationships}, cancel=cancel)
    assets = [{"id": a["id"], "kind": o["kind"], "format": f} for a, o, f in zip(res.get("assets", []), outputs, formats)]
    if not res.get("ok"):
        return {"assets": assets, "spooled": bool(res.get("spooled")), "filed": False, "partial": bool(assets), "error": res.get("error")}
    return {"assets": assets, "spooled": False, "filed": True}
