# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""C1 replies for the three wrapper tools, without changing existing tools.

The client returns JSON data; this boundary validates it, encodes TOON and
optionally consumes a temporary, project-relative PNG. The in-app agent keeps
its existing JSON results.
"""
import base64
import copy
from pathlib import Path

from jsonschema import Draft202012Validator

from .agent.server_tools import project_root
from .compute.toon_out import decode, encode, normalize

NAMES = frozenset(("lampway_inspect", "lampway_view", "lampway_blender_docs"))
TRANSPORT_KEYS = frozenset(("success", "output", "traceback", "created_objects",
                            "modified_objects", "deleted_objects", "execution_time"))
_COMMON = {
    "ok": {"type": "boolean"}, "tool": {"type": "string"},
    "description": {"type": "string"}, "view": {"type": "string"},
    "action": {"type": "string"}, "scene": {"type": "string"},
    "count": {"type": "integer", "minimum": 0},
    "total": {"type": "integer", "minimum": 0},
    "data": {"type": "object"}, "skipped": {"type": "array"},
    "error": {"type": "string"}, "code": {"type": "string"},
    "help": {"type": "array", "items": {"type": "string"}},
}
OUTPUT_SCHEMA = {"$schema": "https://json-schema.org/draft/2020-12/schema",
                 "type": "object", "required": ["help"],
                 "properties": _COMMON,
                 "if": {"required": ["error"]},
                 "then": {"required": ["code"]}}


def output_schema(name):
    if name not in NAMES:
        return None
    schema = copy.deepcopy(OUTPUT_SCHEMA)
    required = {"lampway_inspect": ["view", "scene", "count", "total", "data", "skipped", "help"],
                "lampway_view": ["action", "help"],
                "lampway_blender_docs": ["view", "count", "total", "data", "help"]}[name]
    schema["else"] = {"required": required}
    return schema


def refusal(code, error, help_):
    return {"ok": False, "error": error, "code": code, "help": list(help_)}


def argument_error(name, arguments, schema):
    """Refuse new-tool arguments before a script can reach Blender."""
    help_ = [f"{name} {'action' if name == 'lampway_view' else 'view'}=help"]
    if not isinstance(arguments, dict):
        return refusal("bad_argument", "arguments must be a JSON object", help_)
    unknown = set(arguments) - set(schema.get("properties", {}))
    if unknown:
        return refusal("unknown_argument", "Unknown argument: " + ", ".join(sorted(unknown)), help_)
    error = next(iter(Draft202012Validator(schema).iter_errors(arguments)), None)
    if error is not None:
        return refusal("bad_argument", error.message, help_)
    return None


def truncate(value, *, full=False, max_chars=200):
    """Bound long data strings; tool implementations page their list sections."""
    if full:
        return value
    if isinstance(value, str):
        return value if len(value) <= max_chars else (
            value[:max_chars] + f"... (truncated, {len(value)} chars total; full=true)")
    if isinstance(value, list):
        return [truncate(v, max_chars=max_chars) for v in value]
    if isinstance(value, dict):
        return {k: (v if k == "help" else truncate(v, max_chars=max_chars)) for k, v in value.items()}
    return value


class ImageRefusal(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def _image(path, max_bytes):
    """Consume a PNG through anchored descriptors, with a bounded read.

    Platforms without dir_fd and non-following opens refuse image transfer;
    resolving a pathname and then opening it would reopen the jail race.
    """
    import errno
    import io
    import os
    import stat
    from PIL import Image

    needed = (os.open, os.stat, os.unlink)
    if (not all(operation in os.supports_dir_fd for operation in needed)
            or not hasattr(os, 'O_NOFOLLOW') or not hasattr(os, 'O_DIRECTORY')):
        raise ImageRefusal('image_platform_unsupported',
                           'Secure image transfer requires directory-relative, non-following file opens on this platform')
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or not 1 <= max_bytes <= 900000:
        raise ImageRefusal('bad_argument', 'max_bytes must be an integer from 1 to 900000')
    root = project_root().resolve()
    relative = Path(path)
    if relative.is_absolute() or not relative.parts or any(part in ('.', '..') for part in relative.parts):
        raise ImageRefusal('path_outside_project', 'image_path must be a project-relative PNG inside the project root')
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptors = []
    try:
        # Walk the canonical root from its filesystem anchor too: no ancestor
        # pathname can be swapped to a symlink between resolve and open.
        anchor = os.open(root.anchor, directory_flags)
        descriptors.append(anchor)
        for part in (*root.parts[1:], *relative.parts[:-1]):
            anchor = os.open(part, directory_flags, dir_fd=anchor)
            descriptors.append(anchor)
        filename = relative.parts[-1]
        fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, 'O_NONBLOCK', 0), dir_fd=anchor)
        descriptors.append(fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ImageRefusal('bad_image', 'The temporary image must be a regular PNG file')
        if info.st_size > max_bytes:
            raise ImageRefusal('image_too_large', f'PNG exceeds max_bytes={max_bytes}; capture at a smaller size')
        raw = bytearray()
        while len(raw) <= max_bytes:
            chunk = os.read(fd, min(65536, max_bytes + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        if len(raw) > max_bytes:
            raise ImageRefusal('image_too_large', f'PNG exceeds max_bytes={max_bytes}; capture at a smaller size')
        raw = bytes(raw)
        try:
            with Image.open(io.BytesIO(raw)) as png:
                if png.format != 'PNG':
                    raise ValueError('not PNG')
                png.verify()
        except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
            raise ImageRefusal('bad_image', 'The temporary image must be a valid PNG') from exc
        # Do not consume a replacement file. Unlink is relative to the held
        # directory and never follows a swapped final-component symlink.
        current = os.stat(filename, dir_fd=anchor, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
            raise ImageRefusal('image_changed', 'The temporary image changed during capture; capture it again')
        os.unlink(filename, dir_fd=anchor)
        return {'type': 'image', 'mimeType': 'image/png', 'data': base64.b64encode(raw).decode('ascii')}
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise ImageRefusal('path_outside_project', 'image_path cannot traverse symlinks or non-directory parents') from exc
        if exc.errno == errno.ENOENT:
            raise ImageRefusal('image_not_found', 'The temporary image is missing; capture it again') from exc
        raise ImageRefusal('image_read_failed', 'The temporary image could not be read; capture it again') from exc
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def result(request_id, value, *, name=None, full=False, max_bytes=750000):
    """One equivalent TOON/JSON result; help remains the document's final field."""
    if not isinstance(value, dict):
        value = refusal("invalid_result", "Tool did not return an object", [])
    else:
        value = {k: v for k, v in value.items() if k not in TRANSPORT_KEYS}
    image_path = value.pop("image_path", None)
    image = None
    value = normalize(truncate(value, full=full))
    value = {**{k: v for k, v in value.items() if k != "help"}, "help": value.get("help", [])}
    # TOON's numeric model permits the shortest binary64 spelling. Canonicalize
    # JSON from those exact bytes so lossless integer decoders and Python floats
    # cannot disagree about a large integral float in structuredContent.
    text = encode(value)
    value = decode(text)
    error = next(iter(Draft202012Validator(output_schema(name) or OUTPUT_SCHEMA).iter_errors(value)), None)
    if error is not None:
        value = refusal("invalid_result", "Tool result does not match its outputSchema: " + error.message, [])
        text = encode(value)
        image = None
    elif image_path is not None and value.get("ok", True):
        try:
            image = _image(image_path, max_bytes)
        except (ImageRefusal, OSError, TypeError, ValueError) as exc:
            value = refusal(getattr(exc, "code", "image_read_failed"), str(exc), value.get("help", []))
            text = encode(value)
    is_error = value.get("ok") is False or "error" in value
    content = [{"type": "text", "text": text}]
    if image is not None:
        content.append(image)
    return {"jsonrpc": "2.0", "id": request_id,
            "result": {"content": content, "structuredContent": value, "isError": bool(is_error)}}
