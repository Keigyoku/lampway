"""Higgsfield as a generation provider: the catalogue (models_explore), uploads (media_upload -> PUT -> media_confirm), the price
(get_cost) before any spend, generation in the roles each model takes, motion transfer (Genjutsu ``hf_mult_motion_control``, Kling's
``motion_control``), jobs_wait polling and downloads. All of it through Lampway's own MCP client; nothing here spends credits by itself
(the confirm gate in higgsfield_jobs.py decides that).

The tool RESPONSE shapes are read leniently (the SPEC fixes names and parameters, not bodies); the read-only diff after sign-in checks
them. The rule for failures: a transport timeout on a submit is never retried (the request may have been accepted); a timeout while
waiting just polls the same job ids again.
"""

import time
from typing import Optional

import httpx

from .higgsfield_mcp import HiggsfieldMCP, ToolError, TransportTimeout

TERMINAL_OK = {"completed", "succeeded", "done", "success", "finished"}
TERMINAL_BAD = {"failed", "error", "canceled", "cancelled", "nsfw", "rejected", "expired"}
_URL_KEYS = ("result_url", "url", "video_url", "image_url", "output_url", "download_url")
MAX_UPLOAD_BYTES = 250 * 1024 * 1024
PARAMS_TOOLS = ("generate_video", "generate_image", "motion_control")      # the live schema: ONE argument, ``params`` (an object) holding everything
PAGE = 100                                                                  # models_explore's page size cap (the default is 20)
MAX_PAGES = 20


class HiggsfieldError(RuntimeError):
    pass


class HiggsfieldPreset(HiggsfieldError):
    """get_cost answered a PRESET RECOMMENDATION instead of a price. It is an option for the user, never accepted silently: ``preset`` is {id, name}."""

    def __init__(self, preset: dict):
        self.preset = preset
        super().__init__(f"Higgsfield recommends the preset {preset['name']!r} (id {preset['id']}) instead of quoting a price; accept it by asking for that preset, "
                         "or decline it by resubmitting as a literal request (params.literal = true)")


def find_preset(data) -> Optional[dict]:
    """The recommended preset {id, name} inside a response, if it holds one (a node under a key naming 'preset', with an id)."""
    for node in _walk(data):
        if isinstance(node, dict):
            for key, v in node.items():
                if "preset" in str(key).lower() and isinstance(v, dict):
                    pid = v.get("preset_id") or v.get("id")
                    if pid:
                        return {"id": str(pid), "name": str(v.get("name") or v.get("title") or pid)}
    return None


def _walk(obj):
    """Every dict and list element inside ``obj`` (depth first)."""
    stack = [obj]
    while stack:
        cur = stack.pop()
        yield cur
        if isinstance(cur, dict):
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)


def find_credits(data) -> Optional[float]:
    for node in _walk(data):
        if isinstance(node, dict):
            for key in ("credits", "cost", "total_credits", "credit_cost", "price"):
                v = node.get(key)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    return float(v)
    return None


def find_jobs(data) -> list:
    out = []
    for node in _walk(data):
        if isinstance(node, dict) and isinstance(node.get("jobs"), list):
            for j in node["jobs"]:
                if isinstance(j, dict) and (j.get("job_id") or j.get("id")):
                    out.append(str(j.get("job_id") or j.get("id")))
            if out:
                return out
    for node in _walk(data):
        if isinstance(node, dict) and isinstance(node.get("job_ids"), list):
            return [str(x) for x in node["job_ids"]]
    return out


def _url_of(row) -> Optional[str]:
    for node in _walk(row):
        if isinstance(node, dict):
            for key in _URL_KEYS:
                v = node.get(key)
                if isinstance(v, str) and v.startswith("http"):
                    return v
    return None


def _param_list(raw: dict) -> dict:
    """The model's ``parameters`` (the live shape: a list of {name, type, options, min, max, default}) by name."""
    rows = raw.get("parameters")
    if isinstance(rows, dict):                                       # the SPEC-era shape, kept readable
        return {k: dict(v, name=k) for k, v in rows.items() if isinstance(v, dict)}
    return {p["name"]: p for p in rows or [] if isinstance(p, dict) and p.get("name")}


def normalise_model(raw: dict, kind: str) -> dict:
    roles = []
    for m in raw.get("medias") or []:
        for r in (m.get("roles") if isinstance(m, dict) else []) or []:
            if r not in roles:
                roles.append(r)
    params = _param_list(raw)

    def options(name):
        v = (params.get(name) or {}).get("options")
        return list(v) if isinstance(v, list) else []

    durations = list(raw.get("durations") or []) or options("duration")
    if not durations:
        spec = params.get("duration") or {}
        span = raw.get("duration_range") or ({"min": spec.get("min"), "max": spec.get("max")} if spec.get("max") is not None else None)
        if span and span.get("min") is not None and span.get("max") is not None and 0 < span["max"] - span["min"] <= 40:
            durations = list(range(int(span["min"]), int(span["max"]) + 1))
    resolution_key = "resolution" if options("resolution") else ("quality" if any(str(o).endswith("p") for o in options("quality")) else "resolution")
    return {"id": raw["id"], "name": raw.get("name") or raw["id"], "kind": kind, "durations": durations,
            "resolutions": options(resolution_key), "resolution_key": resolution_key, "aspect_ratios": list(raw.get("aspect_ratios") or []), "roles": roles,
            "supports_unlim": bool(raw.get("supports_unlim")), "supports_audio": "generate_audio" in params, "raw": raw}


