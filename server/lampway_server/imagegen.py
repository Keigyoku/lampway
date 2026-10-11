"""The image backend behind mesh-paint texturing: N painted variants of a clay render, through a configurable backend.

* ``tripo``      the Tripo Studio driver (GPT Image 2.5, 4 images, 4K, free quota). Every setting is set and read back right
                 before Generate and the run refuses on any mismatch (incl. a price that is not free); never fewer than 4 per
                 generation; a DRY RUN unless ``live`` AND the owner's own LAMPWAY_STUDIO_ARMED=1 is set in this process.
* ``openrouter`` an OpenRouter image model (default ``google/gemini-3.1-flash-image``: text + reference images in, one image per
                 call) over POST /api/v1/images. Dry run unless ``live``; live needs the OpenRouter key, counts against the SAME
                 session spend ceiling as the chat models, and is refused before sending once that ceiling is reached.

Backend choice: ``LAMPWAY_IMAGE_BACKEND`` (default ``tripo``). Every path an argument names stays inside the project root.
Also a command: ``python -m lampway_server.imagegen --backend tripo --prompt-file p.txt --ref clay.png --out runs/Front [--live]``.
"""

import argparse
import json
import logging
import base64
import mimetypes
import sys
from pathlib import Path

from .agent import server_tools as ST
from .studios import axi

BACKENDS = ("tripo", "openrouter")              # codex_cli ($imagegen through the Codex CLI) retired: agent-modes spec R0
log = logging.getLogger("lampway.imagegen")
openrouter_transport = None          # tests inject an httpx transport here; None means the real network
_IMG = (".png", ".jpg", ".jpeg", ".webp")


class ImageGenError(RuntimeError):
    pass


def backend_name() -> str:
    from . import provider_prefs
    name = provider_prefs.effective().image_backend
    if name not in BACKENDS:
        raise ValueError(f"unknown image backend {name!r}; the backends are {', '.join(BACKENDS)}")
    return name


IMAGE_CONNECTIONS = {"openrouter": "openrouter", "tripo": "studio:tripo"}


def _register_uses() -> None:
    """Connections' "where it is used" for the image backends: the connection follows the backend chosen now."""
    from .connections import register_use
    register_use("studio_image_generate", lambda: IMAGE_CONNECTIONS.get(backend_name()), "the agent's image generation (studio_image_generate)")
    register_use("image_gen", "openrouter", "the Client's image generation job (image_gen)")


_register_uses()


def _state_dir() -> Path:
    from .config import state_dir
    return state_dir()


def _images(out: Path) -> list:
    return sorted(str(p) for p in out.glob("*") if p.suffix.lower() in _IMG and p.stem.isdigit()) if out.exists() else []


def render_prompt_file(template: str, variables: dict, out_dir: str, model: str = None) -> tuple:
    """Render a library template and STORE the rendered prompt as ``<out_dir>/prompt.txt`` (inside the project root). Returns (path relative as given, render)."""
    from .prompts import render as R
    from .prompts.library import Library
    library = Library.from_env()
    R.provider_template(library, template)
    rendered = R.render(library, template, variables or {}, model)
    d = Path(ST.jail(out_dir))
    d.mkdir(parents=True, exist_ok=True)
    (d / "prompt.txt").write_text(rendered["prompt"], encoding="utf-8")
    return str(Path(out_dir) / "prompt.txt"), rendered


def generate(backend: str, prompt_file: str, refs, out_dir: str, count: int = 4, live: bool = False, size: str = "", aspect_ratio: str = "", purpose: str = "plates") -> dict:
    """Returns {backend, files, dry_run, output}. ``refs`` in order: the clay render first, then any painted consistency view,
    then the design plate (the prompts name them first / second / third)."""
    if backend not in BACKENDS:
        raise ValueError(f"unknown image backend {backend!r}; the backends are {', '.join(BACKENDS)}")
    prompt_path = ST.jail(prompt_file)
    ref_paths = [ST.jail(r) for r in refs]
    out = ST.jail(out_dir)
    if backend == "openrouter":
        return _openrouter(prompt_path, ref_paths, Path(out), int(count), live, size, aspect_ratio, purpose)
    if backend == "tripo":
        cmd = ST.command("studio_tripo_image", {"out_dir": out_dir, "prompt_file": prompt_file, "refs": list(refs),
                                                "count": str(count), "dry_run": not live}, allow_live=True)   # free quota only; the owner's armed env still applies
        rc, text = ST._exec(cmd, ST.environment(), 900.0)
        if rc != 0:
            raise ImageGenError(f"the Tripo driver refused or failed: {text.strip()[-600:]}")
    return {"backend": "tripo", "files": _images(Path(out)) if live else [], "dry_run": not live, "output": text}


