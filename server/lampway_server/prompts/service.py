"""The prompt service the server shares: the library (builtin + user + project), the run log, rendering, and the job hook that renders a payload's
``template`` + ``variables`` and records every image or video job with the rendered prompt."""

from pathlib import Path
from typing import Optional

from . import render as R
from .library import Library, LibraryError
from ..ledger import default_path as ledger_default_path
from .runlog import RunLog

MERGE_VIDEO = ("duration", "resolution", "aspect_ratio", "image_mode", "generate_audio")
MERGE_IMAGE = ("size", "aspect_ratio", "resolution", "quality", "background")


class PromptService:
    def __init__(self, library: Library, runlog: RunLog):
        self.library, self.runlog = library, runlog

    @classmethod
    def from_env(cls, state_dir) -> "PromptService":
        return cls(Library.from_env(), RunLog(ledger_default_path()))

    def render(self, template_id, variables=None, model=None, version=None) -> dict:
        return R.render(self.library, template_id, variables, model, version)

    def apply_to_payload(self, service: str, model: str, payload: dict) -> Optional[dict]:
        """If the payload carries ``template`` ({id, variables?, version?, model?}), render it, set ``payload['prompt']`` and fill the params it does not
        already have; returns the render (or None). Raises RenderError / LibraryError (the caller turns them into a 422)."""
        spec = payload.get("template")
        if not spec:
            return None
        if not isinstance(spec, dict) or not spec.get("id"):
            raise R.RenderError("template must be {id, variables?, version?}")
        rendered = self.render(spec["id"], spec.get("variables"), spec.get("model") or (model if model and model != "default" else None), spec.get("version"))
        payload["prompt"] = rendered["prompt"]
        params = dict(payload.get("params") or {})
        for key in (MERGE_VIDEO if service.startswith("video") else MERGE_IMAGE):
            if key in rendered["params"] and key not in params:
                params[key] = rendered["params"][key]
        payload["params"] = params
        return rendered

    def record_job(self, job, rendered: Optional[dict], *, output: Optional[str] = None, cost=None, extra: Optional[dict] = None) -> None:
        prompt = (rendered or {}).get("prompt") or job.rendered_prompt
        self.runlog.record(job.job_id, prompt=prompt or "", model=(rendered or {}).get("model") or job.model, template=(rendered or {}).get("template"),
                           variables=(rendered or {}).get("variables"), cost=cost, output=output, service=job.service,
                           variant_of=(job.variant_of or None), extra=extra)
