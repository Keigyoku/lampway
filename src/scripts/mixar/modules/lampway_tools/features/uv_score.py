# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""uv_score: score UV layouts on measurements (uv_islands.py), so candidates are compared by numbers: Smart UV attempts (files, measured in a headless Blender so the live scene
is never touched), Lampway's own unwraps and any object in the scene. ``best`` is advice: the user picks."""

import json
import re
from pathlib import Path

from . import common as C
from . import uv_islands as UI


def rows_for_objects(names, res):
    return [UI.measure_object(C.need_object(n), res) for n in names]


def run(objects, files, res, out, root, gates=None):
    if not 256 <= int(res) <= 4096:
        raise C.FeatureError(f"resolution {res} is out of range 256..4096")
    if not objects and not files:
        raise C.FeatureError("give objects or files to score (no attempts downloaded: run tripo.uv.unwrap / retry first)")
    rows = rows_for_objects(objects or [], res)
    if files:
        rows += _score_files(files, res, root)
    for r in rows:
        if "error" not in r:
            r["gates"] = UI.gate_row(r, gates)
    ok = [r for r in rows if "score" in r]
    best = max(ok, key=lambda r: r["score"])["name"] if ok else None
    body = {"method": "uv_islands.py (the shelf's uv_score.py)", "res": int(res), "rows": rows, "best": best,
            "reasons": ["highest utilization x (1 - overlap) x (1 - off_density_2x) - 0.5 x flipped; advice, the user picks"] if best else []}
    if out:
        p = Path(root) / out
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(body, indent=1))
    return body


def _score_files(files, res, root):
    """Each file is imported by a niced headless Blender (scripts/texlib/uv_score.py) and measured there; refused outside the project root."""
    from .. import runner as RUN
    from .. import settings as S
    import tempfile
    s = S.load()
    paths = []
    for f in files:
        p = Path(f) if Path(f).is_absolute() else Path(root) / f
        if not str(p.resolve()).startswith(str(Path(root).resolve())):
            raise C.FeatureError(f"{f} is outside the project root {root}: copy it in")
        if not p.exists():
            raise C.FeatureError(f"{f} not found")
        paths.append(str(p))
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "rows.json"
        res_ = RUN.run("uv_score", [str(out), str(int(res)), *paths], s, timeout=1800)
        if res_.rc != 0 or not out.exists():
            raise C.FeatureError("uv_score could not measure the files: " + re.sub(r"\s+", " ", res_.stdout)[-300:])
        return json.loads(out.read_text())