def _sniff_mime(data: bytes) -> str:
    if data[:4] == b"\x89PNG":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def size_for_aspect(aspect: str) -> str:
    """WIDTHxHEIGHT for an aspect ratio ('3:2'), as large as the image model's pixel budget allows, both sides multiples of 16."""
    from .provider_prefs import MAX_IMAGE_PIXELS
    try:
        a, b = (float(x) for x in str(aspect).split(":"))
        if a <= 0 or b <= 0:
            raise ValueError
    except ValueError:
        raise ValueError(f"aspect_ratio must look like 3:2, not {aspect!r}") from None
    h = (MAX_IMAGE_PIXELS * b / a) ** 0.5
    w = h * a / b
    return f"{int(w // 16 * 16)}x{int(h // 16 * 16)}"          # flooring both sides keeps the product within the budget


_SUPPORTED: dict = {}                # model id -> the supported_parameters its endpoints list (cached for the process)


def supported_parameters_fallback(model: str):
    """What a model family takes when its endpoints cannot be read: GPT Image takes ``size``; FLUX 3, Seedream, Gemini, Riverflow and
    Qwen take ``resolution`` + ``aspect_ratio``. None = unknown (nothing is validated)."""
    if model.startswith("openai/gpt-image"):
        return {"size", "quality", "input_references"}
    if model.startswith(("black-forest-labs/", "bytedance-seed/", "google/", "sourceful/", "qwen/")):
        return {"resolution", "aspect_ratio", "input_references"}
    return None


def supported_parameters(client, key: str, model: str):
    """GET /images/models/<id>/endpoints -> the union of supported_parameters; cached; the family table when the lookup fails."""
    from .agent.providers.openrouter import BASE_URL, REFERER, TITLE
    if model in _SUPPORTED:
        return _SUPPORTED[model]
    found = None
    try:
        resp = client.get(f"{BASE_URL}/images/models/{model}/endpoints", headers={"Authorization": f"Bearer {key}", "HTTP-Referer": REFERER, "X-Title": TITLE})
        if resp.status_code == 200:
            body = resp.json()
            # the live response has ``endpoints`` at the TOP level (an older assumption nested it under ``data``); each record's
            # supported_parameters is an object keyed by parameter name (a list is accepted too)
            eps = body.get("endpoints") or (body.get("data") or {}).get("endpoints") or []
            names = set()
            for e in eps:
                sp = e.get("supported_parameters") or {}
                names |= set(sp) if isinstance(sp, dict) else set(sp)
            found = names or None
    except Exception:  # noqa: BLE001 - validation is best effort; the request itself is the authority
        found = None
    if found is not None and model.startswith("openai/gpt-image"):
        found = found | {"size"}                  # measured 2026-10-05: an accepted passthrough that the record does not list (<= 3840 per edge, ~8.3 MP)
    _SUPPORTED[model] = found if found is not None else supported_parameters_fallback(model)
    return _SUPPORTED[model]


