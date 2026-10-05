"""The image backend behind mesh-paint texturing: N painted variants of a clay render, through a configurable backend.

* ``tripo``      the Tripo Studio driver (GPT Image 2.5, 4 images, 4K, free quota). Every setting is set and read back right
                 before Generate and the run refuses on any mismatch (incl. a price that is not free); never fewer than 4 per
                 generation; a DRY RUN unless ``live`` AND the owner's own LAMPWAY_STUDIO_ARMED=1 is set in this process.
* ``codex_cli``  `codex exec '$imagegen'` on the owner's own ChatGPT login, one image per call (the CLI makes exactly one). Off
                 unless the local-CLI setting is on; the refusal carries the terms caveat.

Backend choice: ``LAMPWAY_IMAGE_BACKEND`` (default ``tripo``). Every path an argument names stays inside the project root.
Also a command: ``python -m lampway_server.imagegen --backend tripo --prompt-file p.txt --ref clay.png --out runs/Front [--live]``.
"""

import argparse
import os
import sys
from pathlib import Path

from .agent import cli_adapters as CLI
from .agent import server_tools as ST
from .studios import axi

BACKENDS = ("tripo", "codex_cli")
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
