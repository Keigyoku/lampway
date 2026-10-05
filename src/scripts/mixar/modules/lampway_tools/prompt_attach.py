# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Carrying a library template on a Video Gen / Image Gen job. ``lampway.prompt_use`` puts the rendered prompt into the surface and remembers which template and
variables made it (on the scene). When the surface builds its job payload it calls ``attach_to``: the template + variables ride on the payload (the server renders
again and records template@version with the run) only while the prompt is still EXACTLY the rendered text; once the user edits it, the job is a raw-prompt job."""

import json

KEY = "lampway_prompt_attach"


def remember(scene, template_id: str, version: str, variables: dict, prompt: str) -> None:
    scene[KEY] = json.dumps({"id": template_id, "version": version, "variables": variables, "prompt": prompt})


def attached(scene, prompt: str):
    raw = scene.get(KEY) if scene is not None else None
    if not raw:
        return None
    data = json.loads(raw)
    return data if data.get("prompt") == (prompt or "").strip() else None


def attach_to(payload: dict, prompt: str, scene) -> dict:
    """Add ``payload['template']`` when the prompt is the attached template's rendered text; returns the payload."""
    data = attached(scene, prompt)
    if data:
        payload["template"] = {"id": data["id"], "version": data["version"], "variables": data["variables"]}
    return payload
