# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The receipt, the per-frame hashes and the Vault filing (motion_graphics.md section 5).

``frames.sha256`` holds one ``index t sha256`` row per frame, the hash taken over the decoded RGB pixels; ``frames_sha256_digest`` is the sha256 of
that file. Frame hashes are the proof, not output hashes: in the spike a pair whose WebM hashes matched differed in one frame. Paths in a receipt are
relative (no home paths)."""
import hashlib
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


def file_in_vault(vault, project_root: Path, receipt: dict, prompt_text=None) -> dict:
    """ONE ``provenance.capture`` call with the MP4 (kind video, subtype render, role main), the WebM (kind video), the receipt (kind receipt,
    subtype qa) and the contact sheet (kind image, subtype strip); then ``curate.relate``: WebM variant_of MP4, receipt and contact sheet
    derived_from MP4. ``capture`` never raises and spools when the library is locked; a spooled filing carries no relations (they need the ids)."""
    from ..library import curate as CU
    from ..library import provenance as PV
    from ..library.store import LibraryError
    out_dir = Path(project_root) / receipt["out_dir"]
    files, name = receipt["files"], receipt["inputs"]["name"]
    outputs, formats = [], []
    for fmt in ("mp4", "webm"):
        if fmt in files:
            o = {"path": str(Path(project_root) / files[fmt]), "kind": "video", "name": f"{name}.{fmt}"}
            if fmt == "mp4":
                o.update(subtype="render", role="main")
            outputs.append(o)
            formats.append(fmt)
    outputs.append({"path": str(out_dir / "receipt.json"), "kind": "receipt", "subtype": "qa", "name": f"{name} receipt"})
    formats.append("receipt")
    outputs.append({"path": str(Path(project_root) / files["contact"]), "kind": "image", "subtype": "strip", "name": f"{name} contact sheet"})
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
    res = PV.capture(lib, vault.spool, {"generation": gen, "outputs": outputs, "tool": "motion_graphics"})
    if not res.get("ok"):
        return {"assets": [], "spooled": bool(res.get("spooled")), "filed": False, "error": res.get("error")}
    assets = [{"id": a["id"], "kind": o["kind"], "format": f} for a, o, f in zip(res["assets"], outputs, formats)]
    by = {a["format"]: a["id"] for a in assets}
    if "mp4" in by:
        if "webm" in by:
            CU.relate(lib, by["webm"], "variant_of", by["mp4"], by="rule")
        CU.relate(lib, by["receipt"], "derived_from", by["mp4"], by="rule")
        CU.relate(lib, by["contact"], "derived_from", by["mp4"], by="rule")
    return {"assets": assets, "spooled": False, "filed": True}