def _purpose_body(client, key, settings, purpose, size, aspect_ratio, override=None):
    """(model, extra body params) for a purpose, validated against the model's supported parameters: one it does not list is refused."""
    from .provider_prefs import PURPOSES
    if purpose not in PURPOSES:
        raise ValueError(f"unknown purpose {purpose!r}; the purposes are {list(PURPOSES)}")
    cfg = dict(settings.image_purposes.get(purpose) or {})
    if override:                                       # an explicit model (a template's) and its own params replace the purpose's
        cfg = {"model": override["model"], **{k: v for k, v in override.items() if k != "model" and v}}
    model = cfg.get("model")
    if not model:
        raise ValueError(f"the {purpose} purpose has no image model: choose one in the Providers dialog")
    supported = supported_parameters(client, key, model)

    def need(param):
        if supported is not None and param not in supported:
            raise ValueError(f"{model} does not take {param} (it lists: {', '.join(sorted(supported))}); change the {purpose} purpose in the Providers dialog")
    extra = {}
    env_size = settings.openrouter_image_size if settings.sources.get("openrouter_image_size") == "env" and not override else ""
    if size:
        need("size")
        extra["size"] = _checked_size(size)
    elif aspect_ratio:
        if supported is not None and "aspect_ratio" in supported:
            extra["aspect_ratio"] = aspect_ratio
            size_for_aspect(aspect_ratio)                       # validates the shape
        else:
            need("size")
            extra["size"] = size_for_aspect(aspect_ratio)
    elif env_size and (supported is None or "size" in supported):
        extra["size"] = _checked_size(env_size)
    elif cfg.get("size"):
        need("size")
        extra["size"] = cfg["size"]
    if env_size and "size" not in extra:
        log.info("the session size %s (env LAMPWAY_OPENROUTER_IMAGE_SIZE) is not used: %s does not take size", env_size, model)
    if cfg.get("resolution"):
        need("resolution")
        extra["resolution"] = cfg["resolution"]
    if cfg.get("quality"):
        need("quality")
        extra["quality"] = cfg["quality"]
    if extra.get("size"):
        origin = "argument" if size else ("env" if env_size and extra["size"] == env_size else
                                          ("saved prefs" if settings.sources.get("image_purposes") == "saved" else "default"))
        log.info("image size %s for purpose %s on %s (from %s)", extra["size"], purpose, model, origin)
    return model, extra


def openrouter_images(prompt: str, references: list, count: int, size: str = "", aspect_ratio: str = "", purpose: str = "", model: str = "",
                      resolution: str = "", quality: str = "") -> list:
    """``count`` images from OpenRouter's images API (one request each), as ``[(bytes, media_type)]``; ``references`` are
    image bytes sent as data URLs. The key comes from the environment, every request is refused past the session spend
    ceiling, and the reported cost goes on the shared ledger."""
    import httpx
    from .agent.providers import spend_ledger
    from .agent.providers.openrouter import BASE_URL, REFERER, TITLE, redact, resolve_api_key
    from . import provider_prefs
    if not 1 <= int(count) <= 4:
        raise ValueError("the openrouter backend makes at most 4 images per generation (one request each)")
    settings = provider_prefs.effective()
    if not purpose:                                     # the pre-purpose path: the one global image model, size and quality
        if size:
            size = _checked_size(size)
        elif aspect_ratio:
            size = size_for_aspect(aspect_ratio)
    explicit_model = model                              # a rendered template's own model; empty = the purpose's (or the global default's)
    model = settings.openrouter_image_model
    refs = [{"type": "image_url", "image_url": {"url": f"data:{_sniff_mime(data)};base64," + base64.b64encode(data).decode()}}
            for data in references]
    key = resolve_api_key()
    ledger = spend_ledger(settings)
    out = []
    from . import egress as EG
    from .choices import registry as CREG
    cls = CREG.PURPOSES.get(f"image.{purpose or 'plates'}", CREG.PURPOSES["image.plates"]).content_class
    with EG.context(content_class=cls, kind="image", observe_private=True), \
            httpx.Client(transport=openrouter_transport, timeout=300.0) as client:          # HC24: declared, observed (CH1 first release)
        if explicit_model:                              # validated against that model's supported parameters
            model, extra = _purpose_body(client, key, settings, purpose or "plates", size, aspect_ratio,
                                         override={"model": explicit_model, "resolution": resolution, "quality": quality})
        elif purpose:
            model, extra = _purpose_body(client, key, settings, purpose, size, aspect_ratio)
        else:
            extra = {}
            if size or settings.openrouter_image_size:
                extra["size"] = size or settings.openrouter_image_size
            if settings.openrouter_image_quality:
                extra["quality"] = settings.openrouter_image_quality
        from .choices import shadow as _SH
        from . import choices as _CH
        _SH.record(f"image.{purpose or 'plates'}", f"openrouter:{model}", _CH.Job(needs={"runs_on": ["openrouter"]}))      # the shadow row: resolved vs ran
        for i in range(1, int(count) + 1):
            ledger.check()
            body = {"model": model, "prompt": prompt, **extra}
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
            media_type = items[0].get("media_type") or "image/png"
            out.append((base64.b64decode(items[0]["b64_json"]), media_type))
    return out


