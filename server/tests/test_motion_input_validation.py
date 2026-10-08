# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Strict wire values and portable provenance; no new resource/retention policy."""
import json

import pytest
from PIL import Image

from lampway_server import motion as M
from lampway_server.motion import check as C
from .fake_motion import FakeCapture


@pytest.mark.parametrize("extra", [
    {"html": {"code": "not HTML"}, "name": "clip"},
    {"scene": 12}, {"entry": []}, {"vault": "false"},
    {"variables": []}, {"template": 42}, {"action": []},
    {"samples": [float("inf")]}, {"samples": [float("nan")]},
    {"variables": {"value": float("nan")}},
    {"variables": {1: "non-string JSON key"}},
    {"html": "inline", "scene": "scene", "name": "clip"},
])
def test_invalid_values_are_refused_before_scene_writes(extra):
    with pytest.raises(M.Refused):
        M.inputs({"scene": "scene", **extra})


@pytest.mark.parametrize("value", [[], "scene", None, 42])
def test_non_object_arguments_are_refused(value):
    with pytest.raises(M.Refused, match="object"):
        M.inputs(value)


def test_verify_validates_its_supplied_wire_values():
    with pytest.raises(M.Refused):
        M.inputs({"action": "verify", "receipt": ["receipt.json"]})
    with pytest.raises(M.Refused):
        M.inputs({"action": "verify", "receipt": "receipt.json", "vault": "false"})


def test_contained_absolute_inputs_write_relative_provenance(tmp_path):
    scene = tmp_path / "scene"
    scene.mkdir()
    entry = scene / "index.html"
    entry.write_text("fixture")
    out = M.render(tmp_path, {"scene": str(scene), "entry": str(entry), "fps": 2,
                              "width": 320, "height": 180, "duration_s": 1,
                              "formats": ["mp4"]}, lambda: FakeCapture())
    receipt = json.loads((tmp_path / out["out_dir"] / "receipt.json").read_text())
    assert receipt["inputs"]["scene"] == "scene"
    assert receipt["inputs"]["entry"] == "index.html"
    assert str(tmp_path) not in receipt["inputs"]["scene"]


@pytest.mark.parametrize("audit", [
    {}, {"text": {}, "marks": []},
    {"text": [{"sel": "#label", "text": "text", "font_px": 24, "opacity": 1,
                "box": [1, 1, float("nan"), 30]}], "marks": []},
    {"text": [], "marks": [{"sel": "figure", "box": [20, 1, 10, 30]}]},
    {"text": [], "marks": [{"sel": [], "box": [1, 1, 10, 30]}]},
    {"text": [{"sel": "#label", "text": [], "font_px": 24, "opacity": 1,
                "box": [1, 1, 10, 30]}], "marks": []},
])
def test_malformed_audit_is_refused(audit):
    with pytest.raises(ValueError, match="audit"):
        C.validate_audit(audit)


@pytest.mark.parametrize("override", [{"box": [70, 30, 30, 60]}, {"opacity": 2}, {"font_px": True}])
def test_invalid_geometry_cannot_silently_pass_pixel_checks(override):
    audit = {"text": [{"sel": "#label", "text": "text", "font_px": 24, "opacity": 0.5,
                       "box": [30, 30, 70, 60], **override}], "marks": []}
    with pytest.raises(ValueError, match="audit"):
        C.findings(Image.new("RGB", (100, 100)), {"detail_share": 0.01}, audit, 100, 100)


def test_identical_inline_scene_preserves_existing_entry(tmp_path, monkeypatch):
    from pathlib import Path
    scene = tmp_path / 'motion/scenes/clip'
    scene.mkdir(parents=True)
    entry = scene / 'index.html'
    entry.write_text('same')
    before = entry.stat()
    outside = tmp_path.parent / (tmp_path.name + '-external.html')
    outside.write_text('untouched')
    write = Path.write_bytes
    def swap_before_write(path, data):
        if path == entry:
            path.unlink()
            path.symlink_to(outside)
        return write(path, data)
    monkeypatch.setattr(Path, 'write_bytes', swap_before_write)
    try:
        M._scene(tmp_path, M.inputs({'html': 'same', 'name': 'clip'}))
    except M.Refused:
        pass
    assert outside.read_text() == 'untouched'
    assert entry.stat().st_mtime_ns == before.st_mtime_ns


def test_new_inline_scene_refuses_entry_swap_without_overwrite(tmp_path, monkeypatch):
    import os
    scene = tmp_path / 'motion/scenes/clip'
    scene.mkdir(parents=True)
    entry = scene / 'index.html'
    outside = tmp_path.parent / (tmp_path.name + '-external.html')
    outside.write_text('untouched')
    original = os.open
    def swap_before_create(path, flags, *args, **kwargs):
        if flags & os.O_CREAT and str(path) == 'index.html':
            entry.symlink_to(outside)
        return original(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, 'open', swap_before_create)
    with pytest.raises(M.Refused):
        M._scene(tmp_path, M.inputs({'html': 'same', 'name': 'clip'}))
    assert outside.read_text() == 'untouched'


def test_large_finite_sample_clamps_without_float_overflow():
    a = M.inputs({'scene': 'scene', 'samples': [10 ** 1000]})
    assert M._sample_frames(30, a['samples'], 30) == [29]


def test_large_duration_is_a_corrective_refusal():
    with pytest.raises(M.Refused, match='duration'):
        M.inputs({'scene': 'scene', 'duration_s': 10 ** 1000})


@pytest.mark.parametrize('key', ['html', 'entry', 'name', 'template', 'variables', 'receipt',
                                 'fps', 'width', 'height', 'duration_s', 'samples', 'action'])
def test_explicit_null_wire_values_are_not_omission(key):
    with pytest.raises(M.Refused):
        M.inputs({'scene': 'scene', key: None})
