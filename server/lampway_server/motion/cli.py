# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""`python -m lampway_server.motion`: the motion-graphics AXI CLI, a thin layer over the agent tool's ``_work`` (the same checks, the same
receipt, the same Vault filing). AXI principles (the shelf's tools/AXI.md, as in compute/cli.py): argparse, a live no-args view, TOON
summaries through compute/toon_out.py with minimal default fields (``--full`` for the rest), counts and explicit empties, a ``help[]`` of next
steps after every output, structured errors on stdout (exit 1 refused or failed, 2 usage), no interactive prompts, unknown flags fail loud."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .. import motion as M
from ..agent import motion_tools as MT
from ..compute import toon_out as T
from . import encode as E
from . import frames as F

PROG = "python -m lampway_server.motion"
DESCRIPTION = "Render scene code to MP4 and WebM frame by frame in a headless Chromium, self-check it and write a receipt; verify re-renders a receipt."
SHOWN = 10                                                          # list rows shown by default; --full shows every row


class UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


@dataclass
class Context:
    root: Path
    state: Path
    capture: Optional[Callable] = None                              # a factory of fresh capture adapters (the tests' fake); default: headless Chromium
    vault_factory: Optional[Callable] = None


def default_context() -> Context:
    from ..config import state_dir
    return Context(Path(os.environ.get("LAMPWAY_PROJECT_ROOT") or Path.cwd()), state_dir())


def _parser() -> _Parser:
    p = _Parser(prog=PROG, description=DESCRIPTION, add_help=True)
    sub = p.add_subparsers(dest="cmd")
    r = sub.add_parser("render", help="render a scene folder, self-check it, write a receipt and file it in the Vault")
    r.add_argument("--scene", required=True, help="the scene folder, project-relative (motion/scenes/<name>)")
    r.add_argument("--width", type=int)
    r.add_argument("--height", type=int)
    r.add_argument("--fps", type=int)
    r.add_argument("--duration", type=float, help="seconds; default: the template's, then window.__scene.duration_s")
    r.add_argument("--audit-every", type=float, metavar="SECONDS", help="also audit every SECONDS into audit.jsonl (no PNGs)")
    r.add_argument("--safe-zone", metavar="X0,Y0,X1,Y1", help="fractions of the frame text must stay inside, e.g. 0.05,0.12,0.95,0.8")
    r.add_argument("--template", help="a motion-graphics template id@version (provenance and defaults)")
    r.add_argument("--var", action="append", default=[], metavar="KEY=VALUE", help="a template variable (repeatable; a value that parses as JSON is JSON)")
    r.add_argument("--no-vault", action="store_true", help="do not file the render in the Asset Vault")
    r.add_argument("--full", action="store_true", help="every field and row")
    v = sub.add_parser("verify", help="re-render a receipt and compare frames, outputs, integrity and provenance")
    v.add_argument("--receipt", required=True, help="the render's receipt.json, project-relative")
    v.add_argument("--full", action="store_true", help="every field and row")
    return p


def _bin() -> str:
    exe, home = os.path.abspath(sys.executable), os.path.abspath(os.path.expanduser("~"))       # abspath, not realpath: keep the venv
    return f"{'~' + exe[len(home):] if exe.startswith(home + os.sep) else exe} -m lampway_server.motion"


def _rows(name: str, rows: list, full: bool, unit: str) -> dict:
    """A list field: every row with --full, else the first SHOWN with a count; an empty list is an explicit '0 <unit>'."""
    if not rows:
        return {name: f"0 {unit}"}
    if full or len(rows) <= SHOWN:
        return {name: rows}
    return {f"{name}_shown": f"{SHOWN} of {len(rows)} (--full for all)", name: rows[:SHOWN]}


def _home(ctx: Context) -> tuple:
    root = Path(ctx.root)
    scenes_dir, out_dir = root / "motion" / "scenes", root / "motion" / "out"
    scenes = sorted(d.name for d in scenes_dir.iterdir() if d.is_dir()) if scenes_dir.is_dir() else []
    runs = []
    for d in sorted(out_dir.iterdir(), key=lambda p: p.stat().st_mtime) if out_dir.is_dir() else []:
        try:
            r = json.loads((d / "receipt.json").read_text(encoding="utf-8"))
            runs.append({"run_id": r["run_id"], "ok": bool(r["ok"]), "warn": int(r["self_check"]["warn"])})
        except (OSError, ValueError, KeyError, TypeError):
            continue                                                 # not a finished run (a verify work folder, a partial write)
    view = {"bin": _bin(), "description": DESCRIPTION, "project": str(root)}
    view.update({"scenes": [{"name": n} for n in scenes]} if scenes else {"scenes": "0 scenes"})
    if len(runs) > SHOWN:
        view["runs_shown"] = f"newest {SHOWN} of {len(runs)}"
    view.update({"runs": runs[-SHOWN:]} if runs else {"runs": "0 runs"})
    helps = [f"{PROG} render --scene motion/scenes/{scenes[0] if scenes else '<name>'}: render it (a folder with index.html and its files)"]
    if runs:
        helps.append(f"{PROG} verify --receipt motion/out/{runs[-1]['run_id'][len('mg-'):]}/receipt.json: re-render the newest run and compare")
    return view, helps


def _zone(text):
    if text is None:
        return None
    try:
        return [float(v) for v in text.split(",")]
    except ValueError:
        raise UsageError(f"--safe-zone {text!r}: use four fractions X0,Y0,X1,Y1") from None


def _variables(pairs) -> dict:
    out = {}
    for kv in pairs:
        k, sep, v = kv.partition("=")
        if not sep or not k:
            raise UsageError(f"--var {kv!r}: use KEY=VALUE")
        try:
            out[k] = json.loads(v)
        except ValueError:
            out[k] = v
    return out


def _render_view(out: dict, full: bool) -> tuple:
    view = {"ok": out["ok"], "run_id": out["run_id"], "out_dir": out["out_dir"], "frames": out["frames"]}
    if out.get("error"):
        view["error"] = out["error"]
    view["files"] = [{"kind": k, "path": p} for k, p in out["files"].items()] + [{"kind": "receipt", "path": f"{out['out_dir']}/receipt.json"}]
    view["inputs"] = out.get("inputs") or []
    if out.get("opening_s"):
        view["opening_s"] = out["opening_s"]
    sc = out["self_check"]
    view["fail"], view["warn"] = sc["fail"], sc["warn"]
    fields = ("frame", "check", "severity", "detail") if full else ("frame", "check", "severity")
    view.update(_rows("findings", [{k: f[k] for k in fields} for f in sc["findings"]], full, "findings"))
    if out.get("warnings"):
        view["warnings"] = [{"warning": w} for w in out["warnings"]]
    filed = out.get("vault") or {}
    view["vault"] = ("filed" if filed.get("filed") else "spooled: the server files it at its next start" if filed.get("spooled")
                     else "error: " + str(filed["error"]) if filed.get("error") else "not filed")
    if full:
        view["vault_assets"] = filed.get("assets") or []
        view.update({"code_sha256": out["code_sha256"], "frames_sha256_digest": out["frames_sha256_digest"],
                     "outputs": [{"format": k, "sha256": v["sha256"], "bytes": v["bytes"]} for k, v in out["outputs"].items()],
                     "network_requests": out["network"]["requests"], "network_non_file": out["network"]["non_file"], "timing_s": out["timing_s"]})
    generic = set(M.next_steps(out))
    helps = [re.sub(r'^pass variables \{"(\w+)": "<project-relative path>"\}', r"--var \1=<project-relative path>", h)    # the agent's wording, as this CLI's flag
             for h in out.get("help") or [] if h not in generic]
    helps += [f"open {out['files']['contact']}: look at it yourself, some defects only an eye sees",
              f"{PROG} verify --receipt {out['out_dir']}/receipt.json: prove it reproduces"]
    if not full:
        helps.append("--full: every finding with its detail, the hashes, outputs and timings")
    return view, helps


def _verify_view(res: dict, full: bool) -> tuple:
    keys = ("reproduced", "frames", "mp4_equal", "webm_equal", "engine_matches", "integrity_matches", "provenance_matches", "error")
    view = {k: res[k] for k in keys if k in res}
    differ = res.get("frames_differing") or []
    view["frames_differing"] = len(differ)
    if differ:
        view.update(_rows("differing", [{"frame": i} for i in differ], full, "frames"))
    if full:
        view["integrity"], view["provenance"] = res["integrity"], res["provenance"]
    helps = [f"{PROG}: the runs"] if res["reproduced"] and res["integrity_matches"] and res["provenance_matches"] else \
        ["--full: which integrity or provenance check differs and the hashes on each side"]
    return view, helps


def main(argv=None, ctx: Optional[Context] = None, out=None) -> int:
    out, ctx = out or sys.stdout, ctx or default_context()

    def emit(obj, helps=(), rc=0):
        body = T.dumps(obj)
        if helps:
            body += ("\n" if body else "") + T.dumps({"help": list(helps)})
        print(body, file=out)
        return rc

    def fail(message, helps=(), rc=1):
        return emit({"error": message}, helps, rc)

    try:
        a = _parser().parse_args(list(argv if argv is not None else sys.argv[1:]))
        if a.cmd is None:
            return emit(*_home(ctx))
        root = Path(ctx.root)
        if a.cmd == "render":
            args = {"scene": a.scene, "width": a.width, "height": a.height, "fps": a.fps, "duration_s": a.duration, "template": a.template,
                    "variables": _variables(a.var) or None, "audit_every_s": a.audit_every, "safe_zone": _zone(a.safe_zone), "vault": False if a.no_vault else None}
        else:
            args = {"action": "verify", "receipt": a.receipt}
        inputs = M.inputs({k: v for k, v in args.items() if v is not None})
        vault = None
        if a.cmd == "render" and not a.no_vault:
            from ..library.vault import Vault
            vault = (ctx.vault_factory or (lambda: Vault(ctx.state, project_root=root)))()
        try:
            res = MT._work(vault, root, inputs, ctx.capture)
        finally:
            if vault is not None and hasattr(vault, "close"):
                vault.close()
        if a.cmd == "render":
            view, helps = _render_view(res, a.full)
            return emit(view, helps, 0 if res["ok"] else 1)
        view, helps = _verify_view(res, a.full)
        return emit(view, helps, 0 if res["reproduced"] else 1)
    except UsageError as exc:
        return fail(str(exc), [f"{PROG} --help: the commands and flags", f"{PROG}: the scenes and runs in this project"], 2)
    except SystemExit as exc:                                        # --help printed its short usage
        return 0 if exc.code in (0, None) else 2
    except (M.Refused, F.ChromiumMissing, E.FfmpegMissing, F.SceneError) as exc:
        return fail(str(exc), MT.refusal_help(exc))
    except Exception as exc:  # noqa: BLE001
        return fail(f"{type(exc).__name__}: {exc}", [f"{PROG}: the scenes and runs in this project"])


if __name__ == "__main__":
    raise SystemExit(main())
