"""The request shapes, one table per studio. Paths, field names and statuses come from each provider's public docs as read on 2026-10-05 (specs/studios/*.md) and are [UNVERIFIED] against the live service. A
list price is the docs' own table, dated, never a quote: the plan says so. `None` is an unpublished price: the user must name the most they accept."""
from __future__ import annotations

import base64
import json
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

DATED = "2026-10-05"


class ParamError(ValueError):
    pass


def _file(p) -> Path:
    f = Path(p)
    if not f.is_file():
        raise ParamError(f"{p} is not a file")
    return f


def data_uri(p) -> str:
    f = _file(p)
    mime = mimetypes.guess_type(f.name)[0] or {".glb": "model/gltf-binary"}.get(f.suffix.lower(), "application/octet-stream")
    return f"data:{mime};base64," + base64.b64encode(f.read_bytes()).decode()


def _choice(args, key, allowed, default=None):
    v = args.get(key, default)
    if v is not None and v not in allowed:
        raise ParamError(f"{key} must be one of {list(allowed)}, not {v!r}")
    return v


def _images(args, lo=1, hi=4, key="images"):
    ims = args.get(key) or []
    if not lo <= len(ims) <= hi:
        raise ParamError(f"{key}: {lo} to {hi} images are needed, got {len(ims)}")
    return [str(_file(i)) for i in ims]


@dataclass
class ActionShape:
    label: str
    validate: Callable                      # (args) -> clean args (paths checked)
    price: Callable                         # (clean) -> credits or None
    create: Callable                        # (clean, studio) -> (method, path, kind, payload)   kind: json | multipart | form
    status_path: Optional[str] = None       # GET template with {id} (None: the studio's own status protocol)
    ceiling_ok: bool = True


@dataclass
class Studio:
    name: str
    base: str
    key_vars: tuple
    balance: tuple                          # (method, path, parse(json) -> number)
    actions: dict = field(default_factory=dict)
    usd_per_credit: Optional[float] = None


# ------------------------------------------------------------------------------------------------ Meshy
def _m_tex(clean):
    return clean.get("texture"), clean.get("texture_resolution", "2k")


def _m_img_price(c):
    tex, res = _m_tex(c)
    return (20 if not tex else (35 if res == "8k" else 30)) + (5 if c.get("geometry_resolution") == "2k" else 0)


def _m_common(a):
    return {"texture": bool(a.get("texture", True)), "texture_resolution": _choice(a, "texture_resolution", ("2k", "4k", "8k"), "2k"), "ai_model": _choice(a, "ai_model", ("meshy-7.1", "meshy-6", "meshy-6-lite", "meshy-t2"), "meshy-7.1"),
            "geometry_resolution": _choice(a, "geometry_resolution", ("standard", "2k"), "standard"), "topology": _choice(a, "topology", ("triangle", "quad"), "triangle"),
            "target_polycount": int(a.get("target_polycount", 30000))}


def _m_validate_image(a):
    c = _m_common(a)
    c["image"] = str(_file(a.get("image") or ""))
    if not 100 <= c["target_polycount"] <= 300000:
        raise ParamError("target_polycount must be 100..300000")
    return c


def _m_validate_multi(a):
    c = _m_common(a)
    c["images"] = _images(a, 1, 4)
    return c


def _m_image_body(c, urls):
    b = {"ai_model": c["ai_model"], "should_texture": c["texture"], "topology": c["topology"], "target_polycount": c["target_polycount"], "geometry_resolution": c["geometry_resolution"]}
    if c["texture"]:
        b.update(enable_pbr=True, texture_resolution=c["texture_resolution"])
    return b


def _m_create_image(c, st):
    return "POST", "/openapi/v1/image-to-3d", "json", dict(_m_image_body(c, None), image_url=data_uri(c["image"]))


def _m_create_multi(c, st):
    return "POST", "/openapi/v1/multi-image-to-3d", "json", dict(_m_image_body(c, None), image_urls=[data_uri(i) for i in c["images"]])


def _m_validate_text(a):
    if not str(a.get("prompt") or "").strip():
        raise ParamError("prompt is required")
    mode = _choice(a, "mode", ("preview", "refine"), "preview")
    if mode == "refine" and not a.get("preview_task_id"):
        raise ParamError("refine needs preview_task_id")
    return {"prompt": str(a["prompt"]), "mode": mode, "preview_task_id": a.get("preview_task_id"), "texture_resolution": _choice(a, "texture_resolution", ("2k", "4k", "8k"), "2k")}


