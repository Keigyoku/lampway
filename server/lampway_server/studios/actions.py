# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Studio action catalog: what the Client and the agent may ask of a Studio, and the laws each action carries.

Every entry names the shelf driver (``tools/studios/<studio>/<driver>.py``, the engine), builds that driver's argv for the PLAN (a read
back that spends nothing) and for the live RUN, and reads the plan's output into a price and the settings read back. Laws
(memory tripo-studio-invariants / tripo-hung-job-quirk) enforced here, before any driver runs:

  * every setting is read back, and an action that spends credits needs a price read back that equals the expected one;
  * 4 variants at the topology's maximum polycount - never fewer, never a lower polycount;
  * Studio actions land on a saved COPY (a fresh clone): Smart UV is planned from ``state`` and refused on an original;
  * texturing comes last (the driver's guard: a Smart UV step in the History);
  * paired pieces (gauntlets, boots) send the front and back views only;
  * nothing here can change the privacy setting; a hung job is never re-clicked (service.py).

The output shapes parsed here were read from the shelf sources (2026-10-05); the first live run against the real Studio is the owner's.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from . import toon


class ActionError(ValueError):
    """The request is refused before any driver runs."""


@dataclass
class Plan:
    price: Optional[int]
    settings: dict
    problems: list = field(default_factory=list)


@dataclass
class Action:
    id: str
    studio: str
    label: str
    driver: str                       # the shelf driver module, e.g. tripo_mesh
    needs_approval: bool = False
    expected_price: Optional[int] = None
    plan_driver: str = ""             # a different driver for the plan (unwrap plans from tripo_uv state); default: driver
    needs_out_dir: bool = False
    validate: Callable = None         # (args, jail) -> clean args
    plan_args: Callable = None        # (clean, out_dir) -> argv tail
    run_args: Callable = None
    read_plan: Callable = None        # (Parsed, clean) -> Plan
    guard_plan: Callable = None       # (Parsed, clean) -> reason or None: a law checked on the plan's read-back


def _int(v, what):
    try:
        return int(v)
    except (TypeError, ValueError):
        raise ActionError(f"{what} must be a whole number") from None


def _price_digits(text) -> Optional[int]:
    m = re.findall(r"(\d+)", str(text or ""))
    return int(m[-1]) if m else None


# ----------------------------------------------------------------------------------------------- Smart Mesh
def _v_mesh(args, jail):
    for key in ("count", "variants"):
        if args.get(key) not in (None, 4, "4"):
            raise ActionError("a Smart Mesh always makes four variants: never fewer")
    if args.get("polycount") not in (None, "", "max"):
        raise ActionError("the polycount is always the topology's maximum value (the user's rule); a lower one is refused")
    paired = bool(args.get("paired"))
    want = ("front", "back") if paired else ("front", "left", "right", "back")
    if any(not args.get(v) for v in want):
        raise ActionError(("a paired piece needs the front and back views only" if paired
                           else "Smart Mesh needs the front, left, right and back views (paired pieces: paired=true with front and back only)"))
    topology = str(args.get("topology") or "Quad")
    if topology not in ("Quad", "Triangle"):
        raise ActionError("topology is Quad or Triangle")
    clean = {v: jail(args[v]) for v in want}
    clean.update(paired=paired, topology=topology)
    return clean


def _mesh_argv(clean, out_dir):
    argv = [out_dir]
    for v in ("front", "left", "right", "back"):
        if v in clean:
            argv += [f"--{v}", clean[v]]
    if clean["paired"]:
        argv += ["--views", "front,back"]
    return argv + ["--topology", clean["topology"], "--polycount", "max", "--expect-price", "100"]


def _read_mesh(parsed, clean):
    kv = parsed.kv
    problems = [] if kv.get("dry_run") == "verified" else ["the dry run did not report 'verified'"]
    price = _price_digits(kv.get("generate_button"))
    return Plan(price, {k: kv.get(k) for k in ("polycount_read_back", "generate_button", "privacy", "thumbnails_seen") if k in kv}, problems)


# ----------------------------------------------------------------------------------------------- image
def _v_image(args, jail):
    if args.get("count") not in (None, 4, "4"):
        raise ActionError("never fewer than 4 images per generation")
    template = None
    if args.get("template"):
        # the prompt comes from the library: rendered, stored as a file under the job's out_dir, and the file is what the driver reads
        from pathlib import Path
        from ..prompts import render as R
        from ..prompts.library import Library
        try:
            rendered = R.render(Library.from_env(), args["template"], args.get("variables") or {}, args.get("model"))
        except ValueError as exc:
            raise ActionError(str(exc)) from None
        out = Path(jail(args.get("out_dir") or "studio/prompts"))
        out.mkdir(parents=True, exist_ok=True)
        pf = out / "prompt.txt"
        pf.write_text(rendered["prompt"], encoding="utf-8")
        args = dict(args, prompt_file=str(pf))
        template = rendered["template"]
    if not args.get("prompt_file"):
        raise ActionError("an image generation needs prompt_file or template")
    out = {"prompt_file": jail(args["prompt_file"]), "refs": [jail(r) for r in args.get("refs") or []],
           "aspect": str(args.get("aspect") or "1:1"), "model": str(args.get("model") or "GPT Image 2.5")}
    if template:
        out["template"] = template
    return out


def _image_argv(clean, out_dir):
    argv = [out_dir, clean["prompt_file"]]
    for r in clean["refs"]:
        argv += ["--ref", r]
    return argv + ["--model", clean["model"], "--aspect", clean["aspect"], "--count", "4"]


def _read_image(parsed, clean):
    kv = parsed.kv
    problems = [] if kv.get("dry_run") == "verified" else ["the dry run did not report 'verified'"]
    live = re.findall(r"'v':\s*(\d+),\s*'struck':\s*False|\"v\":\s*(\d+),\s*\"struck\":\s*false", str(kv.get("price", "")))
    prices = [int(a or b) for a, b in live]
    return Plan(max(prices) if prices else None, {k: kv.get(k) for k in ("model", "4k", "price") if k in kv}, problems)


# ----------------------------------------------------------------------------------------------- Texture / PBR
def _v_texture(args, jail):
    res = str(args.get("res") or "8K")
    if res not in ("2K", "4K", "8K"):
        raise ActionError("res is 2K, 4K or 8K")
    refs_set = args.get("refs_set")
    if refs_set not in (None, "", "generation", "painted"):
        raise ActionError("refs_set is generation or painted (the plates the Texture tool was given; recorded in the receipt)")
    clean = {"res": res, "remove_lighting": args.get("remove_lighting", True) is not False}
    if refs_set:
        clean["refs_set"] = refs_set
    return clean


REFS_SETS = ("generation", "painted", "custom")


def _v_refs(args, jail):
    """The Texture tool's four reference slots: the generation plates (most detail), our painted plates (our palette) or custom ones. A paired piece carries front and back only."""
    if args.get("set") not in REFS_SETS:
        raise ActionError("set is generation, painted or custom: which plates the Texture tool is given (the user chooses per piece)")
    paired = bool(args.get("paired"))
    want = ("front", "back") if paired else ("front", "left", "right", "back")
    if any(not args.get(v) for v in want):
        raise ActionError("a paired piece needs the front and back plates only" if paired
                          else "the Texture tool needs the front, left, right and back plates (paired pieces: paired=true with front and back only)")
    clean = {v: jail(args[v]) for v in want}
    clean.update(set=args["set"], paired=paired)
    return clean


def _refs_argv(clean, out_dir):
    argv = ["refs"]
    for v in ("front", "left", "right", "back"):
        if v in clean:
            argv += [f"--{v}", clean[v]]
    if clean["paired"]:
        argv += ["--views", "front,back"]
    return argv + ["--set", clean["set"], "--out", out_dir]


def _v_restore(args, jail):
    stamp = str(args.get("stamp") or "").strip()
    if not stamp:
        raise ActionError("restore needs the History card's stamp, as Studio shows it ('MM-DD HH:MM')")
    return {"stamp": stamp}


def _texture_args(clean, out_dir):
    argv = ["texture", "--res", clean["res"], "--expect-price", "30"]
    return argv + (["--remove-lighting"] if clean["remove_lighting"] else [])


def _read_texture(parsed, clean):
    kv = parsed.kv
    try:
        st = json.loads(kv.get("settings") or "{}")
    except ValueError:
        st = {}
    problems = [] if kv.get("verified") is True else ["the settings did not read back as requested"]
    settings = {"res": clean["res"], "remove_lighting": clean["remove_lighting"], "button": st.get("button")}
    if clean.get("refs_set"):
        settings["refs_set"] = clean["refs_set"]
    return Plan(_price_digits(st.get("button")), settings, problems)


def _read_pbr(parsed, clean):
    kv = parsed.kv
    problems = [] if kv.get("verified") is True else ["the price did not read back"]
    return Plan(_price_digits(kv.get("button")), {"button": kv.get("button")}, problems)


# ----------------------------------------------------------------------------------------------- Smart UV
_DATED = re.compile(r"\d\d-\d\d \d\d:\d\d")


def _read_unwrap_state(parsed, clean):
    kv = parsed.kv
    try:
        buttons = json.loads(kv.get("smart_uv_buttons") or "[]")
    except ValueError:
        buttons = []
    m = next((re.match(r"Unwrap UV (\d+)$", b) for b in buttons if re.match(r"Unwrap UV \d+$", str(b))), None)
    return Plan(int(m.group(1)) if m else None, {"credits": kv.get("credits"), "faces": kv.get("faces"), "smart_uv_buttons": buttons,
                                                 "history": kv.get("history")}, [] if m else ["no 'Unwrap UV <price>' button in the Smart UV panel"])


def _guard_copy(parsed, clean):
    hist = str(parsed.kv.get("history") or "")
    dated = _DATED.findall(hist)
    if dated:
        return (f"the selected model has {len(dated)} dated History card(s): it is not a fresh saved copy, and a Studio action lands on a saved "
                "copy only. Run tripo.uv.clone on the original's current version first")
    return None


def _v_none(args, jail):
    return {}


def _v_uv_clone(args, jail):
    return {"version": str(args.get("version") or "Current Version"), "expect_faces": _int(args.get("expect_faces"), "expect_faces")}


def _v_uv_select(args, jail):
    return {"faces": _int(args.get("faces"), "faces"), "clone": bool(args.get("clone"))}


def _v_attempt(args, jail):
    return {"attempt": _int(args.get("attempt"), "attempt")}


def _v_save(args, jail):
    try:
        return {"expect_utilization": float(args.get("expect_utilization"))}
    except (TypeError, ValueError):
        raise ActionError("save needs expect_utilization (the panel's % for the shown attempt)") from None


def _stamp(args):
    stamp = str(args.get("stamp") or "").strip()
    if not stamp:
        raise ActionError("the original is selected by its card stamp ('MM-DD HH:MM', or '*' for any loaded card) and its face count")
    return stamp


def _v_regen_pick(args, jail):
    """retry / harvest: the original = its card stamp + its face count (the driver refuses when they do not match what is shown)."""
    return {"stamp": _stamp(args), "faces": _int(args.get("faces"), "faces")}


def _v_regen_sift(args, jail):
    n = _int(5 if args.get("n") is None else args["n"], "n")
    if not 1 <= n <= 10:
        raise ActionError("n is 1 to 10 free retries per sift (each is discarded and banked in the History)")
    return {"faces": _int(args.get("faces"), "faces"), "n": n}


def _v_regen_discard(args, jail):
    return {"expect_faces": _int(args["expect_faces"], "expect_faces")} if args.get("expect_faces") not in (None, "") else {}


def _v_fetch(args, jail):
    return {"stamp": str(args.get("stamp") or ""), "expect": _int(args.get("expect") or 4, "expect")}


ACTIONS = {a.id: a for a in [
    Action("tripo.state", "tripo", "Read the live Studio state", "tripo_texture", validate=_v_none, plan_args=None,
           run_args=lambda c, o: ["state"]),
    Action("tripo.texture.state", "tripo", "Read the Texture panel (settings, price) and the History stamps with their icons", "tripo_texture", validate=_v_none, plan_args=None,
           run_args=lambda c, o: ["state"]),
    Action("tripo.texture.refs", "tripo", "Choose the Texture tool's four reference plates (generation | painted | custom); a receipt lists their sha256", "tripo_texture",
           needs_out_dir=True, validate=_v_refs, run_args=_refs_argv),
    Action("tripo.texture.restore", "tripo", "Make a History version current again (free; the current one stays in History)", "tripo_texture", validate=_v_restore,
           run_args=lambda c, o: ["restore", "--stamp", c["stamp"]]),
    Action("tripo.mesh", "tripo", "Smart Mesh: 4 variants at maximum polycount", "tripo_mesh", needs_approval=True, expected_price=100,
           needs_out_dir=True, validate=_v_mesh, plan_args=lambda c, o: _mesh_argv(c, o) + ["--dry-run"], run_args=_mesh_argv,
           read_plan=_read_mesh),
    Action("tripo.image", "tripo", "Image generation: 4 images, 4K", "tripo_image", needs_approval=True, expected_price=0, needs_out_dir=True,
           validate=_v_image, plan_args=lambda c, o: _image_argv(c, o) + ["--dry-run"], run_args=_image_argv, read_plan=_read_image),
    Action("tripo.texture", "tripo", "Texture on the Smart UV copy (texturing comes last)", "tripo_texture", needs_approval=True,
           expected_price=30, needs_out_dir=True, validate=_v_texture, plan_args=lambda c, o: _texture_args(c, o),
           run_args=lambda c, o: _texture_args(c, o) + ["--go", "--out", o], read_plan=_read_texture),
    Action("tripo.pbr", "tripo", "PBR on the textured copy", "tripo_texture", needs_approval=True, expected_price=5, needs_out_dir=True,
           validate=_v_none, plan_args=lambda c, o: ["pbr", "--expect-price", "5"],
           run_args=lambda c, o: ["pbr", "--expect-price", "5", "--go", "--out", o], read_plan=_read_pbr),
    Action("tripo.uv.select", "tripo", "Select the model showing N faces", "tripo_uv", validate=_v_uv_select,
           run_args=lambda c, o: ["select", "--faces", str(c["faces"])] + (["--clone"] if c["clone"] else [])),
    Action("tripo.uv.clone", "tripo", "Copy a History card (free): Studio actions land on the saved copy", "tripo_uv", validate=_v_uv_clone,
           run_args=lambda c, o: ["clone", "--version", c["version"], "--expect-faces", str(c["expect_faces"])]),
    Action("tripo.uv.unwrap", "tripo", "Smart UV unwrap on the saved copy", "tripo_uv", needs_approval=True, expected_price=20,
           needs_out_dir=True, plan_driver="tripo_uv", validate=_v_none, plan_args=lambda c, o: ["state"],
           run_args=lambda c, o: ["unwrap", "--expect-price", "20", "--out", o], read_plan=_read_unwrap_state, guard_plan=_guard_copy),
    Action("tripo.uv.retry", "tripo", "One free Smart UV retry", "tripo_uv", needs_out_dir=True, validate=_v_none,
           run_args=lambda c, o: ["retry", "--out", o]),
    Action("tripo.uv.collect", "tripo", "Wait for a running unwrap/retry and download it", "tripo_uv", needs_out_dir=True, validate=_v_none,
           run_args=lambda c, o: ["collect", "--out", o]),
    Action("tripo.uv.score", "tripo", "Score every downloaded UV attempt", "tripo_uv", needs_out_dir=True, validate=_v_none,
           run_args=lambda c, o: ["score", "--out", o]),
    Action("tripo.uv.pick", "tripo", "Show one UV attempt", "tripo_uv", needs_out_dir=True, validate=_v_attempt,
           run_args=lambda c, o: ["pick", "--attempt", str(c["attempt"]), "--out", o]),
    Action("tripo.uv.save", "tripo", "Save the shown UV attempt onto the copy (free)", "tripo_uv", validate=_v_save,
           run_args=lambda c, o: ["save", "--expect-utilization", str(c["expect_utilization"])]),
    Action("tripo.regen.retry", "tripo", "One free seed reroll on an ORIGINAL (Edit Mesh Retry; the modal stays open to score it)", "tripo_regen", needs_out_dir=True,
           validate=_v_regen_pick, run_args=lambda c, o: ["retry", o, c["stamp"], str(c["faces"])]),
    Action("tripo.regen.sift", "tripo", "N free seed rerolls on an original, each discarded (banked in History)", "tripo_regen", needs_out_dir=True,
           validate=_v_regen_sift, run_args=lambda c, o: ["sift", o, str(c["faces"]), "--n", str(c["n"])]),
    Action("tripo.regen.harvest", "tripo", "Download every History version (banked rerolls) of an original", "tripo_regen", needs_out_dir=True,
           validate=_v_regen_pick, run_args=lambda c, o: ["harvest", o, c["stamp"], str(c["faces"])]),
    Action("tripo.regen.collect", "tripo", "Wait for a reroll already running in the open modal and download it", "tripo_regen", needs_out_dir=True,
           validate=_v_none, run_args=lambda c, o: ["collect", o]),
    Action("tripo.regen.apply", "tripo", "Keep the Current Version: commits the new seed onto the original (the old one stays in History)", "tripo_regen",
           validate=_v_none, run_args=lambda c, o: ["apply"]),
    Action("tripo.regen.discard", "tripo", "Throw the Current Version away; verifies the original's face count is back", "tripo_regen",
           validate=_v_regen_discard, run_args=lambda c, o: ["discard"] + (["--expect-faces", str(c["expect_faces"])] if c.get("expect_faces") else [])),
    Action("tripo.fetch", "tripo", "Download the variants of one generation by its card stamp", "tripo_fetch", needs_out_dir=True,
           validate=_v_fetch, run_args=lambda c, o: [o, c["stamp"], "--expect", str(c["expect"])]),
]}


# ----------------------------------------------------------------------------------------------- REST studios (Meshy, Hyper3D, Hi3D, Tripo REST)
def _rest_actions():
    """One Action per REST shape. The price is read by the driver's plan (the docs' list price, dated, plus the balance); the confirmed run is the driver's armed --run."""
    import json as _json
    from .rest import shapes as SH
    out = []
    for studio_name, studio in SH.STUDIOS.items():
        for name, shape in studio.actions.items():
            aid = f"{studio_name}.{name}"
            path_keys = ("image", "model", "image_style")

            def validate(args, jail, _shape=shape):
                a = dict(args or {})
                for k in path_keys:
                    if a.get(k):
                        a[k] = jail(a[k])
                if a.get("images"):
                    a["images"] = [jail(i) for i in a["images"]]
                try:
                    ceiling = a.get("accept_up_to_credits")
                    _shape.validate({k: v for k, v in a.items() if k != "accept_up_to_credits"})
                except SH.ParamError as exc:
                    raise ActionError(str(exc)) from None
                if ceiling is not None:
                    a["accept_up_to_credits"] = _int(ceiling, "accept_up_to_credits")
                return a

            def plan_args(clean, out_dir, _aid=aid):
                return [_aid, "--plan", "--args", _json.dumps(clean)]

            def run_args(clean, out_dir, _aid=aid):
                return [_aid, "--run", "--out", out_dir, "--args", _json.dumps(clean)]

            def read_plan(parsed, clean):
                kv = parsed.kv
                problems = [] if kv.get("dry_run") == "verified" else ["the dry run did not report 'verified'"]
                price = kv.get("price_effective_credits")
                return Plan(price, {"unit": "credits", "price_source": kv.get("price_source"), "balance_credits": kv.get("balance_credits"), "price_credits": kv.get("price_credits"),
                                    "ceiling_credits": kv.get("price_ceiling_credits"), "usd_estimate": kv.get("usd_estimate")}, problems)

            out.append(Action(aid, studio_name, shape.label, f"rest.{studio_name}", needs_approval=True, expected_price=None, needs_out_dir=True, validate=validate, plan_args=plan_args,
                              run_args=run_args, read_plan=read_plan))
    return out


for _a in _rest_actions():
    ACTIONS[_a.id] = _a


# ----------------------------------------------------------------------------------------------- Hyper3D's MCP (Lampway's own sign-in)
def _mcp_actions():
    """Hyper3D's seven MCP tools (specs/studios/hyper3d.md, measured 2026-10-05) next to its REST shapes, behind the same gate: the two that
    consume credits are planned (no tool called, an unpublished price needs accept_up_to_credits) and wait for the user's click; the
    reads run at once. rodin_import_images takes ChatGPT's own file parameters and is refused with what to use instead."""
    import json as _json
    labels = {"create_uploads": "Hyper3D (MCP): upload reference images", "import_images": "Hyper3D (MCP): import images (ChatGPT only)",
              "generate": "Hyper3D (MCP): Rodin generate, on your Hyper3D sign-in", "generate_bang": "Hyper3D (MCP): Bang a Rodin generation into parts",
              "get_status": "Hyper3D (MCP): a generation's status", "wait": "Hyper3D (MCP): wait up to 45 s for a generation",
              "get_result": "Hyper3D (MCP): download a generation's files"}
    out = []
    for tool, label in labels.items():
        paid = tool in ("generate", "generate_bang")

        def validate(args, jail, _tool=tool):
            from .mcp_driver import _validate
            a = dict(args or {})
            if a.get("images"):
                a["images"] = [jail(i) for i in a["images"]]
            ceiling = a.pop("accept_up_to_credits", None)
            try:
                a = _validate(_tool, a)
            except ValueError as exc:
                raise ActionError(str(exc)) from None
            if ceiling is not None:
                a["accept_up_to_credits"] = _int(ceiling, "accept_up_to_credits")
            return a

        def read_plan(parsed, clean):
            kv = parsed.kv
            problems = [] if kv.get("dry_run") == "verified" else ["the dry run did not report 'verified'"]
            return Plan(kv.get("price_effective_credits"), {"unit": "credits", "price_source": kv.get("price_source"), "balance_credits": kv.get("balance_credits"),
                                                            "ceiling_credits": kv.get("price_ceiling_credits")}, problems)
        out.append(Action(f"hyper3d.mcp.{tool}", "hyper3d", label, "mcp.hyper3d", needs_approval=paid, needs_out_dir=True, validate=validate,
                          plan_args=lambda c, o, _t=tool: [f"hyper3d.{_t}", "--plan", "--args", _json.dumps(c)],
                          run_args=lambda c, o, _t=tool: [f"hyper3d.{_t}", "--run", "--out", o, "--args", _json.dumps(c)], read_plan=read_plan))
    return out


for _a in _mcp_actions():
    ACTIONS[_a.id] = _a