def _checked_size(size: str) -> str:
    from . import provider_prefs
    try:
        return provider_prefs.check_size(size)
    except provider_prefs.PrefsError as exc:
        raise ValueError(str(exc)) from None


def openrouter_image_backend(model: str, payload: dict):
    """The job-queue backend for the client's ``image_gen`` service (jobqueue.py): ``payload`` is what the client sends
    ({prompt, params{number_of_images}, reference_images_b64, image_name})."""
    from .jobqueue import ImageOutput, MAX_REFERENCE_IMAGES
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("image_gen needs a prompt")
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    count = int(params.get("number_of_images") or 1)
    refs = [base64.b64decode(r) for r in (payload.get("reference_images_b64") or [])[:MAX_REFERENCE_IMAGES] if isinstance(r, str)]
    purpose = str(params.get("purpose") or "plates")
    from . import provider_prefs
    own = (provider_prefs.effective().image_purposes.get(purpose) or {}).get("model")
    explicit = "" if model in ("", "default", None, own) else str(model)          # the job queue passes the model Choices resolved (HC6)
    return ImageOutput(images=openrouter_images(prompt, refs, count, size=str(params.get("size") or ""),
                                                aspect_ratio=str(params.get("aspect_ratio") or ""),
                                                purpose=purpose, model=explicit), image_name=str(payload.get("image_name") or ""))


