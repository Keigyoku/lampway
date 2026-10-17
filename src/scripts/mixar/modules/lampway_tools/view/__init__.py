# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure image bounds and exclusive project output allocation for T2."""
import io
import math
from pathlib import Path

from ..settings import resolve_in_root


class ViewError(ValueError):
    def __init__(self, code, message, help):
        super().__init__(message)
        self.code, self.help = code, help


def reserve_output(root, out):
    """Exclusive-create the destination; only our own reservation may be written."""
    if Path(out).is_absolute():
        from ..settings import PathOutsideProject
        raise PathOutsideProject('out must be project-relative')
    path = resolve_in_root(out, root)
    if path.suffix.lower() != '.png':
        raise ViewError('bad_argument', 'out must name a PNG', ['lampway_view action=help'])
    path.parent.mkdir(parents=True, exist_ok=True)
    for number in range(1, 100001):
        candidate = path if number == 1 else path.with_name(f'{path.stem}-{number}{path.suffix}')
        # Recheck each candidate (including a symlink planted at a numbered path).
        candidate = resolve_in_root(candidate, root)
        try:
            with candidate.open('xb'):
                pass
            return candidate
        except FileExistsError:
            continue
    raise ViewError('output_busy', 'Too many reserved output names', ['lampway_view action=render_still out=renders/<name>.png'])


def crop_png(raw, geometry, rect, max_bytes):
    """Crop the already masked native capture; bottom-left area rect becomes PIL top-left."""
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as source:
        frame = source.convert('RGB')
    if rect is not None:
        x, y, width, height = rect
        sx = frame.width / geometry['window_width']
        sy = frame.height / geometry['window_height']
        frame = frame.crop((round(x * sx), round((geometry['window_height'] - y - height) * sy),
                            round((x + width) * sx), round((geometry['window_height'] - y) * sy)))
    while True:
        stream = io.BytesIO()
        frame.save(stream, format='PNG', optimize=True)
        png = stream.getvalue()
        if len(png) <= max_bytes:
            return png, {'width': frame.width, 'height': frame.height, 'bytes': len(png)}
        if max(frame.size) <= 1:
            raise ViewError('capture_too_large', 'PNG cannot fit max_bytes', ['lampway_view action=screenshot max_bytes=900000'])
        factor = min(0.85, math.sqrt(max_bytes / len(png)) * 0.95)
        frame = frame.resize((max(1, int(frame.width * factor)), max(1, int(frame.height * factor))), Image.Resampling.LANCZOS)