def _pick_role(roles: list, *needles, avoid=()):
    for r in roles:
        if all(n in r for n in needles) and not any(a in r for a in avoid):
            return r
    return None


class Higgsfield:
    def __init__(self, mcp: HiggsfieldMCP, *, http_transport=None, poll_s: float = 4.0, wait_timeout_s: float = 1800.0):
        self.mcp = mcp
        self._http_transport = http_transport
        self.poll_s, self.wait_timeout_s = poll_s, wait_timeout_s
        self._models: dict = {}

    # ----------------------------------------------------------------------- catalogue
    def models(self, kind: str = "video") -> list:
        if kind not in self._models:
            rows, after = [], None
            for _ in range(MAX_PAGES):                              # the catalogue is paged (20 by default): follow the cursor to the end
                data = self.mcp.call("models_explore", dict({"action": "list", "type": kind, "limit": PAGE}, **({"after": after} if after else {})))
                rows += data.get("items") or data.get("models") or []
                after = data.get("next_page_token")
                if not (data.get("has_more") and after):
                    break
            self._models[kind] = [normalise_model(m, kind) for m in rows if isinstance(m, dict) and m.get("id")]
        return self._models[kind]

    def model(self, model_id: str, kind: str = "video") -> dict:
        row = next((m for m in self.models(kind) if m["id"] == model_id), None)
        if row is None:
            raise HiggsfieldError(f"no Higgsfield {kind} model {model_id!r}; the models are: {', '.join(m['id'] for m in self.models(kind)[:40])}")
        return row

    def balance(self) -> dict:
        d = self.mcp.call("balance", {})
        return {"plan": d.get("subscription_plan_type") or d.get("plan"), "credits": find_credits(d)}

    # ------------------------------------------------------------------------- uploads
    def upload(self, data: bytes, kind: str, filename: str, content_type: str) -> str:
        """media_upload -> PUT the bytes to the presigned URL -> media_confirm; returns the media id (medias take ids, never URLs)."""
        if len(data) > MAX_UPLOAD_BYTES:
            raise HiggsfieldError(f"{filename} is {len(data) / 1e6:.0f} MB; uploads are capped at {MAX_UPLOAD_BYTES // 1_000_000} MB")
        args = {"files": [{"filename": filename, "content_type": content_type}]}      # no ``type``: the media type is inferred from the extension
        res = self.mcp.call("media_upload", args)
        row = next((n for n in _walk(res) if isinstance(n, dict) and n.get("upload_url")), None)
        if row is None:
            raise HiggsfieldError("media_upload returned no upload_url")
        media_id = str(row.get("media_id") or row.get("id") or "")
        if not media_id:
            raise HiggsfieldError("media_upload returned no media id")
        try:
            with httpx.Client(transport=self._http_transport, timeout=300.0) as client:
                put = client.put(row["upload_url"], content=data, headers={"Content-Type": content_type})
        except httpx.RequestError as exc:
            raise HiggsfieldError(f"the upload of {filename} failed ({type(exc).__name__})") from None
        if put.status_code >= 400:
            raise HiggsfieldError(f"the upload of {filename} was refused (HTTP {put.status_code})")
        self.mcp.call("media_confirm", {"type": kind, "media_ids": [media_id]})
        return media_id

    # --------------------------------------------------------------------- the requests
    def video_args(self, model_id: str, prompt: str, params: dict, images=(), videos=(), audios=()) -> dict:
        """The generate_video arguments in the roles the model takes. image_mode: first_frame | first_last_frame (one image = a loop) |
        reference; with a video the images and the video go to the model's reference roles (motion transfer)."""
        row = self.model(model_id)
        roles = row["roles"]
        args = {"model": model_id, "prompt": prompt}
        for key in ("duration", "resolution", "aspect_ratio", "generate_audio", "count", "seed"):
            if params.get(key) is not None:
                args[row["resolution_key"] if key == "resolution" else key] = params[key]
        medias = []
        mode = params.get("image_mode") or ("reference" if videos else "first_frame")
        images = list(images)
        if images and videos:
            role = _pick_role(roles, "image") or "image_references"
            medias += [{"value": i, "role": role} for i in images]
        elif images and mode in ("first_frame", "first_last_frame"):
            if "start_image" not in roles:
                raise HiggsfieldError(f"{model_id} takes no start_image (its roles: {roles})")
            medias.append({"value": images[0], "role": "start_image"})
            if mode == "first_last_frame":
                if "end_image" not in roles:
                    raise HiggsfieldError(f"{model_id} takes no end_image (its roles: {roles}); first_last_frame needs one")
                medias.append({"value": images[1] if len(images) > 1 else images[0], "role": "end_image"})
        elif images:
            role = _pick_role(roles, "image", "ref") or _pick_role(roles, "image", avoid=("start", "end")) or "image_references"
            medias += [{"value": i, "role": role} for i in images]
        if videos:
            role = _pick_role(roles, "video") or "video_references"
            medias += [{"value": v, "role": role} for v in videos]
        if audios:
            role = _pick_role(roles, "audio") or "audio_references"
            medias += [{"value": a, "role": role} for a in audios]
        if medias:
            args["medias"] = medias
        if params.get("use_unlim") is not None:
            args["use_unlim"] = params["use_unlim"]
        return args

    # ----------------------------------------------------------------- cost and submit
    def call(self, tool: str, args: dict) -> dict:
        """One tool call. ``args`` is the flat request this class builds; the generation tools take it as their single ``params`` argument."""
        return self.mcp.call(tool, {"params": args} if tool in PARAMS_TOOLS else args)

    def cost(self, tool: str, args: dict, literal: bool = False) -> float:
        """The get_cost price (``args`` gains declined_preset_id when a literal retry declined one). A preset recommendation is raised as HiggsfieldPreset; a ``literal`` request retries ONCE declining exactly that id."""
        out = self.call(tool, dict(args, get_cost=True))
        credits = find_credits(out)
        preset = find_preset(out) if credits is None else None
        if preset is not None:
            if not literal:
                raise HiggsfieldPreset(preset)
            args["declined_preset_id"] = preset["id"]               # in place: the real submit must decline it too, or it would be recommended again
            out = self.call(tool, dict(args, get_cost=True))
            credits = find_credits(out)
            again = find_preset(out) if credits is None else None
            if again is not None:
                raise HiggsfieldPreset(again)
        if credits is None:
            raise HiggsfieldError(f"{tool} get_cost returned no price: {str(out)[:200]}")
        return credits

    def submit(self, tool: str, args: dict) -> dict:
        """One submit. ``question`` carries a server-asked ``unlim_choice`` (for the user: never answered here); a transport timeout
        raises and is NOT retried."""
        out = self.call(tool, args)
        question = next((n["unlim_choice"] for n in _walk(out) if isinstance(n, dict) and "unlim_choice" in n), None)
        return {"job_ids": [] if question else find_jobs(out), "question": question, "raw": out}

    # -------------------------------------------------------------------------- wait
    def wait(self, job_ids: list) -> list:
        """jobs_wait (at most 15 s each) until every job is terminal -> [{job_id, status, url}]; a timeout polls the same ids again."""
        deadline = time.monotonic() + self.wait_timeout_s
        final: dict = {}
        while True:
            pending = [j for j in job_ids if j not in final]
            if not pending:
                return [final[j] for j in job_ids]
            try:
                out = self.mcp.call("jobs_wait", {"jobs": [{"index": i, "job_id": j} for i, j in enumerate(job_ids) if j in pending], "timeout_seconds": 15})
            except TransportTimeout:
                out = {}
            for row in (n for n in _walk(out) if isinstance(n, dict) and n.get("job_id")):
                status = str(row.get("status") or "").lower()
                if status in TERMINAL_OK:
                    final[row["job_id"]] = {"job_id": row["job_id"], "status": "completed", "url": _url_of(row)}
                elif status in TERMINAL_BAD:
                    final[row["job_id"]] = {"job_id": row["job_id"], "status": status if status != "cancelled" else "canceled", "url": None,
                                            "error": str(row.get("error") or row.get("message") or "")[:300]}
            if all(j in final for j in job_ids):
                continue
            if time.monotonic() >= deadline:
                raise HiggsfieldError(f"jobs {', '.join(j for j in job_ids if j not in final)} are still running after {self.wait_timeout_s:.0f} s; "
                                      "they are NOT resubmitted: poll them again or check Higgsfield")
            time.sleep(self.poll_s)

    def poll(self, job_ids: list) -> dict:
        """One non-blocking read of jobs already submitted: {job_id: {status, url, error}} for those that are terminal (a restart resumes by id with this)."""
        out = self.mcp.call("jobs_wait", {"jobs": [{"index": i, "job_id": j} for i, j in enumerate(job_ids)], "timeout_seconds": 1})
        final = {}
        for row in (n for n in _walk(out) if isinstance(n, dict) and n.get("job_id")):
            status = str(row.get("status") or "").lower()
            if status in TERMINAL_OK:
                final[row["job_id"]] = {"status": "completed", "url": _url_of(row)}
            elif status in TERMINAL_BAD:
                final[row["job_id"]] = {"status": "failed", "url": None, "error": str(row.get("error") or row.get("message") or "")[:300]}
        return final

    def stream_fetch(self, url: str):
        data, mime = self.download(url)
        return iter([data]), mime, len(data)

    def download(self, url: str) -> tuple:
        from . import egress as EG
        with EG.context(route="higgsfield", kind="file"), httpx.Client(transport=self._http_transport, timeout=300.0, follow_redirects=True) as client:
            resp = client.get(url)
        if resp.status_code >= 400 or not resp.content:
            raise HiggsfieldError(f"downloading the result answered HTTP {resp.status_code}")
        return resp.content, (resp.headers.get("content-type") or "").split(";")[0] or None
