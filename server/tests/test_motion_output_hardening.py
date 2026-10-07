# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Review falsifiers for immutable, jailed motion output and input refusals."""
import pytest

from lampway_server import motion as M
from .fake_motion import FakeCapture
from .test_motion_graphics import put_scene, SMALL


def test_explicit_empty_formats_is_refused():
    with pytest.raises(M.Refused, match="non-empty subset"):
        M.inputs({"scene": "scene", "formats": []})


def test_each_render_preserves_earlier_receipt_and_media(tmp_path):
    scene = put_scene(tmp_path, "repeat", "<!doctype html>")
    args = {"scene": scene, **SMALL, "formats": ["mp4"]}
    first = M.render(tmp_path, args, FakeCapture)
    directory = tmp_path / first["out_dir"]
    original = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
    second = M.render(tmp_path, dict(args, fps=5), FakeCapture)
    third = M.render(tmp_path, args, FakeCapture)
    assert len({first["out_dir"], second["out_dir"], third["out_dir"]}) == 3
    assert {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()} == original
    assert M.verify(tmp_path, {"receipt": str(directory.relative_to(tmp_path) / "receipt.json")}, FakeCapture)["reproduced"]


@pytest.mark.parametrize("component", ["motion", "motion/out"])
def test_output_parent_symlink_cannot_escape_project(tmp_path, component):
    root = tmp_path / "project"
    root.mkdir()
    scene = "scene"
    (root / scene).mkdir()
    (root / scene / "index.html").write_text("<!doctype html>")
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("keep")
    target = root / component
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(outside, target_is_directory=True)
    with pytest.raises(M.Refused, match="outside|symlink"):
        M.render(root, {"scene": scene, **SMALL, "formats": ["mp4"]}, FakeCapture)
    assert list(outside.iterdir()) == [sentinel]
    assert sentinel.read_text() == "keep"


def test_inline_scene_cannot_overwrite_external_entry_symlink(tmp_path):
    outside = tmp_path / "outside.html"
    outside.write_text("keep")
    root = tmp_path / "project"
    directory = root / "motion/scenes/inline"
    directory.mkdir(parents=True)
    (directory / "index.html").symlink_to(outside)
    before = outside.stat().st_mtime_ns
    with pytest.raises(M.Refused):
        M.render(root, {"html": "keep", "name": "inline", **SMALL}, FakeCapture)
    assert outside.stat().st_mtime_ns == before, "refusal must precede writing through the symlink"
    assert outside.read_text() == "keep"