def _m_create_text(c, st):
    body = {"mode": c["mode"], "prompt": c["prompt"]}
    if c["mode"] == "refine":
        body["preview_task_id"] = c["preview_task_id"]
    return "POST", "/openapi/v2/text-to-3d", "json", body


def _m_validate_model(a, extra=None):
    c = {"model": str(_file(a.get("model") or ""))}
    c.update(extra(a) if extra else {})
    return c


def _m_remesh_v(a):
    return _m_validate_model(a, lambda a: {"topology": _choice(a, "topology", ("triangle", "quad"), "triangle"), "target_polycount": int(a.get("target_polycount", 30000))})


def _m_retex_v(a):
    def extra(a):
        if not (a.get("text_style_prompt") or a.get("image_style")):
            raise ParamError("retexture needs text_style_prompt or image_style")
        out = {"text_style_prompt": a.get("text_style_prompt"), "enable_original_uv": bool(a.get("enable_original_uv", True)), "texture_resolution": _choice(a, "texture_resolution", ("2k", "4k", "8k"), "2k")}
        if a.get("image_style"):
            out["image_style"] = str(_file(a["image_style"]))
        return out
    return _m_validate_model(a, extra)


MESHY = Studio("meshy", "https://api.meshy.ai", ("MESHY_API_KEY",), ("GET", "/openapi/v1/balance", lambda j: j["balance"]), usd_per_credit=None, actions={
    "image_to_3d": ActionShape("Meshy image to 3D", _m_validate_image, _m_img_price, _m_create_image, "/openapi/v1/image-to-3d/{id}"),
    "multi_image_to_3d": ActionShape("Meshy multi-image to 3D (1 to 4 views)", _m_validate_multi, _m_img_price, _m_create_multi, "/openapi/v1/multi-image-to-3d/{id}"),
    "text_to_3d": ActionShape("Meshy text to 3D", _m_validate_text, lambda c: 20 if c["mode"] == "preview" else (15 if c["texture_resolution"] == "8k" else 10), _m_create_text, "/openapi/v2/text-to-3d/{id}"),
    "remesh": ActionShape("Meshy remesh", _m_remesh_v, lambda c: 5, lambda c, st: ("POST", "/openapi/v1/remesh", "json", {"model_url": data_uri(c["model"]), "target_formats": ["glb"], "topology": c["topology"],
                                                                                                                         "target_polycount": c["target_polycount"]}), "/openapi/v1/remesh/{id}"),
    "uv_unwrap": ActionShape("Meshy UV unwrap (GLB, at most 40000 faces)", lambda a: _m_validate_model(a), lambda c: 5, lambda c, st: ("POST", "/openapi/v1/uv-unwrap", "json", {"model_url": data_uri(c["model"])}),
                             "/openapi/v1/uv-unwrap/{id}"),
    "retexture": ActionShape("Meshy retexture (keeps the original UV by default)", _m_retex_v, lambda c: 15 if c["texture_resolution"] == "8k" else 10,
                             lambda c, st: ("POST", "/openapi/v1/retexture", "json", dict({k: v for k, v in {"model_url": data_uri(c["model"]), "text_style_prompt": c.get("text_style_prompt"), "enable_original_uv": c["enable_original_uv"],
                                                                                                           "texture_resolution": c["texture_resolution"], "enable_pbr": True}.items() if v is not None},
                                                                                              **({"image_style_url": data_uri(c["image_style"])} if c.get("image_style") else {}))), "/openapi/v1/retexture/{id}"),
})


