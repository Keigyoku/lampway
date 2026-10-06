"""The thin hooks that feed provenance from the places generations already finish. Each one builds a payload and calls ``provenance.capture`` (which never raises)."""
from __future__ import annotations

import time

from . import provenance as P


def _split_template(t):
    if not t:
        return None, None
    t = str(t)
    return (t.split("@", 1) + [None])[:2] if "@" in t else (t, None)


def job_hook(lib, spool):
    """For ``JobQueue(provenance=...)``: called as ``hook(job, ok, provider)`` while the job's files and payload still exist."""
    def hook(job, ok, provider):
        r = job.result or {}
        outputs = []
        if ok:
            for name, (data, media_type) in job.files.items():
                kind = "video" if str(media_type).startswith("video/") else ("image" if str(media_type).startswith("image/") else None)
                if kind:
                    outputs.append({"bytes": data, "name": f"{job.service} {job.job_id[:8]} {name}", "kind": kind, "role": "main", "attrs": {"media_type": media_type}})
        template_id, template_version = _split_template((job.rendered or {}).get("template") if isinstance(job.rendered, dict) else None)
        usd, credits = r.get("actual_usd"), r.get("credits")
        gen = {"studio": provider or "lampway", "provider": provider, "model": job.model, "action": job.service, "prompt_text": job.rendered_prompt or None,
               "template_id": template_id, "template_version": template_version, "vars": (job.rendered or {}).get("variables") if isinstance(job.rendered, dict) else {},
               "cost_usd": usd, "cost_credits": credits, "cost_basis": "measured" if (usd is not None or credits is not None) else "none", "job_id": job.job_id,
               "started_at": job.created, "finished_at": time.time(), "ok": bool(ok), "error": job.error or None, "params": {"origin": job.origin}}
        return P.capture(lib, spool, {"outputs": outputs, "generation": gen, "tool": job.service})
    return hook