def _openrouter(prompt_path: str, ref_paths: list, out: Path, count: int, live: bool, size: str = "", aspect_ratio: str = "",
                purpose: str = "plates", model: str = "", resolution: str = "", quality: str = "") -> dict:
    from . import provider_prefs
    settings = provider_prefs.effective()
    model_name = model or (settings.image_purposes.get(purpose) or {}).get("model") or settings.openrouter_image_model
    if not 1 <= count <= 4:
        raise ValueError("the openrouter backend makes at most 4 images per generation (one request each)")
    if not live:
        return {"backend": "openrouter", "files": [], "dry_run": True,
                "output": f"dry run: would send {count} request(s) to {model_name} with {len(ref_paths)} reference image(s); nothing sent"}
    from .agent.providers import spend_ledger
    prompt = Path(prompt_path).read_text(encoding="utf-8").strip()
    images = openrouter_images(prompt, [Path(p).read_bytes() for p in ref_paths], count, size=size, aspect_ratio=aspect_ratio, purpose=purpose, model=model, resolution=resolution, quality=quality)
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for i, (data, media_type) in enumerate(images, 1):
        target = out / f"{i}{ {'image/jpeg': '.jpg', 'image/webp': '.webp'}.get(media_type, '.png') }"
        target.write_bytes(data)
        files.append(str(target))
    ledger = spend_ledger(settings)
    return {"backend": "openrouter", "files": files, "dry_run": False,
            "output": f"{len(files)} image(s) from {model_name}; session spend ${ledger.spent:.4f} of ${ledger.ceiling_usd:.2f}"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="imagegen", description="Painted variants of a clay render through a configurable image backend (AXI).")
    ap.add_argument("--backend", default=None)
    ap.add_argument("--prompt-file", default=None, help="a raw prompt file (or use --template)")
    ap.add_argument("--template", default=None, help="a prompt-library template id; its rendered prompt is stored as <out>/prompt.txt")
    ap.add_argument("--var", action="append", default=[], help="a template variable, k=v (repeatable)")
    ap.add_argument("--model", default=None, help="the image model (a template's own default otherwise)")
    ap.add_argument("--ref", action="append", default=[], help="a reference image; with --template a role=path pair, or paths in the template's order")
    ap.add_argument("--out", required=True)
    ap.add_argument("--count", type=int, default=4)
    ap.add_argument("--size", default="", help="WIDTHxHEIGHT for models that take size (explicit: beats the environment and the saved purpose)")
    ap.add_argument("--aspect", default="", help="an aspect ratio such as 16:9 for models that take aspect_ratio")
    ap.add_argument("--purpose", default="plates", help="the image purpose whose model and defaults apply: plates | mask | concept | tile")
    ap.add_argument("--live", action="store_true", help="really generate (tripo also needs LAMPWAY_STUDIO_ARMED=1)")
    ap.add_argument("--print-prompt", action="store_true", help="render the template, print the prompt and its ordered references; generate nothing")
    a = ap.parse_args(argv)
    try:
        if a.print_prompt and a.template:
            from .prompts import render as R
            from .prompts.library import Library
            variables = {}
            for kv in a.var:
                k, _, v = kv.partition("=")
                variables[k] = _coerce(v)
            r = R.render(Library.from_env(), a.template, variables, a.model)
            print(json.dumps({"template": r["template"], "prompt": r["prompt"], "params": r["params"], "inputs": [i["role"] for i in r["inputs_required"]]}))
            return 0
        backend = a.backend or backend_name()
        extra, rendered, prompt_file, refs = {}, None, a.prompt_file, list(a.ref)
        if a.template:
            from .prompts import render as R
            from .prompts.library import Library
            variables = {}
            for kv in a.var:
                k, sep, v = kv.partition("=")
                if not sep:
                    raise ValueError(f"--var needs k=v, not {kv!r}")
                variables[k] = _coerce(v)
            prompt_file, rendered = render_prompt_file(a.template, variables, a.out, a.model)
            tpl = Library.from_env().get(a.template)
            if tpl.get("inputs"):
                named = {r.partition("=")[0]: r.partition("=")[2] for r in refs} if refs and all("=" in r for r in refs) else refs
                refs = [item for _, item in R.order_references(tpl, named)]
            params = R.validate_image_params(rendered["model"], rendered["params"]) if rendered.get("model") else rendered["params"]
            extra = {k: params[k] for k in ("size", "aspect_ratio", "resolution", "quality") if params.get(k)}
            extra["model"] = rendered.get("model") or ""
        elif not prompt_file:
            raise ValueError("give --prompt-file or --template")
        if a.size:
            extra["size"] = _checked_size(a.size)
        if a.aspect:
            extra["aspect_ratio"] = a.aspect
        if a.purpose not in provider_prefs_purposes():
            raise ValueError(f"unknown purpose {a.purpose!r}; the purposes are {list(provider_prefs_purposes())}")
        if backend == "openrouter" and (extra or a.purpose != "plates"):
            res = _openrouter(ST.jail(prompt_file), [ST.jail(r) for r in refs], Path(ST.jail(a.out)), int(a.count), a.live, extra.get("size", ""),
                              extra.get("aspect_ratio", ""), a.purpose, extra.get("model", ""), extra.get("resolution", ""), extra.get("quality", ""))
        else:
            res = generate(backend, prompt_file, refs, a.out, a.count, a.live)
        if rendered is not None or a.live:
            try:
                from .prompts.runlog import RunLog
                from .ledger import default_path
                import uuid
                RunLog(default_path()).record(f"cli-{uuid.uuid4().hex[:10]}", prompt=Path(ST.jail(prompt_file)).read_text(encoding="utf-8") if prompt_file else "",
                                                                 model=(rendered or {}).get("model") or "", template=(rendered or {}).get("template"),
                                                                 variables=(rendered or {}).get("variables"), output=(res["files"] or [None])[0], service="image_gen")
            except Exception:  # noqa: BLE001 - the log never fails the run
                pass
    except (ImageGenError, ValueError) as exc:
        print(f"error: {exc}")
        return 1
    axi.kv({"backend": res["backend"], "dry_run": res["dry_run"], "images": len(res["files"]), **({"template": rendered["template"], "prompt_file": prompt_file} if rendered else {})})
    axi.table("files", [{"file": f} for f in res["files"]], ["file"])
    return 0


def provider_prefs_purposes():
    from .provider_prefs import PURPOSES
    return PURPOSES


def _coerce(v: str):
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    for cast in (int, float):
        try:
            return cast(v)
        except ValueError:
            continue
    return v


if __name__ == "__main__":
    sys.exit(main())
