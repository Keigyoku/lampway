"""``lampway_image_gen``: image generation through the prompt library. A template + variables (or a raw prompt), the references in the ORDER the template
names them (enforced), size or resolution validated for the model's family, a dry run by default (the rendered prompt, the ordered references, the params,
nothing sent), and every run stored with its rendered prompt. OpenRouter's images API on the shared spend ledger; saved under <project>/images/."""

import asyncio
import json
import uuid
from pathlib import Path

from .. import imagegen as IG
from ..prompts import render as R
from .providers.base import ToolSpec

NAMES = {"lampway_image_gen"}


def specs() -> list:
    return [ToolSpec(
        "lampway_image_gen", "Generate images. Give `template` (+ `variables`) from the prompt library or a raw `prompt`. `references` are project-relative image paths: for a template "
        "an object {role: path} (or a list in its order) - the order the prompt names them is ENFORCED (mesh-paint: clay_render, painted_view, design_plate). Default is a DRY RUN: "
        "the rendered prompt, the references in order and the params, nothing sent. dry_run=false generates (1-4 images, counted against the session spend ceiling) and stores the "
        "rendered prompt with the run. `size` (GPT Image, <= 3840 per edge, ~8.3 MP) or `resolution` + `aspect_ratio` (FLUX, Gemini, Seedream, Riverflow) is validated for the model.",
        {"type": "object", "properties": {
            "template": {"type": "string"}, "variables": {"type": "object"}, "prompt": {"type": "string"}, "model": {"type": "string"},
            "references": {"type": ["object", "array"]}, "size": {"type": "string"}, "resolution": {"type": "string"}, "aspect_ratio": {"type": "string"},
            "count": {"type": "integer"}, "dry_run": {"type": "boolean"}}, "additionalProperties": False})]


def _read(root: Path, rel: str) -> bytes:
    full = Path(rel) if Path(rel).is_absolute() else root / rel
    real_root, real = Path(root).resolve(), full.resolve()
    if real != real_root and real_root not in real.parents:
        raise ValueError(f"{rel} is outside the project root")
    if not real.is_file():
        raise ValueError(f"{rel} is not a file")
    return real.read_bytes()


async def call(svc, name: str, arguments: dict) -> tuple:
    a = arguments if isinstance(arguments, dict) else {}
    try:
        from .server_tools import project_root
        root = project_root()
        tpl = rendered = None
        refs: list = []
        if a.get("template"):
            tpl = R.provider_template(svc.library, a["template"])
            rendered = svc.render(a["template"], a.get("variables"), a.get("model"))
            prompt, model, params = rendered["prompt"], rendered["model"], dict(rendered["params"])
            if not model:                                     # CH5: the purpose's choice runs the template (it pins its own model only with a reason)
                from .. import choices as CH
                from ..choices import registry as CREG
                pid = CREG.TEMPLATE_PURPOSES.get(tpl.get("purpose"), "image.plates")
                try:
                    model = CH.resolve(pid, CH.Job(needs={"runs_on": ["openrouter"]}, origin="agent")).model
                except CH.NoChoice as exc:
                    return str(exc), True
            if a.get("references") is not None or any(i.get("required") for i in rendered["inputs_required"]):
                refs = R.order_references(tpl, a.get("references") if a.get("references") is not None else {})
        else:
            prompt = str(a.get("prompt") or "").strip()
            if not prompt:
                return "give a template or a prompt", True
            from .. import choices as CH
            override = None if not a.get("model") else (a["model"] if ":" in a["model"] else f"openrouter:{a['model']}")
            try:                                              # the agent's model is a job override under the Plates policy (CH3)
                model = CH.resolve("image.plates", CH.Job(needs={"runs_on": ["openrouter"]}, override=override, origin="agent")).model
            except CH.NoChoice as exc:
                return str(exc), True
            params = {}
            refs = [("reference_image", r) for r in (a.get("references") if isinstance(a.get("references"), list) else [])]
        for key in ("size", "resolution", "aspect_ratio"):
            if a.get(key):
                params[key] = a[key]
                if key == "size":
                    params.pop("resolution", None) if R.family(model) != "resolution" else None
        for stale in ("resolution_class", "n", "model", "background", "image_mode", "duration", "generate_audio"):
            params.pop(stale, None)
        if R.family(model) == "size":                                     # the family decides which of the two shapes is valid; an explicit mix is refused below
            for k in ("resolution", "aspect_ratio"):
                if k in params and not a.get(k):
                    params.pop(k)
        R.validate_image_params(model, {k: v for k, v in params.items() if k in ("size", "resolution", "aspect_ratio")})
        count = max(1, min(int(a.get("count") or 1), 4))
        info = {"ok": True, "dry_run": a.get("dry_run", True) is not False, "prompt": prompt, "model": model, "params": params,
                "references": [{"role": r, "file": f} for r, f in refs], "count": count}
        if rendered:
            info.update(template=rendered["template"], variables=rendered["variables"], warnings=rendered["warnings"])
        if info["dry_run"]:
            return json.dumps(info), False
        blobs = [_read(root, f) for _, f in refs]
        from .. import provider_prefs
        from .providers import spend_ledger
        ledger = spend_ledger(provider_prefs.effective())
        before = ledger.spent
        images = await asyncio.to_thread(IG.openrouter_images, prompt, blobs, count, size=params.get("size", ""), aspect_ratio=params.get("aspect_ratio", ""),
                                         model=model, resolution=params.get("resolution", ""), quality=(rendered or {}).get("params", {}).get("quality", ""))
        job_id = f"img-{uuid.uuid4().hex[:10]}"
        out = root / "images"
        out.mkdir(parents=True, exist_ok=True)
        files = []
        for i, (data, media) in enumerate(images, 1):
            p = out / f"{job_id}-{i}.{ {'image/jpeg': 'jpg', 'image/webp': 'webp'}.get(media, 'png') }"
            p.write_bytes(data)
            files.append(str(p))
        cost = round(ledger.spent - before, 6)
        svc.runlog.record(job_id, prompt=prompt, model=model, template=(rendered or {}).get("template"), variables=(rendered or {}).get("variables"), cost=cost,
                          output=files[0], service="image_gen")
        info.update(files=files, job_id=job_id, cost_usd=cost)
        return json.dumps(info), False
    except (ValueError, IG.ImageGenError) as exc:
        return str(exc), True
    except Exception as exc:  # noqa: BLE001 - reported to the model, never with a key
        return f"{type(exc).__name__}: {exc}", True