# ------------------------------------------------------------------------------------------------ Hyper3D (Rodin)
def _h_gen_v(a):
    if not a.get("images") and not a.get("prompt"):
        raise ParamError("generate needs images (1 to 5) or a prompt")
    c = {"tier": _choice(a, "tier", ("Gen-2.5-Extreme-Low", "Gen-2.5-Medium", "Gen-2.5-High"), "Gen-2.5-Medium"), "mesh_mode": _choice(a, "mesh_mode", ("Raw", "Quad"), "Quad"),
         "material": _choice(a, "material", ("PBR", "Shaded", "All", "None"), "PBR"), "prompt": a.get("prompt")}
    if a.get("images"):
        c["images"] = _images(a, 1, 5)
    if a.get("bbox_condition"):
        bb = [int(x) for x in a["bbox_condition"]]
        if len(bb) != 3 or not all(1 <= x <= 2048 for x in bb):
            raise ParamError("bbox_condition is [W, H, L], each 1..2048")
        c["bbox_condition"] = bb
    return c


def _h_tex_v(a):
    return {"model": str(_file(a.get("model") or "")), "image": str(_file(a.get("image") or "")), "material": _choice(a, "material", ("PBR", "Shaded", "All"), "PBR"),
            "resolution": _choice(a, "resolution", ("Basic", "High"), "Basic"), "texture_mode": a.get("texture_mode"), "texture_delight": bool(a.get("texture_delight", False))}


def _h_bang_v(a):
    s = int(a.get("strength", 5))
    if not 1 <= s <= 12:
        raise ParamError("strength is 1..12 (more pieces when higher)")
    return {"model": str(_file(a.get("model") or "")), "image": str(_file(a.get("image") or "")), "strength": s, "instruction": a.get("instruction") or ""}


HYPER3D = Studio("hyper3d", "https://api.hyper3d.com", ("HYPER3D_API_KEY", "RODIN_API_KEY"), ("GET", "/api/v2/check_balance", lambda j: j["balance"]), actions={
    "generate": ActionShape("Hyper3D Rodin generate (images or text)", _h_gen_v, lambda c: None, lambda c, st: ("POST", "/api/v2/rodin", "multipart", {"fields": {k: v for k, v in {
        "tier": c["tier"], "mesh_mode": c["mesh_mode"], "material": c["material"], "prompt": c.get("prompt"), "bbox_condition": json.dumps(c["bbox_condition"]) if c.get("bbox_condition") else None}.items() if v is not None},
        "files": [("images", p) for p in c.get("images", [])]})),
    "texture_only": ActionShape("Hyper3D texture on your mesh", _h_tex_v, lambda c: 2.0 if c.get("texture_mode") == "extreme-high" else 0.5, lambda c, st: ("POST", "/api/v2/rodin_texture_only", "multipart", {"fields": {
        "material": c["material"], "resolution": c["resolution"], "texture_delight": str(c["texture_delight"]).lower(), **({"texture_mode": c["texture_mode"]} if c.get("texture_mode") else {})},
        "files": [("model", c["model"]), ("image", c["image"])]})),
    "bang": ActionShape("Hyper3D Bang: split a model into parts", _h_bang_v, lambda c: None, lambda c, st: ("POST", "/api/v2/bang", "multipart", {"fields": {"strength": str(c["strength"]), "instruction": c["instruction"]},
                                                                                                                                                  "files": [("model", c["model"]), ("image", c["image"])]})),
})


# ------------------------------------------------------------------------------------------------ Hi3D (Hitem3D)
HI3D_GEOMETRY = {("hi3dv3.0", "2048quality"): 50, ("hi3dv3.0", "2048master"): 290, ("hitem3dv2.1", "1536fast"): 25, ("hitem3dv2.1", "1536pro"): 45, ("hitem3dv2.0", "1536"): 35, ("hitem3dv2.0", "1536pro"): 45}


def _i_img_v(a):
    model = _choice(a, "model", ("hi3dv3.0", "hitem3dv2.1", "hitem3dv2.0"), "hi3dv3.0")
    res = a.get("resolution") or {"hi3dv3.0": "2048quality", "hitem3dv2.1": "1536fast", "hitem3dv2.0": "1536"}[model]
    if (model, res) not in HI3D_GEOMETRY:
        raise ParamError(f"resolution {res!r} is not offered for {model}: {sorted(r for m, r in HI3D_GEOMETRY if m == model)}")
    face = int(a.get("face", 500000))
    if not 100000 <= face <= 5000000:
        raise ParamError("face is 100000..5000000")
    return {"images": _images(a, 1, 4), "model": model, "resolution": res, "pbr": bool(a.get("pbr", True)), "face": face, "format": int(a.get("format", 2))}


