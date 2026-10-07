# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Everything the client sends with a turn, as the engine's prompt (docs/reports/agent-modes-spec.md R3).

The client sends more than the message (``chat_payloads.build_chat_payload``, ``turn_transport._send``): attached images, the
complete rules snapshot, the context folders it granted, and notes about this turn. The built-in loop read only the message. The
engine's turn gets all of it (spec A2: ``image.attach_bytes`` per image, then ``prompt.submit`` with the text):

* images (``content`` items ``{"type": "image_url", "image_url": {"url": "data:<mime>;base64,..."}}``) -> ``attachments``, one
  ``image.attach_bytes {content_base64, filename}`` each before the prompt (measured on the pinned serve, 2026-10-07);
* the rules snapshot (``{"global": [...], "project": [...]}``, each ``{text, enabled}``) -> a "Your rules" / "Project rules"
  section, sent again only when the enabled set changes for the session (``rules_key`` tracks it);
* ``folder_context`` (``{"folders": [{name, available, file_count, kinds, notes...}]}``) -> a "Context folders" section;
* ``project_context``, ``attachment_names``, ``imported_object_names`` -> a short "This turn" section.

Context management (what is kept, compressed, summarised) is Hermes's (captain's Q3); this module only says what the user sent.
"""

import hashlib
import json
from typing import Optional

MAX_FOLDER_FILES = 40


def _enabled(rules) -> list:
    return [str(r.get("text", "")).strip() for r in (rules or []) if isinstance(r, dict) and r.get("enabled", True) and str(r.get("text", "")).strip()]


def rules_key(snapshot) -> str:
    if not isinstance(snapshot, dict):
        return ""
    data = {"global": _enabled(snapshot.get("global")), "project": _enabled(snapshot.get("project"))}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16] if (data["global"] or data["project"]) else "none"


def rules_section(snapshot) -> str:
    if not isinstance(snapshot, dict):
        return ""
    out = []
    for title, key in (("Your rules (they apply in every project)", "global"), ("Project rules (this file's)", "project")):
        items = _enabled(snapshot.get(key))
        if items:
            out.append(f"{title}:\n" + "\n".join(f"- {t}" for t in items))
    return "\n\n".join(out)


def folders_section(folder_context) -> str:
    folders = (folder_context or {}).get("folders") if isinstance(folder_context, dict) else None
    if not folders:
        return ""
    lines = ["Context folders the user attached (read them with the context_folder tools):"]
    for f in folders:
        if not isinstance(f, dict):
            continue
        if not f.get("available", True):
            lines.append(f"- {f.get('name')}: not reachable on this machine")
            continue
        kinds = ", ".join(f"{k} {v}" for k, v in sorted((f.get("kinds") or {}).items()))
        lines.append(f"- {f.get('name')}: {f.get('file_count', 0)} files{(' (' + kinds + ')') if kinds else ''}"
                     f"{' (listing truncated)' if f.get('truncated') else ''}")
        for name in (f.get("files") or [])[:MAX_FOLDER_FILES]:
            lines.append(f"    {name if isinstance(name, str) else json.dumps(name)}")
        if f.get("notes"):
            lines.append(f"  notes: {str(f['notes'])[:800]}")
    return "\n".join(lines)


def turn_section(payload: dict) -> str:
    lines = []
    if payload.get("attachment_names"):
        lines.append("Images attached in Lampway: " + ", ".join(map(str, payload["attachment_names"])))
    if payload.get("imported_object_names"):
        lines.append("Objects the user just imported: " + ", ".join(map(str, payload["imported_object_names"])))
    if isinstance(payload.get("project_context"), dict) and payload["project_context"]:
        lines.append("Project: " + json.dumps(payload["project_context"], sort_keys=True)[:1500])
    return ("This turn:\n" + "\n".join(lines)) if lines else ""


def images(payload: dict) -> list:
    """(mime, base64) of each attached image."""
    out = []
    for item in payload.get("content") or []:
        url = ((item or {}).get("image_url") or {}).get("url", "") if isinstance(item, dict) else ""
        if url.startswith("data:") and ";base64," in url:
            head, data = url[5:].split(";base64,", 1)
            out.append((head or "image/png", data))
    return out


EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg", "image/webp": "webp", "image/gif": "gif"}


def attachments(payload: Optional[dict]) -> list:
    """(filename, base64) of each attached image, in order: one ``image.attach_bytes`` each before the prompt (spec A2). The name is
    the client's attachment name when it sent one for that position, else ``image-<n>.<ext>``."""
    names = [str(n) for n in ((payload or {}).get("attachment_names") or []) if str(n).strip()]
    out = []
    for i, (mime, data) in enumerate(images(payload or {})):
        name = names[i] if i < len(names) else f"image-{i + 1}.{EXTENSIONS.get(mime.lower(), 'png')}"
        out.append((name, data))
    return out


def prompt_text(text: str, payload: Optional[dict], last_rules_key: str = "") -> tuple:
    """(the prompt's text, the rules key now in force): the message after R3's sections. Rules ride along only when they changed
    for this conversation."""
    payload = payload or {}
    parts = []
    key = rules_key(payload.get("rules")) if "rules" in payload else last_rules_key
    if key and key != last_rules_key and not (key == "none" and not last_rules_key):     # no rules before, none now: nothing to say
        section = rules_section(payload.get("rules"))
        parts.append(section if section else "The user removed every rule: none applies now.")
    for section in (folders_section(payload.get("folder_context")), turn_section(payload)):
        if section:
            parts.append(section)
    body = (text or "").strip()
    return (("\n\n".join(parts) + "\n\n---\n\n" + body) if parts else body), key
