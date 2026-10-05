"""The image backend behind mesh-paint texturing: N painted variants of a clay render, through a configurable backend.

* ``tripo``      the Tripo Studio driver (GPT Image 2.5, 4 images, 4K, free quota). Every setting is set and read back right
                 before Generate and the run refuses on any mismatch (incl. a price that is not free); never fewer than 4 per
                 generation; a DRY RUN unless ``live`` AND the owner's own LAMPWAY_STUDIO_ARMED=1 is set in this process.
* ``codex_cli``  `codex exec '$imagegen'` on the owner's own ChatGPT login, one image per call (the CLI makes exactly one). Off
                 unless the local-CLI setting is on; the refusal carries the terms caveat.

* ``openrouter`` an OpenRouter image model (default ``google/gemini-3.1-flash-image``: text + reference images in, one image per
                 call) over POST /api/v1/images. Dry run unless ``live``; live needs the OpenRouter key, counts against the SAME
                 session spend ceiling as the chat models, and is refused before sending once that ceiling is reached.

Backend choice: ``LAMPWAY_IMAGE_BACKEND`` (default ``tripo``). Every path an argument names stays inside the project root.
Also a command: ``python -m lampway_server.imagegen --backend tripo --prompt-file p.txt --ref clay.png --out runs/Front [--live]``.
"""

import argparse
import base64
import mimetypes
import os
import sys
from pathlib import Path

from .agent import cli_adapters as CLI
from .agent import server_tools as ST
from .studios import axi

BACKENDS = ("tripo", "codex_cli", "openrouter")
openrouter_transport = None          # tests inject an httpx transport here; None means the real network
_IMG = (".png", ".jpg", ".jpeg", ".webp")


class ImageGenError(RuntimeError):
    pass


def backend_name() -> str:
    name = os.environ.get("LAMPWAY_IMAGE_BACKEND", "tripo")
    if name not in BACKENDS:
        raise ValueError(f"unknown image backend {name!r}; the backends are {', '.join(BACKENDS)}")
    return name


def _state_dir() -> Path:
    return Path(os.environ.get("LAMPWAY_STATE_DIR") or Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "lampway-server")


def _images(out: Path) -> list:
    return sorted(str(p) for p in out.glob("*") if p.suffix.lower() in _IMG and p.stem.isdigit()) if out.exists() else []


def generate(backend: str, prompt_file: str, refs, out_dir: str, count: int = 4, live: bool = False) -> dict:
    """Returns {backend, files, dry_run, output}. ``refs`` in order: the clay render first, then any painted consistency view,
    then the design plate (the prompts name them first / second / third)."""
    if backend not in BACKENDS:
        raise ValueError(f"unknown image backend {backend!r}; the backends are {', '.join(BACKENDS)}")
    prompt_path = ST.jail(prompt_file)
    ref_paths = [ST.jail(r) for r in refs]
    out = ST.jail(out_dir)
    if backend == "openrouter":
        return _openrouter(prompt_path, ref_paths, Path(out), int(count), live)
    if backend == "tripo":
        cmd = ST.command("studio_tripo_image", {"out_dir": out_dir, "prompt_file": prompt_file, "refs": list(refs),
                                                "count": str(count), "dry_run": not live})
        rc, text = ST._exec(cmd, ST.environment(), 900.0)
        if rc != 0:
            raise ImageGenError(f"the Tripo driver refused or failed: {text.strip()[-600:]}")
        return {"backend": "tripo", "files": _images(Path(out)) if live else [], "dry_run": not live, "output": text}
    CLI.require_enabled(_state_dir())
    prompt = Path(prompt_path).read_text(encoding="utf-8").strip()
    binary = os.environ.get("LAMPWAY_CODEX_BIN", "codex")
    files = []
    for i in range(1, int(count) + 1):
        try:
            res = CLI.codex_image(binary, prompt, ref_paths, out, name=str(i))
        except CLI.CLIError as exc:
            raise ImageGenError(f"codex made {len(files)} of {count} images, then failed: {exc}") from exc
        files.append(res["file"])
    return {"backend": "codex_cli", "files": files, "dry_run": False, "output": f"{len(files)} image(s) through codex $imagegen"}


def _openrouter(prompt_path: str, ref_paths: list, out: Path, count: int, live: bool) -> dict:
    import httpx
    from .agent.providers import spend_ledger
    from .agent.providers.openrouter import BASE_URL, REFERER, TITLE, redact, resolve_api_key
    from .config import Settings
    if not 1 <= count <= 4:
        raise ValueError("the openrouter backend makes at most 4 images per generation (one request each)")
    settings = Settings.from_env()
    model = settings.openrouter_image_model
    if not live:
        return {"backend": "openrouter", "files": [], "dry_run": True,
                "output": f"dry run: would send {count} request(s) to {model} with {len(ref_paths)} reference image(s); nothing sent"}
    prompt = Path(prompt_path).read_text(encoding="utf-8").strip()
    refs = []
    for path in ref_paths:
        mime = mimetypes.guess_type(path)[0] or "image/png"
        refs.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64," + base64.b64encode(Path(path).read_bytes()).decode()}})
    key = resolve_api_key()
    ledger = spend_ledger(settings)
    out.mkdir(parents=True, exist_ok=True)
    files = []
    with httpx.Client(transport=openrouter_transport, timeout=300.0) as client:
        for i in range(1, count + 1):
            ledger.check()
            body = {"model": model, "prompt": prompt}
            if refs:
                body["input_references"] = refs
            resp = client.post(f"{BASE_URL}/images", json=body, headers={
                "Authorization": f"Bearer {key}", "HTTP-Referer": REFERER, "X-Title": TITLE})
            if resp.status_code >= 400:
                raise ImageGenError(redact(f"OpenRouter answered HTTP {resp.status_code} for image {i}: {resp.text[:400]}", key))
            data = resp.json()
            cost = (data.get("usage") or {}).get("cost")
            if isinstance(cost, (int, float)):
                ledger.add(cost, "image")
            items = data.get("data") or []
            if not items or not items[0].get("b64_json"):
                raise ImageGenError(f"OpenRouter returned no image for request {i}")
            ext = {"image/jpeg": ".jpg", "image/webp": ".webp"}.get(items[0].get("media_type"), ".png")
            target = out / f"{i}{ext}"
            target.write_bytes(base64.b64decode(items[0]["b64_json"]))
            files.append(str(target))
    return {"backend": "openrouter", "files": files, "dry_run": False,
            "output": f"{len(files)} image(s) from {model}; session spend ${ledger.spent:.4f} of ${ledger.ceiling_usd:.2f}"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="imagegen", description="Painted variants of a clay render through a configurable image backend (AXI).")
    ap.add_argument("--backend", default=None)
    ap.add_argument("--prompt-file", required=True)
    ap.add_argument("--ref", action="append", default=[])
    ap.add_argument("--out", required=True)
    ap.add_argument("--count", type=int, default=4)
    ap.add_argument("--live", action="store_true", help="really generate (tripo also needs LAMPWAY_STUDIO_ARMED=1)")
    a = ap.parse_args(argv)
    try:
        res = generate(a.backend or backend_name(), a.prompt_file, a.ref, a.out, a.count, a.live)
    except (ImageGenError, ValueError) as exc:
        print(f"error: {exc}")
        return 1
    axi.kv({"backend": res["backend"], "dry_run": res["dry_run"], "images": len(res["files"])})
    axi.table("files", [{"file": f} for f in res["files"]], ["file"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