def _i_tex_v(a):
    return {"model": str(_file(a.get("model") or "")), "image": str(_file(a.get("image") or "")), "pbr": bool(a.get("pbr", True)), "hi_model": "hi3dv3.0"}


def _i_split_v(a):
    mode = _choice(a, "mode", ("general", "character"), "general")
    return {"model": str(_file(a.get("model") or "")), "mode": mode, "level": _choice(a, "level", ("low", "medium", "high"), "medium")}


HI3D = Studio("hi3d", "https://api.hitem3d.ai", ("HITEM3D_CLIENT_ID", "HITEM3D_CLIENT_SECRET"), ("GET", "/open-api/v1/balance", lambda j: j["data"]["balance"]), usd_per_credit=0.02, actions={
    "image_to_3d": ActionShape("Hi3D image to 3D", _i_img_v, lambda c: HI3D_GEOMETRY[(c["model"], c["resolution"])] + 10 + (5 if c["pbr"] and c["model"] == "hi3dv3.0" else 0),
                               lambda c, st: ("POST", "/open-api/v1/submit-task", "multipart", {"fields": {"request_type": "3", "model": c["model"], "resolution": c["resolution"], "pbr": str(int(c["pbr"])), "face": str(c["face"]),
                                                                                                           "format": str(c["format"])}, "files": [("multi_images" if len(c["images"]) > 1 else "images", p) for p in c["images"]]}),
                               "/open-api/v1/query-task?task_id={id}"),
    "texture_only": ActionShape("Hi3D texture on your GLB (request_type 2)", _i_tex_v, lambda c: 10 + (5 if c["pbr"] else 0),
                                lambda c, st: ("POST", "/open-api/v1/submit-task", "multipart", {"fields": {"request_type": "2", "model": c["hi_model"], "pbr": str(int(c["pbr"]))}, "files": [("mesh", c["model"]), ("images", c["image"])]}),
                                "/open-api/v1/query-task?task_id={id}"),
    "split": ActionShape("Hi3D split a model into parts", _i_split_v, lambda c: 20, lambda c, st: ("POST", "/open-api/v1/split/create-task", "multipart", {"fields": {"model": c["mode"], "level": c["level"]},
                                                                                                                                                       "files": [("model_file", c["model"])]}), "/open-api/v1/split/query-task?task_id={id}"),
})


# ------------------------------------------------------------------------------------------------ Tripo REST v3
def _t_img_v(a):
    return {"image": str(_file(a.get("image") or "")), "model_version": a.get("model_version") or "v3.1-20260211"}


def _t_tex_v(a):
    return {"model": str(_file(a.get("model") or "")), "quality": _choice(a, "quality", ("standard", "detailed", "extreme"), "standard")}


def _t_dec_v(a):
    return {"model": str(_file(a.get("model") or "")), "version": _choice(a, "version", ("2.0", "1.0"), "2.0"), "face_limit": int(a.get("face_limit", 20000))}


TRIPO = Studio("tripo", "https://openapi.tripo3d.ai", ("TRIPO_API_KEY",), ("GET", "/v3/account/balance", lambda j: j["data"]["balance"]), actions={
    "rest.image_to_model": ActionShape("Tripo REST image to model", _t_img_v, lambda c: None, lambda c, st: ("POST", "/v3/generation/image-to-model", "json", {"file_token": st.upload(c["image"]), "model_version": c["model_version"]}), "/v3/tasks/{id}"),
    "rest.texture": ActionShape("Tripo REST texture on your model", _t_tex_v, lambda c: {"standard": 10, "detailed": 20, "extreme": 30}[c["quality"]],
                                lambda c, st: ("POST", "/v3/models/texture", "json", {"file_token": st.upload(c["model"]), "texture_quality": c["quality"]}), "/v3/tasks/{id}"),
    "rest.decimate": ActionShape("Tripo REST decimate (retopology)", _t_dec_v, lambda c: 30 if c["version"] == "2.0" else 10,
                                 lambda c, st: ("POST", "/v3/mesh/decimate", "json", {"file_token": st.upload(c["model"]), "version": c["version"], "face_limit": c["face_limit"]}), "/v3/tasks/{id}"),
})

STUDIOS = {"meshy": MESHY, "hyper3d": HYPER3D, "hi3d": HI3D, "tripo": TRIPO}
